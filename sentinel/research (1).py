import numpy as np
import pandas as pd

def enrich_trades(trades, df):
    if trades is None or trades.empty:
        return pd.DataFrame()
    x = df.copy()
    cols = [
        "datetime","market_regime","rsi14","atr14","vol_ratio",
        "ema_gap_atr","strategy1_score","volume","vol_ma20","close","ema20","ema50"
    ]
    cols = [c for c in cols if c in x.columns]
    snap = x[cols].copy().rename(columns={"datetime":"entry_time"})
    t = trades.merge(snap, on="entry_time", how="left")
    if "volume" in t.columns and "vol_ma20" in t.columns:
        t["volume_ratio"] = t["volume"] / t["vol_ma20"].replace(0, np.nan)
    if "close" in t.columns and "ema20" in t.columns and "atr14" in t.columns:
        t["dist_ema20_atr"] = (t["close"] - t["ema20"]) / t["atr14"].replace(0, np.nan)
    t["winner"] = t["pnl_eur"] > 0
    return t

def winner_loser_profile(enriched):
    if enriched is None or enriched.empty:
        return pd.DataFrame()
    features = [
        "strategy1_score","rsi14","vol_ratio","ema_gap_atr",
        "volume_ratio","dist_ema20_atr"
    ]
    rows = []
    for feat in features:
        if feat not in enriched.columns:
            continue
        for label, subset in [("WIN", enriched[enriched["winner"]]), ("LOSS", enriched[~enriched["winner"]])]:
            s = pd.to_numeric(subset[feat], errors="coerce").dropna()
            if len(s) == 0:
                continue
            rows.append({
                "feature": feat,
                "gruppo": label,
                "n": int(len(s)),
                "media": float(s.mean()),
                "mediana": float(s.median()),
                "q25": float(s.quantile(.25)),
                "q75": float(s.quantile(.75)),
            })
    return pd.DataFrame(rows)

def regime_performance(enriched):
    if enriched is None or enriched.empty or "market_regime" not in enriched.columns:
        return pd.DataFrame()
    return enriched.groupby("market_regime").agg(
        trade=("pnl_eur","size"),
        win_rate=("winner","mean"),
        pnl_medio=("pnl_eur","mean"),
        pnl_totale=("pnl_eur","sum")
    ).reset_index().assign(win_rate=lambda d: d["win_rate"]*100)

def exit_performance(enriched):
    if enriched is None or enriched.empty:
        return pd.DataFrame()
    return enriched.groupby("reason").agg(
        trade=("pnl_eur","size"),
        win_rate=("winner","mean"),
        pnl_medio=("pnl_eur","mean"),
        pnl_totale=("pnl_eur","sum")
    ).reset_index().assign(win_rate=lambda d: d["win_rate"]*100)

def score_bands(enriched):
    if enriched is None or enriched.empty or "score" not in enriched.columns:
        return pd.DataFrame()
    t = enriched.copy()
    t["score_band"] = pd.cut(
        t["score"], bins=[0,70,75,80,85,90,101],
        labels=["<70","70-74","75-79","80-84","85-89","90-100"],
        right=False
    )
    return t.groupby("score_band", observed=False).agg(
        trade=("pnl_eur","size"),
        win_rate=("winner","mean"),
        pnl_medio=("pnl_eur","mean"),
        pnl_totale=("pnl_eur","sum")
    ).reset_index().assign(win_rate=lambda d: d["win_rate"]*100)

def research_summary(enriched):
    if enriched is None or enriched.empty:
        return {
            "trades":0, "wins":0, "losses":0, "win_rate":0.0,
            "avg_win":0.0, "avg_loss":0.0, "payoff":0.0
        }
    wins = enriched.loc[enriched["pnl_eur"]>0, "pnl_eur"]
    losses = enriched.loc[enriched["pnl_eur"]<0, "pnl_eur"]
    avg_win = float(wins.mean()) if len(wins) else 0.0
    avg_loss = abs(float(losses.mean())) if len(losses) else 0.0
    payoff = avg_win/avg_loss if avg_loss > 0 else np.inf if avg_win > 0 else 0.0
    return {
        "trades": int(len(enriched)),
        "wins": int((enriched["pnl_eur"]>0).sum()),
        "losses": int((enriched["pnl_eur"]<0).sum()),
        "win_rate": float((enriched["pnl_eur"]>0).mean()*100),
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "payoff": float(payoff),
    }
