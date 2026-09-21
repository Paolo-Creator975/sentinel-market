import os, time, requests, pandas as pd
BASE=os.getenv("BINANCE_API_BASE","https://api.binance.com").rstrip("/")
ALLOWED={"ADAUSDT","DOGEUSDT","LINKUSDT","LTCUSDT","SOLUSDT","BNBUSDT","XRPUSDT"}

def get_json(path, attempts=5):
    last=None
    for k in range(attempts):
        try:
            r=requests.get(BASE+path,timeout=12,headers={"User-Agent":"SentinelMarket/GA1"})
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last=e
            time.sleep(min(2**k,16))
    raise RuntimeError(f"market-data failure after retries: {last}")

def closed_hourly_bars(symbol, limit=200):
    if symbol not in ALLOWED: raise ValueError("symbol not allowed")
    required=min(int(limit)-1,720) if int(limit)>200 else 168
    last=None
    for attempt in range(3):
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
        if len(df)>=required:
            d=df.open_time.tail(required).diff().dropna().dt.total_seconds()
            if (d==3600).all():
                return df
            last=RuntimeError(f"1h candle gap detected for {symbol}")
        else:
            last=RuntimeError(f"insufficient completed bars for {symbol}: {len(df)}")
        time.sleep(attempt+1)
    raise last
