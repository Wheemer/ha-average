# Why?

While tests aren't required to publish a custom component for Home Assistant, they will generally make development easier because good tests will expose when changes you want to make to the component logic will break expected functionality. Home Assistant uses [`pytest`](https://docs.pytest.org/en/latest/) for its tests, and the tests that have been included are modeled after tests that are written for core Home Assistant integrations. Coverage must be measured for the revision being tested; a passing test suite is not proof of live lifecycle behavior.

# Getting Started

To begin, it is recommended to create a virtual environment and install all necessary dependencies:
```bash
./scripts/setup
```

# Useful commands

Command | Description
------- | -----------
`pytest` | This will run all tests and tell you how many passed/failed. It also show you a [code coverage](https://en.wikipedia.org/wiki/Code_coverage) summary of component, including % of code that was executed and the line numbers of missed executions.
`pytest tests/test_init.py -k test_setup_unload_and_reload_entry` | Runs the `test_setup_unload_and_reload_entry` test function located in `tests/test_init.py`


## Current native checks

The test dependencies use Core-maintained `pytest-homeassistant==2026.11.0`
(Python 3.14). Run `python -m pytest` for the full suite. The standalone lifecycle
harnesses also run in an unmodified Home Assistant Core 2026.11.1 image:

```sh
docker run --rm --network none -v "$PWD:/work:ro" -w /work \
  --entrypoint python ghcr.io/home-assistant/home-assistant:2026.11.1 \
  -m unittest tests.test_shutdown_native tests.test_shutdown_recorder_native \
  tests.test_flow_sections tests.test_require_all
```

The tests use temporary databases and synthetic sources. They do not connect to
or control a live Home Assistant installation. No private installation evidence
or credentials are needed. Keep generated `tests/testing_config/` out of commits.


## GitHub Actions test environment

CI builds `tests/Dockerfile`, installs the declared development/test dependencies,
and runs Ruff and the complete suite with networking disabled. The image keeps
its exact Home Assistant version after installing Core-maintained fixtures,
which can pin a different patch release. The current base is Core 2026.11.1;
`requirements-ci.txt` supplies the matching fixture series and lint version.

```sh
docker build -f tests/Dockerfile -t average-ci .
docker run --rm --network none -v "$PWD:/work" average-ci -m pytest -q
```

GitHub Actions, container-image and Python dependency updates are proposed by
Dependabot. CI requires no administrator token or private Home Assistant access.
HACS validates the fork's metadata, topics, issues and packaging. Its license
identification check has an explicit exception because GitHub reports the
inherited CC-BY-NC-SA-4.0 text as `NOASSERTION`, including in the upstream
repository. `LICENSE.md` and its attribution/terms are unchanged.
