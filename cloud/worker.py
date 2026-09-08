import os,uuid
from pathlib import Path
import pandas as pd, psycopg
from psycopg.rows import dict_row
from app.config_guard import load_and_verify
from app.market import closed_hourly_bars,ALLOWED
ROOT=Path(__file__).resolve().parent; CFG=load_and_verify(ROOT); DB=os.environ['DATABASE_URL']; BASE_COST=.002; MAX_POS=3; ALLOC=.20; START=10000.
def schema(c):
 c.execute((ROOT/'sql'/'schema.sql').read_text()); c.execute("INSERT INTO sentinel_meta(key,value) VALUES('config_sha',%s) ON CONFLICT(key) DO NOTHING",(CFG['sha256'],));
 if c.execute("SELECT value FROM sentinel_meta WHERE key='config_sha'").fetchone()['value']!=CFG['sha256']: raise RuntimeError('config drift')
def equity(c): return START+float(c.execute("SELECT COALESCE(SUM(pnl_eur),0) p FROM paper_positions WHERE status='CLOSED'").fetchone()['p'])
def ingest(c,sym,b):
 for _,x in b.tail(200).iterrows(): c.execute("INSERT INTO hourly_bars(symbol,open_time,close_time,open,high,low,close,volume) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",(sym,x.open_time,x.close_time,x.open,x.high,x.low,x.close,x.volume))
 x=b.iloc[-1]; hi=float(b.high.tail(168).max()); f=float(x.close/hi-1); th=float(CFG['assets'][sym]); sig=f<=th
 c.execute("INSERT INTO signal_observations(symbol,signal_time,feature,threshold,is_signal,bar_close,high_168,config_sha) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",(sym,x.close_time,f,th,sig,float(x.close),hi,CFG['sha256'])); return x
def settle(c,sym,t):
 for p in c.execute("SELECT * FROM paper_positions WHERE symbol=%s AND status='OPEN' AND exit_due<=%s",(sym,t)).fetchall():
  bar=c.execute("SELECT open_time,open FROM hourly_bars WHERE symbol=%s AND open_time>=%s ORDER BY open_time LIMIT 1",(sym,p['exit_due'])).fetchone()
  if bar:
   gross=float(bar['open'])/float(p['entry_price'])-1; net=gross-BASE_COST; pnl=float(p['notional_eur'])*net
   c.execute("UPDATE paper_positions SET status='CLOSED',exit_time=%s,exit_price=%s,gross_return=%s,net_return=%s,pnl_eur=%s WHERE position_id=%s AND status='OPEN'",(bar['open_time'],bar['open'],gross,net,pnl,p['position_id']))
def open_pending(c,sym):
 for s in c.execute("SELECT * FROM signal_observations s WHERE symbol=%s AND is_signal=TRUE AND NOT EXISTS(SELECT 1 FROM paper_positions p WHERE p.symbol=s.symbol AND p.signal_time=s.signal_time) ORDER BY signal_time",(sym,)).fetchall():
  if c.execute("SELECT 1 FROM paper_positions WHERE symbol=%s AND status='OPEN'",(sym,)).fetchone(): return
  if c.execute("SELECT COUNT(*) n FROM paper_positions WHERE status='OPEN'").fetchone()['n']>=MAX_POS: return
  bar=c.execute("SELECT open_time,open FROM hourly_bars WHERE symbol=%s AND open_time>%s ORDER BY open_time LIMIT 1",(sym,s['signal_time'])).fetchone()
  if not bar: continue
  pid=str(uuid.uuid5(uuid.NAMESPACE_URL,f"{sym}|{s['signal_time']}|PD_LONG_REBOUND_24H_V1")); notional=equity(c)*ALLOC
  c.execute("INSERT INTO paper_positions(position_id,symbol,signal_time,entry_time,entry_price,exit_due,notional_eur,feature,threshold,status) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,'OPEN') ON CONFLICT DO NOTHING",(pid,sym,s['signal_time'],bar['open_time'],bar['open'],bar['open_time']+pd.Timedelta(hours=24),notional,s['feature'],s['threshold']))
def mark(c,marks):
 t=max(x[0] for x in marks); realized=equity(c); prices={s:p for _,s,p in marks}; unreal=exp=0.
 for p in c.execute("SELECT * FROM paper_positions WHERE status='OPEN'").fetchall():
  if p['symbol'] in prices: unreal+=float(p['notional_eur'])*(prices[p['symbol']]/float(p['entry_price'])-1); exp+=float(p['notional_eur'])
 marked=realized+unreal; peak=max(float(c.execute("SELECT COALESCE(MAX(marked_equity),%s) p FROM equity_marks",(START,)).fetchone()['p']),marked); dd=max(0.,1-marked/peak)
 c.execute("INSERT INTO equity_marks(mark_time,cash_equity,marked_equity,open_exposure,drawdown) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(mark_time) DO UPDATE SET cash_equity=EXCLUDED.cash_equity,marked_equity=EXCLUDED.marked_equity,open_exposure=EXCLUDED.open_exposure,drawdown=EXCLUDED.drawdown",(t,realized,marked,exp,dd))
def run():
 rh=pd.Timestamp.now(tz='UTC').floor('h')
 with psycopg.connect(DB,row_factory=dict_row,autocommit=False) as c:
  schema(c); old=c.execute("SELECT status FROM worker_runs WHERE run_hour=%s",(rh,)).fetchone()
  if old and old['status']=='OK': return
  c.execute("INSERT INTO worker_runs(run_hour,started_at,status,config_sha) VALUES(%s,now(),'RUNNING',%s) ON CONFLICT(run_hour) DO UPDATE SET started_at=now(),status='RUNNING',error=NULL",(rh,CFG['sha256']))
  data={}; marks=[]
  for s in sorted(ALLOWED):
   b=closed_hourly_bars(s); data[s]=b; x=ingest(c,s,b); marks.append((x.close_time,s,float(x.close)))
  for s,b in data.items(): settle(c,s,b.iloc[-1].close_time)
  for s in sorted(ALLOWED): open_pending(c,s)
  mark(c,marks); c.execute("UPDATE worker_runs SET finished_at=now(),status='OK',bars_ok=7,signals_ok=7 WHERE run_hour=%s",(rh,)); c.commit()
if __name__=='__main__': run()
