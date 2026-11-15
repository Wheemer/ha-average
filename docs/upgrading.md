# Switching from Limych/ha-average

[Back to README](../README.md)

This fork replaces the original integration in `custom_components/average/`.
The domain stays `average`. Keep existing `platform: average` YAML, sensor names,
explicit unique IDs and entity IDs unchanged. Do not add a second copy under a
different folder and do not recreate your sensors.

## Original integration configured only in YAML

The original release, 2.4.0, creates its sensors from YAML without creating
Average Sensor UI configuration entries. For that installation, the normal
repository uninstall/install sequence releases the old repository's ownership
without deleting sensor configuration.

1. Make a Home Assistant backup and retain your existing Average Sensor YAML.
2. Open the **Limych/ha-average** repository in HACS or **Settings > Marketplace**.
3. Select its three-dot menu and **Uninstall**. This removes downloaded integration
   files. **Do not restart yet.** Do not delete anything under Devices & services.
   If you see **integration is in use** or **Delete and uninstall**, cancel and read
   the next section; that is not the YAML-only case covered here.
4. Add `https://github.com/Wheemer/ha-average` as a custom **Integration** repository
   (HACS: **Custom repositories**; Marketplace: **Add from link**).
5. Install this fork's latest stable release. Confirm **Wheemer/ha-average** is
   shown as installed. Install it before accepting any pending restart reminder.
6. Restart Home Assistant once, after the replacement files are present.
7. Verify that your existing entities retain their IDs, settings, units and
   recorder history. The fork imports your YAML definitions into UI entries; it
   does not edit the YAML files.

You can keep the YAML active and continue configuring those sensors there.
To manage them in the UI instead, verify the import first, then comment out only
those Average Sensor YAML definitions and dismiss the import notice. Do not
create replacement sensors with **Add integration** for definitions already imported.

No change from `platform: average` is needed. Once the fork is installed through
the store, its future releases are offered through that repository's update entity.

## Marketplace says the integration is in use

Marketplace refuses repository uninstall when `average` already has UI
configuration entries, including imported or disabled entries. This differs from
an original YAML-only installation. Its **Delete and uninstall** action removes
those entries and their entities; do not use it to switch this fork.

This repository-switching limitation is tracked in
[Home Assistant Core issue #190454](https://github.com/home-assistant/core/issues/190454).
There is no `hacs.json` replacement flag that bypasses it. Adding the fork or
copying its ZIP over the old files does not, by itself, transfer update tracking.

If you hit that restriction, keep the entries and configuration intact and
[open an issue here](https://github.com/Wheemer/ha-average/issues) with your Home
Assistant version, the exact message and which repositories show as installed.
Do not edit Marketplace's internal storage while it is running. The workaround
reported in the Core issue is a separate maintenance operation, not a required
step for the original YAML-only installation above.

## Validation

The YAML-only sequence was exercised in an isolated Home Assistant 2026.11.1
instance with the original upstream 2.4.0 integration and the published fork
v2.5.0 ZIP. It used the actual Marketplace repository uninstall/install handlers
and filesystem lifecycle; GitHub metadata and release transport were supplied
from cached fixtures. The three cases were an explicit unique ID, no unique ID,
and the historical `__legacy__` setting. The checks cover unchanged YAML, existing
entity IDs and registered unique IDs, no duplicate sensors, UI import and retained
SQLite recorder rows across the restart. This does not claim an automatic
repository transfer for installations that already have UI entries.

## References

- [Marketplace: uninstalling a repository](https://www.home-assistant.io/integrations/marketplace/#uninstalling-a-repository)
- [Marketplace: custom repositories](https://www.home-assistant.io/integrations/marketplace/#custom-repositories)
- [HACS: integrations](https://www.hacs.xyz/docs/use/repositories/type/integration/)
