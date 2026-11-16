#!/usr/bin/env python3
"""Synchronize generated metadata without deriving runtime policy from tests."""

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def synchronize(*, check: bool = False, version: str | None = None) -> None:
    """Use manifest metadata and explicit runtime requirements as authoritative."""
    manifest_path = ROOT / "custom_components/average/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if version is not None:
        if re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?", version) is None:
            message = "Use a semantic release version such as 2.5.1"
            raise ValueError(message)
        manifest["version"] = version
    manifest["requirements"] = [
        line.strip()
        for line in (ROOT / "requirements-runtime.txt").read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    outputs = {manifest_path: json.dumps(manifest, indent=4) + "\n"}
    const_path = ROOT / "custom_components/average/const.py"
    constants = const_path.read_text()
    for constant, key in (
        ("NAME", "name"),
        ("DOMAIN", "domain"),
        ("VERSION", "version"),
        ("ISSUE_URL", "issue_tracker"),
    ):
        constants, count = re.subn(
            rf"^{constant}: Final = .+$",
            f"{constant}: Final = {json.dumps(manifest[key])}",
            constants,
            flags=re.MULTILINE,
        )
        if count != 1:
            message = f"Expected exactly one generated {constant} constant"
            raise ValueError(message)
    outputs[const_path] = constants
    for path, expected in outputs.items():
        if path.read_text() != expected:
            if check:
                message = (
                    f"Metadata drift in {path.relative_to(ROOT)}; "
                    "run scripts/update_manifest"
                )
                raise ValueError(message)
            path.write_text(expected)
    # hacs.json is independently maintained support policy, never generated from
    # requirements.txt: that file describes the development/test environment.


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--version")
    arguments = parser.parse_args()
    synchronize(check=arguments.check, version=arguments.version)
