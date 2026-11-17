#!/usr/bin/env python3
"""Supply GitHub HTTPS credentials through Git's askpass pipe, never argv."""

import re
import sys
from urllib.parse import urlsplit

from dev_auth import github_token


def main() -> int:
    """Answer only GitHub HTTPS prompts, without forwarding secrets elsewhere."""
    prompt = sys.argv[1] if len(sys.argv) > 1 else ""
    match = re.fullmatch(
        r"(Username|Password) for '([^']+)':\s*", prompt, re.IGNORECASE
    )
    if match is None:
        return 1
    try:
        url = urlsplit(match[2])
        valid = (
            url.scheme == "https"
            and url.hostname == "github.com"
            and url.port in (None, 443)
            and not url.query
            and not url.fragment
            and url.password is None
        )
    except ValueError:
        return 1
    if not valid:
        return 1
    if match[1].lower() == "username":
        sys.stdout.write("x-access-token\n")
        return 0
    try:
        token = github_token()
    except ValueError:
        return 1
    # Git consumes stdout through its askpass pipe; this is not a log message.
    if token:
        sys.stdout.write(token + "\n")
    return 0 if token else 1


if __name__ == "__main__":
    raise SystemExit(main())
