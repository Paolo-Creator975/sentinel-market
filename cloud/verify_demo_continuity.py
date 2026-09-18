#!/usr/bin/env python3
"""Read-only preflight for moving the frozen demo to another PostgreSQL host."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REQUIRED_TABLES = (
    "hourly_bars",
    "worker_runs",
    "crypto24_opportunity_observations",
    "crypto24_paper_positions",
    "crypto24_cash_flows",
    "crypto24_equity_marks",
)


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def verify() -> dict:
    import psycopg
    from psycopg.rows import dict_row
    from app.config_guard import load_crypto_24h_candidate

    database_url = os.environ["DATABASE_URL"]
    expected_start = parse_timestamp(os.environ["EXPECTED_ACTIVATED_AT"])
    expected_end = parse_timestamp(os.environ["EXPECTED_ENDS_AT"])
    config = load_crypto_24h_candidate(ROOT)

    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        meta_rows = connection.execute(
            """SELECT key,value FROM sentinel_meta
               WHERE key IN ('crypto24_activated_at','crypto24_demo_ends_at',
                             'crypto24_candidate_config_sha')"""
        ).fetchall()
        meta = {row["key"]: row["value"] for row in meta_rows}
        missing = {
            "crypto24_activated_at",
            "crypto24_demo_ends_at",
            "crypto24_candidate_config_sha",
        } - set(meta)
        if missing:
            raise RuntimeError(f"migration is missing frozen metadata: {sorted(missing)}")

        actual_start = parse_timestamp(meta["crypto24_activated_at"])
        actual_end = parse_timestamp(meta["crypto24_demo_ends_at"])
        if actual_start != expected_start:
            raise RuntimeError(f"activation changed: {actual_start} != {expected_start}")
        if actual_end != expected_end:
            raise RuntimeError(f"demo end changed: {actual_end} != {expected_end}")
        if meta["crypto24_candidate_config_sha"] != config["sha256"]:
            raise RuntimeError("database strategy hash differs from frozen source")

        counts = {}
        for table in REQUIRED_TABLES:
            counts[table] = connection.execute(
                f"SELECT COUNT(*) AS count FROM {table}"
            ).fetchone()["count"]

        run_status = connection.execute(
            """SELECT run_hour,status,bars_ok,signals_ok
               FROM worker_runs WHERE status='OK' ORDER BY run_hour DESC LIMIT 1"""
        ).fetchone()
        if not run_status or run_status["status"] != "OK":
            raise RuntimeError("migrated database has no successful worker run")

        positions = connection.execute(
            """SELECT
                 COUNT(*) FILTER (WHERE status='OPEN') AS open_count,
                 COUNT(*) FILTER (WHERE status='CLOSED') AS closed_count,
                 COALESCE(SUM(realized_pnl_eur),0) AS realized_pnl
               FROM crypto24_paper_positions"""
        ).fetchone()

    return {
        "status": "OK",
        "strategy_id": config["strategy_id"],
        "strategy_sha256": config["sha256"],
        "activated_at": actual_start.isoformat(),
        "ends_at": actual_end.isoformat(),
        "table_counts": counts,
        "latest_worker_run": dict(run_status),
        "positions": dict(positions),
    }


if __name__ == "__main__":
    print("SENTINEL_MIGRATION_PREFLIGHT " + json.dumps(verify(), default=str, sort_keys=True))
