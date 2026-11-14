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
| [243](https://github.com/Limych/ha-average/issues/243) | Reproduced and fixed rounded-end caching of unavailable, partial and current-value-fallback results; these now retry at the configured interval instead of requiring a reload. Successful complete closed windows remain cached. Changed active YAML now reloads the affected loaded entry, including source edits with an explicit unique ID and non-identity option edits using a stable generated import ID. Unchanged YAML avoids needless entry reloads. Restored source counts no longer override the configured list, fixing strict-mode unavailability after a source-count edit. The native Quick Reload handler preserves identity and working source listeners with YAML active or commented out; other installation-specific causes remain unproven. No automatic deletion of imported entries. Import notices now direct users to verify identities/settings/history before commenting out YAML for UI management. |
| [225](https://github.com/Limych/ha-average/issues/225) | Backlog: seasonal accumulated temperature is a separate aggregation, not the current arithmetic/time-weighted mean. |
| [223](https://github.com/Limych/ha-average/issues/223) | Backlog: long-term statistics support; raw recorder retention limitation documented. No silent switch to hourly statistics. |
| [222](https://github.com/Limych/ha-average/issues/222) | Fixed reproduced event-driven refresh storm in strict history mode: source events obey update interval while publishing source loss immediately. Overlapping history refreshes are prevented. Large histories now also yield every 512 records so state and STOP callbacks can run; regression tests preserve numeric results. Lazy recorder-state decoding now runs in the recorder executor, and cancelled refreshes cannot start replacement queries while their original SQL job is still running. Ordinary numeric history also omits unused attributes and their SQL join; completed source lists are released before the next query loads. Database-specific query cost remains a follow-up. |
| [217](https://github.com/Limych/ha-average/issues/217) | Not reproduced on current Core: real native configuration checks finish for instantaneous, duration and template-range YAML, without creating entries/states. Bounded regression tests cover the path. The upstream reporter noted that a Core/integration update resolved their old hang; no speculative workaround added. |
| [185](https://github.com/Limych/ha-average/issues/185) | Unit-based temperature detection and metadata recovery covered, including sources with statistics-style metadata. |
| [184](https://github.com/Limych/ha-average/issues/184) | Backlog: hourly sampling changes averaging semantics and needs a separate explicit mode. |
| [183](https://github.com/Limych/ha-average/issues/183) | All calculation options are editable in Advanced, including legacy age/fallback and history-gap controls; native round-trip/explicit-clear checks preserve values and identity. |
| [175](https://github.com/Limych/ha-average/issues/175) | Reproduced a startup TypeError when a source-dependent period template returned None. Missing boundaries now remain unavailable without startup errors; invalid/future/zero-length periods cannot fall back to an instantaneous value or reuse a stale previous period. Valid boundaries recover through normal updates. The broader unspecified startup report is not claimed fully resolved. |
| [168](https://github.com/Limych/ha-average/issues/168) | Polling throttle covered. Reproduced event-loop starvation on 10,000 records and added cooperative processing with STOP checks; lazy attribute/timestamp decoding now runs in the recorder executor. Cancellation retains the active query until its executor job completes, preventing overlapping replacement SQL work. Unused numeric-history attributes and an unnecessary timestamp conversion are now omitted, and source-history lists are released before loading the next source. Database-specific long-window cost and the original ten-second warning remain separate validation work. |
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


## YAML reload, restored counts and source-age follow-up

Real YAML reload tests reproduced saved options changing while the running entity
kept its old source subscriptions. Reimports now schedule reload only for changed,
loaded entries. Stable generated import IDs receive non-identity option updates
as well as explicit-ID entries. Existing field-preservation behavior is retained;
no imported settings are discarded or identities rewritten.

A real options-flow test also reproduced a strict sensor becoming unavailable
permanently after its source list shrank: restored `count_sources` overwrote the
new configuration's source count. That diagnostic is now derived only from the
configured expanded source list, while the existing entity/unique ID is retained.

Configured `max_source_age` was ineffective for a quiet instantaneous sensor until
another event occurred, and a cached closed-period partial average could retain
an expired source. Age-limited instantaneous entities now use normal HA polling;
entities without an age limit remain event-driven. Freshness changes invalidate
history-cache reuse. Native polling tests publish expiry and recovery without
restarting the integration or adding a custom timer.

Compatibility checks found an unreleased regression from fractional-duration
support: whole seconds were serialized as floats, altering generated YAML import
IDs. Whole-second durations now retain the integer representation used at commit
8ad400c. Golden identity tests cover seconds, minutes and days. Both the original
and interim float representations are recognized on reimport without rewriting
stored entry IDs or creating a second entry; fractional seconds remain supported.
These fixes do not establish the cause of the weekly report in #256.


## Recorder decoding and cancellation follow-up (#168 / #222)

Real SQLite tests reproduced deferred recorder-state JSON decoding on Home
Assistant's event loop. History is now queried and its lazy attributes/timestamps
materialized in the recorder executor before cooperative averaging starts. The
state-change query for ordinary numeric sources and the all-updates query for
attribute sources are unchanged. Six native SQLite cases verify that decoding
happens outside the event-loop thread while preserving values, units and extrema.
A 100,000-record workload also retains the expected weighted mean and allows
other callbacks to run before processing finishes.

A separate real-thread test reproduced overlapping SQL work after cancelling an
in-progress refresh. Cancelling an asyncio waiter cannot stop its SQL thread.
The underlying executor future is now shielded and retained until it actually
finishes; polls and direct refreshes cannot submit replacement work for the same
sensor during that interval. Late errors are logged and retrieved, and subsequent
refreshes recover. Ordinary query errors still propagate normally. Both numeric
and attribute query paths are covered, and the tests fail against the prior code.

No timeout setting, hard SQL cancellation, sampling, data truncation or new
calculation mode was introduced. The ten-second message in #168 is a Core slow
update warning, not proof that its query was cancelled. These fixes reduce main
loop work and prevent cancelled-query pileups; they do not prove every database
or month-long history query will complete within ten seconds. Existing YAML
`scan_interval` and UI **History update interval** settings remain unchanged.


## Large-query payload and memory follow-up (#168 / #222)

Ordinary non-temperature numeric histories fetched the full attribute payload and
joined the attributes table even though their calculation only used numeric
states and change times. They now use Core's supported `no_attributes` query
option. Temperature histories retain their recorded units, and selected-attribute
sources retain all their required attributes. Only the timestamp used by each
calculation is materialized, rather than constructing both timestamps per point.

A separate regression test reproduced retention of the previous source's entire
history list while the next executor query loaded another large result. The
processed result is now released before the next source query is submitted.
This applies to both temperature and ordinary numeric histories.

Two native SQLite regressions use 10,000 recorded points each. They verify the
absence of the attributes join only for ordinary numeric sources, identical
state/time sequences, unchanged source and sample counts, availability, units and
extrema. The temperature case alternates recorded Celsius and Fahrenheit units
and verifies the converted mean and extrema. The earlier numeric/attribute,
strict-mode, weights, history-gap, import and UI tests remain passing.

An isolated native Core 2026.11.1 benchmark used 100,000 rows with a 512-byte
attribute payload. Timings below are the median of three query-and-decode runs;
peak allocations were measured separately with Python `tracemalloc`, not process
RSS. Both paths returned all 100,000 points. This measures local SQLite queries
and decoding, not total integration update time or live-system performance.

| Query/materialization path | Median seconds | Peak traced MiB |
| --- | ---: | ---: |
| Previous full metadata, both timestamps | 0.9436 | 140.78 |
| Numeric history without unused metadata | 0.6201 | 79.64 |
| Required metadata retained, only used timestamp | 0.8439 | 136.20 |

The numeric case reduced measured query/decode time by about 34% and peak traced
allocations by about 43% in this workload. Full-metadata histories still carry
their required attributes; their workload is not represented by the numeric
case's savings. No records are sampled, truncated or replaced by statistics.
No configuration fields, default intervals or identities change: existing YAML
and all UI controls retain their meanings. No live installation was accessed.
A ten-second query guarantee or database-driver timeout is not implied.
