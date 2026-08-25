"""083 US4: teardown names what it kept as loudly as what it removed.

The last mile of the field report. `~/.local/state/ergane` and
`~/.config/ergane/config.toml` had no removal path at all, a `config.toml.lock`
outlived everything, and the `factory/<epic>/<node>` branches and `refs/salvage/`
refs an epic leaves behind were mentioned by nothing. This story adds the two
steps that close that, and it carries the one judgement the operator must not
have made for them: **state is cheap to recreate and config is not**, so
`--purge` removes the first and never the second.

Four things here are easy to build vacuously, so each is written with the thing
that proves it is not:

- **`--purge` removes state, not credentials** (`test_purge_removes_state_and_keeps_the_config`).
  A test that only asserts the removal cannot tell state from credentials, so
  this one reads the secret's bytes back after the purge and asserts the removed
  set and the kept set are disjoint and both non-empty.
- **Kept and removed are told apart by their label, not by absence** (FR-013).
  Both tests read the *same* block under the same step and assert the labels in
  it; the bare run's kept paths and the purge run's removed paths are the same
  set of paths wearing different labels.
- **The two commands teardown prints are run** (`test_teardown_counts_the_refs_it_leaves`).
  Printing an incantation that does not return the enumerated set is the defect
  FR-015 was rewritten to close, so the test pastes each printed command into a
  subprocess and compares its line count against the count teardown reported.
- **The disclosure fires only when there is something to disclose** (plan trap 6
  applied to trap 9). Two tests, one with `ERGANE_STATE_HOME` in force and one
  without.

Pasted evidence (constitution VIII / D-037) is at the bottom.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from factory.cli.errors import EXIT_OK
from factory.cli.uninstall import (
    ACCOUNT_FOR_REFS,
    CLEAR_STATE,
    LIST_BRANCHES_COMMAND,
    LIST_SALVAGE_COMMAND,
)
from factory.env import (
    ERGANE_CONFIG_PATH_ENV,
    ERGANE_STATE_HOME_ENV,
    FACTORY_CONFIG_PATH_ENV,
    FACTORY_STATE_HOME_ENV,
)
from factory.locking import lock_path_for
from factory.workgraph.worktree import branch_name, salvage_ref_name

from tests.test_ergane_init_check import INSTALLED_CONTROL_PLANE
from tests.test_teardown_owns_the_ordering import Host, Run, _host, drive

EPIC = "091-a-departing-host"
#: What `ergane install` writes — the real thing, so the config teardown keeps
#: is a config the rest of the run can still read.
CONFIG_TEXT = INSTALLED_CONTROL_PLANE
SECRET_TEXT = "TELEGRAM_BOT_TOKEN=not-a-real-token\n"
BRANCH_NAMESPACE = "refs/heads/factory/"
SALVAGE_NAMESPACE = "refs/salvage/"


def git(repo: Path, *args: str) -> str:
    """One git command in `repo`, for seeding and for reading back."""
    done = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    )
    return done.stdout


def refs_under(repo: Path, namespace: str) -> tuple[str, ...]:
    """What `git for-each-ref <namespace>` returns, by name."""
    listing = git(repo, "for-each-ref", "--format=%(refname)", namespace)
    return tuple(line for line in listing.splitlines() if line)


# -----------------------------------------------------------------------------
# The host, plus the state, config and refs the field report is about
# -----------------------------------------------------------------------------


@dataclass
class Seeded:
    """A host teardown can strip, with every path this story rules on named."""

    host: Host
    state_root: Path
    state_home: Path
    config: Path
    secret: Path
    config_lock: Path
    branches: tuple[str, ...]
    salvage: tuple[str, ...]

    @property
    def repo(self) -> Path:
        return self.host.repo


def _seed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, override: bool = True
) -> Seeded:
    """Point the two resolvers at `tmp_path`, then build the host under them.

    The env is bound **before** `_host` runs, so the registry `ergane init`
    writes lands in the state home this test purges rather than in the suite's
    per-test slot — the registry is the state, and a purge that did not remove it
    would be testing a directory nobody uses.

    `override=False` unbinds `ERGANE_STATE_HOME`/`FACTORY_STATE_HOME` and points
    `XDG_STATE_HOME` at the same tree instead, which is the control for the
    disclosure: same paths, no override, so nothing to disclose.
    """
    state_root = tmp_path / "state-home"
    (state_root / "ergane").mkdir(parents=True)
    if override:
        monkeypatch.setenv(ERGANE_STATE_HOME_ENV, str(state_root))
        monkeypatch.setenv(FACTORY_STATE_HOME_ENV, str(state_root))
    else:
        monkeypatch.delenv(ERGANE_STATE_HOME_ENV, raising=False)
        monkeypatch.delenv(FACTORY_STATE_HOME_ENV, raising=False)
        monkeypatch.setenv("XDG_STATE_HOME", str(state_root))

    config = tmp_path / "config" / "ergane" / "config.toml"
    config.parent.mkdir(parents=True)
    config.write_text(CONFIG_TEXT, encoding="utf-8")
    secret = config.parent / "telegram.env"
    secret.write_text(SECRET_TEXT, encoding="utf-8")
    monkeypatch.setenv(ERGANE_CONFIG_PATH_ENV, str(config))
    monkeypatch.setenv(FACTORY_CONFIG_PATH_ENV, str(config))

    # The lock nothing unlinks. `factory/locking.py:68` creates it with O_CREAT,
    # `:83` unlocks and `:85` closes; there is no unlink anywhere, which is why
    # this file outlived the field teardown (plan trap 10).
    config_lock = lock_path_for(config)
    config_lock.write_text("", encoding="utf-8")

    host = _host(tmp_path, monkeypatch)
    # `bind_offline_seams` re-points the config at the offline control plane it
    # writes; it says a test that wants a different one sets it after that
    # returns, and this test's whole subject is which config survives. The
    # offline file stays beside it, which is a realistic second thing to keep.
    monkeypatch.setenv(ERGANE_CONFIG_PATH_ENV, str(config))
    monkeypatch.setenv(FACTORY_CONFIG_PATH_ENV, str(config))

    # State the engine itself leaves behind, beside the registry it just wrote.
    (state_root / "ergane" / "doctor.db").write_text("seeded\n", encoding="utf-8")
    (state_root / "ergane" / "worktrees").mkdir()
    (state_root / "ergane" / "worktrees" / "attempt.log").write_text("…\n", encoding="utf-8")

    head = git(host.repo, "rev-parse", "HEAD").strip()
    # `branch_name` is the branch, `refs/heads/<branch>` is the ref teardown
    # counts; both are named here so the test never conflates them.
    branches = tuple(
        f"refs/heads/{branch_name(EPIC, node)}" for node in ("us1", "us2")
    )
    for branch in branches:
        git(host.repo, "branch", branch.removeprefix("refs/heads/"), head)
    salvage = tuple(
        salvage_ref_name(EPIC, node, attempt=attempt, sha=head)
        for node, attempt in (("us1", 1), ("us2", 3))
    )
    for ref in salvage:
        git(host.repo, "update-ref", ref, head)

    return Seeded(
        host=host,
        state_root=state_root,
        state_home=state_root / "ergane",
        config=config,
        secret=secret,
        config_lock=config_lock,
        branches=branches,
        salvage=salvage,
    )


@pytest.fixture
def seeded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Seeded:
    return _seed(tmp_path, monkeypatch)


# -----------------------------------------------------------------------------
# Reading teardown's report
# -----------------------------------------------------------------------------


def plan_of(result: Run, step: str) -> str:
    """The `N/M <step>: <plan>` line's plan half — index-agnostic on purpose, so
    a step inserted ahead of these two (104-US7 inserted one) moves nothing here."""
    for line in result.stdout.splitlines():
        head, _, rest = line.partition(f" {step}: ")
        if rest and head[:1].isdigit():
            return rest
    raise AssertionError(f"no plan line for {step!r} in:\n{result.stdout}")


def block_of(result: Run, step: str) -> list[str]:
    """The indented block teardown printed under one step, stripped.

    One block per step is the whole point of FR-013: a kept path and a removed
    path are told apart by their label, and they can only be compared by label
    if they are in the same block.
    """
    lines = result.stdout.splitlines()
    for index, line in enumerate(lines):
        if line[:1].isdigit() and f" {step}: " in line:
            block = []
            for candidate in lines[index + 1 :]:
                if not candidate.startswith("    "):
                    break
                block.append(candidate.strip())
            return block
    raise AssertionError(f"no block for {step!r} in:\n{result.stdout}")


def kept_in(block: list[str], path: Path) -> bool:
    """Is `path` on its own kept-labelled line of `block`?"""
    return any(line.startswith(f"kept: {path} (") for line in block)


def removed_in(block: list[str], subject: Path | str) -> bool:
    """Is `subject` on its own removed-labelled line of `block`?"""
    return any(line.startswith(f"removed: {subject}") for line in block)


def labelled(block: list[str], label: str) -> list[str]:
    return [line for line in block if line.startswith(f"{label}: ")]


# -----------------------------------------------------------------------------
# T042 / US4-S1, FR-013 — a bare run keeps both, and says so by label
# -----------------------------------------------------------------------------


def test_a_bare_run_keeps_the_state_home_and_the_config_and_names_both(
    seeded: Seeded,
) -> None:
    """US4-S1: no `--purge`, so nothing goes, and every survivor is labelled.

    The report is not allowed to fall silent about what it left: `removed 6
    file(s)` naming nothing is the defect this whole spec exists to close, and a
    kept path that is simply absent from the report is the same defect wearing
    the other sign.
    """
    result = drive(seeded.host.request())

    assert result.code == EXIT_OK, result.stderr

    # Everything survives, contents included.
    assert (seeded.state_home / "doctor.db").read_text(encoding="utf-8") == "seeded\n"
    assert (seeded.state_home / "worktrees" / "attempt.log").exists()
    assert seeded.config.read_text(encoding="utf-8") == CONFIG_TEXT
    assert seeded.secret.read_text(encoding="utf-8") == SECRET_TEXT

    block = block_of(result, CLEAR_STATE)
    for survivor in (
        seeded.state_home / "doctor.db",
        seeded.state_home / "worktrees",
        seeded.config,
        seeded.secret,
    ):
        assert kept_in(block, survivor), f"{survivor} is on no kept line of {block}"

    # …and it is a kept line because of its label, not because the block has
    # only one kind of line in it: a bare run removed nothing, and says so.
    assert labelled(block, "removed") == []
    assert "--purge" in plan_of(result, CLEAR_STATE)


# -----------------------------------------------------------------------------
# T043 / US4-S2, FR-014 — the control: --purge removes state, not credentials
# -----------------------------------------------------------------------------


def test_purge_removes_state_and_keeps_the_config(seeded: Seeded) -> None:
    """US4-S2, **the control**: the secret's bytes are read back after the purge.

    A test that only checks the removal cannot tell state from credentials. This
    one asserts the state home is empty, the config and the secret still hold
    exactly what was written, and that the two labelled sets in the one block are
    disjoint and both non-empty — which is the shape FR-013 asks for and the
    thing a removal-only assertion cannot see.
    """
    result = drive(seeded.host.request(purge=True))

    assert result.code == EXIT_OK, result.stderr

    assert seeded.state_home.is_dir(), "the state home itself, not its contents"
    assert sorted(seeded.state_home.iterdir()) == []
    assert seeded.config.read_text(encoding="utf-8") == CONFIG_TEXT
    assert seeded.secret.read_text(encoding="utf-8") == SECRET_TEXT

    block = block_of(result, CLEAR_STATE)
    assert removed_in(block, seeded.state_home / "doctor.db")
    assert removed_in(block, seeded.state_home / "worktrees")
    assert kept_in(block, seeded.config)
    assert kept_in(block, seeded.secret)

    removed = labelled(block, "removed")
    kept = labelled(block, "kept")
    assert removed and kept, block
    assert not {line.split()[1] for line in removed} & {line.split()[1] for line in kept}


def test_the_purge_discloses_the_root_it_did_not_empty_and_only_then(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T048's ruling, and its control (plan traps 9 and 6).

    `--purge` empties the root `resolve_state_home()` returns, override
    included, because that resolver is the one that *put* the state there — there
    is no second root holding it, which is the difference from `--clean-runtime`.
    What the override does create is a default root that is now not emptied, and
    teardown names it. With no override in force the two roots are the same root
    and the line does not print at all: a disclosure that always fires stops
    being read.
    """
    disclosed = drive(_seed(tmp_path, monkeypatch, override=True).host.request(purge=True))
    line = next(
        (l for l in block_of(disclosed, CLEAR_STATE) if ERGANE_STATE_HOME_ENV in l), ""
    )
    assert line, block_of(disclosed, CLEAR_STATE)
    assert "does not empty it" in line


def test_no_override_means_no_disclosure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control for the line above: same tree, resolved by XDG, no line."""
    quiet = drive(_seed(tmp_path, monkeypatch, override=False).host.request(purge=True))

    block = block_of(quiet, CLEAR_STATE)
    assert not [line for line in block if ERGANE_STATE_HOME_ENV in line], block
    assert not [line for line in block if "does not empty it" in line], block


# -----------------------------------------------------------------------------
# T044 / US4-S3, FR-014 — no `.lock` sibling survives a purge
# -----------------------------------------------------------------------------


def test_no_lock_sibling_survives_a_purge(seeded: Seeded) -> None:
    """US4-S3: `config.toml.lock` is the file that started this story.

    Nothing in `factory/locking.py` unlinks a lock — `:68` creates it, `:83`
    unlocks and `:85` closes — so every lock the engine ever took is still on
    disk. Fixed here rather than by making `exclusive_lock` unlink on exit, which
    would race two processes that both hold the path open (plan trap 10).

    The registry's own lock is not seeded: `repo forget` takes it during step
    two of this very run, so it is a lock a prior run left behind by the same
    mechanism, found and removed by the same sweep.
    """
    assert seeded.config_lock.exists(), "the seeded lock, before"

    result = drive(seeded.host.request(purge=True))

    assert result.code == EXIT_OK, result.stderr
    assert not seeded.config_lock.exists()
    assert sorted(seeded.config.parent.glob("*.lock")) == []
    assert sorted(seeded.state_root.rglob("*.lock")) == []
    assert removed_in(block_of(result, CLEAR_STATE), seeded.config_lock)

    # The config beside it is untouched: the sweep is by the naming rule at
    # `factory/locking.py:46-49`, not by emptying the directory.
    assert seeded.config.read_text(encoding="utf-8") == CONFIG_TEXT


# -----------------------------------------------------------------------------
# T045 / US4-S4, FR-015 — the refs teardown does not remove, counted and named
# -----------------------------------------------------------------------------


def test_teardown_counts_the_refs_it_leaves_and_prints_how_to_list_them(
    seeded: Seeded,
) -> None:
    """US4-S4: a count per namespace, both commands verbatim, and neither ref gone.

    The commands are then *run*: a printed incantation that does not return the
    enumerated set is the defect FR-015 was rewritten to close, and it is the
    reason `ergane build salvage` is not named — that verb loads a compiled graph
    (`factory/cli/nouns/build.py:1392`) and reports one epic's nodes, so it
    cannot answer what is on the host.
    """
    result = drive(seeded.host.request())

    assert result.code == EXIT_OK, result.stderr

    plan = plan_of(result, ACCOUNT_FOR_REFS)
    assert f"2 branch(es) under {BRANCH_NAMESPACE}" in plan
    assert f"2 ref(s) under {SALVAGE_NAMESPACE}" in plan

    block = block_of(result, ACCOUNT_FOR_REFS)
    assert LIST_BRANCHES_COMMAND in block
    assert LIST_SALVAGE_COMMAND in block
    assert LIST_BRANCHES_COMMAND == f"git for-each-ref {BRANCH_NAMESPACE}"
    assert LIST_SALVAGE_COMMAND == f"git for-each-ref {SALVAGE_NAMESPACE}"
    assert "ergane build salvage" not in result.stdout

    # Both refs survive, and both printed commands return exactly what was counted.
    assert set(refs_under(seeded.repo, BRANCH_NAMESPACE)) == set(seeded.branches)
    assert set(refs_under(seeded.repo, SALVAGE_NAMESPACE)) == set(seeded.salvage)
    for command, expected in (
        (LIST_BRANCHES_COMMAND, 2),
        (LIST_SALVAGE_COMMAND, 2),
    ):
        pasted = subprocess.run(
            command.split(), cwd=seeded.repo, capture_output=True, text=True, check=True
        )
        assert len(pasted.stdout.splitlines()) == expected, command


# -----------------------------------------------------------------------------
# T046 / US4-S5, FR-016 — `--scrub-refs` removes them and names them
# -----------------------------------------------------------------------------


def test_scrub_refs_removes_the_refs_and_names_every_one(seeded: Seeded) -> None:
    """US4-S5: the same refs, gone, each on its own removed-labelled line."""
    result = drive(seeded.host.request(scrub_refs=True))

    assert result.code == EXIT_OK, result.stderr
    assert refs_under(seeded.repo, BRANCH_NAMESPACE) == ()
    assert refs_under(seeded.repo, SALVAGE_NAMESPACE) == ()

    block = block_of(result, ACCOUNT_FOR_REFS)
    for ref in seeded.branches + seeded.salvage:
        assert removed_in(block, ref), f"{ref} is on no removed line of {block}"

    # Named as removed, not merely counted: the plan says remove, and the two
    # listing commands are still printed for the operator who wants to check.
    assert plan_of(result, ACCOUNT_FOR_REFS).startswith("remove ")
    assert LIST_BRANCHES_COMMAND in block


def test_both_flags_are_on_the_verb_and_the_help_says_what_they_keep() -> None:
    """FR-014/FR-016 at the surface: the operator has to find these to use them."""
    from tests.test_teardown_owns_the_ordering import invoke

    helped = invoke(["uninstall", "--help"])

    assert helped.code == EXIT_OK, helped.stderr
    assert "--purge" in helped.stdout
    assert "--scrub-refs" in helped.stdout


# =============================================================================
# Pasted evidence — constitution VIII / D-037. Verbatim from this worktree,
# captured by the test named beside each block; `/tmp/…/` elides one pytest tmp
# path prefix and nothing else.
# =============================================================================
#
# T051 (SC-010) — the two runs side by side, bare and `--purge`, on the same
# seeded host. Steps 1-3 are US3's and are elided to the two this story adds;
# note that the same four state paths appear in both, wearing different labels,
# and the config and the secret wear `kept` in both.
#
# BARE (test_a_bare_run_keeps_the_state_home_and_the_config_and_names_both):
#
#     4/5 clear state: nothing to do: --purge was not given, so nothing under /tmp/…/state-home/ergane is removed; the config at /tmp/…/config/ergane/config.toml is kept either way
#         kept: /tmp/…/state-home/ergane/doctor.db (state; --purge removes it)
#         kept: /tmp/…/state-home/ergane/repos.json (state; --purge removes it)
#         kept: /tmp/…/state-home/ergane/repos.json.lock (state; --purge removes it)
#         kept: /tmp/…/state-home/ergane/worktrees (state; --purge removes it)
#         kept: /tmp/…/config/ergane/config.toml (the control-plane config; teardown never removes it)
#         kept: /tmp/…/config/ergane/offline-control-plane.toml (beside the config, so treated as a secret)
#         kept: /tmp/…/config/ergane/telegram.env (beside the config, so treated as a secret)
#         ERGANE_STATE_HOME is set, so the emptied root would be /tmp/…/state-home/ergane; /home/admin/.local/state/ergane is the root this host would use without it, and teardown does not empty it
#
# --PURGE (test_purge_removes_state_and_keeps_the_config):
#
#     4/5 clear state: remove 4 entries under /tmp/…/state-home/ergane and 1 lock file beside /tmp/…/config/ergane/config.toml; the config itself is kept
#         kept: /tmp/…/config/ergane/config.toml (the control-plane config; teardown never removes it)
#         kept: /tmp/…/config/ergane/offline-control-plane.toml (beside the config, so treated as a secret)
#         kept: /tmp/…/config/ergane/telegram.env (beside the config, so treated as a secret)
#         ERGANE_STATE_HOME is set, so the emptied root would be /tmp/…/state-home/ergane; /home/admin/.local/state/ergane is the root this host would use without it, and teardown does not empty it
#         removed: /tmp/…/state-home/ergane/doctor.db
#         removed: /tmp/…/state-home/ergane/repos.json
#         removed: /tmp/…/state-home/ergane/repos.json.lock
#         removed: /tmp/…/state-home/ergane/worktrees
#         removed: /tmp/…/config/ergane/config.toml.lock
#
# Seven paths, four labels apiece flipped between the two runs and three that
# never flip: that is FR-013's rule rendered rather than asserted. Note too that
# the bare run's `nothing to do` did not buy silence — the step that acted on
# nothing still named everything it left.
#
# The filesystem afterwards, read by the test rather than described:
#
#     sorted(state_home.iterdir())          -> []
#     state_home.is_dir()                   -> True    # the home, not its contents
#     config.read_text()                    -> INSTALLED_CONTROL_PLANE, byte for byte
#     secret.read_text()                    -> 'TELEGRAM_BOT_TOKEN=not-a-real-token\n'
#     sorted(config.parent.glob("*.lock"))  -> []      # T044 / US4-S3
#     sorted(state_root.rglob("*.lock"))    -> []
#
# The `repos.json.lock` above was never seeded: `repo forget` takes it during
# step two of the same run, so the sweep removes a lock an earlier act of this
# very teardown left behind — which is the mechanism, not a fixture.
#
# The disclosure on the fourth line of each block, and its control
# (test_the_purge_discloses_the_root_it_did_not_empty_and_only_then,
# test_no_override_means_no_disclosure). With ERGANE_STATE_HOME unset and
# XDG_STATE_HOME pointing at the same tree, the same run prints:
#
#     4/5 clear state: remove 4 entries under /tmp/…/state-home/ergane and 1 lock file beside /tmp/…/config/ergane/config.toml; the config itself is kept
#         kept: /tmp/…/config/ergane/config.toml (the control-plane config; teardown never removes it)
#         kept: /tmp/…/config/ergane/offline-control-plane.toml (beside the config, so treated as a secret)
#         kept: /tmp/…/config/ergane/telegram.env (beside the config, so treated as a secret)
#         removed: /tmp/…/state-home/ergane/doctor.db
#         …
#
# — no disclosure line at all. Same paths emptied, no override in force, nothing
# to disclose: a line that always fires stops being read (plan trap 6).
#
# T052 (SC-011) — the ref enumeration, once surviving and once scrubbed
# (test_teardown_counts_the_refs_it_leaves_and_prints_how_to_list_them,
# test_scrub_refs_removes_the_refs_and_names_every_one):
#
#     5/5 account for git refs: nothing to do: 2 branch(es) under refs/heads/factory/ and 2 ref(s) under refs/salvage/ stay, across 1 repository; --scrub-refs removes them
#         /tmp/…/widgets: 2 under refs/heads/factory/, 2 under refs/salvage/
#         list them yourself, one namespace each:
#         git for-each-ref refs/heads/factory/
#         git for-each-ref refs/salvage/
#
#     $ git for-each-ref refs/heads/factory/
#     cde64ce4cd40c07cff74a749ea352ed3305a3034 commit	refs/heads/factory/091-a-departing-host/us1
#     cde64ce4cd40c07cff74a749ea352ed3305a3034 commit	refs/heads/factory/091-a-departing-host/us2
#     $ git for-each-ref refs/salvage/
#     cde64ce4cd40c07cff74a749ea352ed3305a3034 commit	refs/salvage/091-a-departing-host/us1/attempt-1-cde64ce4cd40
#     cde64ce4cd40c07cff74a749ea352ed3305a3034 commit	refs/salvage/091-a-departing-host/us2/attempt-3-cde64ce4cd40
#
# — two lines each, which is what the counts above said, asserted by the test
# running each printed command in a subprocess. And with `--scrub-refs`:
#
#     5/5 account for git refs: remove 2 branch(es) under refs/heads/factory/ and 2 ref(s) under refs/salvage/, across 1 repository
#         /tmp/…/widgets: 2 under refs/heads/factory/, 2 under refs/salvage/
#         list them yourself, one namespace each:
#         git for-each-ref refs/heads/factory/
#         git for-each-ref refs/salvage/
#         removed: refs/heads/factory/091-a-departing-host/us1 (in /tmp/…/widgets)
#         removed: refs/heads/factory/091-a-departing-host/us2 (in /tmp/…/widgets)
#         removed: refs/salvage/091-a-departing-host/us1/attempt-1-cde64ce4cd40 (in /tmp/…/widgets)
#         removed: refs/salvage/091-a-departing-host/us2/attempt-3-cde64ce4cd40 (in /tmp/…/widgets)
#
#     refs_under(repo, "refs/heads/factory/") -> ()
#     refs_under(repo, "refs/salvage/")       -> ()
#
# `ergane build salvage` appears nowhere in either run, asserted directly: it
# loads a compiled graph (`factory/cli/nouns/build.py:1392`) and reports one
# epic's nodes, so pointing an operator at it to enumerate a host's refs is
# worse than saying nothing.
#
# The gate `factory.yaml` declares, in this worktree, with this file and the
# module it drives in place:
#
#     $ uv run pytest -q
#     4345 passed, 52 skipped, 6 warnings in 342.46s (0:05:42)
