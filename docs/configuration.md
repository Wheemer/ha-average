# Configuration reference

[Back to README](../README.md)

## Configure

1. Open **Settings > Devices & services > Integrations**.
2. Select **Add integration** and search for **Average Sensor**.
3. Enter a name and choose the source entities.
4. Choose whether to **Require every source**.
5. Open **Advanced** if you need an averaging window, custom period, update interval, or precision.
6. Save the sensor.

To edit an existing average, open its entry under **Average Sensor** and select
**Configure**. Saving options reloads that entry, so consumers may see a brief
availability change. Editing options does not require a full Home Assistant restart.

### Source availability

**Require every source** is directly visible in the main form and defaults
to **off**.

| Setting | Behavior |
| --- | --- |
| **Off** | Use the sources that provide usable values for the calculation. The average is unavailable when no usable values remain. |
| **On** | Mark the average unavailable if any required source is missing, unknown, unavailable, nonnumeric, nonfinite, or older than a configured source-age limit. |

Strict history averages publish source loss immediately. History recalculation
still respects the update interval. Valid source readings allow recovery; an
undefined-value fallback never overrides the strict source requirement.

For averages used by automations or control systems, choose availability behavior
that reflects whether a partial reading is acceptable.

### Advanced settings

| Setting | Purpose |
| --- | --- |
| **Averaging window** | Use recorded history for a fixed duration. Leave unset for a current-value average. |
| **Start / end time templates** | Use templates for a custom calculation period. |
| **History update interval** | Minimum interval between history refreshes; defaults to 20 seconds. Actual refresh timing also depends on Home Assistant's polling schedule. |
| **Source attributes** | Optional mapping of source IDs to attribute names, such as `weather.home: humidity`. |
| **Source weights** | Optional mapping of configured source IDs to relative weights. Leave empty for equal weights. |
| **Decimal places** | Decimal places used to round the result; defaults to 2. |

All calculation settings are editable in the UI. **Advanced** also contains
maximum source age, undefined-value fallback, and both undefined-history controls.
Existing YAML settings are presented as saved; opening the form does not reset
them. Clear an optional field to disable that setting.

## YAML Examples

YAML remains supported as an import path. Definitions are added under `sensor:`.
Keep a stable, explicit `unique_id` for an existing sensor.

### Current room temperature

```yaml
sensor:
  - platform: average
    name: Room Average Temperature
    unique_id: room_average_temperature
    entities:
      - sensor.room_temperature_a
      - sensor.room_temperature_b
```

### Rolling average with every source required

```yaml
sensor:
  - platform: average
    name: Temperature Average Last 15 Minutes
    unique_id: temperature_average_last_15_minutes
    entities:
      - sensor.room_temperature_a
      - sensor.room_temperature_b
    require_all_sources: true
    duration:
      minutes: 15
    scan_interval:
      seconds: 30
    precision: 2
```

### Average since midnight

```yaml
sensor:
  - platform: average
    name: Outside Temperature Today
    unique_id: outside_temperature_today
    entities:
      - sensor.outside_temperature
    start: "{{ now().replace(hour=0, minute=0, second=0, microsecond=0) }}"
    end: "{{ now() }}"
```

### Existing YAML installations

YAML definitions are imported into config entries. A notice appears under
Home Assistant **Repairs** after a successful import or recognition of an existing
entry. Before switching to UI management:

1. Find the imported entry under **Settings > Devices & services > Integrations > Average Sensor**.
2. Verify the existing entity ID, unique ID, settings, units, recorder history and long-term statistics are intact.
3. Comment out **only that sensor's Average Sensor YAML definition**. Keep the commented copy as a backup.
4. Manage the sensor through **Configure** in the UI, then dismiss the import notice.

The integration does not edit your YAML files. Removing or commenting out YAML
does **not** delete its imported entry or recorder history. Do not delete and
recreate the entry to switch configuration methods.

You can also keep managing a sensor from YAML. Leave its definition active and
make its changes there: active YAML is reimported on startup or YAML reload and
may overwrite later UI edits. Use one configuration source for each sensor.
After editing active YAML, the Average Sensor reload service or Quick Reload
applies changed settings to the loaded entry. Unchanged definitions do not trigger
an extra entry reload. As with a UI save, reloading a changed entry can briefly
affect its availability. Remove unwanted entries explicitly through **Devices & services**.

Do not change existing unique IDs or delete and recreate sensors as a migration
shortcut. The historical `unique_id: __legacy__` setting remains supported for
installations already using it; it is not recommended for new sensors.

### Average humidity from weather and a local sensor

Use **Advanced > Source attributes** to select an attribute for individual
sources. Sources omitted from the mapping keep their normal reading: numeric
entities use their state, and weather/climate/water-heater sources use their
current temperature by default.

```yaml
sensor:
  - platform: average
    name: Combined Humidity
    unique_id: combined_humidity
    entities:
      - weather.home
      - sensor.room_humidity
    source_attributes:
      weather.home: humidity
    require_all_sources: true
```

This combines the weather entity's `humidity` attribute with the local sensor's
numeric state. The mapping works for instantaneous and history averages, alongside
source weights. History includes attribute-only updates even when the entity's
main state stays unchanged. A missing or invalid selected attribute is an invalid reading;
strict mode becomes unavailable immediately, even if the weather condition still
says `sunny`.

Recognized temperature attributes (`temperature`, `current_temperature`,
`dew_point`, `apparent_temperature`) use temperature metadata and conversion.
`humidity` and `current_humidity` use percentage humidity metadata. Weather
`pressure` and `wind_speed` use their reported unit attributes. Other numeric
attributes are supported; their unit is taken from `<attribute>_unit` when present,
otherwise no unit is inferred. Only combine readings of the same quantity with
compatible units; non-temperature units are not automatically normalized.

Map explicitly listed entity IDs, not YAML group IDs. Clear the mapping to restore
default readings. To start measuring a different quantity, create a new average
rather than mixing different quantities in one sensor's existing recorder history.

### Weighted source contributions

Under **Advanced > Source weights**, or with YAML `weights`, use relative weights
for explicitly listed source entity IDs. For example, `2:1:1` gives one source
half the contribution when all three are available:

```yaml
sensor:
  - platform: average
    name: Weighted Room Temperature
    unique_id: weighted_room_temperature
    entities:
      - sensor.room_main_temperature
      - sensor.room_window_temperature
      - sensor.room_door_temperature
    weights:
      sensor.room_main_temperature: 2
      sensor.room_window_temperature: 1
      sensor.room_door_temperature: 1
```

Omitted weights default to `1`. Weight `0` removes a source's contribution to the
result, but **Require every source** still requires it to have a valid reading.
In partial mode, weights are renormalized over the sources with usable values;
if only zero-weight sources remain, the average is unavailable. Invalid, negative,
nonfinite, all-zero, and non-source weight mappings are rejected. When using
weights, list the source entities explicitly rather than weighting a YAML group.
For history averages, each source is time-weighted first, then its source weight
is applied. Clear the mapping to restore equal weighting.

## Options Reference

| YAML option | Default | Description |
| --- | --- | --- |
| `entities` | Required | Source entity IDs. YAML groups are expanded into their members when the sensor is created. |
| `name` | `Average` | Sensor name. |
| `unique_id` | Optional | Stable sensor identity; preserve existing values. |
| `require_all_sources` | `false` | Require every source to be valid. |
| `duration` | Unset | Averaging window as a time-period mapping, seconds, or a quoted duration string. |
| `start` / `end` | Unset | Templates returning datetimes or timestamps. |
| `scan_interval` | 20 seconds | Minimum interval between history refreshes. |
| `source_attributes` | Unset | Mapping of explicitly configured source entity IDs to attribute names. Unmapped sources keep their default reading. |
| `weights` | Unset | Mapping of explicitly configured source entity IDs to nonnegative relative weights. Omitted sources use weight 1. At least one source must have a positive weight. |
| `precision` | `2` | Decimal places for the result. |
| `max_source_age` | Unset | Exclude readings whose `last_updated` is older than this duration; strict mode becomes unavailable. |
| `process_undef_as` | Unset | Substitute a configured number for undefined values during calculation. Does not bypass strict availability. |
| `ignore_undef` | `false` | Allow a history average over valid recorded intervals when the latest recorded value is undefined. |
| `calculate_to_now_undef` | `false` | Carry the last valid reading across undefined intervals through the window end. Requires `ignore_undef: true`. |

### Time periods

Use one of these combinations:

- No period options: average current values.
- `duration` alone: a rolling window ending now.
- `start` and `end`: an explicit period.
- `start` and `duration`, or `end` and `duration`: calculate the remaining boundary.

A lone `start` or `end`, or all three period options together, is invalid.
Durations must be positive. In the UI, put these values under **Advanced**.
A missing, invalid, future or zero-length range makes a history sensor unavailable;
it does not substitute a current-value average. Source-dependent templates recover
on a later update when their boundary values become valid. Datetimes without a
timezone use Home Assistant's configured timezone.

```yaml
# Last 5 minutes
duration:
  minutes: 5
```

Or use a quoted duration string:

```yaml
# A fixed 2-hour, 30-minute window
duration: "02:30:00"
```

### Undefined history values

By default, undefined intervals are not assigned an invented numeric value. The
optional gap controls apply to history calculations:

- `ignore_undef: true` can retain an average over valid recorded intervals even when the latest recorded reading is undefined.
- Adding `calculate_to_now_undef: true` assumes the last valid reading continues through subsequent gaps. Enable this only when that assumption is appropriate for the source.

Neither option invents a reading before the first valid value. If no usable data
exists, the sensor remains unavailable. Neither option overrides **Require all
source sensors**.

## Sensor Attributes

| Attribute | Meaning |
| --- | --- |
| `sources` | Expanded source entity IDs. |
| `count_sources` | Number of configured sources. |
| `available_sources` | Sources contributing numeric values to the last calculation. Strict availability also checks current source states. |
| `count` | Numeric values processed, including history boundary values; not a number of days or elapsed seconds. |
| `start` / `end` | Boundaries of the calculated history period, when configured. |
| `min_value` / `max_value` | Lowest and highest processed values. |
| `min_datetime` / `max_datetime` | Times associated with those extrema for a history calculation. |
| `trending_towards` | Projection to the configured period end if sources keep their last readings. Useful when the end is in the future. |

## Limitations

- **History retention:** windows use raw recorder state history. Long-term statistics are not queried automatically. A monthly window needs the relevant raw history retained for that period.
- **Large windows:** frequently changing sources can produce large queries. A longer update interval reduces frequency, but does not remove the cost of processing a large history. Recorder results are decoded in the recorder executor, and history averaging yields periodically so other Home Assistant callbacks can run during long calculations. A cancelled refresh does not start replacement SQL work for that sensor until its existing query finishes. These measures do not impose a database-query time limit.
- **Temperature units:** unmapped weather, climate, and water-heater temperatures retain the existing assumption that values use Home Assistant's configured unit. Explicit temperature-attribute selections use reported units when available. Historical unit changes cannot always be reconstructed.
- **Compatible inputs:** use readings that represent the same quantity with compatible units. This integration does not perform arbitrary unit normalization for non-temperature values.
- **Consumption totals:** averaging an increasing meter reading gives its average level, not consumption per day. Use consumption differences or an appropriate utility meter for that quantity.
- **Other aggregations:** medians, trimmed averages, and automatic area/label selection are not currently implemented.

For a single current-value aggregate, Home Assistant also has built-in helpers.
History and Filter integrations can produce different results because their
weighting, retained data, and update timing differ.

## Troubleshooting

### The average is unavailable

Check the source states, units, and **Require every source** setting.
Inspect `sources` and `available_sources` to confirm which entities are involved.
If a maximum source age is configured, check each source's `last_updated` time.
Quiet-source expiry follows Home Assistant's normal polling cadence. Instantaneous
sensors without an age limit remain event-driven.

For history averages, confirm the sources are included in Recorder and that
history exists for the requested period. Allow the configured update interval
for a new calculation. For a closed historical period, incomplete results are
retried at that interval when sources or recorder history become available;
a complete recorded-history result is cached.

### A temperature unit is missing

Confirm the sources expose a temperature device class or temperature unit.
The fork can recognize temperature metadata that arrives after startup,
including metadata from another average or a statistics sensor.

### Enable debug logging

Use Home Assistant's integration debug logging when available, or add:

```yaml
logger:
  default: info
  logs:
    custom_components.average: debug
```

Report problems in [this fork's issue tracker](https://github.com/Wheemer/ha-average/issues).
Include your Home Assistant version, integration version, relevant configuration,
and the complete traceback. Remove credentials and private installation details.

