"""The roadmap render command: every spec, its state, and each blocker named.

`factory-roadmap render` is the one command that shows the whole roadmap
(acceptance scenario 5): every spec appears with its state, and each blocked
spec names its unsatisfied dependencies — never a bare "blocked". US1's render
needs no service; it reads a `specs/` corpus from disk and prints. The exit-code
contract is the same as `factory-epic`'s and is stated once here: `0` success,
`1` an operator-fixable grammar rejection, `2` a service that is not answering
(render cannot reach `2` yet — it touches no service — but the number is
reserved by the contract).

Three properties carry the weight:

- **Every spec appears.** No spec is dropped; the render is the whole roadmap.
- **Blockers are named.** A blocked spec lists the spec dirs it waits on, so
  the operator's next move (unblock or edit the edge) is on the line.
- **Output is deterministic.** Specs appear in sorted order (the spec dir),
  so two operators reading the same corpus see the same lines.

Written before `factory/roadmap/cli.py` exists (T005 precedes T008): until the
module lands, every test here fails at import.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, NamedTuple

import pytest

from factory.roadmap.cli import main

CORPUS = Path(__file__).resolve().parent / "fixtures" / "roadmap"


class Run(NamedTuple):
    code: int
    stdout: str
    stderr: str


def _invoke(argv: tuple[str, ...]) -> int:
    try:
        return main(list(argv))
    except SystemExit as exit_request:
        return 0 if exit_request.code is None else int(exit_request.code)


@pytest.fixture
def run(capsys: pytest.CaptureFixture[str]) -> Callable[..., Run]:
    def invoke(*argv: str) -> Run:
        code = _invoke(argv)
        captured = capsys.readouterr()
        return Run(code, captured.out, captured.err)

    return invoke


def specs_root(case: str) -> str:
    return str(CORPUS / case / "specs")


# Acceptance (scenario 5) -----------------------------------------------------


def test_every_spec_appears_with_its_state(run: Callable[..., Run]) -> None:
    """Every spec in the corpus appears in the render with its state.

    `001-alpha` landed, `002-bravo` draft, `003-ready` ready, `004-blocked`
    ready, `006-deferred` deferred — five lines, one per spec, no spec dropped.
    """
    result = run("render", specs_root("valid"))

    assert result.code == 0
    out = result.stdout
    assert "001-alpha" in out and "landed" in out
    assert "002-bravo" in out and "draft" in out
    assert "003-ready" in out and "ready" in out
    assert "006-deferred" in out and "deferred" in out


def test_a_blocked_spec_names_its_unsatisfied_dependencies(
    run: Callable[..., Run]
) -> None:
    """Never a bare "blocked": the render names the edges a spec waits on.

    `004-blocked` is `ready` and depends on the draft `002-bravo`; the line for
    `004-blocked` names `002-bravo` as the blocker.
    """
    result = run("render", specs_root("valid"))

    assert result.code == 0
    assert "004-blocked" in result.stdout
    assert "002-bravo" in result.stdout


def test_the_render_is_deterministic(run: Callable[..., Run]) -> None:
    """Two renders of the same corpus produce identical output.

    Specs appear in sorted order (by spec dir), so the roadmap reads the same
    for every operator and every invocation — no hidden ordering dependency.
    """
    one = run("render", specs_root("valid"))
    two = run("render", specs_root("valid"))

    assert one.stdout == two.stdout


def test_render_orders_specs_by_spec_dir(run: Callable[..., Run]) -> None:
    """Specs appear in sorted order of their directory names.

    Deterministic ordering: `001-alpha` before `002-bravo` before `003-ready`
    before `004-blocked` before `006-deferred`, the order the operator reads
    the directory listing.
    """
    result = run("render", specs_root("valid"))

    out = result.stdout
    pos = {name: out.index(name) for name in (
        "001-alpha", "002-bravo", "003-ready", "004-blocked", "006-deferred"
    )}
    assert pos["001-alpha"] < pos["002-bravo"] < pos["003-ready"]
    assert pos["003-ready"] < pos["004-blocked"] < pos["006-deferred"]


# Exit codes (the contract, stated once) --------------------------------------


def test_render_exits_zero_on_a_valid_corpus(run: Callable[..., Run]) -> None:
    """`0` success: a valid corpus renders and returns 0."""
    assert run("render", specs_root("valid")).code == 0


def test_render_exits_one_on_a_grammar_rejection(run: Callable[..., Run]) -> None:
    """`1` operator-fixable: a grammar rejection names the offender, exit 1.

    The render refuses to print a corpus with a broken spec; the operator
    must edit the spec, which is the `1` case — never a silent partial render.
    """
    result = run("render", specs_root("unknown_key"))

    assert result.code == 1
    # The offender and the file are named in the error, on stderr.
    assert "priority" in result.stderr
    assert "001-x" in result.stderr


def test_render_exits_one_on_a_cycle(run: Callable[..., Run]) -> None:
    """A cycle is an operator-fixable grammar rejection (exit 1)."""
    result = run("render", specs_root("cycle"))

    assert result.code == 1
    assert "001-a" in result.stderr and "002-b" in result.stderr


def test_render_needs_no_service(
    run: Callable[..., Run], monkeypatch: pytest.MonkeyPatch
) -> None:
    """US1's render touches no service — a dead Temporal address cannot stop it.

    The exit-2 contract (service not answering) is reserved for the commands
    that talk to Temporal; the render reads disk only, so a closed port is
    invisible to it.
    """
    monkeypatch.setenv("TEMPORAL_ADDRESS", "127.0.0.1:9")  # nothing listening

    assert run("render", specs_root("valid")).code == 0


def test_render_names_every_blocker_across_multiple_blocked_specs(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    """Two blocked specs each name their own unsatisfied dependencies.

    A corpus with two ready specs blocked on different edges: the render names
    each blocker on its own spec's line, so the operator sees which spec waits
    on what — not one undifferentiated "blocked".
    """
    root = tmp_path / "specs"
    for spec_dir, state, deps in (
        ("001-anchor", "draft", None),
        ("002-waits-on-anchor", "ready", ["001-anchor"]),
        ("003-also-waits", "ready", ["001-anchor"]),
    ):
        target = root / spec_dir
        target.mkdir(parents=True)
        frontmatter = f"---\nstate: {state}\n"
        if deps is not None:
            frontmatter += f"depends_on_landed: {deps}\n"
        frontmatter += "---\n\n# Feature\n\n"
        target.joinpath("spec.md").write_text(frontmatter)

    result = run("render", str(root))

    assert result.code == 0
    out = result.stdout
    assert "002-waits-on-anchor" in out
    assert "003-also-waits" in out
    assert "001-anchor" in out