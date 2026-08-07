"""How readiness is computed over the roadmap graph (FR-003).

"Intent is declared; progress is observed." A spec's frontmatter may say
`ready`, but only the system may say `building`/dispatchable — and a spec is
dispatchable only when `state: ready` *and* every `depends_on_landed` edge is
satisfied. Satisfaction has two kinds, and they MUST be distinguishable in
reporting:

- **attested**: the dependency's own frontmatter carries `state: landed` — the
  operator's attestation for work that predates the roadmap (001/002/005 were
  never epics; nothing will ever observe them landing).
- **observed**: a child epic returned COMPLETED with every landing MERGED —
  derived from Temporal and git. This kind arrives in US2; the seam for it must
  exist now so US2 does not have to restructure the graph to add it.

At US1 the default resolver is "attested only": a dependency is satisfied iff
its target spec attests `landed` in its own frontmatter. US2 supplies a resolver
that also consults the live record.

Written before `factory/roadmap/models.py` carries readiness (T004 precedes
T007): until it lands, every test here fails.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from factory.roadmap.models import (
    LandedKind,
    LandedStatus,
    RoadmapError,
    SpecState,
    compute_readiness,
    read_roadmap,
)

CORPUS = Path(__file__).resolve().parent / "fixtures" / "roadmap"


def read(case: str) -> Any:
    return read_roadmap(CORPUS / case / "specs")


# Acceptance (FR-003) ---------------------------------------------------------


def test_ready_with_an_attested_landed_dependency_is_dispatchable() -> None:
    """Acceptance scenario 1: ready + attested-landed edge → dispatchable.

    `003-ready` is `ready` and depends on `001-alpha`, which attests `landed`.
    The edge is satisfied (attested), so the spec is dispatchable, and the
    satisfaction is reported as `attested` — the operator can see *why* it
    dispatches.
    """
    roadmap = read("valid")
    ready = compute_readiness(roadmap)

    spec = ready.spec("003-ready")
    assert spec.dispatchable is True
    assert spec.blockers == []
    # The satisfied edge is attested, and that is distinguishable.
    assert spec.satisfied_as["001-alpha"] is LandedKind.ATTESTED


def test_ready_with_an_unsatisfied_dependency_is_blocked_and_names_it() -> None:
    """Acceptance scenario 5: a blocked spec names its unsatisfied dependency.

    `004-blocked` is `ready` and depends on `002-bravo`, which is `draft` (not
    landed). The edge is unsatisfied, so the spec is blocked, and the blocker
    is named — never a bare "blocked".
    """
    roadmap = read("valid")
    ready = compute_readiness(roadmap)

    spec = ready.spec("004-blocked")
    assert spec.dispatchable is False
    assert spec.blockers == ["002-bravo"]


def test_deferred_and_draft_are_never_dispatchable() -> None:
    """`deferred` and `draft` never dispatch, regardless of edges.

    `002-bravo` is `draft`, `006-deferred` is `deferred`; neither is `ready`, so
    neither is dispatchable even with no edges to wait on.
    """
    roadmap = read("valid")
    ready = compute_readiness(roadmap)

    assert ready.spec("002-bravo").dispatchable is False
    assert ready.spec("006-deferred").dispatchable is False
    # A non-ready spec reports no blockers — it is not "blocked" in the
    # edge sense; its state is its own reason.
    assert ready.spec("002-bravo").blockers == []
    assert ready.spec("006-deferred").blockers == []


def test_attested_and_observed_satisfaction_are_distinguishable() -> None:
    """FR-003: the two kinds of satisfaction MUST be distinguishable.

    At US1 the default resolver satisfies a dependency only via attestation,
    so `001-alpha` (attested `landed`) reads `LandedKind.ATTESTED`. The seam
    for `observed` is exercised by injecting a resolver that reports
    `002-bravo` as observed-landed: with that, `004-blocked` becomes
    dispatchable and the satisfaction reads `OBSERVED`, not `ATTESTED`. US2
    supplies that resolver against Temporal + git; the seam exists now so it
    does not have to restructure the graph later.
    """
    roadmap = read("valid")

    # Default (attested-only): 004-blocked is blocked on the draft 002-bravo.
    default = compute_readiness(roadmap)
    assert default.spec("004-blocked").dispatchable is False
    assert default.spec("004-blocked").blockers == ["002-bravo"]

    # Inject an observed-landed fact for 002-bravo, the US2 seam.
    observed = compute_readiness(
        roadmap,
        landed_for=lambda spec_dir: (
            LandedStatus(landed=True, kind=LandedKind.OBSERVED)
            if spec_dir == "002-bravo"
            else None
        ),
    )
    blocked = observed.spec("004-blocked")
    assert blocked.dispatchable is True
    assert blocked.blockers == []
    assert blocked.satisfied_as["002-bravo"] is LandedKind.OBSERVED
    # 003-ready still reads its attested dependency as attested — the two kinds
    # are reported distinctly in the same graph.
    ready = observed.spec("003-ready")
    assert ready.satisfied_as["001-alpha"] is LandedKind.ATTESTED


def test_an_observed_landed_dependency_unblocks_a_ready_spec() -> None:
    """The seam resolves a dependency the frontmatter does not attest.

    `002-bravo`'s frontmatter is `draft`, so it is not attested-landed; only an
    observed-landed resolver (US2's input) can satisfy an edge on it. This proves
    the seam carries observation independently of the frontmatter.
    """
    roadmap = read("valid")

    def resolver(spec_dir: str) -> LandedStatus | None:
        if spec_dir == "002-bravo":
            return LandedStatus(landed=True, kind=LandedKind.OBSERVED)
        return None

    ready = compute_readiness(roadmap, landed_for=resolver)
    assert ready.spec("004-blocked").dispatchable is True


def test_a_landed_spec_is_not_dispatchable_itself() -> None:
    """`landed` is an attestation, not a dispatch intent.

    `001-alpha` attests `landed`; it is not `ready`, so it is not itself
    dispatchable. Landing is a fact about the past, not a request to build.
    """
    roadmap = read("valid")
    ready = compute_readiness(roadmap)

    assert ready.spec("001-alpha").dispatchable is False


def test_every_spec_appears_in_the_readiness_graph() -> None:
    """Readiness covers the whole corpus: no spec is dropped."""
    roadmap = read("valid")
    ready = compute_readiness(roadmap)

    assert {s.spec_dir for s in ready.specs} == {
        "001-alpha",
        "002-bravo",
        "003-ready",
        "004-blocked",
        "006-deferred",
    }