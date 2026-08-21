"""US2: the promotion rung can be switched on from the command line.

070/US5 built the third rung of the retry ladder and left it unreachable: a
`VerificationConfig.promotion_persona` that no operator surface could set, so
`_promotion_available` returned `False` on every floor. These tests hold the
two start verbs to the four things that make the rung real — the flag reaches
the epic's config, it reaches every child epic a roadmap starts, its absence
leaves today's behaviour untouched, and a persona the registry does not know is
refused before anything is started.

Every case reads what the command would *start*: a recording client stands in
for Temporal, so what is asserted is the payload the CLI built and nothing
downstream of it (US2-S1, US2-S2). The registry is a fixture on
`ERGANE_PERSONAS_PATH`, so the refusal is decided by a registry this test
wrote rather than by whatever the operator's floor happens to declare.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import yaml

from factory.cli.errors import OperatorError
from factory.usage.litellm_client import PROXY_URL_ENV
from factory.verify.ladder import next_action
from factory.verify.models import (
    AttemptRecord,
    NextAction,
    OverallVerdict,
    VerificationConfig,
)

#: The stronger persona an operator promotes to. It exists in the fixture
#: registry below; the code under test may not know it by name (constitution
#: VII), it may only look it up.
CLOSER = "closer"

#: A name no registry in this file declares — the typo case (US2-S4).
ABSENT = "cl0ser"

EPIC_ID = "075-a-stronger-rung-runs-a-stronger-model"
PROXY_URL = "http://litellm.test"


# --- fixtures -----------------------------------------------------------------


def _registry(tmp_path: Path) -> Path:
    """A two-persona registry: the node's builder and the promotion target."""
    path = tmp_path / "personas.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "implementer": {
                    "agent": "claude-code",
                    "model": "local/small",
                    "fallback": None,
                    "skills": [],
                    "write_scope": "worktree",
                    "needs_worktree": True,
                    "timeout": 300,
                },
                CLOSER: {
                    "agent": "claude-code",
                    "model": "vendor/large",
                    "fallback": None,
                    "skills": [],
                    "write_scope": "worktree",
                    "needs_worktree": True,
                    "timeout": 600,
                },
            }
        ),
        encoding="utf-8",
    )
    return path


@pytest.fixture
def registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = _registry(tmp_path)
    monkeypatch.setenv("ERGANE_PERSONAS_PATH", str(path))
    monkeypatch.delenv("FACTORY_PERSONAS_PATH", raising=False)
    return path


def _write_graph(tmp_path: Path) -> Path:
    """A minimal compiled graph `ergane build start` will accept.

    The target directory gets a v1 manifest so the dispatch-time loop-config
    read succeeds; it declares no `ladder` block, which is what makes the
    control case (US2-S3) meaningful — `promotion_persona` is `None` unless the
    flag puts something there.
    """
    target = tmp_path / "target"
    target.mkdir(parents=True, exist_ok=True)
    (target / "ergane.yaml").write_text(
        "version: 1\nruntime: bwrap\ngates:\n  test: uv run pytest -q\n",
        encoding="utf-8",
    )
    graph_path = tmp_path / "workgraph.json"
    graph_path.write_text(
        json.dumps(
            {
                "epic_id": EPIC_ID,
                "feature": EPIC_ID,
                "specs_root": str(tmp_path / "specs"),
                "target_repo": str(target),
                "nodes": [
                    {
                        "id": "us1",
                        "story_key": "US1",
                        "persona": "implementer",
                        "spec_ref": f"{EPIC_ID}/us1",
                        "requirement_keys": ["US1", "FR-001"],
                        "depends_on": [],
                        "depends_on_merged": [],
                        "timeout_override_s": None,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return graph_path


class _RecordingClient:
    """Stands in for the Temporal client; records what would have been started."""

    def __init__(self) -> None:
        self.started: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    async def start_workflow(self, *args: Any, **kwargs: Any) -> Any:
        self.started.append((args, kwargs))
        return object()


def _parse(add_parser: Any, argv: list[str]) -> argparse.Namespace:
    """Parse through the noun's own `add_parser`, so the flag must really exist.

    A `Namespace` hand-built in the test would pass whether or not the operator
    can type the flag; this route fails with argparse's usage error until the
    parser declares it.
    """
    parser = argparse.ArgumentParser(prog="ergane")
    subparsers = parser.add_subparsers(dest="noun", required=True)
    add_parser(subparsers)
    return parser.parse_args(argv)


def _start_build(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *flags: str,
) -> Any:
    """Drive `ergane build start` to the brink and return the `EpicInput` built."""
    import factory.cli.nouns as nouns_package
    from factory.cli.nouns import build as build_module

    recorder = _RecordingClient()

    async def _open_client() -> Any:
        return recorder

    async def _no_findings(graph: Any) -> list[Any]:
        return []

    monkeypatch.setenv(PROXY_URL_ENV, PROXY_URL)
    monkeypatch.setattr(nouns_package, "_open_client", _open_client)
    monkeypatch.setattr(build_module, "_run_preflight", _no_findings)

    graph_path = _write_graph(tmp_path)
    args = _parse(
        build_module.add_parser, ["build", "start", str(graph_path), *flags]
    )
    assert args.run(args) == 0
    return recorder.started[0][0][1]


def _start_roadmap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *flags: str,
) -> Any:
    """Drive `ergane roadmap start` to the brink and return the `RoadmapInput`."""
    from factory.cli import roadmap as roadmap_module

    recorder = _RecordingClient()

    async def _connect() -> Any:
        return recorder

    monkeypatch.setattr(roadmap_module, "_connect", _connect)

    specs_root = tmp_path / "specs"
    specs_root.mkdir(parents=True, exist_ok=True)
    args = _parse(
        roadmap_module.add_roadmap_parser,
        [
            "roadmap",
            "start",
            str(specs_root),
            "--target-repo",
            str(tmp_path / "target"),
            "--proxy-url",
            PROXY_URL,
            *flags,
        ],
    )
    assert args.run(args) == 0
    return recorder.started[0][0][1]


# --- T012 / US2-S1 — the flag reaches the epic's VerificationConfig -----------


def test_build_start_puts_the_declared_persona_into_the_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, registry: Path
) -> None:
    """US2-S1, FR-007: read off the start payload, not off the flag.

    The assertion is on `EpicInput.config`, because that is the only thing the
    workflow ever sees. A flag that parses and is then dropped between argparse
    and `start_workflow` is exactly the shape of no-op this story exists to
    end.
    """
    built = _start_build(tmp_path, monkeypatch, "--promotion-persona", CLOSER)

    assert built.config.promotion_persona == CLOSER


def test_the_declared_persona_does_not_disturb_the_rest_of_the_ladder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, registry: Path
) -> None:
    """The flag sets one field. Every other ladder dial keeps the manifest's value."""
    without = _start_build(tmp_path, monkeypatch)
    with_flag = _start_build(tmp_path, monkeypatch, "--promotion-persona", CLOSER)

    assert replace(with_flag.config, promotion_persona=None) == without.config


# --- T013 / US2-S2 — every child epic of a roadmap receives it ----------------


def test_roadmap_start_puts_the_declared_persona_into_the_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, registry: Path
) -> None:
    """US2-S2, FR-008, half one: the roadmap's own payload carries it."""
    built = _start_roadmap(tmp_path, monkeypatch, "--promotion-persona", CLOSER)

    assert built.config.promotion_persona == CLOSER


def test_every_child_epic_gets_the_declared_persona(registry: Path) -> None:
    """US2-S2, FR-008, half two: the child epic's config carries it too.

    Half one alone would be a lie. The roadmap does not hand `request.config`
    to its children — it starts each one on the ladder read from the target
    clone's manifest at dispatch (023 US2), so an operator's flag that stopped
    at `RoadmapInput` would reach no epic at all. This asserts the overlay the
    child is actually started with: the manifest's ladder, with the operator's
    rung on top and every other dial the manifest pinned left alone.
    """
    from factory.roadmap.workflow import _child_config

    pinned = VerificationConfig(max_attempts=4, debugger_cycles=0)
    requested = VerificationConfig(promotion_persona=CLOSER)

    child = _child_config(pinned, requested)

    assert child.promotion_persona == CLOSER
    assert child.max_attempts == 4
    assert child.debugger_cycles == 0


def test_a_manifest_declared_rung_survives_a_roadmap_started_without_the_flag(
    registry: Path,
) -> None:
    """The overlay is an override, not a reset (FR-010 at the child boundary).

    A target repo that declares `ladder.promotion_persona` in its manifest has
    already switched the rung on for itself. An operator who starts a roadmap
    without the flag has said nothing about promotion, and saying nothing must
    not turn the manifest's rung off.
    """
    from factory.roadmap.workflow import _child_config

    pinned = VerificationConfig(promotion_persona="manifest-closer")

    child = _child_config(pinned, VerificationConfig())

    assert child == pinned


# --- T014 / US2-S3 — the control: no flag, no rung ----------------------------


def _spent(config: VerificationConfig) -> list[AttemptRecord]:
    """A history with the ordinary attempt budget exhausted, debugger unspent."""
    return [
        AttemptRecord(
            attempt=number + 1,
            persona="implementer",
            verdict=OverallVerdict.FAIL,
        )
        for number in range(config.max_attempts)
    ]


def test_without_the_flag_the_promotion_persona_is_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, registry: Path
) -> None:
    """US2-S3, FR-010: today's behaviour is the default, on both verbs.

    The control for the whole story. A flag that defaulted to a persona — or a
    pass-through that substituted one when the operator declared none — would
    promote every struggling node on every floor to the metered builder, which
    is a worse defect than the rung being off.
    """
    epic = _start_build(tmp_path, monkeypatch)
    roadmap = _start_roadmap(tmp_path, monkeypatch)

    assert epic.config.promotion_persona is None
    assert roadmap.config.promotion_persona is None


def test_without_the_flag_the_rung_stays_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, registry: Path
) -> None:
    """The other half of the control: the field's value is what the ladder reads.

    Asserting `is None` proves the payload; this proves the consequence. The
    same exhausted history that promotes under the flag's config must fall
    through to the debugger under the default one — so a change that switched
    the rung on by accident cannot pass by leaving the field alone.
    """
    default = _start_build(tmp_path, monkeypatch).config
    declared = _start_build(
        tmp_path, monkeypatch, "--promotion-persona", CLOSER
    ).config
    # `max_attempts` is raised on both so the promotion rung is observable at
    # all: at the shipped defaults the ordinary and debugger budgets expire
    # together and every history lands on DEBUGGER either way.
    default = replace(default, max_attempts=4)
    declared = replace(declared, max_attempts=4)

    assert next_action(_spent(default), default) is NextAction.DEBUGGER
    assert next_action(_spent(declared), declared) is NextAction.PROMOTE


# --- T015 / US2-S4 — an unknown persona is refused before anything starts -----


class _PoisonedClient:
    """Any use of Temporal is a test failure: the refusal is pre-dispatch."""

    async def start_workflow(self, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError("the epic was started despite an unknown persona")


def test_build_start_refuses_an_unknown_persona_before_starting_anything(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, registry: Path
) -> None:
    """US2-S4, FR-009: refused by name, with no workflow started.

    "Before the epic starts" is asserted mechanically rather than read off the
    message: the client factory raises if it is called at all, so a check that
    ran after dispatch fails here with that assertion instead of the refusal.
    """
    import factory.cli.nouns as nouns_package
    from factory.cli.nouns import build as build_module

    async def _open_client() -> Any:
        raise AssertionError("Temporal was dialled before the persona was checked")

    async def _no_findings(graph: Any) -> list[Any]:
        return []

    monkeypatch.setenv(PROXY_URL_ENV, PROXY_URL)
    monkeypatch.setattr(nouns_package, "_open_client", _open_client)
    monkeypatch.setattr(build_module, "_run_preflight", _no_findings)

    graph_path = _write_graph(tmp_path)
    args = _parse(
        build_module.add_parser,
        ["build", "start", str(graph_path), "--promotion-persona", ABSENT],
    )

    with pytest.raises(OperatorError) as excinfo:
        args.run(args)

    message = str(excinfo.value)
    assert ABSENT in message
    # Naming the persona is the point: an operator who typo'd needs to see
    # what they typed, and what they could have typed instead.
    assert CLOSER in message


def test_roadmap_start_refuses_an_unknown_persona_before_starting_anything(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, registry: Path
) -> None:
    """US2-S4, FR-009 on the second verb: one rule, both commands."""
    from factory.cli import roadmap as roadmap_module

    async def _connect() -> Any:
        raise AssertionError("Temporal was dialled before the persona was checked")

    monkeypatch.setattr(roadmap_module, "_connect", _connect)

    specs_root = tmp_path / "specs"
    specs_root.mkdir(parents=True, exist_ok=True)
    args = _parse(
        roadmap_module.add_roadmap_parser,
        [
            "roadmap",
            "start",
            str(specs_root),
            "--target-repo",
            str(tmp_path / "target"),
            "--proxy-url",
            PROXY_URL,
            "--promotion-persona",
            ABSENT,
        ],
    )

    with pytest.raises(OperatorError) as excinfo:
        args.run(args)

    assert ABSENT in str(excinfo.value)


def test_the_ladders_synthetic_placeholder_is_not_a_settable_persona(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, registry: Path
) -> None:
    """`PROMOTION_PERSONA` is a sentinel, never a registry entry (plan trap 6).

    It is the one name that would look plausible to somebody reading
    `ladder.py`, and a rung configured with it would count cycles against a
    persona no dispatch can resolve.
    """
    from factory.cli.nouns import build as build_module
    from factory.verify.ladder import PROMOTION_PERSONA

    graph_path = _write_graph(tmp_path)
    monkeypatch.setenv(PROXY_URL_ENV, PROXY_URL)
    args = _parse(
        build_module.add_parser,
        ["build", "start", str(graph_path), "--promotion-persona", PROMOTION_PERSONA],
    )

    with pytest.raises(OperatorError) as excinfo:
        args.run(args)

    assert PROMOTION_PERSONA in str(excinfo.value)
