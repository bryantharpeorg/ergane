"""The one thing an operator runs, and the one thing it must never do.

`factory-usage` is the read side of the ledger (FR-012, US2 scenario 4): it
answers "what did this persona / epic / requirement / retry cost?" and it does
so without being able to change the answer. Both halves are tested here.

The read half is thin on purpose. `rollup` already returns the exact document
`contracts/cli.md` publishes — `by`, echoed `filters`, `groups`, `totals` — so
`--json` is a dump, not a re-assembly, and the tests below assert the whole
document rather than sampling it. That is what makes the contract stable: a
renderer that recomputed anything would give the never-fabricate-a-zero rule
(FR-004/FR-005) a second implementation to drift from. The human table gets
looser assertions — alignment and number formatting are the renderer's business
— but not on the one point that is not cosmetic: a metric nobody measured must
not print as `0`, in any mode.

The write half is a guarantee about structure rather than about care. The CLI
opens the file with a `file:...?mode=ro` URI, so "no CLI invocation ever writes
to the ledger" is enforced by SQLite refusing the statement, not by the code
happening never to issue one. Two tests hold that line: the connection the CLI
opens rejects a mutation, and a run leaves the database byte for byte as it was.
A third guards the quieter version of the same mistake — pointing the CLI at a
path that does not exist must be exit 3, not a freshly created empty ledger,
which `factory.usage.ledger.connect` would happily do.

Exit codes are the scripting contract: 0 for any answer including an empty one,
2 for arguments the CLI cannot honour, 3 for a ledger it cannot read. On 3
stdout stays empty, so a `--json` consumer never parses an error message.

Written before `factory/usage/cli.py` exists (T020 precedes T022, and the
rollups it renders precede both): until they land, every test here fails at
import.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Callable, Iterator, NamedTuple

import pytest

from factory.usage.cli import main, open_readonly
from factory.usage.ledger import ROLLUP_DIMENSIONS, connect, upsert_record
from factory.usage.models import Termination, UsageRecord

#: Issue time is not a rollup dimension, so every seeded attempt shares one.
ISSUED_AT = "2026-07-20T09:00:00Z"


def seed_row(
    epic_id: str,
    node_id: str,
    attempt: int,
    persona: str,
    spec_ref: str,
    *,
    day: int,
    spend: float,
    tokens: tuple[int, int] | None = None,
    cache: tuple[int, int] | None = None,
    requests: int | None = None,
    confirmed: bool = True,
    termination: Termination = Termination.COMPLETED,
) -> UsageRecord:
    """One teardown's row. `tokens=None`/`cache=None` mean *nobody reported it*."""
    prompt_tokens, completion_tokens = tokens or (None, None)
    cache_read_tokens, cache_write_tokens = cache or (None, None)
    return UsageRecord(
        epic_id=epic_id,
        node_id=node_id,
        attempt=attempt,
        persona=persona,
        spec_ref=spec_ref,
        key_alias=f"{epic_id}:{node_id}:{attempt}",
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cache_read_tokens=cache_read_tokens,
        cache_write_tokens=cache_write_tokens,
        request_count=requests,
        spend_usd=spend,
        final_usage_confirmed=confirmed,
        termination=termination,
        issued_at=ISSUED_AT,
        torn_down_at=f"2026-07-{day:02d}T10:00:00Z",
    )


#: Five teardowns, enough for every dimension to have something to say: two
#: epics, three personas, a node with a retry, one requirement worked in both
#: epics, an unconfirmed fallback row, and an epic (`epic-b`) where no row
#: carried cache counters — the group that must serialize as `null`.
SEED: list[UsageRecord] = [
    seed_row("epic-a", "node-plan", 1, "architect", "add-usage/spec",
             day=20, tokens=(1000, 100), cache=(500, 50), requests=4, spend=0.10),
    seed_row("epic-a", "node-impl", 1, "implementer", "add-usage/ledger",
             day=21, tokens=(2000, 200), cache=(800, 80), requests=6, spend=0.20),
    seed_row("epic-a", "node-impl", 2, "implementer", "add-usage/ledger",
             day=22, tokens=(3000, 300), cache=(900, 90), requests=9, spend=0.30),
    seed_row("epic-a", "node-debug", 1, "debugger", "add-usage/ledger",
             day=23, spend=0.05, confirmed=False, termination=Termination.KILLED),
    seed_row("epic-b", "node-impl", 1, "implementer", "add-usage/ledger",
             day=24, tokens=(4000, 400), requests=5, spend=0.40),
]


def metrics(
    *,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    cache_read_tokens: int | None,
    cache_write_tokens: int | None,
    requests: int | None,
    spend_usd: float | None,
    rows: int,
    unconfirmed_rows: int,
) -> dict[str, Any]:
    """One group's (or the totals') metric block, per `contracts/cli.md`."""
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "cache_read_tokens": cache_read_tokens,
        "cache_write_tokens": cache_write_tokens,
        "requests": requests,
        "spend_usd": None if spend_usd is None else pytest.approx(spend_usd),
        "rows": rows,
        "unconfirmed_rows": unconfirmed_rows,
    }


def group(key: Any, **expected: Any) -> dict[str, Any]:
    """A whole expected group: its key plus the full metric block."""
    return {"key": key, **metrics(**expected)}


class Run(NamedTuple):
    """What an operator (or a script) sees: a status, and two streams."""

    code: int
    stdout: str
    stderr: str

    @property
    def json(self) -> dict[str, Any]:
        """`--json` output must be the whole of stdout, and nothing but."""
        return json.loads(self.stdout)


@pytest.fixture
def run(capsys: pytest.CaptureFixture[str]) -> Callable[..., Run]:
    """Invoke the CLI the way the console script does, capturing its exit.

    `main` returns its status so `sys.exit(main())` works as an entry point, but
    argparse raises `SystemExit` from inside it for usage errors; both are the
    same thing to a caller, so both are normalized to a code here.
    """

    def invoke(*argv: str) -> Run:
        try:
            code = main(list(argv))
        except SystemExit as exit_request:
            code = exit_request.code
        captured = capsys.readouterr()
        return Run(0 if code is None else int(code), captured.out, captured.err)

    return invoke


@pytest.fixture
def ledger_path(tmp_path: Path) -> Iterator[Path]:
    """A seeded ledger on disk, with no connection left open to it."""
    path = tmp_path / "ledger.db"
    conn = connect(path)
    try:
        for record in SEED:
            upsert_record(conn, record)
    finally:
        conn.close()
    yield path


def row_count(path: Path) -> int:
    conn = sqlite3.connect(path)
    try:
        return conn.execute("SELECT COUNT(*) FROM usage_records").fetchone()[0]
    finally:
        conn.close()


def line_for(output: str, key: str) -> str:
    """The single table line whose first column is `key`."""
    matches = [
        line for line in output.splitlines() if line.split() and line.split()[0] == key
    ]
    assert len(matches) == 1, f"expected exactly one line for {key!r}, got {matches!r}"
    return matches[0]


def numbers_in(line: str) -> list[float]:
    """Every field on a table line that renders as a number.

    Tolerant of formatting — separators and a currency prefix are stripped, and
    a placeholder for "not measured" simply is not a number and drops out.
    """
    values = []
    for field in line.split():
        try:
            values.append(float(field.replace(",", "").replace("_", "").lstrip("$")))
        except ValueError:
            continue
    return values


# --- the rollups, rendered -------------------------------------------------


@pytest.mark.parametrize("dimension", ROLLUP_DIMENSIONS)
def test_every_dimension_the_contract_offers_is_reachable(
    run: Callable[..., Run], ledger_path: Path, dimension: str
) -> None:
    # `--by` accepts exactly the dimensions the ledger can group by, so a
    # dimension cannot exist in SQL and be unreachable from the CLI.
    result = run("--db", str(ledger_path), "--by", dimension, "--json")

    assert result.code == 0
    assert result.json["by"] == dimension
    assert result.json["totals"]["rows"] == len(SEED)


def test_the_json_document_is_the_contract(
    run: Callable[..., Run], ledger_path: Path
) -> None:
    result = run("--db", str(ledger_path), "--by", "persona", "--json")

    # The whole document, not a sample of it: `contracts/cli.md` promises these
    # keys, this nesting, and groups in a deterministic order to scripts that
    # will still be parsing it after this component ships.
    assert result.code == 0
    assert result.json == {
        "by": "persona",
        "filters": {"epic": None, "since": None},
        "groups": [
            group(
                "architect",
                prompt_tokens=1000, completion_tokens=100,
                cache_read_tokens=500, cache_write_tokens=50,
                requests=4, spend_usd=0.10, rows=1, unconfirmed_rows=0,
            ),
            group(
                "debugger",
                prompt_tokens=None, completion_tokens=None,
                cache_read_tokens=None, cache_write_tokens=None,
                requests=None, spend_usd=0.05, rows=1, unconfirmed_rows=1,
            ),
            group(
                "implementer",
                prompt_tokens=9000, completion_tokens=900,
                cache_read_tokens=1700, cache_write_tokens=170,
                requests=20, spend_usd=0.90, rows=3, unconfirmed_rows=0,
            ),
        ],
        "totals": metrics(
            prompt_tokens=10000, completion_tokens=1000,
            cache_read_tokens=2200, cache_write_tokens=220,
            requests=24, spend_usd=1.05, rows=5, unconfirmed_rows=1,
        ),
    }


def test_an_unmeasured_metric_serializes_as_null(
    run: Callable[..., Run], ledger_path: Path
) -> None:
    result = run("--db", str(ledger_path), "--by", "epic", "--json")
    epic_b = {entry["key"]: entry for entry in result.json["groups"]}["epic-b"]

    # No row in epic-b carried cache counters. `null`, not `0` — and asserted
    # against the raw text too, because a renderer that stringified `None` into
    # a JSON `0` would still satisfy a Python-side `is None` on a parsed dict.
    assert epic_b["cache_read_tokens"] is None
    assert epic_b["cache_write_tokens"] is None
    assert epic_b["prompt_tokens"] == 4000
    assert '"cache_read_tokens": null' in re.sub(r"\s+", " ", result.stdout)


def test_the_retry_view_keys_stay_numbers(
    run: Callable[..., Run], ledger_path: Path
) -> None:
    result = run("--db", str(ledger_path), "--by", "attempt", "--json")

    # `--by attempt` is the retry-cost view (FR-006): ordinals are numbers so a
    # script can say `key >= 2` without parsing strings.
    assert [entry["key"] for entry in result.json["groups"]] == [1, 2]
    assert result.json["groups"][1]["spend_usd"] == pytest.approx(0.30)


def test_the_filters_are_applied_and_echoed(
    run: Callable[..., Run], ledger_path: Path
) -> None:
    result = run(
        "--db", str(ledger_path),
        "--by", "persona", "--epic", "epic-a", "--since", "2026-07-22", "--json",
    )

    # `--since` filters on `torn_down_at` and includes the named day, so the
    # 07-22 retry and the 07-23 fallback survive and the earlier rows do not.
    assert result.code == 0
    assert result.json["filters"] == {"epic": "epic-a", "since": "2026-07-22"}
    assert [entry["key"] for entry in result.json["groups"]] == ["debugger", "implementer"]
    assert result.json["totals"]["rows"] == 2
    assert result.json["totals"]["spend_usd"] == pytest.approx(0.35)


def test_an_empty_result_is_a_success(
    run: Callable[..., Run], ledger_path: Path
) -> None:
    result = run("--db", str(ledger_path), "--by", "persona", "--epic", "epic-none", "--json")

    # "Nothing matched" is an answer, not a failure (exit 0, cli.md).
    assert result.code == 0
    assert result.json["groups"] == []
    assert result.json["totals"]["rows"] == 0
    assert result.json["totals"]["prompt_tokens"] is None


# --- the human table -------------------------------------------------------


def test_the_table_lists_every_group_and_totals_them(
    run: Callable[..., Run], ledger_path: Path
) -> None:
    result = run("--db", str(ledger_path), "--by", "node")

    # One line per group, keyed `epic:node` so two epics' `node-impl` stay
    # apart, plus the footer an operator reads first: the grand total and how
    # much of it is an estimate.
    assert result.code == 0
    for key in ("epic-a:node-debug", "epic-a:node-impl", "epic-a:node-plan",
                "epic-b:node-impl"):
        line_for(result.stdout, key)
    assert "9000" in re.sub(r"[,_]", "", line_for(result.stdout, "epic-a:node-impl"))
    assert re.search(r"(?i)total", result.stdout)
    assert re.search(r"(?i)unconf", result.stdout)


def test_the_table_never_prints_a_fabricated_zero(
    run: Callable[..., Run], ledger_path: Path
) -> None:
    result = run("--db", str(ledger_path), "--by", "persona")
    debugger = line_for(result.stdout, "debugger")

    # The killed debugger's tokens were never measured. Whatever placeholder the
    # renderer picks, it may not be a `0`: every number on that line is one the
    # proxy actually reported (spend 0.05) or one always knowable (1 row, 1
    # unconfirmed). A printed 0 would read as "this attempt used nothing".
    assert 0.0 not in numbers_in(debugger)
    assert 0.05 in numbers_in(debugger)


def test_json_mode_prints_json_and_nothing_else(
    run: Callable[..., Run], ledger_path: Path
) -> None:
    table = run("--db", str(ledger_path), "--by", "epic")
    machine = run("--db", str(ledger_path), "--by", "epic", "--json")

    # `--json` replaces the table rather than decorating it: stdout parses whole
    # (the `.json` property would raise on a stray header or footer line), while
    # the default mode is the aligned table with its own footer.
    assert machine.json["by"] == "epic"
    assert line_for(table.stdout, "epic-a")
    assert re.search(r"(?i)total", table.stdout)


# --- where the ledger comes from -------------------------------------------


def test_the_environment_supplies_the_default_path(
    run: Callable[..., Run], ledger_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FACTORY_LEDGER_PATH", str(ledger_path))

    result = run("--by", "epic", "--json")

    assert result.code == 0
    assert result.json["totals"]["rows"] == len(SEED)


def test_the_db_flag_beats_the_environment(
    run: Callable[..., Run], ledger_path: Path, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FACTORY_LEDGER_PATH", str(tmp_path / "elsewhere.db"))

    result = run("--db", str(ledger_path), "--by", "epic", "--json")

    assert result.code == 0
    assert result.json["totals"]["rows"] == len(SEED)


def test_without_a_flag_or_an_environment_it_is_dot_factory_ledger_db(
    run: Callable[..., Run], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("FACTORY_LEDGER_PATH", raising=False)
    monkeypatch.chdir(tmp_path)
    conn = connect(tmp_path / ".factory" / "ledger.db")
    try:
        upsert_record(conn, SEED[0])
    finally:
        conn.close()

    result = run("--by", "persona", "--json")

    # The path the rest of the factory writes to, so the documented invocation
    # in quickstart §3 works from a repo root with no flags.
    assert result.code == 0
    assert [entry["key"] for entry in result.json["groups"]] == ["architect"]


# --- exit codes ------------------------------------------------------------


@pytest.mark.parametrize("dimension", ["cost", "spec_ref", "", "persona; DROP TABLE"])
def test_an_unknown_dimension_is_a_usage_error(
    run: Callable[..., Run], ledger_path: Path, dimension: str
) -> None:
    # Exit 2, and refused at the argument boundary — the dimension names a
    # column in generated SQL and never reaches it unvalidated.
    assert run("--db", str(ledger_path), "--by", dimension).code == 2


def test_the_dimension_is_required(run: Callable[..., Run], ledger_path: Path) -> None:
    assert run("--db", str(ledger_path)).code == 2


@pytest.mark.parametrize("since", ["2026/07/23", "yesterday", "07-23-2026", "2026-7-3"])
def test_a_malformed_since_is_a_usage_error(
    run: Callable[..., Run], ledger_path: Path, since: str
) -> None:
    # `--since` compares against ISO `torn_down_at` values, so a date in any
    # other shape silently matches the wrong rows. Better to refuse it (exit 2)
    # than to answer a question the operator did not ask.
    assert run("--db", str(ledger_path), "--by", "epic", "--since", since).code == 2


def test_a_missing_ledger_is_exit_3_and_is_not_created(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    missing = tmp_path / "nowhere" / "ledger.db"

    result = run("--db", str(missing), "--by", "persona", "--json")

    # `ledger.connect` would create the file and its directory; the read side
    # must not. An operator who typos `--db` gets an error, not a new empty
    # ledger that reports zero spend.
    assert result.code == 3
    assert not missing.exists()
    assert not missing.parent.exists()
    assert result.stdout == ""
    assert result.stderr != ""


def test_an_unreadable_ledger_is_exit_3(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    not_a_database = tmp_path / "ledger.db"
    not_a_database.write_bytes(b"this is not a sqlite file")

    result = run("--db", str(not_a_database), "--by", "persona")

    assert result.code == 3
    assert result.stdout == ""


# --- structurally read-only (US2 scenario 4) -------------------------------


def test_the_connection_the_cli_opens_refuses_writes(ledger_path: Path) -> None:
    conn = open_readonly(ledger_path)
    try:
        # `mode=ro`: "no CLI invocation ever writes to the ledger" is SQLite
        # refusing the statement, not the code happening not to issue one.
        with pytest.raises(sqlite3.OperationalError, match="(?i)readonly"):
            conn.execute("DELETE FROM usage_records")
        with pytest.raises(sqlite3.OperationalError, match="(?i)readonly"):
            conn.execute("UPDATE usage_records SET spend_usd = 0")
    finally:
        conn.close()


def test_open_readonly_will_not_create_a_ledger(tmp_path: Path) -> None:
    missing = tmp_path / "absent.db"

    with pytest.raises(sqlite3.OperationalError):
        open_readonly(missing)

    assert not missing.exists()


def test_a_cli_run_leaves_the_ledger_byte_identical(
    run: Callable[..., Run], ledger_path: Path
) -> None:
    before = hashlib.sha256(ledger_path.read_bytes()).hexdigest()

    for dimension in ROLLUP_DIMENSIONS:
        assert run("--db", str(ledger_path), "--by", dimension, "--json").code == 0

    assert hashlib.sha256(ledger_path.read_bytes()).hexdigest() == before
    assert row_count(ledger_path) == len(SEED)
