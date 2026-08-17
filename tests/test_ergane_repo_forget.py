"""034 US5: a repo can leave, and can take the engine's record of it with it.

US7 landed `ergane repo forget <slug>` — it deletes the roadmap schedule, then
removes the registry entry, and refuses the whole verb when the control plane
will not answer.  This story adds the two flags that make leaving complete:
`--clean-runtime`, which empties the repository's own runtime root once no epic
is running, and `--export <dir>`, which writes what the engine learned about the
repo into open formats outside that root.

Three claims here would be easy to build vacuously, so each is written with the
mutation that proves it is not (the battery is at the bottom):

- **Two exports against an untouched engine are byte-identical** (US5's
  independent test).  An export that wrote nothing satisfies that trivially, so
  the comparison runs inside a test that first asserts the file set and the row
  counts, and a sibling test pins the record *order* — which byte-identity alone
  cannot see.
- **`--clean-runtime` empties the departing repo's root and nothing else.**  The
  path it deletes is derived from the registry entry; the environment is given a
  decoy root in the same test and must survive untouched.
- **No test can empty a live runtime root.**  The guard is exercised through the
  CLI with the tmp tree moved out from under the repo rather than assumed.  This
  repository lost its whole runtime root on 2026-08-14 to a process acting on a
  root it had been handed; D-045 answered that class with a guard at the choke
  point, and this is that guard.

Pasted evidence (constitution VIII / D-037) is at the bottom.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, Callable

import pytest

import factory.cli.init as init_module
import factory.cli.repo as repo_module
from factory import registry
from factory.cli import repo_export
from factory.cli.errors import EXIT_OK, EXIT_USER
from factory.doctor import store as doctor_store
from factory.usage import ledger as usage_ledger
from factory.verify import store as verify_store

from tests.fake_schedules import FakeScheduleServer, desired_for, seed
from tests.test_ergane_init import ScriptedPrompter, _git, _invoke
from tests.test_ergane_init_check import bind_offline_seams, make_repo

SLUG = "widgets"
OTHER_SLUG = "gadgets"

#: What one export writes, and nothing else.
EXPORT_FILES = {"findings.jsonl", "usage.jsonl", "escalations.jsonl", "digest.md"}

#: A credential-shaped value seeded into free text the engine stores verbatim.
#: It must match the scrubber's own pattern (`sk-[A-Za-z0-9_-]{8,}`, see
#: `factory/cli/repo_export.py`), and must otherwise look nothing like a live
#: key: low entropy and self-labelling, so neither a human reader nor a secret
#: scanner mistakes a test fixture in a public repository for a real credential.
LEAKED_KEY = "sk-EXAMPLE-not-a-real-key-0000000000"

Init = Callable[..., Any]


# -----------------------------------------------------------------------------
# Fixtures and helpers
# -----------------------------------------------------------------------------


@pytest.fixture
def floor(monkeypatch: pytest.MonkeyPatch) -> FakeScheduleServer:
    """Every outward seam bound; the control plane the test may inspect."""
    control_plane = FakeScheduleServer()
    bind_offline_seams(monkeypatch, schedules=control_plane)
    return control_plane


@pytest.fixture
def no_epics(monkeypatch: pytest.MonkeyPatch) -> None:
    """The capacity read reports an idle floor."""

    async def empty() -> set[str]:
        return set()

    monkeypatch.setattr(repo_module, "_running_epic_ids", empty)


@pytest.fixture
def init(monkeypatch: pytest.MonkeyPatch) -> Init:
    """Run a full `ergane init`, scripting the interview in top-level key order."""

    def run(repo: Path, *, slug: str = SLUG) -> Any:
        # …, landing_branch, roadmap, forge (049/US5, omitted), slug
        answers = ["1", "bwrap", 'test: "uv run pytest -q"', "", "", "main", "", "", slug]
        monkeypatch.setattr(init_module, "_prompter_factory", lambda: ScriptedPrompter(answers))
        return _invoke(["init", str(repo)])

    return run


def registered(tmp_path: Path, *, name: str = "widgets", slug: str = SLUG) -> Path:
    """A scaffolded repo the engine knows about."""
    repo = make_repo(tmp_path, name=name)
    registry.register(slug, repo)
    return repo


def seed_stores(root: Path, *, tag: str, secret: str = "") -> None:
    """Write one row into each of the three stores this repo owns.

    Raw inserts against the real schemas: what is being tested is the reader, and
    a fixture that went through the typed writers would test those instead.
    """
    root.mkdir(parents=True, exist_ok=True)

    findings = doctor_store.connect(root / "doctor.db")
    findings.execute(
        "INSERT INTO findings (key, category, severity, status, summary, refs,"
        " notes, source, occurrences, first_seen, last_seen)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            f"{tag}/the-gate-never-ran", tag, "critical", "open",
            f"{tag}: the gate never ran {secret}".strip(),
            '["factory/verify/gates.py:12"]', f"seen twice {secret}".strip(),
            "operator", 2, "2026-01-01T00:00:00Z", "2026-01-09T00:00:00Z",
        ),
    )
    findings.execute(
        "INSERT INTO finding_events (finding_key, seen_at, source, severity, kind)"
        " VALUES (?, ?, ?, ?, ?)",
        (f"{tag}/the-gate-never-ran", "2026-01-01T00:00:00Z", "operator", "critical", "reported"),
    )
    findings.commit()
    findings.close()

    usage = usage_ledger.connect(root / "ledger.db")
    usage.execute(
        "INSERT INTO usage_records (epic_id, node_id, attempt, persona, spec_ref,"
        " key_alias, prompt_tokens, completion_tokens, spend_usd,"
        " final_usage_confirmed, termination, issued_at, torn_down_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            f"epic-{tag}", "us1", 1, "coder", f"specs/{tag}",
            f"epic-{tag}:us1:1:coder", 100, 200, 0.25, 1, "completed",
            "2026-01-01T00:00:00Z", "2026-01-01T01:00:00Z",
        ),
    )
    usage.commit()
    usage.close()

    escalations = verify_store.connect(root / "verification.db")
    escalations.execute(
        "INSERT INTO escalations (escalation_id, workflow_id, epic_id, node_id,"
        " choices, history_summary, sent_at, expires_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            f"{tag}0badc0de"[:12], f"epic-{tag}", f"epic-{tag}", "us1",
            '["RETRY", "KILL"]', f"attempt 1 failed the gate {secret}".strip(),
            "2026-01-02T00:00:00Z", "2026-01-02T01:00:00Z",
        ),
    )
    escalations.commit()
    escalations.close()


def add_findings(root: Path, *keys: str) -> None:
    """Extra findings, written in the order given so it can differ from key order."""
    conn = doctor_store.connect(root / "doctor.db")
    for key in keys:
        conn.execute(
            "INSERT INTO findings (key, category, severity, status, summary, refs,"
            " source, occurrences, first_seen, last_seen)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                key, key.split("/")[0], "info", "open", f"summary for {key}",
                "[]", "operator", 1, "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z",
            ),
        )
    conn.commit()
    conn.close()


def tree_state(repo: Path) -> tuple[str, str, tuple[tuple[str, str], ...]]:
    """History, working-tree status, and every file's hash: what may not change."""
    files: list[tuple[str, str]] = []
    for path in sorted(repo.rglob("*")):
        if ".git" in path.parts or not path.is_file():
            continue
        files.append(
            (str(path.relative_to(repo)), hashlib.sha256(path.read_bytes()).hexdigest())
        )
    return (
        _git(repo, "log", "--format=%H %s"),
        _git(repo, "status", "--porcelain"),
        tuple(files),
    )


def lines(path: Path) -> list[str]:
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line]


def every_byte(directory: Path) -> str:
    """Everything the export wrote, as one string, for absence assertions."""
    blob = ""
    for path in sorted(directory.rglob("*")):
        if path.is_file():
            blob += path.read_text(encoding="utf-8")
    return blob


# -----------------------------------------------------------------------------
# T033 / US5-S1, SC-006 — a clean departure
# -----------------------------------------------------------------------------


def test_forget_leaves_the_tree_untouched_and_the_slug_reusable(
    tmp_path: Path, floor: FakeScheduleServer, init: Init
) -> None:
    """SC-006: registered, forgotten, re-registered — byte-identical in-tree.

    The portability claim in one run: the engine lets go, the repo does not
    notice, and a fresh `ergane init .` takes the same slug back.
    """
    repo = make_repo(tmp_path)

    assert init(repo).code == EXIT_OK
    assert registry.load_registry().get(SLUG) is not None
    joined = tree_state(repo)

    result = _invoke(["repo", "forget", SLUG])

    assert result.code == EXIT_OK, result.stderr
    assert registry.load_registry().get(SLUG) is None
    assert SLUG not in _invoke(["repo", "list"]).stdout
    assert tree_state(repo) == joined, "forget touched the repository's own files"

    assert init(repo).code == EXIT_OK
    assert registry.load_registry().get(SLUG).path == repo.resolve()
    assert tree_state(repo) == joined


# -----------------------------------------------------------------------------
# T034 / US5-S2 — --clean-runtime refuses while an epic is open
# -----------------------------------------------------------------------------


def test_clean_runtime_refuses_while_any_epic_is_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, floor: FakeScheduleServer
) -> None:
    """The runtime root under a live epic is evidence in use, so nothing happens.

    Refused on *any* open epic: workflow ids are `epic-{epic_id}` and carry no
    repo token (034 plan, trap 6), so a per-repo filter would match nothing and
    delete a live epic's evidence the first time it mattered.  The refusal lands
    before the schedule is deleted.
    """
    repo = registered(tmp_path)
    seed(floor, desired_for(repo))
    root = repo / ".ergane"
    seed_stores(root, tag="widgets")

    async def one_open_epic() -> set[str]:
        return {"epic-034-live"}

    monkeypatch.setattr(repo_module, "_running_epic_ids", one_open_epic)

    result = _invoke(["repo", "forget", SLUG, "--clean-runtime"])

    assert result.code == EXIT_USER
    assert "epic-034-live" in result.stderr
    assert registry.load_registry().get(SLUG) is not None, "the entry must survive"
    assert floor.schedules != {}, "the schedule must survive a refused departure"
    assert (root / "doctor.db").exists()


# -----------------------------------------------------------------------------
# --clean-runtime deletes the repo's root, derived from the entry
# -----------------------------------------------------------------------------


def test_clean_runtime_empties_the_entrys_root_and_not_the_environments(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    floor: FakeScheduleServer,
    no_epics: None,
) -> None:
    """The root emptied comes from the registry entry, never from the environment.

    `ERGANE_ROOT` and `FACTORY_ROOT` point at a decoy holding a database of its
    own.  A `--clean-runtime` that asked `resolve_factory_root()` — which reads
    exactly those variables — would empty the decoy and leave this repo's root
    full.  The directory itself survives: the repo's `.gitignore` still names it.
    """
    repo = registered(tmp_path)
    seed(floor, desired_for(repo))
    root = repo / ".ergane"
    seed_stores(root, tag="widgets")
    (root / "homes").mkdir()
    (root / "homes" / "node.json").write_text("{}", encoding="utf-8")

    decoy = tmp_path / "host-root"
    seed_stores(decoy, tag="host")
    monkeypatch.setenv("ERGANE_ROOT", str(decoy))
    monkeypatch.setenv("FACTORY_ROOT", str(decoy))

    result = _invoke(["repo", "forget", SLUG, "--clean-runtime"])

    assert result.code == EXIT_OK, result.stderr
    assert root.is_dir(), "the ignored directory itself belongs to the repo"
    assert list(root.iterdir()) == []
    assert (decoy / "doctor.db").exists(), "the environment's root is not this repo's"
    assert registry.load_registry().get(SLUG) is None


def test_clean_runtime_is_refused_for_a_root_outside_the_tmp_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    floor: FakeScheduleServer,
    no_epics: None,
) -> None:
    """No test can empty a live runtime root: D-045's enforcement, for a deletion.

    The repo is real and its root is full; what moves is the tmp tree the guard
    measures against, so the guard sees what it would see against
    `/home/<operator>/code/<repo>/.ergane`.  The assertion names the finding key
    and then checks the files are still there, so a coincidental substring in
    some other refusal cannot satisfy it.
    """
    repo = registered(tmp_path)
    seed(floor, desired_for(repo))
    root = repo / ".ergane"
    seed_stores(root, tag="widgets")

    elsewhere = tmp_path / "not-the-tmp-tree"
    elsewhere.mkdir()
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(elsewhere))

    result = _invoke(["repo", "forget", SLUG, "--clean-runtime"])

    assert result.code != EXIT_OK
    assert repo_module.RUNTIME_ROOT_TEST_ISOLATION_FINDING in result.stderr
    assert (root / "doctor.db").exists(), "the guard fired after the deletion"
    assert (root / "ledger.db").exists()
    assert (root / "verification.db").exists()


# -----------------------------------------------------------------------------
# T035 / US5-S3, US5-S4, FR-013 — the export
# -----------------------------------------------------------------------------


def test_export_writes_one_jsonl_per_store_and_a_digest(
    tmp_path: Path, floor: FakeScheduleServer
) -> None:
    """US5-S3: the repo's findings, usage and escalations, in documented formats."""
    repo = registered(tmp_path)
    seed(floor, desired_for(repo))
    seed_stores(repo / ".ergane", tag="widgets")
    out = tmp_path / "out"

    result = _invoke(["repo", "forget", SLUG, "--export", str(out)])

    assert result.code == EXIT_OK, result.stderr
    assert {path.name for path in out.iterdir()} == EXPORT_FILES

    findings = lines(out / "findings.jsonl")
    assert len(findings) == 1
    assert '"key":"widgets/the-gate-never-ran"' in findings[0]
    assert '"occurrences":2' in findings[0]
    assert '"events":[' in findings[0], "the recurrence trail is the findings ledger"

    assert len(lines(out / "usage.jsonl")) == 1
    assert '"key_alias":"epic-widgets:us1:1:coder"' in lines(out / "usage.jsonl")[0]

    assert len(lines(out / "escalations.jsonl")) == 1
    assert '"epic_id":"epic-widgets"' in lines(out / "escalations.jsonl")[0]

    digest = (out / "digest.md").read_text(encoding="utf-8")
    assert "widgets/the-gate-never-ran" in digest
    assert "findings.jsonl" in digest and "usage.jsonl" in digest

    assert registry.load_registry().get(SLUG) is None


def test_export_carries_only_the_departing_repos_rows(
    tmp_path: Path, floor: FakeScheduleServer
) -> None:
    """FR-013's selection: this repo's records, not the whole engine's.

    No store in this engine has a repo column — `findings` is keyed by finding
    key and `usage_records` by epic, and an epic id carries no repo token — so
    selection is by store *location*, derived from the entry the slug names.  A
    second registered repo with rows of its own is what makes that testable.
    """
    repo = registered(tmp_path)
    other = registered(tmp_path, name="gadgets", slug=OTHER_SLUG)
    seed(floor, desired_for(repo))
    seed_stores(repo / ".ergane", tag="widgets")
    seed_stores(other / ".ergane", tag="gadgets")
    out = tmp_path / "out"

    assert _invoke(["repo", "forget", SLUG, "--export", str(out)]).code == EXIT_OK

    written = every_byte(out)
    assert "widgets/the-gate-never-ran" in written
    assert "gadgets" not in written, "another repo's records left with this one"
    assert (other / ".ergane" / "doctor.db").exists()


def test_two_exports_of_an_untouched_engine_are_byte_identical(
    tmp_path: Path, floor: FakeScheduleServer, no_epics: None
) -> None:
    """US5's independent test, and the one most likely to be quietly false.

    Byte-identity is trivially true of two empty directories, so the file set and
    row counts are asserted first and the comparison runs over files known to
    hold rows.  A clock, or a dict whose order is an accident, breaks this and
    nothing else.
    """
    repo = registered(tmp_path)
    seed(floor, desired_for(repo))
    seed_stores(repo / ".ergane", tag="widgets")

    first = tmp_path / "first"
    second = tmp_path / "second"
    for destination in (first, second):
        repo_export.export_records(
            slug=SLUG,
            repo=repo,
            runtime_root=repo / ".ergane",
            destination=destination,
        )

    assert {path.name for path in first.iterdir()} == EXPORT_FILES
    assert len(lines(first / "findings.jsonl")) == 1
    assert len(lines(first / "usage.jsonl")) == 1
    assert len(lines(first / "escalations.jsonl")) == 1
    assert (first / "digest.md").read_bytes() != b""

    for name in sorted(EXPORT_FILES):
        assert (first / name).read_bytes() == (second / name).read_bytes(), name


def test_forget_without_the_flag_writes_no_export(
    tmp_path: Path, floor: FakeScheduleServer
) -> None:
    """US5-S4: leaving quietly is the default; taking the records is a choice."""
    repo = registered(tmp_path)
    seed(floor, desired_for(repo))
    seed_stores(repo / ".ergane", tag="widgets")
    before = sorted(path.name for path in tmp_path.iterdir())

    result = _invoke(["repo", "forget", SLUG])

    assert result.code == EXIT_OK, result.stderr
    assert sorted(path.name for path in tmp_path.iterdir()) == before
    assert "export" not in result.stdout
    assert (repo / ".ergane" / "doctor.db").exists(), "no flag, no deletion either"


def test_export_refuses_a_destination_inside_the_runtime_root(
    tmp_path: Path, floor: FakeScheduleServer, no_epics: None
) -> None:
    """FR-013: outside `.ergane/`, which `--clean-runtime` may empty in the same act.

    `no_epics` is load-bearing, and the assertion names the export refusal rather
    than a substring both refusals share.  Written first without either, this
    test passed under the mutation that deletes the check it exists for: the
    capacity read reached the operator's real Temporal, found a real running
    epic, and refused for that reason instead — exit 1, and the words "runtime
    root" in a message about something else entirely.
    """
    repo = registered(tmp_path)
    seed(floor, desired_for(repo))
    seed_stores(repo / ".ergane", tag="widgets")
    inside = repo / ".ergane" / "records"

    result = _invoke(
        ["repo", "forget", SLUG, "--export", str(inside), "--clean-runtime"]
    )

    assert result.code == EXIT_USER
    assert "refusing to export into" in result.stderr
    assert not inside.exists()
    assert registry.load_registry().get(SLUG) is not None, "a refusal changes nothing"
    assert (repo / ".ergane" / "doctor.db").exists(), "and nothing was emptied"


def test_records_come_out_in_a_declared_order_not_an_accidental_one(
    tmp_path: Path, floor: FakeScheduleServer
) -> None:
    """The `ORDER BY` behind the byte-identity claim, tested where it is visible.

    Byte-identity alone cannot see this: SQLite hands back rows in rowid order on
    a store nothing has deleted from, so two exports of an unordered `SELECT`
    agree with each other and are still wrong — an engine that had rewritten a
    row would reorder the file under the operator with no other change.  The keys
    are therefore seeded in an order that is not their sorted order.
    """
    repo = registered(tmp_path)
    seed(floor, desired_for(repo))
    root = repo / ".ergane"
    seed_stores(root, tag="widgets")
    add_findings(root, "zeta/last", "alpha/first")
    out = tmp_path / "out"

    assert _invoke(["repo", "forget", SLUG, "--export", str(out)]).code == EXIT_OK

    keys = [json.loads(line)["key"] for line in lines(out / "findings.jsonl")]
    assert keys == ["alpha/first", "widgets/the-gate-never-ran", "zeta/last"]


def test_a_repo_that_never_migrated_keeps_its_records(
    tmp_path: Path, floor: FakeScheduleServer
) -> None:
    """The split state trap 12 names, and the one the operator's checkout was in.

    A repo joined before the rename has an empty `.ergane/` and a populated
    `.factory/`.  Resolving the root and stopping there hands the operator three
    empty files and calls it their history, so each store follows the data.
    """
    repo = registered(tmp_path)
    seed(floor, desired_for(repo))
    seed_stores(repo / ".factory", tag="widgets")
    assert (repo / ".ergane").is_dir() and list((repo / ".ergane").iterdir()) == []
    out = tmp_path / "out"

    assert _invoke(["repo", "forget", SLUG, "--export", str(out)]).code == EXIT_OK

    assert len(lines(out / "findings.jsonl")) == 1
    assert "widgets/the-gate-never-ran" in every_byte(out)


def test_no_credential_shaped_value_reaches_an_exported_file(
    tmp_path: Path, floor: FakeScheduleServer
) -> None:
    """FR-013's last clause, against the columns that actually hold free text.

    `history_summary` is a verbatim failure history and a finding's `notes` and
    `summary` are whatever the reporter wrote, so a run whose output echoed a
    proxy key puts that key in a store.  Every string is redacted at one choke
    point on the way out, which is why the digest — built from the same cleaned
    records the JSONL is — is covered without a second redactor.
    """
    repo = registered(tmp_path)
    seed(floor, desired_for(repo))
    seed_stores(repo / ".ergane", tag="widgets", secret=LEAKED_KEY)
    out = tmp_path / "out"

    assert _invoke(["repo", "forget", SLUG, "--export", str(out)]).code == EXIT_OK

    written = every_byte(out)
    assert LEAKED_KEY not in written
    assert "[REDACTED]" in written
    assert "the gate never ran" in written, "redaction, not omission"


def test_a_repo_that_never_ran_an_epic_exports_empty_files_and_creates_no_store(
    tmp_path: Path, floor: FakeScheduleServer
) -> None:
    """Every store is opened read-only, so an absent one stays absent.

    An export that bootstrapped a schema would leave three new databases in a
    repository that had just been told the engine was letting go of it.
    """
    repo = registered(tmp_path)
    seed(floor, desired_for(repo))
    out = tmp_path / "out"

    result = _invoke(["repo", "forget", SLUG, "--export", str(out)])

    assert result.code == EXIT_OK, result.stderr
    assert {path.name for path in out.iterdir()} == EXPORT_FILES
    assert (out / "findings.jsonl").read_bytes() == b""
    assert sorted(path.name for path in (repo / ".ergane").iterdir()) == []


def test_the_export_never_opens_a_store_for_writing(tmp_path: Path) -> None:
    """The reader's door is `mode=ro`, so a write is refused by the driver.

    Asserted against the connection the export uses rather than against its
    observable behaviour: "no file appeared" is also true of a reader that opened
    a store read-write and happened not to write.
    """
    root = tmp_path / "root"
    seed_stores(root, tag="widgets")

    conn = repo_export.open_store(root / "doctor.db")
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("DELETE FROM findings")
    conn.close()


# -----------------------------------------------------------------------------
# Pasted evidence — constitution VIII / D-037.  The judge sees this diff and the
# acceptance criteria, never a terminal, so US5's independent test is committed
# as the run that produced it.  Three findings, two usage rows and one escalation
# seeded under one repo's runtime root; two exports into two directories; run in
# this worktree with `uv run python`:
#
#   $ sha256sum first/* second/*
#   7bdd5949e1cc2c984aa4955e7603413852b28fae63f9756ece2ecda364475d9f  first/digest.md
#   15cea56502c0d3038e134cd7bd6cbc08f51d30c15e8c8d6334c05fa7e931bbb1  first/escalations.jsonl
#   6c7700687f74c21a0b725fa4f0c684042bc93fef153a25a57e4128deb05aa603  first/findings.jsonl
#   847eb301cf3b2d8a497f305031b613b8cf8ff289ecd4092786285cad880a6230  first/usage.jsonl
#   7bdd5949e1cc2c984aa4955e7603413852b28fae63f9756ece2ecda364475d9f  second/digest.md
#   15cea56502c0d3038e134cd7bd6cbc08f51d30c15e8c8d6334c05fa7e931bbb1  second/escalations.jsonl
#   6c7700687f74c21a0b725fa4f0c684042bc93fef153a25a57e4128deb05aa603  second/findings.jsonl
#   847eb301cf3b2d8a497f305031b613b8cf8ff289ecd4092786285cad880a6230  second/usage.jsonl
#
#   $ diff -r first second && echo IDENTICAL
#   IDENTICAL
#
#   $ cat first/digest.md
#   # Ergane export — widgets
#   [... prose, then the store table, verbatim: ...]
#   | store | rows | read from |
#   | --- | --- | --- |
#   | findings | 3 | .ergane/doctor.db |
#   | usage | 2 | .ergane/ledger.db |
#   | escalations | 1 | .ergane/verification.db |
#   [... then one section per file, each documenting its format, and: ...]
#   - `agent/escape` — critical, open, 2 occurrence(s): summary for agent/escape
#   - `doctor/ledger` — critical, open, 3 occurrence(s): summary for doctor/ledger
#   - `interpreter/ci-failure` — critical, open, 1 occurrence(s): summary for ...
#
#   $ head -c 200 first/findings.jsonl
#   {"key":"agent/escape","category":"agent","severity":"critical","status":
#   "open","summary":"summary for agent/escape","refs":"[\"factory/a.py:1\"]",
#   "notes":null,"source":"operator","occurrences":2,"first_seen":"2026-01-01
#
# The findings come out ordered by `key`, not by insertion: they were seeded
# interpreter, agent, doctor.  That matters more than the identical hashes do —
# an unordered `SELECT` agrees with insertion order on a fresh SQLite file, so it
# would have produced this same pair of matching hashes and still been wrong.
#
# Mutation battery — one production behaviour broken at a time, against this
# file plus `tests/test_repo_ast.py`.  A mutation nothing catches is a test that
# cannot fail, so the run is committed rather than summarised:
#
#   M1  digest carries a clock                    CAUGHT  1 failed, 15 passed
#   M2  findings read without ORDER BY            CAUGHT  1 failed, 15 passed
#   M3  the credential redactor is a no-op        CAUGHT  1 failed, 15 passed
#   M4  stores opened read-write, not mode=ro     CAUGHT  1 failed, 15 passed
#   M5  runtime root comes from the environment   CAUGHT  6 failed, 10 passed
#   M6  the tmp-tree removal guard is deleted     CAUGHT  1 failed, 15 passed
#   M7  --clean-runtime never asks about epics    CAUGHT  1 failed, 15 passed
#   M8  export destination never range-checked    CAUGHT  1 failed, 15 passed
#   M9  export runs without --export              CAUGHT  1 failed, 15 passed
#   M10 --clean-runtime empties nothing           CAUGHT  1 failed, 15 passed
#   M11 a legacy .factory/ store is ignored       CAUGHT  1 failed, 15 passed
#   M12 visit_Assign's empty-scope guard removed  CAUGHT  2 failed, 14 passed
#
# Three were NOT caught on the first run, and each named a real hole:
#
# - M2 and M11 were behaviours with no test at all — declared ordering, and the
#   legacy-store fallback.  Both were written, both claimed in a docstring, and
#   neither was ever run against a case that could tell the difference.
# - M8 is the one worth reading twice.  `test_export_refuses_a_destination_
#   inside_the_runtime_root` passed with the check deleted, because it also
#   passed `--clean-runtime` without binding the capacity read: the CLI reached
#   the operator's *real* Temporal, found a genuinely running epic, and refused
#   for that instead.  Exit 1 either way, and the phrase the assertion looked for
#   — "runtime root" — appears in both messages.  A test that consults a
#   production control plane is also one whose verdict depends on what the floor
#   is doing; `no_epics` and a refusal-specific assertion are the fix, and
#   `_open_client` having no pytest refusal of its own — unlike
#   `factory/roadmap/schedule.py` — is reported as a finding, not changed here.
#
# The gate, run the way the factory runs it — the declared `test` gate inside the
# real bwrap boundary over this worktree:
#
#   test: PASS exit=0 258.9s
#   2848 passed, 44 skipped, 5 warnings in 258.15s (0:04:18)
#
# (2828 before this story: 16 tests here and in `test_repo_ast.py`, plus four
# existing parametrized sweeps that now also cover `factory/cli/repo_export.py`.
# That run was over the committed tree; the only edit after it was this line.)
#
# And the same verb driven for real, outside pytest, against a scratch repo under
# an isolated `ERGANE_STATE_HOME` — because a green suite has shipped a command
# that could not start, and because two claims here are only true in production:
# the removal guard is inert without `PYTEST_CURRENT_TEST`, so no test can watch
# the deletion it protects, and the redactor's worth is a real key not reaching a
# real file.
#
#   $ ergane repo forget smokeapp --export .../records --clean-runtime
#   ergane: refusing to empty the runtime root of 'smokeapp' while epic(s) are
#   running: epic-capacity-can-5d08add3, epic-capacity-can-de7caf85. [...]
#   EXIT=1                       <- two genuinely open epics on the live floor
#
#   $ ergane repo forget smokeapp --export .../records
#   no roadmap schedule ergane-roadmap-smokeapp existed
#   wrote 1 findings record(s) to .../records/findings.jsonl
#   [... usage 1, escalations 0, then digest.md ...]
#   forgot smokeapp (.../smoke/app); the repository itself is untouched
#   EXIT=0
#   $ grep -c 'sk-REALLOOKINGKEY123456' records/*  -> no match in any file
#   $ ls -A app/.ergane                            -> all three stores still there
#
#   # then the deletion, guard inert:
#   emptied entries: 10   after: []   dir still exists: True
#   repo files intact: ['.ergane', '.git', 'README.md']
# -----------------------------------------------------------------------------
