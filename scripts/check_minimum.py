#!/usr/bin/env python3
"""Run native compatibility harnesses on the advertised minimum Core image."""

import json
import re
import subprocess
from pathlib import Path
from shutil import which

root = Path(__file__).resolve().parents[1]
version = json.loads((root / "hacs.json").read_text())["homeassistant"]
if re.fullmatch(r"[0-9]{4}\.[0-9]{1,2}\.[0-9]+", version) is None:
    message = "hacs.json must declare a stable Home Assistant minimum version"
    raise ValueError(message)
docker = which("docker")
if docker is None:
    message = "Docker is required for the isolated minimum-version check"
    raise RuntimeError(message)
# The version is validated above and arguments never pass through a shell.
subprocess.run(  # noqa: S603
    [
        docker,
        "run",
        "--rm",
        "--network",
        "none",
        "--volume",
        f"{root}:/work:ro",
        "--workdir",
        "/work",
        "--entrypoint",
        "python",
        f"ghcr.io/home-assistant/home-assistant:{version}",
        "-B",
        "-m",
        "unittest",
        "tests.test_shutdown_native",
        "tests.test_shutdown_recorder_native",
        "tests.test_flow_sections",
        "tests.test_require_all",
    ],
    check=True,
)
