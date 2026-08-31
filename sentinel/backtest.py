import pandas as pd

def simulate(df,cfg):
    x=df.reset_index(drop=True).copy(); capital=float(cfg['starting_capital']); risk_pct=float(cfg['risk_per_trade_pct'])/100; max_pos=float(cfg['max_position_pct'])/100; rr=float(cfg['min_rr']); costs=(float(cfg['fee_pct_roundtrip'])+float(cfg['slippage_pct_roundtrip']))/100; threshold=float(cfg['score_threshold']); trades=[]; inpos=False
    for i in range(60,len(x)-1):
        r=x.iloc[i]
        if not inpos:
            if pd.isna(r.sentinel_score) or pd.isna(r.atr14) or r.sentinel_score<threshold or r.extreme_risk>=70 or not (r.close>r.ema20>r.ema50): continue
            entry=float(r.close); stop=entry-1.2*float(r.atr14); risk_unit=max(entry-stop,entry*0.001); target=entry+rr*risk_unit; risk_eur=capital*risk_pct; size=min(risk_eur/risk_unit,(capital*max_pos)/entry)
            if size<=0: continue
            inpos=True; ei=i; escore=float(r.sentinel_score); erisk=float(r.extreme_risk); continue
        if i<=ei: continue
        r=x.iloc[i]; exitp=None; reason=None
        if r.low<=stop: exitp=stop; reason='STOP'
        elif r.high>=target: exitp=target; reason='TARGET'
        elif i-ei>=32: exitp=float(r.close); reason='TIME'
        if exitp is not None:
            gross=(exitp-entry)*size; pos=entry*size; pnl=gross-pos*costs; capital+=pnl
            trades.append({'entry_time':x.iloc[ei].datetime,'exit_time':r.datetime,'entry':entry,'exit':exitp,'stop':stop,'target':target,'position_eur':pos,'score':escore,'extreme_risk':erisk,'reason':reason,'pnl_eur':pnl,'capital_after':capital})
            inpos=False
    return pd.DataFrame(trades)

def metrics(t,start):
    if t.empty: return {'trades':0,'win_rate':0,'net_return_pct':0,'profit_factor':0,'max_drawdown_pct':0,'expectancy_eur':0}
    wins=t[t.pnl_eur>0].pnl_eur.sum(); losses=-t[t.pnl_eur<0].pnl_eur.sum(); pf=wins/losses if losses>0 else float('inf'); eq=pd.concat([pd.Series([start]),t.capital_after.reset_index(drop=True)],ignore_index=True); dd=(eq-eq.cummax())/eq.cummax()*100
    return {'trades':len(t),'win_rate':(t.pnl_eur>0).mean()*100,'net_return_pct':t.pnl_eur.sum()/start*100,'profit_factor':pf,'max_drawdown_pct':dd.min(),'expectancy_eur':t.pnl_eur.mean()}

def probability_by_score(t,score):
    if t.empty:return None,0
    lo=int(score//10)*10; b=t[(t.score>=lo)&(t.score<lo+10)]
    if len(b)<10:b=t[(t.score>=score-7.5)&(t.score<=score+7.5)]
    if b.empty:return None,0
    return float((b.pnl_eur>0).mean()*100),int(len(b))
