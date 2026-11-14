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
| [267](https://github.com/Limych/ha-average/issues/267) | Temperature unit recovery already implemented; startup metadata regression retained. |
| [263](https://github.com/Limych/ha-average/issues/263) | Clarified in README: time-weighted level of a cumulative total is not consumption per day. |
| [256](https://github.com/Limych/ha-average/issues/256) | Source-loss recovery covered by native tests; weekly failure not reproduced. Needs a minimal failing trace/config rather than a claim of resolution. |
| [243](https://github.com/Limych/ha-average/issues/243) | Config-entry reload and restored identity tested; upstream Quick Reload report remains unproven. No automatic deletion of imported entries. |
| [225](https://github.com/Limych/ha-average/issues/225) | Backlog: seasonal accumulated temperature is a separate aggregation, not the current arithmetic/time-weighted mean. |
| [223](https://github.com/Limych/ha-average/issues/223) | Backlog: long-term statistics support; raw recorder retention limitation documented. No silent switch to hourly statistics. |
| [222](https://github.com/Limych/ha-average/issues/222) | Fixed reproduced event-driven refresh storm in strict history mode: source events obey update interval while publishing source loss immediately. Large-window processing performance remains a separate follow-up. |
| [217](https://github.com/Limych/ha-average/issues/217) | YAML schema/import tested. Old check-config hang lacks a reproducer; no claim of resolution. |
| [185](https://github.com/Limych/ha-average/issues/185) | Unit-based temperature detection and metadata recovery covered, including sources with statistics-style metadata. |
| [184](https://github.com/Limych/ha-average/issues/184) | Backlog: hourly sampling changes averaging semantics and needs a separate explicit mode. |
| [183](https://github.com/Limych/ha-average/issues/183) | UI configuration and Advanced interval/window controls implemented; native form/storage checks retained. |
| [175](https://github.com/Limych/ha-average/issues/175) | Missing/invalid source recovery covered; missing sources log at debug level. No forced zero fallback added. |
| [168](https://github.com/Limych/ha-average/issues/168) | Polling throttle covered; long-window query/processing benchmark and event-loop work remain backlog. |
| [143](https://github.com/Limych/ha-average/issues/143) | Stacked temperature-unit metadata recovery covered. |
| [123](https://github.com/Limych/ha-average/issues/123) | Intentional preservation: removing YAML does not delete imported entries or history. Remove unwanted entries explicitly from Integrations. Regression checks preserve entry and entity identity. |
| [109](https://github.com/Limych/ha-average/issues/109) | Partial averages skip unavailable/unknown sources; restore/recovery and invalid-value checks covered. New undefined-history flags support explicit gap policy. Original screenshot not reproduced. |
| [83](https://github.com/Limych/ha-average/issues/83) | Backlog: optional per-source weights with explicit zero/missing-weight rules. |
| [56](https://github.com/Limych/ha-average/issues/56) | Backlog: selecting weather/climate attributes needs unit/device-class rules. Template sensors remain an explicit workaround. |
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
