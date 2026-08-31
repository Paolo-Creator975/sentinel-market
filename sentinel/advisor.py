def investment_range(capital,risk_pct,entry,stop,max_pos_pct=5.0):
    risk_eur=capital*risk_pct/100; price_risk=max((entry-stop)/entry,0.001); suggested=min(risk_eur/price_risk,capital*max_pos_pct/100); return max(0,suggested*.8),max(0,suggested)

def recommendation(score,extreme_risk,prob):
    if extreme_risk>=70:return 'NON ENTRARE','Rischio estremo/anomalia troppo elevato.'
    if score<75:return 'ATTENDI','Il vantaggio statistico non supera la soglia minima.'
    if prob is not None and prob<52:return 'ATTENDI','Lo storico comparabile non mostra sufficiente vantaggio.'
    return 'OPPORTUNITÀ','Il setup supera i filtri iniziali di Sentinel.'
