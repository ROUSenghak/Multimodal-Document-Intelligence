# E8 reader smoke

- **Status:** frozen technical diagnostic; not a scored experiment.
- **Date:** 2026-11-25.
- **Source run:** `experiments/runs/e8_smoke/20261125T124909290128Z_cd901245_smoke` (git-ignored live run).
- **Committed implementation before execution:** notebook 07 at `e6b0bf6`.
- **Authorization:** at most 8 calls and $0.10; 6 calls were made for $0.0015431 at list price.
- **Data:** development questions already used in E6/E7. No untouched-pool question was read or sent.

`result.json` preserves the request fingerprints, token usage, latency, raw replies, technical gates and measured reader profile. It contains no API key and no image bytes. `SHA256SUMS` protects the package.

The smoke passed every technical gate. It does not approve the 354-call E8 run. The known-unanswerable S5 item received a schema-valid but non-abstaining answer; this is recorded as a behavioural warning, not hidden as a technical failure.
