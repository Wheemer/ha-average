"""Keep the coordinated test stack installable and bot updates grouped."""

import re
from importlib.metadata import requires
from pathlib import Path

import yaml
from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[1]


def test_test_image_matches_core_and_fixture_requirements():
    """The fixture's exact Core requirement must accept the test image version."""
    core = Requirement((ROOT / "requirements.txt").read_text().splitlines()[0])
    fixture_core = next(
        Requirement(line)
        for line in requires("pytest-homeassistant") or []
        if Requirement(line).name == "homeassistant"
    )
    match = re.match(
        r"FROM ghcr.io/home-assistant/home-assistant:([^@]+)@sha256:[0-9a-f]{64}\n",
        (ROOT / "tests/Dockerfile").read_text(),
    )
    assert match is not None
    version = match.group(1)
    assert version in core.specifier
    assert version in fixture_core.specifier


def test_dependabot_coordinates_python_and_test_image():
    """Related changes must not become independent incompatible PRs."""
    config = yaml.safe_load((ROOT / ".github/dependabot.yml").read_text())
    group = config["multi-ecosystem-groups"]["test-stack"]
    assert group["schedule"]["interval"] == "weekly"
    updates = {entry["package-ecosystem"]: entry for entry in config["updates"]}
    for ecosystem in ("pip", "docker"):
        assert updates[ecosystem]["multi-ecosystem-group"] == "test-stack"
        assert updates[ecosystem]["patterns"] == ["*"]
    assert updates["github-actions"]["groups"]["github-actions"]["patterns"] == ["*"]
