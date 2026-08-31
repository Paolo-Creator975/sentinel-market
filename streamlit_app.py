import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

from sentinel.config import load_config
from sentinel.data import fetch_history_with_fallback
from sentinel.features import add_features
from sentinel.validation import chronological_split, evaluate_period, verdict, score_calibration, parameter_sweep

st.set_page_config(page_title="Sentinel Calibration Lab", layout="wide")
cfg = load_config()

st.title("Sentinel Market — Calibration Lab V1.2")
st.caption("Ricerca storica rigorosa: sviluppo, validazione e test finale separati nel tempo. Nessun denaro reale.")

with st.sidebar:
    symbol = st.selectbox("Mercato", cfg["symbols"])
    days = st.slider("Storico richiesto (giorni)", 90, 365, 365, step=30)
    capital = st.number_input("Capitale simulato (€)", min_value=100.0, value=float(cfg["starting_capital"]), step=100.0)
    st.info("Split temporale: 60% sviluppo · 20% validazione · 20% test finale")

@st.cache_data(ttl=3600, show_spinner=False)
def load_market(candidates, symbol, days):
    source, raw = fetch_history_with_fallback(candidates, symbol, "15m", days)
    return source, add_features(raw)

try:
    with st.spinner("Carico e preparo lo storico..."):
        source, df = load_market(tuple(cfg["exchange_candidates"]), symbol, days)
except Exception as e:
    st.error(f"Errore dati: {e}")
    st.stop()

cfg_run = dict(cfg)
cfg_run["starting_capital"] = capital

train, val, test = chronological_split(df)
train_trades, train_m = evaluate_period(train, cfg_run)
val_trades, val_m = evaluate_period(val, cfg_run)
test_trades, test_m = evaluate_period(test, cfg_run)

st.caption(f"Fonte pubblica: {source.upper()} · Candele chiuse: {len(df):,}")

st.subheader("1 · Esame della Strategia Zero")
cols = st.columns(3)
periods = [
    ("SVILUPPO 60%", train_m),
    ("VALIDAZIONE 20%", val_m),
    ("TEST FINALE 20%", test_m),
]
for c, (name, m) in zip(cols, periods):
    with c:
        st.markdown(f"### {name}")
        st.metric("Verdetto", verdict(m))
        st.metric("Trade", m["trades"])
        st.metric("Win rate", f'{m["win_rate"]:.1f}%')
        pf = m["profit_factor"]
        st.metric("Profit factor", "∞" if np.isinf(pf) else f"{pf:.2f}")
        st.metric("Rendimento netto", f'{m["net_return_pct"]:.2f}%')
        st.metric("Max drawdown", f'{m["max_drawdown_pct"]:.2f}%')
        st.metric("Expectancy / trade", f'€ {m["expectancy_eur"]:.2f}')

st.warning(
    "Il TEST FINALE non deve essere usato per scegliere i parametri. "
    "Serve soltanto come esame indipendente dopo le decisioni prese su sviluppo/validazione."
)

st.subheader("2 · Il Sentinel Score predice davvero qualcosa?")
all_trades = pd.concat([train_trades, val_trades, test_trades], ignore_index=True)
cal = score_calibration(all_trades)
st.dataframe(cal, use_container_width=True, hide_index=True)
st.caption(
    "Se lo Score è utile, le fasce più alte dovrebbero mostrare risultati migliori in modo abbastanza regolare. "
    "Se non accade, i pesi dello Score vanno riprogettati."
)

st.subheader("3 · Laboratorio parametri — SOLO periodo di sviluppo")
sweep = parameter_sweep(train, cfg_run)
display = sweep.sort_values(["profit_factor","net_return_pct"], ascending=False).copy()
st.dataframe(display, use_container_width=True, hide_index=True)
st.caption(
    "Questa tabella non autorizza a scegliere semplicemente la riga con il rendimento maggiore. "
    "Le varianti promettenti devono essere confermate sulla validazione e poi sul test finale."
)

st.subheader("4 · Regime di mercato e andamento")
recent = df.tail(300)
fig = go.Figure()
fig.add_trace(go.Candlestick(
    x=recent["datetime"], open=recent["open"], high=recent["high"],
    low=recent["low"], close=recent["close"], name=symbol
))
fig.add_trace(go.Scatter(x=recent["datetime"], y=recent["ema20"], name="EMA20"))
fig.add_trace(go.Scatter(x=recent["datetime"], y=recent["ema50"], name="EMA50"))
fig.update_layout(height=460, xaxis_rangeslider_visible=False)
st.plotly_chart(fig, use_container_width=True)

st.subheader("5 · Regola di promozione")
st.write(
    "Una strategia non passa al paper trading perché funziona sul periodo di sviluppo. "
    "Deve mantenere expectancy positiva dopo costi, profit factor > 1, drawdown controllato, "
    "campione sufficiente e comportamento coerente su validazione e test finale."
)

st.divider()
st.caption(
    "V1.2 Calibration Lab — strumento di ricerca. I risultati storici non garantiscono risultati futuri "
    "e non costituiscono una raccomandazione di investimento."
)
