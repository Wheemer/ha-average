#!/usr/bin/env python3
"""Check real Core types for both editable native images and pip installs."""

import os
import site
import subprocess
import sys
from pathlib import Path

import homeassistant

root = Path(__file__).resolve().parents[1]
core_root = Path(next(iter(homeassistant.__path__))).resolve().parent
environment = dict(os.environ)
site_roots = {Path(path).resolve() for path in site.getsitepackages()}
user_site = site.getusersitepackages()
if isinstance(user_site, str):
    site_roots.add(Path(user_site).resolve())
if core_root not in site_roots:
    # Mypy cannot follow editable-install import hooks. Supply Core's actual
    # source directory, never site-packages, instead of treating its APIs as Any.
    paths = [str(core_root)]
    if environment.get("MYPYPATH"):
        paths.append(environment["MYPYPATH"])
    environment["MYPYPATH"] = os.pathsep.join(paths)
# Fixed interpreter/arguments; no shell and no user-provided command text.
result = subprocess.run(
    [sys.executable, "-m", "mypy", "--no-incremental", "custom_components/average"],
    cwd=root,
    env=environment,
    check=False,
)
raise SystemExit(result.returncode)
