"""Tests for `ergane install --requirements` (063-US3).

The command prints what the gateway must serve: every distinct `model` and
`fallback` alias from the persona registry, excluding personas declared
`agent: none`, plus the key-management endpoints the gateway must answer.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path
from typing import Any

import pytest

import factory.cli.main as main_module
import factory.controlplane.verify as verify_module
from factory.config import DETERMINISTIC_AGENT, Persona, WriteScope


#: A small fixture registry with distinct models, fallbacks, and one deterministic
#: persona that must contribute no alias.
FIXTURE_PERSONAS: dict[str, Persona] = {
    "architect": Persona(
        name="architect",
        agent="claude-code",
        model="proxy/model-a",
        fallback="proxy/fallback-a",
        skills=(),
        write_scope=WriteScope.WORKTREE,
        needs_worktree=True,
    ),
    "implementer": Persona(
        name="implementer",
        agent="claude-code",
        model="proxy/model-b",
        fallback="proxy/fallback-a",  # shared with architect
        skills=(),
        write_scope=WriteScope.WORKTREE,
        needs_worktree=True,
    ),
    "verifier": Persona(
        name="verifier",
        agent=DETERMINISTIC_AGENT,
        model=None,
        fallback=None,
        skills=(),
        write_scope=WriteScope.READ,
        needs_worktree=True,
    ),
    "subscription": Persona(
        name="subscription",
        agent="subscription",
        model="claude-opus-5",
        fallback=None,
        skills=(),
        write_scope=WriteScope.WORKTREE,
        needs_worktree=True,
    ),
}


#: The distinct gateway aliases that FIXTURE_PERSONAS resolves to.
FIXTURE_ALIASES = {"proxy/model-a", "proxy/model-b", "proxy/fallback-a"}


def _invoke(argv: list[str]) -> tuple[int, str, str]:
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
    return code, buf_out.getvalue(), buf_err.getvalue()


@pytest.fixture
def fixture_registry_path(tmp_path: Path) -> Path:
    """A personas.yaml on disk that the resolver can reach."""
    path = tmp_path / "personas.yaml"
    lines: list[str] = [
        "architect:",
        "  agent: claude-code",
        "  model: proxy/model-a",
        "  fallback: proxy/fallback-a",
        "  skills: []",
        "  write_scope: worktree",
        "  needs_worktree: true",
        "",
        "implementer:",
        "  agent: claude-code",
        "  model: proxy/model-b",
        "  fallback: proxy/fallback-a",
        "  skills: []",
        "  write_scope: worktree",
        "  needs_worktree: true",
        "",
        "verifier:",
        "  agent: none",
        "  model: null",
        "  fallback: null",
        "  skills: []",
        "  write_scope: read",
        "  needs_worktree: true",
        "",
        "subscription:",
        "  agent: subscription",
        "  model: claude-opus-5",
        "  fallback: null",
        "  skills: []",
        "  write_scope: worktree",
        "  needs_worktree: true",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# T017 [P] [US3-S1] `--requirements` prints every distinct model and fallback alias
# ---------------------------------------------------------------------------


def test_requirements_prints_distinct_gateway_aliases(
    fixture_registry_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """US3-S1 / FR-009: the output lists every distinct model and fallback alias."""
    monkeypatch.setenv("ERGANE_PERSONAS_PATH", str(fixture_registry_path))
    monkeypatch.setenv("FACTORY_PERSONAS_PATH", str(fixture_registry_path))

    code, stdout, stderr = _invoke(["install", "--requirements"])

    with capsys.disabled():
        print("\n--- requirements output ---")
        print(stdout)
        print("--- end requirements output ---")

    assert code == 0, stderr
    output = stdout.lower()
    for alias in FIXTURE_ALIASES:
        assert alias in stdout, f"expected alias {alias!r} in output"
    # Distinct: the shared fallback appears once conceptually; we assert the set.
    found_aliases = set()
    for line in stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("proxy/"):
            found_aliases.add(stripped.split()[0])
    assert found_aliases == FIXTURE_ALIASES


# ---------------------------------------------------------------------------
# T018 [P] [US3-S2] the output names the key-management endpoints
# ---------------------------------------------------------------------------


def test_requirements_names_key_management_endpoints(
    fixture_registry_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """US3-S2 / FR-009: the output names the gateway endpoints Ergane must answer."""
    monkeypatch.setenv("ERGANE_PERSONAS_PATH", str(fixture_registry_path))
    monkeypatch.setenv("FACTORY_PERSONAS_PATH", str(fixture_registry_path))

    code, stdout, stderr = _invoke(["install", "--requirements"])

    with capsys.disabled():
        print("\n--- requirements output ---")
        print(stdout)
        print("--- end requirements output ---")

    assert code == 0, stderr
    assert "POST /key/generate" in stdout
    assert "GET /key/info" in stdout
    assert "GET /spend/logs/v2" in stdout


# ---------------------------------------------------------------------------
# T019 [P] [US3-S3] personas declared `agent: none` contribute no alias
# ---------------------------------------------------------------------------


def test_requirements_ignores_agent_none_persona(
    fixture_registry_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US3-S3 / trap 9: deterministic personas have no model and add no alias."""
    monkeypatch.setenv("ERGANE_PERSONAS_PATH", str(fixture_registry_path))
    monkeypatch.setenv("FACTORY_PERSONAS_PATH", str(fixture_registry_path))

    code, stdout, _stderr = _invoke(["install", "--requirements"])
    assert code == 0
    assert "verifier" not in stdout, "agent:none persona name leaked into alias output"
    assert "null" not in stdout, "null alias leaked into output"


# ---------------------------------------------------------------------------
# T020 [P] [US3-S4] `--requirements` and `--verify` resolve identical alias sets
# ---------------------------------------------------------------------------


def test_requirements_and_verify_resolve_identical_alias_sets(
    fixture_registry_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US3-S4 / FR-010: both commands derive aliases from the same function."""
    monkeypatch.setenv("ERGANE_PERSONAS_PATH", str(fixture_registry_path))
    monkeypatch.setenv("FACTORY_PERSONAS_PATH", str(fixture_registry_path))

    # The shared derivation function is the source of truth.
    registry = FIXTURE_PERSONAS
    derived = verify_module.gather_gateway_aliases(registry)
    expected = set(derived)

    _, stdout, _ = _invoke(["install", "--requirements"])
    requirements_aliases = set()
    for line in stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("proxy/"):
            requirements_aliases.add(stripped.split()[0])

    assert requirements_aliases == expected, (
        f"--requirements aliases {requirements_aliases} do not match "
        f"shared derivation {expected}"
    )


# ---------------------------------------------------------------------------
# T021 [P] [US3 Edge] no configured registry prints guidance naming resolution order
# ---------------------------------------------------------------------------


def test_requirements_with_example_registry_prints_configuration_guidance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Edge: example aliases mean the registry is unconfigured; output names the path
    and the resolution order (env override, XDG/HOME default, packaged default)."""
    example_path = tmp_path / "personas.yaml"
    example_path.write_text(
        "architect:\n"
        "  agent: claude-code\n"
        "  model: example/your-architect-model\n"
        "  fallback: example/your-fallback-model\n"
        "  skills: []\n"
        "  write_scope: docs\n"
        "  needs_worktree: true\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ERGANE_PERSONAS_PATH", str(example_path))
    monkeypatch.setenv("FACTORY_PERSONAS_PATH", str(example_path))

    code, stdout, stderr = _invoke(["install", "--requirements"])

    with capsys.disabled():
        print("\n--- example-registry output ---")
        print(stdout)
        print("stderr:", stderr)
        print("--- end example-registry output ---")

    assert code != 0, "an unconfigured registry must refuse, not print empty requirements"
    output = stdout + stderr
    assert "ERGANE_PERSONAS_PATH" in output
    assert "FACTORY_PERSONAS_PATH" in output
    assert "XDG_CONFIG_HOME" in output
    assert str(example_path) in output


# ---------------------------------------------------------------------------
# T022 [P] [US3 trap 8] `--requirements` mints no key and issues no completion
# ---------------------------------------------------------------------------


class _NoLLMCallsClient:
    """A fake LiteLLM client that fails loudly if any proxy API is touched."""

    async def issue_key(self, **kwargs: Any) -> str:
        raise AssertionError("--requirements must not mint a key")

    async def get_key_info(self, key: str) -> dict[str, Any]:
        raise AssertionError("--requirements must not query key info")

    async def fetch_spend_log_rows(self, key: str, *, issued_at: str) -> list[dict[str, Any]]:
        raise AssertionError("--requirements must not read spend logs")

    async def revoke_key_by_tokens(self, keys: list[str]) -> bool:
        raise AssertionError("--requirements must not revoke a key")

    async def chat_completion(self, request: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError("--requirements must not issue a completion")

    async def aclose(self) -> None:
        pass


def test_requirements_mints_no_key_and_issues_no_completion(
    fixture_registry_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Trap 8: `--requirements` is read-only; it must not exercise the gateway."""
    monkeypatch.setenv("ERGANE_PERSONAS_PATH", str(fixture_registry_path))
    monkeypatch.setenv("FACTORY_PERSONAS_PATH", str(fixture_registry_path))
    monkeypatch.setattr(
        verify_module, "_llm_client_factory", lambda _config: _NoLLMCallsClient()
    )

    code, stdout, stderr = _invoke(["install", "--requirements"])

    assert code == 0, stderr
    assert "[PASS]" not in stdout and "[FAIL]" not in stdout
    assert "mint" not in stdout.lower()
    assert "completion" not in stdout.lower()
