# Sentinel methodological audit

This directory is an external, read-only control layer for the frozen
`CRYPTO_24H_DEMO_V1` paper demo.

It is deliberately not imported by `cloud/worker.py` or any decision module.
It cannot create, block, resize, open, or close a position. During the 90-day
demo its only permitted job is to detect and report a change to the frozen
runtime or a breach of the methodological rules in `ten_commandments.json`.

Run the local integrity check from the repository root:

```bash
python audit/verify_frozen_demo.py
```

An `OK` result means every protected file still has the exact Git blob hash
recorded from `main` at the start of this audit branch. Any mismatch is a hard
audit failure; it is not permission to alter the strategy during the demo.

The full methodological review remains scheduled for the end of the 90 days.
