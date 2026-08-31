import numpy as np
import pandas as pd

def add_strategy1_signals(df):
    x = df.copy()

    # Pullback: price close to EMA20, but not deeply below it.
    dist_atr = (x["close"] - x["ema20"]) / x["atr14"].replace(0, np.nan)
    pullback = dist_atr.between(-0.20, 0.65)

    # Resumption: current candle regains short-term strength after a pullback.
    resumption = (
        (x["close"] > x["open"]) &
        (x["close"] > x["close"].shift(1)) &
        (x["close"].shift(1) <= x["close"].shift(2) * 1.003)
    )

    momentum_ok = x["rsi14"].between(50, 68)
    volume_ratio = x["volume"] / x["vol_ma20"].replace(0, np.nan)
    volume_ok = volume_ratio.between(0.85, 2.50)
    volatility_ok = x["vol_ratio"].between(0.65, 1.55)
    risk_ok = x["extreme_risk"] < 55
    regime_ok = x["market_regime"] == "TREND_UP"

    # A new score built around the setup rather than the old generic score.
    trend_strength = np.clip(55 + x["ema_gap_atr"] * 18 + x["ema50_slope"] * 3500, 0, 100)
    pullback_quality = np.clip(100 - np.abs(dist_atr - 0.15) * 70, 0, 100)
    momentum_quality = np.clip(100 - np.abs(x["rsi14"] - 58) * 4, 0, 100)
    volume_quality = np.clip(70 + (volume_ratio - 1.0) * 30, 0, 100)

    x["strategy1_score"] = (
        0.35 * trend_strength +
        0.30 * pullback_quality +
        0.20 * momentum_quality +
        0.15 * volume_quality
    ).clip(0, 100)

    x["strategy1_signal"] = (
        regime_ok & pullback & resumption & momentum_ok &
        volume_ok & volatility_ok & risk_ok
    )
    return x
