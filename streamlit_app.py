import streamlit as st
import pandas as pd
import numpy as np

from sentinel.config import load_config
from sentinel.data import fetch_history_with_fallback
from sentinel.features import add_features
from sentinel.regime import add_regime_features
from sentinel.strategy1 import add_strategy1_signals
from sentinel.backtest import metrics
from sentinel.backtest_strategy1 import simulate_strategy1
from sentinel.validation import chronological_split, verdict
from sentinel.research import (
    enrich_trades, winner_loser_profile, regime_performance,
    exit_performance, score_bands, research_summary
)

st.set_page_config(page_title="Sentinel Research Engine V1.4", layout="wide")
cfg = load_config()

st.title("Sentinel Market — Research Engine V1.4")
st.caption("Diagnostica quantitativa di Strategy 1. Ricerca storica, nessun denaro reale.")

with st.sidebar:
    symbol = st.selectbox("Mercato", cfg["symbols"])
    days = st.slider("Storico richiesto (giorni)", 90, 365, 365, step=30)
    capital = st.number_input("Capitale simulato (€)", min_value=100.0,
                              value=float(cfg["starting_capital"]), step=100.0)
    threshold = st.slider("Strategy 1 Score minimo", 60, 90, 70, 5)
    rr = st.select_slider("Risk / Reward", options=[1.5, 2.0, 2.5], value=2.0)
    st.info("Il Research Engine cerca differenze tra trade vincenti e perdenti. Non ottimizza sul test finale.")

@st.cache_data(ttl=3600, show_spinner=False)
def load_market(candidates, symbol, days):
    source, raw = fetch_history_with_fallback(candidates, symbol, "15m", days)
    x = add_features(raw)
    x = add_regime_features(x)
    x = add_strategy1_signals(x)
    return source, x

try:
    with st.spinner("Carico storico e preparo la diagnostica..."):
        source, df = load_market(tuple(cfg["exchange_candidates"]), symbol, days)
except Exception as e:
    st.error(f"Errore dati: {e}")
    st.stop()

cfg_run = dict(cfg)
cfg_run["starting_capital"] = capital
train, val, test = chronological_split(df)

def run(part, label):
    t = simulate_strategy1(part, cfg_run, threshold=threshold, rr=rr)
    if not t.empty:
        t = t.assign(periodo=label)
    return t, metrics(t, capital)

train_t, train_m = run(train, "Sviluppo")
val_t, val_m = run(val, "Validazione")
test_t, test_m = run(test, "Test finale")

all_t = pd.concat([train_t, val_t, test_t], ignore_index=True)
enriched = enrich_trades(all_t, df)
summary = research_summary(enriched)

st.caption(f"Fonte pubblica: {source.upper()} · Candele: {len(df):,}")

st.subheader("1 · Stato della Strategy 1")
c1,c2,c3,c4,c5 = st.columns(5)
c1.metric("Trade totali", summary["trades"])
c2.metric("Win rate", f'{summary["win_rate"]:.1f}%')
c3.metric("Vincite", summary["wins"])
c4.metric("Perdite", summary["losses"])
c5.metric("Payoff medio", "∞" if np.isinf(summary["payoff"]) else f'{summary["payoff"]:.2f}')

cols = st.columns(3)
for c, (name, m) in zip(cols, [
    ("SVILUPPO 60%", train_m), ("VALIDAZIONE 20%", val_m), ("TEST FINALE 20%", test_m)
]):
    with c:
        st.markdown(f"### {name}")
        st.metric("Verdetto", verdict(m))
        st.metric("Trade", m["trades"])
        st.metric("Profit factor", "∞" if np.isinf(m["profit_factor"]) else f'{m["profit_factor"]:.2f}')
        st.metric("Rendimento netto", f'{m["net_return_pct"]:.2f}%')
        st.metric("Expectancy / trade", f'€ {m["expectancy_eur"]:.2f}')

st.subheader("2 · Dove finiscono le operazioni?")
ep = exit_performance(enriched)
if ep.empty:
    st.info("Nessun trade da analizzare.")
else:
    st.dataframe(ep, use_container_width=True, hide_index=True)
    st.caption("Serve per capire quanto pesano STOP, TARGET e TIME sul risultato complessivo.")

st.subheader("3 · Vincitori contro perdenti")
profile = winner_loser_profile(enriched)
if profile.empty:
    st.info("Campione insufficiente per confrontare le caratteristiche.")
else:
    st.dataframe(profile, use_container_width=True, hide_index=True)
    st.caption(
        "Qui confrontiamo RSI, volatilità, forza del trend, volume, distanza da EMA20 e Score "
        "al momento dell'ingresso. Differenze persistenti possono suggerire filtri per Strategy 2."
    )

st.subheader("4 · Performance per regime")
rp = regime_performance(enriched)
if rp.empty:
    st.info("Nessun regime analizzabile.")
else:
    st.dataframe(rp, use_container_width=True, hide_index=True)

st.subheader("5 · Lo Score distingue davvero la qualità?")
sb = score_bands(enriched)
if sb.empty:
    st.info("Nessun dato sufficiente.")
else:
    st.dataframe(sb, use_container_width=True, hide_index=True)
    st.caption(
        "Se le fasce più alte non migliorano con regolarità win rate e PNL medio, "
        "lo Strategy 1 Score non va trattato come misura affidabile di qualità."
    )

st.subheader("6 · Campioni grezzi per audit")
if enriched.empty:
    st.info("Nessuna operazione.")
else:
    show_cols = [c for c in [
        "periodo","entry_time","exit_time","reason","pnl_eur","score",
        "market_regime","rsi14","vol_ratio","ema_gap_atr",
        "volume_ratio","dist_ema20_atr"
    ] if c in enriched.columns]
    st.dataframe(enriched[show_cols].sort_values("entry_time", ascending=False),
                 use_container_width=True, hide_index=True)

st.warning(
    "V1.4 è un laboratorio diagnostico. Non scegliamo un filtro perché migliora casualmente questi dati. "
    "Qualunque ipotesi per Strategy 2 dovrà essere definita prima e poi verificata su dati separati."
)

st.divider()
st.caption("Sentinel Research Engine V1.4 — ricerca quantitativa. I risultati storici non garantiscono risultati futuri.")
