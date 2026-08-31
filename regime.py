import numpy as np
import pandas as pd

def add_regime_features(df):
    x = df.copy()
    x["ema50_slope"] = x["ema50"].pct_change(8)
    x["atr_pct"] = x["atr14"] / x["close"]
    x["atr_pct_median"] = x["atr_pct"].rolling(200).median()
    x["vol_ratio"] = x["atr_pct"] / x["atr_pct_median"].replace(0, np.nan)
    x["ema_gap_atr"] = (x["ema20"] - x["ema50"]).abs() / x["atr14"].replace(0, np.nan)

    up = (
        (x["close"] > x["ema20"]) &
        (x["ema20"] > x["ema50"]) &
        (x["ema50_slope"] > 0.0015) &
        (x["ema_gap_atr"] > 0.35)
    )
    down = (
        (x["close"] < x["ema20"]) &
        (x["ema20"] < x["ema50"]) &
        (x["ema50_slope"] < -0.0015) &
        (x["ema_gap_atr"] > 0.35)
    )
    high_vol = x["vol_ratio"] > 1.65

    x["market_regime"] = np.select(
        [high_vol, up, down],
        ["HIGH_VOL", "TREND_UP", "TREND_DOWN"],
        default="SIDEWAYS"
    )
    return x
