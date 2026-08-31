import numpy as np
import pandas as pd


def add_strategy2_signals(df):
    """Frozen Strategy 2 hypothesis: trend breakout with participation.

    Rules are intentionally simple and fixed before validation/test:
    - established uptrend (EMA20 > EMA50, positive EMA20 slope)
    - close breaks the previous 20-candle high
    - RSI confirms momentum without extreme extension
    - volume participation above its 20-candle average
    - volatility is not in an extreme state
    """
    x = df.copy()

    x["prev_high20"] = x["high"].shift(1).rolling(20).max()
    x["volume_ratio"] = x["volume"] / x["vol_ma20"].replace(0, np.nan)
    x["ema20_slope_atr"] = (x["ema20"] - x["ema20"].shift(4)) / x["atr14"].replace(0, np.nan)

    trend_ok = (
        (x["close"] > x["ema20"]) &
        (x["ema20"] > x["ema50"]) &
        (x["ema20_slope_atr"] > 0.10)
    )
    breakout_ok = x["close"] > x["prev_high20"]
    momentum_ok = x["rsi14"].between(55, 72)
    volume_ok = x["volume_ratio"].between(1.05, 3.00)
    volatility_ok = x["vol_ratio"].between(0.65, 1.60)
    risk_ok = x.get("extreme_risk", pd.Series(0, index=x.index)).fillna(0) < 65

    x["strategy2_signal"] = (
        trend_ok & breakout_ok & momentum_ok & volume_ok & volatility_ok & risk_ok
    ).fillna(False)

    # Diagnostic score only; it does not alter the frozen entry rule.
    score = (
        25 * trend_ok.astype(float) +
        25 * breakout_ok.astype(float) +
        20 * momentum_ok.astype(float) +
        15 * volume_ok.astype(float) +
        10 * volatility_ok.astype(float) +
        5 * risk_ok.astype(float)
    )
    x["strategy2_score"] = score.clip(0, 100)
    return x
