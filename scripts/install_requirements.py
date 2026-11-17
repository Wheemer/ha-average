#!/usr/bin/env python3
"""Install developer requirements with credential-free pip and git arguments."""

import os
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

from dev_auth import SafeArgumentParser

ROOT = Path(__file__).resolve().parents[1]


def inspect_requirements(path: Path, seen: set[Path] | None = None) -> list[str]:
    """Reject credential-bearing URLs and recursively inspect local includes."""
    seen = set() if seen is None else seen
    path = path.resolve()
    if path in seen:
        return []
    seen.add(path)
    lines = path.read_text().splitlines()
    git_lines = []
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if "{GITHUB_TOKEN}" in line or re.search(
            r"\$\{[^}]+\}|https?://[^/\s]+@", line
        ):
            message = (
                "Use credential-free repository URLs and GITHUB_TOKEN_FILE or "
                "GITHUB_TOKEN; embedded credentials are not supported"
            )
            raise ValueError(message)
        fields = shlex.split(line, comments=True)
        if not fields:
            continue
        include = None
        if fields[0] in ("-r", "--requirement", "-c", "--constraint"):
            if len(fields) == 1:
                message = "Invalid requirements include"
                raise ValueError(message)
            include = fields[1]
        elif fields[0].startswith(("--requirement=", "--constraint=")):
            include = fields[0].split("=", 1)[1]
        elif fields[0].startswith(("-r", "-c")):
            include = fields[0][2:]
        if include:
            if "://" in include:
                message = "Requirement includes must be local files"
                raise ValueError(message)
            git_lines.extend(inspect_requirements(path.parent / include, seen))
        elif "git+" in line:
            git_lines.append(line)
    return git_lines


def main(argv: list[str] | None = None) -> int:
    """Keep pip's native requirements handling, without injecting token URLs."""
    parser = SafeArgumentParser(description=__doc__)
    parser.add_argument("requirements", nargs="?", default="requirements.txt")
    parser.add_argument("--pre", action="store_true")
    parser.add_argument(
        "--git-only",
        action="store_true",
        help="Bootstrap only explicitly declared Git dependencies",
    )
    args = parser.parse_args(argv)
    requirements = Path(args.requirements).resolve()
    try:
        git_lines = inspect_requirements(requirements)
    except OSError, ValueError:
        parser.exit(
            2, "Unable to use requirements: use local files and credential-free URLs.\n"
        )
    environment = dict(os.environ)
    environment.update(
        GIT_ASKPASS=str(ROOT / "scripts/git_askpass.py"),
        GIT_TERMINAL_PROMPT="0",
        LC_ALL="C",
    )
    command = [sys.executable, "-m", "pip", "install", "--upgrade"]
    if args.pre:
        command.append("--pre")
    with tempfile.TemporaryDirectory(prefix="average-requirements-") as temporary:
        if args.git_only:
            if not git_lines:
                return 0
            requirements = Path(temporary) / "requirements.txt"
            requirements.write_text("\n".join(git_lines) + "\n")
            requirements.chmod(0o600)
        command.extend(["-r", str(requirements)])
        # Fixed executable/flags and a file path; never shell-expanded credentials.
        result = subprocess.run(command, env=environment, check=False)  # noqa: S603
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
