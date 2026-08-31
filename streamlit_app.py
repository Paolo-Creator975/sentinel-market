import json
import hashlib
import streamlit as st
import pandas as pd
import numpy as np

from sentinel.config import load_config
from sentinel.data import fetch_history_with_fallback
from sentinel.features import add_features
from sentinel.regime import add_regime_features
from sentinel.strategy2 import add_strategy2_signals
from sentinel.backtest_strategy2 import simulate_strategy2
from sentinel.backtest import metrics
from sentinel.validation import chronological_split

st.set_page_config(page_title="Sentinel Strategy 2 Builder V1.6", layout="wide")
cfg = load_config()

st.title("Sentinel Market — Strategy 2 Builder V1.6")
st.caption("Specifica congelata · sviluppo + validazione · TEST FINALE ancora sigillato")

with st.sidebar:
    symbol = st.selectbox("Mercato", cfg["symbols"])
    days = st.slider("Storico richiesto (giorni)", 90, 365, 365, step=30)
    capital = st.number_input(
        "Capitale simulato (€)", min_value=100.0,
        value=float(cfg["starting_capital"]), step=100.0
    )
    st.info(
        "Strategy 2 non viene ottimizzata con slider.\n\n"
        "60% SVILUPPO\n20% VALIDAZIONE\n20% TEST FINALE SIGILLATO"
    )

@st.cache_data(ttl=3600, show_spinner=False)
def load_market(candidates, symbol, days):
    source, raw = fetch_history_with_fallback(candidates, symbol, "15m", days)
    x = add_features(raw)
    x = add_regime_features(x)
    x = add_strategy2_signals(x)
    return source, x

try:
    with st.spinner("Carico dati e valuto la specifica congelata..."):
        source, df = load_market(tuple(cfg["exchange_candidates"]), symbol, days)
except Exception as e:
    st.error(f"Errore dati: {e}")
    st.stop()

cfg_run = dict(cfg)
cfg_run["starting_capital"] = capital

train, val, test = chronological_split(df)

# Firewall: the test dataframe is intentionally never passed to a simulator.
train_trades = simulate_strategy2(train, cfg_run)
val_trades = simulate_strategy2(val, cfg_run)

m_train = metrics(train_trades, capital)
m_val = metrics(val_trades, capital)

spec_json = json.dumps(STRATEGY2_PARAMS, sort_keys=True, separators=(",", ":"))
spec_hash = hashlib.sha256(spec_json.encode("utf-8")).hexdigest()

MIN_DEV_TRADES = 30
MIN_VAL_TRADES = 10

def finite_pf(v):
    return np.isfinite(v) and v > 1.0

sample_ok = (
    m_train["trades"] >= MIN_DEV_TRADES and
    m_val["trades"] >= MIN_VAL_TRADES
)
edge_ok = (
    m_train["expectancy_eur"] > 0 and
    m_val["expectancy_eur"] > 0 and
    finite_pf(m_train["profit_factor"]) and
    finite_pf(m_val["profit_factor"])
)
risk_ok = (
    m_train["max_drawdown_pct"] > -15 and
    m_val["max_drawdown_pct"] > -15
)

if not sample_ok:
    verdict = "CAMPIONE INSUFFICIENTE"
elif not edge_ok:
    verdict = "STRATEGY 2 NON CONFERMATA"
elif not risk_ok:
    verdict = "RISCHIO ECCESSIVO"
else:
    verdict = "CANDIDATA AL TEST FINALE"

st.caption(f"Fonte pubblica: {source.upper()} · {symbol} · Candele: {len(df):,}")

st.subheader("1 · Specifica Strategy 2 congelata")
c1, c2 = st.columns([2, 1])
with c1:
    st.code(
        "TREND: close > EMA20 > EMA50 + pendenza positiva\n"
        "INGRESSO: breakout del massimo delle 20 candele precedenti\n"
        "MOMENTUM: RSI 55–72\n"
        "PARTECIPAZIONE: volume 1.05–3.00× media 20\n"
        "VOLATILITÀ: vol_ratio 0.65–1.60\n"
        "RISCHIO ESTREMO: < 65/100\n"
        "STOP: 1.50 ATR · TARGET: 2.00R · TIME EXIT: 32 barre"
    )
with c2:
    st.metric("ID specifica", spec_hash[:12].upper())
    st.caption("SHA-256 della configurazione congelata. Se cambiano le regole, cambia l'ID.")

st.subheader("2 · Firewall anti-overfitting")
a, b, c = st.columns(3)
a.metric("Sviluppo", f"{len(train):,} candele")
b.metric("Validazione", f"{len(val):,} candele")
c.metric("Test finale", "SIGILLATO")
st.warning(
    "Il 20% finale NON viene simulato in V1.6. Prima devono essere soddisfatti "
    "i criteri dichiarati qui sotto. Nessun risultato del test finale viene usato "
    "per modificare Strategy 2."
)

def metric_row(title, m):
    st.markdown(f"#### {title}")
    cols = st.columns(6)
    cols[0].metric("Trade", m["trades"])
    cols[1].metric("Win rate", f'{m["win_rate"]:.1f}%')
    pf = m["profit_factor"]
    cols[2].metric("Profit factor", "∞" if np.isinf(pf) else f"{pf:.2f}")
    cols[3].metric("Rendimento netto", f'{m["net_return_pct"]:.2f}%')
    cols[4].metric("Max drawdown", f'{m["max_drawdown_pct"]:.2f}%')
    cols[5].metric("Expectancy", f'€ {m["expectancy_eur"]:.3f}')

st.subheader("3 · Esame indipendente")
metric_row("SVILUPPO — 60%", m_train)
metric_row("VALIDAZIONE — 20%", m_val)

st.subheader("4 · Gate predefiniti")
gates = pd.DataFrame([
    {
        "Gate": "Campione",
        "Regola": f"Sviluppo ≥ {MIN_DEV_TRADES} trade e Validazione ≥ {MIN_VAL_TRADES}",
        "Esito": "PASS" if sample_ok else "FAIL"
    },
    {
        "Gate": "Edge dopo costi",
        "Regola": "Expectancy > 0 e Profit Factor > 1 in entrambi",
        "Esito": "PASS" if edge_ok else "FAIL"
    },
    {
        "Gate": "Rischio",
        "Regola": "Max drawdown > -15% in entrambi",
        "Esito": "PASS" if risk_ok else "FAIL"
    },
])
st.dataframe(gates, use_container_width=True, hide_index=True)

st.metric("Verdetto V1.6", verdict)

if verdict == "CANDIDATA AL TEST FINALE":
    st.success(
        "Strategy 2 ha superato i gate preliminari. Il test finale resta comunque "
        "sigillato in questa versione: verrà aperto una sola volta nella fase successiva."
    )
else:
    st.info(
        "Il test finale resta chiuso. Un FAIL non è un errore del programma: "
        "significa che non abbiamo ancora evidenza sufficiente per promuovere la strategia."
    )

st.subheader("5 · Audit dei trade")
left, right = st.columns(2)
with left:
    st.markdown("**Sviluppo**")
    if train_trades.empty:
        st.write("Nessun trade.")
    else:
        st.dataframe(train_trades, use_container_width=True, hide_index=True)
with right:
    st.markdown("**Validazione**")
    if val_trades.empty:
        st.write("Nessun trade.")
    else:
        st.dataframe(val_trades, use_container_width=True, hide_index=True)

st.divider()
st.caption(
    "Sentinel Strategy 2 Builder V1.6 — ricerca quantitativa, nessun denaro reale. "
    "I risultati storici non garantiscono risultati futuri."
)
