import numpy as np
import pandas as pd

def rsi(s,p=14):
    d=s.diff(); g=d.clip(lower=0).rolling(p).mean(); l=(-d.clip(upper=0)).rolling(p).mean(); rs=g/l.replace(0,np.nan); return 100-(100/(1+rs))

def add_features(df):
    x=df.copy(); x['ema20']=x['close'].ewm(span=20,adjust=False).mean(); x['ema50']=x['close'].ewm(span=50,adjust=False).mean(); x['rsi14']=rsi(x['close']); x['vol_ma20']=x['volume'].rolling(20).mean()
    tr=pd.concat([(x.high-x.low),(x.high-x.close.shift()).abs(),(x.low-x.close.shift()).abs()],axis=1).max(axis=1); x['atr14']=tr.rolling(14).mean(); x['ret1']=x.close.pct_change(); x['ret_std20']=x.ret1.rolling(20).std(); x['zret']=x.ret1/x.ret_std20.replace(0,np.nan)
    trend=np.where((x.close>x.ema20)&(x.ema20>x.ema50),80,np.where(x.close>x.ema20,60,35)); trend=trend+np.where(x.ema20>x.ema20.shift(3),10,0); x['trend_score']=np.clip(trend,0,100)
    x['momentum_score']=np.clip(100-(x.rsi14-62).abs()*2.2,0,100)
    vr=x.volume/x.vol_ma20.replace(0,np.nan); x['volume_score']=np.clip(45+(vr-1)*45,0,100)
    dist=(x.close-x.ema20)/x.atr14.replace(0,np.nan); setup=90-dist.abs()*25+np.where(x.close>x.open,8,-5); x['setup_score']=np.clip(setup,0,100)
    x['sentinel_score']=(.35*x.trend_score+.25*x.momentum_score+.2*x.volume_score+.2*x.setup_score).clip(0,100)
    range_rel=(x.high-x.low)/x.close; vol_comp=(x.ret_std20/x.ret_std20.rolling(100).median().replace(0,np.nan))*30; shock=x.zret.abs()*12; range_comp=(range_rel/range_rel.rolling(100).median().replace(0,np.nan))*15
    x['extreme_risk']=np.clip(vol_comp.fillna(0)+shock.fillna(0)+range_comp.fillna(0)-30,0,100)
    return x
