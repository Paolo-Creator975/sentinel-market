"""Pure calculations for the crypto-only 24-hour paper demo."""

import math

import pandas as pd


MINIMUM_BARS = 721


def _clamp(value, low=0.0, high=1.0):
    return max(low, min(high, float(value)))


def calculate_opportunity(bars, config, news_state="UNAVAILABLE", data_ok=True):
    """Return an hourly, look-ahead-safe opportunity assessment."""
    if len(bars) < MINIMUM_BARS:
        raise RuntimeError(f"Crypto 24H warm-up requires {MINIMUM_BARS} closed bars; got {len(bars)}")
    frame = bars.sort_values("open_time").drop_duplicates("open_time").copy()
    continuity = frame.open_time.tail(MINIMUM_BARS).diff().dropna().dt.total_seconds()
    if not (continuity == 3600).all():
        raise RuntimeError("Crypto 24H warm-up contains an hourly gap")

    last = frame.iloc[-1]
    close = frame.close.astype(float)
    high_series = frame.high.astype(float).shift(1).rolling(int(config["breakout_lookback_hours"])).max()
    prior_high = high_series.iloc[-1]
    ema = close.ewm(span=int(config["trend_ema_hours"]), adjust=False,
                    min_periods=int(config["trend_ema_hours"])).mean().iloc[-1]
    returns = close.pct_change()
    volatility = returns.rolling(int(config["volatility_lookback_hours"])).std().iloc[-1]
    momentum = close.iloc[-1] / close.iloc[-int(config["momentum_lookback_hours"])-1] - 1
    volume_median = frame.volume.astype(float).shift(1).rolling(
        int(config["liquidity_lookback_hours"])).median().iloc[-1]
    volume_ratio = float(last.volume) / volume_median if volume_median > 0 else 0.0

    breakout = bool(last.close > prior_high)
    new_breakout = bool(breakout and close.iloc[-2] <= high_series.iloc[-2])
    breakout_distance = float(last.close) / prior_high - 1
    trend_distance = float(last.close) / ema - 1
    vol_floor = max(float(volatility), 1e-9)
    components = {
        "breakout": _clamp(0.5 + breakout_distance / (4 * vol_floor)),
        "trend": _clamp(0.5 + trend_distance / (8 * vol_floor)),
        "momentum": _clamp(0.5 + momentum / (12 * vol_floor)),
        "liquidity": _clamp(volume_ratio / float(config["full_liquidity_volume_ratio"])),
    }
    weights = config["observable_score_weights"]
    score = 100 * sum(components[k] * float(weights[k]) for k in components) / sum(
        float(weights[k]) for k in components
    )

    reasons = []
    if not data_ok or not all(math.isfinite(float(x)) for x in
                              [last.close, prior_high, ema, volatility, volume_ratio, score]):
        decision = "BLOCKED_DATA"
        reasons.append("market_data_invalid")
    elif volume_ratio < float(config["minimum_volume_ratio"]):
        decision = "REJECT"
        reasons.append("insufficient_liquidity")
    elif news_state == "CONFLICT":
        decision = "WAIT"
        reasons.append("price_news_conflict")
    elif (new_breakout and last.close > ema and
          score >= float(config["candidate_score_floor"])):
        decision = "TECHNICAL_CANDIDATE" if news_state == "UNAVAILABLE" else "CANDIDATE"
        reasons.append("hourly_breakout_with_positive_trend")
    else:
        decision = "WATCH"
        reasons.append("setup_incomplete")

    return {
        "symbol": str(last.symbol), "signal_time": last.close_time,
        "bar_close": float(last.close), "prior_high": float(prior_high),
        "ema": float(ema), "hourly_volatility": float(volatility),
        "momentum": float(momentum), "volume_ratio": float(volume_ratio),
        "breakout": breakout, "new_breakout": new_breakout, "trend_ok": bool(last.close > ema),
        "score": float(score), "decision": decision, "reasons": reasons,
        "news_state": news_state,
    }


def drawdown_risk_multiplier(equity, reference_equity):
    """User-approved €1000 ladder: reduce at -10/-20%, block at -30%."""
    if reference_equity <= 0 or equity < 0:
        raise ValueError("equity values must be valid")
    ratio = equity / reference_equity
    if ratio <= 0.70:
        return 0.0
    if ratio <= 0.80:
        return 0.25
    if ratio <= 0.90:
        return 0.50
    return 1.0


def available_risk(equity, reference_equity, open_risk, max_total_risk_rate=0.10):
    """Maximum additional loss budget; never exceeds 10% aggregate open risk."""
    multiplier = drawdown_risk_multiplier(equity, reference_equity)
    total_cap = max(0.0, equity * float(max_total_risk_rate) * multiplier)
    return max(0.0, total_cap - max(0.0, float(open_risk)))


def plan_paper_position(entry_price, hourly_volatility, score, equity,
                        reference_equity, open_risk, config):
    """Size a no-leverage paper position from its maximum loss, not its notional."""
    if entry_price <= 0 or equity <= 0 or not math.isfinite(hourly_volatility):
        raise ValueError("position inputs must be positive and finite")
    risk_room = available_risk(
        equity, reference_equity, open_risk,
        config["maximum_aggregate_open_risk_rate"])
    score_span = max(1.0, 100.0-float(config["candidate_score_floor"]))
    quality = _clamp((float(score)-float(config["candidate_score_floor"]))/score_span)
    desired_rate = (float(config["minimum_position_risk_rate"]) + quality *
                    (float(config["maximum_position_risk_rate"])-
                     float(config["minimum_position_risk_rate"])))
    desired_risk = equity * desired_rate
    risk_eur = min(risk_room, desired_risk)
    stop_rate = max(float(config["minimum_stop_distance_rate"]), min(
        float(config["maximum_stop_distance_rate"]),
        float(hourly_volatility)*float(config["stop_volatility_multiplier"])))
    notional = min(risk_eur/stop_rate if stop_rate else 0.0,
                   equity*float(config["maximum_position_notional_rate"]))
    risk_eur = notional*stop_rate
    if risk_eur <= 0:
        return None
    return {
        "notional_eur": notional,
        "risk_eur": risk_eur,
        "stop_price": entry_price*(1-stop_rate),
        "first_target_price": entry_price*(1+stop_rate*float(config["first_profit_r_multiple"])),
        "stop_distance_rate": stop_rate,
    }
