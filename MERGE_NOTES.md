# Merge notes: `pet-9-select-contract` (incl. `pet-8`, `pet-10`) into `main` (with restored `server.transform`)

Branch `pet-12-detect-select-integration`. These notes are for the authors of both sides to check how each conflict was resolved.
Rule used: keep `main`'s architecture (one shared `server.actions`, one export path `server.transform`) and keep `pet-9`'s
artifact contract (provenance, issue codes, statuses, approval rule) unchanged.

| File | Conflict | Resolution |
|---|---|---|
| `server/select/select.py` | `main` added `input_digest` (content hash of parsed CSVs); `pet-9` added `provenance` (byte SHA of each CSV + `dataset_fingerprint`) and status `policy_valid` | **`pet-9` kept, `input_digest` removed.** One binding mechanism, shared with the Detect manifest. `release_id_explicit` from `main` kept (Transform needs to know the release id was given). |
| `server/select/search.py` | `main` extracted `risk_violations()`; `pet-9` added `outcome` and `budget_exhausted` | Both kept: `outcome` from `pet-9`; the violation strings come from `risk_violations()` (identical text to `pet-9`'s inline loop). |
| `server/select/transform.py` | `main` made it a thin layer over `server.actions`; `pet-9` added the approval gate and `--allow-unapproved` to the old in-module executor | `main`'s thin layer, plus `pet-9`'s gate extracted as `release_gate(plan, allow_unapproved)`. `apply()` keeps `pet-9`'s signature, `release_gate` stats and `NOT_APPROVED.txt`. |
| `server/select/__main__.py` | `main` delegates `transform` to `server.transform`; `pet-9` checked `artifacts.check_plan`, rejected preview-only rungs and exported via `transform.apply` | **Delegation kept** (one export path). `server.transform` now runs `artifacts.check_plan` first and supports every preview rung, so the preview-only guard is no longer needed. `--allow-unapproved` is passed through. `--spans` replaced by `--detect <dir>`. |
| `tests/test_preview.py` | both rewrote the legacy-export test | `main`'s delegation test, using a `policy_valid` plan with real `provenance`. |
| `README.md`, `combination.md` | module table / flow diagram / gaps table | `pet-9` text kept; Transform rows updated to the shared gate and `--detect`. |

## Behaviour changes in `server.transform` caused by the merge

- **Approval:** a release needs `status == measured_ok` **and** `outcome.approved` (the `pet-9` rule: provenance must be bound to a Detect manifest). Plans selected with the built-in detector are refused unless `--allow-unapproved` is passed.
- **`--allow-unapproved`:** exports with the same staged layout and checks. k/l/t and utility failures are recorded but do not gate; identifier, round-trip, row-map, join and suppression checks still do. Writes `NOT_APPROVED.txt` in `protected/` and `evaluation/`; status `unapproved_export`; `blocked` never exports.
- **Binding:** `artifacts.check_plan` runs before any output is created; a mismatch prints `[code]` on stderr and exits 2 (same as `pet-9`'s CLI).
- **Spans:** read from a Detect output dir (`--detect`) in contract-v1 format (`span_id`, `row_index`, no text), verified against the manifest sha256, the plan's `provenance.spans_sha256`, the input fingerprint and each recomputed `span_id`. The old `--spans TABLE.COLUMN=FILE` (record_id + text format) is removed.
- **Test counts:** 312 tests pass after the merge (`main` 268 + `pet-9`/`pet-8` tests; `tests/test_transform_stage.py` rewritten to bind plans like the CLI does).
