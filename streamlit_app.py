import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

from sentinel.config import load_config
from sentinel.data import fetch_history_with_fallback
from sentinel.features import add_features
from sentinel.regime import add_regime_features
from sentinel.strategy1 import add_strategy1_signals
from sentinel.backtest import metrics
from sentinel.backtest_strategy1 import simulate_strategy1
from sentinel.validation import chronological_split, verdict

st.set_page_config(page_title="Sentinel Strategy Lab V1.3", layout="wide")
cfg = load_config()

st.title("Sentinel Market — Strategy Lab V1.3")
st.caption("Strategy 1 + Market Regime Engine. Ricerca storica, nessun denaro reale.")

with st.sidebar:
    symbol = st.selectbox("Mercato", cfg["symbols"])
    days = st.slider("Storico richiesto (giorni)", 90, 365, 365, step=30)
    capital = st.number_input("Capitale simulato (€)", min_value=100.0,
                              value=float(cfg["starting_capital"]), step=100.0)
    threshold = st.slider("Strategy 1 Score minimo", 60, 90, 70, 5)
    rr = st.select_slider("Risk / Reward", options=[1.5, 2.0, 2.5], value=2.0)
    st.info("Split cronologico: 60% sviluppo · 20% validazione · 20% test finale")

@st.cache_data(ttl=3600, show_spinner=False)
def load_market(candidates, symbol, days):
    source, raw = fetch_history_with_fallback(candidates, symbol, "15m", days)
    x = add_features(raw)
    x = add_regime_features(x)
    x = add_strategy1_signals(x)
    return source, x

try:
    with st.spinner("Carico lo storico e classifico i regimi..."):
        source, df = load_market(tuple(cfg["exchange_candidates"]), symbol, days)
except Exception as e:
    st.error(f"Errore dati: {e}")
    st.stop()

cfg_run = dict(cfg)
cfg_run["starting_capital"] = capital
train, val, test = chronological_split(df)

def run(part):
    t = simulate_strategy1(part, cfg_run, threshold=threshold, rr=rr)
    return t, metrics(t, capital)

train_t, train_m = run(train)
val_t, val_m = run(val)
test_t, test_m = run(test)

st.caption(f"Fonte pubblica: {source.upper()} · Candele: {len(df):,}")

st.subheader("1 · Market Regime Engine")
counts = df["market_regime"].value_counts()
c1,c2,c3,c4 = st.columns(4)
for c, name, label in [
    (c1,"TREND_UP","Trend rialzista"),
    (c2,"TREND_DOWN","Trend ribassista"),
    (c3,"SIDEWAYS","Laterale"),
    (c4,"HIGH_VOL","Alta volatilità")
]:
    c.metric(label, f"{counts.get(name,0)/len(df)*100:.1f}%")

st.caption("Strategy 1 opera soltanto nel regime TREND_UP; negli altri regimi resta ferma.")

st.subheader("2 · Esame indipendente di Strategy 1")
cols = st.columns(3)
for c, (name, m) in zip(cols, [
    ("SVILUPPO 60%", train_m), ("VALIDAZIONE 20%", val_m), ("TEST FINALE 20%", test_m)
]):
    with c:
        st.markdown(f"### {name}")
        st.metric("Verdetto", verdict(m))
        st.metric("Trade", m["trades"])
        st.metric("Win rate", f'{m["win_rate"]:.1f}%')
        st.metric("Profit factor", "∞" if np.isinf(m["profit_factor"]) else f'{m["profit_factor"]:.2f}')
        st.metric("Rendimento netto", f'{m["net_return_pct"]:.2f}%')
        st.metric("Max drawdown", f'{m["max_drawdown_pct"]:.2f}%')
        st.metric("Expectancy / trade", f'€ {m["expectancy_eur"]:.2f}')

st.warning("Non ottimizziamo sul TEST FINALE. Se Strategy 1 fallisce fuori campione, viene bocciata.")

st.subheader("3 · Diagnostica delle operazioni")
all_t = pd.concat([train_t.assign(periodo="Sviluppo"),
                   val_t.assign(periodo="Validazione"),
                   test_t.assign(periodo="Test finale")], ignore_index=True)
if all_t.empty:
    st.info("Nessuna operazione con i filtri correnti. Anche questo è un risultato utile.")
else:
    diag = all_t.groupby(["periodo","reason"]).agg(
        trade=("pnl_eur","size"),
        pnl_medio=("pnl_eur","mean")
    ).reset_index()
    st.dataframe(diag, use_container_width=True, hide_index=True)

st.subheader("4 · Mercato e regime recente")
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

current = df.iloc[-1]
regime_it = {
    "TREND_UP":"TREND RIALZISTA",
    "TREND_DOWN":"TREND RIBASSISTA",
    "SIDEWAYS":"MERCATO LATERALE",
    "HIGH_VOL":"VOLATILITÀ ELEVATA"
}.get(current["market_regime"], current["market_regime"])
st.info(f"Regime più recente classificato da Sentinel: **{regime_it}**")

st.subheader("5 · Criterio di promozione")
st.write(
    "Strategy 1 sarà considerata soltanto se mostra un campione sufficiente, expectancy positiva "
    "dopo costi, Profit Factor > 1 e drawdown controllato, soprattutto su validazione e test finale. "
    "Un risultato positivo sul solo sviluppo non basta."
)

st.divider()
st.caption("V1.3 Strategy Lab — ricerca quantitativa. I risultati storici non garantiscono risultati futuri.")
