"""055-US2: `llm.mode = "direct"` parses, dispatches, and says what it gave up.

The 048-US2 refusal is now a supported mode. These tests prove the new shape:

- `direct` parses with a `base_url` and `api_key_env` (FR-006).
- `issue_attempt_key` still runs and still writes the ledger row; it returns the
  declared static credential instead of minting a virtual key (FR-007).
- The three surrendered properties are stated at declaration time (FR-008).
- `ergane usage` reports that attribution is unavailable rather than returning an
  empty rollup (FR-009).
- `personas.yaml`'s stated invariant matches the modes the config admits (FR-011).
- The declared credential is redacted from errors, logs and rendered output
  (FR-010).
- The surrendered-properties text has exactly one definition and is rendered
  by the interview, the config error and the docs (SC-003).

Every test binds the config path explicitly (FR-012) — through the
`config_path` fixture imported from the 033 walkthrough tests — so nothing reaches
an operator's real `~/.config/ergane/config.toml`.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from factory.activities.usage_activities import IssueKeyInput, issue_attempt_key
from factory.cli.usage import usage_command
from factory.controlplane.config import (
    KNOWN_LL_MODES,
    RULE_UNKNOWN_LLM_MODE,
    ControlPlaneConfig,
    ControlPlaneConfigError,
    controlplane_document,
    parse_controlplane_config,
    render_controlplane_document,
)
from factory.usage import ledger
from factory.usage.litellm_client import LiteLLMClient
from factory.usage.models import Termination

# The 033 harness. Fixtures are imported here.
from tests.test_ergane_install_walkthrough import (  # noqa: F401
    GATEWAY_ANSWERS,
    Run,
    ScriptedPrompter,
    _invoke,
    config_path,
    walkthrough,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SHIPPED_REGISTRY = REPO_ROOT / "personas.yaml"

DIRECT_CREDENTIAL = "sk-direct-credential-not-for-logs"
DIRECT_CREDENTIAL_ENV = "ERGANE_DIRECT_LLM_KEY"

#: A minimal direct-mode config with a base URL and an API key env var.
DIRECT_CONFIG = f"""\
version = 1

[llm]
mode = "direct"
base_url = "http://127.0.0.1:1/v1"
api_key_env = "{DIRECT_CREDENTIAL_ENV}"

[memory]
backend = "none"

[temporal]
mode = "external"
address = "127.0.0.1:4"
namespace = "ergane"

[telemetry]

[escalation]
adapter = "telegram"
"""

DIRECT_LLM_BLOCK = """\
mode = "direct"
base_url = "http://127.0.0.1:1/v1"
api_key_env = "ERGANE_DIRECT_LLM_KEY"
"""


def _load_config(source: str = DIRECT_CONFIG) -> ControlPlaneConfig:
    return parse_controlplane_config(source, source="fixture.toml")


# ---------------------------------------------------------------------------
# T012 / US2-S1 — direct parses and carries a direct block
# ---------------------------------------------------------------------------


def test_direct_mode_parses_with_base_url_and_api_key_env_var() -> None:
    """FR-006: a direct config carries the two declared values."""
    cfg = _load_config()

    assert cfg.llm.mode == "direct"
    assert cfg.llm.direct is not None
    assert cfg.llm.direct.base_url == "http://127.0.0.1:1/v1"
    assert cfg.llm.direct.api_key_env == DIRECT_CREDENTIAL_ENV


def test_known_llm_modes_unchanged() -> None:
    """The token list does not widen; 'direct' stays recognized."""
    assert KNOWN_LL_MODES == ("gateway", "direct")


def test_unknown_mode_still_refused() -> None:
    """Recognized-but-supported must stay distinct from unsupported."""
    text = DIRECT_CONFIG.replace('mode = "direct"', 'mode = "sidecar"')
    with pytest.raises(ControlPlaneConfigError) as excinfo:
        parse_controlplane_config(text, source="fixture.toml")

    assert excinfo.value.rule == RULE_UNKNOWN_LLM_MODE
    assert "sidecar" in excinfo.value.problem


def test_direct_config_renders_round_trip() -> None:
    """Rendering a parsed direct config produces a parseable direct config."""
    cfg = _load_config()
    document = controlplane_document(cfg)
    rendered = render_controlplane_document(document)
    reparsed = parse_controlplane_config(rendered, source="rendered.toml")

    assert reparsed.llm.mode == "direct"
    assert reparsed.llm.direct == cfg.llm.direct


# ---------------------------------------------------------------------------
# T013 / US2-S2 — issue_attempt_key still runs, returns the declared credential,
# and writes the ledger row
# ---------------------------------------------------------------------------


@pytest.fixture
def direct_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """A ledger path and an environment with the declared direct credential set."""
    ledger_path = tmp_path / "ledger.db"
    monkeypatch.setenv("ERGANE_LEDGER_PATH", str(ledger_path))
    monkeypatch.setenv(DIRECT_CREDENTIAL_ENV, DIRECT_CREDENTIAL)
    return ledger_path


async def test_issue_attempt_key_returns_declared_credential_and_writes_row(
    direct_env: Path,
    config_path: Path,
) -> None:
    """FR-007: the activity is not skipped; the ledger records the attempt."""
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(DIRECT_CONFIG, encoding="utf-8")
    cfg = _load_config()
    request = IssueKeyInput(
        node_id="us2",
        epic_id="055-the-gateway-is-a-choice-with-a-scan",
        attempt=1,
        persona="implementer",
        spec_ref="specs/055-the-gateway-is-a-choice-with-a-scan/spec.md",
        models=["anthropic/CHANGEME"],
    )

    from factory.activities.usage_activities import teardown_attempt, TeardownInput

    lease = await issue_attempt_key(request)

    assert lease.key == DIRECT_CREDENTIAL
    assert lease.key_alias == "055-the-gateway-is-a-choice-with-a-scan:us2:1:implementer"

    # The activity that opens every attempt must still be paired with teardown,
    # which writes the ledger row. Direct mode has no proxy to revoke.
    await teardown_attempt(
        TeardownInput(lease=lease, termination=Termination.COMPLETED)
    )

    conn = ledger.connect(direct_env)
    try:
        rows = conn.execute(
            "SELECT epic_id, node_id, attempt, persona, spec_ref, key_alias, "
            "prompt_tokens, completion_tokens, cache_read_tokens, cache_write_tokens, "
            "request_count, spend_usd, final_usage_confirmed, termination "
            "FROM usage_records WHERE key_alias = ?",
            (lease.key_alias,),
        ).fetchall()
    finally:
        conn.close()

    assert len(rows) == 1
    row = rows[0]
    assert row[:5] == (
        request.epic_id,
        request.node_id,
        request.attempt,
        request.persona,
        request.spec_ref,
    )
    assert row[5] == lease.key_alias
    # Direct mode has no proxy to report token or spend detail.
    assert row[6] is None
    assert row[7] is None
    assert row[8] is None
    assert row[9] is None
    assert row[10] is None
    assert row[11] is None
    assert row[12] == 0  # final_usage_confirmed
    assert row[13] == Termination.COMPLETED.value


async def test_issue_attempt_key_for_gateway_still_mints(
    litellm_env: Any,  # noqa: ANN401 - conftest fixture
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Gateway mode is unchanged: a virtual key is minted at the proxy."""
    # Ensure no direct-mode config is visible to this gateway test by writing a
    # gateway config to the session config path the activity reads.
    import factory.controlplane.resolve as resolve_module
    import factory.activities.usage_activities as usage_activities

    session_config = Path(resolve_module.resolve_config_path())
    session_config.parent.mkdir(parents=True, exist_ok=True)
    session_config.write_text(
        """\
version = 1

[llm]
mode = "gateway"
base_url = "http://127.0.0.1:1/v1"
master_key_env = "LITELLM_MASTER_KEY"

[memory]
backend = "none"
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("ERGANE_LEDGER_PATH", str(tmp_path / "gateway.db"))
    monkeypatch.setenv("LITELLM_PROXY_URL", litellm_env.base_url)
    monkeypatch.setenv("LITELLM_MASTER_KEY", litellm_env.master_key)
    monkeypatch.setattr(
        usage_activities,
        "open_client",
        lambda: LiteLLMClient.from_env(transport=litellm_env.transport),
    )
    request = IssueKeyInput(
        node_id="us2",
        epic_id="055-the-gateway-is-a-choice-with-a-scan",
        attempt=1,
        persona="implementer",
        spec_ref="specs/055-the-gateway-is-a-choice-with-a-scan/spec.md",
        models=["anthropic/CHANGEME"],
    )

    lease = await issue_attempt_key(request)

    assert lease.key != DIRECT_CREDENTIAL
    assert lease.key.startswith("sk-")


# ---------------------------------------------------------------------------
# T014 / US2-S3 — the three surrendered properties are named at declaration time
# ---------------------------------------------------------------------------


SURRENDERED_PROPERTIES = (
    "credential is neither per-attempt nor expiring",
    "persona-to-model binding is advisory",
    "Spend attribution is unavailable: there is no LiteLLM proxy",
)


def test_surrendered_properties_are_named_in_direct_block() -> None:
    """FR-008: the degradation text is reachable from the parsed config."""
    cfg = _load_config()

    assert cfg.llm.mode == "direct"
    text = cfg.llm.direct.surrendered_properties_text
    for phrase in SURRENDERED_PROPERTIES:
        assert phrase in text, f"missing surrendered property: {phrase!r}"


def test_surrendered_properties_text_has_exactly_three_bullets() -> None:
    """SC-003: the list of what direct gives up is bounded and enumerable."""
    cfg = _load_config()
    text = cfg.llm.direct.surrendered_properties_text

    # Exactly three declarative sentences, each naming one surrendered property.
    assert len(re.findall(r"^-\s+", text, flags=re.MULTILINE)) == 3
    for phrase in SURRENDERED_PROPERTIES:
        assert phrase in text


# ---------------------------------------------------------------------------
# T015 / US2-S4 — ergane usage reports attribution unavailable in direct mode
# ---------------------------------------------------------------------------


async def test_ergane_usage_reports_attribution_unavailable_in_direct_mode(
    direct_env: Path,
    config_path: Path,
) -> None:
    """FR-009: an inapplicable rollup is reported, not hidden as an empty table."""
    from factory.activities.usage_activities import teardown_attempt, TeardownInput

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(DIRECT_CONFIG, encoding="utf-8")
    request = IssueKeyInput(
        node_id="us2",
        epic_id="055-the-gateway-is-a-choice-with-a-scan",
        attempt=1,
        persona="implementer",
        spec_ref="specs/055-the-gateway-is-a-choice-with-a-scan/spec.md",
        models=["anthropic/CHANGEME"],
    )
    lease = await issue_attempt_key(request)
    await teardown_attempt(
        TeardownInput(lease=lease, termination=Termination.COMPLETED)
    )

    args = type("Args", (), {"db": direct_env, "by": "persona", "epic": None, "since": None, "as_json": False})()
    import io, contextlib

    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        usage_command(args)
    rendered = captured.getvalue()

    assert "attribution is unavailable" in rendered.lower()
    assert "TOTAL" not in rendered


async def test_ergane_usage_json_reports_attribution_unavailable_in_direct_mode(
    direct_env: Path,
    config_path: Path,
) -> None:
    """The JSON output shape also carries the unavailable message."""
    from factory.activities.usage_activities import teardown_attempt, TeardownInput

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(DIRECT_CONFIG, encoding="utf-8")
    request = IssueKeyInput(
        node_id="us2",
        epic_id="055-the-gateway-is-a-choice-with-a-scan",
        attempt=1,
        persona="implementer",
        spec_ref="specs/055-the-gateway-is-a-choice-with-a-scan/spec.md",
        models=["anthropic/CHANGEME"],
    )
    lease = await issue_attempt_key(request)
    await teardown_attempt(
        TeardownInput(lease=lease, termination=Termination.COMPLETED)
    )

    args = type("Args", (), {"db": direct_env, "by": "persona", "epic": None, "since": None, "as_json": True})()
    import io, contextlib

    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        usage_command(args)
    rendered = captured.getvalue()

    assert "attribution is unavailable" in rendered.lower()


# ---------------------------------------------------------------------------
# T016 / US2-S5 — personas.yaml header matches the modes the config admits
# ---------------------------------------------------------------------------


def test_personas_yaml_header_matches_admitted_modes() -> None:
    """FR-011: the registry no longer claims enforceability unconditionally."""
    header = SHIPPED_REGISTRY.read_text(encoding="utf-8").split("# Current wiring")[0]
    assert "gateway" in header
    assert "direct" in header
    # It must not claim the binding is enforceable without qualification.
    assert "enforceable, not advisory" not in header
    assert "advisory" in header or "enforceable only" in header


# ---------------------------------------------------------------------------
# T017 / US2-S6 — the declared credential is redacted from observable output
# ---------------------------------------------------------------------------


def _scrubbing_client() -> LiteLLMClient:
    """A client that would echo the credential if redaction failed."""
    return LiteLLMClient(
        base_url="http://127.0.0.1:1/v1",
        master_key=DIRECT_CREDENTIAL,
    )


def test_litellm_client_scrubs_direct_credential_from_error() -> None:
    """FR-010: the credential is removed from any LiteLLMError message."""
    client = _scrubbing_client()
    raw = f"connection refused: {DIRECT_CREDENTIAL}"
    scrubbed = client._scrub(raw)
    assert DIRECT_CREDENTIAL not in scrubbed
    assert "<redacted>" in scrubbed


def test_litellm_client_repr_does_not_expose_credential() -> None:
    """Even repr/repr-like output must not leak the credential."""
    client = _scrubbing_client()
    assert DIRECT_CREDENTIAL not in repr(client)


def test_rendered_config_does_not_contain_credential_value() -> None:
    """The rendered TOML keeps the env-var name, not the credential value."""
    cfg = _load_config()
    rendered = render_controlplane_document(controlplane_document(cfg))
    assert DIRECT_CREDENTIAL not in rendered
    assert DIRECT_CREDENTIAL_ENV in rendered


# ---------------------------------------------------------------------------
# T018 / SC-003 — one definition, three renderings
# ---------------------------------------------------------------------------


def test_surrendered_properties_source_is_single_module_constant() -> None:
    """The three sentences live in one module-level constant."""
    from factory.controlplane.config import DIRECT_MODE_SURRENDERED_PROPERTIES_TEXT

    text = DIRECT_MODE_SURRENDERED_PROPERTIES_TEXT
    for phrase in SURRENDERED_PROPERTIES:
        assert phrase in text
    assert len(re.findall(r"^-\s+", text, flags=re.MULTILINE)) == 3


def test_config_error_renders_surrendered_properties_from_source() -> None:
    """The parser's direct block carries the same text as the source constant."""
    from factory.controlplane.config import DIRECT_MODE_SURRENDERED_PROPERTIES_TEXT

    cfg = _load_config()
    assert cfg.llm.direct.surrendered_properties_text == DIRECT_MODE_SURRENDERED_PROPERTIES_TEXT


