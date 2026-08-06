"""What the spec's `## Work Graph` section compiles into, and what it refuses.

The deriver is the only thing standing between an epic spec and a dispatch: a
node it emits is a worktree, a virtual key, an agent attempt and a branch, and a
declaration it misreads is all of those pointed at the wrong story. So it is a
pure function — spec text in, `WorkGraph` out, no filesystem and no registry
(FR-011, R7) — and this suite is a plain unit test over the fixture corpus in
`tests/fixtures/workgraph/`, read as text.

The corpus is the point. Every fixture is the same "Short Links" feature with
byte-identical stories and requirement bullets; only the `## Work Graph` section
differs, so a case that fails has exactly one explanation, and every rejection
fixture is a spec the criteria parser accepts — what the deriver refuses is the
work graph, never the spec around it (tests/fixtures/README.md).

Four properties carry the weight:

- **The compiled graph is exact, not approximately right.** One node per story
  in spec order, ids lowercased, `requirement_keys` = `[story_key, *implements]`,
  `spec_ref` = `<feature>:<story_key>`. Those four are what later gets handed to
  `snapshot_criteria`, the branch name, the ledger's attribution string and the
  scheduler's tiebreak, so the acceptance test asserts the whole `WorkGraph`
  value rather than spot-checking fields.

- **Identity comes from the caller, never from the text.** `epic_id`, `feature`,
  `specs_root` and `target_repo` are arguments (contracts/workgraph-schema.md);
  the deriver does not know what directory the spec was read from and must not
  guess.

- **A bad declaration is refused by name, and nothing is emitted** (SC-006). The
  audience is an author who has to go edit one line of one spec, so every
  rejection carries the offending story and the rule slug from the contract's
  table — not prose a caller has to grep. Errors are *collected*, not raised at
  the first: the CLI prints all of them at once (contracts/cli.md), because an
  author fixing one typo per run is the failure mode this avoids.

- **Purity is literal.** Derivation opens no file. It is called with text the CLI
  already read, so the same text derives the same graph forever — which is what
  makes `workgraph.json` a compiled artifact rather than a snapshot of whatever
  the filesystem said at derive time.

Two deliberate choices in the setup:

- **Rejections are one parametrized table over the corpus**, one row per rule in
  contracts/workgraph-schema.md § Shape rules. A rule with no fixture is visibly
  a hole in the table.

- **Shape rules the corpus cannot express are tested against inline variants** of
  `valid_epic` (`respecified`), which swap only the `## Work Graph` block and
  leave the stories byte-identical. `depends_on` and `implements` are *required*
  keys; no fixture omits one, so a deriver that read a missing key as an empty
  list would pass the whole corpus while silently unhooking an edge.

Written before `factory/workgraph/derive.py` exists (T021 precedes T022): until
the module lands, every test here fails at import.
"""

from __future__ import annotations

import builtins
from pathlib import Path
from typing import Any

import pytest

from factory.config import Persona, WriteScope, load_personas
from factory.verify.criteria import parse_spec
from factory.verify.models import RequirementKind
from factory.workgraph.derive import DerivationError, derive_workgraph
from factory.workgraph.models import WorkGraph, WorkNode, validate_workgraph

CORPUS = Path(__file__).resolve().parent / "fixtures" / "workgraph"

#: The accepting fixture: three stories, one edge, one leaf, one override.
VALID = "valid_epic"

#: What the CLI supplies; none of it is parsed out of the spec text.
EPIC_ID = "042-short-links"
FEATURE = "042-short-links"
SPECS_ROOT = "specs"
TARGET_REPO = "/home/admin/code/ergane-target"

#: The persona every derived node names in the minimal interpreter.
IMPLEMENTER = "implementer"


def spec_text(fixture: str) -> str:
    return (CORPUS / fixture / "spec.md").read_text(encoding="utf-8")


def derive(fixture: str = VALID, **overrides: str) -> WorkGraph:
    """Derive one fixture with the caller-supplied identity fields."""
    return derive_workgraph(spec_text(fixture), **{**IDENTITY, **overrides})


def derive_text(text: str, **overrides: str) -> WorkGraph:
    return derive_workgraph(text, **{**IDENTITY, **overrides})


IDENTITY = {
    "epic_id": EPIC_ID,
    "feature": FEATURE,
    "specs_root": SPECS_ROOT,
    "target_repo": TARGET_REPO,
}


def respecified(work_graph: str) -> str:
    """`valid_epic`'s spec with its `## Work Graph` block swapped for another.

    Every story header, scenario and `FR-###` bullet stays byte-identical, so a
    variant tests the graph grammar and nothing else — the same discipline the
    fixture corpus follows on disk, applied to shapes no fixture holds.
    """
    head, _, tail = spec_text(VALID).partition("## Work Graph\n")
    assert tail, "valid_epic must declare a `## Work Graph` section"
    _, _, after = tail.partition("## Assumptions")
    block = work_graph.strip("\n")
    return f"{head}## Work Graph\n\n```yaml\n{block}\n```\n\n## Assumptions{after}"


def work_graph(us2: str) -> str:
    """The valid block with `US2`'s declaration replaced; US1/US3 untouched."""
    return (
        "US1:\n  depends_on: []\n  implements: [FR-001, FR-002]\n"
        f"{us2}"
        "US3:\n  depends_on: []\n  implements: [FR-004]\n"
    )


def rejections(fixture: str) -> list[Any]:
    with pytest.raises(DerivationError) as caught:
        derive(fixture)
    return list(caught.value.rejections)


def _persona(*, timeout_s: int | None = 3600) -> Persona:
    """An agent-backed registry entry; the alias is a placeholder by design."""
    return Persona(
        name=IMPLEMENTER,
        agent="claude-code",
        model="fake-provider/CHANGEME",
        fallback=None,
        skills=(),
        write_scope=WriteScope.WORKTREE,
        needs_worktree=True,
        timeout_s=timeout_s,
    )


#: The three nodes `valid_epic` must compile into, in spec order.
EXPECTED_NODES = [
    WorkNode(
        id="us1",
        story_key="US1",
        persona=IMPLEMENTER,
        spec_ref=f"{FEATURE}:US1",
        requirement_keys=["US1", "FR-001", "FR-002"],
        depends_on=[],
        depends_on_merged=[],
        timeout_override_s=None,
    ),
    WorkNode(
        id="us2",
        story_key="US2",
        persona=IMPLEMENTER,
        spec_ref=f"{FEATURE}:US2",
        requirement_keys=["US2", "FR-003"],
        depends_on=["us1"],
        depends_on_merged=[],
        timeout_override_s=7200,
    ),
    WorkNode(
        id="us3",
        story_key="US3",
        persona=IMPLEMENTER,
        spec_ref=f"{FEATURE}:US3",
        requirement_keys=["US3", "FR-004"],
        depends_on=[],
        depends_on_merged=[],
        timeout_override_s=None,
    ),
]


# Acceptance (SC-006) ---------------------------------------------------------


def test_the_valid_fixture_compiles_into_exactly_the_expected_graph() -> None:
    """The whole artifact, asserted as one value (SC-006).

    Every field here is load-bearing downstream — `requirement_keys` is what
    `snapshot_criteria` filters to, `id` names the branch and the worktree,
    `spec_ref` is component 1's attribution string — so the acceptance case
    pins the compiled graph entire rather than sampling it. The section's prose
    and the `# comment` after the override are read past by construction: the
    fence-masked scan finds the block, and YAML drops the comment.
    """
    assert derive() == WorkGraph(
        epic_id=EPIC_ID,
        feature=FEATURE,
        specs_root=SPECS_ROOT,
        target_repo=TARGET_REPO,
        nodes=EXPECTED_NODES,
    )


def test_one_node_per_story_with_lowercased_ids() -> None:
    """`US1` → `us1`: the id names a branch and a directory, so case matters."""
    graph = derive()

    assert [node.id for node in graph.nodes] == ["us1", "us2", "us3"]
    assert [node.story_key for node in graph.nodes] == ["US1", "US2", "US3"]


def test_edges_reference_node_ids_not_story_ids() -> None:
    """`depends_on: [US1]` compiles to `["us1"]` — the id the scheduler holds.

    Leaving story ids in the edge list would produce a graph that validates
    (nothing declared `US1`… so it would not, in fact: it would be rejected at
    epic start as a dangling reference). Either way the dependency would never
    resolve, and US2 would be dispatched against an unbuilt US1 or not at all.
    """
    us2 = next(node for node in derive().nodes if node.id == "us2")

    assert us2.depends_on == ["us1"]


def test_requirement_keys_are_the_story_key_then_its_implements() -> None:
    """`[story_key, *implements]`, in declaration order (contracts/…schema.md).

    The story key comes first because it is the requirement the node is *for*;
    the FR keys follow in the order the author listed them. This list is handed
    to `snapshot_criteria` verbatim, so its order is the order the judge reads.
    """
    keys = {node.id: node.requirement_keys for node in derive().nodes}

    assert keys == {
        "us1": ["US1", "FR-001", "FR-002"],
        "us2": ["US2", "FR-003"],
        "us3": ["US3", "FR-004"],
    }


def test_spec_ref_is_feature_and_story_key() -> None:
    """`<feature>:<story_key>` — component 1's attribution string, from the caller.

    The feature is the argument, not the fixture directory name, which is why
    this fixture derives as `042-short-links:US1` and not `valid_epic:US1`.
    """
    assert [node.spec_ref for node in derive().nodes] == [
        "042-short-links:US1",
        "042-short-links:US2",
        "042-short-links:US3",
    ]


def test_every_derived_node_is_an_implementer() -> None:
    """Persona is not authored per story yet — the grammar has no key for it.

    `unknown_key` refuses `persona: debugger` rather than honouring it, so the
    only persona a derived node can carry is this one (contracts/…schema.md).
    """
    assert {node.persona for node in derive().nodes} == {IMPLEMENTER}


def test_the_timeout_override_travels_only_where_it_was_declared() -> None:
    """One story declares `timeout: 7200`; the other two resolve persona-first (R8).

    A deriver that spread the override, or that baked the persona's registry
    value into the nodes that declared none, would make `workgraph.json` stale
    the moment an operator edits `personas.yaml` — the reason resolution is
    deliberately deferred to dispatch.
    """
    overrides = {node.id: node.timeout_override_s for node in derive().nodes}

    assert overrides == {"us1": None, "us2": 7200, "us3": None}


def test_identity_fields_come_from_the_caller() -> None:
    """The four graph-level fields are arguments; nothing is parsed out of the text.

    The deriver never sees a path, so it cannot know the epic id — passing a
    different one must produce a graph that differs in exactly that field and
    in the `spec_ref`s built from the feature.
    """
    graph = derive(epic_id="003-merge-queue", feature="003-merge-queue")

    assert (graph.epic_id, graph.feature) == ("003-merge-queue", "003-merge-queue")
    assert (graph.specs_root, graph.target_repo) == (SPECS_ROOT, TARGET_REPO)
    assert graph.nodes[0].spec_ref == "003-merge-queue:US1"


def test_node_order_follows_the_spec_not_the_yaml_block() -> None:
    """Declaration order is scheduling order (R10) — and the spec author declares it.

    The block is a YAML mapping, which an author may write in any order (and a
    reformatter may sort). Node order is the order the stories appear in the
    spec, so the sequencing the operator reads top-to-bottom in the spec is the
    sequencing the scheduler runs.
    """
    reordered = respecified(
        """
US3:
  depends_on: []
  implements: [FR-004]
US2:
  depends_on: [US1]
  implements: [FR-003]
US1:
  depends_on: []
  implements: [FR-001, FR-002]
"""
    )

    assert [node.id for node in derive_text(reordered).nodes] == ["us1", "us2", "us3"]


def test_the_derived_graph_passes_start_time_validation() -> None:
    """What derive emits, `start` accepts (FR-002) — the two ends must agree.

    Derivation and start-time validation are separate functions with separate
    rules; a deriver that emitted, say, a duplicate id or a dangling edge would
    produce an artifact rejected at the moment an operator tries to run it,
    with no earlier signal.
    """
    validate_workgraph(derive(), {IMPLEMENTER: _persona()})


# Purity and determinism (FR-011) ---------------------------------------------


def test_derivation_opens_no_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """Text in, `WorkGraph` out — no filesystem, no registry (R7).

    Purity is what makes SC-006 unit-testable without infrastructure, and what
    keeps the deriver honest about its inputs: a function that could read
    `personas.yaml` would be tempted to resolve timeouts at derive time and bake
    a registry value into a compiled artifact. Every read path is broken here,
    so a lapse is an error rather than a silent dependency.
    """

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("derivation must not touch the filesystem")

    text = spec_text(VALID)
    monkeypatch.setattr(builtins, "open", refuse)
    monkeypatch.setattr(Path, "open", refuse)
    monkeypatch.setattr(Path, "read_text", refuse)
    monkeypatch.setattr(Path, "read_bytes", refuse)

    graph = derive_text(text)

    monkeypatch.undo()
    assert [node.id for node in graph.nodes] == ["us1", "us2", "us3"]


def test_the_same_text_derives_the_same_graph() -> None:
    """Deterministic (SC-006): `workgraph.json` is compiled, never sampled."""
    assert derive() == derive()


# Rejections (SC-006) ---------------------------------------------------------

#: One row per rule in contracts/workgraph-schema.md § Shape rules, against the
#: fixture built for it: (fixture, rule slug, offending story or None, the
#: identifier the message must name).
REJECTIONS = [
    ("missing_story", "coverage", "US3", "US3"),
    ("unknown_story", "story_id", "US4", "US4"),
    ("unknown_fr", "implements", "US2", "FR-404"),
    ("unknown_dep", "depends_on", "US2", "US9"),
    ("self_dep", "depends_on", "US2", "US2"),
    ("cycle", "acyclic", "US2", "US3"),
    ("no_section", "section_missing", None, "Work Graph"),
    ("two_blocks", "section_missing", None, "Work Graph"),
    ("non_mapping", "mapping", None, "mapping"),
    ("unknown_key", "unknown_key", "US2", "persona"),
    ("bad_timeout", "timeout", "US2", "US2"),
]


@pytest.mark.parametrize(
    ("fixture", "rule", "story", "named"),
    REJECTIONS,
    ids=[row[0] for row in REJECTIONS],
)
def test_each_rejection_fixture_fails_naming_its_story_and_rule(
    fixture: str, rule: str, story: str | None, named: str
) -> None:
    """Every rule in the table refuses its fixture, and says which one and why.

    Each fixture carries exactly one defect with everything around it
    well-formed, so "exactly one rejection" is assertable — a deriver that
    reported the whole graph as broken because one story was would send the
    author to the wrong line, and one that reported nothing here would emit a
    graph whose nodes do not match the spec they claim to compile.
    """
    faults = rejections(fixture)

    assert len(faults) == 1
    fault = faults[0]
    assert (fault.rule, fault.story) == (rule, story)
    assert named in str(fault)


def test_a_rejected_spec_emits_nothing() -> None:
    """No partial graph, no best-effort nodes: the epic does not compile at all.

    Emitting the well-formed nodes of a broken spec would be the worst outcome
    available — an epic that starts, dispatches the stories that parsed, and
    silently never builds the one that did not.
    """
    with pytest.raises(DerivationError):
        derive("missing_story")


def test_the_cycle_rejection_names_only_the_cycle() -> None:
    """`US2 ⇄ US3` — and `US1`, which is outside it, goes unmentioned.

    The author's next move is to delete one of the cycle's edges, so the message
    lists the members of the cycle. Naming every story in the graph would leave
    them to re-derive the cycle by hand, which is the work this just did.
    """
    (fault,) = rejections("cycle")

    assert "US2" in str(fault) and "US3" in str(fault)
    assert "US1" not in str(fault)


def test_every_rejection_is_collected_not_just_the_first() -> None:
    """Two broken stories produce two rejections (contracts/cli.md).

    `factory-epic derive` prints every collected error and writes nothing; an
    author fixing one typo per run — with the next one revealed only after the
    fix — is the failure mode collection exists to avoid.
    """
    two_faults = respecified(
        """
US1:
  depends_on: []
  implements: [FR-001, FR-002]
US2:
  depends_on: [US9]
  implements: [FR-003]
US3:
  depends_on: []
  implements: [FR-404]
"""
    )

    with pytest.raises(DerivationError) as caught:
        derive_text(two_faults)

    assert {(fault.rule, fault.story) for fault in caught.value.rejections} == {
        ("depends_on", "US2"),
        ("implements", "US3"),
    }
    rendered = str(caught.value)
    assert "US9" in rendered and "FR-404" in rendered


#: Shape rules the fixture corpus cannot express: a *missing* required key, and
#: values of the wrong type. `depends_on` and `implements` are required
#: (contracts/workgraph-schema.md), so absence is a rejection and never an
#: implied empty list — an unhooked edge is invisible in the compiled artifact.
MALFORMED = [
    ("no_depends_on", "US2:\n  implements: [FR-003]\n", "depends_on"),
    ("no_implements", "US2:\n  depends_on: [US1]\n", "implements"),
    (
        "depends_on_scalar",
        "US2:\n  depends_on: US1\n  implements: [FR-003]\n",
        "depends_on",
    ),
    (
        "timeout_not_an_int",
        "US2:\n  depends_on: [US1]\n  implements: [FR-003]\n  timeout: 2h\n",
        "timeout",
    ),
    ("declaration_scalar", "US2: 7200\n", "mapping"),
]


@pytest.mark.parametrize(
    ("case", "declaration", "rule"), MALFORMED, ids=[row[0] for row in MALFORMED]
)
def test_a_malformed_declaration_is_refused_by_rule(
    case: str, declaration: str, rule: str
) -> None:
    """A required key omitted or given the wrong type names `US2` and its rule."""
    with pytest.raises(DerivationError) as caught:
        derive_text(respecified(work_graph(declaration)))

    assert [(fault.rule, fault.story) for fault in caught.value.rejections] == [
        (rule, "US2")
    ]


# FR-009: `depends_on_merged` in the `## Work Graph` grammar --------------------
#
# A merge-gated edge is additive (D-025): a story may declare `depends_on_merged`
# beside `depends_on`, and a graph without it stays valid. It is *optional* — a
# declaration omitting it is not malformed the way omitting required `depends_on`
# is — and its entries compile to the node's `depends_on_merged` in id form.


def _declares_depends_on_merged() -> str:
    """The valid block with US2 merge-gated on US1 (and nothing else)."""
    return work_graph(
        "US2:\n  depends_on: []\n  depends_on_merged: [US1]\n"
        "  implements: [FR-003]\n"
    )


def test_depends_on_merged_derives_onto_the_node() -> None:
    """`depends_on_merged: [US1]` compiles to `["us1"]` — the scheduler's id."""
    graph = derive_text(respecified(_declares_depends_on_merged()))

    (us2,) = [node for node in graph.nodes if node.id == "us2"]
    assert us2.depends_on_merged == ["us1"]


def test_a_node_without_depends_on_merged_stays_empty() -> None:
    """The key is optional: a declaration without it derives an empty tuple."""
    graph = derive_text(respecified(work_graph(
        "US2:\n  depends_on: [US1]\n  implements: [FR-003]\n"
    )))

    (us1,) = [node for node in graph.nodes if node.id == "us1"]
    assert us1.depends_on_merged == []


def test_an_unknown_merge_gated_dependency_is_rejected() -> None:
    """`depends_on_merged: [US9]` names no declared story — refuse, emit nothing."""
    block = work_graph(
        "US2:\n  depends_on: [US1]\n  depends_on_merged: [US9]\n"
        "  implements: [FR-003]\n"
    )

    with pytest.raises(DerivationError) as caught:
        derive_text(respecified(block))

    assert [(fault.rule, fault.story) for fault in caught.value.rejections] == [
        ("depends_on_merged", "US2")
    ]


def test_a_self_merge_gated_dependency_is_rejected() -> None:
    """`depends_on_merged: [US2]` on US2 could never dispatch (cycle of one)."""
    block = work_graph(
        "US2:\n  depends_on: [US1]\n  depends_on_merged: [US2]\n"
        "  implements: [FR-003]\n"
    )

    with pytest.raises(DerivationError) as caught:
        derive_text(respecified(block))

    assert [(fault.rule, fault.story) for fault in caught.value.rejections] == [
        ("depends_on_merged", "US2")
    ]


def test_a_key_in_both_edge_sets_is_rejected() -> None:
    """One dependency cannot gate on both verified and merged (D-025)."""
    block = work_graph(
        "US2:\n  depends_on: [US1]\n  depends_on_merged: [US1]\n"
        "  implements: [FR-003]\n"
    )

    with pytest.raises(DerivationError) as caught:
        derive_text(respecified(block))

    assert [(fault.rule, fault.story) for fault in caught.value.rejections] == [
        ("depends_on_merged", "US2")
    ]


def test_a_cycle_through_the_union_of_both_edge_sets_is_rejected() -> None:
    """A cycle may span both edge kinds — `US1 ⇄ US2` across verified/merged."""
    block = (
        "US1:\n  depends_on: []\n  depends_on_merged: [US2]\n"
        "  implements: [FR-001, FR-002]\n"
        "US2:\n  depends_on: [US1]\n  depends_on_merged: []\n"
        "  implements: [FR-003]\n"
        "US3:\n  depends_on: []\n  implements: [FR-004]\n"
    )

    with pytest.raises(DerivationError) as caught:
        derive_text(respecified(block))

    faults = caught.value.rejections
    assert (faults[0].rule, faults[0].story) == ("acyclic", "US1")
    assert "US1" in str(faults[0]) and "US2" in str(faults[0])


# The crossover epic, for real (005 T030) -------------------------------------
#
# Everything above compiles fixtures written to exercise the grammar. This
# section compiles the spec the factory is actually going to be handed: 003, the
# epic it dispatches against this repository with the operator as merge queue
# (D-024). A fixture proves the deriver reads the grammar; only the real spec
# proves the grammar can express a real epic — and this is the crossover's input,
# so a defect here is a defect in the first live run, not in a test.


#: The repository root: `tests/` sits directly beneath it.
REPO_ROOT = Path(__file__).resolve().parents[1]

#: The epic the factory builds by dispatching itself (constitution I, D-024).
CROSSOVER = "003-merge-queue"


def crossover_graph() -> WorkGraph:
    """003's spec, compiled as `factory-epic derive` will compile it.

    Read from disk on purpose: this is the one case in the suite whose input is
    not a fixture the test controls, which is exactly what makes it worth having.
    Identity is still the caller's — the target repo is this repository, since
    that is what the crossover builds against.
    """
    spec = (REPO_ROOT / "specs" / CROSSOVER / "spec.md").read_text(encoding="utf-8")
    return derive_workgraph(
        spec,
        epic_id=CROSSOVER,
        feature=CROSSOVER,
        specs_root=SPECS_ROOT,
        target_repo=str(REPO_ROOT),
    )


def test_the_crossover_epic_compiles_into_exactly_three_nodes() -> None:
    """003 derives, and into the graph its stories describe.

    The whole value is asserted rather than sampled, for the same reason the
    fixture's acceptance case is: these three nodes are three branches, three
    virtual keys and three agent attempts against this repository, and the
    `requirement_keys` are what the judge will be handed. The edge is the one the
    spec argues for in prose — recovery (US2) reads the landing path US1 builds,
    while onboarding validation (US3) waits on neither.
    """
    assert crossover_graph() == WorkGraph(
        epic_id=CROSSOVER,
        feature=CROSSOVER,
        specs_root=SPECS_ROOT,
        target_repo=str(REPO_ROOT),
        nodes=[
            WorkNode(
                id="us1",
                story_key="US1",
                persona=IMPLEMENTER,
                spec_ref=f"{CROSSOVER}:US1",
                requirement_keys=[
                    "US1",
                    "FR-001",
                    "FR-002",
                    "FR-003",
                    "FR-004",
                    "FR-009",
                ],
                depends_on=[],
                depends_on_merged=[],
                timeout_override_s=None,
            ),
            WorkNode(
                id="us2",
                story_key="US2",
                persona=IMPLEMENTER,
                spec_ref=f"{CROSSOVER}:US2",
                requirement_keys=["US2", "FR-005", "FR-006", "FR-007", "FR-008"],
                depends_on=["us1"],
                depends_on_merged=[],
                timeout_override_s=None,
            ),
            WorkNode(
                id="us3",
                story_key="US3",
                persona=IMPLEMENTER,
                spec_ref=f"{CROSSOVER}:US3",
                requirement_keys=["US3", "FR-010"],
                depends_on=[],
                depends_on_merged=[],
                timeout_override_s=None,
            ),
        ],
    )


def test_every_requirement_003_declares_is_claimed_by_exactly_one_node() -> None:
    """No FR is orphaned, and none is verified twice.

    `coverage` already guarantees every story is a node; nothing in the grammar
    guarantees the same of the requirement bullets, because a spec may legitimately
    declare an FR no single story owns. For *this* epic it would be a hole: an
    unclaimed FR is a requirement the factory builds nothing for and no node is
    verified against, and a doubly-claimed one splits the verdict for one
    requirement across two nodes. Asserting it here also catches the drift case —
    an FR-011 added to 003 later without a home in the graph.
    """
    claimed = [
        key
        for node in crossover_graph().nodes
        for key in node.requirement_keys
        if key.startswith("FR-")
    ]
    declared = [
        requirement.key
        for requirement in parse_spec(
            (REPO_ROOT / "specs" / CROSSOVER / "spec.md").read_text(encoding="utf-8")
        )
        if requirement.kind is RequirementKind.FUNCTIONAL
    ]

    assert sorted(claimed) == declared
    assert len(claimed) == len(set(claimed))


def test_the_crossover_graph_passes_start_time_validation() -> None:
    """Against the shipped registry, not a stub — `start` will use that one.

    The fixture case validates against a hand-built persona; this one asks
    whether the graph this repo will actually run resolves in `personas.yaml` as
    committed, timeout included (R8). A persona rename that broke it would
    otherwise surface as `GRAPH_INVALID` at the moment an operator starts the
    crossover epic.
    """
    validate_workgraph(crossover_graph(), load_personas())
