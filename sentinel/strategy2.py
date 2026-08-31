import numpy as np
import pandas as pd

# SENTINEL V1.6 - FROZEN STRATEGY 2 SPECIFICATION
# This rule set is deliberately fixed before any final-test inspection.
STRATEGY2_PARAMS = {
    "breakout_lookback": 20,
    "ema_slope_lookback": 4,
    "min_ema20_slope_atr": 0.10,
    "rsi_min": 55.0,
    "rsi_max": 72.0,
    "volume_ratio_min": 1.05,
    "volume_ratio_max": 3.00,
    "vol_ratio_min": 0.65,
    "vol_ratio_max": 1.60,
    "extreme_risk_max": 65.0,
    "stop_atr": 1.50,
    "rr": 2.00,
    "max_holding_bars": 32
}


def add_strategy2_signals(df):
    """Frozen structural hypothesis: trend breakout with participation."""
    x = df.copy()
    p = STRATEGY2_PARAMS

    x["prev_high20"] = x["high"].shift(1).rolling(p["breakout_lookback"]).max()
    x["volume_ratio_s2"] = x["volume"] / x["vol_ma20"].replace(0, np.nan)
    x["ema20_slope_atr_s2"] = (
        x["ema20"] - x["ema20"].shift(p["ema_slope_lookback"])
    ) / x["atr14"].replace(0, np.nan)

    trend_ok = (
        (x["close"] > x["ema20"]) &
        (x["ema20"] > x["ema50"]) &
        (x["ema20_slope_atr_s2"] > p["min_ema20_slope_atr"])
    )

    breakout_ok = x["close"] > x["prev_high20"]
    momentum_ok = x["rsi14"].between(p["rsi_min"], p["rsi_max"])
    volume_ok = x["volume_ratio_s2"].between(
        p["volume_ratio_min"], p["volume_ratio_max"]
    )
    volatility_ok = x["vol_ratio"].between(
        p["vol_ratio_min"], p["vol_ratio_max"]
    )
    risk_ok = x.get(
        "extreme_risk", pd.Series(0.0, index=x.index)
    ).fillna(0) < p["extreme_risk_max"]

    x["strategy2_signal"] = (
        trend_ok &
        breakout_ok &
        momentum_ok &
        volume_ok &
        volatility_ok &
        risk_ok
    ).fillna(False)

    x["strategy2_score"] = (
        25 * trend_ok.astype(float) +
        25 * breakout_ok.astype(float) +
        20 * momentum_ok.astype(float) +
        15 * volume_ok.astype(float) +
        10 * volatility_ok.astype(float) +
        5 * risk_ok.astype(float)
    ).clip(0, 100)

    return x
