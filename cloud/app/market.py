import os, time, requests, pandas as pd

BASE=os.getenv("BINANCE_API_BASE","https://api.binance.com").rstrip("/")
FALLBACK_BASES=tuple(
    base.rstrip("/") for base in os.getenv(
        "BINANCE_FALLBACK_BASES", "https://data.binance.com,https://api.binance.us"
    ).split(",") if base.strip()
)
ALLOWED={"ADAUSDT","DOGEUSDT","LINKUSDT","LTCUSDT","SOLUSDT","BNBUSDT","XRPUSDT"}
_working_base=None

def _normalize_small_gaps(df, symbol, max_gap_hours=24):
    """Represent short no-trade periods as flat, zero-volume hourly bars."""
    if df.empty:
        return df
    df=df.sort_values("open_time").drop_duplicates("open_time",keep="last").set_index("open_time")
    full=pd.date_range(df.index.min(),df.index.max(),freq="1h",tz="UTC")
    missing=~full.isin(df.index)
    longest=run=0
    for is_missing in missing:
        run=run+1 if is_missing else 0
        longest=max(longest,run)
    if longest>max_gap_hours:
        raise RuntimeError(f"1h candle gap too large for {symbol}: {longest}h")
    if missing.any():
        df=df.reindex(full)
        previous_close=df["close"].ffill()
        for column in ("open","high","low","close"):
            df[column]=df[column].fillna(previous_close)
        df["volume"]=df["volume"].fillna(0.0)
        df["symbol"]=df["symbol"].fillna(symbol)
        df["close_time"]=df["close_time"].fillna(
            pd.Series(df.index+pd.Timedelta(hours=1)-pd.Timedelta(milliseconds=1),index=df.index)
        )
    return df.rename_axis("open_time").reset_index()

def get_json(path, attempts=1):
    global _working_base
    last=None
    bases=[]
    for base in ((_working_base,) if _working_base else ()) + (BASE,) + FALLBACK_BASES:
        if base and base not in bases:
            bases.append(base)
    for base in bases:
        for k in range(attempts):
            try:
                r=requests.get(
                    base+path,
                    timeout=(3.05, 8),
                    headers={"User-Agent":"SentinelMarket/GA1"},
                )
                r.raise_for_status()
                _working_base=base
                return r.json()
            except Exception as e:
                last=e
                if k+1 < attempts:
                    time.sleep(1)
    raise RuntimeError(f"market-data failure after retries: {last}")

def closed_hourly_bars(symbol, limit=200):
    if symbol not in ALLOWED: raise ValueError("symbol not allowed")
    required=min(int(limit)-1,720) if int(limit)>200 else 168
    last=None
    for attempt in range(1):
        now=pd.Timestamp.now(tz="UTC")
        end_ms=int((now.floor("h")-pd.Timedelta(milliseconds=1)).timestamp()*1000)
        raw=get_json(f"/api/v3/klines?symbol={symbol}&interval=1h&limit={int(limit)}&endTime={end_ms}")
        rows=[]
        for x in raw:
            close_time=pd.to_datetime(x[6],unit="ms",utc=True)
            if close_time >= now: continue
            rows.append(dict(
              symbol=symbol,
              open_time=pd.to_datetime(x[0],unit="ms",utc=True),
              close_time=close_time, open=float(x[1]), high=float(x[2]), low=float(x[3]),
              close=float(x[4]), volume=float(x[5])
            ))
        df=pd.DataFrame(rows)
        df=_normalize_small_gaps(df,symbol)
        if len(df)>=required:
            d=df.open_time.tail(required).diff().dropna().dt.total_seconds()
            if (d==3600).all():
                return df
            last=RuntimeError(f"1h candle gap detected for {symbol}")
        else:
            last=RuntimeError(f"insufficient completed bars for {symbol}: {len(df)}")
        time.sleep(attempt+1)
    raise last
