import time, requests, pandas as pd
BASE="https://api.binance.com"
ALLOWED={"ADAUSDT","DOGEUSDT","LINKUSDT","LTCUSDT","SOLUSDT","BNBUSDT","XRPUSDT"}
def get_json(path,attempts=5):
    last=None
    for k in range(attempts):
        try:
            r=requests.get(BASE+path,timeout=12,headers={"User-Agent":"SentinelMarket/GA1"}); r.raise_for_status(); return r.json()
        except Exception as e:
            last=e; time.sleep(min(2**k,16))
    raise RuntimeError(f"market-data failure after retries: {last}")
def closed_hourly_bars(symbol,limit=200):
    if symbol not in ALLOWED: raise ValueError("symbol not allowed")
    raw=get_json(f"/api/v3/klines?symbol={symbol}&interval=1h&limit={int(limit)}")
    now=pd.Timestamp.now(tz="UTC"); rows=[]
    for x in raw:
        ct=pd.to_datetime(x[6],unit="ms",utc=True)
        if ct>=now: continue
        rows.append(dict(symbol=symbol,open_time=pd.to_datetime(x[0],unit="ms",utc=True),close_time=ct,open=float(x[1]),high=float(x[2]),low=float(x[3]),close=float(x[4]),volume=float(x[5])))
    df=pd.DataFrame(rows)
    if len(df)<168: raise RuntimeError(f"insufficient bars {symbol}")
    d=df.open_time.tail(168).diff().dropna().dt.total_seconds()
    if not (d==3600).all(): raise RuntimeError(f"1h candle gap {symbol}")
    return df
