"""Tests for US2 of 062-the-registry-belongs-to-the-operator.

The packaged `personas.yaml` is a neutral example, `ergane install` seeds the
operator's own copy at `~/.config/ergane/personas.yaml`, and an unconfigured
registry is reported as one actionable condition rather than one gateway fault
per placeholder alias.
"""

from __future__ import annotations

import asyncio
import io
import os
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pytest
import yaml

import factory.cli.init as init_module
import factory.cli.main as main_module
import factory.config as config_module
import factory.controlplane.verify as verify_module
from factory.cli.errors import EXIT_USER
from factory.config import DETERMINISTIC_AGENT, Persona, WriteScope

REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"
SHIPPED_REGISTRY = REPO_ROOT / "personas.yaml"
EXAMPLE_REGISTRY = REPO_ROOT / "personas.example.yaml"


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
    """Answers the install interview from a list, in order."""

    def __init__(self, answers: list[str]) -> None:
        self.answers = list(answers)

    def ask(
        self, prompt: str, *, default: str | None = None, error: str | None = None
    ) -> str:
        if not self.answers:
            raise AssertionError(f"prompter ran out of answers for: {prompt!r}")
        return self.answers.pop(0)


@pytest.fixture
def config_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The control-plane config path for this test, isolated from the host."""
    path = tmp_path / "ergane" / "config.toml"
    monkeypatch.setenv("ERGANE_CONFIG_PATH", str(path))
    monkeypatch.setenv("FACTORY_CONFIG_PATH", str(path))
    return path


@pytest.fixture
def xdg_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An isolated XDG_CONFIG_HOME for this test."""
    home = tmp_path / "xdg"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    return home


#: The full gateway-mode interview, in the order the walkthrough asks.
#: All network addresses are closed loopback ports so verify fails fast.
GATEWAY_ANSWERS: list[str] = [
    "gateway",  # llm mode
    "external",  # gateway mode (external|managed)
    "http://127.0.0.1:1/v1",  # llm gateway base_url
    "ERGANE_LLM_MASTER_KEY",  # llm gateway master key env-var name
    "none",  # memory backend
    "external",  # temporal mode
    "127.0.0.1:4",  # temporal address
    "ergane",  # temporal namespace
    "-",  # temporal api key env-var name (cleared)
    "false",  # temporal TLS enabled
    "",  # telemetry OTLP endpoint (optional)
    "none",  # escalation adapter
]


# ---------------------------------------------------------------------------
# T011 / T012: the packaged registry is a neutral, documented example
# ---------------------------------------------------------------------------


def _build_wheel(tmp_path: Path) -> Path:
    """Build a wheel from a clean copy of the repo and return its path."""
    copy_root = tmp_path / "repo"
    subprocess.run(
        ["git", "checkout-index", "-a", "-f", "--prefix", f"{copy_root}/"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    shutil.copy2(PYPROJECT, copy_root / "pyproject.toml")
    shutil.copy2(REPO_ROOT / "personas.example.yaml", copy_root / "personas.example.yaml")
    env = os.environ.copy()
    env["PYTHONPATH"] = ""
    env.pop("VIRTUAL_ENV", None)
    uv = shutil.which("uv")
    assert uv
    subprocess.run(
        [uv, "build", "--wheel", "--out-dir", "dist"],
        cwd=copy_root,
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    wheels = list((copy_root / "dist").glob("*.whl"))
    assert len(wheels) == 1, wheels
    return wheels[0]


def _wheel_personas_text(whl: Path) -> str:
    with zipfile.ZipFile(whl) as zf:
        names = [n for n in zf.namelist() if n.endswith("factory/personas.yaml")]
        assert len(names) == 1, names
        return zf.read(names[0]).decode("utf-8")


@pytest.fixture
def built_wheel(tmp_path: Path) -> Path:
    return _build_wheel(tmp_path)


def test_packaged_registry_contains_no_deployment_specific_aliases(
    built_wheel: Path,
) -> None:
    """T011: the wheel's personas.yaml must not ship one operator's wiring."""
    text = _wheel_personas_text(built_wheel)
    for prefix in ("ollama-cloud/", "local/", "anthropic/"):
        assert prefix not in text, f"packaged registry contains {prefix!r}"
    for name in ("Bryan", "bryan"):
        assert name not in text, f"packaged registry names operator {name!r}"
    for marker in ("2026-08-06", "homelab"):
        assert marker not in text.lower(), f"packaged registry contains {marker!r}"


def test_packaged_registry_documents_shape_and_placeholders(
    built_wheel: Path,
) -> None:
    """T012: the wheel's personas.yaml explains what a persona is and that aliases
    are placeholders the operator must replace."""
    text = _wheel_personas_text(built_wheel)
    lowered = text.lower()
    assert "placeholders the operator must replace" in lowered
    assert "persona" in lowered
    assert "agent" in lowered
    assert "model" in lowered
    assert "write_scope" in lowered
    assert "needs_worktree" in lowered
    assert "timeout" in lowered


# ---------------------------------------------------------------------------
# T013 / T014: install seeds the operator copy
# ---------------------------------------------------------------------------


@pytest.fixture
def walkthrough(
    monkeypatch: pytest.MonkeyPatch, config_path: Path, xdg_home: Path
) -> Callable[..., Run]:
    """Run `ergane install` with a scripted prompter."""

    def runner(answers: list[str] | None = None) -> Run:
        prompter = ScriptedPrompter(answers if answers is not None else list(GATEWAY_ANSWERS))
        monkeypatch.setattr(init_module, "_prompter_factory", lambda: prompter)
        monkeypatch.delenv("TEMPORAL_ADDRESS", raising=False)
        monkeypatch.delenv("TEMPORAL_NAMESPACE", raising=False)
        return _invoke(["install"])

    return runner


def test_install_seeds_personas_registry_when_absent(
    config_path: Path, xdg_home: Path, walkthrough: Callable[..., Run]
) -> None:
    """T013: `ergane install` writes ~/.config/ergane/personas.yaml and reports it."""
    personas_path = xdg_home / "ergane" / "personas.yaml"
    assert personas_path.exists() is False

    result = walkthrough()

    assert personas_path.is_file(), result.stderr
    # The seeded content is the shipped example and parses.
    registry = yaml.safe_load(personas_path.read_text(encoding="utf-8"))
    assert isinstance(registry, dict)
    assert "implementer" in registry
    assert result.stdout.count(str(personas_path)) >= 1, result.stdout


def test_install_does_not_overwrite_existing_personas_registry(
    config_path: Path, xdg_home: Path, walkthrough: Callable[..., Run]
) -> None:
    """T014: a re-run leaves an existing operator registry untouched."""
    personas_path = xdg_home / "ergane" / "personas.yaml"
    personas_path.parent.mkdir(parents=True, exist_ok=True)
    personas_path.write_text(
        yaml.safe_dump({"implementer": {"model": "operator/kept-model"}}),
        encoding="utf-8",
    )
    original = personas_path.read_bytes()

    walkthrough()

    assert personas_path.read_bytes() == original


# ---------------------------------------------------------------------------
# T015: unconfigured registry is one condition, not one fault per alias
# ---------------------------------------------------------------------------


def _config() -> Cfg:
    """Build a minimal gateway-mode control-plane config."""
    from factory.controlplane.config import parse_controlplane_config

    toml = (
        "version = 1\n"
        "\n"
        "[llm]\n"
        'mode = "gateway"\n'
        'base_url = "http://llm.test/v1"\n'
        'master_key_env = "ERGANE_LLM_MASTER_KEY"\n'
        "\n"
        "[memory]\n"
        'backend = "none"\n'
        "\n"
        "[temporal]\n"
        'mode = "managed"\n'
        "\n"
        "[telemetry]\n"
        "\n"
        "[escalation]\n"
        'adapter = "none"\n'
    )
    return parse_controlplane_config(toml, source="test-config")


def _placeholder_persona(name: str) -> Persona:
    return Persona(
        name=name,
        agent="claude-code",
        model="example/your-model",
        fallback="example/your-fallback",
        skills=(),
        write_scope=WriteScope.WORKTREE,
        needs_worktree=True,
        timeout_s=3600,
    )


@pytest.mark.asyncio
async def test_verify_reports_unconfigured_registry_as_one_condition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T015: placeholder-only registry produces one llm finding naming the file."""
    registry_path = Path("/home/example/.config/ergane/personas.yaml")
    registry = {
        "implementer": _placeholder_persona("implementer"),
        "judge": _placeholder_persona("judge"),
    }
    monkeypatch.setattr(verify_module, "_load_personas_for_probe", lambda: registry)
    monkeypatch.setattr(
        verify_module, "_resolve_registry_path_for_probe", lambda: registry_path
    )
    monkeypatch.setenv("ERGANE_LLM_MASTER_KEY", "sk-fake")

    probe = verify_module.LLMProbe()
    snapshot = await probe.gather(_config())
    finding = probe.evaluate(snapshot)

    assert finding.passed is False, finding.detail
    assert "registry" in finding.detail.lower()
    assert "not been configured" in finding.detail.lower()
    assert str(registry_path) in finding.detail
    # The failure is one condition, not a per-alias fault list.
    assert "example/your-model" not in finding.detail
    assert "example/your-fallback" not in finding.detail


# ---------------------------------------------------------------------------
# T016: this repository's own registry still resolves
# ---------------------------------------------------------------------------


def test_repo_root_registry_still_resolves_real_wiring_in_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T016: with no operator override, the checkout resolves the repo's own
    personas.yaml so factory work against this repository uses the real wiring.
    """
    monkeypatch.delenv("ERGANE_PERSONAS_PATH", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

    resolved = config_module.resolve_default_registry_path()
    assert resolved == SHIPPED_REGISTRY

    registry = config_module.load_personas()
    # The repo's real wiring still resolves. Assert that it LOADS, not which
    # vendor it names: pinning the alias here makes the operator's own dial
    # untouchable, which is `ci/test-suite-pins-the-operator-dial` — the same
    # defect 037 un-pinned for `context_window`, recurring on `model` when the
    # implementer was pointed at Opus 5 on 2026-08-19.
    #
    # The rule below the comment now matches the rule inside it: an alias-shape
    # check (`"/" in ...model`) stood here until 122-US1 and was a vendor
    # decision in a format check's clothing — every gateway alias carries a
    # slash and no `agent: subscription` model does, so it refused a persona the
    # registry already ships. What remains catches the defect that is real: an
    # implementer entry that resolves no model to route work to.
    # `tests/test_122_registry_is_not_pinned.py` drives this check against a
    # gateway, a subscription and an unresolvable registry, and fails if any
    # assertion in this suite starts constraining a vendor or route again.
    assert registry["implementer"].model


# ---------------------------------------------------------------------------
# T017: unwritable XDG_CONFIG_HOME is reported
# ---------------------------------------------------------------------------


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file permission bits")
def test_install_reports_unwritable_config_home(
    config_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    walkthrough: Callable[..., Run],
) -> None:
    """T017: an unwritable XDG_CONFIG_HOME fails naming the personas path, not
    by writing inside the package."""
    unwritable = tmp_path / "unwritable"
    unwritable.mkdir(parents=True)
    unwritable.chmod(0o000)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(unwritable))

    try:
        result = walkthrough()
    finally:
        unwritable.chmod(0o755)

    assert result.code == EXIT_USER
    personas_path = unwritable / "ergane" / "personas.yaml"
    assert str(personas_path) in result.stdout or str(personas_path) in result.stderr
    assert not personas_path.exists()
    # Nothing fell back into the package directory.
    assert not (REPO_ROOT / "factory" / "personas.yaml").exists()
