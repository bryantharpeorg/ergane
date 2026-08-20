"""049-US6: the seam cannot silently re-leak.

A protocol with one implementation and no guard erodes back into a direct call
within a quarter. US1-US5 drew the seam; nothing in them stops the next
implementer reading `mergeStateStatus` from a module written in six months,
because every structural check those stories left names *one* place —
`onboard.py` (`tests/test_forge_readiness.py`), `classify.py` and the five
landing activities (`tests/test_forge_landing.py`). A module nobody thought of
escapes all of them silently. This file is the sweep with no such blind spot: it
reads every `.py` under `factory/` and holds forge-native vocabulary to a path
allowlist.

**By path, never by count** (US6-S1, FR-016). "At most four occurrences" passes
the day somebody deletes one and adds one somewhere new — the same defect
wearing a number. The allowlist is checked in both directions: a module outside
it may spell nothing, and a module inside it must still spell something, so an
entry cannot outlive the reason it was granted.

**Which modules may name a forge natively, and why** (T046). Four, and every one
is under `factory/mergequeue/` — FR-017 paying for itself, since the
merge-surface guards in `tests/test_mergequeue_sweep.py` are scoped to exactly
that directory:

- `gh.py` — the one place this component spawns `gh`. The GitHub forge's
  subprocess layer, kept by name in the spec's Out of Scope.
- `github_forge.py` — the implementation. Every GitHub spelling that answers
  Q1-Q5 is *meant* to be here; this is the module the seam exists to concentrate.
- `wiring.py` — 034/US3's rulesets writes: GitHub's answer to "make this branch
  gate, land and title", reached only through `apply_landing_policy` (FR-012).
- `models.py` — `PrSnapshot.from_gh_json`, GitHub's own payload reader. The
  record keeps its name by the spec's Out of Scope, and what mattered — the
  *decision* — moved to `in_conflict` in US3. The one entry here that is a record
  module rather than an implementation one, and so the one a later story could
  still tighten.

**Not swept, deliberately: the forge's own name.** `github` is a registry key
(`DEFAULT_FORGE`), a manifest value (`forge: github`) and a default on
`FactoryConfig`; FR-002 and FR-014 require it to be spellable, and a module
naming the forge it *resolved* is using the seam rather than going round it. What
had to stop travelling is the vocabulary of one forge's API and CLI, which is
what `FORGE_NATIVE_SPELLINGS` holds.

Case is load-bearing. `PR_TITLE` is GitHub's enum value and is swept; `pr_title`
is `factory/mergequeue/messages.py`'s renderer and is not, because "pull request"
is shared vocabulary Azure DevOps also speaks (spec § Out of Scope). `DIRTY` is
GitHub's `mergeStateStatus` value; `_is_dirty` in `factory/workgraph/worktree.py`
is git's word for an uncommitted tree and has nothing to do with a forge.

Docstrings are excluded, after `tests/test_final_sweep.py:551`: a module is
required to *explain* which forge it talks to, and saying so is not doing so.

The mutation transcript proving each test can fail is committed at
`specs/049-forge-seam/evidence/us6-mutations.md`.
"""

from __future__ import annotations

import ast
import dataclasses
import json
import re
from pathlib import Path

import pytest

from factory.mergequeue.forge import (
    Forge,
    LandingPolicy,
    Proposal,
    RepositoryDescription,
    WiringStep,
)
from tests.test_final_sweep import ENFORCEMENT_WORDS
from tests.test_mergequeue_sweep import COMMAND_MODULES

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPONENT_ROOT = REPO_ROOT / "factory"
FORGE_DIRECTORY = COMPONENT_ROOT / "mergequeue"

#: The shipped package, whole. Every module, not a chosen subset — a sweep that
#: picks its own targets never reaches the one written after it.
COMPONENT_MODULES = sorted(COMPONENT_ROOT.rglob("*.py"))
MODULE_IDS = [path.relative_to(REPO_ROOT).as_posix() for path in COMPONENT_MODULES]

#: Every module of the forge's own directory — derived, so a module added there
#: is enrolled by existing rather than by being remembered.
FORGE_DIRECTORY_MODULES = sorted(FORGE_DIRECTORY.rglob("*.py"))

FORGE_IMPLEMENTATION = "factory/mergequeue/github_forge.py"

#: One forge's API and CLI vocabulary. Every term here is a GitHub field name,
#: setting, ruleset type, enum value or binary — a spelling that means nothing on
#: a forge that never heard of it, which is the test trap 1 sets for a name.
FORGE_NATIVE_SPELLINGS = frozenset(
    {
        "nameWithOwner",
        "defaultBranchRef",
        "mergeStateStatus",
        "autoMergeRequest",
        "statusCheckRollup",
        "isDraft",
        "squash_merge_commit_title",
        "PR_TITLE",
        "merge_queue",
        "required_status_checks",
        "DIRTY",
        "gh",
    }
)

#: The four, by path. Read the module docstring for what each one bought.
NATIVE_VOCABULARY_ALLOWLIST = frozenset(
    {
        "factory/mergequeue/gh.py",
        FORGE_IMPLEMENTATION,
        "factory/mergequeue/wiring.py",
        "factory/mergequeue/models.py",
    }
)

#: The two files `tests/test_mergequeue_sweep.py` names *beside* the directory
#: glob, both predating this spec. US6-S3 turns on this staying exactly two: a
#: third would mean a forge module had been covered by an added entry rather than
#: by where FR-017 put it.
SWEPT_BESIDE_THE_FORGE_DIRECTORY = frozenset(
    {
        "factory/activities/merge_activities.py",
        "factory/workgraph/worktree.py",
    }
)

#: Trap 5's workaround, which US4 had to carry across the seam intact: GitHub's
#: rulesets API requires a field literally named `enforcement`, and
#: `ENFORCEMENT_WORDS` reserves that word for the spend enforcement D-021
#: deferred. So the payload lives in JSON and is never spelled in Python.
RULESET_DATA_FILE = FORGE_DIRECTORY / "merge_queue_ruleset.json"

_BOUNDED = {
    term: re.compile(rf"(?<![A-Za-z0-9_]){re.escape(term)}(?![A-Za-z0-9_])")
    for term in FORGE_NATIVE_SPELLINGS
}


def _spelled(tree: ast.Module) -> list[str]:
    """Every token the module's *code* spells, docstrings excluded.

    Identifiers, attributes, arguments, keywords, aliases and string constants —
    the same reach as `tests/test_final_sweep.py:551`, minus its lowercasing,
    because `PR_TITLE` and `pr_title` are different claims here.
    """
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        )
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }

    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.append(node.name)
        elif isinstance(node, ast.Name):
            out.append(node.id)
        elif isinstance(node, ast.Attribute):
            out.append(node.attr)
        elif isinstance(node, ast.arg):
            out.append(node.arg)
        elif isinstance(node, ast.keyword) and node.arg:
            out.append(node.arg)
        elif isinstance(node, ast.alias):
            out.extend(name for name in (node.name, node.asname) if name)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in docstrings:
                out.append(node.value)
    return out


def _native_spellings_in(path: Path) -> set[str]:
    """Which forge-native terms this module's code spells, as whole words."""
    tokens = _spelled(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
    return {
        term
        for term, pattern in _BOUNDED.items()
        if any(pattern.search(token) for token in tokens)
    }


# --- US6-S1 / FR-016: the allowlist is by path, and it is tight both ways ------


@pytest.mark.parametrize("path", COMPONENT_MODULES, ids=MODULE_IDS)
def test_forge_native_vocabulary_lives_only_where_the_allowlist_says(
    path: Path,
) -> None:
    """What edit would make this fail? Reading `mergeStateStatus`, `PR_TITLE` or
    `gh` from any module outside the four — which is what a re-leak looks like on
    the day it happens, long before anything misbehaves. It caught one already:
    `merge_activities.py`'s read-failure finding still said "via gh", prose US3
    deferred to US2 and US2 to nobody, and no per-module check either story wrote
    was pointed at it.

    The allowlisted branch asserts too, on purpose: an entry that has stopped
    spelling anything is a licence nobody spends, and a sweep whose allowlist only
    ever grows stops being a boundary.
    """
    where = path.relative_to(REPO_ROOT).as_posix()
    spelled = _native_spellings_in(path)

    if where in NATIVE_VOCABULARY_ALLOWLIST:
        assert spelled, (
            f"{where} is allowed to speak a forge's own vocabulary and no longer "
            "does; drop it from NATIVE_VOCABULARY_ALLOWLIST rather than leaving "
            "an entry nothing needs"
        )
        return

    assert spelled == set(), (
        f"{where} spells {sorted(spelled)} — one forge's own API vocabulary "
        "outside the modules FR-016 allows it in. Ask the forge instead, or say "
        "in the module docstring above why this module is the exception"
    )


# --- US6-S2 / FR-016: the sweep proves it read something -----------------------


def test_the_sweep_read_the_package_and_can_still_find_a_forge_native_term() -> None:
    """The anti-vacuity guard, after `tests/test_final_sweep.py:644`, which exists
    because a parametrized sweep over an empty file list passes forever without
    asserting anything.

    Three claims, and the third is the one that matters most. The file list is
    non-empty; it contains the forge implementation *by name*, plus three modules
    outside `factory/mergequeue/` so the sweep is shown to reach past the forge's
    own directory. And the same scanner, run over the implementation, still finds
    forge-native terms — so `spelled == set()` above means "absent" rather than
    "the extractor is broken". Point `COMPONENT_ROOT` at a path that does not
    exist and this is the test that goes red; the parametrized sweep above just
    collects nothing and says nothing.
    """
    assert COMPONENT_MODULES, "the sweep matched no module in factory/"
    swept = set(MODULE_IDS)

    assert FORGE_IMPLEMENTATION in swept
    assert NATIVE_VOCABULARY_ALLOWLIST <= swept
    # The three modules the seam exists to free: if the sweep stopped reaching
    # them it would be checking the forge against itself.
    assert {
        "factory/activities/merge_activities.py",
        "factory/workgraph/workflow.py",
        "factory/cli/init.py",
    } <= swept, sorted(swept)

    assert FORGE_NATIVE_SPELLINGS, "an empty term list forbids nothing"
    assert _native_spellings_in(REPO_ROOT / FORGE_IMPLEMENTATION) >= {
        "nameWithOwner",
        "squash_merge_commit_title",
        "PR_TITLE",
        "merge_queue",
        "gh",
    }


# --- US6-S3 / FR-017, trap 6: covered by construction, not by an added entry ---


def test_every_forge_module_is_guarded_because_of_where_it_lives() -> None:
    """"Covered" and "covered by construction" are different claims, and only the
    second survives the next refactor — so both halves are asserted here.

    `COMMAND_MODULES` is imported from the sweep that owns it, so a narrowed sweep
    fails here too. What edit would make this fail? Moving any forge module out of
    `factory/mergequeue/` — it drops out of the glob, and the three guards that
    keep this factory from deleting a branch, forcing a push or merging outside
    the queue stop covering it silently. Adding it back by name to
    `COMMAND_MODULES` does not repair this: that is what the last assertion
    refuses, because a promise the next implementer inherits is not a property the
    tree holds (FR-017).
    """
    assert COMMAND_MODULES, "the merge-surface sweep matched no module"
    assert FORGE_DIRECTORY_MODULES, "the forge directory matched no module"

    swept = {path.relative_to(REPO_ROOT).as_posix() for path in COMMAND_MODULES}
    in_directory = {
        path.relative_to(REPO_ROOT).as_posix() for path in FORGE_DIRECTORY_MODULES
    }

    assert {"factory/mergequeue/forge.py", FORGE_IMPLEMENTATION} <= in_directory
    # Every forge module is guarded, and every module allowed to speak a forge's
    # vocabulary is one of them.
    assert in_directory <= swept, sorted(in_directory - swept)
    assert NATIVE_VOCABULARY_ALLOWLIST <= in_directory

    # And the guards reached them through the directory glob. The named entries
    # beside it are the two that predate this spec, and no third.
    assert swept - in_directory == set(SWEPT_BESIDE_THE_FORGE_DIRECTORY)


# --- US6-S4: this spec spells none of the reserved vocabulary ------------------


def test_nothing_the_seam_declares_spells_a_reserved_word() -> None:
    """`ENFORCEMENT_WORDS` is imported rather than copied, so a word added to it
    reaches this seam without anyone remembering to come back.

    A forge operation named for what a forge *does to* a merge would fail
    `tests/test_final_sweep.py:588` on the word alone — a green implementation
    rejected on vocabulary. What edit would make this fail? Renaming
    `apply_landing_policy` to anything built on "enforce".
    """
    assert ENFORCEMENT_WORDS, "an empty reserved list reserves nothing"

    declared = [
        *(name for name in vars(Forge) if not name.startswith("_")),
        *(
            field.name
            for record in (RepositoryDescription, LandingPolicy, Proposal, WiringStep)
            for field in dataclasses.fields(record)
        ),
    ]
    # 25 until 069-US3 added the cleanup half's two operations. Pinned as a
    # literal so a seam that quietly stopped declaring names fails here rather
    # than passing over an empty list.
    assert len(declared) == 27, sorted(declared)

    spoken = sorted(
        {
            word
            for name in declared
            for word in re.findall(r"[A-Za-z]+", name.lower())
            if word in ENFORCEMENT_WORDS
        }
    )
    assert spoken == [], (
        f"the seam declares {spoken}, which `tests/test_final_sweep.py:462` "
        "reserves for the spend enforcement D-021 deferred"
    )


def test_the_word_the_package_may_not_spell_still_lives_only_in_the_data_file() -> None:
    """Trap 5's workaround, held after US4 moved wiring behind the seam.

    `test_the_component_cannot_even_spell_a_cap` already refuses `enforcement`
    anywhere in `factory/**/*.py`; what nothing checks is that the payload needing
    it is still *reachable* — inlining the JSON into Python would fail that sweep,
    so the pressure is to drop the field instead and ship a ruleset GitHub stores
    as disabled. What edit would make this fail? Inlining the payload, or
    loading it by any name other than the file's.
    """
    payload = json.loads(RULESET_DATA_FILE.read_text(encoding="utf-8"))
    assert payload["enforcement"] == "active"
    assert {rule["type"] for rule in payload["rules"]} == {
        "merge_queue",
        "required_status_checks",
    }
    assert RULESET_DATA_FILE.name in (FORGE_DIRECTORY / "wiring.py").read_text(
        encoding="utf-8"
    )
