"""Tests for the `ergane install` walkthrough (US3 of 033-ergane-install).

The walkthrough interviews the operator subsystem by subsystem, writes the
control-plane config, and ends by running US2's verification.  Most tests drive
it through the CLI with the scripted prompter seam 034/us1 landed
(`factory.cli.init._prompter_factory`) — never a monkeypatched `input()` — and
one drives the *real* `_TerminalPrompter` over stdin, because a seam every test
rebinds is a seam nothing executes (plan trap 9).

**What each test has to be unable to pass without the production code**, because
the defect that has cost this repository most is a fixture that makes a test
unable to fail:

- the blank-host test points every subsystem at a *distinct closed port* typed
  at the prompt, so the findings printed at the end can only carry those four
  addresses if the file just written was really loaded and really probed;
- the re-run test seeds the existing file with values no built-in default could
  produce, and asserts the prompter was *offered* them as defaults;
- the refuse-at-entry tests record whether the config file exists at each
  question, so "refuse at entry, never write-then-fail" is asserted rather than
  assumed;
- the lock tests hold the lock from a **separate OS process**, so a walkthrough
  that took no lock would sail straight past them.

Evidence rule (constitution VIII): every runtime claim below is pasted verbatim
from a run, and paths are elided only where a pytest tmp dir would add noise.

Red before green
----------------

The tests in this file against the tree before `factory/cli/install.py`,
`factory/locking.py` and the renderer existed:

.. code-block:: text

    $ uv run pytest tests/test_ergane_install_walkthrough.py -q
    ==================================== ERRORS ====================================
    __________ ERROR collecting tests/test_ergane_install_walkthrough.py ___________
    ImportError while importing test module '/…/tests/test_ergane_install_walkthrough.py'.
    Hint: make sure your test modules/packages have valid Python names.
    Traceback:
    /home/admin/.local/share/uv/python/cpython-3.13.12-linux-aarch64-gnu/lib/python3.13/importlib/__init__.py:88: in import_module
        return _bootstrap._gcd_import(name[level:], package, level)
    tests/test_ergane_install_walkthrough.py:107: in <module>
        from factory.controlplane.config import (
    E   ImportError: cannot import name 'render_controlplane_config' from 'factory.controlplane.config'
    =========================== short test summary info ============================
    ERROR tests/test_ergane_install_walkthrough.py
    !!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
    1 error in 0.16s

Green, and the transcripts these tests print
--------------------------------------------

.. code-block:: text

    $ uv run pytest tests/test_ergane_install_walkthrough.py -q
    .........
    child pid 2499464 holds /tmp/…/test_a_second_install_is_refus0/ergane/config.toml.lock
    ergane: another `ergane install` holds the lock on /tmp/…/ergane/config.toml (waited 0.5s); wait for it to finish, or remove config.toml.lock if no install is running
    refused after 0.50s, exit 1, config written: False
    .
    child pid 2499492 holds /tmp/…/test_a_second_install_waits_fo0/ergane/config.toml.lock for 1.0s
    walkthrough returned after 1.02s, exit 1, config written: True
    ..
    credentials in play this session:
      ERGANE_LLM_MASTER_KEY       = 'sk-secret-llm-value-do-not-log'
      ERGANE_HINDSIGHT_KEY        = 'hs-secret-memory-value-do-not-log'
      ERGANE_TELEGRAM_BOT_TOKEN   = '123456:SECRET-bot-token-do-not-log'
    the escalation probe used its credential: True
    occurrences in /tmp/…/ergane/config.toml: 0
    occurrences in captured stdout+stderr: 0
    env-var NAMES present in the config file: True
    .                                                            [100%]
    13 passed in 2.18s

(That run predates the redaction test below by two commits, which is why it
reports 13 tests and the SC-002 block has one fewer line than it does now.)

Controls: each property switched off, and what goes red
-------------------------------------------------------

A green suite proves nothing about a test that cannot fail, so each of FR-007's
clauses was disabled in turn and the file re-run.  The mutations, in order: the
lock replaced by a no-op context manager; `_starting_document` forced to ignore
an existing file; `_ask` returning the first answer unvalidated; the closing
verification removed; and the refusal message left un-redacted.

.. code-block:: text

    ### mutation: nolock
    FAILED …::test_a_second_install_is_refused_while_another_holds_the_lock
    FAILED …::test_a_second_install_waits_for_the_lock_and_then_writes
    2 failed, 11 passed in 0.69s

    ### mutation: nodefaults
    FAILED …::test_rerun_offers_the_existing_file_as_defaults_and_touches_only_telemetry
    FAILED …::test_rerun_with_unchanged_answers_is_byte_identical
    2 failed, 11 passed in 2.18s

    ### mutation: novalidate
    FAILED …::test_a_plaintext_secret_is_refused_at_entry_with_the_parsers_rule
    FAILED …::test_managed_temporal_is_refused_at_entry_naming_042
    2 failed, 11 passed in 2.19s

    ### mutation: noverify
    FAILED …::test_walkthrough_on_a_blank_host_writes_a_parsing_config_and_ends_with_findings
    FAILED …::test_the_real_terminal_prompter_drives_the_interview
    FAILED …::test_walkthrough_and_verify_never_write_a_credential
    3 failed, 10 passed in 2.04s

    ### mutation: noredact
    FAILED …::test_the_real_terminal_prompter_drives_the_interview
    FAILED …::test_a_plaintext_secret_is_refused_at_entry_with_the_parsers_rule
    2 failed, 11 passed in 2.21s

The command, run by hand
------------------------

A green suite has shipped a command that could not start, so the console script
was driven from a shell with answers on stdin — including a pasted credential
and a `managed` Temporal mode, both of which must be refused at entry.  The
config path is redirected to a scratch file; `~/.config/ergane` below is that
path, elided.

This transcript is from the 033 tree.  One line of it has since gone stale: the
first question reads `llm mode (gateway)` as of 048-US2, which refused `direct`
at the parser and stopped the interview offering it.  A run of the same command
against the current tree — answering `direct` and reading what it says — is
pasted in `tests/test_direct_mode_refused.py`; everything else below still holds.

.. code-block:: text

    $ printf 'gateway\nexternal\nhttp://127.0.0.1:1/v1\nsk-live-pasted-by-mistake\nERGANE_LLM_MASTER_KEY\nnone\nmanaged\nexternal\n127.0.0.1:4\nergane\n\n\nhttp://127.0.0.1:3\n\n\n\n' \
        | ERGANE_CONFIG_PATH=…/config.toml uv run ergane install
    llm mode (gateway) [gateway]: gateway mode (external|managed) [external]: llm gateway base_url [http://127.0.0.1:4000]: llm gateway master key env-var name [ERGANE_LLM_MASTER_KEY]:   ~/.config/ergane/config.toml: [secret_value_not_reference] `master_key_env` looks like a credential (<value withheld>); it must name an environment variable, not contain the secret value
    llm gateway master key env-var name [ERGANE_LLM_MASTER_KEY]: memory backend (hindsight|none) [none]: temporal mode (external|managed) [external]:   ~/.config/ergane/config.toml: [temporal_managed_not_implemented] `temporal.mode = "managed"` is not implemented; it arrives with epic 042 (managed Temporal + worker units)
    temporal mode (external|managed) [external]: temporal address [127.0.0.1:7233]: temporal namespace [ergane]: temporal api key env-var name (optional): temporal TLS enabled (true|false) [false]: telemetry OTLP endpoint (optional): escalation adapter (telegram) [telegram]: escalation bot token env-var name (optional) [TELEGRAM_BOT_TOKEN]: escalation chat id env-var name (optional) [TELEGRAM_CHAT_ID]: wrote ~/.config/ergane/config.toml

    verifying the control plane...
    [FAIL] llm: ERGANE_LLM_MASTER_KEY is not set; no credential to complete a round trip
    [FAIL] temporal: Temporal at 127.0.0.1:4 did not answer: RuntimeError: Failed client connect: Server connection error: tonic::transport::Error(Transport, ConnectError(ConnectError("tcp connect error", 127.0.0.1:4, Os { code: 111, kind: ConnectionRefused, message: "Connection refused" })))
    [PASS] memory: skipped by declaration: memory.backend is `none`
    [FAIL] telemetry: could not export to OTLP endpoint http://127.0.0.1:3: ConnectError: All connection attempts failed
    [FAIL] escalation: TELEGRAM_CHAT_ID is not set; cannot deliver a test escalation
    EXIT=1

    $ grep -c 'sk-live-pasted-by-mistake' run.log
    0

    $ cat config.toml
    version = 1

    [llm]
    mode = "gateway"
    base_url = "http://127.0.0.1:1/v1"
    master_key_env = "ERGANE_LLM_MASTER_KEY"

    [memory]
    backend = "none"

    [temporal]
    mode = "external"
    address = "127.0.0.1:4"
    namespace = "ergane"

    [telemetry]
    otlp_endpoint = "http://127.0.0.1:3"

    [escalation]
    adapter = "telegram"
    bot_token_env = "TELEGRAM_BOT_TOKEN"
    chat_id_env = "TELEGRAM_CHAT_ID"

The refused answers reached neither the file nor the transcript, and the file
carries no `tls_enabled = false` — the canonical rendering omits a flag at its
default, so a hand-written config does not gain a line on its first re-run.

US3-S2 by hand: re-run, change only the OTLP endpoint, diff the file.

.. code-block:: text

    $ diff -u before.toml config.toml
    --- ~/.config/ergane/before.toml	2026-08-16 03:57:19.294467675 +0000
    +++ ~/.config/ergane/config.toml	2026-08-16 03:57:19.521917896 +0000
    @@ -14,7 +14,7 @@
     namespace = "ergane"

     [telemetry]
    -otlp_endpoint = "http://127.0.0.1:3"
    +otlp_endpoint = "http://127.0.0.1:9"

     [escalation]
     adapter = "telegram"

    # and a third run, changing nothing
    byte-identical: yes

One more thing that run found, before the redaction landed: an out-of-position
answer (a URL where the TLS question was) was refused at entry rather than
written, and the re-run stayed byte-identical.

.. code-block:: text

    temporal TLS enabled (true|false) [false]:   …/config.toml: [field_type] `temporal.tls_enabled` must be a boolean, not a str ('http://127.0.0.1:9')
    temporal TLS enabled (true|false) [false]:

The full suite
--------------

.. code-block:: text

    $ uv run pytest -q
    4953 passed, 56 skipped, 6 warnings in 357.81s (0:05:57)
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
    render_controlplane_document,
)
from factory.locking import LockUnavailable, exclusive_lock, lock_path_for

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _stub_persona_step_and_closing_demo(monkeypatch: pytest.MonkeyPatch) -> None:
    """US4/US6: the persona and closing steps are tested in their own files.

    The walkthrough tests below drive the LLM/memory/temporal/telemetry/
    escalation interview and the verification that ends it.  Stubbing the later
    acts keeps each module focused on the questions it actually covers.
    """
    import factory.cli.install as install_module

    monkeypatch.setattr(install_module, "_interview_personas", lambda _p, _d, _pp: None)
    monkeypatch.setattr(install_module, "_closing_demonstration", lambda *_a, **_k: None)


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
    # 062/US2: install seeds ~/.config/ergane/personas.yaml.  Existing walkthrough
    # tests exercise the real repo registry; point the persona resolver at it so
    # verify probes the addresses the operator typed, and isolate the config home.
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    repo_registry = str(REPO_ROOT / "personas.yaml")
    monkeypatch.setenv("ERGANE_PERSONAS_PATH", repo_registry)
    monkeypatch.setenv("FACTORY_PERSONAS_PATH", repo_registry)
    return path


@pytest.fixture
def walkthrough(
    monkeypatch: pytest.MonkeyPatch, config_path: Path
) -> Callable[..., tuple[Run, ScriptedPrompter]]:
    """Run `ergane install` with a scripted prompter, returning the run and prompter.

    US4 adds the persona interview step to interactive install; these walkthrough
    tests are about the LLM/memory/temporal/telemetry/escalation interview and
    deliberately stub that step out so they keep covering their own concerns.
    """
    def runner(answers: list[str], *argv: str) -> tuple[Run, ScriptedPrompter]:
        prompter = ScriptedPrompter(answers, watch=config_path)
        monkeypatch.setattr(init_module, "_prompter_factory", lambda: prompter)
        # 048-US4: `--verify` resolves Temporal under the one precedence now, so
        # an inherited `TEMPORAL_ADDRESS` would send the probe somewhere other
        # than the address just typed — and the four distinct closed ports are
        # the whole evidence that verify read the file the interview wrote.
        monkeypatch.delenv("TEMPORAL_ADDRESS", raising=False)
        monkeypatch.delenv("TEMPORAL_NAMESPACE", raising=False)
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
    "external",  # gateway mode (external|managed)
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
        "gateway_mode",
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
    # Direct mode skips the gateway-mode question entirely (109-US1 FR-006).
    if answers[order.index("llm_mode")] == "direct":
        del answers[order.index("gateway_mode")]
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


def test_walkthrough_can_select_none_escalation_adapter(
    walkthrough: Callable[..., tuple[Run, ScriptedPrompter]],
    config_path: Path,
) -> None:
    """US3 / T029: the interactive path offers `none` and reaches the same state."""
    answers = _answers(escalation_adapter="none")
    # `none` needs no bot token or chat id, so those two answers go unused.
    del answers[-2:]
    _, prompter = walkthrough(answers)

    config = load_controlplane_config(str(config_path))
    assert config.escalation.adapter == "none"
    assert config.escalation.bot_token_env is None
    assert config.escalation.chat_id_env is None

    prompts = prompter.prompts
    assert any("escalation adapter (telegram|none)" in prompt for prompt in prompts)
    assert not any("escalation bot token" in prompt for prompt in prompts)
    assert not any("escalation chat id" in prompt for prompt in prompts)
    assert prompter.answers == []


def test_walkthrough_asks_only_the_fields_the_chosen_mode_needs(
    walkthrough: Callable[..., tuple[Run, ScriptedPrompter]],
) -> None:
    """US3-S1: mode first, then only that mode's fields.

    Two runs that differ only in one mode answer must ask different questions —
    a walkthrough with a fixed question list cannot pass this.

    Until 048-US2 this property was demonstrated on the *llm* block, whose two
    modes were `gateway` and `direct`. `direct` is now refused at the parser,
    so the demonstration moves to `memory`, which still has two shapes; the llm
    half became `test_the_interview_re_asks_carrying_the_parsers_own_refusal`
    in `tests/test_direct_mode_refused.py`, where it asserts the refusal rather
    than the persona questions.
    """
    _, hindsight = walkthrough(_answers())
    hindsight_prompts = hindsight.prompts

    none_answers = _answers(memory_backend="none")
    # `none` needs neither a url nor an api key, so those two answers go unused.
    del none_answers[5:7]
    _, without = walkthrough(none_answers)
    none_prompts = without.prompts

    assert any("memory url" in prompt for prompt in hindsight_prompts)
    assert any("memory api key" in prompt for prompt in hindsight_prompts)

    assert not any("memory url" in prompt for prompt in none_prompts)
    assert not any("memory api key" in prompt for prompt in none_prompts)
    assert without.answers == []

    # And the file really carries the backend that was chosen.
    config = load_controlplane_config()
    assert config.memory.backend == "none"
    assert config.memory.url is None


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
    # One answer is a pasted credential, refused and re-asked — the path that
    # printed a live key to the terminal the first time this command was run by
    # hand, because only the real prompter renders the error at all.
    pasted = "sk-live-pasted-by-mistake"
    answers = _answers()
    answers.insert(3, pasted)
    monkeypatch.setattr(sys, "stdin", io.StringIO("\n".join(answers) + "\n"))

    # US3 runs a scan before the LLM question. On this host that scan finds an
    # inference-only endpoint and offers `direct`; the test's answers still pick
    # `gateway`, so the only thing that must hold is that the default mode is
    # shown in brackets, whichever mode the scan chose.
    import factory.cli.install as install_module

    def _no_scan(*_a: object, **_k: object) -> list:
        return []

    monkeypatch.setattr(install_module, "_scan_endpoints", _no_scan)

    result = _invoke(["install"])

    assert pasted not in result.stdout
    assert pasted not in result.stderr
    assert "secret_value_not_reference" in result.stderr
    assert "<value withheld>" in result.stderr

    # The values could only reach the file through the real prompter.
    config = load_controlplane_config(str(config_path))
    assert config.llm.gateway is not None
    assert config.llm.gateway.base_url == LLM_ADDRESS
    assert config.temporal.address == TEMPORAL_ADDRESS
    assert config.telemetry.otlp_endpoint == TELEMETRY_ADDRESS
    # The questions were echoed to the terminal, defaults shown in brackets.
    assert "llm mode (gateway) [gateway]" in result.stdout
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
    rerun_answers[12] = "http://127.0.0.1:5"
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
    answers.insert(4, "ERGANE_LLM_MASTER_KEY")

    result, prompter = walkthrough(answers)

    errors = prompter.errors_for("llm gateway master key env-var name")
    assert len(errors) == 1
    assert "secret_value_not_reference" in errors[0]
    assert "master_key_env" in errors[0]
    # FR-003: the refusal names the field and the rule, and does NOT echo the
    # credential back at the operator. The first terminal run of this
    # walkthrough printed the pasted `sk-…` in full; that is what this asserts
    # can no longer happen.
    assert secret not in errors[0]
    assert "<value withheld>" in errors[0]

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
    assert secret not in result.stderr




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


def test_verify_with_no_config_reads_as_a_skipped_step_not_a_broken_tool(
    config_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`ergane install --verify` before `ergane install` names the missing step.

    Found by walking the installed package as a new user would. The parser's
    refusal was already the right sentence — it names the file and says to run
    `ergane install` — but nothing caught `ControlPlaneConfigError` at the noun,
    so it fell through to `run_cli`'s defensive boundary and was wrapped as
    `ergane: unexpected error (…); re-run with --debug for the traceback`. A
    first run that has not been configured yet is an expected condition; the
    only thing a traceback offer adds is the impression that Ergane is broken.
    (Finding `interpreter/missing-config-presents-as-an-unexpected-error`.)

    The exit code was already 1 and stays 1 — what changes is what the operator
    is told to do about it.
    """
    assert config_path.exists() is False

    result = _invoke(["install", "--verify"])

    with capsys.disabled():
        print("\n" + result.stderr.strip())

    assert result.code == EXIT_USER
    assert "unexpected error" not in result.stderr
    assert "--debug" not in result.stderr
    assert "run `ergane install` to create the control-plane config" in result.stderr
    assert str(config_path) in result.stderr
    # The refusal reaches the operator instead of anything reaching stdout.
    assert result.stdout == ""


# ---------------------------------------------------------------------------
# T001-T006 [US1] install can be driven from an answer file
# ---------------------------------------------------------------------------

#: The full answer document, in the same TOML schema the command writes.
#: Omitting a block means "use the documented default for every field in it".
_FILE_ANSWER_DOC: dict[str, Any] = {
    "version": 1,
    "llm": {
        "mode": "gateway",
        "base_url": LLM_ADDRESS,
        "master_key_env": "ERGANE_LLM_MASTER_KEY",
    },
    "memory": {
        "backend": "hindsight",
        "url": MEMORY_ADDRESS,
        "api_key_env": "ERGANE_HINDSIGHT_KEY",
    },
    "temporal": {
        "mode": "external",
        "address": TEMPORAL_ADDRESS,
        "namespace": "ergane",
        "tls_enabled": False,
    },
    "telemetry": {"otlp_endpoint": TELEMETRY_ADDRESS},
    "escalation": {
        "adapter": "telegram",
        "bot_token_env": "ERGANE_TELEGRAM_BOT_TOKEN",
        "chat_id_env": "ERGANE_TELEGRAM_CHAT_ID",
    },
}


#: In-tree path to the worked example the documentation promises.
ANSWER_FILE_EXAMPLE = REPO_ROOT / "docs" / "ergane-install-answer.example.toml"


def _run_from_file(
    document: dict[str, Any],
    config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Run:
    """Run `ergane install --from-file <tmp>` with an answer document."""
    answer_path = tmp_path / "answers.toml"
    answer_path.write_text(render_controlplane_document(document), encoding="utf-8")

    # The file-driven path must never fall back to the interactive seam.
    def _refusing_prompter_factory() -> Any:
        raise AssertionError("interactive prompter factory was invoked for --from-file")

    monkeypatch.setattr(init_module, "_prompter_factory", _refusing_prompter_factory)
    monkeypatch.delenv("TEMPORAL_ADDRESS", raising=False)
    monkeypatch.delenv("TEMPORAL_NAMESPACE", raising=False)
    return _invoke(["install", "--from-file", str(answer_path)])


def test_install_from_file_writes_config_without_invoking_terminal_prompter(
    config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """US1-S1: with stdin closed, --from-file writes the config and never prompts."""
    assert config_path.exists() is False
    # Simulate a closed stdin: any read would be an EOFError.
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    sys.stdin.close()

    result = _run_from_file(_FILE_ANSWER_DOC, config_path, monkeypatch, tmp_path)

    assert config_path.is_file()
    config = load_controlplane_config(str(config_path))
    assert config.llm.gateway is not None
    assert config.llm.gateway.base_url == LLM_ADDRESS
    assert config.temporal.address == TEMPORAL_ADDRESS
    assert config.telemetry.otlp_endpoint == TELEMETRY_ADDRESS
    # The interactive seam was not used, so the closed stdin never mattered.
    assert result.code == EXIT_USER
    assert "unexpected error" not in result.stderr


def test_install_from_file_and_interactive_walkthrough_write_identical_configs(
    walkthrough: Callable[..., tuple[Run, ScriptedPrompter]],
    config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """US1-S2: the file-driven path must not fork the interview (trap 1)."""
    interactive, _ = walkthrough(_answers())
    assert interactive.code == EXIT_USER
    interactive_bytes = config_path.read_bytes()
    config_path.unlink()

    result = _run_from_file(_FILE_ANSWER_DOC, config_path, monkeypatch, tmp_path)
    assert result.code == EXIT_USER
    file_bytes = config_path.read_bytes()

    assert file_bytes == interactive_bytes


def test_install_from_file_applies_and_reports_documented_defaults(
    config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """US1-S3: a field omitted from the file takes its documented default, loudly."""
    doc = dict(_FILE_ANSWER_DOC)
    doc["temporal"] = {
        "mode": "external",
        "address": TEMPORAL_ADDRESS,
        # namespace deliberately omitted; the documented default is "ergane".
    }

    result = _run_from_file(doc, config_path, monkeypatch, tmp_path)

    assert result.code == EXIT_USER
    assert config_path.is_file()
    config = load_controlplane_config(str(config_path))
    assert config.temporal.namespace == "ergane"
    assert "applied default: temporal.namespace" in result.stdout
    assert '"ergane"' in result.stdout


def test_install_from_file_refuses_when_a_field_has_no_safe_default(
    config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """US1-S4: a required field with no safe default is named and nothing is written."""
    doc = dict(_FILE_ANSWER_DOC)
    doc["escalation"] = {
        # adapter deliberately omitted; no safe default exists in US1.
        "bot_token_env": "ERGANE_TELEGRAM_BOT_TOKEN",
        "chat_id_env": "ERGANE_TELEGRAM_CHAT_ID",
    }

    result = _run_from_file(doc, config_path, monkeypatch, tmp_path)

    assert result.code == EXIT_USER
    assert config_path.exists() is False
    assert "escalation.adapter" in (result.stdout + result.stderr)


def test_install_from_file_refuses_secret_shape_with_the_same_wording(
    config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """US1-S5: a credential supplied by file hits the same secret-shape guard."""
    secret = "sk-live-super-secret-value"
    doc = dict(_FILE_ANSWER_DOC)
    doc["llm"] = {
        "mode": "gateway",
        "base_url": LLM_ADDRESS,
        "master_key_env": secret,
    }

    result = _run_from_file(doc, config_path, monkeypatch, tmp_path)

    assert result.code == EXIT_USER
    assert config_path.exists() is False
    output = result.stdout + result.stderr
    assert "secret_value_not_reference" in output
    assert "<value withheld>" in output
    assert "master_key_env" in output
    assert secret not in output
    assert secret not in result.stdout
    assert secret not in result.stderr


def test_install_documented_answer_file_example_drives_a_successful_install(
    config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """US1-S6: the in-tree worked example parses and writes a config unmodified."""
    assert ANSWER_FILE_EXAMPLE.is_file(), f"documented example missing: {ANSWER_FILE_EXAMPLE}"
    example_path = tmp_path / "example-answers.toml"
    example_path.write_bytes(ANSWER_FILE_EXAMPLE.read_bytes())

    def _refusing_prompter_factory() -> Any:
        raise AssertionError("interactive prompter factory was invoked for --from-file")

    monkeypatch.setattr(init_module, "_prompter_factory", _refusing_prompter_factory)
    monkeypatch.delenv("TEMPORAL_ADDRESS", raising=False)
    monkeypatch.delenv("TEMPORAL_NAMESPACE", raising=False)
    result = _invoke(["install", "--from-file", str(example_path)])

    assert config_path.is_file(), "config was not written from the documented example"
    config = load_controlplane_config(str(config_path))
    assert config.version == 1
    assert config.llm.mode == "gateway"
    assert "unexpected error" not in result.stderr
    assert "--debug" not in result.stderr
