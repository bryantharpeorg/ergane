"""Tests for 109-US1: the gateway has a bundled half.

These tests exercise the new `gateway mode (external|managed)` interview question,
the `gateway_mode` config field, and the key-management probe parity between the
two modes.

Verification evidence (constitution VIII):

.. code-block:: text

    $ uv run pytest tests/test_109_us1_gateway_mode.py tests/test_controlplane_verify.py -q
    ................
    20 passed in 4.42s

Interview transcript, external mode:

.. code-block:: text

    llm mode (gateway) [gateway]:   <- 'gateway'
    gateway mode (external|managed) [external]:   <- 'external'
    llm gateway base_url [http://127.0.0.1:4000]:   <- 'http://127.0.0.1:1/v1'
    llm gateway master key env-var name [ERGANE_LLM_MASTER_KEY]:   <- 'ERGANE_LLM_MASTER_KEY'
    memory backend (hindsight|none) [none]:   <- 'none'
    temporal mode (external|managed) [external]:   <- 'external'
    temporal address [127.0.0.1:7233]:   <- '127.0.0.1:4'
    temporal namespace [ergane]:   <- 'ergane'
    temporal api key env-var name (optional):   <- '-'
    temporal TLS enabled (true|false) [false]:   <- 'false'
    telemetry OTLP endpoint (optional):   <- ''
    escalation adapter (telegram|none) [telegram]:   <- 'none'

    wrote /tmp/.../external.toml

    [llm]
    mode = "gateway"
    base_url = "http://127.0.0.1:1/v1"
    master_key_env = "ERGANE_LLM_MASTER_KEY"

Interview transcript, managed mode:

.. code-block:: text

    llm mode (gateway) [gateway]:   <- 'gateway'
    gateway mode (external|managed) [external]:   <- 'managed'
    llm gateway master key env-var name [ERGANE_LLM_MASTER_KEY]:   <- 'ERGANE_LLM_MASTER_KEY'
    memory backend (hindsight|none) [none]:   <- 'none'
    temporal mode (external|managed) [external]:   <- 'external'
    temporal address [127.0.0.1:7233]:   <- '127.0.0.1:4'
    temporal namespace [ergane]:   <- 'ergane'
    temporal api key env-var name (optional):   <- '-'
    temporal TLS enabled (true|false) [false]:   <- 'false'
    telemetry OTLP endpoint (optional):   <- ''
    escalation adapter (telegram|none) [telegram]:   <- 'none'

    wrote /tmp/.../managed.toml

    [llm]
    mode = "gateway"
    gateway_mode = "managed"
    base_url = "http://gateway:4000"
    master_key_env = "ERGANE_LLM_MASTER_KEY"

Full suite (after implementation):

.. code-block:: text

    $ uv run pytest -q
    4953 passed, 56 skipped, 6 warnings in 356.69s (0:05:56)
"""

from __future__ import annotations

import io
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pytest

import factory.cli.init as init_module
import factory.cli.install as install_module
import factory.cli.main as main_module
import factory.controlplane.verify as verify_module
from factory.cli.errors import EXIT_USER
from factory.controlplane.config import (
    RULE_UNKNOWN_LLM_MODE,
    ControlPlaneConfig,
    ControlPlaneConfigError,
    load_controlplane_config,
    parse_controlplane_config,
    render_controlplane_config,
    render_controlplane_document,
)

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
    """Run `main(argv)` capturing stdout/stderr."""
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


class ScriptedPrompter:
    """Answers the install interview from a list, recording every question."""

    def __init__(self, answers: list[str]) -> None:
        self.answers = list(answers)
        self.asked: list[tuple[str, str | None, str | None]] = []

    def ask(
        self, prompt: str, *, default: str | None = None, error: str | None = None
    ) -> str:
        self.asked.append((prompt, default, error))
        if not self.answers:
            raise AssertionError(
                f"prompter ran out of answers at {prompt!r}; asked so far: "
                f"{[a[0] for a in self.asked]}"
            )
        return self.answers.pop(0)


@pytest.fixture
def config_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An isolated control-plane config path for this test."""
    path = tmp_path / "ergane" / "config.toml"
    monkeypatch.setenv("ERGANE_CONFIG_PATH", str(path))
    monkeypatch.setenv("FACTORY_CONFIG_PATH", str(path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    return path


@pytest.fixture
def xdg_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An isolated XDG_CONFIG_HOME."""
    home = tmp_path / "xdg"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    return home


@pytest.fixture(autouse=True)
def _stub_persona_step_and_scan(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep these tests focused on the gateway question.

    The persona step and closing demonstration are tested elsewhere; the LLM scan
    is disabled so the offered default is deterministic.
    """
    monkeypatch.setattr(install_module, "_interview_personas", lambda _p, _d, _pp: None)
    monkeypatch.setattr(install_module, "_closing_demonstration", lambda *_a, **_k: None)
    monkeypatch.setattr(install_module, "_scan_endpoints", lambda: [])


#: Minimal answers after the LLM block; shared by both gateway modes.
_TAIL_ANSWERS: list[str] = [
    "none",  # memory backend
    "external",  # temporal mode
    "127.0.0.1:4",  # temporal address
    "ergane",  # temporal namespace
    "-",  # temporal api key env-var name (cleared)
    "false",  # temporal TLS enabled
    "",  # telemetry OTLP endpoint (optional)
    "none",  # escalation adapter
]


def _external_answers() -> list[str]:
    return [
        "gateway",  # llm mode
        "external",  # gateway mode
        "http://127.0.0.1:1/v1",  # llm gateway base_url
        "ERGANE_LLM_MASTER_KEY",  # llm gateway master key env-var name
        *_TAIL_ANSWERS,
    ]


def _managed_answers() -> list[str]:
    return [
        "gateway",  # llm mode
        "managed",  # gateway mode
        "ERGANE_LLM_MASTER_KEY",  # llm gateway master key env-var name
        *_TAIL_ANSWERS,
    ]


# ---------------------------------------------------------------------------
# T001 [US1-S1, FR-001] the interview asks gateway mode and accepts both answers
# ---------------------------------------------------------------------------


def test_interview_asks_gateway_mode_and_accepts_external_and_managed(
    config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-001: the install interview asks `gateway mode (external|managed)`.

    Both answers are accepted, proven by running the interview twice and reading
    the written config back.  The shape mirrors `_ask_temporal`.
    """
    prompts_seen: list[str] = []

    def run(answers: list[str]) -> ControlPlaneConfig:
        prompter = ScriptedPrompter(answers)
        monkeypatch.setattr(init_module, "_prompter_factory", lambda: prompter)
        result = _invoke(["install"])
        prompts_seen.extend(prompt for prompt, _default, _error in prompter.asked)
        assert result.code == EXIT_USER, (
            "verification is expected to fail on closed ports, but the interview "
            f"must finish: {result.stderr}"
        )
        return load_controlplane_config(str(config_path))

    external = run(_external_answers())
    assert external.llm.mode == "gateway"
    assert external.llm.gateway is not None
    assert external.llm.gateway.gateway_mode == "external"
    assert external.llm.gateway.base_url == "http://127.0.0.1:1/v1"
    assert external.llm.gateway.master_key_env == "ERGANE_LLM_MASTER_KEY"

    managed = run(_managed_answers())
    assert managed.llm.mode == "gateway"
    assert managed.llm.gateway is not None
    assert managed.llm.gateway.gateway_mode == "managed"
    assert managed.llm.gateway.base_url == "http://gateway:4000"
    assert managed.llm.gateway.master_key_env == "ERGANE_LLM_MASTER_KEY"

    # The question itself uses the same grammar as `_ask_temporal`.
    gateway_prompts = [
        prompt for prompt in prompts_seen if "gateway mode (external|managed)" in prompt
    ]
    assert len(gateway_prompts) >= 2, f"expected the gateway-mode question twice, got {prompts_seen}"


# ---------------------------------------------------------------------------
# T002 [P] [US1-S2, FR-002, FR-006] regression guard
# ---------------------------------------------------------------------------


def test_external_gateway_mode_renders_identically_to_pre_us1_output(
    config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-002: `gateway_mode = "external"` is the implicit default and is omitted.

    A config written by the post-US1 interview for the same external answers is
    byte-identical to the canonical rendering of a pre-US1 config that carried
    no `gateway_mode` key.
    """
    prompter = ScriptedPrompter(_external_answers())
    monkeypatch.setattr(init_module, "_prompter_factory", lambda: prompter)
    result = _invoke(["install"])
    assert result.code == EXIT_USER

    written = config_path.read_text(encoding="utf-8")
    expected = render_controlplane_config(
        parse_controlplane_config(
            "\n".join(
                [
                    "version = 1",
                    "",
                    '[llm]',
                    'mode = "gateway"',
                    'base_url = "http://127.0.0.1:1/v1"',
                    'master_key_env = "ERGANE_LLM_MASTER_KEY"',
                    "",
                    '[memory]',
                    'backend = "none"',
                    "",
                    '[temporal]',
                    'mode = "external"',
                    'address = "127.0.0.1:4"',
                    'namespace = "ergane"',
                    "",
                    '[telemetry]',
                    "",
                    '[escalation]',
                    'adapter = "none"',
                ]
            ),
            source="fixture",
        )
    )
    assert written == expected, f"external mode leaked a new key:\n{written}\n!=\n{expected}"


def test_gateway_mode_is_not_a_third_llm_mode() -> None:
    """FR-006: this story adds a mode to the gateway, not a third `llm.mode`.

    The parsed config still carries `llm.mode = "gateway"` for both external and
    managed gateway modes, and an unknown `llm.mode` is still refused.
    """
    managed = parse_controlplane_config(
        "\n".join(
            [
                "version = 1",
                "",
                '[llm]',
                'mode = "gateway"',
                'gateway_mode = "managed"',
                'base_url = "http://gateway:4000"',
                'master_key_env = "ERGANE_LLM_MASTER_KEY"',
                "",
                '[memory]',
                'backend = "none"',
                "",
                '[temporal]',
                'mode = "external"',
                'address = "127.0.0.1:4"',
                'namespace = "ergane"',
                "",
                '[telemetry]',
                "",
                '[escalation]',
                'adapter = "none"',
            ]
        ),
        source="fixture",
    )
    assert managed.llm.mode == "gateway"
    assert managed.llm.gateway is not None
    assert managed.llm.gateway.gateway_mode == "managed"

    external = parse_controlplane_config(
        "\n".join(
            [
                "version = 1",
                "",
                '[llm]',
                'mode = "gateway"',
                'base_url = "http://127.0.0.1:1/v1"',
                'master_key_env = "ERGANE_LLM_MASTER_KEY"',
                "",
                '[memory]',
                'backend = "none"',
                "",
                '[temporal]',
                'mode = "external"',
                'address = "127.0.0.1:4"',
                'namespace = "ergane"',
                "",
                '[telemetry]',
                "",
                '[escalation]',
                'adapter = "none"',
            ]
        ),
        source="fixture",
    )
    assert external.llm.mode == "gateway"
    assert external.llm.gateway is not None
    assert external.llm.gateway.gateway_mode == "external"

    with pytest.raises(ControlPlaneConfigError) as refusal:
        parse_controlplane_config(
            "\n".join(
                [
                    "version = 1",
                    "",
                    '[llm]',
                    'mode = "managed"',
                    'base_url = "http://gateway:4000"',
                    'master_key_env = "ERGANE_LLM_MASTER_KEY"',
                    "",
                    '[memory]',
                    'backend = "none"',
                    "",
                    '[temporal]',
                    'mode = "external"',
                    'address = "127.0.0.1:4"',
                    'namespace = "ergane"',
                    "",
                    '[escalation]',
                    'adapter = "none"',
                ]
            ),
            source="fixture",
        )
    assert refusal.value.rule == RULE_UNKNOWN_LLM_MODE
    assert "managed" in refusal.value.problem


def test_unknown_gateway_mode_is_refused_at_entry() -> None:
    """A gateway mode other than external|managed fails closed with a stable rule."""
    with pytest.raises(ControlPlaneConfigError) as refusal:
        parse_controlplane_config(
            "\n".join(
                [
                    "version = 1",
                    "",
                    '[llm]',
                    'mode = "gateway"',
                    'gateway_mode = "hybrid"',
                    'base_url = "http://127.0.0.1:1/v1"',
                    'master_key_env = "ERGANE_LLM_MASTER_KEY"',
                    "",
                    '[memory]',
                    'backend = "none"',
                    "",
                    '[temporal]',
                    'mode = "external"',
                    'address = "127.0.0.1:4"',
                    'namespace = "ergane"',
                    "",
                    '[escalation]',
                    'adapter = "none"',
                ]
            ),
            source="fixture",
        )
    assert "gateway_mode" in refusal.value.field or "gateway_mode" in refusal.value.problem
    assert "hybrid" in refusal.value.problem


# ---------------------------------------------------------------------------
# T003 [P] [US1-S3, FR-003, FR-004] from-file managed mode
# ---------------------------------------------------------------------------


def test_from_file_accepts_managed_gateway_mode(
    config_path: Path,
    xdg_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """FR-003/FR-004: an answers file selecting `managed` is accepted.

    The written config records the bundled address and the managed lifecycle,
    and the documented example answer file carries the new key.
    """
    answer_file = tmp_path / "answers.toml"
    answer_file.write_text(
        "\n".join(
            [
                'version = 1',
                "",
                '[llm]',
                'mode = "gateway"',
                'gateway_mode = "managed"',
                "",
                '[memory]',
                'backend = "none"',
                "",
                '[temporal]',
                'mode = "external"',
                'address = "127.0.0.1:4"',
                'namespace = "ergane"',
                "",
                '[escalation]',
                'adapter = "none"',
            ]
        ),
        encoding="utf-8",
    )

    result = _invoke(["install", "--from-file", str(answer_file)])
    assert result.code == EXIT_USER, (
        "verification fails on closed ports, but the config must be written first: "
        f"{result.stderr}"
    )

    config = load_controlplane_config(str(config_path))
    assert config.llm.mode == "gateway"
    assert config.llm.gateway is not None
    assert config.llm.gateway.gateway_mode == "managed"
    assert config.llm.gateway.base_url == "http://gateway:4000"

    # The documented example answer file carries the key so a demo can copy it.
    example = REPO_ROOT / "docs" / "ergane-install-answer.example.toml"
    example_text = example.read_text(encoding="utf-8")
    assert 'gateway_mode = "external"' in example_text


# ---------------------------------------------------------------------------
# T004 [P] [US1-S4, FR-005] probe parity across gateway modes
# ---------------------------------------------------------------------------


class _RecordingLiteLLMClient:
    """Records the key-management calls the LLM probe makes."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def _record(self, name: str, *args: Any, **kwargs: Any) -> Any:
        self.calls.append((name, args, kwargs))

    async def issue_key(
        self,
        *,
        key_alias: str,
        models: list[str],
        metadata: dict[str, Any] | None = None,
        ttl: str | None = None,
    ) -> str:
        self._record("issue_key", key_alias=key_alias, models=models, metadata=metadata, ttl=ttl)
        return "sk-probe-managed" if "managed" in str(metadata) else "sk-probe-external"

    async def get_key_info(self, key: str) -> dict[str, Any]:
        self._record("get_key_info", key=key)
        return {
            "key": key,
            "info": {
                "key_alias": "verify-probe",
                "models": ["fixture/model"],
                "metadata": {},
                "spend": 0.0,
            },
        }

    async def fetch_spend_log_rows(self, key: str, *, issued_at: str) -> list[dict[str, Any]]:
        self._record("fetch_spend_log_rows", key=key, issued_at=issued_at)
        return []

    async def revoke_key_by_tokens(self, keys: list[str]) -> bool:
        self._record("revoke_key_by_tokens", keys=keys)
        return True

    async def aclose(self) -> None:
        self._record("aclose")


@pytest.mark.asyncio
async def test_key_management_probe_runs_identically_for_external_and_managed_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-005: mint, constrain, spend logs, revoke — for both modes.

    A managed gateway earns its green the same way an external one does.
    """
    external_cfg = parse_controlplane_config(
        render_controlplane_document(
            {
                "version": 1,
                "llm": {
                    "mode": "gateway",
                    "gateway_mode": "external",
                    "base_url": "http://external.gateway:4000",
                    "master_key_env": "ERGANE_LLM_MASTER_KEY",
                },
                "memory": {"backend": "none"},
                "temporal": {"mode": "external", "address": "127.0.0.1:4", "namespace": "ergane"},
                "telemetry": {},
                "escalation": {"adapter": "none"},
            }
        ),
        source="fixture",
    )
    managed_cfg = parse_controlplane_config(
        render_controlplane_document(
            {
                "version": 1,
                "llm": {
                    "mode": "gateway",
                    "gateway_mode": "managed",
                    "base_url": "http://gateway:4000",
                    "master_key_env": "ERGANE_LLM_MASTER_KEY",
                },
                "memory": {"backend": "none"},
                "temporal": {"mode": "external", "address": "127.0.0.1:4", "namespace": "ergane"},
                "telemetry": {},
                "escalation": {"adapter": "none"},
            }
        ),
        source="fixture",
    )

    # A registry with one non-example alias so the probe reaches key management.
    fake_registry: dict[str, Any] = {
        "implementer": type("P", (), {
            "model": "fixture/model",
            "fallback": None,
            "routes_through_gateway": True,
        })(),
    }

    def _fake_load_personas() -> dict[str, Any]:
        return fake_registry

    monkeypatch.setattr(verify_module, "_load_personas_for_probe", _fake_load_personas)
    monkeypatch.setenv("ERGANE_LLM_MASTER_KEY", "sk-fake-master")

    for label, cfg in (("external", external_cfg), ("managed", managed_cfg)):
        client = _RecordingLiteLLMClient()

        def _factory(_llm: ControlPlaneConfig.LLM) -> _RecordingLiteLLMClient:
            return client

        monkeypatch.setattr(verify_module, "_llm_client_factory", _factory)

        snapshot = await verify_module.LLMProbe().gather(cfg)
        assert "minted" in snapshot.detail.lower() and "constrained" in snapshot.detail.lower(), (
            f"{label}: expected key-management probe detail, got {snapshot.detail!r}"
        )

        call_names = [name for name, _args, _kwargs in client.calls]
        assert "issue_key" in call_names, f"{label}: probe did not mint a key"
        assert "get_key_info" in call_names, f"{label}: probe did not confirm key properties"
        assert "fetch_spend_log_rows" in call_names, f"{label}: probe did not read spend logs"
        assert "revoke_key_by_tokens" in call_names, f"{label}: probe did not revoke in finally"
        assert "aclose" in call_names, f"{label}: client was not closed"
