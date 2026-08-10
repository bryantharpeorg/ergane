"""US4 `ergane env` and `ergane completion` surface tests.

`env` enumerates every environment variable the CLI reads, reporting set/unset
and the resolution source, and must never print a credential value.
`completion bash|zsh` emits a non-empty static completion script; any other
shell exits 2 naming the two supported shells.

Written before `factory/cli/env.py` and `factory/cli/completion.py` exist (T026
precedes T029): until they land, both nouns are unknown.
"""

from __future__ import annotations

import io
import sys
from typing import Callable, NamedTuple

import pytest

from factory.cli import main as main_module


class Run(NamedTuple):
    code: int
    stdout: str
    stderr: str


def _invoke(argv: list[str]) -> Run:
    old_stdout, old_stderr = sys.stdout, sys.stderr
    buf_out, buf_err = io.StringIO(), io.StringIO()
    try:
        sys.stdout, sys.stderr = buf_out, buf_err
        try:
            code = main_module.main(argv)
        except SystemExit as exit_request:
            code = 0 if exit_request.code is None else int(exit_request.code)
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr
    return Run(code, buf_out.getvalue(), buf_err.getvalue())


@pytest.fixture
def invoke(monkeypatch: pytest.MonkeyPatch) -> Callable[..., Run]:
    def _caller(*argv: str, env: dict[str, str] | None = None) -> Run:
        saved: dict[str, str | None] = {}
        if env:
            saved = {k: os.environ.get(k) for k in env}
            for k, v in env.items():
                monkeypatch.setenv(k, v)
        try:
            return _invoke(list(argv))
        finally:
            for k, v in saved.items():
                if v is None:
                    monkeypatch.delenv(k, raising=False)
                else:
                    monkeypatch.setenv(k, v)

    return _caller


# --- env ----------------------------------------------------------------------


def test_env_lists_every_variable_and_source(
    invoke: Callable[..., Run],
) -> None:
    result = invoke("env")
    assert result.code == 0
    for name in (
        "TEMPORAL_ADDRESS",
        "TEMPORAL_NAMESPACE",
        "LITELLM_PROXY_URL",
        "LITELLM_MASTER_KEY",
        "TELEGRAM_BOT_TOKEN",
        "FACTORY_LEDGER_PATH",
        "FACTORY_VERIFICATION_DB_PATH",
    ):
        assert name in result.stdout


def test_env_never_prints_credential_values(
    invoke: Callable[..., Run],
) -> None:
    result = invoke(
        "env",
        env={
            "LITELLM_MASTER_KEY": "sk-do-not-print-me",
            "TELEGRAM_BOT_TOKEN": "123456:also-secret",
        },
    )
    assert result.code == 0
    assert "sk-do-not-print-me" not in result.stdout
    assert "123456:also-secret" not in result.stdout
    assert "LITELLM_MASTER_KEY" in result.stdout
    assert "TELEGRAM_BOT_TOKEN" in result.stdout


# --- completion ---------------------------------------------------------------


@pytest.mark.parametrize("shell", ["bash", "zsh"])
def test_completion_emits_a_script_for_supported_shells(
    invoke: Callable[..., Run], shell: str
) -> None:
    result = invoke("completion", shell)
    assert result.code == 0
    assert result.stdout != ""
    assert "complete" in result.stdout or "compdef" in result.stdout


def test_completion_bash_includes_nouns_and_verbs(invoke: Callable[..., Run]) -> None:
    result = invoke("completion", "bash")
    assert result.code == 0
    for noun in ("doctor", "findings", "usage", "repo", "roadmap", "env", "completion"):
        assert noun in result.stdout
    for verb in ("start", "pause", "resume", "promote", "status"):
        assert verb in result.stdout
    for verb in ("list", "report", "resolve", "promote"):
        assert verb in result.stdout
    assert "onboard" in result.stdout
    assert "bash" in result.stdout
    assert "zsh" in result.stdout


def test_completion_bash_completes_verbs_when_sourced(invoke: Callable[..., Run]) -> None:
    import subprocess

    result = invoke("completion", "bash")
    assert result.code == 0
    script = result.stdout
    driver = """
_init_completion() {
    cur="start"
    prev="roadmap"
    words=(ergane roadmap start)
    cword=2
    return 0
}
""" + script + """
_ergane_completion
printf '%s\n' "${COMPREPLY[@]}"
"""
    proc = subprocess.run(["bash", "-c", driver], capture_output=True, text=True)
    assert proc.returncode == 0
    assert "start" in proc.stdout.splitlines()


def test_completion_unsupported_shell_exits_two_naming_supported(
    invoke: Callable[..., Run],
) -> None:
    result = invoke("completion", "fish")
    assert result.code == 2
    message = result.stdout + result.stderr
    assert "bash" in message.lower()
    assert "zsh" in message.lower()


# Import at module bottom to avoid circular imports with fixtures.
import os  # noqa: E402
