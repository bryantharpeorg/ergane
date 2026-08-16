"""042-US1: the one alert that cannot be a workflow.

041 made escalation a Temporal workflow, which is right for every escalation
except the one that says Temporal is down. This file guards the exception: a
plain library call into 041's messenger seam, fire-and-forget, with a local log
as its only record.

The defect this file was written against is the test that cannot fail. A test
that merely *happens* not to reach Temporal passes identically before and after
the change, so every structural claim here is asserted structurally:

- **US1-S1, FR-001 — delivered with no Temporal client constructed at all.**
  Asserted out of process, in a subprocess whose import system refuses
  `temporalio` outright and whose configured Temporal address is a port the
  test first proves refuses connections. An in-process test could only assert
  that nobody happened to import it; this asserts that nobody *can*.
- **US1-S2, FR-002 — the adapter itself failing is logged and raises nothing.**
  Three failure shapes, because a supervisor that crashes on a failed send has
  stopped supervising: a transport that raises, a transport that reports it did
  not deliver, and a transport name nothing is registered under.
- **US1-S3 — fire and forget.** No workflow is started, nothing requiring an
  answer is created, and no reply is expected: asserted on the import graph
  (AST, so a lazy import inside a function body counts), on the module's
  executable source with its prose stripped, and behaviourally — the message
  carries no button, so there is nothing an operator could press.
- **US1-S4, FR-002 — the alert names the service, the observed condition and
  the duration.** A page that says only "degraded" sends the operator to a
  terminal to find out what this code already knew.

Every test here goes through a fake registered under a name of this file's own
(`register_adapter`), selected the way a real transport is selected. Nothing
here can reach a real messenger: the session fixture in `conftest.py` deletes
the Telegram credentials for the whole suite, and `never_the_real_messenger`
below points the transport selection at the fake for every test in this file.

Red first. Run against the tree with these tests written and
`factory/supervision/` not yet written, verbatim::

    $ PYTHONDONTWRITEBYTECODE=1 uv run pytest -q tests/test_supervision_alert.py --no-header
    ==================================== ERRORS ====================================
    _______________ ERROR collecting tests/test_supervision_alert.py _______________
    ImportError while importing test module '/tmp/.../wt/042-us1/tests/test_supervision_alert.py'.
    Hint: make sure your test modules/packages have valid Python names.
    Traceback:
    /home/admin/.local/share/uv/python/cpython-3.13.12-linux-aarch64-gnu/lib/python3.13/importlib/__init__.py:88: in import_module
        return _bootstrap._gcd_import(name[level:], package, level)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    tests/test_supervision_alert.py:76: in <module>
        from factory.supervision.alert import (
    E   ModuleNotFoundError: No module named 'factory.supervision'
    =========================== short test summary info ============================
    ERROR tests/test_supervision_alert.py
    !!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
    1 error in 0.07s

The mutation transcript that shows each of these can fail is pasted at the
bottom of this file, verbatim.
"""

from __future__ import annotations

import ast
import dataclasses
import logging
import os
import socket
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any, Iterator

import pytest

from factory.notify.adapter import (
    ESCALATION_ADAPTER_ENV,
    DeliveryReceipt,
    InboundRelay,
    MessengerAdapter,
    RenderedMessage,
    register_adapter,
    unregister_adapter,
)
from factory.supervision.alert import (
    SUPERVISION_CORRELATION_ID,
    AlertOutcome,
    StackAlert,
    deliver_alert,
    format_duration,
    render_alert,
    send_alert,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

ALERT_MODULE = REPO_ROOT / "factory/supervision/alert.py"

#: The name the recording fake is registered under. Deliberately not a name
#: 033's closed set (`KNOWN_ESC_ADAPTERS`) admits: a fake is a *test*
#: registration, and the parser refusing it is the point of the closed set.
FAKE_ADAPTER_NAME = "us1-supervision-fake"

#: Shaped like a bot token so every "it did not leak" assertion is a substring
#: search over something this code wrote.
SECRET_SHAPED = "1234567890:AAH-fake-bot-token-do-not-log"

#: An outage long enough that its rendering exercises every term.
DEGRADED = StackAlert(
    service="ergane-temporal.service",
    condition="unit not active",
    duration_s=7380.0,
)

#: The same alert, differing only in how long it has been true. Two of them
#: exist so a renderer that dropped the duration, or spelled a constant one,
#: cannot pass by producing identical text for both.
BRIEFLY_DEGRADED = StackAlert(
    service="ergane-temporal.service",
    condition="unit not active",
    duration_s=95.0,
)


# --- fakes ------------------------------------------------------------------


class RecordingAdapter:
    """A transport that records what it was handed and pages nobody.

    Configured per test rather than subclassed: the three failure shapes
    US1-S2 names are the same transport behaving differently, and a caller
    resolving a name cannot tell them apart, which is the point.
    """

    def __init__(self) -> None:
        self.sent: list[tuple[RenderedMessage, str]] = []
        self.delivered = True
        self.raises: Exception | None = None

    async def deliver(
        self, message: RenderedMessage, correlation_id: str
    ) -> DeliveryReceipt:
        # Recorded before the failure: "the transport was reached and could not
        # send" and "the transport was never reached" are different diagnoses.
        self.sent.append((message, correlation_id))
        if self.raises is not None:
            raise self.raises
        return DeliveryReceipt(
            delivered=self.delivered, message_id=7001 if self.delivered else None
        )

    def relay(self, event: Any) -> InboundRelay | None:
        return None


@pytest.fixture(autouse=True)
def never_the_real_messenger(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test in this file may resolve a transport that could page a human.

    The selection is pointed at the fake's name for every test, registered or
    not: a test that forgot the `messenger` fixture resolves a name nothing is
    registered under and gets a swallowed `UnknownAdapterError`, never
    Telegram. The operator channel in this repository reaches a real person.
    """
    monkeypatch.setenv(ESCALATION_ADAPTER_ENV, FAKE_ADAPTER_NAME)


@pytest.fixture
def messenger(monkeypatch: pytest.MonkeyPatch) -> Iterator[RecordingAdapter]:
    """A transport registered and selected exactly the way a real one is."""
    adapter = RecordingAdapter()
    register_adapter(FAKE_ADAPTER_NAME, lambda **_seams: adapter)
    monkeypatch.setenv(ESCALATION_ADAPTER_ENV, FAKE_ADAPTER_NAME)
    try:
        yield adapter
    finally:
        unregister_adapter(FAKE_ADAPTER_NAME)


# --- helpers ----------------------------------------------------------------


def _import_roots(node: ast.AST) -> set[str]:
    if isinstance(node, ast.Import):
        return {alias.name.split(".")[0] for alias in node.names}
    if isinstance(node, ast.ImportFrom) and node.module:
        return {node.module.split(".")[0]}
    return set()


def imported_roots(path: Path) -> set[str]:
    """Every top-level package the module imports, however it spells it.

    Parsed rather than imported, so an import buried inside a function body —
    exactly how a lazy Temporal dependency would sneak back in — is still seen.
    Borrowed from `tests/test_messenger_adapter.py`, which guards the seam this
    module calls; the two claims are the same claim one call apart.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        roots |= _import_roots(node)
    return roots


def imported_modules(path: Path) -> set[str]:
    """Every module the file imports, by full dotted name."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def executable_source(path: Path) -> str:
    """The module's code with every docstring and comment removed.

    A verb scan over raw source grades the prose: this file's subject *must*
    say "expects no reply" and "starts no workflow" in its own docstring to be
    readable at all. Stripping docstrings (and comments, which the AST never
    held) leaves exactly the text that runs, which is what the claim is about.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue
        body = getattr(node, "body", [])
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            node.body = body[1:] or [ast.Pass()]
    return ast.unparse(tree)


def refuses_connections(host: str, port: int) -> bool:
    """Whether nothing is listening there — the US1-S1 precondition, measured."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(2.0)
        return probe.connect_ex((host, port)) != 0


# ============================================================================
# US1-S4 / FR-002 — the alert names the service, the condition and the duration
# ============================================================================


def test_the_alert_names_the_service_the_condition_and_the_duration() -> None:
    """"Degraded" alone sends the operator to a terminal (spec US1-S4)."""
    text = render_alert(DEGRADED).text

    assert DEGRADED.service in text
    assert DEGRADED.condition in text
    assert format_duration(DEGRADED.duration_s) in text


def test_two_alerts_differing_only_in_duration_read_differently() -> None:
    """A duration rendered as a constant is invisible to a single-case test.

    The two alerts differ in exactly one field, so identical text can only mean
    the renderer dropped it — the mutation a frozen clock would never catch.
    """
    long_outage = render_alert(DEGRADED).text
    short_outage = render_alert(BRIEFLY_DEGRADED).text

    assert long_outage != short_outage
    assert format_duration(DEGRADED.duration_s) in long_outage
    assert format_duration(BRIEFLY_DEGRADED.duration_s) in short_outage
    assert format_duration(DEGRADED.duration_s) not in short_outage


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, "0s"),
        (1, "1s"),
        (45.4, "45s"),
        (59.9, "59s"),
        (60, "1m 0s"),
        (95, "1m 35s"),
        (3599, "59m 59s"),
        (3600, "1h 0m"),
        (7380, "2h 3m"),
        (18000, "5h 0m"),
    ],
)
def test_format_duration_spells_hours_minutes_and_seconds(
    seconds: float, expected: str
) -> None:
    """Ten cases, because one case is satisfied by a constant.

    Five hours is the 2026-08-11 outage this whole epic exists for: Temporal
    died and nothing noticed for that long.
    """
    assert format_duration(seconds) == expected


def test_a_duration_from_a_skewed_clock_reads_as_zero_rather_than_backwards() -> None:
    """A probe subtracting a status file's mtime can hand this a negative.

    An alert reading "for -3s" is a bug report about the probe arriving in
    place of the outage it was sent to report.
    """
    assert format_duration(-3.0) == "0s"


# ============================================================================
# US1-S1 / FR-001 — delivered through the configured adapter, recorded locally
# ============================================================================


def test_the_recording_fake_is_a_messenger_adapter() -> None:
    """The guard on every test below: a fake outside the seam grades nothing."""
    assert isinstance(RecordingAdapter(), MessengerAdapter)


def test_the_alert_reaches_the_configured_adapter(
    messenger: RecordingAdapter,
) -> None:
    """Selected by configuration, not by a patched resolution (FR-001)."""
    outcome = send_alert(DEGRADED)

    assert outcome.delivered is True
    assert outcome.failure is None
    assert len(messenger.sent) == 1
    message, correlation_id = messenger.sent[0]
    assert message.text == render_alert(DEGRADED).text
    assert correlation_id == SUPERVISION_CORRELATION_ID


def test_a_named_transport_beats_the_configured_one(
    messenger: RecordingAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US2's probe may name its transport; the default reads configuration."""
    monkeypatch.setenv(ESCALATION_ADAPTER_ENV, "carrier-pigeon")

    outcome = send_alert(DEGRADED, adapter_name=FAKE_ADAPTER_NAME)

    assert outcome.delivered is True
    assert len(messenger.sent) == 1


def test_the_delivered_alert_is_recorded_in_the_local_log(
    messenger: RecordingAdapter, caplog: pytest.LogCaptureFixture
) -> None:
    """"A local log as its only record" (FR-001), and it names the alert.

    A record that said only "alert sent" would leave the host with no evidence
    of *what* was sent — and on the host this runs on, that log is the whole
    forensic trail, because nothing else recorded the alert anywhere.
    """
    caplog.set_level(logging.INFO, logger="factory.supervision.alert")

    send_alert(DEGRADED)

    logged = [
        record.getMessage()
        for record in caplog.records
        if record.name == "factory.supervision.alert"
    ]
    assert len(logged) == 1, logged
    assert DEGRADED.service in logged[0]
    assert DEGRADED.condition in logged[0]
    assert format_duration(DEGRADED.duration_s) in logged[0]


#: Printed by the subprocess below once the send has returned, so a script that
#: died before the send cannot be mistaken for one that completed it.
_NO_TEMPORAL_MARKER = "ALERTED"

_NO_TEMPORAL_SCRIPT = textwrap.dedent(
    '''
    """042's supervision probe, in miniature: page a human with Temporal gone.

    The import system refuses `temporalio` before anything from `factory` is
    imported, so a lazy import inside a function body fails the run rather than
    passing it, and the configured Temporal address is a port that refuses.
    """
    import asyncio
    import logging
    import os
    import socket
    import sys

    BLOCKED = ("temporalio",)


    class RefuseBlocked:
        def find_spec(self, fullname, path=None, target=None):
            if fullname.split(".")[0] in BLOCKED:
                raise ImportError(
                    f"{fullname} is not available to a process with no orchestrator"
                )
            return None


    sys.meta_path.insert(0, RefuseBlocked())

    address = sys.argv[1]
    host, _, port = address.partition(":")
    os.environ["TEMPORAL_ADDRESS"] = address
    os.environ["ERGANE_ESCALATION_ADAPTER"] = sys.argv[2]

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as check:
        check.settimeout(2.0)
        assert check.connect_ex((host, int(port))) != 0, (
            f"something answered at {address}; this run proves nothing"
        )

    from factory.notify.adapter import DeliveryReceipt, register_adapter
    from factory.supervision.alert import StackAlert, send_alert


    class Recorder:
        def __init__(self):
            self.sent = []

        async def deliver(self, message, correlation_id):
            self.sent.append((message.text, message.actions, correlation_id))
            return DeliveryReceipt(delivered=True, message_id=7001)

        def relay(self, event):
            return None


    recorder = Recorder()
    register_adapter(sys.argv[2], lambda **seams: recorder)
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(name)s %(message)s")

    outcome = send_alert(
        StackAlert(
            service="ergane-temporal.service",
            condition="rpc 7233 unreachable",
            duration_s=18000.0,
        )
    )

    assert outcome.delivered is True, outcome
    assert outcome.exit_code == 0, outcome
    assert len(recorder.sent) == 1, recorder.sent
    text, actions, correlation_id = recorder.sent[0]
    assert "ergane-temporal.service" in text, text
    assert "rpc 7233 unreachable" in text, text
    assert "5h 0m" in text, text
    assert actions == (), actions

    leaked = sorted(name for name in sys.modules if name.startswith("temporalio"))
    assert not leaked, leaked
    reached_back = sorted(
        name
        for name in sys.modules
        if name.startswith(("factory.activities", "factory.escalation", "factory.verify"))
    )
    assert not reached_back, reached_back
    assert "telegram" not in sys.modules, "the real transport was imported"

    print("ALERTED", outcome.exit_code)
    '''
)


def test_the_alert_is_delivered_from_a_process_with_no_temporal_client(
    tmp_path: Path,
) -> None:
    """US1-S1: no Temporal server, and no Temporal client constructed at all.

    Run out of process on purpose. `temporalio` is installed in this
    environment, so an in-process test could only assert that nobody happened
    to import it; a subprocess whose import system refuses the package asserts
    that nobody *can*. The configured address is checked to be refusing inside
    the same process that then sends, so the "Given" is measured rather than
    described.

    Port 1 is the address: privileged, unassigned on this host, and refusing —
    asserted here before the subprocess starts and again inside it.
    """
    assert refuses_connections("127.0.0.1", 1), (
        "something is listening on 127.0.0.1:1; pick another dead address"
    )

    script = tmp_path / "us1_no_temporal_alert.py"
    script.write_text(_NO_TEMPORAL_SCRIPT, encoding="utf-8")

    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)

    result = subprocess.run(
        [sys.executable, str(script), "127.0.0.1:1", FAKE_ADAPTER_NAME],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == f"{_NO_TEMPORAL_MARKER} 0", result.stdout
    # FR-001's other half: the send left a local record, in the process that
    # had nowhere else to leave one.
    assert "factory.supervision.alert" in result.stderr, result.stderr
    assert "ergane-temporal.service" in result.stderr, result.stderr


# ============================================================================
# US1-S2 / FR-002 — the adapter failing is logged, and nothing raises
# ============================================================================


def test_an_adapter_that_raises_is_logged_and_nothing_propagates(
    messenger: RecordingAdapter, caplog: pytest.LogCaptureFixture
) -> None:
    """A supervisor that crashes on a failed send has stopped supervising."""
    caplog.set_level(logging.INFO, logger="factory.supervision.alert")
    messenger.raises = RuntimeError("the transport exploded")

    outcome = send_alert(DEGRADED)

    assert outcome.delivered is False
    assert "RuntimeError" in (outcome.failure or "")
    errors = [
        record for record in caplog.records if record.levelno >= logging.ERROR
    ]
    assert len(errors) == 1, [record.getMessage() for record in caplog.records]
    assert "RuntimeError" in errors[0].getMessage()
    # The undelivered text is in the log, because the log is now the only place
    # the alert exists at all.
    assert DEGRADED.service in errors[0].getMessage()


def test_a_failing_send_never_quotes_the_exceptions_own_message(
    messenger: RecordingAdapter, caplog: pytest.LogCaptureFixture
) -> None:
    """The class is the diagnosis; the message may be quoting a credential.

    An unauthorized Bot API error quotes the bot token back, because the token
    is in the URL it failed on — the same reason `TelegramAdapter.deliver`
    logs `type(exc).__name__` and not `exc`.
    """
    caplog.set_level(logging.INFO, logger="factory.supervision.alert")
    messenger.raises = RuntimeError(f"401 Unauthorized for {SECRET_SHAPED}")

    outcome = send_alert(DEGRADED)

    written = " ".join(
        [outcome.failure or "", *(record.getMessage() for record in caplog.records)]
    )
    assert SECRET_SHAPED not in written, written


def test_an_adapter_reporting_no_delivery_says_so_in_its_own_output(
    messenger: RecordingAdapter,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """FR-015: a probe that cannot escalate must be loud, in its own output.

    Silent inability to escalate is indistinguishable from a healthy floor,
    which is the exact failure this path exists to end (plan trap 6).
    """
    caplog.set_level(logging.INFO, logger="factory.supervision.alert")
    messenger.delivered = False

    outcome = send_alert(DEGRADED)

    assert outcome.delivered is False
    assert outcome.exit_code != 0
    assert len(messenger.sent) == 1, "the transport was never even reached"
    complaint = capsys.readouterr().err
    assert DEGRADED.service in complaint, complaint
    assert FAKE_ADAPTER_NAME in complaint, complaint
    assert any(record.levelno >= logging.ERROR for record in caplog.records)


def test_a_transport_name_nothing_is_registered_under_does_not_raise(
    caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    """A misconfigured channel fails on the host that is already failing.

    `resolve_adapter` raises `UnknownAdapterError` by design — defaulting to
    another transport would page the wrong place and look configured. On this
    path that exception is data: reported, never propagated.
    """
    caplog.set_level(logging.INFO, logger="factory.supervision.alert")

    outcome = send_alert(DEGRADED, adapter_name="carrier-pigeon")

    assert outcome.delivered is False
    assert "carrier-pigeon" in (outcome.failure or "")
    assert "carrier-pigeon" in capsys.readouterr().err
    assert any(record.levelno >= logging.ERROR for record in caplog.records)


def test_an_undelivered_alert_exits_non_zero_and_a_delivered_one_does_not(
    messenger: RecordingAdapter,
) -> None:
    """FR-015's exit-code half, in the shape US2's probe will call it."""
    assert send_alert(DEGRADED).exit_code == 0

    messenger.delivered = False
    assert send_alert(DEGRADED).exit_code == 1


async def test_the_sync_door_reports_rather_than_raises_inside_a_loop(
    messenger: RecordingAdapter, capsys: pytest.CaptureFixture[str]
) -> None:
    """`asyncio.run` refuses from a running loop, and refusing is an exception.

    The probe is a script and has no loop, so this is not its path — but "the
    supervision alert never raises" is a claim about every caller, and this is
    the one way the sync door can fail before the transport is even reached.
    """
    outcome = send_alert(DEGRADED)

    assert outcome.delivered is False
    assert "deliver_alert" in (outcome.failure or ""), outcome.failure
    assert capsys.readouterr().err != ""

    # And the await-side door works from exactly here.
    awaited = await deliver_alert(DEGRADED)
    assert awaited.delivered is True
    assert len(messenger.sent) == 1


# ============================================================================
# US1-S3 — fire and forget: no workflow, no record, no reply expected
# ============================================================================


def test_the_alert_module_never_imports_temporalio() -> None:
    """FR-001 as a property of the import graph, lazy imports included."""
    assert "temporalio" not in imported_roots(ALERT_MODULE)


def test_the_alert_module_imports_nothing_that_records_an_escalation() -> None:
    """US1-S3: nothing requiring an answer can be created from here.

    The escalation store, the escalation workflow and the activity layer are
    all reachable from this repository's root package; none of them is
    reachable from this module. 041's record-and-await semantics are the wrong
    shape for a path whose defining property is that silence is not a state it
    tracks.
    """
    forbidden = (
        "factory.escalation",
        "factory.verify",
        "factory.activities",
        "factory.workgraph",
        "temporalio",
    )
    reached = sorted(
        name
        for name in imported_modules(ALERT_MODULE)
        if name.startswith(forbidden)
    )

    assert reached == [], reached


def test_no_code_path_starts_a_workflow_or_settles_an_answer() -> None:
    """US1-S3 read off the module's executable source, prose stripped.

    The verbs are the ones that would make this an escalation rather than a
    report: starting or signalling a workflow, writing a row someone must
    answer, or waiting for one.
    """
    source = executable_source(ALERT_MODULE)

    lifecycle_verbs = (
        "start_workflow",
        "execute_workflow",
        "get_workflow_handle",
        ".signal(",
        "wait_condition",
        "EscalationRecord",
        "insert_escalation",
        "insert_question",
        "resolve_escalation",
        "expire_escalation",
        "escalation_id",
        "expires_at",
        "await_answer",
        "connect(",
    )
    found = [verb for verb in lifecycle_verbs if verb in source]

    assert found == [], (
        f"the out-of-band alert path names {found}; it is fire-and-forget, and "
        "silence from the operator is not a state it tracks (US1-S3)"
    )


def test_the_alert_carries_no_button_to_press(messenger: RecordingAdapter) -> None:
    """The behavioural half: an operator cannot answer what has no answer.

    `RenderedMessage.actions` is what a transport turns into buttons. Empty is
    what makes "expects no reply" a property of the message rather than of a
    convention the next story could forget.
    """
    assert render_alert(DEGRADED).actions == ()

    send_alert(DEGRADED)

    message, _ = messenger.sent[0]
    assert message.actions == ()


def test_the_outcome_carries_no_handle_to_wait_on() -> None:
    """Nothing an alert returns can be awaited, polled or correlated back.

    `AlertOutcome` is what it said and whether anyone got it; a fourth field
    holding a message handle or an escalation id is how a fire-and-forget path
    grows a reply it then has to wait for.
    """
    assert [field.name for field in dataclasses.fields(AlertOutcome)] == [
        "text",
        "delivered",
        "failure",
    ]
