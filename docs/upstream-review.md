# Upstream review — November 14, 2026

This fork tracks applicable contributions from Limych/ha-average. Upstream issues
remain upstream; this document records their disposition in this fork, without
claiming to have closed them or reproduced installation-specific failures.

## All eight open upstream PRs

| PR | Disposition in this fork |
| --- | --- |
| [272](https://github.com/Limych/ha-average/pull/272) | Incorporated with attribution. Core-maintained pytest fixtures, current Template API and template syntax. Fork-specific UI/import/lifecycle tests retained and adapted. |
| [271](https://github.com/Limych/ha-average/pull/271) | Incorporated unchanged with attribution: local 256/512 pixel icons. |
| [266](https://github.com/Limych/ha-average/pull/266) | Already present: packaging 25.0. |
| [265](https://github.com/Limych/ha-average/pull/265) | Already present: pre-commit 4.2. |
| [264](https://github.com/Limych/ha-average/pull/264) | Already present: PyGithub 2.6. |
| [262](https://github.com/Limych/ha-average/pull/262) | Already present: mypy 1.15. |
| [261](https://github.com/Limych/ha-average/pull/261) | Adapted, not blindly merged. Added opt-in undefined-history handling; defaults and strict source rules retained. Fixed always-available reporting, no-history handling, multi-gap weighting and invalid option combinations. Tests cover all these paths. |
| [260](https://github.com/Limych/ha-average/pull/260) | Already present: upstream copyright year update; license terms unchanged. |

Our temperature-unit PR [270](https://github.com/Limych/ha-average/pull/270) was
closed by us in July without upstream merge. Its fix is already in this fork.

## All 24 open upstream issues

| Issue | Status and next action in this fork |
| --- | --- |
| [269](https://github.com/Limych/ha-average/issues/269) | Report contains a stray `ATTR_` identifier absent from this fork. Existing metadata code and regression checks exercise the path; reported installation error not reproduced here. |
| [268](https://github.com/Limych/ha-average/issues/268) | Backlog: area/label source selection needs explicit filtering and registry-change semantics; no automatic source membership changes added. |
| [267](https://github.com/Limych/ha-average/issues/267) | Reproduced a remaining closed-window cache path that blocked temperature metadata arriving after startup. Cache validity now includes source unit/device-class metadata and the configured temperature unit; native values and unit labels are recalculated together. Existing startup recovery tests retained. |
| [263](https://github.com/Limych/ha-average/issues/263) | Clarified in README: time-weighted level of a cumulative total is not consumption per day. |
| [256](https://github.com/Limych/ha-average/issues/256) | Source-loss recovery covered by native tests; weekly failure not reproduced. Needs a minimal failing trace/config rather than a claim of resolution. |
| [243](https://github.com/Limych/ha-average/issues/243) | Reproduced and fixed rounded-end caching of unavailable, partial and current-value-fallback results; these now retry at the configured interval instead of requiring a reload. Successful complete closed windows remain cached. The native Quick Reload handler preserves identity and working source listeners with YAML active or commented out; other installation-specific causes remain unproven. No automatic deletion of imported entries. Import notices now direct users to verify identities/settings/history before commenting out YAML for UI management. |
| [225](https://github.com/Limych/ha-average/issues/225) | Backlog: seasonal accumulated temperature is a separate aggregation, not the current arithmetic/time-weighted mean. |
| [223](https://github.com/Limych/ha-average/issues/223) | Backlog: long-term statistics support; raw recorder retention limitation documented. No silent switch to hourly statistics. |
| [222](https://github.com/Limych/ha-average/issues/222) | Fixed reproduced event-driven refresh storm in strict history mode: source events obey update interval while publishing source loss immediately. Overlapping history refreshes are prevented. Large histories now also yield every 512 records so state and STOP callbacks can run; regression tests preserve numeric results. Overall query/CPU cost remains a follow-up. |
| [217](https://github.com/Limych/ha-average/issues/217) | Not reproduced on current Core: real native configuration checks finish for instantaneous, duration and template-range YAML, without creating entries/states. Bounded regression tests cover the path. The upstream reporter noted that a Core/integration update resolved their old hang; no speculative workaround added. |
| [185](https://github.com/Limych/ha-average/issues/185) | Unit-based temperature detection and metadata recovery covered, including sources with statistics-style metadata. |
| [184](https://github.com/Limych/ha-average/issues/184) | Backlog: hourly sampling changes averaging semantics and needs a separate explicit mode. |
| [183](https://github.com/Limych/ha-average/issues/183) | All calculation options are editable in Advanced, including legacy age/fallback and history-gap controls; native round-trip/explicit-clear checks preserve values and identity. |
| [175](https://github.com/Limych/ha-average/issues/175) | Reproduced a startup TypeError when a source-dependent period template returned None. Missing boundaries now remain unavailable without startup errors; invalid/future/zero-length periods cannot fall back to an instantaneous value or reuse a stale previous period. Valid boundaries recover through normal updates. The broader unspecified startup report is not claimed fully resolved. |
| [168](https://github.com/Limych/ha-average/issues/168) | Polling throttle covered. Reproduced event-loop starvation on 10,000 records and added cooperative processing with STOP checks; long-window database/query cost and timeout behavior remain separate follow-up work. |
| [143](https://github.com/Limych/ha-average/issues/143) | Stacked temperature-unit metadata recovery covered. |
| [123](https://github.com/Limych/ha-average/issues/123) | Intentional preservation: removing YAML does not delete imported entries or history. Remove unwanted entries explicitly from Integrations. Regression checks preserve entry and entity identity. |
| [109](https://github.com/Limych/ha-average/issues/109) | Partial averages skip unavailable/unknown sources; restore/recovery and invalid-value checks covered. New undefined-history flags support explicit gap policy. Original screenshot not reproduced. |
| [83](https://github.com/Limych/ha-average/issues/83) | Implemented optional source weights in Advanced and YAML, including partial-mode renormalization, strict-mode zero-weight rules, stable identity and finite/nonnegative validation. Existing sensors retain equal weights. |
| [56](https://github.com/Limych/ha-average/issues/56) | Implemented optional per-source attribute selection in YAML and Advanced. Covers weather/local humidity, numeric attributes, recognized metadata, explicit temperature conversion, strict loss/recovery, history and weights. Compatible non-temperature units are still required; no implicit quantity switching. |
| [55](https://github.com/Limych/ha-average/issues/55) | Corrected README management route and described UI/YAML import behavior. |
| [26](https://github.com/Limych/ha-average/issues/26) | Added cautious comparison with Filter; no claim that one is universally more accurate. |
| [20](https://github.com/Limych/ha-average/issues/20) | Backlog: median of samples needs a separate explicit mode; arithmetic mean unchanged. |
| [8](https://github.com/Limych/ha-average/issues/8) | Backlog: trimmed/percentile averaging needs explicit trimming and weighting semantics. |

## Additional reproduced bug

Nonfinite source values (`nan`, `inf`, `-inf`) could contaminate partial averages,
and precision zero could raise during integer conversion. Numeric extraction now
omits nonfinite values; strict mode continues to reject invalid required sources.
Regression tests verify invalid readings and recovery at both precision settings.

## Validation boundaries

All testing occurs in isolated Linux containers. Full Core/SQLite recorder shutdown
is exercised in a native test, including an actual state event during CLOSE and a
previously queued source callback after executor shutdown. This does not prove a
live installation's shutdown. No release or live deployment is implied by this work.


## Source-attribute follow-up

A required weather entity could retain numeric temperature attributes while its
state was unavailable. Strict availability now rejects the unavailable source
before reading retained attributes. Tests cover both default temperature and
explicit attributes. Ordinary non-temperature sources also recover units/device
class when metadata arrives after their first reading, without a reload.

A delayed calculation could also project `trending_towards` beyond a completed
period. The projection fraction is now bounded to the configured period and a
zero-length projection is omitted. This leaves the calculated mean unchanged.
A deterministic completed-period regression covers the delay case.


## Reported-bug verification

The rounded `end` template described in #243 exposed a concrete cache defect:
if the first closed-window result was unavailable, partial, or based on the
current-value fallback, unchanged time boundaries prevented any later query.
Only a fully calculated recorded-history result is now marked complete. Failed
new windows also clear completeness before querying, so a transient recorder
error cannot reuse the previous window's success flag. Errors still propagate.
The mean calculation, YAML options, UI controls, identities and history storage
are unchanged.

The Core Quick Reload handler and the real Average reload service are exercised
with temporary YAML and synthetic source readings. Unrelated core/theme reload
handlers are stubbed. Tests verify that source updates still arrive after reload
and that commenting out imported YAML does not remove entries or change their
unique IDs/settings. These tests do not establish the cause of every report in
#243 or the weekly incident in #256.

Late temperature metadata was separately reproduced against a completed cached
window (#267). Cache validity now includes source measurement metadata, not the
numeric current reading, so metadata arrival triggers recalculation without
requerying a complete fixed window on every normal source update. Changes to
Home Assistant's temperature unit also update the conversion target and published
native unit together. No YAML/UI settings or entity identities are migrated.


## Invalid-period and recorded-attribute bugs

A source-dependent boundary template returning `None` raised `TypeError` at
startup. A malformed boundary after a valid calculation reused the old period,
and a future period could accidentally publish a current-value average. Period
parsing now clears stale boundaries, accepts the documented datetime/timestamp
forms, treats missing inputs as unavailable, and does not switch a configured
history sensor to instantaneous averaging. Zero-length periods have no average.
Naive datetimes are interpreted in Home Assistant's configured timezone. Invalid
configured values still produce a useful error; missing source values do not.

A separate real SQLite recorder regression showed that a weather condition
remaining `sunny` caused attribute-only temperature and humidity updates to be
omitted by the old history API. Attribute-based sources now query all recorded
updates and use `last_updated` for weighting and extrema timestamps. Ordinary
numeric-state sources retain the existing state-change query and timestamps.
Native recorder tests cover weather, climate, water-heater, selected numeric
attributes and ordinary numeric sensors, using a FIFO recorder commit barrier.
The averaging formula and existing YAML/UI configuration fields are unchanged.
