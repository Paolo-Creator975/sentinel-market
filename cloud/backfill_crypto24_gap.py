#!/usr/bin/env python3
"""Replay missing hourly crypto24 decisions after an infrastructure gap."""

import json
import os
import uuid
from pathlib import Path

import pandas as pd
import psycopg
from psycopg.rows import dict_row

from app.config_guard import load_crypto_24h_candidate
from app.crypto_24h import calculate_opportunity, plan_paper_position
from app.market import ALLOWED, closed_hourly_bars


ROOT = Path(__file__).resolve().parent
DB = os.environ["DATABASE_URL"]
CFG = load_crypto_24h_candidate(ROOT)
APPLY = os.getenv("BACKFILL_APPLY", "false").lower() == "true"
START_EQUITY = 1000.0


def contributed_equity(conn, at_time):
    row = conn.execute(
        """SELECT COALESCE(SUM(amount_eur),0) AS total
           FROM crypto24_cash_flows WHERE flow_month <= %s""",
        (at_time.date().replace(day=1),),
    ).fetchone()
    return START_EQUITY + float(row["total"])


def realized_equity(conn, at_time):
    contributed = contributed_equity(conn, at_time)
    pnl = conn.execute(
        "SELECT COALESCE(SUM(realized_pnl_eur),0) AS total FROM crypto24_paper_positions"
    ).fetchone()
    return contributed, contributed + float(pnl["total"])


def open_risk(conn):
    row = conn.execute(
        """SELECT COALESCE(SUM(
             GREATEST((entry_price-stop_price)/entry_price,0)*remaining_notional_eur),0) AS total
           FROM crypto24_paper_positions WHERE status='OPEN'"""
    ).fetchone()
    return float(row["total"])


def settle_hour(conn, open_time, bars_by_symbol):
    cost = float(CFG["round_trip_cost_rate"])
    fraction = float(CFG["first_profit_fraction"])
    positions = conn.execute(
        "SELECT * FROM crypto24_paper_positions WHERE status='OPEN' ORDER BY entry_time,symbol"
    ).fetchall()
    for original in positions:
        p = dict(original)
        bar = bars_by_symbol[p["symbol"]].get(open_time)
        if not bar or open_time <= p["last_checked_time"]:
            continue
        exit_price = reason = None
        if float(bar["low"]) <= float(p["stop_price"]):
            exit_price = min(float(bar["open"]), float(p["stop_price"]))
            reason = "stop"
        elif open_time >= p["exit_due"]:
            exit_price = float(bar["open"])
            reason = "max_hold"
        if exit_price is not None:
            amount = float(p["remaining_notional_eur"])
            pnl = amount * (exit_price / float(p["entry_price"]) - 1 - cost)
            total_pnl = float(p["realized_pnl_eur"]) + pnl
            conn.execute(
                """UPDATE crypto24_paper_positions SET status='CLOSED',
                   remaining_notional_eur=0,realized_pnl_eur=%s,exit_time=%s,exit_price=%s,
                   exit_reason=%s,last_checked_time=%s WHERE position_id=%s""",
                (total_pnl, open_time, exit_price, reason, open_time, p["position_id"]),
            )
            continue
        if (not p["first_target_hit"] and
                float(bar["high"]) >= float(p["first_target_price"])):
            price = max(float(bar["open"]), float(p["first_target_price"]))
            amount = float(p["initial_notional_eur"]) * fraction
            pnl = amount * (price / float(p["entry_price"]) - 1 - cost)
            conn.execute(
                """UPDATE crypto24_paper_positions SET first_target_hit=TRUE,
                   remaining_notional_eur=remaining_notional_eur-%s,
                   realized_pnl_eur=realized_pnl_eur+%s,stop_price=entry_price,
                   last_checked_time=%s WHERE position_id=%s""",
                (amount, pnl, open_time, p["position_id"]),
            )
        else:
            conn.execute(
                "UPDATE crypto24_paper_positions SET last_checked_time=%s WHERE position_id=%s",
                (open_time, p["position_id"]),
            )


def open_hour(conn, open_time, bars_by_symbol):
    candidates = conn.execute(
        """SELECT o.* FROM crypto24_opportunity_observations o
           WHERE o.decision IN ('TECHNICAL_CANDIDATE','CANDIDATE')
             AND o.signal_time < %s
             AND NOT EXISTS (SELECT 1 FROM crypto24_paper_positions p
                             WHERE p.symbol=o.symbol AND p.signal_time=o.signal_time)
           ORDER BY o.signal_time,o.score DESC,o.symbol""",
        (open_time,),
    ).fetchall()
    for obs in candidates:
        frame = bars_by_symbol[obs["symbol"]]
        entry_times = [t for t in frame if t > obs["signal_time"]]
        if not entry_times or min(entry_times) != open_time:
            continue
        if conn.execute(
            "SELECT 1 FROM crypto24_paper_positions WHERE symbol=%s AND status='OPEN'",
            (obs["symbol"],),
        ).fetchone():
            continue
        bar = frame[open_time]
        contributed, equity = realized_equity(conn, open_time)
        plan = plan_paper_position(
            float(bar["open"]), float(obs["hourly_volatility"]), float(obs["score"]),
            equity, contributed, open_risk(conn), CFG,
        )
        if not plan:
            continue
        pid = str(uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"{obs['symbol']}|{obs['signal_time']}|{CFG['strategy_id']}",
        ))
        conn.execute(
            """INSERT INTO crypto24_paper_positions(position_id,symbol,signal_time,
               entry_time,entry_price,exit_due,last_checked_time,initial_notional_eur,
               remaining_notional_eur,initial_risk_eur,stop_price,first_target_price,score,
               config_sha,status) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'OPEN')
               ON CONFLICT(symbol,signal_time) DO NOTHING""",
            (pid, obs["symbol"], obs["signal_time"], open_time, bar["open"],
             open_time + pd.Timedelta(hours=int(CFG["maximum_holding_hours"])),
             open_time, plan["notional_eur"], plan["notional_eur"], plan["risk_eur"],
             plan["stop_price"], plan["first_target_price"], obs["score"], CFG["sha256"]),
        )


def mark_hour(conn, open_time, bars_by_symbol):
    closes = {symbol: float(rows[open_time]["close"])
              for symbol, rows in bars_by_symbol.items() if open_time in rows}
    if len(closes) != len(ALLOWED):
        return
    mark_time = open_time + pd.Timedelta(hours=1) - pd.Timedelta(milliseconds=1)
    contributed, realized = realized_equity(conn, open_time)
    positions = conn.execute(
        "SELECT * FROM crypto24_paper_positions WHERE status='OPEN'"
    ).fetchall()
    unrealized = exposure = 0.0
    for p in positions:
        amount = float(p["remaining_notional_eur"])
        unrealized += amount * (closes[p["symbol"]] / float(p["entry_price"]) - 1)
        exposure += amount
    marked = realized + unrealized
    peak = conn.execute(
        """SELECT COALESCE(MAX(marked_equity),%s) AS peak
           FROM crypto24_equity_marks WHERE mark_time <= %s""",
        (START_EQUITY, mark_time),
    ).fetchone()["peak"]
    peak = max(float(peak), marked)
    drawdown = max(0.0, 1 - marked / peak)
    conn.execute(
        """INSERT INTO crypto24_equity_marks(mark_time,contributed_equity,realized_equity,
           marked_equity,open_exposure,open_risk,drawdown) VALUES(%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT(mark_time) DO UPDATE SET contributed_equity=EXCLUDED.contributed_equity,
           realized_equity=EXCLUDED.realized_equity,marked_equity=EXCLUDED.marked_equity,
           open_exposure=EXCLUDED.open_exposure,open_risk=EXCLUDED.open_risk,
           drawdown=EXCLUDED.drawdown""",
        (mark_time, contributed, marked - unrealized, marked, exposure, open_risk(conn), drawdown),
    )


def run():
    fetched = {symbol: closed_hourly_bars(symbol, 1000) for symbol in sorted(ALLOWED)}
    with psycopg.connect(DB, row_factory=dict_row, autocommit=False,
                         options="-c lock_timeout=5000 -c statement_timeout=120000") as conn:
        existing = conn.execute(
            "SELECT COUNT(*) AS n FROM crypto24_paper_positions"
        ).fetchone()["n"]
        if existing:
            raise RuntimeError("backfill requires an empty crypto24 position table")
        activation = pd.Timestamp(conn.execute(
            "SELECT value FROM sentinel_meta WHERE key='crypto24_activated_at'"
        ).fetchone()["value"])

        bar_rows = []
        for symbol, frame in fetched.items():
            for b in frame.itertuples(index=False):
                bar_rows.append((symbol, b.open_time, b.close_time, b.open, b.high,
                                 b.low, b.close, b.volume))

        with conn.cursor() as cursor:
            cursor.executemany(
                """INSERT INTO hourly_bars(symbol,open_time,close_time,open,high,low,close,volume)
                   VALUES(%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT(symbol,open_time) DO NOTHING""",
                bar_rows,
            )

        frames = {}
        bars_by_symbol = {}
        observation_rows = []
        for symbol in sorted(ALLOWED):
            rows = conn.execute(
                """SELECT symbol,open_time,close_time,open,high,low,close,volume
                   FROM hourly_bars WHERE symbol=%s ORDER BY open_time""",
                (symbol,),
            ).fetchall()
            frame = pd.DataFrame(rows)
            frames[symbol] = frame
            bars_by_symbol[symbol] = {
                row.open_time: row for row in frame.itertuples(index=False)
            }
            for idx in range(len(frame)):
                if frame.iloc[idx].close_time < activation:
                    continue
                obs = calculate_opportunity(frame.iloc[:idx + 1], CFG, news_state="UNAVAILABLE")
                observation_rows.append((
                    obs["symbol"], obs["signal_time"], obs["bar_close"], obs["prior_high"],
                    obs["ema"], obs["hourly_volatility"], obs["momentum"], obs["volume_ratio"],
                    obs["breakout"], obs["new_breakout"], obs["trend_ok"], obs["score"],
                    obs["decision"], obs["reasons"], obs["news_state"], CFG["sha256"],
                ))

        with conn.cursor() as cursor:
            cursor.executemany(
                """INSERT INTO crypto24_opportunity_observations(
                   symbol,signal_time,asset_class,bar_close,prior_high,ema,hourly_volatility,momentum,
                   volume_ratio,breakout,new_breakout,trend_ok,score,decision,reasons,news_state,config_sha)
                   VALUES(%s,%s,'crypto',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT(symbol,signal_time) DO NOTHING""",
                observation_rows,
            )

        hours = sorted(set.intersection(*[set(rows) for rows in bars_by_symbol.values()]))
        for open_time in (t for t in hours if t >= activation.floor("h")):
            settle_hour(conn, open_time, bars_by_symbol)
            open_hour(conn, open_time, bars_by_symbol)
            mark_hour(conn, open_time, bars_by_symbol)

        result = conn.execute(
            """SELECT COUNT(*) FILTER (WHERE status='OPEN') AS open_count,
                      COUNT(*) FILTER (WHERE status='CLOSED') AS closed_count,
                      COALESCE(SUM(realized_pnl_eur),0) AS realized_pnl
               FROM crypto24_paper_positions"""
        ).fetchone()
        decisions = conn.execute(
            """SELECT decision,COUNT(*) AS n FROM crypto24_opportunity_observations
               WHERE signal_time >= %s GROUP BY decision ORDER BY decision""",
            (activation,),
        ).fetchall()
        output = {"apply": APPLY, "positions": dict(result),
                  "decisions": {r["decision"]: r["n"] for r in decisions},
                  "bars_loaded": len(bar_rows), "observations_replayed": len(observation_rows)}
        print("SENTINEL_CRYPTO24_BACKFILL " + json.dumps(output, default=str, sort_keys=True),
              flush=True)
        if APPLY:
            conn.commit()
        else:
            conn.rollback()


if __name__ == "__main__":
    run()
