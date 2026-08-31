"""119-US1: the declared Temporal mode reaches the layout, or the verb refuses.

Written before the implementation (T001-T005), against the shape T006-T008 add:

- `declared_temporal_mode` reads `temporal.mode` out of the control-plane config
  and refuses naming the file it could not read. It is the caller's half.
- `resolve_layout` takes the mode as an argument, like every other parameter it
  has, and never reads configuration itself (plan trap 2) — there is a test
  below that binds a managed declaration at the env var the config resolver
  honours and asserts the resolver ignores it.
- A layout nobody declared a mode for is refused where the mode decides an
  outcome, rather than read as external (plan trap 3). External is the mode
  whose failure looks like the operator's own Temporal being down, which is how
  this defect survived three patches.

Every test binds every path it touches under `tmp_path`: none of them may read
the operator's own `~/.config/ergane/config.toml`, which exists on this host and
not on the grader's.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pytest

from factory.cli.errors import OperatorError
from factory.env import ERGANE_CONFIG_PATH_ENV, FACTORY_CONFIG_PATH_ENV
from factory.supervision.units import (
    BRIDGE_UNIT,
    PROBE_TIMER,
    PROBE_UNIT,
    SLICE_UNIT,
    TEMPORAL_UNIT,
    WORKER_TEMPLATE_UNIT,
    WRAPPER_NAME,
    InstallLayout,
    _temporal_managed,
    declared_layout,
    declared_temporal_mode,
    generated_files,
    resolve_layout,
)

#: The `[temporal]` body of a managed declaration. Managed mode takes no address
#: and no namespace — the parser returns on the mode alone
#: (`factory/controlplane/config.py:447`), so this is the whole block.
MANAGED_BLOCK = 'mode = "managed"'

#: The external declaration, which needs both of the values managed mode has no
#: operator input for.
EXTERNAL_BLOCK = """\
mode = "external"
address = "declared.temporal.test:7233"
namespace = "declared-namespace"\
"""


def _write_config(tmp_path: Path, *, temporal: str) -> Path:
    """A complete config at a bound path, declaring `temporal` and nothing else.

    All five blocks, since the parser requires all five; only the `[temporal]`
    body varies between the tests below.
    """
    path = tmp_path / "config.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""\
version = 1

[llm]
mode = "gateway"
base_url = "http://declared.gateway.test/v1"
master_key_env = "DECLARED_KEY_VAR"

[memory]
backend = "none"

[temporal]
{temporal}

[telemetry]

[escalation]
adapter = "telegram"
chat_id_env = "DECLARED_CHAT_ID"
bot_token_env = "DECLARED_BOT_TOKEN"
""",
        encoding="utf-8",
    )
    return path


def _installation(tmp_path: Path) -> dict[str, Path]:
    """Every path `resolve_layout` would otherwise derive from the real host."""
    home = tmp_path / "home"
    interpreter = home / "code/ergane/.venv/bin/python3"
    interpreter.parent.mkdir(parents=True)
    interpreter.touch()
    return {
        "home": home,
        "install_root": home / "code/ergane",
        "interpreter": interpreter,
        "unit_dir": home / ".config/systemd/user",
        "generated_dir": home / ".local/state/ergane/supervision",
    }


def _names(layout: InstallLayout) -> set[str]:
    return {generated.name for generated in generated_files(layout)}


# --- T001 [US1-S1 / FR-001] the declared mode reaches the layout ---------------


def test_a_managed_declaration_reaches_the_layout(tmp_path: Path) -> None:
    """US1-S1: an install declaring managed resolves a layout carrying managed.

    The whole defect in one assertion: before this story `resolve_layout` had no
    parameter for the mode, so this layout carried the dataclass default and the
    operator's declaration reached nothing.
    """
    config = _write_config(tmp_path, temporal=MANAGED_BLOCK)

    layout = declared_layout(config_path=config, **_installation(tmp_path))

    assert layout.temporal_mode == "managed"


def test_worker_install_resolves_the_layout_from_the_declaration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US1-S1 at the verb: the caller that knows the mode is the one that passes it.

    `install` is stubbed because the subject here is which layout the verb
    resolves, not what systemd does with it.
    """
    import factory.cli.nouns.worker as worker

    config = _write_config(tmp_path, temporal=MANAGED_BLOCK)
    monkeypatch.setenv(ERGANE_CONFIG_PATH_ENV, str(config))
    monkeypatch.setattr(worker, "_require_systemd_user_session", lambda: None)

    seen: dict[str, InstallLayout] = {}

    class _Report:
        def render(self) -> str:
            return ""

    def _fake_install(layout: InstallLayout, **_: Any) -> _Report:
        seen["layout"] = layout
        return _Report()

    monkeypatch.setattr(worker, "install", _fake_install)
    worker._install(argparse.Namespace(env_command=None))

    assert seen["layout"].temporal_mode == "managed"


# --- T002 [US1-S2 / FR-002] the managed layout generates the server unit -------


def test_the_managed_layout_generates_the_temporal_server_unit(
    tmp_path: Path,
) -> None:
    """US1-S2: with the mode carried, generation needs no change to follow it."""
    config = _write_config(tmp_path, temporal=MANAGED_BLOCK)
    layout = declared_layout(config_path=config, **_installation(tmp_path))

    assert TEMPORAL_UNIT in _names(layout)


# --- T003 [US1-S3 / FR-002] the control: external stays working ---------------


def test_an_external_declaration_carries_external_and_writes_no_temporal_unit(
    tmp_path: Path,
) -> None:
    """US1-S3: the working path stays working, file set unchanged."""
    config = _write_config(tmp_path, temporal=EXTERNAL_BLOCK)
    layout = declared_layout(config_path=config, **_installation(tmp_path))

    assert layout.temporal_mode == "external"
    names = _names(layout)
    assert TEMPORAL_UNIT not in names
    assert names == {
        SLICE_UNIT,
        WORKER_TEMPLATE_UNIT,
        BRIDGE_UNIT,
        PROBE_UNIT,
        PROBE_TIMER,
        WRAPPER_NAME,
    }


# --- T004 [US1-S4 / FR-003, plan trap 3] undeterminable is refused ------------


def test_a_missing_declaration_is_refused_naming_the_file(tmp_path: Path) -> None:
    """US1-S4: no config, no layout — and the refusal names the file it wanted."""
    missing = tmp_path / "nowhere" / "config.toml"

    with pytest.raises(OperatorError) as refused:
        declared_layout(config_path=missing, **_installation(tmp_path))

    assert str(missing) in str(refused.value)
    assert "temporal.mode" in str(refused.value)


def test_a_declaration_without_a_mode_is_refused_naming_the_file(
    tmp_path: Path,
) -> None:
    """US1-S4: a `[temporal]` block with no `mode` is undeterminable too."""
    config = _write_config(tmp_path, temporal="")

    with pytest.raises(OperatorError) as refused:
        declared_temporal_mode(config)

    assert str(config) in str(refused.value)
    assert "temporal.mode" in str(refused.value)


def test_an_undeterminable_declaration_does_not_default_to_external(
    tmp_path: Path,
) -> None:
    """US1-S4, plan trap 3: the refusal replaces the default, it does not join it.

    A fallback to external here is the behaviour that made this defect survive
    three patches: external mode fails by not finding a server, which reads as
    the operator's own Temporal being down.
    """
    missing = tmp_path / "nowhere" / "config.toml"

    with pytest.raises(OperatorError):
        declared_temporal_mode(missing)


def test_a_layout_nobody_declared_a_mode_for_is_refused_at_generation(
    tmp_path: Path,
) -> None:
    """US1-S4: the backstop, for a layout resolved without a mode at all.

    It carries neither mode — not "external" — and asking what to generate for
    it refuses naming the declaration that was never made.
    """
    layout = resolve_layout(**_installation(tmp_path))

    assert layout.temporal_mode != "external"
    assert layout.temporal_mode != "managed"
    with pytest.raises(OperatorError) as refused:
        generated_files(layout)
    assert "temporal.mode" in str(refused.value)


def test_a_mode_that_is_not_a_mode_is_refused_naming_the_value(
    tmp_path: Path,
) -> None:
    """FR-003: a typo is refused where it is passed, not carried into generation."""
    with pytest.raises(OperatorError) as refused:
        resolve_layout(temporal_mode="managd", **_installation(tmp_path))

    assert "managd" in str(refused.value)
    assert "managed" in str(refused.value)


def test_resolve_layout_does_not_read_the_declaration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Plan trap 2: the resolver resolves from its arguments and the filesystem.

    A managed declaration bound at the variable the config resolver honours does
    not reach a layout resolved with `external` passed in — which is what keeps
    `resolve_layout` testable without a config loader, and keeps supervision
    uncoupled from the control plane.
    """
    config = _write_config(tmp_path, temporal=MANAGED_BLOCK)
    monkeypatch.setenv(ERGANE_CONFIG_PATH_ENV, str(config))

    layout = resolve_layout(temporal_mode="external", **_installation(tmp_path))

    assert layout.temporal_mode == "external"


# --- T005 [US1-S5 / FR-004, plan trap 4] the docstring is a test --------------


def test_temporal_managed_is_true_exactly_for_a_declared_managed_layout(
    tmp_path: Path,
) -> None:
    """US1-S5: the first claim the docstring makes, asserted.

    `_temporal_managed` reports what the layout carries, and the layout carries
    what the declaration said — both directions, from a real declaration.
    """
    paths = _installation(tmp_path)
    managed = declared_layout(
        config_path=_write_config(tmp_path / "m", temporal=MANAGED_BLOCK), **paths
    )
    external = declared_layout(
        config_path=_write_config(tmp_path / "e", temporal=EXTERNAL_BLOCK), **paths
    )

    assert _temporal_managed(managed) is True
    assert _temporal_managed(external) is False


def test_temporal_managed_refuses_a_layout_that_declares_nothing(
    tmp_path: Path,
) -> None:
    """US1-S5: the second claim — an undeclared mode is refused, not read as false."""
    with pytest.raises(OperatorError):
        _temporal_managed(resolve_layout(**_installation(tmp_path)))


def test_the_docstring_names_the_mechanism_that_exists(tmp_path: Path) -> None:
    """US1-S5, plan trap 4: prose and code cannot drift again.

    The three tests above assert the behaviour; this one holds the prose to
    naming that behaviour's parts, and to no longer claiming the default that
    was the defect — `ergane worker install` never "defaulted to managed".
    """
    doc = _temporal_managed.__doc__ or ""

    assert "temporal_mode" in doc
    assert "declared_temporal_mode" in doc
    assert "defaults to managed" not in doc


@pytest.fixture(autouse=True)
def _no_inherited_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test here reads a config it did not write.

    `scripts/ergane-env.sh` exports the config path on this host, and a test
    inheriting it would measure the operator's installation.
    """
    monkeypatch.delenv(ERGANE_CONFIG_PATH_ENV, raising=False)
    monkeypatch.delenv(FACTORY_CONFIG_PATH_ENV, raising=False)
