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
python scripts/typecheck.py
python -m ruff check .
python -m ruff format . --check
python -m bandit -r custom_components -c tests/bandit.yaml
python -m pytest -n 2 --dist=loadfile -q
```

The native minimum-version checks run with `python scripts/check_minimum.py`
and require Docker. Tests use temporary instances and synthetic data; do not
connect them to a live Home Assistant installation. Preserve YAML compatibility,
UI configuration, entity IDs and unique IDs when fixing existing behavior.

Update the Home Assistant requirement, the matching `pytest-homeassistant`
fixture pin, and the digest-pinned test image together. The fixture package pins
an exact Core version, so independently updating those requirements can make
the test environment impossible to install. Dependabot groups Python and test
image updates into one weekly `test-stack` PR; GitHub Actions updates remain a
separate weekly group. Both fixture and newer-plugin checks must pass before
merging. Dependency maintenance does not authorize a live installation or release.

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


## Developer credentials

The integration needs no GitHub credential. Optional developer helpers accept
`GITHUB_TOKEN_FILE` (preferred, pointing to a private single-token file) or
`GITHUB_TOKEN` supplied by your credential manager/CI. They do not read Home
Assistant `secrets.yaml`, accept positional tokens, or support `--token`.

```sh
GITHUB_TOKEN_FILE=/secure/path/github-token scripts/install_requirements requirements-dev.txt
GITHUB_TOKEN_FILE=/secure/path/github-token scripts/gen_releasenotes --repo Wheemer/ha-average --dry-run
```

Use credential-free Git URLs such as
`git+https://github.com/owner/private-repository.git@ref`. Git receives GitHub
HTTPS credentials through its askpass pipe; tokens are never substituted into
pip/git arguments. Legacy `{GITHUB_TOKEN}` URLs and credential-bearing URLs are
rejected with a generic message. Keep token files outside the repository with
owner-only permissions. The bootstrap helper installs Git dependencies only.
