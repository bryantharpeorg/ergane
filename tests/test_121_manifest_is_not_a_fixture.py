"""121-US1: the operator's manifest is checked for validity, not for content.

Spec 121 exists because two tests in `tests/test_factory_yaml.py` read this
repository's live `ergane.yaml` and froze its parsed value — one at
`assert config.version == 1`, the other at a whole-`FactoryConfig` identity
whose `ladder=VerificationConfig()` line made *any* declared ladder fail. The
manifest is the operator's file: every dial it carries is a dial the operator is
meant to turn, which is why spec 023 added the `ladder:` block in the first
place, and freezing its parsed value means the operator cannot turn any of them
without reddening the gate every node of every epic must pass. This finding has
recurred four times on other surfaces (persona `context_window`, then `model`
twice) because each fix removed one literal; US1-S6 is the test that makes the
next one fail here instead of surprising an operator.

The line this module holds is the spec's own:

> A test may assert that the operator's live manifest is *valid*. It may not
> assert what the operator *chose*.

Parser behaviour is proved against committed samples under
`tests/fixtures/target_repo/manifests/`, which no operator edits and which can
therefore be frozen honestly. The live-manifest load itself survives (trap 1):
`test_erganes_declared_standards_document_exists` is the one place that catches
a stale `standards` path in seconds instead of on the first dispatched node,
hours in, and the standards control below proves that coverage survived.

FR-011 survives too, as US1-S5: a dispatched node still may not edit the
manifest, and the check that holds it to that now reads the relationship
between a node worktree's manifest and the landing branch's copy — a property
of *validity*, one the node cannot satisfy by choosing any particular value —
instead of the frozen-literal identity the old test enforced against the
operator's file.

Every test answers "what edit would make this fail?" in its docstring, the
convention `tests/test_forge_manifest.py` established one file away — the
neighbour this spec copies, down to calling the live manifest the file a node
may not edit.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from factory.verify.factory_yaml import (
    MANIFEST_NAME,
    FactoryConfigError,
    load_factory_config,
    parse_factory_config,
)
from factory.verify.models import FactoryConfig, VerificationConfig

REPO_ROOT = Path(__file__).resolve().parents[1]
OWN_MANIFEST = REPO_ROOT / MANIFEST_NAME

#: The sibling module this story edits. US1-S2 and US1-S6 are tests about *that
#: file's assertions*, so they read its source rather than importing it: an
#: import proves nothing about what the assertions say, and a source read is
#: what turns "trust me, the literals are gone" into a failing check.
TEST_FACTORY_YAML = REPO_ROOT / "tests" / "test_factory_yaml.py"

#: The committed sample T007 adds and T008 repoints the identity test at. Named
#: for the one condition it demonstrates, as its eleven neighbours are: it is
#: the file whose bytes are the frozen thing now.
SAMPLE_V1 = (
    REPO_ROOT / "tests" / "fixtures" / "target_repo" / "manifests" / "v1-sample.yaml"
)

#: A legal v2 ladder block — the dial the operator was refused. Every key is one
#: the parser accepts (spec 023's `_LADDER_KEYS` / `_LADDER_STRING_KEYS`), and
#: the values sit inside the published floors and ceilings (`opus-closer` is a
#: registered persona), so the only thing this copy can be refused for is the
#: thing this spec exists to remove.
DECLARED_LADDER = (
    "ladder:\n"
    "  max_attempts: 2\n"
    "  promotion_cycles: 1\n"
    "  promotion_persona: opus-closer\n"
)


# --- US1-S1: a declared ladder parses -----------------------------------------


def test_a_manifest_declaring_a_ladder_parses(tmp_path: Path) -> None:
    """US1-S1, plan trap 2. The scenario the whole spec exists for.

    Driven against a copy of the operator's manifest with a legal ladder block
    appended and the version bumped to 2 — the exact shape the suite refused —
    so the proof does not depend on the operator having declared one. Before
    this story the v1 vocabulary refused the key outright; after T008 the
    identity test would have refused it a second way; either alone would have
    failed this test, which is why trap 2 insists both sites move.

    Mutation: restore `assert config.version == 1` or the whole-config identity
    in `tests/test_factory_yaml.py` — or make `_read_ladder` refuse a declared
    block — and this fails.
    """
    text = _live_manifest_copy_with_ladder()

    config = parse_factory_config(text, source="with-ladder")

    assert config.ladder.max_attempts == 2
    assert config.ladder.promotion_cycles == 1
    assert config.ladder.promotion_persona == "opus-closer"


def test_a_ladder_carrying_copy_of_the_live_manifest_is_valid() -> None:
    """US1-S1's second half: the copy must be *valid*, not merely parseable.

    Appending a ladder and bumping the version exercises the same read the gate
    runner makes of a node worktree, so the copy's `runtime` and gates — the
    things a node reads to learn what "green" means — must survive it.

    Mutation: make `_read_runtime` or `_read_gates` refuse a manifest that
    carries the optional v2 blocks and this fails.
    """
    config = parse_factory_config(
        _live_manifest_copy_with_ladder(), source="operator-shape"
    )

    assert config.runtime
    assert config.gates, "a valid manifest declares at least one gate"


def _live_manifest_copy_with_ladder() -> str:
    """The live manifest with a `ladder:` declared, as text.

    The operator's file is read and *copied*, never asserted against: appending
    is how an operator declares the block, so the copy is the operator's own
    declared state plus the dial this spec unblocks. No value the operator
    chose is pinned here — this module asserts only that the copy is valid.
    """
    text = OWN_MANIFEST.read_text(encoding="utf-8").replace("version: 1", "version: 2", 1)
    return text.rstrip("\n") + "\n" + DECLARED_LADDER


# --- US1-S2: no live-manifest test names a schema version ---------------------


def test_no_live_manifest_test_names_a_schema_version() -> None:
    """US1-S2, FR-001. A version is an operator's choice, so no assertion read
    against the operator's manifest may name a version number.

    Today the offending line is `test_erganes_own_manifest_loads`'s
    `assert config.version == 1`. The assertions are located by the
    `REPO_ROOT / MANIFEST_NAME` load each test performs — the only way a test
    gets the operator's config — so a version assertion written into any
    *other* live-manifest test is covered by having been written (the shape
    this finding keeps returning in).

    Sample-facing and rejection-table version assertions are out of scope by
    construction: they follow a `parse_factory_config(text)` or a load of a
    committed sample, and never touch `REPO_ROOT / MANIFEST_NAME`.

    Mutation: reintroduce `assert config.version == 1` into
    `test_erganes_own_manifest_loads` (or any live-manifest block) and this
    fails naming the line.
    """
    source = TEST_FACTORY_YAML.read_text(encoding="utf-8")

    offenders = [
        line.strip()
        for block in _live_manifest_assertion_blocks(source)
        for line in block.splitlines()
        if re.search(r"\bversion\b", line) and re.search(r"==|!=|is\b|>>>|not in", line)
    ]
    assert offenders == [], offenders


# --- US1-S3: the standards control must survive -------------------------------


async def test_a_manifest_whose_standards_path_is_absent_still_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US1-S3, FR-004, plan trap 1 — the control.

    The live-manifest load's real job is catching a stale `standards` path in
    seconds, where the first dispatched node would surface it as `CONFIG_ERROR`
    hours in. The cheap fix this spec refuses is to stop reading the operator's
    file; this proves the refusal that load protects did not quietly go away.

    The parser stays pure (shape only), so a declared-but-absent file is
    refused at dispatch — `prepare_worktree` → `_require_standards` — the seam
    a live dispatch actually hits. Driven here against a real repository whose
    manifest declares a document it does not carry, and the refusal must name
    the missing file.

    Mutation: drop the existence check in `_require_standards` (or its
    non-retryable classification) and this fails; a later edit that deletes the
    live load in `test_erganes_declared_standards_document_exists` is caught by
    `test_the_live_manifest_load_survives` beside the control.
    """
    from temporalio.exceptions import ApplicationError

    from factory.activities.agent_activities import (
        STANDARDS_MISSING,
        PrepareWorktreeInput,
        prepare_worktree,
    )
    from tests.target_repo import build_target_repo

    # Declared, never ambient (constitution IX): the runtime root the activity
    # resolves is pointed into the scratch tree, so the test writes nothing to
    # the worker host's own `.ergane/` and depends on no ambient root.
    monkeypatch.setenv("ERGANE_ROOT", str(tmp_path / "runtime"))

    repo = build_target_repo(tmp_path / "standards-control", variant="passing")
    declared = "docs/STANDARDS.md"
    # The skeleton ships `docs/STANDARDS.md` (121's own v1 sample declares it),
    # so the control removes it and commits the removal: the worktree is
    # checked out from the repo's HEAD, so a deletion left uncommitted would
    # still be present in the tree the check inspects, and the stale path would
    # never go stale.
    from tests.target_repo import git

    (repo / declared).unlink()
    git(repo, "add", "-A")
    git(repo, "commit", "--quiet", "-m", "remove the declared standards document")

    with pytest.raises(ApplicationError) as raised:
        await ActivityEnvironment().run(
            prepare_worktree,
            PrepareWorktreeInput(
                epic_id="121",
                node_id="us1",
                target_repo=str(repo),
                standards=declared,
            ),
        )

    message = str(raised.value)
    assert declared in message, message
    assert MANIFEST_NAME in message, message
    assert raised.value.type == STANDARDS_MISSING


def test_the_live_manifest_load_survives() -> None:
    """The load half of the control (trap 1), read from source.

    `test_erganes_declared_standards_document_exists` must keep reading the
    operator's file: it is the one place that catches a stale path before a
    live dispatch pays for it. The load is located by its
    `REPO_ROOT / MANIFEST_NAME` read, so a rename cannot outflank the check —
    a module with zero live-manifest reads fails here just as hard.

    Mutation: delete the live-manifest load anywhere in the sibling module and
    this fails.
    """
    source = TEST_FACTORY_YAML.read_text(encoding="utf-8")

    assert "def test_erganes_declared_standards_document_exists" in source, (
        "the standards-document existence test must survive (FR-004)"
    )
    assert source.count("REPO_ROOT / MANIFEST_NAME") >= 1, (
        "the live-manifest load must survive (trap 1)"
    )
    blocks = _live_manifest_assertion_blocks(source)
    assert len(blocks) >= 2, "live-manifest assertion blocks went missing"


# --- US1-S4: the v1 regression fixture lives on the committed sample ----------


def test_the_v1_sample_is_a_v1_manifest() -> None:
    """US1-S4, FR-005, plan trap 4 — the sample is v1, provably.

    The regression fixture proves *v1 semantics never moved*. A sample copied
    from the operator's manifest after their ladder lands would be v2 and would
    prove something else, and nothing else in the suite would notice. Two pins
    here: the v2-only keys are absent from the sample's parsed document, and
    the parser read the file back as version 1 with the v1-only defaults. The
    forge corpus (`FIXTURE_MANIFESTS` rglobs every `*.yaml` under the fixture
    root) asserts only forge resolution, so this is the guard that keeps the
    sample the thing its name says it is.

    Mutation: overwrite the sample with today's `ergane.yaml` after the
    operator's ladder lands, or otherwise make it v2, and this fails.
    """
    assert SAMPLE_V1.is_file(), SAMPLE_V1

    import yaml

    document = yaml.safe_load(SAMPLE_V1.read_text(encoding="utf-8"))
    for key in ("ladder", "verify"):
        assert key not in document, (
            f"{SAMPLE_V1.name} must not declare the v2 key {key!r}: "
            "its committed bytes are the v1 fixture (trap 4)"
        )

    config = load_factory_config(SAMPLE_V1)
    assert config.version == 1
    assert config.ladder == VerificationConfig()
    assert config.verify_order == ("gates", "diff_check", "judge")


def test_v1_parse_shape_change_fails_against_the_committed_sample() -> None:
    """US1-S4: v1 semantics are frozen on the sample, field for field.

    This is the coverage FR-007 forbids deleting, restated where it now lives.
    The comparison is deliberately the same whole-`FactoryConfig` identity the
    sibling module carries against the sample after T008, so a v1 semantic that
    moves — a default that changes, a reader that normalises — fails *here*
    rather than only in a test this story owns.

    Mutation: change any `FactoryConfig` default or any v1 reader in
    `factory/verify/factory_yaml.py` and this fails naming the difference.
    """
    config = load_factory_config(SAMPLE_V1)

    assert config == FactoryConfig(
        version=1,
        runtime="bwrap",
        gates={
            "lint": "bash gates/lint.sh",
            "test": "bash gates/test.sh",
            "typecheck": "bash gates/typecheck.sh",
        },
        standards="docs/STANDARDS.md",
        timeouts={"lint": 30},
        ladder=VerificationConfig(),
        verify_order=("gates", "diff_check", "judge"),
    )


def test_the_v1_identity_test_reads_the_sample_not_the_operator() -> None:
    """US1-S4's second half: the moved fixture must actually have moved.

    T008's edit is a repoint, and a repoint that leaves the operator's file in
    one of the two loads would keep the freeze half alive. This reads the
    sibling module's source and requires the v1-identity test to load the
    committed sample and to no longer load `REPO_ROOT / MANIFEST_NAME`.

    Mutation: repoint the identity test back at the operator's manifest and
    this fails; US1-S6 fails with it.
    """
    source = TEST_FACTORY_YAML.read_text(encoding="utf-8")

    body = _function_body(source, "test_v1_identity_against_erganes_own_manifest")
    assert body is not None, (
        "the v1 identity test must keep existing (FR-007, trap 3)"
    )
    assert "REPO_ROOT / MANIFEST_NAME" not in body, (
        "the v1 identity test must not read the operator's manifest (FR-002)"
    )
    assert str(SAMPLE_V1.relative_to(REPO_ROOT)) in body or "SAMPLE" in body, (
        "the v1 identity test must read the committed sample (FR-005)"
    )


def test_the_v1_identity_test_still_compares_field_for_field() -> None:
    """US1-S4's third half: FR-007 forbids passing by deleting the comparison.

    The identity test is the parser regression fixture spec 023 put in place.
    Moved, it must keep comparing the *whole* config — a rewrite into spot
    assertions would let a v1 default drift while every spot assert stays
    green, which is exactly the silent under-verification this component
    refuses everywhere else. The `FactoryConfig(` construction is the
    field-for-field shape; its absence means the comparison was diluted.

    Mutation: replace the identity comparison with a handful of spot asserts
    and this fails.
    """
    source = TEST_FACTORY_YAML.read_text(encoding="utf-8")

    body = _function_body(source, "test_v1_identity_against_erganes_own_manifest")
    assert body is not None, "the v1 identity test must keep existing (trap 3)"
    assert "FactoryConfig(" in body, (
        "the v1 identity test must still compare whole-config, field for field"
    )


# --- US1-S5: a node's worktree manifest may not differ -----------------------


def test_a_node_whose_worktree_manifest_differs_is_refused_naming_the_file(
    tmp_path: Path,
) -> None:
    """US1-S5, FR-006. The FR-011 invariant, asserted where it is enforced.

    `ensure` (or the check that runs at its seam) refuses a node worktree
    whose manifest differs from the landing branch's copy — the state a node
    reaches by editing the file its dispatch started from. The refusal names
    the file, because that is the thing an operator would go look at.

    The control: an untouched worktree agrees, so the refusal is about the
    edit and not about the topology.

    Mutation: delete `_worktree_manifest_is_untouched`'s comparison, or make
    it return agreement on a mismatched worktree, and this fails; drop the
    filename from the refusal and this fails naming what went missing.
    """
    from factory.workgraph import worktree as worktrees
    from tests.target_repo import build_target_repo

    factory_root = tmp_path / "runtime"
    repo = build_target_repo(tmp_path / "target", variant="passing")

    prepared = worktrees.ensure(repo, "121", "us1", factory_root=factory_root)
    untouched = _worktree_manifest_is_untouched(Path(prepared.path), repo)
    assert untouched is None, untouched

    # The node rewrites its manifest — the one edit this story exists to refuse.
    manifest = Path(prepared.path) / MANIFEST_NAME
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace("version: 1", "version: 2", 1)
        + DECLARED_LADDER,
        encoding="utf-8",
    )

    refusal = _worktree_manifest_is_untouched(Path(prepared.path), repo)
    assert refusal is not None, "the edit must be refused, or the check proves nothing"
    assert MANIFEST_NAME in refusal, refusal


def test_a_node_that_commits_a_manifest_edit_is_still_refused(tmp_path: Path) -> None:
    """Salvage commits whatever a node left, so a node's edit usually arrives
    *as a commit* — the committed shape must be refused just as the dirty one
    is. This is the shape that reached landing in the D-051 incidents: clean,
    committed, plausible.

    Mutation: compare the working file instead of the committed tree and this
    fails.
    """
    from factory.workgraph import worktree as worktrees
    from tests.target_repo import build_target_repo, git

    factory_root = tmp_path / "runtime"
    repo = build_target_repo(tmp_path / "target", variant="passing")

    prepared = worktrees.ensure(repo, "121", "us2", factory_root=factory_root)
    manifest = Path(prepared.path) / MANIFEST_NAME
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace("version: 1", "version: 2", 1)
        + DECLARED_LADDER,
        encoding="utf-8",
    )
    from tests.target_repo import git

    git(Path(prepared.path), "add", "-A")
    git(Path(prepared.path), "commit", "--quiet", "-m", "declared a ladder")

    refusal = _worktree_manifest_is_untouched(Path(prepared.path), repo)
    assert refusal is not None, "the committed edit must be refused too"
    assert MANIFEST_NAME in refusal, refusal


def test_this_repositorys_node_worktree_agrees_with_the_landing_branch() -> None:
    """The check applied to this repository — the invariant, in force.

    This repository *is* the factory's first self-target (D-024): the gate runs
    this suite inside a node worktree, so this is the line that turns "a node
    edited `ergane.yaml`" into a red gate naming the file, today and on every
    future dispatch. In the landing branch's own checkout — the operator clone,
    or any plain clone — there is no node and the check passes.

    Mutation: edit `ergane.yaml` in a node worktree of this repo and that
    node's gate fails here, naming the file.
    """
    assert _worktree_manifest_is_untouched(REPO_ROOT, REPO_ROOT) is None


def _worktree_manifest_is_untouched(worktree: Path, repo: Path) -> str | None:
    """`None` when the worktree's manifest is the landing branch's, else why not.

    The check FR-011 asks for: the manifest a node *has* must be the manifest
    it was dispatched with — the landing branch's copy at the worktree's own
    branch point. A node's edit (dirty or committed) moves the worktree's copy
    away from that; the operator's own moves on the landing branch do not
    appear, because the branch point is fixed at dispatch and a rewritten
    manifest is re-read when `ensure` rebuilds the worktree.

    Topology decides who the check applies to: in a linked worktree the two
    `--git-dir`s differ, and the comparison runs; in the landing branch's own
    checkout they are one directory, there is no node, and the check is
    vacuously satisfied. The landing branch is read from the manifest that
    declares it (`landing_branch:`), never guessed from the checkout, and an
    unresolvable branch is a refusal — never a pass.

    Raises `WorktreeError` when git cannot answer at all, so a worktree whose
    topology cannot be established is not silently waved through (FR-006).
    """
    from factory.workgraph.worktree import WorktreeError, resolve_landing_base

    def _git(*args: str) -> str:
        completed = subprocess.run(
            ["git", "-C", str(worktree), *args],
            capture_output=True,
            text=True,
            check=True,
        )
        return completed.stdout.strip()

    git_dir = Path(_git("rev-parse", "--absolute-git-dir")).resolve()
    common_dir = Path(_git("rev-parse", "--git-common-dir")).resolve()
    if git_dir == common_dir:
        # The landing branch's own checkout: there is no node, so there is
        # nothing for the check to refuse.
        return None

    declared = resolve_landing_base(worktree)
    if not declared.declared:
        raise WorktreeError(
            f"{MANIFEST_NAME} could not be read in {worktree} "
            f"({declared.detail}); the manifest a node's worktree starts "
            "from must be readable"
        )

    base = _git("merge-base", "HEAD", declared.branch)
    committed = subprocess.run(
        ["git", "-C", str(repo), "show", f"{base}:{MANIFEST_NAME}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if committed.returncode != 0:
        raise WorktreeError(
            f"{MANIFEST_NAME} is not in {base}, the commit on "
            f"{declared.branch} this worktree branched from: {committed.stderr.strip()}"
        )

    here = (worktree / MANIFEST_NAME).read_text(encoding="utf-8")
    if here == committed.stdout:
        return None
    return (
        f"the node worktree's {MANIFEST_NAME} differs from {declared.branch}'s copy "
        f"at the commit this worktree was pinned to ({base[:12]}); a dispatched "
        f"node may not edit the manifest — revert it in {worktree / MANIFEST_NAME}"
    )


# --- US1-S6: the anti-recurrence guard — assertions follow from validity -----


def test_every_live_manifest_assertion_follows_from_validity_not_choice() -> None:
    """US1-S6, FR-007, plan trap 7 — the guard that makes the fifth recurrence
    fail a test instead of surprising an operator.

    Reads the sibling module's source and requires every assertion made in a
    live-manifest test (one that loads `REPO_ROOT / MANIFEST_NAME`) to be one
    of the allowed shapes. The allow-list is the point, and each entry names
    why it is not a pinned dial:

    - the standards path and the landing branch: documented operator facts a
      node reads — the landing-branch comment in the live test itself records
      that line as an operator *action*, not a choice among dial values;
    - the declared gate commands: what every dispatched node is told "green"
      means, and the reason a red suite here reds every node;
    - truthiness and shape (`config.runtime`, `is not None`, `.is_file()`):
      derivable from the manifest being *valid*.

    Everything else in a live-manifest assertion — a version number, a ladder
    block, a forge name, an equality against any other literal the operator
    could choose — fails, and so does a whole-`FactoryConfig` comparison,
    which is the shape that pinned `ladder` to its default.

    Mutation: add `assert config.version == 1`, any `assert config.ladder …`,
    or any comparison naming an operator-chosen literal to a live-manifest
    test, and this fails naming the line.
    """
    source = TEST_FACTORY_YAML.read_text(encoding="utf-8")
    blocks = _live_manifest_assertion_blocks(source)
    assert len(blocks) >= 2, "live-manifest assertion blocks went missing"

    offences: list[str] = []
    for block in blocks:
        for line in block.splitlines():
            verdict = _classify_live_assertion(line)
            if verdict is not None:
                offences.append(f"{line.strip()} — {verdict}")
    assert offences == [], offences


def _classify_live_assertion(line: str) -> str | None:
    """Why one `assert` line in a live-manifest test is a pin, or `None`.

    Three shapes pass, everything else offends:

    - a comparison against one of the documented operator facts;
    - a truthiness or shape check (`config.runtime`, `is not None`,
      `.is_file()`), which follows from the manifest being *valid*;
    - nothing else. In particular a `FactoryConfig(` comparison — the
      whole-config identity this story removes — and any version comparison
      offend, as does any comparison naming a literal that is not on the
      allow-list: the fifth recurrence reaches for a convenient literal, and
      the only honest guard is one where the literal has to be admitted here,
      with a reason, before a test can assert it.
    """
    stripped = line.strip()
    if not stripped.startswith("assert "):
        return None

    # The whole-config comparison is refused by shape, before any literal is
    # looked up: it pins every dial at once, which is the defect's strongest
    # form (023's `ladder=VerificationConfig()` line).
    if "FactoryConfig(" in stripped:
        return "asserts the operator's whole config against a frozen value (FR-002)"

    ALLOWED_FACTS = (
        ".specify/memory/constitution.md",
        "ergane-buildout",
        "uv run pytest -q",
    )
    for literal in ALLOWED_FACTS:
        if literal in stripped:
            return None

    # Truthiness / shape checks are assertions about validity, not choice.
    TRUTHY = re.compile(
        r"^assert ((not )?\w+\.\w+|\w+\.\w+ (is not None|is None|is_file\(\)))$"
    )
    if TRUTHY.match(stripped):
        return None

    return (
        "names a value that is neither a documented operator fact nor a "
        "validity check; to assert it against the operator's manifest, add it "
        "to the allow-list with a reason in the guard's docstring"
    )


def test_the_version_guard_reads_every_current_live_block() -> None:
    """US1-S2 and US1-S6 share a locator; this keeps the locator honest.

    A locator that matched nothing would pass both guards forever — the
    corpus-is-asserted-non-empty lesson the forge suite's glob comment states.
    The count pinned here is the sibling module's live-manifest tests today
    (the loader and the standards-document check).

    Mutation: delete a live-manifest test — or the locator's load detection —
    and this fails.
    """
    source = TEST_FACTORY_YAML.read_text(encoding="utf-8")
    blocks = _live_manifest_assertion_blocks(source)
    assert len(blocks) >= 2, blocks


# --- helpers ------------------------------------------------------------------


def _live_manifest_assertion_blocks(source: str) -> list[str]:
    """Every top-level test in `test_factory_yaml.py` that reads the operator's
    manifest, as its assertion lines.

    Located structurally rather than by name: a test is a live-manifest test
    when its body contains a load of `REPO_ROOT / MANIFEST_NAME` — the only way
    a test in that module obtains the operator's config — and its assertion
    lines are the `assert` statements of that body. A test this story does not
    know about, or a rename of one it does, is covered by the structure rather
    than by a list.
    """
    blocks: list[str] = []
    for body in _top_level_function_bodies(source):
        if "REPO_ROOT / MANIFEST_NAME" not in body:
            continue
        kept = "\n".join(
            line for line in body.splitlines() if line.strip().startswith("assert ")
        )
        if kept:
            blocks.append(kept)
    return blocks


def _top_level_function_bodies(source: str) -> list[str]:
    """Bodies of every top-level function in a module's source, sans def line.

    Indentation-delimited: a top-level def starts at column 0, its body runs
    until the next line that is neither blank nor indented. Reading the source
    rather than importing is the honest way to guard assertions — an import
    says nothing about what the assertions say.
    """
    lines = source.splitlines()
    bodies: list[str] = []
    index = 0
    while index < len(lines):
        if re.match(r"^def \w+", lines[index]):
            body: list[str] = []
            cursor = index + 1
            while cursor < len(lines):
                line = lines[cursor]
                if line.strip() and not line[0].isspace():
                    break
                body.append(line)
                cursor += 1
            bodies.append("\n".join(body))
            index = cursor
        else:
            index += 1
    return bodies


def _function_body(source: str, name: str) -> str | None:
    """The body of exactly one top-level function, or `None` when absent."""
    for match in re.finditer(rf"^def {name}\(", source, flags=re.MULTILINE):
        lines = source.splitlines()
        start = source[: match.start()].count("\n")
        body: list[str] = []
        cursor = start + 1
        while cursor < len(lines):
            line = lines[cursor]
            if line.strip() and not line[0].isspace():
                break
            body.append(line)
            cursor += 1
        return "\n".join(body)
    return None


import temporalio.testing  # noqa: E402 — used as the activity harness below

ActivityEnvironment = temporalio.testing.ActivityEnvironment