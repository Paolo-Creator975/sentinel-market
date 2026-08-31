import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from sentinel.config import load_config
from sentinel.data import build_exchange,fetch_history
from sentinel.features import add_features
from sentinel.backtest import simulate,metrics,probability_by_score
from sentinel.advisor import investment_range,recommendation

st.set_page_config(page_title='Sentinel Market',layout='wide')
cfg=load_config(); st.title('Sentinel Market — Historical Replay'); st.caption('Demo storica: nessun denaro reale, nessun account, nessuna API key.')
with st.sidebar:
    symbol=st.selectbox('Mercato',cfg['symbols']); days=st.slider('Storico (giorni)',30,365,int(cfg['history_days_default']),step=30); capital=st.number_input('Capitale simulato (€)',min_value=100.0,value=float(cfg['starting_capital']),step=100.0); replay=st.slider('Punto del replay',20,100,100)
@st.cache_data(ttl=3600,show_spinner=False)
def load_market(exchange_name,symbol,days):
    return add_features(fetch_history(build_exchange(exchange_name),symbol,'15m',days))
try:
    with st.spinner('Carico dati storici pubblici...'): df=load_market(cfg['exchange'],symbol,days)
except Exception as e:
    st.error(f'Impossibile caricare i dati: {e}'); st.stop()
cut=max(80,int(len(df)*replay/100)); view=df.iloc[:cut].copy(); cur=view.iloc[-1]; run=dict(cfg); run['starting_capital']=capital; trades=simulate(view,run); m=metrics(trades,capital); prob,n=probability_by_score(trades,float(cur.sentinel_score))
entry=float(cur.close); atr=float(cur.atr14) if not pd.isna(cur.atr14) else entry*.01; stop=entry-1.2*atr; rr=float(cfg['min_rr']); target=entry+rr*(entry-stop); lo,hi=investment_range(capital,float(cfg['risk_per_trade_pct']),entry,stop,float(cfg['max_position_pct'])); net=((target-entry)/entry*100)-(float(cfg['fee_pct_roundtrip'])+float(cfg['slippage_pct_roundtrip'])); rec,why=recommendation(float(cur.sentinel_score),float(cur.extreme_risk),prob)
if rec=='OPPORTUNITÀ': st.success('🟢 SENTINEL: OPPORTUNITÀ')
elif rec=='ATTENDI': st.warning('🟡 SENTINEL: ATTENDI')
else: st.error('🔴 SENTINEL: NON ENTRARE')
st.write(why)
c1,c2,c3,c4=st.columns(4); c1.metric('Sentinel Score',f'{cur.sentinel_score:.0f}/100'); c2.metric('Successo storico comparabile','N/D' if prob is None else f'{prob:.1f}%',None if prob is None else f'campione {n}'); c3.metric('Rischio estremo',f'{cur.extreme_risk:.0f}/100'); c4.metric('Guadagno netto target',f'{net:.2f}%')
st.subheader('Indicazione semplice'); a1,a2,a3=st.columns(3); a1.metric('Range indicativo da esporre',f'€ {lo:,.0f} – {hi:,.0f}'); a2.metric('Perdita pianificata sul capitale',f"{float(cfg['risk_per_trade_pct']):.2f}%"); a3.metric('Rapporto rischio/rendimento',f'1 : {rr:.1f}')
st.caption('Il range € deriva dal Risk Manager sul capitale simulato e sullo stop; non è una raccomandazione finanziaria personalizzata.')
st.subheader('Analisi statistica numerica'); b1,b2,b3,b4,b5=st.columns(5); b1.metric('Trade simulati',m['trades']); b2.metric('Win rate',f"{m['win_rate']:.1f}%"); b3.metric('Profit factor','∞' if np.isinf(m['profit_factor']) else f"{m['profit_factor']:.2f}"); b4.metric('Rendimento netto',f"{m['net_return_pct']:.2f}%"); b5.metric('Max drawdown',f"{m['max_drawdown_pct']:.2f}%")
risk=float(cur.extreme_risk); label='BASSO' if risk<30 else 'MODERATO' if risk<55 else 'ALTO' if risk<70 else 'ESTREMO'; st.subheader('Eventi estremi / Black Swan Risk'); st.write(f'**Indice attuale: {risk:.0f}/100 — {label}.** È un indicatore di anomalie statistiche, non una probabilità matematica di un vero cigno nero.')
st.subheader('Replay del mercato'); recent=view.tail(250); fig=go.Figure(); fig.add_trace(go.Candlestick(x=recent.datetime,open=recent.open,high=recent.high,low=recent.low,close=recent.close,name=symbol)); fig.add_trace(go.Scatter(x=recent.datetime,y=recent.ema20,name='EMA20')); fig.add_trace(go.Scatter(x=recent.datetime,y=recent.ema50,name='EMA50')); fig.update_layout(height=470,xaxis_rangeslider_visible=False); st.plotly_chart(fig,use_container_width=True)
if not trades.empty:
    st.subheader('Equity simulata'); eq=pd.concat([pd.DataFrame({'exit_time':[view.iloc[0].datetime],'capital_after':[capital]}),trades[['exit_time','capital_after']]],ignore_index=True); fig2=go.Figure(go.Scatter(x=eq.exit_time,y=eq.capital_after,mode='lines')); fig2.update_layout(height=300); st.plotly_chart(fig2,use_container_width=True);
    with st.expander('Ultime operazioni simulate'): st.dataframe(trades.tail(20),use_container_width=True)
st.divider(); st.caption('Historical Replay V1: modello iniziale. Prima di qualunque uso reale servono test fuori campione e paper trading live.')
