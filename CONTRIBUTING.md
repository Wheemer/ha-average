# Contributing

Report bugs through [this fork's issue tracker](https://github.com/Wheemer/ha-average/issues/new/choose).
Include the integration and Home Assistant versions, reproduction steps and
relevant configuration or logs with private details removed. Report suspected
security vulnerabilities privately as described in [SECURITY.md](SECURITY.md).

## Development

Clone the repository and branch from `dev`; generated source archives omit the
test suite and development dotfiles. Use a Python 3.14 virtual environment and install
`python -m pip install -r requirements-dev.txt`. Install hooks with
`pre-commit install`.

Before submitting a pull request, run:

```sh
python scripts/metadata.py --check
python -m mypy custom_components/average
python -m ruff check .
python -m ruff format . --check
python -m bandit -r custom_components -c tests/bandit.yaml
python -m pytest -n 2 --dist=loadfile -q
```

The native minimum-version checks run with `python scripts/check_minimum.py`
and require Docker. Tests use temporary instances and synthetic data; do not
connect them to a live Home Assistant installation. Preserve YAML compatibility,
UI configuration, entity IDs and unique IDs when fixing existing behavior.

## Metadata and releases

`custom_components/average/manifest.json` is authoritative for the integration
version and issue tracker. `requirements-runtime.txt` lists genuine runtime
dependencies; developer/test packages do not belong in the integration manifest.
Run `scripts/update_manifest` after changing either file. The hook validates
metadata without changing the Home Assistant minimum in `hacs.json`.

`scripts/release VERSION` prepares version metadata for review only. Submit and
merge the change through a pull request after checks pass. Publishing requires a
separately authorized `vVERSION` tag; the release workflow builds `average.zip`
and its checksum. Release notes should describe changes and credit contributors.

## License

This project and contributions are covered by the existing
[Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International license](LICENSE.md).
Keep original attribution and license notices. This fork does not claim an MIT
license or permission to relicense the inherited work.
