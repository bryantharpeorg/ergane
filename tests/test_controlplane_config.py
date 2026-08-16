"""Tests for the control-plane config parser (US1 of 033-ergane-install).

The evidence rule (constitution VIII) says runtime claims must be met by tool
output pasted verbatim into a comment block in the test file. After the first
run the suite output will be pasted below.

Suite output (to be filled after first run):

"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import pytest

from factory.controlplane.config import (
    KNOWN_ESC_ADAPTERS,
    KNOWN_LL_MODES,
    KNOWN_MEMORY_BACKENDS,
    load_controlplane_config,
    render_controlplane_config,
    resolve_config_path,
)
from factory.controlplane.config import ControlPlaneConfig as Cfg
from factory.controlplane.config import ControlPlaneConfigError
from factory.env import (
    ERGANE_CONFIG_PATH_ENV,
    FACTORY_CONFIG_PATH_ENV,
)


#: The `[llm]` block this file's canonical config used to carry. Kept verbatim
#: rather than deleted: 048-US2 changed the verdict on this text, not the text,
#: and `test_direct_llm_mode_refused` below is the same input with the opposite
#: expectation.
_DIRECT_LLM_BLOCK = """\
mode = "direct"

[[llm.persona]]
name = "implementer"
base_url = "http://llm.local/v1"
model = "openai/gpt-4o"
api_key_env = "ERGANE_LLM_IMPLEMENTER_KEY"
"""

_GATEWAY_LLM_BLOCK = """\
mode = "gateway"
base_url = "http://llm.local/v1"
master_key_env = "ERGANE_LLM_MASTER_KEY"
"""


def _happy_toml() -> str:
    """The canonical full config from US1-S1, in the one mode that dispatches."""
    return f"""
version = 1

[llm]
{_GATEWAY_LLM_BLOCK}
[memory]
backend = "hindsight"
url = "http://hindsight.local:8888"
api_key_env = "ERGANE_HINDSIGHT_KEY"

[temporal]
mode = "external"
address = "temporal.local:7233"
namespace = "ergane"
api_key_env = "ERGANE_TEMPORAL_API_KEY"

[telemetry]
otlp_endpoint = "http://otel.local:4317"

[escalation]
adapter = "telegram"
chat_id_env = "ERGANE_TELEGRAM_CHAT_ID"
bot_token_env = "ERGANE_TELEGRAM_BOT_TOKEN"
""".lstrip()


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


def test_resolve_config_path_uses_xdg_config_home(tmp_path: Path) -> None:
    """FR-001: the default path lives under XDG_CONFIG_HOME."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    cfg_home = fake_home / ".config"
    cfg_home.mkdir()
    env = dict(os.environ)
    env["HOME"] = str(fake_home)
    env["XDG_CONFIG_HOME"] = str(cfg_home)
    env.pop("ERGANE_CONFIG_PATH", None)
    env.pop("FACTORY_CONFIG_PATH", None)

    import subprocess

    script = """
import os
from factory.controlplane.config import resolve_config_path
print(resolve_config_path())
"""
    result = subprocess.run(
        ["python", "-c", script],
        env=env,
        text=True,
        capture_output=True,
        cwd=str(tmp_path),
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(cfg_home / "ergane" / "config.toml")


# ---------------------------------------------------------------------------
# T001 [US1-S1] Happy parse
# ---------------------------------------------------------------------------


def test_happy_parse(tmp_path: Path) -> None:
    """US1-S1: a version 1 config with every subsystem parses to typed shape."""
    path = tmp_path / "config.toml"
    path.write_text(_happy_toml(), encoding="utf-8")

    cfg = load_controlplane_config(path)

    assert isinstance(cfg, Cfg)
    assert cfg.version == 1
    assert cfg.llm.mode == "gateway"
    assert cfg.llm.gateway == Cfg.LLMGateway(
        base_url="http://llm.local/v1",
        master_key_env="ERGANE_LLM_MASTER_KEY",
    )

    assert cfg.memory.backend == "hindsight"
    assert cfg.memory.url == "http://hindsight.local:8888"
    assert cfg.memory.api_key_env == "ERGANE_HINDSIGHT_KEY"

    assert cfg.temporal.mode == "external"
    assert cfg.temporal.address == "temporal.local:7233"
    assert cfg.temporal.namespace == "ergane"
    assert cfg.temporal.api_key_env == "ERGANE_TEMPORAL_API_KEY"

    assert cfg.telemetry.mode == "otlp"
    assert cfg.telemetry.otlp_endpoint == "http://otel.local:4317"

    assert cfg.escalation.adapter == "telegram"
    assert cfg.escalation.chat_id_env == "ERGANE_TELEGRAM_CHAT_ID"
    assert cfg.escalation.bot_token_env == "ERGANE_TELEGRAM_BOT_TOKEN"

    # Defaults that were not declared
    assert cfg.llm.timeout_s == 300
    assert cfg.memory.timeout_s == 5
    assert cfg.temporal.tls_enabled is False
    assert cfg.temporal.timeout_s == 5
    assert cfg.telemetry.timeout_s == 5
    assert cfg.escalation.timeout_s == 30
    # 041 FR-011: an undeclared responder list is unrestricted, which is what
    # every 008 deployment is — Telegram's single chat *was* the identity, so a
    # default that refused every reply would take the operator channel down.
    assert cfg.escalation.authorized_responders == ()


# ---------------------------------------------------------------------------
# T002 [US1-S2 / FR-005] One namespace
# ---------------------------------------------------------------------------


def test_temporal_namespace_list_refused(tmp_path: Path) -> None:
    """US1-S2: a list of namespaces is refused naming the one-namespace rule."""
    path = tmp_path / "config.toml"
    text = _happy_toml().replace(
        'namespace = "ergane"',
        "namespace = [\"ergane\", \"other\"]",
    )
    path.write_text(text, encoding="utf-8")

    with pytest.raises(ControlPlaneConfigError) as exc_info:
        load_controlplane_config(path)

    err = exc_info.value
    assert err.rule == "temporal_namespace_not_scalar"
    assert "one namespace" in err.problem.lower()
    assert "workflow id" in err.problem.lower()


# ---------------------------------------------------------------------------
# T003 [US1-S3 / FR-003] Secret-shape refusals
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("llm.master_key_env", "sk-this-is-a-key-value"),
        ("escalation.bot_token_env", "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"),
    ],
)
def test_secret_shaped_value_refused(field: str, bad_value: str, tmp_path: Path) -> None:
    """US1-S3: any secret field carrying a credential shape is refused."""
    path = tmp_path / "config.toml"
    text = _happy_toml()
    if field == "llm.master_key_env":
        text = text.replace(
            'master_key_env = "ERGANE_LLM_MASTER_KEY"',
            f'master_key_env = "{bad_value}"',
        )
    elif field == "escalation.bot_token_env":
        text = text.replace(
            'bot_token_env = "ERGANE_TELEGRAM_BOT_TOKEN"',
            f'bot_token_env = "{bad_value}"',
        )
    path.write_text(text, encoding="utf-8")

    with pytest.raises(ControlPlaneConfigError) as exc_info:
        load_controlplane_config(path)

    err = exc_info.value
    assert err.rule == "secret_value_not_reference"
    assert err.field in (field, "master_key_env")


def test_identifier_value_accepted(tmp_path: Path) -> None:
    """US1-S3: an identifier-shaped env-var name is accepted."""
    path = tmp_path / "config.toml"
    path.write_text(_happy_toml(), encoding="utf-8")
    cfg = load_controlplane_config(path)
    assert cfg.llm.gateway is not None
    assert cfg.llm.gateway.master_key_env == "ERGANE_LLM_MASTER_KEY"
    assert cfg.escalation.bot_token_env == "ERGANE_TELEGRAM_BOT_TOKEN"


# ---------------------------------------------------------------------------
# T004 [US1-S4] Unknown adapter
# ---------------------------------------------------------------------------


def test_unknown_escalation_adapter_refused(tmp_path: Path) -> None:
    """US1-S4: an unregistered escalation adapter is refused and known ones listed."""
    path = tmp_path / "config.toml"
    text = _happy_toml().replace('adapter = "telegram"', 'adapter = "signal"')
    path.write_text(text, encoding="utf-8")

    with pytest.raises(ControlPlaneConfigError) as exc_info:
        load_controlplane_config(path)

    err = exc_info.value
    assert err.rule == "unknown_escalation_adapter"
    assert "signal" in err.problem
    for adapter in KNOWN_ESC_ADAPTERS:
        assert adapter in err.problem


# ---------------------------------------------------------------------------
# T027a [041-US4 / FR-011] `escalation.authorized_responders` — the field 033
# was assumed to have landed and did not (a repo-wide grep on 2026-08-16 found
# the name only in 041's spec, plan and tasks). Added with the parser's own
# conventions: a wrong type is `field_type`, the slug every block already uses.
# ---------------------------------------------------------------------------


def test_authorized_responders_parses_to_a_tuple_of_identities(tmp_path: Path) -> None:
    """FR-011's list, in the spelling both transports report identities in."""
    path = tmp_path / "config.toml"
    path.write_text(
        _happy_toml() + 'authorized_responders = ["@bryan", "4242"]\n',
        encoding="utf-8",
    )

    cfg = load_controlplane_config(path)

    assert cfg.escalation.authorized_responders == ("@bryan", "4242")


@pytest.mark.parametrize(
    "declared",
    ['"@bryan"', "[]", '["@bryan", 42]', '["@bryan", ""]'],
    ids=["a-bare-string", "an-empty-list", "a-non-string", "an-empty-string"],
)
def test_a_malformed_responder_list_is_refused(declared: str, tmp_path: Path) -> None:
    """A list that cannot be an identity list is refused, never coerced.

    `[]` is refused rather than read as unrestricted: whoever typed one meant to
    restrict something, and granting everyone is the one reading they cannot
    have meant. Omitting the key says unrestricted, and is a different keystroke.
    """
    path = tmp_path / "config.toml"
    path.write_text(
        _happy_toml() + f"authorized_responders = {declared}\n", encoding="utf-8"
    )

    with pytest.raises(ControlPlaneConfigError) as exc_info:
        load_controlplane_config(path)

    assert exc_info.value.rule == "field_type"
    assert exc_info.value.field == "escalation.authorized_responders"


def test_a_responder_list_survives_the_render_round_trip(tmp_path: Path) -> None:
    """A field that parses and is dropped on write is worse than no field.

    Not hypothetical: `EscalationRecord.check_evidence` reached the outgoing
    message and never the store for three weeks, added on one side of a round
    trip. `ergane install` re-renders from the typed shape, so an unrendered
    list is one re-run from gone.
    """
    path = tmp_path / "config.toml"
    path.write_text(
        _happy_toml() + 'authorized_responders = ["@bryan", "4242"]\n',
        encoding="utf-8",
    )
    parsed = load_controlplane_config(path)

    rendered = tmp_path / "rendered.toml"
    rendered.write_text(render_controlplane_config(parsed), encoding="utf-8")

    assert load_controlplane_config(rendered).escalation == parsed.escalation


# ---------------------------------------------------------------------------
# T005 [US1-S5 / FR-013] Fail closed with no config file
# ---------------------------------------------------------------------------


def test_no_config_file_fails_closed(tmp_path: Path) -> None:
    """US1-S5: absence of the config file fails closed naming ergane install."""
    missing = tmp_path / "config.toml"

    with pytest.raises(ControlPlaneConfigError) as exc_info:
        load_controlplane_config(missing)

    err = exc_info.value
    assert err.rule == "config_missing"
    assert "ergane install" in err.problem.lower()


def test_load_from_default_path_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-013: commands that need the control plane fail closed when default path missing."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty-config"))
    monkeypatch.delenv(ERGANE_CONFIG_PATH_ENV, raising=False)
    monkeypatch.delenv(FACTORY_CONFIG_PATH_ENV, raising=False)

    with pytest.raises(ControlPlaneConfigError) as exc_info:
        load_controlplane_config()

    err = exc_info.value
    assert err.rule == "config_missing"
    assert "ergane install" in err.problem.lower()


# ---------------------------------------------------------------------------
# T006 [US1-S6 / FR-004] Managed mode refused before 042
# ---------------------------------------------------------------------------


def test_temporal_managed_mode_refused(tmp_path: Path) -> None:
    """US1-S6: temporal.mode = managed is refused naming 042."""
    path = tmp_path / "config.toml"
    text = _happy_toml().replace('mode = "external"', 'mode = "managed"')
    path.write_text(text, encoding="utf-8")

    with pytest.raises(ControlPlaneConfigError) as exc_info:
        load_controlplane_config(path)

    err = exc_info.value
    assert err.rule == "temporal_managed_not_implemented"
    assert "042" in err.problem


# ---------------------------------------------------------------------------
# 048-US2 — direct mode refused, the same shape one subsystem over
# ---------------------------------------------------------------------------


def test_direct_llm_mode_refused(tmp_path: Path) -> None:
    """048-US2 / FR-008: the config this file's fixture used to be is now refused.

    The text is unchanged — a complete `[[llm.persona]]` block that parsed to a
    `direct` LLM block until this story, which is what makes the refusal the new
    rule firing rather than an incidental "persona block missing". What moved is
    the verdict.
    """
    path = tmp_path / "config.toml"
    text = _happy_toml().replace(_GATEWAY_LLM_BLOCK, _DIRECT_LLM_BLOCK)
    path.write_text(text, encoding="utf-8")

    with pytest.raises(ControlPlaneConfigError) as exc_info:
        load_controlplane_config(path)

    err = exc_info.value
    assert err.rule == "llm_direct_not_supported"
    assert "virtual key" in err.problem
    assert "gateway" in err.problem


# ---------------------------------------------------------------------------
# Additional closed-set refusals
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["proxy", "local"])
def test_unknown_llm_mode_refused(mode: str, tmp_path: Path) -> None:
    text = _happy_toml().replace('mode = "gateway"', f'mode = "{mode}"')
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")

    with pytest.raises(ControlPlaneConfigError) as exc_info:
        load_controlplane_config(path)

    assert exc_info.value.rule == "unknown_llm_mode"
    assert mode in exc_info.value.problem
    for known in KNOWN_LL_MODES:
        assert known in exc_info.value.problem


@pytest.mark.parametrize("backend", ["postgres", "redis"])
def test_unknown_memory_backend_refused(backend: str, tmp_path: Path) -> None:
    text = _happy_toml().replace('backend = "hindsight"', f'backend = "{backend}"')
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")

    with pytest.raises(ControlPlaneConfigError) as exc_info:
        load_controlplane_config(path)

    assert exc_info.value.rule == "unknown_memory_backend"
    assert backend in exc_info.value.problem
    for known in KNOWN_MEMORY_BACKENDS:
        assert known in exc_info.value.problem


def test_top_level_unknown_key_refused(tmp_path: Path) -> None:
    text = "version = 1\nfoo = true\n" + _happy_toml().split("\n", 1)[1]
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")

    with pytest.raises(ControlPlaneConfigError) as exc_info:
        load_controlplane_config(path)

    assert exc_info.value.rule == "unknown_key"
    assert "foo" in exc_info.value.problem


def test_missing_version_refused(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(_happy_toml().replace("version = 1\n", ""), encoding="utf-8")

    with pytest.raises(ControlPlaneConfigError) as exc_info:
        load_controlplane_config(path)

    assert exc_info.value.rule == "version"
