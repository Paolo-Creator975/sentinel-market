import numpy as np
import pandas as pd

FEATURES = [
    "strategy1_score",
    "rsi14",
    "vol_ratio",
    "ema_gap_atr",
    "volume_ratio",
    "dist_ema20_atr",
]

def _safe_numeric(s):
    return pd.to_numeric(s, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()

def feature_separation(train_enriched):
    if train_enriched is None or train_enriched.empty:
        return pd.DataFrame()

    rows = []
    for feat in FEATURES:
        if feat not in train_enriched.columns:
            continue

        win = _safe_numeric(train_enriched.loc[train_enriched["winner"], feat])
        loss = _safe_numeric(train_enriched.loc[~train_enriched["winner"], feat])

        if len(win) < 3 or len(loss) < 3:
            continue

        pooled = np.sqrt((win.var(ddof=1) + loss.var(ddof=1)) / 2)
        effect = (win.mean() - loss.mean()) / pooled if pooled and np.isfinite(pooled) else 0.0

        rows.append({
            "feature": feat,
            "n_win": int(len(win)),
            "n_loss": int(len(loss)),
            "media_win": float(win.mean()),
            "media_loss": float(loss.mean()),
            "differenza": float(win.mean() - loss.mean()),
            "effect_size": float(effect),
            "abs_effect": abs(float(effect)),
        })

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows).sort_values("abs_effect", ascending=False)


def quantile_discovery(train_enriched):
    if train_enriched is None or train_enriched.empty:
        return pd.DataFrame()

    rows = []

    for feat in FEATURES:
        if feat not in train_enriched.columns:
            continue

        t = train_enriched[[feat, "pnl_eur", "winner"]].copy()
        t[feat] = pd.to_numeric(t[feat], errors="coerce")
        t = t.dropna()

        if len(t) < 15 or t[feat].nunique() < 4:
            continue

        try:
            t["bucket"] = pd.qcut(t[feat], q=3, duplicates="drop")
        except Exception:
            continue

        for bucket, g in t.groupby("bucket", observed=False):
            if len(g) == 0:
                continue

            rows.append({
                "feature": feat,
                "bucket": str(bucket),
                "n": int(len(g)),
                "win_rate": float(g["winner"].mean() * 100),
                "pnl_medio": float(g["pnl_eur"].mean()),
                "pnl_totale": float(g["pnl_eur"].sum()),
            })

    return pd.DataFrame(rows)


def candidate_hypotheses(train_enriched, min_group=6):
    if train_enriched is None or train_enriched.empty:
        return pd.DataFrame()

    ideas = []

    def add_rule(name, mask, feature, direction, threshold):
        g = train_enriched.loc[mask].copy()
        if len(g) < min_group:
            return

        ideas.append({
            "ipotesi": name,
            "feature": feature,
            "direzione": direction,
            "soglia": float(threshold),
            "n_sviluppo": int(len(g)),
            "win_rate_sviluppo": float(g["winner"].mean() * 100),
            "pnl_medio_sviluppo": float(g["pnl_eur"].mean()),
        })

    for feat in FEATURES:
        if feat not in train_enriched.columns:
            continue

        s = pd.to_numeric(train_enriched[feat], errors="coerce")

        if s.notna().sum() < 15:
            continue

        q33 = float(s.quantile(.33))
        q67 = float(s.quantile(.67))

        add_rule(f"{feat} <= Q33", s <= q33, feat, "<=", q33)
        add_rule(f"{feat} >= Q67", s >= q67, feat, ">=", q67)

    if not ideas:
        return pd.DataFrame()

    return pd.DataFrame(ideas).sort_values(
        ["pnl_medio_sviluppo", "n_sviluppo"],
        ascending=[False, False]
    )


def apply_hypothesis(enriched, row):
    if enriched is None or enriched.empty:
        return pd.DataFrame()

    feat = row["feature"]

    if feat not in enriched.columns:
        return pd.DataFrame()

    s = pd.to_numeric(enriched[feat], errors="coerce")
    thr = float(row["soglia"])

    if row["direzione"] == "<=":
        return enriched.loc[s <= thr].copy()

    return enriched.loc[s >= thr].copy()


def evaluate_subset(subset):
    if subset is None or subset.empty:
        return {
            "n": 0,
            "win_rate": 0.0,
            "pnl_medio": 0.0,
            "pnl_totale": 0.0,
        }

    return {
        "n": int(len(subset)),
        "win_rate": float(subset["winner"].mean() * 100),
        "pnl_medio": float(subset["pnl_eur"].mean()),
        "pnl_totale": float(subset["pnl_eur"].sum()),
    }


def validation_screen(train_candidates, validation_enriched, top_n=8):
    if train_candidates is None or train_candidates.empty:
        return pd.DataFrame()

    rows = []

    for _, r in train_candidates.head(top_n).iterrows():
        subset = apply_hypothesis(validation_enriched, r)
        ev = evaluate_subset(subset)

        rows.append({
            **r.to_dict(),
            "n_validazione": ev["n"],
            "win_rate_validazione": ev["win_rate"],
            "pnl_medio_validazione": ev["pnl_medio"],
            "pnl_totale_validazione": ev["pnl_totale"],
            "coerente": bool(
                r["pnl_medio_sviluppo"] > 0 and
                ev["n"] >= 3 and
                ev["pnl_medio"] > 0
            )
        })

    return pd.DataFrame(rows)


def discovery_verdict(screen):
    if screen is None or screen.empty:
        return "NESSUNA IPOTESI VALUTABILE"

    coherent = int(screen["coerente"].sum()) if "coerente" in screen.columns else 0

    if coherent == 0:
        return "NESSUNA IPOTESI CONFERMATA"

    return f"{coherent} IPOTESI DA STUDIARE"
