
import os, uuid, time, math, json
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import psycopg
from psycopg.rows import dict_row
from app.config_guard import load_and_verify, load_and_verify_donchian, load_crypto_24h_candidate
from app.donchian_shadow import calculate_snapshot, position_weight
from app.crypto_24h import calculate_opportunity, plan_paper_position
from app.market import closed_hourly_bars, ALLOWED

ROOT=Path(__file__).resolve().parent
CFG=load_and_verify(ROOT)
DONCHIAN_CFG=load_and_verify_donchian(ROOT)
CRYPTO24_CFG=load_crypto_24h_candidate(ROOT)
DB=os.environ["DATABASE_URL"]
BASE_COST=0.002
MAX_POS=3
ALLOC=0.20
START_EQUITY=10000.0
SHADOW_START_EQUITY=1000.0
SHADOW_MONTHLY_FLOW=300.0
CRYPTO24_START_EQUITY=1000.0
CRYPTO24_MONTHLY_FLOW=300.0

def hour_floor(ts):
    return ts.floor("h")

def ensure_schema(conn):
    conn.execute((ROOT/"sql"/"schema.sql").read_text())
    conn.execute("""INSERT INTO sentinel_meta(key,value) VALUES('starting_equity_eur',%s)
                    ON CONFLICT(key) DO NOTHING""",(str(START_EQUITY),))
    conn.execute("""INSERT INTO sentinel_meta(key,value) VALUES('config_sha',%s)
                    ON CONFLICT(key) DO NOTHING""",(CFG["sha256"],))
    saved=conn.execute("SELECT value FROM sentinel_meta WHERE key='config_sha'").fetchone()["value"]
    if saved != CFG["sha256"]: raise RuntimeError("database config hash differs from frozen config")
    conn.execute("""INSERT INTO sentinel_meta(key,value) VALUES('donchian_shadow_config_sha',%s)
                    ON CONFLICT(key) DO NOTHING""",(DONCHIAN_CFG["sha256"],))
    conn.execute("""INSERT INTO sentinel_meta(key,value) VALUES('donchian_shadow_activated_at',now()::text)
                    ON CONFLICT(key) DO NOTHING""")
    shadow_saved=conn.execute("SELECT value FROM sentinel_meta WHERE key='donchian_shadow_config_sha'").fetchone()["value"]
    if shadow_saved != DONCHIAN_CFG["sha256"]:
        raise RuntimeError("database Donchian hash differs from frozen config")
    conn.execute("""INSERT INTO sentinel_meta(key,value) VALUES('crypto24_candidate_config_sha',%s)
                    ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value,updated_at=now()""",
                 (CRYPTO24_CFG["sha256"],))
    conn.execute("""INSERT INTO sentinel_meta(key,value) VALUES('crypto24_activated_at',now()::text)
                    ON CONFLICT(key) DO NOTHING""")
    conn.execute("""INSERT INTO sentinel_meta(key,value)
                    SELECT 'crypto24_demo_ends_at',(value::timestamptz+interval '90 days')::text
                    FROM sentinel_meta WHERE key='crypto24_activated_at'
                    ON CONFLICT(key) DO NOTHING""")
    conn.execute("""WITH activation AS (
          SELECT value::timestamptz activated_at FROM sentinel_meta WHERE key='crypto24_activated_at'
        ), months AS (
          SELECT generate_series(date_trunc('month',activated_at)+interval '1 month',
                                 date_trunc('month',now()),interval '1 month')::date flow_month
          FROM activation
        )
        INSERT INTO crypto24_cash_flows(flow_month,amount_eur)
        SELECT flow_month,%s FROM months ON CONFLICT(flow_month) DO NOTHING""",
        (CRYPTO24_MONTHLY_FLOW,))
    conn.execute("""WITH activation AS (
          SELECT value::timestamptz activated_at FROM sentinel_meta
          WHERE key='donchian_shadow_activated_at'
        ), months AS (
          SELECT generate_series(date_trunc('month',activated_at)+interval '1 month',
                                 date_trunc('month',now()),interval '1 month')::date flow_month
          FROM activation
        )
        INSERT INTO donchian_shadow_cash_flows(flow_month,amount_eur)
        SELECT flow_month,%s FROM months ON CONFLICT(flow_month) DO NOTHING""",
        (SHADOW_MONTHLY_FLOW,))

def current_realized_equity(conn):
    r=conn.execute("SELECT COALESCE(SUM(pnl_eur),0) pnl FROM paper_positions WHERE status='CLOSED'").fetchone()
    return START_EQUITY+float(r["pnl"])

def shadow_equity(conn):
    flows=conn.execute("SELECT COALESCE(SUM(amount_eur),0) total FROM donchian_shadow_cash_flows").fetchone()
    pnl=conn.execute("""SELECT COALESCE(SUM(pnl_eur),0) total FROM donchian_shadow_positions
                        WHERE status='CLOSED'""").fetchone()
    contributed=SHADOW_START_EQUITY+float(flows["total"])
    return contributed,contributed+float(pnl["total"])

def ingest_and_signal(conn,symbol,bars):
    for _,b in bars.iterrows():
        conn.execute("""INSERT INTO hourly_bars(symbol,open_time,close_time,open,high,low,close,volume)
          VALUES(%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(symbol,open_time) DO NOTHING""",
          (symbol,b.open_time,b.close_time,b.open,b.high,b.low,b.close,b.volume))
    last=bars.iloc[-1]
    high168=float(bars["high"].tail(168).max())
    feature=float(last["close"]/high168-1)
    threshold=float(CFG["assets"][symbol])
    is_signal=feature<=threshold
    conn.execute("""INSERT INTO signal_observations(symbol,signal_time,feature,threshold,is_signal,bar_close,high_168,config_sha)
      VALUES(%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(symbol,signal_time) DO NOTHING""",
      (symbol,last.close_time,feature,threshold,is_signal,float(last.close),high168,CFG["sha256"]))
    return last,feature,threshold,is_signal

def ingest_donchian_shadow(conn,symbol):
    rows=conn.execute("""SELECT symbol,open_time,close_time,open,high,low,close,volume
                         FROM hourly_bars WHERE symbol=%s ORDER BY open_time""",(symbol,)).fetchall()
    snapshot=calculate_snapshot(pd.DataFrame(rows),DONCHIAN_CFG)
    conn.execute("""INSERT INTO donchian_shadow_observations(
      symbol,signal_time,bar_close,high_336,low_168,ema_720,vol_168,breakout,trend_ok,
      daily_decision,entry_signal,exit_signal,config_sha)
      VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
      ON CONFLICT(symbol,signal_time) DO NOTHING""",
      (snapshot["symbol"],snapshot["signal_time"],snapshot["bar_close"],
       snapshot["high_336"],snapshot["low_168"],snapshot["ema_720"],snapshot["vol_168"],
       snapshot["breakout"],snapshot["trend_ok"],snapshot["daily_decision"],
       snapshot["entry_signal"],snapshot["exit_signal"],DONCHIAN_CFG["sha256"]))
    return snapshot

def ingest_crypto24_observer(conn,symbol):
    rows=conn.execute("""SELECT symbol,open_time,close_time,open,high,low,close,volume
                         FROM hourly_bars WHERE symbol=%s ORDER BY open_time""",(symbol,)).fetchall()
    obs=calculate_opportunity(pd.DataFrame(rows),CRYPTO24_CFG,news_state="UNAVAILABLE")
    conn.execute("""INSERT INTO crypto24_opportunity_observations(
      symbol,signal_time,asset_class,bar_close,prior_high,ema,hourly_volatility,momentum,
      volume_ratio,breakout,new_breakout,trend_ok,score,decision,reasons,news_state,config_sha)
      VALUES(%s,%s,'crypto',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
      ON CONFLICT(symbol,signal_time) DO NOTHING""",
      (obs["symbol"],obs["signal_time"],obs["bar_close"],obs["prior_high"],obs["ema"],
       obs["hourly_volatility"],obs["momentum"],obs["volume_ratio"],obs["breakout"],
       obs["new_breakout"],obs["trend_ok"],obs["score"],obs["decision"],obs["reasons"],obs["news_state"],
       CRYPTO24_CFG["sha256"]))
    return obs

def crypto24_equity(conn):
    flows=conn.execute("SELECT COALESCE(SUM(amount_eur),0) total FROM crypto24_cash_flows").fetchone()
    pnl=conn.execute("SELECT COALESCE(SUM(realized_pnl_eur),0) total FROM crypto24_paper_positions").fetchone()
    contributed=CRYPTO24_START_EQUITY+float(flows["total"])
    return contributed,contributed+float(pnl["total"])

def crypto24_open_risk(conn):
    row=conn.execute("""SELECT COALESCE(SUM(
      GREATEST((entry_price-stop_price)/entry_price,0)*remaining_notional_eur),0) total
      FROM crypto24_paper_positions WHERE status='OPEN'""").fetchone()
    return float(row["total"])

def try_open_crypto24(conn):
    active=conn.execute("""SELECT now() < value::timestamptz active
                            FROM sentinel_meta WHERE key='crypto24_demo_ends_at'""").fetchone()
    if not active or not active["active"]: return
    pending=conn.execute("""SELECT o.* FROM crypto24_opportunity_observations o
      WHERE o.decision IN ('TECHNICAL_CANDIDATE','CANDIDATE')
      AND NOT EXISTS (SELECT 1 FROM crypto24_paper_positions p
                      WHERE p.symbol=o.symbol AND p.signal_time=o.signal_time)
      ORDER BY o.signal_time,o.score DESC,o.symbol""").fetchall()
    for obs in pending:
        if conn.execute("SELECT 1 FROM crypto24_paper_positions WHERE symbol=%s AND status='OPEN'",
                        (obs["symbol"],)).fetchone():
            continue
        bar=conn.execute("""SELECT open_time,open FROM hourly_bars
          WHERE symbol=%s AND open_time>%s ORDER BY open_time LIMIT 1""",
          (obs["symbol"],obs["signal_time"])).fetchone()
        if not bar: continue
        contributed,equity=crypto24_equity(conn)
        plan=plan_paper_position(float(bar["open"]),float(obs["hourly_volatility"]),
             float(obs["score"]),equity,contributed,crypto24_open_risk(conn),CRYPTO24_CFG)
        if not plan: continue
        pid=str(uuid.uuid5(uuid.NAMESPACE_URL,
                           f"{obs['symbol']}|{obs['signal_time']}|{CRYPTO24_CFG['strategy_id']}"))
        conn.execute("""INSERT INTO crypto24_paper_positions(position_id,symbol,signal_time,
          entry_time,entry_price,exit_due,last_checked_time,initial_notional_eur,
          remaining_notional_eur,initial_risk_eur,stop_price,first_target_price,score,
          config_sha,status) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'OPEN')
          ON CONFLICT(symbol,signal_time) DO NOTHING""",
          (pid,obs["symbol"],obs["signal_time"],bar["open_time"],bar["open"],
           bar["open_time"]+pd.Timedelta(hours=int(CRYPTO24_CFG["maximum_holding_hours"])),
           bar["open_time"],plan["notional_eur"],plan["notional_eur"],plan["risk_eur"],
           plan["stop_price"],plan["first_target_price"],obs["score"],CRYPTO24_CFG["sha256"]))

def settle_crypto24(conn):
    cost=float(CRYPTO24_CFG["round_trip_cost_rate"])
    fraction=float(CRYPTO24_CFG["first_profit_fraction"])
    positions=conn.execute("SELECT * FROM crypto24_paper_positions WHERE status='OPEN'").fetchall()
    for original in positions:
        p=dict(original)
        bars=conn.execute("""SELECT open_time,open,high,low,close FROM hourly_bars
          WHERE symbol=%s AND open_time>%s ORDER BY open_time""",
          (p["symbol"],p["last_checked_time"])).fetchall()
        for bar in bars:
            if p["status"] != "OPEN": break
            exit_price=reason=None
            # Conservative convention when stop and target occur inside the same hourly bar.
            if float(bar["low"]) <= float(p["stop_price"]):
                exit_price=min(float(bar["open"]),float(p["stop_price"]))
                reason="stop"
            elif bar["open_time"] >= p["exit_due"]:
                exit_price=float(bar["open"])
                reason="max_hold"
            if exit_price is not None:
                amount=float(p["remaining_notional_eur"])
                pnl=amount*(exit_price/float(p["entry_price"])-1-cost)
                p["realized_pnl_eur"]=float(p["realized_pnl_eur"])+pnl
                p["remaining_notional_eur"]=0.0; p["status"]="CLOSED"
                conn.execute("""UPDATE crypto24_paper_positions SET status='CLOSED',
                  remaining_notional_eur=0,realized_pnl_eur=%s,exit_time=%s,exit_price=%s,
                  exit_reason=%s,last_checked_time=%s WHERE position_id=%s""",
                  (p["realized_pnl_eur"],bar["open_time"],exit_price,reason,
                   bar["open_time"],p["position_id"]))
                continue
            if (not p["first_target_hit"] and
                float(bar["high"]) >= float(p["first_target_price"])):
                exit_price=max(float(bar["open"]),float(p["first_target_price"]))
                amount=float(p["initial_notional_eur"])*fraction
                pnl=amount*(exit_price/float(p["entry_price"])-1-cost)
                p["remaining_notional_eur"]=float(p["remaining_notional_eur"])-amount
                p["realized_pnl_eur"]=float(p["realized_pnl_eur"])+pnl
                p["first_target_hit"]=True; p["stop_price"]=float(p["entry_price"])
                conn.execute("""UPDATE crypto24_paper_positions SET first_target_hit=TRUE,
                  remaining_notional_eur=%s,realized_pnl_eur=%s,stop_price=entry_price,
                  last_checked_time=%s WHERE position_id=%s""",
                  (p["remaining_notional_eur"],p["realized_pnl_eur"],bar["open_time"],p["position_id"]))
            else:
                conn.execute("UPDATE crypto24_paper_positions SET last_checked_time=%s WHERE position_id=%s",
                             (bar["open_time"],p["position_id"]))
                p["last_checked_time"]=bar["open_time"]

def mark_crypto24(conn,marks):
    if not marks: return
    t=max(x[0] for x in marks)
    contributed,realized=crypto24_equity(conn)
    prices={symbol:price for _,symbol,price in marks}
    positions=conn.execute("SELECT * FROM crypto24_paper_positions WHERE status='OPEN'").fetchall()
    unrealized=exposure=0.0
    for p in positions:
        if p["symbol"] in prices:
            amount=float(p["remaining_notional_eur"])
            unrealized+=amount*(prices[p["symbol"]]/float(p["entry_price"])-1)
            exposure+=amount
    marked=realized+unrealized
    peakrow=conn.execute("SELECT COALESCE(MAX(marked_equity),%s) peak FROM crypto24_equity_marks",
                         (CRYPTO24_START_EQUITY,)).fetchone()
    peak=max(float(peakrow["peak"]),marked)
    drawdown=max(0.0,1-marked/peak)
    conn.execute("""INSERT INTO crypto24_equity_marks(mark_time,contributed_equity,
      realized_equity,marked_equity,open_exposure,open_risk,drawdown)
      VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(mark_time) DO UPDATE SET
      contributed_equity=EXCLUDED.contributed_equity,realized_equity=EXCLUDED.realized_equity,
      marked_equity=EXCLUDED.marked_equity,open_exposure=EXCLUDED.open_exposure,
      open_risk=EXCLUDED.open_risk,drawdown=EXCLUDED.drawdown""",
      (t,contributed,realized,marked,exposure,crypto24_open_risk(conn),drawdown))

def log_crypto24_summary(conn,run_hour):
    """Emit one compact, read-only operational snapshot for Railway logs."""
    decisions=conn.execute("""SELECT decision,COUNT(*) AS n
      FROM crypto24_opportunity_observations
      WHERE signal_time >= %s-interval '2 hours'
      GROUP BY decision ORDER BY decision""",(run_hour,)).fetchall()
    positions=conn.execute("""SELECT symbol,status,entry_time,entry_price,exit_time,exit_price,
      initial_notional_eur,remaining_notional_eur,initial_risk_eur,realized_pnl_eur,
      score,first_target_hit,exit_reason
      FROM crypto24_paper_positions ORDER BY entry_time""").fetchall()
    latest_mark=conn.execute("""SELECT mark_time,contributed_equity,realized_equity,
      marked_equity,open_exposure,open_risk,drawdown
      FROM crypto24_equity_marks ORDER BY mark_time DESC LIMIT 1""").fetchone()
    meta=conn.execute("""SELECT key,value FROM sentinel_meta
      WHERE key IN ('crypto24_activated_at','crypto24_demo_ends_at') ORDER BY key""").fetchall()

    def number(value):
        return None if value is None else round(float(value),6)

    position_rows=[]
    for p in positions:
        position_rows.append({
          "symbol":p["symbol"],"status":p["status"],
          "entry_time":p["entry_time"],"entry_price":number(p["entry_price"]),
          "exit_time":p["exit_time"],"exit_price":number(p["exit_price"]),
          "initial_notional_eur":number(p["initial_notional_eur"]),
          "remaining_notional_eur":number(p["remaining_notional_eur"]),
          "initial_risk_eur":number(p["initial_risk_eur"]),
          "realized_pnl_eur":number(p["realized_pnl_eur"]),
          "score":number(p["score"]),"first_target_hit":p["first_target_hit"],
          "exit_reason":p["exit_reason"]})
    mark=None if not latest_mark else {
      "mark_time":latest_mark["mark_time"],
      "contributed_equity":number(latest_mark["contributed_equity"]),
      "realized_equity":number(latest_mark["realized_equity"]),
      "marked_equity":number(latest_mark["marked_equity"]),
      "open_exposure":number(latest_mark["open_exposure"]),
      "open_risk":number(latest_mark["open_risk"]),
      "drawdown":number(latest_mark["drawdown"])}
    payload={"run_hour":run_hour,"demo":{r["key"]:r["value"] for r in meta},
             "recent_decisions":{r["decision"]:r["n"] for r in decisions},
             "positions_total":len(position_rows),
             "positions_open":sum(p["status"]=="OPEN" for p in position_rows),
             "positions_closed":sum(p["status"]=="CLOSED" for p in position_rows),
             "positions":position_rows,"equity":mark}
    print("SENTINEL_CRYPTO24_SUMMARY "+json.dumps(payload,default=str,
          sort_keys=True,separators=(",",":")),flush=True)

def settle_due(conn,symbol,bars):
    px=float(bars.iloc[-1]["close"])
    t=bars.iloc[-1]["close_time"]
    due=conn.execute("""SELECT * FROM paper_positions
       WHERE symbol=%s AND status='OPEN' AND exit_due<=%s ORDER BY exit_due""",(symbol,t)).fetchall()
    for p in due:
        # Frozen semantics: use first stored hourly OPEN at/after exit_due; if absent, wait.
        bar=conn.execute("""SELECT open_time,open FROM hourly_bars
          WHERE symbol=%s AND open_time >= %s ORDER BY open_time LIMIT 1""",(symbol,p["exit_due"])).fetchone()
        if not bar: continue
        gross=float(bar["open"])/float(p["entry_price"])-1
        net=gross-BASE_COST
        pnl=float(p["notional_eur"])*net
        conn.execute("""UPDATE paper_positions SET status='CLOSED',exit_time=%s,exit_price=%s,
          gross_return=%s,net_return=%s,pnl_eur=%s WHERE position_id=%s AND status='OPEN'""",
          (bar["open_time"],bar["open"],gross,net,pnl,p["position_id"]))

def settle_donchian_shadow(conn):
    positions=conn.execute("SELECT * FROM donchian_shadow_positions WHERE status='OPEN'").fetchall()
    for p in positions:
        signal=conn.execute("""SELECT signal_time FROM donchian_shadow_observations
          WHERE symbol=%s AND exit_signal=TRUE AND signal_time>=%s
          ORDER BY signal_time LIMIT 1""",(p["symbol"],p["entry_time"])).fetchone()
        signal_bar=None
        if signal:
            signal_bar=conn.execute("""SELECT open_time,open FROM hourly_bars
              WHERE symbol=%s AND open_time>%s ORDER BY open_time LIMIT 1""",
              (p["symbol"],signal["signal_time"])).fetchone()
        due_bar=conn.execute("""SELECT open_time,open FROM hourly_bars
          WHERE symbol=%s AND open_time>=%s ORDER BY open_time LIMIT 1""",
          (p["symbol"],p["exit_due"])).fetchone()
        choices=[]
        if signal_bar: choices.append((signal_bar["open_time"],signal_bar,"signal"))
        if due_bar: choices.append((due_bar["open_time"],due_bar,"max_hold"))
        if not choices: continue
        _,bar,reason=min(choices,key=lambda item:item[0])
        gross=float(bar["open"])/float(p["entry_price"])-1
        net=gross-float(DONCHIAN_CFG["round_trip_cost_rate"])
        pnl=float(p["notional_eur"])*net
        conn.execute("""UPDATE donchian_shadow_positions SET status='CLOSED',exit_time=%s,
          exit_price=%s,gross_return=%s,net_return=%s,pnl_eur=%s,exit_reason=%s
          WHERE position_id=%s AND status='OPEN'""",
          (bar["open_time"],bar["open"],gross,net,pnl,reason,p["position_id"]))

def try_open_from_previous_signal(conn,symbol,bars):
    # Open only at the first hourly open strictly after signal_time.
    prev=conn.execute("""SELECT * FROM signal_observations s
      WHERE s.symbol=%s AND s.is_signal=TRUE
      AND NOT EXISTS (SELECT 1 FROM paper_positions p WHERE p.symbol=s.symbol AND p.signal_time=s.signal_time)
      ORDER BY signal_time""",(symbol,)).fetchall()
    for s in prev:
        if conn.execute("SELECT 1 FROM paper_positions WHERE symbol=%s AND status='OPEN'",(symbol,)).fetchone():
            return
        if conn.execute("SELECT COUNT(*) n FROM paper_positions WHERE status='OPEN'").fetchone()["n"]>=MAX_POS:
            return
        bar=conn.execute("""SELECT open_time,open FROM hourly_bars WHERE symbol=%s AND open_time>%s
                            ORDER BY open_time LIMIT 1""",(symbol,s["signal_time"])).fetchone()
        if not bar: continue
        equity=current_realized_equity(conn)
        notional=equity*ALLOC
        pid=str(uuid.uuid5(uuid.NAMESPACE_URL,f"{symbol}|{s['signal_time']}|PD_LONG_REBOUND_24H_V1"))
        conn.execute("""INSERT INTO paper_positions(position_id,symbol,signal_time,entry_time,entry_price,exit_due,
          notional_eur,feature,threshold,status) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,'OPEN')
          ON CONFLICT(symbol,signal_time) DO NOTHING""",
          (pid,symbol,s["signal_time"],bar["open_time"],bar["open"],
           bar["open_time"]+pd.Timedelta(hours=24),notional,s["feature"],s["threshold"]))

def try_open_donchian_shadow(conn):
    pending=conn.execute("""SELECT o.* FROM donchian_shadow_observations o
      WHERE o.entry_signal=TRUE
      AND NOT EXISTS (SELECT 1 FROM donchian_shadow_positions p
                      WHERE p.symbol=o.symbol AND p.signal_time=o.signal_time)
      ORDER BY ((o.bar_close/o.high_336)-1)/GREATEST(o.vol_168,1e-9) DESC,
               o.signal_time,o.symbol""").fetchall()
    for obs in pending:
        if conn.execute("""SELECT 1 FROM donchian_shadow_positions
                            WHERE symbol=%s AND status='OPEN'""",(obs["symbol"],)).fetchone():
            continue
        count=conn.execute("SELECT COUNT(*) n FROM donchian_shadow_positions WHERE status='OPEN'").fetchone()["n"]
        if count>=int(DONCHIAN_CFG["maximum_concurrent_positions"]): return
        bar=conn.execute("""SELECT open_time,open FROM hourly_bars
          WHERE symbol=%s AND open_time>%s ORDER BY open_time LIMIT 1""",
          (obs["symbol"],obs["signal_time"])).fetchone()
        if not bar: continue
        _,equity=shadow_equity(conn)
        notional=equity*position_weight(float(obs["vol_168"]),DONCHIAN_CFG)
        pid=str(uuid.uuid5(uuid.NAMESPACE_URL,
                           f"{obs['symbol']}|{obs['signal_time']}|{DONCHIAN_CFG['strategy_id']}"))
        conn.execute("""INSERT INTO donchian_shadow_positions(position_id,symbol,signal_time,
          entry_time,entry_price,exit_due,notional_eur,vol_168,config_sha,status)
          VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,'OPEN')
          ON CONFLICT(symbol,signal_time) DO NOTHING""",
          (pid,obs["symbol"],obs["signal_time"],bar["open_time"],bar["open"],
           bar["open_time"]+pd.Timedelta(hours=int(DONCHIAN_CFG["maximum_holding_hours"])),
           notional,obs["vol_168"],DONCHIAN_CFG["sha256"]))

def mark_equity(conn,marks):
    if not marks: return
    t=max(x[0] for x in marks)
    realized=current_realized_equity(conn)
    openpos=conn.execute("SELECT * FROM paper_positions WHERE status='OPEN'").fetchall()
    unreal=0.0; exposure=0.0
    prices={sym:px for _,sym,px in marks}
    for p in openpos:
        if p["symbol"] in prices:
            r=prices[p["symbol"]]/float(p["entry_price"])-1
            unreal += float(p["notional_eur"])*r
            exposure += float(p["notional_eur"])
    marked=realized+unreal
    peakrow=conn.execute("SELECT COALESCE(MAX(marked_equity),%s) peak FROM equity_marks",(START_EQUITY,)).fetchone()
    peak=max(float(peakrow["peak"]),marked)
    dd=max(0.0,1-marked/peak)
    conn.execute("""INSERT INTO equity_marks(mark_time,cash_equity,marked_equity,open_exposure,drawdown)
                    VALUES(%s,%s,%s,%s,%s) ON CONFLICT(mark_time) DO UPDATE SET
                    cash_equity=EXCLUDED.cash_equity,marked_equity=EXCLUDED.marked_equity,
                    open_exposure=EXCLUDED.open_exposure,drawdown=EXCLUDED.drawdown""",
                 (t,realized,marked,exposure,dd))

def mark_donchian_shadow(conn,marks):
    if not marks: return
    t=max(x[0] for x in marks)
    contributed,realized=shadow_equity(conn)
    positions=conn.execute("SELECT * FROM donchian_shadow_positions WHERE status='OPEN'").fetchall()
    prices={symbol:price for _,symbol,price in marks}
    unrealized=exposure=0.0
    for p in positions:
        if p["symbol"] in prices:
            unrealized+=float(p["notional_eur"])*(prices[p["symbol"]]/float(p["entry_price"])-1)
            exposure+=float(p["notional_eur"])
    marked=realized+unrealized
    peakrow=conn.execute("""SELECT COALESCE(MAX(marked_equity),%s) peak
                            FROM donchian_shadow_equity_marks""",(SHADOW_START_EQUITY,)).fetchone()
    peak=max(float(peakrow["peak"]),marked)
    drawdown=max(0.0,1-marked/peak)
    conn.execute("""INSERT INTO donchian_shadow_equity_marks(mark_time,contributed_equity,
      realized_equity,marked_equity,open_exposure,drawdown) VALUES(%s,%s,%s,%s,%s,%s)
      ON CONFLICT(mark_time) DO UPDATE SET contributed_equity=EXCLUDED.contributed_equity,
      realized_equity=EXCLUDED.realized_equity,marked_equity=EXCLUDED.marked_equity,
      open_exposure=EXCLUDED.open_exposure,drawdown=EXCLUDED.drawdown""",
      (t,contributed,realized,marked,exposure,drawdown))

def run_once():
    run_hour=pd.Timestamp.now(tz="UTC").floor("h")
    with psycopg.connect(DB,row_factory=dict_row,autocommit=False) as conn:
        ensure_schema(conn)
        existing=conn.execute("SELECT status FROM worker_runs WHERE run_hour=%s",(run_hour,)).fetchone()
        if existing and existing["status"]=="OK": return
        conn.execute("""INSERT INTO worker_runs(run_hour,started_at,status,config_sha)
                       VALUES(%s,now(),'RUNNING',%s)
                       ON CONFLICT(run_hour) DO UPDATE SET started_at=now(),status='RUNNING',error=NULL""",
                     (run_hour,CFG["sha256"]))
        bars_ok=signals_ok=0
        marks=[]
        try:
            data={}
            for symbol in sorted(ALLOWED):
                bars=closed_hourly_bars(symbol,1000)
                data[symbol]=bars
                last,feature,threshold,is_signal=ingest_and_signal(conn,symbol,bars)
                ingest_donchian_shadow(conn,symbol)
                ingest_crypto24_observer(conn,symbol)
                bars_ok+=1; signals_ok+=1
                marks.append((last.close_time,symbol,float(last.close)))
            # lifecycle order: settle exits, then open pending next-hour entries, then mark equity
            for symbol,bars in data.items(): settle_due(conn,symbol,bars)
            settle_donchian_shadow(conn)
            settle_crypto24(conn)
            for symbol,bars in data.items(): try_open_from_previous_signal(conn,symbol,bars)
            try_open_donchian_shadow(conn)
            try_open_crypto24(conn)
            mark_equity(conn,marks)
            mark_donchian_shadow(conn,marks)
            mark_crypto24(conn,marks)
            log_crypto24_summary(conn,run_hour)
            conn.execute("""UPDATE worker_runs SET finished_at=now(),status='OK',bars_ok=%s,signals_ok=%s
                            WHERE run_hour=%s""",(bars_ok,signals_ok,run_hour))
            conn.commit()
        except Exception as e:
            conn.rollback()
            with psycopg.connect(DB,row_factory=dict_row,autocommit=True) as c2:
                ensure_schema(c2)
                c2.execute("""INSERT INTO worker_runs(run_hour,started_at,finished_at,status,error,config_sha,bars_ok,signals_ok)
                   VALUES(%s,now(),now(),'ERROR',%s,%s,%s,%s)
                   ON CONFLICT(run_hour) DO UPDATE SET finished_at=now(),status='ERROR',error=EXCLUDED.error,
                     bars_ok=EXCLUDED.bars_ok,signals_ok=EXCLUDED.signals_ok""",
                  (run_hour,str(e)[:2000],CFG["sha256"],bars_ok,signals_ok))
            raise

if __name__=="__main__":
    run_once()
