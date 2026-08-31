import numpy as np
import pandas as pd


def simulate(df, cfg):
    """
    Backtest legacy Strategy Zero.
    Kept for V1.2 validation compatibility.
    """
    x = df.reset_index(drop=True).copy()
    capital = float(cfg["starting_capital"])
    risk_pct = float(cfg["risk_per_trade_pct"]) / 100
    max_pos = float(cfg["max_position_pct"]) / 100
    rr = float(cfg["min_rr"])
    threshold = float(cfg["score_threshold"])
    costs = (
        float(cfg["fee_pct_roundtrip"]) +
        float(cfg["slippage_pct_roundtrip"])
    ) / 100

    trades = []
    inpos = False

    for i in range(60, len(x) - 1):
        r = x.iloc[i]

        if not inpos:
            score = float(r.get("score", 0) or 0)
            if score < threshold:
                continue

            entry = float(r["close"])
            atr = float(r.get("atr14", 0) or 0)
            if atr <= 0:
                continue

            stop = entry - 1.25 * atr
            risk_unit = max(entry - stop, entry * 0.001)
            target = entry + rr * risk_unit

            risk_eur = capital * risk_pct
            size = min(
                risk_eur / risk_unit,
                (capital * max_pos) / entry
            )
            if size <= 0:
                continue

            inpos = True
            entry_i = i
            continue

        exit_price = None
        reason = None

        if float(r["low"]) <= stop:
            exit_price = stop
            reason = "STOP"
        elif float(r["high"]) >= target:
            exit_price = target
            reason = "TARGET"
        elif i - entry_i >= 24:
            exit_price = float(r["close"])
            reason = "TIME"

        if exit_price is not None:
            gross = (exit_price - entry) * size
            position_eur = entry * size
            pnl = gross - position_eur * costs
            capital += pnl

            trades.append({
                "entry_time": x.iloc[entry_i]["datetime"],
                "exit_time": r["datetime"],
                "entry": entry,
                "exit": exit_price,
                "stop": stop,
                "target": target,
                "position_eur": position_eur,
                "score": float(x.iloc[entry_i].get("score", 0) or 0),
                "reason": reason,
                "pnl_eur": pnl,
                "capital_after": capital,
            })
            inpos = False

    return pd.DataFrame(trades)


def metrics(trades, starting_capital):
    """
    Common performance metrics used by both Strategy Zero and Strategy 1.
    """
    starting_capital = float(starting_capital)

    if trades is None or len(trades) == 0:
        return {
            "trades": 0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "net_return_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "expectancy_eur": 0.0,
        }

    t = trades.copy()
    pnl = pd.to_numeric(t["pnl_eur"], errors="coerce").fillna(0.0)

    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]

    gross_profit = float(wins.sum())
    gross_loss = abs(float(losses.sum()))

    if gross_loss == 0:
        profit_factor = np.inf if gross_profit > 0 else 0.0
    else:
        profit_factor = gross_profit / gross_loss

    total_pnl = float(pnl.sum())
    net_return_pct = (total_pnl / starting_capital) * 100 if starting_capital else 0.0
    win_rate = (float((pnl > 0).mean()) * 100) if len(pnl) else 0.0
    expectancy = float(pnl.mean()) if len(pnl) else 0.0

    equity = starting_capital + pnl.cumsum()
    running_max = equity.cummax()
    drawdown_pct = ((equity / running_max) - 1.0) * 100
    max_drawdown_pct = float(drawdown_pct.min()) if len(drawdown_pct) else 0.0

    return {
        "trades": int(len(t)),
        "win_rate": win_rate,
        "profit_factor": float(profit_factor),
        "net_return_pct": net_return_pct,
        "max_drawdown_pct": max_drawdown_pct,
        "expectancy_eur": expectancy,
    }
