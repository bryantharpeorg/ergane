"""Tests for the engine's repo registry (034 US2).

The registry is a *cache*: the committed manifest is the authority on
membership, and every claim these tests make is aimed at keeping the cache
honest about that — it prunes what is gone, it reports drift rather than hiding
it, and losing it entirely is an inconvenience rather than amnesia.

Every test runs against a state home under `tmp_path`; `tests/conftest.py`
redirects `ERGANE_STATE_HOME` per test so a test can never reach the operator's
real registry (plan trap 8).

Pasted evidence (plan trap 7) — SC-005, the registry surviving its own
destruction, driven **by hand** against a scratch state home rather than through
pytest, because a test that deletes a file it created itself proves less than a
terminal does.  Verbatim transcript, `ERGANE_STATE_HOME=/tmp/sc005/state`, after
`ergane init` in two scratch repos:

    $ ergane repo list
    slug   manifest  path
    alpha  valid     /tmp/sc005/alpha
    beta   valid     /tmp/sc005/beta
    $ md5sum $ERGANE_STATE_HOME/ergane/repos.json
    5f2137072a243c7a885c6a3966ad86f7  /tmp/sc005/state/ergane/repos.json
    $ rm $ERGANE_STATE_HOME/ergane/repos.json
    $ ergane repo list
    no repos are registered; run `ergane init` inside a repository to join one
    $ ergane repo rebuild /tmp/sc005/alpha /tmp/sc005/beta
    adopted alpha -> /tmp/sc005/alpha
    adopted beta -> /tmp/sc005/beta
    2 entries kept, 0 pruned
    $ ergane repo list
    slug   manifest  path
    alpha  valid     /tmp/sc005/alpha
    beta   valid     /tmp/sc005/beta
    $ md5sum $ERGANE_STATE_HOME/ergane/repos.json
    5f2137072a243c7a885c6a3966ad86f7  /tmp/sc005/state/ergane/repos.json

Both listings and both checksums are identical: the rebuilt cache is the same
cache, byte for byte.

FR-008's lock, contended by a genuinely separate process — `flock(1)` holding
the sidecar while `ergane` tries to write.  Verbatim:

    $ ( flock -x /tmp/sc005/state/ergane/repos.json.lock -c 'sleep 3' & )
    $ ergane repo rebuild --lock-timeout 0
    ergane: another writer holds the registry lock
    /tmp/sc005/state/ergane/repos.json.lock (waited 0s); wait for it to finish,
    or remove that file if no `ergane` command is running
    exit=1
    $ sleep 3; ergane repo rebuild
    1 entry kept, 0 pruned
    exit=0

AS2's collision, refused at the terminal with the holder named:

    $ ergane init /tmp/sc005/other/alpha        # declaring slug 'alpha' again
    ergane: slug 'alpha' is already registered to /tmp/sc005/alpha; slugs are
    unique because they name the repo in every workflow ID, so declare a
    different slug for this repository; the scaffold in /tmp/sc005/other/alpha
    was written and is unchanged
    exit=1

Mutation evidence (calibration — what would make each test pass if the
production code did nothing).  Each mutation was applied to the implementation,
`uv run pytest tests/test_ergane_registry.py tests/test_ergane_init.py -q` was
re-run, and the mutation reverted.  Verbatim last lines:

    mutation                                          result
    ------------------------------------------------------------------------
    register() never writes the document              16 failed, 17 passed
    rebuild() never prunes a dead entry                1 failed, 32 passed
    register() drops the exclusive_lock                2 failed, 31 passed
    derive_scopes() always returns {}                  1 failed, 32 passed
    manifest_status() always returns "valid"           2 failed, 31 passed
    register() never raises SlugCollision              2 failed, 31 passed
    `repo rebuild` prints nothing about what it pruned 1 failed, 32 passed
    the slug is neither normalized nor validated        2 failed, 25 passed
                                                        (registry file only)

Every mutation is caught, and the two large numbers are the two claims the whole
story rests on: a registry that is never written fails 16 of these, and there is
no test here that a do-nothing registry could satisfy.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pytest

import factory.cli.init as init_module
import factory.cli.main as main_module
import factory.env as factory_env
import factory.registry as registry
from factory.cli.errors import EXIT_OK, EXIT_USER
from factory.cli.install import BLANK_DOCUMENT
from factory.controlplane.config import render_controlplane_document
from factory.env import ERGANE_CONFIG_PATH_ENV, FACTORY_CONFIG_PATH_ENV
from factory.locking import LockUnavailable, exclusive_lock
from factory.verify.factory_yaml import MANIFEST_NAME, _SUPPORTED_VERSION

from tests.target_repo import git_env


# -----------------------------------------------------------------------------
# Harness
# -----------------------------------------------------------------------------


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
    """Answers the init interview from a list, in order."""

    def __init__(self, answers: list[str]) -> None:
        self.answers = list(answers)

    def ask(
        self, prompt: str, *, default: str | None = None, error: str | None = None
    ) -> str:
        if not self.answers:
            raise AssertionError(f"prompter ran out of answers for: {prompt!r}")
        return self.answers.pop(0)


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        env=git_env(),
        check=True,
    )
    return completed.stdout


def make_repo(parent: Path, name: str) -> Path:
    """A git repo with one commit, ready for `ergane init`."""
    repo = parent / name
    repo.mkdir(parents=True)
    (repo / "README.md").write_text(f"# {name}\n", encoding="utf-8")
    _git(repo, "init", "-b", "main", "--quiet")
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", "initial commit")
    return repo


def answers_for(slug: str) -> list[str]:
    """The manifest answers plus the template source and slug, in interview order."""
    return [
        str(_SUPPORTED_VERSION),  # version
        "bwrap",  # runtime
        'test: "uv run pytest -q"',  # gates
        "",  # timeouts (omitted)
        "",  # standards (omitted)
        "main",  # landing_branch
        "",  # roadmap dials (omitted; 034/US6)
        "",  # forge (omitted; 049/US5 — absent means github)
        "",  # writes (omitted; 084/US3 — absent means nothing declared)
        "",  # caches (omitted; 101/US2 — absent means the uv cache alone)
        "",  # diff_refusal_bytes (omitted; 092/US2 — absent means the default)
        "",  # template source (empty -> shipped default; 057/US4)
        slug,
    ]


@pytest.fixture
def run_init(monkeypatch: pytest.MonkeyPatch) -> Callable[..., Run]:
    """Run `ergane init <repo>` with a scripted interview."""

    def runner(repo: Path, slug: str, answers: list[str] | None = None) -> Run:
        prompter = ScriptedPrompter(answers if answers is not None else answers_for(slug))
        monkeypatch.setattr(init_module, "_prompter_factory", lambda: prompter)
        return _invoke(["init", str(repo)])

    return runner


def declare_memory_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, backend: str
) -> Path:
    """Write a control-plane config declaring `backend`, and point the CLI at it."""
    document = json.loads(json.dumps(BLANK_DOCUMENT))
    if backend == "none":
        document["memory"] = {"backend": "none"}
    else:
        document["memory"] = {"backend": backend, "url": "http://127.0.0.1:8888"}
    path = tmp_path / "controlplane.toml"
    path.write_text(render_controlplane_document(document), encoding="utf-8")
    monkeypatch.setenv(ERGANE_CONFIG_PATH_ENV, str(path))
    monkeypatch.setenv(FACTORY_CONFIG_PATH_ENV, str(path))
    return path


# -----------------------------------------------------------------------------
# T010 / AS1 — the engine learns the repo exists, outside the repo
# -----------------------------------------------------------------------------


def test_completed_init_maps_the_slug_to_the_repo_absolute_path(
    tmp_path: Path, run_init: Callable[..., Run]
) -> None:
    """AS1: after init with slug `myapp`, the registry maps it to the repo path."""
    repo = make_repo(tmp_path, "myapp")

    result = run_init(repo, "myapp")

    assert result.code == EXIT_OK, result.stderr
    entries = {entry.slug: entry for entry in registry.load_registry().entries}
    assert "myapp" in entries
    assert entries["myapp"].path == repo.resolve()
    assert entries["myapp"].path.is_absolute()
    assert entries["myapp"].manifest == (repo / MANIFEST_NAME).resolve()


def test_the_registry_entry_exists_nowhere_inside_the_repo(
    tmp_path: Path, run_init: Callable[..., Run]
) -> None:
    """AS1: the registry lives under the engine's state home, never in a repo."""
    repo = make_repo(tmp_path, "myapp")

    assert run_init(repo, "myapp").code == EXIT_OK

    registry_path = registry.resolve_registry_path()
    assert registry_path.is_file()
    assert repo.resolve() not in registry_path.resolve().parents

    # Nothing anywhere under the repo mentions the slug outside the manifest
    # the operator declared -- no shadow copy of the cache was left behind.
    strays = [
        path
        for path in repo.rglob("*")
        if path.is_file() and path.name == registry_path.name
    ]
    assert strays == []


# -----------------------------------------------------------------------------
# T011 / AS2 — slugs are unique, and a collision names the holder
# -----------------------------------------------------------------------------


def test_a_second_repo_declaring_a_taken_slug_is_refused_naming_the_holder(
    tmp_path: Path, run_init: Callable[..., Run]
) -> None:
    """AS2: a colliding slug is refused, and the refusal names the holder's path."""
    first = make_repo(tmp_path / "one", "myapp")
    second = make_repo(tmp_path / "two", "myapp")

    assert run_init(first, "myapp").code == EXIT_OK
    result = run_init(second, "myapp")

    assert result.code == EXIT_USER
    assert "myapp" in result.stderr
    assert str(first.resolve()) in result.stderr


def test_a_refused_collision_leaves_the_holder_in_place(
    tmp_path: Path, run_init: Callable[..., Run]
) -> None:
    """AS2: the loser of a collision does not displace the winner."""
    first = make_repo(tmp_path / "one", "myapp")
    second = make_repo(tmp_path / "two", "myapp")

    assert run_init(first, "myapp").code == EXIT_OK
    run_init(second, "myapp")

    entries = {entry.slug: entry for entry in registry.load_registry().entries}
    assert entries["myapp"].path == first.resolve()


def test_reregistering_the_same_repo_under_the_same_slug_is_a_no_op(
    tmp_path: Path, run_init: Callable[..., Run]
) -> None:
    """SC-003: a second init with unchanged answers leaves the registry alone."""
    repo = make_repo(tmp_path, "myapp")

    assert run_init(repo, "myapp").code == EXIT_OK
    before = registry.resolve_registry_path().read_bytes()

    assert run_init(repo, "myapp").code == EXIT_OK
    after = registry.resolve_registry_path().read_bytes()

    assert before == after


def test_an_awkward_directory_name_yields_a_proposed_slug_the_operator_accepts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Edge case: the directory name is normalized as a *proposal* (D-009).

    The operator presses Enter; the accepted proposal is what is registered, and
    it is a token that can be woven into a workflow ID.
    """
    repo = make_repo(tmp_path, "My App")
    answers = answers_for("")
    answers[-1] = ""  # press Enter at the slug question

    prompter = ScriptedPrompter(answers)
    monkeypatch.setattr(init_module, "_prompter_factory", lambda: prompter)
    result = _invoke(["init", str(repo)])

    assert result.code == EXIT_OK, result.stderr
    slugs = {entry.slug for entry in registry.load_registry().entries}
    assert slugs == {"my-app"}
    assert registry.is_valid_slug("my-app")


def test_an_unusable_slug_is_re_asked_rather_than_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FR-007: nothing that cannot name a workflow reaches the registry."""
    repo = make_repo(tmp_path, "app")
    answers = answers_for("My App")
    answers.append("myapp")  # the corrected answer, after the re-ask

    prompter = ScriptedPrompter(answers)
    monkeypatch.setattr(init_module, "_prompter_factory", lambda: prompter)
    result = _invoke(["init", str(repo)])

    assert result.code == EXIT_OK, result.stderr
    assert prompter.answers == [], "the re-ask never happened"
    slugs = {entry.slug for entry in registry.load_registry().entries}
    assert slugs == {"myapp"}


# -----------------------------------------------------------------------------
# T012 / AS3 + AS5 — the cache prunes what is gone and reports what drifted
# -----------------------------------------------------------------------------


def test_rebuild_prunes_a_repo_that_is_gone_and_reports_it(
    tmp_path: Path, run_init: Callable[..., Run]
) -> None:
    """AS3: a dead entry is pruned and named; live entries survive."""
    alpha = make_repo(tmp_path / "a", "alpha")
    beta = make_repo(tmp_path / "b", "beta")
    assert run_init(alpha, "alpha").code == EXIT_OK
    assert run_init(beta, "beta").code == EXIT_OK

    subprocess.run(["rm", "-rf", str(alpha)], check=True)

    result = _invoke(["repo", "rebuild"])

    assert result.code == EXIT_OK, result.stderr
    assert "alpha" in result.stdout
    assert "pruned" in result.stdout.lower()

    slugs = {entry.slug for entry in registry.load_registry().entries}
    assert slugs == {"beta"}


def test_rebuild_leaves_a_live_entry_byte_identical(
    tmp_path: Path, run_init: Callable[..., Run]
) -> None:
    """AS3: rebuilding is always safe -- it never edits a live entry."""
    alpha = make_repo(tmp_path / "a", "alpha")
    beta = make_repo(tmp_path / "b", "beta")
    assert run_init(alpha, "alpha").code == EXIT_OK
    assert run_init(beta, "beta").code == EXIT_OK

    before = {
        entry.slug: entry for entry in registry.load_registry().entries
    }
    subprocess.run(["rm", "-rf", str(alpha)], check=True)
    assert _invoke(["repo", "rebuild"]).code == EXIT_OK

    after = {entry.slug: entry for entry in registry.load_registry().entries}
    assert after["beta"] == before["beta"]


def test_list_renders_a_deleted_manifest_as_missing_rather_than_dropping_it(
    tmp_path: Path, run_init: Callable[..., Run]
) -> None:
    """AS5: drift is reported, never hidden."""
    repo = make_repo(tmp_path, "myapp")
    assert run_init(repo, "myapp").code == EXIT_OK

    (repo / MANIFEST_NAME).unlink()

    result = _invoke(["repo", "list"])

    assert result.code == EXIT_OK, result.stderr
    assert "myapp" in result.stdout
    assert registry.MANIFEST_MISSING in result.stdout


def test_list_renders_an_unparseable_manifest_as_invalid(
    tmp_path: Path, run_init: Callable[..., Run]
) -> None:
    """AS5: an entry whose manifest the parser refuses renders as invalid."""
    repo = make_repo(tmp_path, "myapp")
    assert run_init(repo, "myapp").code == EXIT_OK

    (repo / MANIFEST_NAME).write_text("version: 99\n", encoding="utf-8")

    result = _invoke(["repo", "list"])

    assert result.code == EXIT_OK, result.stderr
    assert "myapp" in result.stdout
    assert registry.MANIFEST_INVALID in result.stdout


def test_list_renders_a_valid_manifest_as_valid(
    tmp_path: Path, run_init: Callable[..., Run]
) -> None:
    """AS5's control: a healthy entry is not reported as drifted."""
    repo = make_repo(tmp_path, "myapp")
    assert run_init(repo, "myapp").code == EXIT_OK

    result = _invoke(["repo", "list"])

    assert result.code == EXIT_OK, result.stderr
    assert registry.MANIFEST_VALID in result.stdout
    assert registry.MANIFEST_MISSING not in result.stdout
    assert registry.MANIFEST_INVALID not in result.stdout


def test_list_says_so_when_nothing_is_registered() -> None:
    """An empty cache is a sentence, not a blank screen."""
    result = _invoke(["repo", "list"])

    assert result.code == EXIT_OK
    assert "ergane init" in (result.stdout + result.stderr)


# -----------------------------------------------------------------------------
# T013 / AS4 — the memory scope is derived from the slug
# -----------------------------------------------------------------------------


def test_memory_scope_is_recorded_when_the_control_plane_declares_a_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, run_init: Callable[..., Run]
) -> None:
    """AS4: a declared backend puts the repo's bank identity on the entry."""
    declare_memory_backend(tmp_path, monkeypatch, "hindsight")
    repo = make_repo(tmp_path, "myapp")

    assert run_init(repo, "myapp").code == EXIT_OK

    entry = registry.load_registry().get("myapp")
    assert entry is not None
    assert entry.scopes["memory_bank"] == registry.derive_memory_bank("myapp")
    assert "myapp" in entry.scopes["memory_bank"]


def test_no_memory_scope_when_the_control_plane_declares_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, run_init: Callable[..., Run]
) -> None:
    """AS4's control: `backend = "none"` records no bank identity."""
    declare_memory_backend(tmp_path, monkeypatch, "none")
    repo = make_repo(tmp_path, "myapp")

    assert run_init(repo, "myapp").code == EXIT_OK

    entry = registry.load_registry().get("myapp")
    assert entry is not None
    assert "memory_bank" not in entry.scopes


def test_no_memory_scope_when_no_control_plane_is_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, run_init: Callable[..., Run]
) -> None:
    """A host with no control-plane config still registers, without a scope."""
    monkeypatch.setenv(ERGANE_CONFIG_PATH_ENV, str(tmp_path / "absent.toml"))
    monkeypatch.setenv(FACTORY_CONFIG_PATH_ENV, str(tmp_path / "absent.toml"))
    repo = make_repo(tmp_path, "myapp")

    assert run_init(repo, "myapp").code == EXIT_OK

    entry = registry.load_registry().get("myapp")
    assert entry is not None
    assert entry.scopes == {}


# -----------------------------------------------------------------------------
# T014 / FR-008 — the lock, tested contended
# -----------------------------------------------------------------------------


@pytest.fixture
def held_lock(tmp_path: Path):
    """Hold the registry lock in another thread for the duration of the block.

    `flock` is owned by the open file description, so a second `open()` in this
    same process contends exactly as a second process would (see
    `factory/locking.py`).  The thread makes the contention real without making
    the test depend on process startup timing.
    """
    taken = threading.Event()
    release = threading.Event()
    failure: list[BaseException] = []

    def hold() -> None:
        try:
            with exclusive_lock(registry.resolve_registry_path(), timeout_s=5):
                taken.set()
                release.wait(10)
        except BaseException as error:  # pragma: no cover - surfaced below
            failure.append(error)
            taken.set()

    thread = threading.Thread(target=hold, daemon=True)
    thread.start()
    assert taken.wait(5), "the holder thread never acquired the lock"
    assert not failure, failure
    try:
        yield
    finally:
        release.set()
        thread.join(10)


def test_registration_is_refused_while_another_writer_holds_the_lock(
    tmp_path: Path, held_lock: None
) -> None:
    """FR-008: a contended registry mutation waits, then refuses."""
    repo = make_repo(tmp_path, "myapp")

    with pytest.raises(LockUnavailable):
        registry.register("myapp", repo, timeout_s=0)

    assert not registry.resolve_registry_path().exists()


def test_registration_succeeds_once_the_lock_is_released(tmp_path: Path) -> None:
    """FR-008's other half: the waiter is served, not starved."""
    repo = make_repo(tmp_path, "myapp")
    path = registry.resolve_registry_path()

    with exclusive_lock(path, timeout_s=5):
        with pytest.raises(LockUnavailable):
            registry.register("myapp", repo, timeout_s=0)

    registry.register("myapp", repo, timeout_s=5)
    assert registry.load_registry().get("myapp") is not None


def test_repo_rebuild_refuses_while_another_writer_holds_the_lock(
    tmp_path: Path, held_lock: None
) -> None:
    """The CLI face of FR-008: one line naming the lock, exit 1."""
    result = _invoke(["repo", "rebuild", "--lock-timeout", "0"])

    assert result.code == EXIT_USER
    assert ".lock" in result.stderr


# -----------------------------------------------------------------------------
# T014a / SC-005 — the registry survives its own destruction
# -----------------------------------------------------------------------------


def test_the_registry_survives_its_own_destruction(
    tmp_path: Path, run_init: Callable[..., Run]
) -> None:
    """SC-005: delete the cache, rebuild from the repo paths, converge exactly."""
    alpha = make_repo(tmp_path / "a", "alpha")
    beta = make_repo(tmp_path / "b", "beta")
    assert run_init(alpha, "alpha").code == EXIT_OK
    assert run_init(beta, "beta").code == EXIT_OK

    listing_before = _invoke(["repo", "list"])
    assert listing_before.code == EXIT_OK
    bytes_before = registry.resolve_registry_path().read_bytes()

    registry.resolve_registry_path().unlink()

    rebuilt = _invoke(["repo", "rebuild", str(alpha), str(beta)])
    assert rebuilt.code == EXIT_OK, rebuilt.stderr

    listing_after = _invoke(["repo", "list"])
    assert listing_after.stdout == listing_before.stdout
    assert registry.resolve_registry_path().read_bytes() == bytes_before


def test_rebuild_refuses_a_seed_path_that_is_not_a_managed_repo(
    tmp_path: Path,
) -> None:
    """A seed with no committed manifest is not membership, and is refused."""
    stranger = make_repo(tmp_path, "stranger")

    result = _invoke(["repo", "rebuild", str(stranger)])

    assert result.code == EXIT_USER
    assert str(stranger.resolve()) in result.stderr
    assert MANIFEST_NAME in result.stderr


def test_rebuild_keeps_the_declared_slug_of_a_repo_it_already_knows(
    tmp_path: Path, run_init: Callable[..., Run]
) -> None:
    """A seeded path already registered keeps its declared slug, not the dirname."""
    repo = make_repo(tmp_path, "checkout-dir")
    assert run_init(repo, "declared").code == EXIT_OK

    assert _invoke(["repo", "rebuild", str(repo)]).code == EXIT_OK

    slugs = {entry.slug for entry in registry.load_registry().entries}
    assert slugs == {"declared"}


# -----------------------------------------------------------------------------
# FR-006 — the state home, and a cache that refuses to be trusted when corrupt
# -----------------------------------------------------------------------------


def test_state_home_override_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FR-006: one operator-facing variable relocates the whole state home."""
    monkeypatch.setenv(registry.ERGANE_STATE_HOME_ENV, str(tmp_path / "elsewhere"))
    monkeypatch.delenv(registry.FACTORY_STATE_HOME_ENV, raising=False)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg"))

    assert registry.resolve_state_home() == tmp_path / "elsewhere"


def test_state_home_falls_back_to_xdg_then_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FR-006: `XDG_STATE_HOME`, then the documented `~/.local/state`."""
    monkeypatch.delenv(registry.ERGANE_STATE_HOME_ENV, raising=False)
    monkeypatch.delenv(registry.FACTORY_STATE_HOME_ENV, raising=False)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg"))
    assert registry.resolve_state_home() == tmp_path / "xdg"

    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    assert registry.resolve_state_home() == tmp_path / "home" / ".local" / "state"


def test_legacy_state_home_name_is_honored_with_one_deprecation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FR-006 follows the 040 rename convention, not `os.environ.get`."""
    monkeypatch.delenv(registry.ERGANE_STATE_HOME_ENV, raising=False)
    monkeypatch.setenv(registry.FACTORY_STATE_HOME_ENV, str(tmp_path / "legacy"))
    factory_env._WARNED.clear()

    try:
        with pytest.warns(DeprecationWarning):
            resolved = registry.resolve_state_home()
    finally:
        factory_env._WARNED.clear()

    assert resolved == tmp_path / "legacy"


def test_a_corrupt_registry_is_refused_naming_the_path_and_offering_rebuild(
    tmp_path: Path, run_init: Callable[..., Run]
) -> None:
    """Edge case: a hand-edited cache refuses, and names the safe answer."""
    repo = make_repo(tmp_path, "myapp")
    assert run_init(repo, "myapp").code == EXIT_OK

    path = registry.resolve_registry_path()
    path.write_text("{not json", encoding="utf-8")

    result = _invoke(["repo", "list"])

    assert result.code == EXIT_USER
    assert str(path) in result.stderr
    assert "rebuild" in result.stderr


def test_rebuild_recovers_a_corrupt_registry_from_seed_paths(
    tmp_path: Path, run_init: Callable[..., Run]
) -> None:
    """Rebuilding must always be the safe answer, corruption included."""
    repo = make_repo(tmp_path, "myapp")
    assert run_init(repo, "myapp").code == EXIT_OK
    registry.resolve_registry_path().write_text("{not json", encoding="utf-8")

    result = _invoke(["repo", "rebuild", str(repo)])

    assert result.code == EXIT_OK, result.stderr
    assert {entry.slug for entry in registry.load_registry().entries} == {"myapp"}
