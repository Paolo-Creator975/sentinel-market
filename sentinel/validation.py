import pandas as pd
import numpy as np
from .backtest import simulate, metrics

def chronological_split(df, train_pct=0.60, validation_pct=0.20):
    n = len(df)
    a = int(n * train_pct)
    b = int(n * (train_pct + validation_pct))
    return df.iloc[:a].copy(), df.iloc[a:b].copy(), df.iloc[b:].copy()

def evaluate_period(df, cfg):
    trades = simulate(df, cfg)
    return trades, metrics(trades, float(cfg["starting_capital"]))

def verdict(m):
    if m["trades"] < 30:
        return "CAMPIONE INSUFFICIENTE"
    pf = m["profit_factor"]
    if (not np.isfinite(pf)) or pf <= 1.0 or m["net_return_pct"] <= 0:
        return "NON SUPERA IL TEST"
    if m["max_drawdown_pct"] < -15:
        return "RISCHIO ECCESSIVO"
    return "PROMETTENTE"

def score_calibration(trades):
    if trades.empty:
        return pd.DataFrame(columns=["fascia_score","n","win_rate","pnl_medio_eur"])
    t = trades.copy()
    bins = [0,60,70,80,90,101]
    labels = ["0-59","60-69","70-79","80-89","90-100"]
    t["fascia_score"] = pd.cut(t["score"], bins=bins, labels=labels, right=False)
    out = t.groupby("fascia_score", observed=False).agg(
        n=("pnl_eur","size"),
        win_rate=("pnl_eur", lambda s: (s>0).mean()*100 if len(s) else np.nan),
        pnl_medio_eur=("pnl_eur","mean")
    ).reset_index()
    return out

def parameter_sweep(train_df, base_cfg):
    # Piccola griglia trasparente: serve per ricerca, NON per dichiarare un vincitore definitivo.
    rows = []
    for threshold in [70, 75, 80, 85]:
        for rr in [1.5, 2.0, 2.5]:
            cfg = dict(base_cfg)
            cfg["score_threshold"] = threshold
            cfg["min_rr"] = rr
            trades, m = evaluate_period(train_df, cfg)
            rows.append({
                "score_threshold": threshold,
                "rr": rr,
                "trades": m["trades"],
                "win_rate": m["win_rate"],
                "profit_factor": m["profit_factor"],
                "net_return_pct": m["net_return_pct"],
                "max_drawdown_pct": m["max_drawdown_pct"],
                "expectancy_eur": m["expectancy_eur"]
            })
    return pd.DataFrame(rows)
