import pandas as pd

def simulate_strategy1(df, cfg, threshold=70, rr=2.0):
    x = df.reset_index(drop=True).copy()
    capital = float(cfg["starting_capital"])
    risk_pct = float(cfg["risk_per_trade_pct"]) / 100
    max_pos = float(cfg["max_position_pct"]) / 100
    costs = (float(cfg["fee_pct_roundtrip"]) + float(cfg["slippage_pct_roundtrip"])) / 100
    trades = []
    inpos = False

    for i in range(220, len(x)-1):
        r = x.iloc[i]
        if not inpos:
            if (
                not bool(r.get("strategy1_signal", False)) or
                pd.isna(r.get("strategy1_score")) or
                float(r["strategy1_score"]) < threshold
            ):
                continue

            entry = float(r["close"])
            # Technical/volatility stop: below EMA20 or 1.25 ATR, whichever gives room.
            stop = min(float(r["ema20"] - 0.35*r["atr14"]), entry - 1.25*float(r["atr14"]))
            risk_unit = max(entry-stop, entry*0.001)
            target = entry + rr*risk_unit
            risk_eur = capital*risk_pct
            size = min(risk_eur/risk_unit, (capital*max_pos)/entry)
            if size <= 0:
                continue
            inpos = True
            ei = i
            score = float(r["strategy1_score"])
            regime = str(r["market_regime"])
            continue

        r = x.iloc[i]
        exitp = None
        reason = None
        if r["low"] <= stop:
            exitp, reason = stop, "STOP"
        elif r["high"] >= target:
            exitp, reason = target, "TARGET"
        elif i-ei >= 24:
            exitp, reason = float(r["close"]), "TIME"

        if exitp is not None:
            gross = (exitp-entry)*size
            pos = entry*size
            pnl = gross-pos*costs
            capital += pnl
            trades.append({
                "entry_time": x.iloc[ei]["datetime"], "exit_time": r["datetime"],
                "entry": entry, "exit": exitp, "stop": stop, "target": target,
                "position_eur": pos, "score": score, "regime": regime,
                "reason": reason, "pnl_eur": pnl, "capital_after": capital
            })
            inpos = False

    return pd.DataFrame(trades)
