import pandas as pd
from .strategy2 import STRATEGY2_PARAMS

def simulate_strategy2(df, cfg):
    """Backtest the frozen Strategy 2 without parameter search."""
    x = df.reset_index(drop=True).copy()
    p = STRATEGY2_PARAMS
    capital = float(cfg["starting_capital"])
    risk_pct = float(cfg["risk_per_trade_pct"]) / 100.0
    max_pos = float(cfg["max_position_pct"]) / 100.0
    costs = (
        float(cfg["fee_pct_roundtrip"]) +
        float(cfg["slippage_pct_roundtrip"])
    ) / 100.0

    trades = []
    inpos = False

    for i in range(220, len(x) - 1):
        r = x.iloc[i]

        if not inpos:
            if not bool(r.get("strategy2_signal", False)):
                continue
            atr = float(r.get("atr14", 0) or 0)
            if atr <= 0:
                continue

            entry = float(r["close"])
            stop = entry - p["stop_atr"] * atr
            risk_unit = max(entry - stop, entry * 0.001)
            target = entry + p["rr"] * risk_unit
            risk_eur = capital * risk_pct
            size = min(risk_eur / risk_unit, (capital * max_pos) / entry)
            if size <= 0:
                continue

            inpos = True
            ei = i
            score = float(r.get("strategy2_score", 0) or 0)
            regime = str(r.get("market_regime", "N/D"))
            continue

        exitp = None
        reason = None

        # Conservative convention: if stop and target are touched in the same
        # candle, STOP is evaluated first because intrabar order is unknown.
        if float(r["low"]) <= stop:
            exitp, reason = stop, "STOP"
        elif float(r["high"]) >= target:
            exitp, reason = target, "TARGET"
        elif i - ei >= p["max_holding_bars"]:
            exitp, reason = float(r["close"]), "TIME"

        if exitp is not None:
            gross = (exitp - entry) * size
            position_eur = entry * size
            pnl = gross - position_eur * costs
            capital += pnl
            trades.append({
                "entry_time": x.iloc[ei]["datetime"],
                "exit_time": r["datetime"],
                "entry": entry,
                "exit": exitp,
                "stop": stop,
                "target": target,
                "position_eur": position_eur,
                "score": score,
                "regime": regime,
                "reason": reason,
                "pnl_eur": pnl,
                "capital_after": capital
            })
            inpos = False

    return pd.DataFrame(trades)
