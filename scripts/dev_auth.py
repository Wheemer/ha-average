"""Credential loading without secret command-line arguments or logging."""

import argparse
import os
from pathlib import Path


class SafeArgumentParser(argparse.ArgumentParser):
    """Reject obsolete credential arguments without echoing their values."""

    def error(self, message: str) -> None:  # noqa: ARG002 - never echo unsafe arguments
        """Keep unexpected argument values out of stderr and CI logs."""
        self.exit(
            2,
            f"{self.prog}: invalid arguments; use --help. "
            "Credentials belong in GITHUB_TOKEN or GITHUB_TOKEN_FILE.\n",
        )


def github_token() -> str | None:
    """Read an explicitly supplied credential, preferring a private token file."""
    if filename := os.environ.get("GITHUB_TOKEN_FILE"):
        try:
            token = Path(filename).read_text().strip()
        except OSError, UnicodeError:
            message = "Unable to read GITHUB_TOKEN_FILE"
            raise ValueError(message) from None
    else:
        token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        return None
    if (
        not token.isascii()
        or not token.isprintable()
        or any(char.isspace() for char in token)
    ):
        message = "GitHub credentials must contain exactly one token"
        raise ValueError(message)
    return token or None
