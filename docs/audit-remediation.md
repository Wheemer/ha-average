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


## Follow-up batch

- **M5:** no-ID edits matching an existing imported name/configuration produce an
  actionable Repairs notice instead of silently creating another sensor. For a
  single matching definition, the edit is refused until its existing registry ID
  is added; explicit adoption reuses the entry and entity. Intentionally multiple
  same-name YAML definitions remain supported with a warning. Completely changed
  names and sources cannot be reliably inferred as edits; keep explicit IDs.
- **M7/M8:** manifest version/tracker are authoritative; deterministic offline
  metadata synchronization updates generated constants and genuine runtime
  dependencies, preserving the independent HACS minimum. The pre-commit gate is
  non-mutating. The release helper prepares metadata only, without commits/tags.
- **M10/M11:** replace stale HACS information and contribution instructions with
  fork links, supported migration and the actual inherited CC BY-NC-SA license.
- **M12/L25/L28:** repair the Bandit profile, run Bandit in CI, align pre-commit
  Ruff with CI and remove the unused conflicting pyproject Ruff configuration.
- **L19/L21:** invalid imports now abort with a translated reason rather than an
  unhandled validation exception; UI creation rejects empty/whitespace names.
- **L23/L24/L31/L32:** remove pip from runtime requirements, identify the current
  fork maintainer, fix issue links/nonexistent diagnostics and test documentation.

Other low/informational findings remain pending verification. No live system was
accessed and no release was published for this follow-up.


## Calculation and lifecycle follow-up

- **L2/L6:** undefined substitutions now contribute to diagnostic count/extrema;
  projected trends use the configured precision, including legacy negative values.
- **L9/L10/L11:** tracked refresh waiters are cancelled and awaited for at most one
  second during unload. Running SQL remains shielded and registered across
  replacement entities. Failed/cancelled refreshes clear partial diagnostics and
  stale values; a failed attempt does not consume the retry throttle window.
  STOP also cancels the integration's refresh waiters without cancelling SQL.
- **L7/L12/L13/L17/L18/L29:** availability checks do not emit conversion errors or
  mutate their budgets; both calculation modes report conversion summaries.
  Repeated identical current-value conversion tracebacks are suppressed until
  data/units change or the source recovers. Full
  State objects are absent from history/conversion logs. Missing-history and
  malformed-boundary warnings are deduplicated while retries continue. Template
  error handling accepts non-string exception arguments. Scalar legacy duration
  formats are normalized and malformed formats fail before polling arithmetic.
- **L4:** reversed boundaries retain the documented legacy swap with a warning.
- **L3/L15/L16/L20/L22:** document the existing no-history/backfill behavior,
  reload requirement for changed group membership, template refresh cadence,
  negative precision and shared import-notice dismissal semantics.
- **L5 verification:** retain the strict source-count guard. A recovered live
  source has not yet contributed to a previously partial history average; making
  that result available before recalculation would weaken strict availability.
- **L27:** enforce measured coverage >=93% and strict markers in the full CI
  matrix, while keeping local focused tests usable without a full-suite floor.
- **I4/I16:** clamp weighting timestamps to the requested interval and use public
  hashlib SHA-1 with usedforsecurity=False for legacy identity hashes. Existing
  golden identity and real Recorder regression tests remain unchanged in result.

- **L30 verification:** keep positive scan intervals configurable in YAML/UI.
  A forced 20-second floor would reject existing intentional configurations;
  document the SQL-frequency tradeoff instead of silently clamping user settings.
- **L26:** remove blanket mypy error suppression, correct nullable state/period
  annotations and accumulator typing, and run real type checking in both CI
  environments. The single narrow call-arg exception documents Core's dynamic
  flow-registration keyword; unused ignores are errors.

This does not claim that SQL execution can be cancelled. Remaining informational
observations are documented rather than treated as runtime bugs. No live Home
Assistant was accessed and no release was published.
