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
from sentinel.validation import chronological_split
from sentinel.research import enrich_trades
from sentinel.discovery import (
    feature_separation, quantile_discovery, candidate_hypotheses,
    validation_screen, discovery_verdict
)

st.set_page_config(page_title="Sentinel Discovery Engine V1.5", layout="wide")
cfg = load_config()

st.title("Sentinel Market — Discovery Engine V1.5")
st.caption("Scoperta controllata di ipotesi per Strategy 2. Il TEST FINALE resta fuori dalla fase di scoperta.")

with st.sidebar:
    symbol = st.selectbox("Mercato", cfg["symbols"])
    days = st.slider("Storico richiesto (giorni)", 90, 365, 365, step=30)
    capital = st.number_input("Capitale simulato (€)", min_value=100.0,
                              value=float(cfg["starting_capital"]), step=100.0)
    threshold = st.slider("Strategy 1 Score minimo", 60, 90, 70, 5)
    rr = st.select_slider("Risk / Reward", options=[1.5, 2.0, 2.5], value=2.0)
    st.info(
        "60% SVILUPPO = scoperta\n"
        "20% VALIDAZIONE = conferma preliminare\n"
        "20% TEST FINALE = BLOCCATO durante la scoperta"
    )

@st.cache_data(ttl=3600, show_spinner=False)
def load_market(candidates, symbol, days):
    source, raw = fetch_history_with_fallback(candidates, symbol, "15m", days)
    x = add_features(raw)
    x = add_regime_features(x)
    x = add_strategy1_signals(x)
    return source, x

try:
    with st.spinner("Carico dati e avvio la scoperta controllata..."):
        source, df = load_market(tuple(cfg["exchange_candidates"]), symbol, days)
except Exception as e:
    st.error(f"Errore dati: {e}")
    st.stop()

cfg_run = dict(cfg)
cfg_run["starting_capital"] = capital

train, val, test = chronological_split(df)

def make_enriched(part, label):
    t = simulate_strategy1(part, cfg_run, threshold=threshold, rr=rr)
    if not t.empty:
        t = t.assign(periodo=label)
    return enrich_trades(t, df)

train_e = make_enriched(train, "Sviluppo")
val_e = make_enriched(val, "Validazione")

# IMPORTANT: Test is not analyzed in discovery.
sep = feature_separation(train_e)
qscan = quantile_discovery(train_e)
cands = candidate_hypotheses(train_e)
screen = validation_screen(cands, val_e, top_n=8)

st.caption(f"Fonte pubblica: {source.upper()} · Candele: {len(df):,}")

st.subheader("1 · Firewall anti-overfitting")
a,b,c = st.columns(3)
a.metric("Sviluppo", f"{len(train):,} candele")
b.metric("Validazione", f"{len(val):,} candele")
c.metric("Test finale", "BLOCCATO")
st.warning(
    "Il 20% finale non viene usato qui né per scoprire soglie né per selezionare ipotesi. "
    "Lo apriremo soltanto dopo aver congelato una Strategy 2."
)

st.subheader("2 · Quali caratteristiche separano vincitori e perdenti?")
if sep.empty:
    st.info("Campione di sviluppo insufficiente.")
else:
    st.dataframe(sep, use_container_width=True, hide_index=True)
    st.caption(
        "Effect size vicino a 0 = poca separazione. Valori più lontani da 0 indicano una differenza "
        "descrittiva tra vincenti e perdenti, non una causalità."
    )

st.subheader("3 · Scansione per fasce — SOLO sviluppo")
if qscan.empty:
    st.info("Campione insufficiente per creare fasce robuste.")
else:
    st.dataframe(qscan, use_container_width=True, hide_index=True)
    st.caption(
        "Ogni variabile viene divisa in fasce. Serve a formulare ipotesi semplici e leggibili, "
        "non a scegliere automaticamente la combinazione più redditizia."
    )

st.subheader("4 · Ipotesi candidate generate sullo sviluppo")
if cands.empty:
    st.info("Nessuna ipotesi con campione sufficiente.")
else:
    st.dataframe(cands.head(12), use_container_width=True, hide_index=True)

st.subheader("5 · Screening sulla VALIDAZIONE")
st.metric("Verdetto Discovery", discovery_verdict(screen))
if screen.empty:
    st.info("Nessuna ipotesi da sottoporre a validazione.")
else:
    st.dataframe(screen, use_container_width=True, hide_index=True)
    st.caption(
        "Una riga 'coerente = True' NON è ancora Strategy 2. Significa soltanto che una semplice "
        "ipotesi nata sullo sviluppo mantiene segno positivo anche nella validazione."
    )

st.subheader("6 · Regola per costruire Strategy 2")
st.write(
    "Strategy 2 verrà definita soltanto usando ipotesi semplici, interpretabili e coerenti tra "
    "SVILUPPO e VALIDAZIONE. Dopo aver congelato le sue regole, il TEST FINALE verrà aperto una sola volta. "
    "Se fallisce, la strategia viene respinta."
)

st.divider()
st.caption(
    "Sentinel Discovery Engine V1.5 — ricerca quantitativa. "
    "Nessun denaro reale. I risultati storici non garantiscono risultati futuri."
)
