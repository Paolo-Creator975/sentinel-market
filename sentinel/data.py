import time
import pandas as pd
import ccxt

TF_MS = {"15m": 15*60*1000, "1h": 60*60*1000}


def build_exchange(name):
    if not hasattr(ccxt, name):
        raise ValueError(f"Exchange non supportato da CCXT: {name}")
    cls = getattr(ccxt, name)
    ex = cls({"enableRateLimit": True, "timeout": 20000})
    ex.load_markets()
    return ex


def fetch_history(exchange, symbol, timeframe="15m", days=90, limit=1000):
    now = exchange.milliseconds()
    since = now - days * 24 * 60 * 60 * 1000
    step = TF_MS[timeframe]
    all_rows = []
    cursor = since

    for _ in range(500):
        batch = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=cursor, limit=limit)
        if not batch:
            break
        all_rows.extend(batch)
        last_ts = batch[-1][0]
        nxt = last_ts + step
        if nxt <= cursor:
            break
        cursor = nxt
        if cursor >= now - step:
            break
        time.sleep(exchange.rateLimit / 1000.0 if getattr(exchange, "rateLimit", None) else 0.05)

    if not all_rows:
        raise RuntimeError(f"Nessun dato ricevuto per {symbol} {timeframe}")

    df = pd.DataFrame(all_rows, columns=["timestamp","open","high","low","close","volume"])
    df = df.drop_duplicates("timestamp").sort_values("timestamp")
    df = df[df["timestamp"] + step <= now].copy()
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    return df.reset_index(drop=True)


def fetch_history_with_fallback(exchange_candidates, symbol, timeframe="15m", days=90):
    errors = []
    for name in exchange_candidates:
        try:
            ex = build_exchange(name)
            if symbol not in ex.markets:
                errors.append(f"{name}: mercato {symbol} non disponibile")
                continue
            df = fetch_history(ex, symbol, timeframe=timeframe, days=days)
            if len(df) >= 100:
                return name, df
            errors.append(f"{name}: storico insufficiente ({len(df)} righe)")
        except Exception as e:
            errors.append(f"{name}: {type(e).__name__}")
    raise RuntimeError("Nessuna fonte pubblica disponibile. " + " | ".join(errors))
