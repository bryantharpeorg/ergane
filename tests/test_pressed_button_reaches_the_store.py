"""A pressed button lands, or the operator is told why — never silence.

At 03:16Z on 2026-08-21 an operator pressed a button on a live escalation and
nothing happened: no signal reached the workflow, no row changed in the store,
and no log line anywhere named the escalation. The press did not lose a race and
was not refused; it *vanished*, and the reason nobody could say which branch
swallowed it is that the branches had never been enumerated.

So this file does not test a fix to one branch. It enumerates the press path
**from the code** and holds every branch in it to one contract (FR-006):

    exactly one of {the signal is sent and the row is resolved}
    or          {a named refusal comes back to the operator},

and, either way, a line an operator can read without a debugger, naming the
escalation id (FR-007).

Three mechanical enumerations, none of them a hand-written list:

- **`_press_path()`** walks `CallbackBridge.handle`'s AST and follows every
  `self.<method>(...)` call transitively, so the set of methods a press can
  return from is derived from the tree rather than remembered. Add a helper to
  the press path and it is enumerated the moment it is called.
- **`_return_spans()`** collects every `return` statement in those methods.
  `test_every_return_in_the_press_path_is_taken_by_a_branch` traces the suite's
  own execution with `sys.settrace` and fails if any of them is a branch no
  scenario below reaches. A new unreached `return` is the 03:16Z defect coming
  back, and this is what refuses it.
- **`BridgeOutcome`** — the enumeration the module already had (the plan's trap
  8). Every member must be produced by a branch here, and every branch must
  produce a member.

`BRANCHES` is the registry those three checks run over. A branch declares what
it expects the press to do — signalled or not, row resolved or not — and the
contract is asserted uniformly, so a branch cannot be added with a weaker
promise than its neighbours.

**The control (US2-S4, FR-008).** `stale_already_resolved`, `stale_expired` and
`stale_race_to_expiry` are here to fail if the staleness guard is ever removed
to make presses "land". A press on a settled escalation must stay refused, must
send nothing new, must leave the decision that was already made standing, and
must be *told it is stale* — an old message re-answering a live node is worse
than a dropped press, because nobody learns the node moved on.

Written before the branch-closing change exists: `_handle_press` and
`BridgeOutcome.BRIDGE_ERROR` are named here first, so until they land this file
fails at import.
"""

from __future__ import annotations

import ast
import inspect
import logging
import sqlite3
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator

import pytest

from factory.notify import service
from factory.notify.adapter import ESCALATION_ADAPTER_ENV
from factory.notify.service import (
    SIGNAL_NAME,
    UNPARSED_ESCALATION,
    BridgeOutcome,
    CallbackBridge,
)
from factory.verify.models import EscalationChoice
from factory.verify.store import (
    EXPIRED,
    connect,
    expire_escalation,
    insert_escalation,
)

# The fakes are 008's, imported rather than rebuilt: a second Telegram fake
# would be a second opinion about what an update looks like, and the branch
# enumeration below is only as honest as the shape it is driven with.
from tests.test_notify import (
    ESCALATION_ID,
    RESOLVED_AT,
    WORKFLOW_ID,
    FakeCallbackQuery,
    FakeTemporalClient,
    FakeUpdate,
    SentSignal,
    escalation_row,
    make_escalation,
    press,
)

#: An identity the configured list does not carry, for the one branch that
#: refuses before it reads anything.
INTRUDER = "@not-the-operator"
AUTHORIZED = "@the-operator"

#: What `_press_path` starts its walk from. The *only* name here that is
#: hand-written; everything it reaches is derived.
PRESS_ENTRY = "handle"


# --- fixtures ---------------------------------------------------------------


@pytest.fixture(autouse=True)
def telegram_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    """The bridge relays through 008's transport unless a deployment says
    otherwise — and a stray export must not decide which branches this file
    walks."""
    monkeypatch.delenv(ESCALATION_ADAPTER_ENV, raising=False)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / ".factory" / "verification.db"


@pytest.fixture
def store(db_path: Path) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def client() -> FakeTemporalClient:
    return FakeTemporalClient()


@pytest.fixture
def bridge(db_path: Path, client: FakeTemporalClient) -> CallbackBridge:
    return CallbackBridge(db_path=db_path, client=client, now=lambda: RESOLVED_AT)


# --- the fakes this file adds ------------------------------------------------


class FakeUser:
    def __init__(self, username: str) -> None:
        self.username = username
        self.id = 4242


def pressed(
    choice: EscalationChoice | str = EscalationChoice.RETRY,
    *,
    escalation_id: str = ESCALATION_ID,
    username: str | None = None,
) -> FakeUpdate:
    """One press, optionally from a named sender."""
    update = press(choice, escalation_id=escalation_id)
    update.callback_query.from_user = None if username is None else FakeUser(username)
    return update


class NoCallbackUpdate:
    """An update that is not a press at all — the one branch with nobody to
    toast at, and therefore the one that has to be recorded or it is silence."""

    callback_query = None


class HostileQuery(FakeCallbackQuery):
    """A callback query Telegram will not let us answer.

    Not hypothetical: the Bot API rejects an answer to a query it considers too
    old ("query ID is invalid"), which is exactly the state a callback is in
    after a bridge restart. Before this story that exception escaped `handle`,
    so the press it belonged to left no trace at all.
    """

    async def answer(self, text: str | None = None, **kwargs: Any) -> None:
        self.answers.append(text)  # recorded, then refused
        raise RuntimeError("Bad Request: query ID is invalid")


# --- the branch registry -----------------------------------------------------


@dataclass
class Arrange:
    """What a branch is handed to set its world up before the press."""

    store: sqlite3.Connection
    client: FakeTemporalClient
    patch: pytest.MonkeyPatch


@dataclass(frozen=True)
class Branch:
    """One reachable way `handle` can end, and what it owes the operator."""

    name: str
    outcome: BridgeOutcome
    build: Callable[[Arrange], Any]
    #: Did the workflow hear about this press?
    signalled: bool
    #: Did this press leave the row carrying its own choice?
    resolves_row: bool
    #: The escalation id the journal line must name — `None` only where the
    #: press named none, because `parse_callback_data` refused the payload.
    names: str | None = ESCALATION_ID
    #: False only for the update that carries no callback query at all: there is
    #: nobody to toast at, which is exactly why the journal line is not optional.
    toastable: bool = True
    responders: tuple[str, ...] = ()
    #: Substring the operator's toast must contain, lowercased.
    notice_says: str | None = None


def _seed(arrange: Arrange, **overrides: Any) -> None:
    insert_escalation(arrange.store, make_escalation(**overrides))


def _live(arrange: Arrange) -> Any:
    _seed(arrange)
    return pressed(EscalationChoice.RETRY)


def _no_callback(arrange: Arrange) -> Any:
    _seed(arrange)
    return NoCallbackUpdate()


def _foreign_payload(arrange: Arrange) -> Any:
    _seed(arrange)
    return FakeUpdate("someoneelse:whatever")


def _unauthorized(arrange: Arrange) -> Any:
    _seed(arrange)
    return pressed(EscalationChoice.RETRY, username=INTRUDER)


def _no_row(arrange: Arrange) -> Any:
    _seed(arrange)
    return pressed(EscalationChoice.RETRY, escalation_id="ffffffffffff")


def _never_offered(arrange: Arrange) -> Any:
    _seed(arrange, choices=[EscalationChoice.RETRY])
    return pressed(EscalationChoice.KILL_EPIC)


def _already_resolved(arrange: Arrange) -> Any:
    _seed(arrange)
    service.resolve_escalation(
        arrange.store, ESCALATION_ID, EscalationChoice.KILL, resolved_at=RESOLVED_AT
    )
    return pressed(EscalationChoice.RETRY)


def _expired(arrange: Arrange) -> Any:
    _seed(arrange)
    expire_escalation(arrange.store, ESCALATION_ID, resolved_at=RESOLVED_AT)
    return pressed(EscalationChoice.RETRY)


def _unreachable_orchestrator(arrange: Arrange) -> Any:
    _seed(arrange)

    def refuse(signal: SentSignal) -> None:
        raise RuntimeError("temporal unreachable")

    arrange.client.on_signal = refuse
    return pressed(EscalationChoice.RETRY)


def _expires_mid_signal(arrange: Arrange) -> Any:
    """The read goes stale while the signal is in flight — the guarded UPDATE
    is the authority, and the timeout's decision stands (R12)."""
    _seed(arrange)
    arrange.client.on_signal = lambda _signal: expire_escalation(
        arrange.store, ESCALATION_ID, resolved_at=RESOLVED_AT
    )
    return pressed(EscalationChoice.RETRY)


def _row_vanishes_mid_signal(arrange: Arrange) -> Any:
    """The row is gone by the time the guarded UPDATE runs — a store rebuilt
    under a running bridge. `_answer_settled` has to answer a `None`."""
    _seed(arrange)

    def rebuild_the_store(_signal: SentSignal) -> None:
        arrange.store.execute(
            "DELETE FROM escalations WHERE escalation_id = ?", (ESCALATION_ID,)
        )
        arrange.store.commit()

    arrange.client.on_signal = rebuild_the_store
    return pressed(EscalationChoice.RETRY)


def _unreadable_row(arrange: Arrange) -> Any:
    """A stored choice this build's enum does not carry.

    `_escalation_from_row` maps `choices` through `EscalationChoice`, so a row
    written by a deployment whose vocabulary has moved on makes `get_escalation`
    raise — before the signal, before any notice, from a line no operator would
    think to look at. One of the ways the 03:16Z press could vanish.
    """
    _seed(arrange)
    arrange.store.execute(
        "UPDATE escalations SET choices = ? WHERE escalation_id = ?",
        ('["MELT_DOWN"]', ESCALATION_ID),
    )
    arrange.store.commit()
    return pressed(EscalationChoice.RETRY)


def _store_fails_after_the_signal(arrange: Arrange) -> Any:
    """The signal lands and the store then refuses the write.

    The worst shape of the defect: the workflow has the decision and the row
    does not, so a toast saying "press again" would be a lie. The operator must
    still be told, and the line must say the decision was already sent.
    """
    _seed(arrange)

    def exploding(*_args: Any, **_kwargs: Any) -> bool:
        raise sqlite3.OperationalError("database is locked")

    arrange.patch.setattr(service, "resolve_escalation", exploding)
    return pressed(EscalationChoice.RETRY)


def _telegram_refuses_the_toast(arrange: Arrange) -> Any:
    """Telegram rejects the answer, and the press still has to land.

    A callback the Bot API considers too old cannot be acknowledged. That is a
    fact about the transport, not a reason to drop a decision the operator made
    — and not a reason for the store to disagree with the workflow.
    """
    _seed(arrange)
    update = pressed(EscalationChoice.RETRY)
    update.callback_query = HostileQuery(update.callback_query.data)
    return update


#: Every reachable end of `handle`, and what each one owes.
#:
#: This is a registry, not a list of tests: the three enumerations at the top of
#: this file check it against the code rather than against anyone's memory.
BRANCHES: tuple[Branch, ...] = (
    Branch(
        name="live_escalation",
        outcome=BridgeOutcome.RESOLVED,
        build=_live,
        signalled=True,
        resolves_row=True,
    ),
    Branch(
        name="not_a_callback",
        outcome=BridgeOutcome.MALFORMED,
        build=_no_callback,
        signalled=False,
        resolves_row=False,
        names=None,
        toastable=False,
    ),
    Branch(
        name="payload_from_elsewhere",
        outcome=BridgeOutcome.MALFORMED,
        build=_foreign_payload,
        signalled=False,
        resolves_row=False,
        names=None,
        notice_says="not one of this factory's",
    ),
    Branch(
        name="unauthorized_sender",
        outcome=BridgeOutcome.UNAUTHORIZED,
        build=_unauthorized,
        signalled=False,
        resolves_row=False,
        responders=(AUTHORIZED,),
        notice_says="not an authorized responder",
    ),
    Branch(
        name="row_is_gone",
        outcome=BridgeOutcome.UNKNOWN,
        build=_no_row,
        signalled=False,
        resolves_row=False,
        names="ffffffffffff",
        notice_says="no longer on record",
    ),
    Branch(
        name="choice_never_offered",
        outcome=BridgeOutcome.INVALID_CHOICE,
        build=_never_offered,
        signalled=False,
        resolves_row=False,
        notice_says="not offered",
    ),
    Branch(
        name="stale_already_resolved",
        outcome=BridgeOutcome.ALREADY_RESOLVED,
        build=_already_resolved,
        signalled=False,
        resolves_row=False,
        notice_says="stale",
    ),
    Branch(
        name="stale_expired",
        outcome=BridgeOutcome.EXPIRED,
        build=_expired,
        signalled=False,
        resolves_row=False,
        notice_says="stale",
    ),
    Branch(
        name="orchestrator_unreachable",
        outcome=BridgeOutcome.SIGNAL_FAILED,
        build=_unreachable_orchestrator,
        signalled=False,
        resolves_row=False,
        notice_says="press again",
    ),
    Branch(
        name="stale_race_to_expiry",
        outcome=BridgeOutcome.EXPIRED,
        build=_expires_mid_signal,
        signalled=True,
        resolves_row=False,
        notice_says="stale",
    ),
    Branch(
        name="row_vanishes_mid_signal",
        outcome=BridgeOutcome.UNKNOWN,
        build=_row_vanishes_mid_signal,
        signalled=True,
        resolves_row=False,
        notice_says="no longer on record",
    ),
    Branch(
        name="row_this_build_cannot_read",
        outcome=BridgeOutcome.BRIDGE_ERROR,
        build=_unreadable_row,
        signalled=False,
        resolves_row=False,
        notice_says="press again",
    ),
    Branch(
        name="store_fails_after_the_signal",
        outcome=BridgeOutcome.BRIDGE_ERROR,
        build=_store_fails_after_the_signal,
        signalled=True,
        resolves_row=False,
        notice_says="reached the workflow",
    ),
    Branch(
        name="telegram_refuses_the_toast",
        outcome=BridgeOutcome.RESOLVED,
        build=_telegram_refuses_the_toast,
        signalled=True,
        resolves_row=True,
    ),
)


# --- driving one branch ------------------------------------------------------


@dataclass
class Driven:
    """What one branch actually did, as an operator could observe it."""

    branch: Branch
    outcome: BridgeOutcome
    signals: list[SentSignal]
    row: dict[str, Any] | None
    notices: list[str]
    log: str
    lines: set[int] = field(default_factory=set)


async def drive(branch: Branch, root: Path, caplog: pytest.LogCaptureFixture) -> Driven:
    """Run one branch end to end against a real store and a fake Telegram."""
    db_path = root / branch.name / "verification.db"
    conn = connect(db_path)
    client = FakeTemporalClient()
    covered: set[int] = set()
    try:
        with pytest.MonkeyPatch.context() as patch:
            patch.delenv(ESCALATION_ADAPTER_ENV, raising=False)
            arrange = Arrange(store=conn, client=client, patch=patch)
            update = branch.build(arrange)
            bridge = CallbackBridge(
                db_path=db_path,
                client=client,
                now=lambda: RESOLVED_AT,
                authorized_responders=branch.responders,
            )
            caplog.clear()
            with caplog.at_level(logging.INFO, logger=service.__name__):
                with trace_lines(service.__file__, covered):
                    outcome = await bridge.handle(update)

        query = getattr(update, "callback_query", None)
        notices = [] if query is None else [str(text) for text in _texts(query.answers)]
        row = _row_or_none(conn, ESCALATION_ID)
    finally:
        conn.close()

    return Driven(
        branch=branch,
        outcome=outcome,
        signals=client.signals,
        row=row,
        notices=notices,
        log="\n".join(record.getMessage() for record in caplog.records),
        lines=covered,
    )


def _texts(answers: list[Any]) -> list[str]:
    """`FakeCallbackQuery` records calls; `HostileQuery` records bare text."""
    return [
        answer.text if hasattr(answer, "text") else answer
        for answer in answers
        if (answer.text if hasattr(answer, "text") else answer)
    ]


def _row_or_none(conn: sqlite3.Connection, escalation_id: str) -> dict[str, Any] | None:
    try:
        return escalation_row(conn, escalation_id)
    except AssertionError:
        return None


# --- reading the press path out of the code ---------------------------------


def _press_path() -> dict[str, ast.AST]:
    """Every `CallbackBridge` method a press can reach, walked from `handle`.

    Derived, never listed: the walk follows `self.<name>(...)` transitively, so
    a helper extracted out of `handle` tomorrow joins the enumeration by being
    called rather than by someone remembering to name it here. This is the
    answer to "one of them swallowed a press and nobody can say which".
    """
    module = ast.parse(Path(inspect.getfile(service)).read_text(encoding="utf-8"))
    klass = next(
        node
        for node in module.body
        if isinstance(node, ast.ClassDef) and node.name == CallbackBridge.__name__
    )
    methods = {
        node.name: node
        for node in klass.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    reached: dict[str, ast.AST] = {}
    pending = [PRESS_ENTRY]
    while pending:
        name = pending.pop()
        if name in reached or name not in methods:
            continue
        node = methods[name]
        reached[name] = node
        for call in ast.walk(node):
            if (
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and isinstance(call.func.value, ast.Name)
                and call.func.value.id == "self"
            ):
                pending.append(call.func.attr)
    return reached


def _return_spans() -> dict[str, list[range]]:
    """Every `return` in the press path, as the lines it occupies.

    A span rather than a line: a `return` whose expression wraps reports its
    line events across the wrap, and the branch is taken if execution touched
    any of them.
    """
    spans: dict[str, list[range]] = {}
    for name, node in _press_path().items():
        for statement in ast.walk(node):
            if isinstance(statement, ast.Return):
                spans.setdefault(name, []).append(
                    range(statement.lineno, (statement.end_lineno or statement.lineno) + 1)
                )
    return spans


@contextmanager
def trace_lines(filename: str, into: set[int]) -> Iterator[None]:
    """Record which lines of `filename` execute inside the block.

    `sys.settrace` rather than a coverage dependency (constitution III): nothing
    new is installed to answer a question the interpreter already answers.
    """

    def local(frame: Any, event: str, _arg: Any) -> Any:
        if event == "line":
            into.add(frame.f_lineno)
        return local

    def entered(frame: Any, event: str, _arg: Any) -> Any:
        if event == "call" and frame.f_code.co_filename == filename:
            into.add(frame.f_lineno)
            return local
        return None

    previous = sys.gettrace()
    sys.settrace(entered)
    try:
        yield
    finally:
        sys.settrace(previous)


# --- US2-S1 (FR-006): the press lands ---------------------------------------


async def test_a_press_on_a_live_escalation_signals_and_resolves_the_row(
    bridge: CallbackBridge, client: FakeTemporalClient, store: sqlite3.Connection
) -> None:
    """The whole point of the button. Signal first, then the guarded UPDATE."""
    insert_escalation(store, make_escalation())

    outcome = await bridge.handle(pressed(EscalationChoice.RETRY))

    assert outcome is BridgeOutcome.RESOLVED
    assert client.signals == [
        SentSignal(WORKFLOW_ID, SIGNAL_NAME, [ESCALATION_ID, EscalationChoice.RETRY.value])
    ]
    row = escalation_row(store, ESCALATION_ID)
    assert row["resolution"] == EscalationChoice.RETRY.value
    assert row["resolved_at"] == RESOLVED_AT
    assert row["resolved_via"] == "BUTTON"


# --- US2-S2 (FR-006): every branch lands or refuses by name ------------------


@pytest.mark.parametrize("branch", BRANCHES, ids=lambda branch: branch.name)
async def test_every_press_branch_lands_or_names_its_refusal(
    branch: Branch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """FR-006, per branch: signalled-and-resolved, or a named refusal. Never both
    and never neither."""
    driven = await drive(branch, tmp_path, caplog)

    assert driven.outcome is branch.outcome

    if branch.resolves_row:
        assert driven.signals, f"{branch.name}: the row moved without a signal"
        assert driven.row is not None
        assert driven.row["resolution"] == EscalationChoice.RETRY.value
        assert driven.row["resolved_via"] == "BUTTON"
    else:
        # A refusal is only a refusal if the operator can read it — and the one
        # branch with nobody to toast at is the reason FR-007's record below is
        # the half with no exceptions.
        if branch.toastable:
            assert driven.notices, f"{branch.name}: refused the press in silence"
        assert driven.row is None or driven.row["resolution"] != (
            EscalationChoice.RETRY.value
        ), f"{branch.name}: a refused press moved the row anyway"

    assert bool(driven.signals) == branch.signalled, (
        f"{branch.name}: signalled={bool(driven.signals)}, expected {branch.signalled}"
    )

    if branch.notice_says is not None:
        assert any(
            branch.notice_says in notice.lower() for notice in driven.notices
        ), f"{branch.name}: no notice said {branch.notice_says!r}; got {driven.notices}"


async def test_every_return_in_the_press_path_is_taken_by_a_branch(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The enumeration itself (US2-S2): read the returns out of the code, then
    prove the registry reaches all of them.

    Hand-listing the branches is how one of them came to swallow a press. A
    `return` in `handle`'s call graph that no scenario above reaches is a branch
    nobody has ever observed — which is exactly what the 03:16Z press found.
    """
    covered: set[int] = set()
    for branch in BRANCHES:
        covered |= (await drive(branch, tmp_path, caplog)).lines

    unreached = {
        f"{name}:{span.start}"
        for name, spans in _return_spans().items()
        for span in spans
        if not covered & set(span)
    }

    assert not unreached, (
        "these returns in CallbackBridge.handle's call graph are branches no "
        f"scenario reaches, so nobody can say what a press through them does: {sorted(unreached)}"
    )


def test_every_bridge_outcome_is_produced_by_a_branch() -> None:
    """`BridgeOutcome` is the enumeration the module already had (trap 8). A
    member no branch produces is a situation nobody has tested; a branch whose
    member does not exist is a fiction."""
    declared = {outcome for outcome in BridgeOutcome}
    covered = {branch.outcome for branch in BRANCHES}

    assert covered == declared, (
        f"outcomes with no branch: {sorted(o.value for o in declared - covered)}; "
        f"branches with no outcome: {sorted(o.value for o in covered - declared)}"
    )


# --- US2-S3 (FR-007): every press is recorded -------------------------------


@pytest.mark.parametrize("branch", BRANCHES, ids=lambda branch: branch.name)
async def test_every_handled_press_is_recorded_naming_the_escalation(
    branch: Branch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """FR-007. The 03:16Z press left no signal, no row change and no line naming
    the escalation. A press an operator cannot find in the journal is a press
    that needs a debugger to explain, which is the thing this forbids."""
    driven = await drive(branch, tmp_path, caplog)

    assert driven.log, f"{branch.name}: the press left no trace at all"
    assert branch.outcome.value in driven.log, (
        f"{branch.name}: nothing recorded says what the press did"
    )
    if branch.names is not None:
        assert branch.names in driven.log, (
            f"{branch.name}: recorded without naming the escalation"
        )
    else:
        assert UNPARSED_ESCALATION in driven.log, (
            f"{branch.name}: a press that named no escalation still has to be filed"
        )


async def test_the_press_that_crashes_the_bridge_still_names_its_escalation(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The 03:16Z shape, reproduced and closed.

    A row this build cannot read makes `get_escalation` raise from inside
    `handle`. Before this story that exception left the bridge through the poll
    loop: no signal, no row change, and a traceback that never named which
    escalation the operator had pressed.
    """
    driven = await drive(_branch("row_this_build_cannot_read"), tmp_path, caplog)

    assert driven.outcome is BridgeOutcome.BRIDGE_ERROR
    assert driven.signals == []
    assert driven.row is not None and driven.row["resolution"] is None
    assert driven.notices, "the crash was not reported to the operator"
    assert ESCALATION_ID in driven.log
    assert "MELT_DOWN" in driven.log or "ValueError" in driven.log


async def test_a_press_the_transport_will_not_acknowledge_still_lands(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Telegram refusing the toast is not a reason to drop the decision.

    A callback the Bot API considers too old cannot be answered; the operator's
    press is still a press, and the workflow and the store must both hear it.
    The undeliverable notice goes to the journal instead, so it is still
    readable without a debugger.
    """
    driven = await drive(_branch("telegram_refuses_the_toast"), tmp_path, caplog)

    assert driven.outcome is BridgeOutcome.RESOLVED
    assert [signal.args[1] for signal in driven.signals] == [
        EscalationChoice.RETRY.value
    ]
    assert driven.row is not None
    assert driven.row["resolution"] == EscalationChoice.RETRY.value
    assert ESCALATION_ID in driven.log


# --- US2-S4 (FR-008): the control -------------------------------------------


@pytest.mark.parametrize(
    "branch_name", ["stale_already_resolved", "stale_expired", "stale_race_to_expiry"]
)
async def test_a_stale_press_stays_refused_and_is_told_it_is_stale(
    branch_name: str, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """**The control.** Making every press "land" by deleting the staleness
    guard would let an old message re-answer a live node — worse than a dropped
    press, because the operator never learns the node moved on.

    So: no second signal recorded against the row, the existing resolution
    untouched, and a refusal that says the word.
    """
    branch = _branch(branch_name)
    driven = await drive(branch, tmp_path, caplog)

    assert driven.outcome in (BridgeOutcome.ALREADY_RESOLVED, BridgeOutcome.EXPIRED)
    assert driven.row is not None
    assert driven.row["resolution"] != EscalationChoice.RETRY.value, (
        "a stale press overwrote the decision that was already made"
    )
    assert any("stale" in notice.lower() for notice in driven.notices), (
        f"the operator was refused without being told it was stale: {driven.notices}"
    )
    assert ESCALATION_ID in driven.log


async def test_an_expired_escalation_keeps_its_timeout_resolution(
    bridge: CallbackBridge, client: FakeTemporalClient, store: sqlite3.Connection
) -> None:
    """The staleness guard, asserted on the row rather than on the outcome: the
    hour's decision and the way it was reached both survive the press."""
    insert_escalation(store, make_escalation())
    expire_escalation(store, ESCALATION_ID, resolved_at="2026-08-04T12:00:00Z")

    outcome = await bridge.handle(pressed(EscalationChoice.RETRY))

    assert outcome is BridgeOutcome.EXPIRED
    assert client.signals == []
    row = escalation_row(store, ESCALATION_ID)
    assert row["resolution"] == EXPIRED
    assert row["resolved_at"] == "2026-08-04T12:00:00Z"
    assert row["resolved_via"] == "TIMEOUT"


# --- T019: the second entry point -------------------------------------------


async def test_a_press_arriving_at_the_reply_entry_is_handled_as_a_press(
    bridge: CallbackBridge, client: FakeTemporalClient, store: sqlite3.Connection
) -> None:
    """`TelegramAdapter.relay` reads `callback_query` first, so a press that
    reaches `handle_reply` is a press the question machinery would look up as a
    question, find nothing for, and drop.

    Both inbound entries have to end the same way for the same update, or "which
    handler saw it" becomes part of whether a press lands.
    """
    insert_escalation(store, make_escalation())

    outcome = await bridge.handle_reply(pressed(EscalationChoice.RETRY))

    assert outcome is BridgeOutcome.RESOLVED
    assert [signal.args[1] for signal in client.signals] == [
        EscalationChoice.RETRY.value
    ]
    assert escalation_row(store, ESCALATION_ID)["resolution"] == (
        EscalationChoice.RETRY.value
    )


async def test_an_update_that_is_neither_press_nor_reply_is_recorded(
    bridge: CallbackBridge, caplog: pytest.LogCaptureFixture
) -> None:
    """Nobody to toast at is not a licence for silence (FR-007)."""
    with caplog.at_level(logging.INFO, logger=service.__name__):
        outcome = await bridge.handle(NoCallbackUpdate())

    assert outcome is BridgeOutcome.MALFORMED
    assert BridgeOutcome.MALFORMED.value in "\n".join(
        record.getMessage() for record in caplog.records
    )


def _branch(name: str) -> Branch:
    return next(branch for branch in BRANCHES if branch.name == name)
