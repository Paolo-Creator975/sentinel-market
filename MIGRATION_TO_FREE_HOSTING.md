# Railway to GitHub Actions + Neon migration

This migration changes infrastructure only. It must not change the frozen
`CRYPTO_24H_DEMO_V1` strategy, its activation time, its 90-day deadline, or
any simulated position.

## Safety sequence

1. Create a free Neon PostgreSQL project.
2. Export Railway PostgreSQL with `pg_dump` while Railway remains active.
3. Restore the dump into Neon with `pg_restore`.
4. Run `cloud/verify_demo_continuity.py` against Neon.
5. Add `NEON_DATABASE_URL` as a GitHub Actions secret.
6. Keep repository variable `SENTINEL_FREE_HOST_ACTIVE` unset or `false`.
7. Run the workflow manually and compare its summary with Railway.
8. Enable hourly Actions only after a 24–48 hour neutral parallel check.
9. Stop Railway only after the two paths produce equivalent decisions.

## Frozen continuity values

- Activation: `2026-09-13T19:07:52.404388+00:00`
- End: `2026-12-12T19:07:52.404388+00:00`
- Starting paper equity: EUR 1,000
- Markets: seven Binance spot crypto pairs already in frozen configuration
- Real trading: disabled

The workflow is intentionally gated by the repository variable
`SENTINEL_FREE_HOST_ACTIVE`. Merely merging the workflow cannot start a second
worker accidentally.
