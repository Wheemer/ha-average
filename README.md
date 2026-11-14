<div align="center">

<img src="custom_components/average/brand/icon@2x.png" width="120" alt="Average Sensor icon">

<h1>Average Sensor</h1>

### Current and time-weighted averages for Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-CUSTOM-FD7E14?style=for-the-badge&logo=home-assistant&logoColor=white&labelColor=555555)](https://hacs.xyz/)
[![GitHub Activity](https://img.shields.io/github/last-commit/Wheemer/ha-average/dev?style=for-the-badge&logo=github&logoColor=white&label=UPDATED&labelColor=555555&color=22C55E)](https://github.com/Wheemer/ha-average/commits/dev/)
[![License](https://img.shields.io/badge/LICENSE-CC%20BY--NC--SA%204.0-64748B?style=for-the-badge&labelColor=555555)](LICENSE.md)

[Features](#features) • [Install](#install) • [Configure](#configure) • [YAML Examples](#yaml-examples) • [Configuration reference](docs/configuration.md)

</div>

Average Sensor combines numeric readings from one or more sources into a single
sensor. Use their current values, or calculate a time-weighted average over a
rolling window or custom period.

Originally created by [Andrey “Limych” Khrolenok](https://github.com/Limych).
This fork adds UI configuration, editable options, source availability controls,
and fixes maintained in [Wheemer/ha-average](https://github.com/Wheemer/ha-average).

## Features

- Average current readings or recorded history over a rolling window or custom period.
- Configure and edit sensors in the UI, including source attributes, weights, precision and availability settings.
- Import existing YAML definitions while retaining their unique IDs.
- Convert compatible temperature readings to the configured temperature unit.

## Install

Requires **Home Assistant 2024.12 or newer**. History averages also require Recorder history for their sources.

### HACS

[![Add this repository to HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Wheemer&repository=ha-average&category=integration)

Add `https://github.com/Wheemer/ha-average` as an **Integration** custom repository in HACS, download **Average Sensor**, then restart Home Assistant when you are ready.

### Manual

Download a [release](https://github.com/Wheemer/ha-average/releases) and copy `custom_components/average` into your Home Assistant configuration directory. Restart Home Assistant to load the integration.

This fork and the original integration both use the `average` domain. Install one implementation at a time and preserve existing entity IDs and unique IDs when switching.

## Configure

Open **Settings > Devices & services > Add integration > Average Sensor**. Choose a name and source entities, then save. Use **Configure** on an existing entry to edit its settings. Additional calculation settings are available under **Advanced**.

Leave the averaging window unset to average current readings. Set a duration to calculate a time-weighted average from recorded history. **Require every source** makes the average unavailable when any required source has no usable reading; otherwise, valid sources are averaged.

## YAML Examples

Existing YAML configuration remains supported:

```yaml
sensor:
  - platform: average
    name: Room Average Temperature
    unique_id: room_average_temperature
    entities:
      - sensor.room_temperature_a
      - sensor.room_temperature_b
```

For a rolling history average, add:

```yaml
    duration:
      minutes: 15
```

### Moving an existing YAML sensor to the UI

After import, Home Assistant shows a **Repairs** notice. Verify the imported sensor's entity ID, settings and history, then comment out its YAML definition and manage it through **Configure**. The integration does not edit your YAML files.

You can also keep managing a sensor in YAML. Active YAML is imported again on startup or reload and can overwrite UI changes, so choose one configuration source per sensor.

See the [configuration reference](docs/configuration.md) for all options, additional examples and troubleshooting.

## Credits and Support

Average Sensor was originally created by [Andrey “Limych” Khrolenok](https://github.com/Limych).
This fork builds on his work, with the original attribution and license retained.

Support this fork's maintenance through [GitHub Sponsors](https://github.com/sponsors/Wheemer) or [PayPal](https://www.paypal.me/wheemer).

## License

Licensed under **Creative Commons Attribution-NonCommercial-ShareAlike 4.0
International (CC BY-NC-SA 4.0)**. See [LICENSE.md](LICENSE.md) for the full terms.
