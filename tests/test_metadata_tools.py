"""Metadata maintenance must never infer runtime support from CI packages."""

import json
import re
import runpy
import shutil
from pathlib import Path

import pytest


def metadata_copy(tmp_path):
    """Run the actual synchronizer only against a disposable metadata tree."""
    root = Path(__file__).parents[1]
    for filename in (
        "custom_components/average/const.py",
        "custom_components/average/manifest.json",
        "hacs.json",
        "requirements.txt",
        "requirements-runtime.txt",
    ):
        target = tmp_path / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / filename, target)
    synchronize = runpy.run_path(str(root / "scripts/metadata.py"))["synchronize"]
    synchronize.__globals__["ROOT"] = tmp_path
    return synchronize


def test_metadata_sync_retains_support_floor_and_manifest_version(tmp_path):
    """Test requirements cannot raise the HACS floor or downgrade a release."""
    synchronize = metadata_copy(tmp_path)
    hacs = (tmp_path / "hacs.json").read_bytes()
    manifest_path = tmp_path / "custom_components/average/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    const_path = tmp_path / "custom_components/average/const.py"
    const_path.write_text(
        re.sub(
            r"^VERSION: Final = .+$",
            'VERSION: Final = "0.0.0"',
            const_path.read_text(),
            flags=re.MULTILINE,
        )
    )
    (tmp_path / "requirements.txt").write_text("homeassistant>=2099.1.0\npip>=99\n")
    with pytest.raises(ValueError, match="Metadata drift"):
        synchronize(check=True)
    synchronize()
    assert (tmp_path / "hacs.json").read_bytes() == hacs
    assert json.loads(manifest_path.read_text())["version"] == manifest["version"]
    assert json.loads(manifest_path.read_text())["requirements"] == []
    assert (
        f"VERSION: Final = {json.dumps(manifest['version'])}" in const_path.read_text()
    )
    assert "https://github.com/Wheemer/ha-average/issues" in const_path.read_text()
    synchronize(check=True)


def test_release_metadata_preparation_uses_manifest_as_source_of_truth(tmp_path):
    """Preparing a version changes metadata only, without git or publication."""
    synchronize = metadata_copy(tmp_path)
    synchronize(version="2.5.1")
    assert (
        json.loads((tmp_path / "custom_components/average/manifest.json").read_text())[
            "version"
        ]
        == "2.5.1"
    )
    assert (
        'VERSION: Final = "2.5.1"'
        in (tmp_path / "custom_components/average/const.py").read_text()
    )
    synchronize(check=True)
