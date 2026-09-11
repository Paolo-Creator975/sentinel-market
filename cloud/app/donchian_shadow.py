"""Pure calculations for the frozen Donchian shadow candidate."""

import math

import pandas as pd


MINIMUM_BARS = 721


def calculate_snapshot(bars, config):
    if len(bars) < MINIMUM_BARS:
        raise RuntimeError(f"Donchian warm-up requires {MINIMUM_BARS} closed bars; got {len(bars)}")
    frame = bars.sort_values("open_time").drop_duplicates("open_time").copy()
    continuity = frame.open_time.tail(MINIMUM_BARS).diff().dropna().dt.total_seconds()
    if not (continuity == 3600).all():
        raise RuntimeError("Donchian warm-up contains an hourly gap")

    close = frame.close
    prior_high = frame.high.shift(1)
    prior_low = frame.low.shift(1)
    lookback = int(config["lookback_hours"])
    exit_lookback = int(config["exit_lookback_hours"])
    high = prior_high.rolling(lookback).max()
    low = prior_low.rolling(exit_lookback).min()
    ema = close.ewm(span=720, adjust=False, min_periods=720).mean()
    volatility = close.pct_change().rolling(168).std() * math.sqrt(24 * 365)
    last = frame.iloc[-1]
    next_open = last.open_time + pd.Timedelta(hours=1)
    breakout = bool(last.close > high.iloc[-1])
    trend_ok = bool(last.close > ema.iloc[-1])
    daily_decision = next_open.hour == 0
    return {
        "symbol": str(last.symbol),
        "signal_time": last.close_time,
        "bar_close": float(last.close),
        "high_336": float(high.iloc[-1]),
        "low_168": float(low.iloc[-1]),
        "ema_720": float(ema.iloc[-1]),
        "vol_168": float(volatility.iloc[-1]),
        "breakout": breakout,
        "trend_ok": trend_ok,
        "daily_decision": daily_decision,
        "entry_signal": bool(daily_decision and breakout and trend_ok),
        "exit_signal": bool(last.close < low.iloc[-1]),
    }


def position_weight(volatility, config):
    cap = float(config["allocation_cap_per_position"])
    target = float(config["annualized_volatility_target_for_weighting"])
    if not math.isfinite(volatility) or volatility <= 0:
        raise ValueError("volatility must be positive and finite")
    return min(cap, cap * target / volatility)
