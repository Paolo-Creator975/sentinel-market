import pandas as pd
import numpy as np


def _safe_numeric(series):
    return pd.to_numeric(series, errors="coerce")


def compare_winners_losers(trades):
    """
    Confronta le caratteristiche presenti all'ingresso
    delle operazioni vincenti e perdenti.
    Uso diagnostico: non modifica la strategia.
    """
    if trades is None or len(trades) == 0:
        return pd.DataFrame()

    df = trades.copy()

    if "pnl_eur" not in df.columns:
        return pd.DataFrame()

    df["group"] = np.where(
        _safe_numeric(df["pnl_eur"]) > 0,
        "WIN",
        "LOSS"
    )

    features = [
        "strategy1_score",
        "rsi14",
        "vol_ratio",
        "volume_ratio",
        "ema_gap_atr",
        "dist_ema20_atr",
    ]

    rows = []

    for feature in features:
        if feature not in df.columns:
            continue

        values = _safe_numeric(df[feature])

        for group in ["WIN", "LOSS"]:
            mask = df["group"] == group
            sample = values[mask].dropna()

            if len(sample) == 0:
                continue

            rows.append({
                "feature": feature,
                "gruppo": group,
                "n": int(len(sample)),
                "media": round(float(sample.mean()), 4),
                "mediana": round(float(sample.median()), 4),
                "q25": round(float(sample.quantile(0.25)), 4),
                "q75": round(float(sample.quantile(0.75)), 4),
            })

    return pd.DataFrame(rows)


def discover_candidate_rules(trades, min_samples=5):
    """
    Cerca differenze descrittive tra trade vincenti e perdenti.

    IMPORTANTE:
    le regole restituite sono IPOTESI DI RICERCA,
    non segnali approvati per il trading.
    """

    comparison = compare_winners_losers(trades)

    if comparison.empty:
        return pd.DataFrame()

    candidates = []

    for feature in comparison["feature"].unique():

        part = comparison[comparison["feature"] == feature]

        win = part[part["gruppo"] == "WIN"]
        loss = part[part["gruppo"] == "LOSS"]

        if win.empty or loss.empty:
            continue

        w = win.iloc[0]
        l = loss.iloc[0]

        if w["n"] < min_samples or l["n"] < min_samples:
            continue

        difference = float(w["mediana"] - l["mediana"])

        pooled_scale = max(
            abs(float(w["q75"] - w["q25"])),
            abs(float(l["q75"] - l["q25"])),
            1e-9
        )

        separation = abs(difference) / pooled_scale

        if difference > 0:
            direction = "VALORI PIÙ ALTI associati ai WIN"
        elif difference < 0:
            direction = "VALORI PIÙ BASSI associati ai WIN"
        else:
            direction = "NESSUNA DIFFERENZA"

        candidates.append({
            "feature": feature,
            "n_win": int(w["n"]),
            "n_loss": int(l["n"]),
            "mediana_win": round(float(w["mediana"]), 4),
            "mediana_loss": round(float(l["mediana"]), 4),
            "differenza": round(difference, 4),
            "separation_index": round(float(separation), 3),
            "ipotesi": direction,
        })

    if not candidates:
        return pd.DataFrame()

    result = pd.DataFrame(candidates)

    return result.sort_values(
        "separation_index",
        ascending=False
    ).reset_index(drop=True)


def score_quality_by_band(trades):
    """
    Controlla se score più elevati corrispondono realmente
    a risultati migliori.
    """

    if trades is None or len(trades) == 0:
        return pd.DataFrame()

    df = trades.copy()

    required = {"strategy1_score", "pnl_eur"}

    if not required.issubset(df.columns):
        return pd.DataFrame()

    df["strategy1_score"] = _safe_numeric(df["strategy1_score"])
    df["pnl_eur"] = _safe_numeric(df["pnl_eur"])

    bins = [-np.inf, 70, 75, 80, 85, 90, np.inf]
    labels = [
        "<70",
        "70-74",
        "75-79",
        "80-84",
        "85-89",
        "90-100",
    ]

    df["score_band"] = pd.cut(
        df["strategy1_score"],
        bins=bins,
        labels=labels,
        right=False
    )

    rows = []

    for band in labels:

        sample = df[df["score_band"] == band].dropna(
            subset=["pnl_eur"]
        )

        n = len(sample)

        if n == 0:
            rows.append({
                "score_band": band,
                "trade": 0,
                "win_rate": np.nan,
                "pnl_medio": np.nan,
                "pnl_totale": np.nan,
            })
            continue

        rows.append({
            "score_band": band,
            "trade": int(n),
            "win_rate": round(
                float((sample["pnl_eur"] > 0).mean() * 100), 2
            ),
            "pnl_medio": round(
                float(sample["pnl_eur"].mean()), 4
            ),
            "pnl_totale": round(
                float(sample["pnl_eur"].sum()), 4
            ),
        })

    return pd.DataFrame(rows)
