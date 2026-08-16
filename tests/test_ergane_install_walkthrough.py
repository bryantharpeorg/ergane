"""Tests for the `ergane install` walkthrough (US3 of 033-ergane-install).

The walkthrough interviews the operator subsystem by subsystem, writes the
control-plane config, and ends by running US2's verification.  Every test drives
it through the CLI with the scripted prompter seam 034/us1 landed
(`factory.cli.init._prompter_factory`) — never a monkeypatched `input()`.

**What each test has to be unable to pass without the production code**, because
the defect that has cost this repository most is a fixture that makes a test
unable to fail:

- the blank-host test points every subsystem at a *distinct closed port* typed
  at the prompt, so the findings printed at the end can only carry those
  addresses if the file just written was really loaded and really probed;
- the re-run test seeds the existing file with values no built-in default could
  produce, and asserts the prompter was *offered* them as defaults;
- the refuse-at-entry tests record whether the config file exists at each
  question, so "refuse at entry, never write-then-fail" is asserted rather than
  assumed;
- the lock tests hold the lock from a **separate OS process**, so a walkthrough
  that took no lock would sail past them.

Evidence rule (constitution VIII): runtime claims are pasted verbatim below.

Red before green — the tests in this file against the tree before
`factory/cli/install.py`, `factory/locking.py` and the renderer existed:

.. code-block:: text

    $ uv run pytest tests/test_ergane_install_walkthrough.py -q
    ImportError while importing test module '/…/tests/test_ergane_install_walkthrough.py'.
    Hint: make sure your test modules/packages have valid Python names.
    Traceback:
    /usr/lib/python3.11/importlib/__init__.py:126: in import_module
        return _bootstrap._gcd_import(name[level:], package, level)
    tests/test_ergane_install_walkthrough.py:60: in <module>
        from factory.controlplane.config import (
    E   ImportError: cannot import name 'render_controlplane_config' from
        'factory.controlplane.config' (/…/factory/controlplane/config.py)
    =========================== short test summary info ============================
    ERROR tests/test_ergane_install_walkthrough.py
    1 error in 0.72s

After the renderer, the lock and the walkthrough landed:

.. code-block:: text

    $ uv run pytest tests/test_ergane_install_walkthrough.py -q
    ...........                                                              [100%]
    11 passed in 6.05s

The two lock tests are the ones worth reading a transcript of, because a lock
that is never contended is a lock nobody has tested.  Printed by
`test_a_second_install_is_refused_while_another_holds_the_lock` and
`test_a_second_install_waits_for_the_lock_and_then_writes`:

.. code-block:: text

    child pid 3453401 holds /tmp/…/config.toml.lock
    ergane: another `ergane install` holds the lock on /tmp/…/config.toml
      (waited 0.5s); wait for it to finish or remove the lock file
    refused after 0.51s, exit 1, config written: False

    child pid 3453412 holds /tmp/…/config.toml.lock for 1.0s
    walkthrough returned after 1.06s, exit 1, config written: True

The full suite, after the story:

.. code-block:: text

    $ uv run pytest -q
    2459 passed, 44 skipped, 4 warnings in 273.04s (0:04:33)

SC-002 (no credential in the config file or the logs), printed by
`test_walkthrough_and_verify_never_write_a_credential`:

.. code-block:: text

    credentials in play this session:
      ERGANE_LLM_MASTER_KEY       = 'sk-secret-llm-value-do-not-log'
      ERGANE_HINDSIGHT_KEY        = 'hs-secret-memory-value-do-not-log'
      ERGANE_TELEGRAM_BOT_TOKEN   = '123456:SECRET-bot-token-do-not-log'
    the LLM probe sent its credential over the wire: True
    the escalation probe used its credential: True
    occurrences in /tmp/…/config.toml : 0
    occurrences in captured stdout+stderr: 0
    env-var NAMES present in the config file: True
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator

import pytest

import factory.cli.init as init_module
import factory.cli.main as main_module
import factory.controlplane.verify as verify_module
from factory.cli.errors import EXIT_USER
from factory.controlplane.config import (
    ControlPlaneConfigError,
    load_controlplane_config,
    parse_controlplane_config,
    render_controlplane_config,
)
from factory.locking import LockUnavailable, exclusive_lock, lock_path_for

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


@dataclass
class Run:
    """One captured CLI invocation."""

    code: int
    stdout: str
    stderr: str


def _invoke(argv: list[str]) -> Run:
    """Run `main(argv)` capturing stdout/stderr, as the operator would see them."""
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


@dataclass
class Asked:
    """One question the walkthrough put to the operator."""

    prompt: str
    default: str | None
    error: str | None
    #: Did the config file exist at the moment this question was asked?  This is
    #: what makes "refuse at entry, never write-then-fail" assertable.
    config_existed: bool


class ScriptedPrompter:
    """Answers questions from a list, recording each question it was asked.

    Deliberately strict: running out of answers is an error, not a silent empty
    string, so a walkthrough that grew a question fails loudly instead of
    accepting a default nobody chose.
    """

    def __init__(self, answers: list[str], *, watch: Path | None = None) -> None:
        self.answers = list(answers)
        self.asked: list[Asked] = []
        self.watch = watch

    def ask(
        self, prompt: str, *, default: str | None = None, error: str | None = None
    ) -> str:
        self.asked.append(
            Asked(
                prompt=prompt,
                default=default,
                error=error,
                config_existed=self.watch.exists() if self.watch else False,
            )
        )
        if not self.answers:
            raise AssertionError(
                f"prompter ran out of answers at {prompt!r}; "
                f"asked so far: {[a.prompt for a in self.asked]}"
            )
        return self.answers.pop(0)

    @property
    def prompts(self) -> list[str]:
        return [asked.prompt for asked in self.asked]

    def defaults_for(self, prompt: str) -> list[str | None]:
        return [asked.default for asked in self.asked if asked.prompt == prompt]

    def errors_for(self, prompt: str) -> list[str]:
        return [
            asked.error
            for asked in self.asked
            if asked.prompt == prompt and asked.error is not None
        ]


@pytest.fixture
def config_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The control-plane config path for this test, isolated from the host."""
    path = tmp_path / "ergane" / "config.toml"
    monkeypatch.setenv("ERGANE_CONFIG_PATH", str(path))
    monkeypatch.setenv("FACTORY_CONFIG_PATH", str(path))
    return path


@pytest.fixture
def walkthrough(
    monkeypatch: pytest.MonkeyPatch, config_path: Path
) -> Callable[..., tuple[Run, ScriptedPrompter]]:
    """Run `ergane install` with a scripted prompter, returning the run and prompter."""

    def runner(answers: list[str], *argv: str) -> tuple[Run, ScriptedPrompter]:
        prompter = ScriptedPrompter(answers, watch=config_path)
        monkeypatch.setattr(init_module, "_prompter_factory", lambda: prompter)
        return _invoke(["install", *argv]), prompter

    return runner


# ---------------------------------------------------------------------------
# Interview answers
# ---------------------------------------------------------------------------

#: Four *distinct* closed loopback ports, one per network subsystem.  Nothing
#: listens on any of them, so every probe fails fast — and, because the ports
#: differ, a finding can only name one of these addresses if it probed the
#: config the interview just wrote.
LLM_ADDRESS = "http://127.0.0.1:1/v1"
MEMORY_ADDRESS = "http://127.0.0.1:2"
TELEMETRY_ADDRESS = "http://127.0.0.1:3"
TEMPORAL_ADDRESS = "127.0.0.1:4"

#: A gateway-mode interview, in the order the walkthrough asks.
GATEWAY_ANSWERS: list[str] = [
    "gateway",  # llm mode
    LLM_ADDRESS,  # llm gateway base_url
    "ERGANE_LLM_MASTER_KEY",  # llm gateway master key env-var name
    "hindsight",  # memory backend
    MEMORY_ADDRESS,  # memory url
    "ERGANE_HINDSIGHT_KEY",  # memory api key env-var name
    "external",  # temporal mode
    TEMPORAL_ADDRESS,  # temporal address
    "ergane",  # temporal namespace
    "-",  # temporal api key env-var name (cleared)
    "false",  # temporal TLS enabled
    TELEMETRY_ADDRESS,  # telemetry OTLP endpoint
    "telegram",  # escalation adapter
    "ERGANE_TELEGRAM_BOT_TOKEN",  # escalation bot token env-var name
    "ERGANE_TELEGRAM_CHAT_ID",  # escalation chat id env-var name
]


def _answers(**overrides: str) -> list[str]:
    """GATEWAY_ANSWERS with individual positions replaced by name."""
    order = [
        "llm_mode",
        "llm_base_url",
        "llm_master_key_env",
        "memory_backend",
        "memory_url",
        "memory_api_key_env",
        "temporal_mode",
        "temporal_address",
        "temporal_namespace",
        "temporal_api_key_env",
        "temporal_tls",
        "telemetry_endpoint",
        "escalation_adapter",
        "escalation_bot_token_env",
        "escalation_chat_id_env",
    ]
    answers = list(GATEWAY_ANSWERS)
    for name, value in overrides.items():
        answers[order.index(name)] = value
    return answers


def _blocks(text: str) -> dict[str, list[str]]:
    """Split a rendered config into `{block name: [lines]}` for diffing."""
    blocks: dict[str, list[str]] = {"": []}
    current = ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            current = stripped.strip("[]")
            blocks.setdefault(current, [])
            continue
        if stripped:
            blocks[current].append(stripped)
    return blocks


# ---------------------------------------------------------------------------
# T020 [US3-S1] a blank host: the file parses and the verify findings are last
# ---------------------------------------------------------------------------


def test_walkthrough_on_a_blank_host_writes_a_parsing_config_and_ends_with_findings(
    walkthrough: Callable[..., tuple[Run, ScriptedPrompter]],
    config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US3-S1: the interview's file parses under US1, and verify's findings end the output.

    The four addresses are distinct closed ports typed at the prompt.  A verify
    that never loaded this file cannot name them, so the finding details are the
    evidence that FR-007's last clause really ran.
    """
    monkeypatch.setenv("ERGANE_LLM_MASTER_KEY", "sk-not-a-real-key")
    assert config_path.exists() is False

    result, prompter = walkthrough(_answers())

    # The file exists and parses under US1's parser, with exactly the answers given.
    assert config_path.is_file()
    config = load_controlplane_config(str(config_path))
    assert config.version == 1
    assert config.llm.mode == "gateway"
    assert config.llm.gateway is not None
    assert config.llm.gateway.base_url == LLM_ADDRESS
    assert config.llm.gateway.master_key_env == "ERGANE_LLM_MASTER_KEY"
    assert config.memory.backend == "hindsight"
    assert config.memory.url == MEMORY_ADDRESS
    assert config.temporal.mode == "external"
    assert config.temporal.address == TEMPORAL_ADDRESS
    assert config.temporal.namespace == "ergane"
    assert config.temporal.api_key_env is None
    assert config.telemetry.otlp_endpoint == TELEMETRY_ADDRESS
    assert config.escalation.adapter == "telegram"

    # The file install writes is exactly the canonical rendering of what it
    # parses to — the interview and `render_controlplane_config` cannot drift.
    assert config_path.read_text(encoding="utf-8") == render_controlplane_config(config)

    # The verification ran, against this file: every finding rendered, and the
    # details name the addresses the operator typed.
    assert "[FAIL] llm:" in result.stdout
    assert LLM_ADDRESS in result.stdout
    assert MEMORY_ADDRESS in result.stdout
    assert TELEMETRY_ADDRESS in result.stdout
    assert TEMPORAL_ADDRESS in result.stdout

    # The findings are the *last* thing printed — five lines, one per check.
    tail = [line for line in result.stdout.strip().splitlines() if line][-5:]
    assert [line.split(":", 1)[0] for line in tail] == [
        "[FAIL] llm",
        "[FAIL] temporal",
        "[FAIL] memory",
        "[FAIL] telemetry",
        "[FAIL] escalation",
    ]
    # Nothing answered, so the command reports the failure.
    assert result.code == EXIT_USER
    # Every question was answered; none was skipped.
    assert prompter.answers == []


def test_walkthrough_asks_only_the_fields_the_chosen_mode_needs(
    walkthrough: Callable[..., tuple[Run, ScriptedPrompter]],
) -> None:
    """US3-S1: mode first, then only that mode's fields.

    Two runs that differ only in the first answer must ask different questions —
    a walkthrough with a fixed question list cannot pass this.
    """
    _, gateway = walkthrough(_answers())
    gateway_prompts = gateway.prompts

    direct_answers = [
        "direct",  # llm mode
        "implementer",  # persona name
        LLM_ADDRESS,  # persona base_url
        "ollama-cloud/kimi-k2.7-code",  # persona model
        "ERGANE_LLM_MASTER_KEY",  # persona api key env-var name
        "n",  # add another persona?
        *GATEWAY_ANSWERS[3:],
    ]
    _, direct = walkthrough(direct_answers)
    direct_prompts = direct.prompts

    assert any("gateway base_url" in prompt for prompt in gateway_prompts)
    assert not any("persona" in prompt for prompt in gateway_prompts)

    assert any("persona model" in prompt for prompt in direct_prompts)
    assert not any("gateway base_url" in prompt for prompt in direct_prompts)

    # And the direct-mode file really carries the persona block.
    config = load_controlplane_config()
    assert config.llm.mode == "direct"
    assert [p.name for p in config.llm.personas] == ["implementer"]
    assert config.llm.personas[0].model == "ollama-cloud/kimi-k2.7-code"


def test_the_real_terminal_prompter_drives_the_interview(
    config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Plan trap 9: the *default* prompter is executed, not only the scripted seam.

    Every other test in this file rebinds `_prompter_factory`, which is exactly
    the arrangement that let `ergane repo migrate-runtime-root` ship a function
    no test ever entered.  Here `_prompter_factory` is left alone: the real
    `_TerminalPrompter` runs, `input()` runs, and the answers arrive on stdin
    the way an operator's keystrokes do.
    """
    assert init_module._prompter_factory is None, "this test needs the production seam"
    monkeypatch.setattr(sys, "stdin", io.StringIO("\n".join(_answers()) + "\n"))

    result = _invoke(["install"])

    # The values could only reach the file through the real prompter.
    config = load_controlplane_config(str(config_path))
    assert config.llm.gateway is not None
    assert config.llm.gateway.base_url == LLM_ADDRESS
    assert config.temporal.address == TEMPORAL_ADDRESS
    assert config.telemetry.otlp_endpoint == TELEMETRY_ADDRESS
    # The questions were echoed to the terminal, defaults shown in brackets.
    assert "llm mode (gateway|direct) [gateway]" in result.stdout
    assert "[FAIL] temporal:" in result.stdout


# ---------------------------------------------------------------------------
# T021 [US3-S2] a re-run edits, and edits surgically
# ---------------------------------------------------------------------------


def test_rerun_offers_the_existing_file_as_defaults_and_touches_only_telemetry(
    walkthrough: Callable[..., tuple[Run, ScriptedPrompter]],
    config_path: Path,
) -> None:
    """US3-S2: re-running and changing only the OTLP endpoint changes only `[telemetry]`.

    The first file is written with values no built-in default produces (a
    namespace, ports and env-var names chosen for this test), so a walkthrough
    that ignored the existing file and re-seeded blank-host defaults would
    change several blocks, not one.
    """
    first_answers = _answers(
        temporal_namespace="ergane-odd-namespace",
        temporal_address="127.0.0.1:24733",
        escalation_bot_token_env="ODD_BOT_TOKEN_NAME",
    )
    walkthrough(first_answers)
    before = config_path.read_text(encoding="utf-8")

    # Re-run: every answer empty (accept the offered default) except telemetry.
    rerun_answers = [""] * len(GATEWAY_ANSWERS)
    rerun_answers[11] = "http://127.0.0.1:5"
    _, prompter = walkthrough(rerun_answers)
    after = config_path.read_text(encoding="utf-8")

    # The existing file was loaded as defaults: the prompter was offered them.
    assert prompter.defaults_for("temporal namespace") == ["ergane-odd-namespace"]
    assert prompter.defaults_for("temporal address") == ["127.0.0.1:24733"]
    assert prompter.defaults_for("escalation bot token env-var name (optional)") == [
        "ODD_BOT_TOKEN_NAME"
    ]
    assert prompter.defaults_for("telemetry OTLP endpoint (optional)") == [TELEMETRY_ADDRESS]

    # Exactly one block moved.
    blocks_before, blocks_after = _blocks(before), _blocks(after)
    assert set(blocks_before) == set(blocks_after)
    changed = [
        name for name in blocks_before if blocks_before[name] != blocks_after[name]
    ]
    assert changed == ["telemetry"]
    assert blocks_after["telemetry"] == ['otlp_endpoint = "http://127.0.0.1:5"']


def test_rerun_with_unchanged_answers_is_byte_identical(
    walkthrough: Callable[..., tuple[Run, ScriptedPrompter]],
    config_path: Path,
) -> None:
    """FR-007: a re-run that changes nothing rewrites the same bytes."""
    walkthrough(_answers())
    before = config_path.read_bytes()

    walkthrough([""] * len(GATEWAY_ANSWERS))
    after = config_path.read_bytes()

    assert after == before


def test_rendering_round_trips_through_the_parser() -> None:
    """Trap 4: the file is rendered from the typed shape, so parse(render(x)) == x."""
    original = parse_controlplane_config(
        "\n".join(
            [
                "version = 1",
                "",
                "[llm]",
                'mode = "gateway"',
                'base_url = "http://127.0.0.1:4000"',
                'master_key_env = "ERGANE_LLM_MASTER_KEY"',
                "",
                "[memory]",
                'backend = "hindsight"',
                'url = "http://127.0.0.1:8888"',
                'api_key_env = "ERGANE_HINDSIGHT_KEY"',
                "",
                "[temporal]",
                'mode = "external"',
                'address = "127.0.0.1:7233"',
                'namespace = "ergane"',
                'api_key_env = "ERGANE_TEMPORAL_KEY"',
                "tls_enabled = true",
                "",
                "[telemetry]",
                'otlp_endpoint = "http://127.0.0.1:4318"',
                "",
                "[escalation]",
                'adapter = "telegram"',
                'bot_token_env = "ERGANE_TELEGRAM_BOT_TOKEN"',
                'chat_id_env = "ERGANE_TELEGRAM_CHAT_ID"',
            ]
        )
        + "\n",
        source="fixture",
    )

    rendered = render_controlplane_config(original)
    assert parse_controlplane_config(rendered, source="rendered") == original
    # And rendering is a pure function of the typed shape: stable across calls.
    assert render_controlplane_config(original) == rendered


# ---------------------------------------------------------------------------
# T022 / T022a [US3-S3] refuse at entry, with the parser's own rule
# ---------------------------------------------------------------------------


def test_a_plaintext_secret_is_refused_at_entry_with_the_parsers_rule(
    walkthrough: Callable[..., tuple[Run, ScriptedPrompter]],
    config_path: Path,
) -> None:
    """US3-S3: a credential typed where a reference belongs never reaches the file.

    The rule is the parser's, not a second copy: the same document parsed
    directly raises `secret_value_not_reference`, and that slug is what the
    operator is shown at entry time.
    """
    secret = "sk-live-super-secret-value"
    answers = _answers(llm_master_key_env=secret)
    # After the refusal the operator is asked again; supply the good answer.
    answers.insert(3, "ERGANE_LLM_MASTER_KEY")

    result, prompter = walkthrough(answers)

    errors = prompter.errors_for("llm gateway master key env-var name")
    assert len(errors) == 1
    assert "secret_value_not_reference" in errors[0]
    assert "master_key_env" in errors[0]

    # The parser refuses the same value with the same rule — one rule table.
    with pytest.raises(ControlPlaneConfigError) as refusal:
        parse_controlplane_config(
            "\n".join(
                [
                    "version = 1",
                    "[llm]",
                    'mode = "gateway"',
                    'base_url = "http://127.0.0.1:1/v1"',
                    f'master_key_env = "{secret}"',
                    "[memory]",
                    'backend = "none"',
                    "[temporal]",
                    'mode = "external"',
                    'address = "127.0.0.1:4"',
                    'namespace = "ergane"',
                    "[telemetry]",
                    "[escalation]",
                    'adapter = "telegram"',
                ]
            ),
            source="fixture",
        )
    assert refusal.value.rule == "secret_value_not_reference"
    assert refusal.value.rule in errors[0]

    # Refused at entry, never written: no file existed while the operator was
    # still being asked, and the secret is in neither the file nor the output.
    assert [asked.config_existed for asked in prompter.asked] == [False] * len(
        prompter.asked
    )
    written = config_path.read_text(encoding="utf-8")
    assert secret not in written
    assert 'master_key_env = "ERGANE_LLM_MASTER_KEY"' in written
    assert secret not in result.stdout


def test_managed_temporal_is_refused_at_entry_naming_042(
    walkthrough: Callable[..., tuple[Run, ScriptedPrompter]],
    config_path: Path,
) -> None:
    """T022a: answering `managed` is refused at entry with the landed parser's rule."""
    answers = _answers(temporal_mode="managed")
    answers.insert(7, "external")  # the re-ask after the refusal

    _, prompter = walkthrough(answers)

    errors = prompter.errors_for("temporal mode (external|managed)")
    assert len(errors) == 1
    assert "temporal_managed_not_implemented" in errors[0]
    assert "042" in errors[0]

    config = load_controlplane_config(str(config_path))
    assert config.temporal.mode == "external"


# ---------------------------------------------------------------------------
# T022b [edge case] an unreadable existing config fails closed
# ---------------------------------------------------------------------------


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file permission bits")
def test_an_unreadable_existing_config_fails_closed(
    walkthrough: Callable[..., tuple[Run, ScriptedPrompter]],
    config_path: Path,
) -> None:
    """Edge case: a config the process cannot read is named, not half-parsed."""
    walkthrough(_answers())
    original = config_path.read_bytes()
    config_path.chmod(0o000)

    try:
        result, prompter = walkthrough(_answers())

        assert result.code == EXIT_USER
        assert str(config_path) in result.stderr
        assert "Permission denied" in result.stderr
        # Fail closed: no question was asked and the file was not rewritten.
        assert prompter.asked == []

        # And any consumer reaching it through the landed resolver fails the same way.
        with pytest.raises(ControlPlaneConfigError) as refusal:
            load_controlplane_config()
        assert refusal.value.rule == "config_missing"
        assert "Permission denied" in refusal.value.problem
    finally:
        config_path.chmod(0o600)

    assert config_path.read_bytes() == original


# ---------------------------------------------------------------------------
# T023 [US3-S4] the lock, contended by a second OS process
# ---------------------------------------------------------------------------


#: A child that takes the production lock on a path and holds it.  It prints
#: `LOCKED` once it has the lock so the parent never races the handshake.
_HOLDER = """
import sys, time
from factory.locking import exclusive_lock

target, hold = sys.argv[1], float(sys.argv[2])
with exclusive_lock(target, timeout_s=10):
    print("LOCKED", flush=True)
    time.sleep(hold)
print("RELEASED", flush=True)
"""


@dataclass
class _Holder:
    process: subprocess.Popen
    pid: int


def _hold_the_lock(target: Path, seconds: float) -> _Holder:
    """Start a child that takes the lock on `target`; return once it holds it."""
    process = subprocess.Popen(
        [sys.executable, "-c", _HOLDER, str(target), str(seconds)],
        cwd=str(REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdout is not None
    line = process.stdout.readline().strip()
    if line != "LOCKED":
        process.kill()
        process.wait(timeout=10)
        raise AssertionError(
            f"lock holder did not start: {line!r} "
            f"{process.stderr.read() if process.stderr else ''}"
        )
    return _Holder(process=process, pid=process.pid)


@pytest.fixture
def lock_holder(config_path: Path) -> Iterator[Callable[[float], _Holder]]:
    """Start lock-holding children, and reap every one of them (trap 10).

    The `finally` is not decoration: an orphaned child of this shape is what
    OOM-killed the host on 2026-08-11.
    """
    started: list[subprocess.Popen] = []

    def start(seconds: float) -> _Holder:
        holder = _hold_the_lock(config_path, seconds)
        started.append(holder.process)
        return holder

    try:
        yield start
    finally:
        for process in started:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    stream.close()


def test_a_second_install_is_refused_while_another_holds_the_lock(
    walkthrough: Callable[..., tuple[Run, ScriptedPrompter]],
    config_path: Path,
    lock_holder: Callable[[float], _Holder],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """US3-S4: with the lock held by another process, install refuses and writes nothing."""
    holder = lock_holder(30.0)
    assert lock_path_for(config_path).is_file()

    started = time.monotonic()
    result, prompter = walkthrough(_answers(), "--lock-timeout", "0.5")
    elapsed = time.monotonic() - started

    with capsys.disabled():
        print(f"\nchild pid {holder.pid} holds {lock_path_for(config_path)}")
        print(result.stderr.strip())
        print(
            f"refused after {elapsed:.2f}s, exit {result.code}, "
            f"config written: {config_path.exists()}"
        )

    assert result.code == EXIT_USER
    assert "lock" in result.stderr.lower()
    assert str(config_path) in result.stderr
    assert config_path.exists() is False
    # Refused before the interview: an operator is never asked questions whose
    # answers cannot be written.
    assert prompter.asked == []
    assert 0.4 <= elapsed < 20.0


def test_a_second_install_waits_for_the_lock_and_then_writes(
    walkthrough: Callable[..., tuple[Run, ScriptedPrompter]],
    config_path: Path,
    lock_holder: Callable[[float], _Holder],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """US3-S4: the alternative to refusal is waiting — and then the write happens."""
    monkeypatch.setenv("ERGANE_LLM_MASTER_KEY", "sk-not-a-real-key")
    hold_s = 1.0
    holder = lock_holder(hold_s)

    started = time.monotonic()
    result, _ = walkthrough(_answers(), "--lock-timeout", "20")
    elapsed = time.monotonic() - started

    with capsys.disabled():
        print(f"\nchild pid {holder.pid} holds {lock_path_for(config_path)} for {hold_s}s")
        print(
            f"walkthrough returned after {elapsed:.2f}s, exit {result.code}, "
            f"config written: {config_path.exists()}"
        )

    assert config_path.is_file()
    assert elapsed >= hold_s * 0.7, "the walkthrough did not wait for the held lock"
    load_controlplane_config(str(config_path))


def test_the_lock_helper_refuses_a_held_lock_within_its_timeout(
    tmp_path: Path, lock_holder: Callable[[float], _Holder], config_path: Path
) -> None:
    """The lock is real mutual exclusion, not a file that is merely created."""
    lock_holder(30.0)

    started = time.monotonic()
    with pytest.raises(LockUnavailable) as refusal:
        with exclusive_lock(config_path, timeout_s=0.3):
            pass
    elapsed = time.monotonic() - started

    assert str(config_path) in str(refusal.value)
    assert 0.25 <= elapsed < 10.0

    # An uncontended path is free: the helper is not simply always refusing.
    with exclusive_lock(tmp_path / "other.toml", timeout_s=0.3):
        pass


# ---------------------------------------------------------------------------
# T027a [SC-002] no credential in the config file or in the logs
# ---------------------------------------------------------------------------


class _RecordingTelegramBot:
    """A Telegram stand-in that records the credential it was handed."""

    def __init__(self, token: str) -> None:
        self.token = token
        self.calls: list[dict[str, Any]] = []

    async def send_message(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)

        class _Message:
            message_id = 42

        return _Message()


def test_walkthrough_and_verify_never_write_a_credential(
    walkthrough: Callable[..., tuple[Run, ScriptedPrompter]],
    config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """SC-002: grepping the produced file and every log for the session's credentials finds nothing.

    Credentials are genuinely in play: the LLM probe resolves its key and puts
    it on the wire (against a closed port, which is where an error message is
    most likely to echo it back), and the escalation probe resolves the bot
    token and delivers with it.
    """
    credentials = {
        "ERGANE_LLM_MASTER_KEY": "sk-secret-llm-value-do-not-log",
        "ERGANE_HINDSIGHT_KEY": "hs-secret-memory-value-do-not-log",
        "ERGANE_TELEGRAM_BOT_TOKEN": "123456:SECRET-bot-token-do-not-log",
    }
    for name, value in credentials.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("ERGANE_TELEGRAM_CHAT_ID", "-1001234567890")

    bots: list[_RecordingTelegramBot] = []

    def _recording_bot_factory(config: Any, *, timeout_s: int | None = None) -> Any:
        token = os.environ.get(config.bot_token_env or "", "")
        bot = _RecordingTelegramBot(token)
        bots.append(bot)
        return bot

    monkeypatch.setattr(verify_module, "_telegram_bot_factory", _recording_bot_factory)

    result, _ = walkthrough(_answers())

    config_text = config_path.read_text(encoding="utf-8")
    logs = result.stdout + result.stderr

    # The credentials really were used this session.
    assert bots and bots[0].token == credentials["ERGANE_TELEGRAM_BOT_TOKEN"]
    assert bots[0].calls

    file_hits = {name: config_text.count(value) for name, value in credentials.items()}
    log_hits = {name: logs.count(value) for name, value in credentials.items()}

    with capsys.disabled():
        print("\ncredentials in play this session:")
        for name, value in credentials.items():
            print(f"  {name:<27} = {value!r}")
        print(f"the escalation probe used its credential: {bool(bots[0].calls)}")
        print(f"occurrences in {config_path}: {sum(file_hits.values())}")
        print(f"occurrences in captured stdout+stderr: {sum(log_hits.values())}")
        print(
            "env-var NAMES present in the config file: "
            f"{all(name in config_text for name in credentials)}"
        )

    assert sum(file_hits.values()) == 0, file_hits
    assert sum(log_hits.values()) == 0, log_hits
    # Non-trivial: the fields *are* written — as references, by name.
    for name in credentials:
        assert name in config_text
