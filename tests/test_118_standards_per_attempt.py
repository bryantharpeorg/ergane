"""US3 of epic 118: an attempt reads the standards on the landing branch.

`load_prompt_sources` reads the target repo's declared standards *path* once per
epic, and the prompt points the agent at that path "in this worktree" — so a
correction the operator lands on the landing branch mid-epic never reaches the
next attempt of a running node: the retry re-opens the tree the pin branched,
and the tree's copy predates the correction. Measured live on 2026-08-28
(spec 118's second finding): a documentation fix landed during a running epic
was re-read in its pre-fix form by attempts 4, 5 and 6.

The fix this story is verified against has three parts:

- **Per attempt, the caller resolves the text from the landing branch** — the
  caller that already reads the repository, so the builder stays pure (trap 6:
  the prompt module keeps taking a location and gains no git opinion).
- **Any read failure falls back to the pinned tree's copy**, and the fallback
  is reported — a node must not fail to start because a document could not be
  fetched (trap 7).
- **The archived prompt records the source** — landing branch or pinned tree —
  because a prompt that changes no verdict still needs to be auditable (trap 8).

Five tests, one per acceptance scenario plus the purity control (T021):

- T017 — a correction landed after dispatch reaches the next attempt (US3-S1).
- T018 — an unreadable landing branch falls back, reports it, does not fail the
  attempt (US3-S2; two arms: a path absent on the landing branch, and a landing
  branch a fetch cannot reach).
- T019 — the archived prompt records the source (US3-S3), both arms.
- T020 — a repo declaring no standards path behaves exactly as today (US3-S4).
- T021 — the builder still takes a path and reads no repository (FR-008, trap 6).

These run the real activity in `ActivityEnvironment` against a real git
repository, the same way `tests/test_agent_activities.py` runs
`prepare_worktree`: git is the thing being claimed about, and a fake would
prove nothing about a fetch, a `show`, or a ref.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest
from temporalio import activity  # noqa: F401  (env.run over @activity.defn)
from temporalio.testing import ActivityEnvironment

from factory.activities.agent_activities import (
    LoadPromptSourcesInput,
    ResolveStandardsInput,
    load_prompt_sources,
    resolve_standards,
)
from factory.workgraph.models import (
    STANDARDS_SOURCE_LANDING,
    STANDARDS_SOURCE_PINNED,
    StandardsResolution,
)
from factory.workgraph.prompt import build_attempt_prompt
from factory.workgraph.worktree import PreparedWorktree, branch_name, ensure
from factory.workgraph.models import WorkNode
from tests.target_repo import git

EPIC = "118-a-verified-tree-is-the-tree-that-will-merge"
NODE = "us3"
BRANCH = branch_name(EPIC, NODE)

#: The declared standards path, planted by the setup helper below onto a copy
#: of the fixture repo whose own manifest declares no standards at all.
STANDARDS_PATH = "docs/notes.md"

#: The document's authored content, distinctive so a stale read cannot pass.
ORIGINAL_TEXT = "PIN-118-ORIGINAL: no correction has landed yet."
CORRECTED_TEXT = "PIN-118-CORRECTED: the operator's fix, landed mid-epic."

#: Minimal authored texts, the shape `build_attempt_prompt` cuts a prompt from.
PLAN_TEXT = "# Plan\n"
SPEC_TEXT = "# Spec\n\n## User Story 1 - Do the thing (Priority: P1)\n\nBody.\n"
TASKS_TEXT = "# Tasks\n\n## Phase 1: User Story 1 - Do the thing\n\n- [ ] T001 Do it\n"


# --- setup --------------------------------------------------------------------


def _node() -> WorkNode:
    return WorkNode(
        id=NODE,
        story_key="US1",
        persona="implementer",
        spec_ref="demo:US1",
        requirement_keys=["US1"],
        depends_on=[],
    )


def _prompt(resolution: StandardsResolution | None) -> str:
    return build_attempt_prompt(
        node=_node(),
        epic_id=EPIC,
        spec_text=SPEC_TEXT,
        plan_text=PLAN_TEXT,
        tasks_text=TASKS_TEXT,
        standards=STANDARDS_PATH,
        standards_resolution=resolution,
    )


def _declare_standards(repo: Path) -> None:
    """Commit `standards:` into the target repo's manifest (fixture bookkeeping).

    The shipped fixture manifest declares no standards key — the ordinary case
    and the shape US3-S4's control needs — so the repo this helper edits is the
    control repo plus one committed edit, and the variant bookkeeping in
    `tests/target_repo.py` stays untouched by this story.
    """
    manifest = repo / "ergane.yaml"
    text = manifest.read_text(encoding="utf-8")
    assert "standards:" not in text, "fixture manifest grew a standards key"
    manifest.write_text(text + "\nstandards: docs/notes.md\n", encoding="utf-8")
    (repo / STANDARDS_PATH).write_text(ORIGINAL_TEXT + "\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "--quiet", "-m", "declare standards for epic 118's US3 tests")


@pytest.fixture
def env() -> ActivityEnvironment:
    return ActivityEnvironment()


@pytest.fixture
def factory_root(tmp_path: Path) -> Path:
    return tmp_path / ".ergane"


@pytest.fixture
def declared_repo(target_repo, factory_root) -> Path:
    """A target repo that declares `standards:`, with the node's tree prepared.

    Prepared at fixture time — the scenarios are then about what the *next*
    preparation happens to read.
    """
    repo = target_repo("passing")
    _declare_standards(repo)
    prepared: PreparedWorktree = ensure(repo, EPIC, NODE, factory_root=factory_root)
    assert (Path(prepared.path) / STANDARDS_PATH).is_file()
    return repo


async def _resolve(env: ActivityEnvironment, repo: Path, worktree: Path):
    return await env.run(
        resolve_standards,
        ResolveStandardsInput(
            target_repo=str(repo),
            worktree_path=str(worktree),
            standards=STANDARDS_PATH,
        ),
    )


# --- T017 (US3-S1): a correction landed after dispatch reaches the next attempt


async def test_a_correction_landed_after_dispatch_reaches_the_next_attempt(
    env, declared_repo, factory_root
) -> None:
    """The standards text the next attempt is prepared with is the updated one.

    First preparation resolves the document as it stood (the pinned copy);
    the operator's correction lands on the landing branch; the second
    resolution — the node's next attempt — carries the updated text, while the
    worktree still holds the old copy. That gap is the defect: only per-attempt
    resolution crosses it.
    """
    worktree = factory_root / "worktrees" / EPIC / NODE

    first = await _resolve(env, declared_repo, worktree)
    assert first.source == STANDARDS_SOURCE_LANDING
    assert ORIGINAL_TEXT in first.text
    assert CORRECTED_TEXT not in first.text

    # The operator lands the correction on the landing branch.
    (declared_repo / STANDARDS_PATH).write_text(CORRECTED_TEXT + "\n", encoding="utf-8")
    git(declared_repo, "add", "-A")
    git(declared_repo, "commit", "--quiet", "-m", "the operator's correction")

    second = await _resolve(env, declared_repo, worktree)
    assert second.source == STANDARDS_SOURCE_LANDING
    assert CORRECTED_TEXT in second.text
    assert ORIGINAL_TEXT not in second.text
    # The pinned tree was not touched — no rebase, no reset (FR-004/FR-010).
    assert ORIGINAL_TEXT in (worktree / STANDARDS_PATH).read_text(encoding="utf-8")

    # US3-S1's proof is about the prompt: the text the prompt refers to is the
    # updated one.
    prompt = _prompt(second)
    assert CORRECTED_TEXT in prompt
    assert ORIGINAL_TEXT not in prompt


# --- T018 (US3-S2, trap 7): an unreadable landing branch falls back


async def test_a_landing_branch_that_lacks_the_document_falls_back_to_the_pinned_copy(
    env, declared_repo, factory_root
) -> None:
    """A path that does not exist on the landing branch is a fallback, not a
    dead node: the pinned tree's copy is used and the fallback is reported."""
    worktree = factory_root / "worktrees" / EPIC / NODE
    # Land a commit that removes the document from the landing branch — the
    # "path may not exist yet" shape of unreadable.
    (declared_repo / STANDARDS_PATH).unlink()
    git(declared_repo, "add", "-A")
    git(declared_repo, "commit", "--quiet", "-m", "remove the document upstream")

    resolved = await _resolve(env, declared_repo, worktree)

    assert resolved.source == STANDARDS_SOURCE_PINNED
    assert ORIGINAL_TEXT in resolved.text
    assert ORIGINAL_TEXT in (worktree / STANDARDS_PATH).read_text(encoding="utf-8")
    assert resolved.detail
    # The prompt still carries the standards text, and it says where it came from.
    prompt = _prompt(resolved)
    assert ORIGINAL_TEXT in prompt
    assert STANDARDS_SOURCE_PINNED in prompt
    assert resolved.detail in prompt


async def test_an_unreachable_landing_branch_falls_back_and_does_not_fail_the_attempt(
    env, declared_repo, factory_root
) -> None:
    """A landing branch no fetch can reach is a transient condition, and trap 7
    says it may not cost an attempt: same fallback, same report, no exception."""
    worktree = factory_root / "worktrees" / EPIC / NODE
    git(declared_repo, "remote", "add", "origin", "/nonexistent/cannot-be-fetched.git")

    resolved = await _resolve(env, declared_repo, worktree)

    assert resolved.source == STANDARDS_SOURCE_PINNED
    assert ORIGINAL_TEXT in resolved.text
    assert resolved.detail


# --- T019 (US3-S3, trap 8): the archived prompt records the source


async def test_the_archived_prompt_records_which_source_the_standards_came_from(
    env, declared_repo, factory_root
) -> None:
    """Both answers are recorded: `landing-branch` when the landing branch
    answered, `pinned-tree` (with the reason) when it could not be read."""
    worktree = factory_root / "worktrees" / EPIC / NODE

    landed: StandardsResolution = await _resolve(env, declared_repo, worktree)
    assert STANDARDS_SOURCE_LANDING in _prompt(landed)

    # The fallback arm: the landing branch loses the document, so the next
    # attempt is prepared against the pinned copy — and that is what its
    # prompt must record, with the reason beside it.
    (declared_repo / STANDARDS_PATH).unlink()
    git(declared_repo, "add", "-A")
    git(declared_repo, "commit", "--quiet", "-m", "remove the document upstream")
    fallback: StandardsResolution = await _resolve(env, declared_repo, worktree)
    prompt = _prompt(fallback)
    assert STANDARDS_SOURCE_PINNED in prompt
    assert fallback.detail in prompt


# --- T020 (US3-S4): a repo declaring no standards path behaves as today


async def test_a_repo_declaring_no_standards_behaves_exactly_as_today(
    env, target_repo
) -> None:
    """No declared path means no resolution and an unchanged prompt: the
    fixture repo's manifest declares nothing, so `load_prompt_sources` reads
    standards as None, `resolve_standards` resolves nothing, and the assembled
    prompt is byte-identical to today's assembly."""
    repo = target_repo("passing")
    sources = await env.run(
        load_prompt_sources,
        LoadPromptSourcesInput(
            specs_root=str(Path("specs")),
            feature="118-a-verified-tree-is-the-tree-that-will-merge",
            target_repo=str(repo),
        ),
    )
    assert sources.standards is None

    assert (
        await env.run(
            resolve_standards,
            ResolveStandardsInput(
                target_repo=str(repo),
                worktree_path=str(repo),
                standards=None,
            ),
        )
        is None
    )

    as_today = build_attempt_prompt(
        node=_node(),
        epic_id=EPIC,
        spec_text=SPEC_TEXT,
        plan_text=PLAN_TEXT,
        tasks_text=TASKS_TEXT,
        standards=None,
    )
    unchanged = build_attempt_prompt(
        node=_node(),
        epic_id=EPIC,
        spec_text=SPEC_TEXT,
        plan_text=PLAN_TEXT,
        tasks_text=TASKS_TEXT,
        standards=None,
        standards_resolution=None,
    )
    assert unchanged == as_today
    assert "## Standards" not in unchanged


# --- T021 (FR-008, trap 6): the builder stays pure


def test_the_builder_still_takes_a_path_and_a_resolution_it_does_not_fetch() -> None:
    """`build_attempt_prompt` still takes the standards path, and the new
    resolution arrives as already-resolved data the builder never went to get.
    Purity is a documented property (prompt-assembly.md); US3 extends the
    builder without trading it away (trap 6)."""
    signature = inspect.signature(build_attempt_prompt)
    assert signature.parameters["standards"].default is None
    assert signature.parameters["standards_resolution"].default is None


def test_the_prompt_module_imports_no_filesystem_or_subprocess() -> None:
    """No filesystem or subprocess import anywhere in the prompt module, and no
    file read or process launch in the builder — text in, prompt out, and US3
    must not trade that away for a shortcut (trap 6)."""
    module_text = Path("factory/workgraph/prompt.py").read_text(encoding="utf-8")
    tree = ast.parse(module_text)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    offending = imported & {"subprocess", "shutil", "tempfile", "git", "pathlib"}
    assert not offending, (
        f"factory/workgraph/prompt.py imports {sorted(offending)} — the prompt "
        "builder has stopped being pure (trap 6)"
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {"open", "Popen", "run"}, (
                "the prompt module reaches the filesystem or a subprocess "
                f"through {node.func.id}() (trap 6)"
            )