"""Developer credentials must never be interpolated into subprocess arguments."""

import os
import runpy
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).parents[1]
FAKE_TOKEN = "TEST_ONLY_NOT_A_REAL_GITHUB_TOKEN"


@pytest.fixture(autouse=True)
def clean_auth_environment(monkeypatch):
    """Use only explicitly supplied synthetic credentials."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN_FILE", raising=False)
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))


@pytest.mark.parametrize("from_file", [False, True])
def test_installer_keeps_credentials_out_of_pip_arguments(
    tmp_path, monkeypatch, from_file
):
    """Private Git installs use plain URLs and Git askpass environment wiring."""
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("git+https://github.com/example/private.git@main\n")
    if from_file:
        token_file = tmp_path / "token"
        token_file.write_text(FAKE_TOKEN + "\n")
        monkeypatch.setenv("GITHUB_TOKEN_FILE", str(token_file))
    else:
        monkeypatch.setenv("GITHUB_TOKEN", FAKE_TOKEN)
    namespace = runpy.run_path(str(ROOT / "scripts/install_requirements.py"))
    calls = []

    def pip(command, **kwargs: object) -> SimpleNamespace:
        calls.append((command, kwargs))
        assert FAKE_TOKEN not in repr(command)
        assert FAKE_TOKEN not in Path(command[-1]).read_text()
        return SimpleNamespace(returncode=0)

    namespace["main"].__globals__["subprocess"] = SimpleNamespace(run=pip)
    assert namespace["main"]([str(requirements), "--pre"]) == 0
    command, kwargs = calls[0]
    assert "--pre" in command
    assert command[-2] == "-r"
    assert kwargs["env"]["GIT_ASKPASS"] == str(ROOT / "scripts/git_askpass.py")
    assert kwargs["env"]["GIT_TERMINAL_PROMPT"] == "0"


def test_nested_token_url_is_rejected_without_echoing_it(tmp_path, capsys):
    """Nested includes cannot bypass the ban on token-bearing URLs."""
    (tmp_path / "requirements.txt").write_text(
        "-r nested.txt # included dependencies\n"
    )
    (tmp_path / "nested.txt").write_text(
        f"git+https://{FAKE_TOKEN}@github.com/example/private.git\n"
    )
    namespace = runpy.run_path(str(ROOT / "scripts/install_requirements.py"))
    with pytest.raises(SystemExit) as error:
        namespace["main"]([str(tmp_path / "requirements.txt")])
    assert error.value.code == 2
    captured = capsys.readouterr()
    assert FAKE_TOKEN not in captured.out + captured.err


def test_legacy_positional_token_is_rejected_without_echo(tmp_path, capsys):
    """Unsafe old CLI forms fail with guidance, without copying secrets to logs."""
    namespace = runpy.run_path(str(ROOT / "scripts/install_requirements.py"))
    with pytest.raises(SystemExit):
        namespace["main"]([str(tmp_path / "requirements.txt"), FAKE_TOKEN])
    captured = capsys.readouterr()
    assert FAKE_TOKEN not in captured.out + captured.err


def test_git_only_bootstrap_does_not_install_public_core_packages(tmp_path):
    """Bootstrap retains its Git-only scope instead of upgrading Home Assistant."""
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("homeassistant>=2026.11.1\npip>=26.3\n")
    namespace = runpy.run_path(str(ROOT / "scripts/install_requirements.py"))
    pip = Mock()
    namespace["main"].__globals__["subprocess"] = SimpleNamespace(run=pip)
    assert namespace["main"]([str(requirements), "--git-only"]) == 0
    pip.assert_not_called()


@pytest.mark.parametrize(
    "prompt",
    [
        "Password for 'https://github.com.evil.test': ",
        "Password for 'https://evil.test/?next=https://github.com': ",
        "Password for 'http://github.com': ",
        "Password for 'https://github.com:444': ",
    ],
)
def test_askpass_refuses_other_hosts_and_lookalikes(prompt):
    """A requirements URL cannot send the GitHub token to another host."""
    result = subprocess.run(  # noqa: S603 - fixed script and synthetic test arguments
        [sys.executable, str(ROOT / "scripts/git_askpass.py"), prompt],
        env={**os.environ, "GITHUB_TOKEN": FAKE_TOKEN},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert not result.stdout
    assert FAKE_TOKEN not in result.stderr


def test_askpass_reads_private_file_and_only_answers_github(tmp_path):
    """Only the askpass pipe receives the secret, never the command arguments."""
    token_file = tmp_path / "token"
    token_file.write_text(FAKE_TOKEN + "\n")
    command = [
        sys.executable,
        str(ROOT / "scripts/git_askpass.py"),
        "Password for 'https://x-access-token@github.com': ",
    ]
    assert FAKE_TOKEN not in repr(command)
    result = subprocess.run(  # noqa: S603 - fixed script and synthetic test arguments
        command,
        env={**os.environ, "GITHUB_TOKEN_FILE": str(token_file)},
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout == FAKE_TOKEN + "\n"
    assert not result.stderr


def test_release_notes_uses_environment_auth_and_rejects_token_flag(
    monkeypatch, capsys
):
    """Release-note testing never calls GitHub or edits an actual release."""
    namespace = runpy.run_path(str(ROOT / "scripts/gen_releasenotes"))
    main = namespace["main"]
    factory = Mock()
    main.__globals__["Github"] = factory
    main.__globals__["_default_repo"] = lambda: "Wheemer/ha-average"
    main.__globals__["gen_changes"] = lambda _repo: (namespace["NOCHANGE"],) * 3
    monkeypatch.setenv("GITHUB_TOKEN", FAKE_TOKEN)
    main(["--repo", "Wheemer/ha-average", "--dry-run"])
    assert factory.call_args.kwargs["auth"].token == FAKE_TOKEN
    assert FAKE_TOKEN not in capsys.readouterr().out
    with pytest.raises(SystemExit):
        main(["--token", FAKE_TOKEN])
    captured = capsys.readouterr()
    assert FAKE_TOKEN not in captured.out + captured.err
