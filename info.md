# Average Sensor

Maintained fork of Limych's Average Sensor, with current-value and time-weighted
history averages, YAML imports, UI configuration and editable options.

Requires **Home Assistant 2026.4 or newer**. Install this fork as a custom
repository; it is not in the default HACS catalog.

- [Installation and configuration](https://github.com/Wheemer/ha-average#install)
- [Switching from the original integration](https://github.com/Wheemer/ha-average/blob/dev/docs/upgrading.md)
- [All YAML and UI options](https://github.com/Wheemer/ha-average/blob/dev/docs/configuration.md)
- [Report a bug](https://github.com/Wheemer/ha-average/issues/new/choose)
- [Releases and ZIP downloads](https://github.com/Wheemer/ha-average/releases)

Keep the `average` domain, existing sensor names and unique IDs unchanged when
switching. Do not delete configured sensors to replace the downloaded repository.
After YAML import, verify IDs, settings and history before commenting out the YAML
if you want UI management. Active YAML remains supported and is reapplied on reload.

Originally created by [Andrey “Limych” Khrolenok](https://github.com/Limych).
The inherited [CC BY-NC-SA 4.0 license](https://github.com/Wheemer/ha-average/blob/dev/LICENSE.md)
and attribution remain intact.

Support this fork through [GitHub Sponsors](https://github.com/sponsors/Wheemer)
or [PayPal](https://www.paypal.me/wheemer).
