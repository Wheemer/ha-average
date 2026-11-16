# Independent audit remediation

Tracking verification against `HA-Average-v2.5.0-Audit-Findings.md` (v2.5.0,
commit `7484bd40`). The audit report remains external and unchanged.

## Verified and addressed in this patch

| Finding | Evidence and change |
| --- | --- |
| H3: duplicate YAML IDs | Four new real-Core regression cases reproduced the destructive behavior before the fix. Preflight all YAML blocks, refuse conflicting explicit IDs with a Repairs issue, give each `__legacy__` import its own fingerprint, and retain existing legacy entry/entity identities. YAML reloads still support source and name changes with stable explicit IDs. |
| H1: temperature order/latch | Reproduced source-order-dependent results and stale mode after metadata removal. Choose fresh deterministic metadata before consuming readings; unitless temperature readings retain the documented HA-unit assumption. Test both current and history paths, both source orders and explicit attributes. |
| H2 / M3: oversized or stalled history | Reproduced unbounded windows and stalled waits. Add YAML/UI `max_history_period` (31 days) and `history_query_timeout` (60 seconds), fail visibly without truncation, and retain shielded SQL completion/backpressure across reloads. Larger legitimate windows can be configured explicitly. A waiter timeout cannot stop running SQL. |
| M1: non-finite substitutes/results | Reproduced infinity/NaN publication, precision-zero exceptions and boolean substitutes. Shared YAML/UI finite-number validation, defensive stored-option/restore handling, finite computed results, and normalized weighted contributions. |
| M2: sub-second windows | Reproduced a 400 ms window yielding zero. Keep fractional timestamps throughout weighting/cache comparisons and reject a nonpositive elapsed interval. |
| M4: missing Recorder | Reproduced Core get_instance raising KeyError. Report unavailable, warn once while absent, and retry without consuming a failed throttle window. |
| M6: removed YAML options | Replace imported options with the active YAML definition, clearing removed optional settings while preserving sensor identity. Covered by a real YAML reload test. |
| M9: minimum-version coverage | Add a CI job that reads the declared minimum from hacs.json and runs native lifecycle, recorder and UI-schema harnesses on that exact Core image. This is minimum-version API coverage, not the full pytest matrix on older Core. |
| L8 / L14 | Reject boolean period boundaries; discard malformed/non-finite restored sensor values. |

Other findings remain pending independent verification. In particular, this patch
does not claim to fix metadata-generation hooks, stale contribution/HACS pages,
tooling gates, or every low/informational observation in the audit.

## Validation boundaries

Tests use temporary Home Assistant instances, synthetic sources and isolated
Recorder databases on the development server. No live Home Assistant is accessed.
Native lifecycle/UI-schema harnesses also run on the advertised minimum Core
2026.4.0. A green suite is not proof of live installation behavior or SQL
cancellation, and this patch does not claim that timed-out database work stops.
