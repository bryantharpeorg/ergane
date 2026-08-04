"""The three guarantees no single module of this component can prove alone.

Every other test file here asks whether one module does its job. This one asks
whether verification, taken whole, still has the three properties tasks.md picked
as the ones an operator has to be able to trust blind — the ones whose failure
mode is silence:

- **Two credentials exist in the worker environment and nowhere else.**
  `LITELLM_MASTER_KEY` (001's, still sitting in the same process the judge runs
  in) and `TELEGRAM_BOT_TOKEN` (this component's) are both set, to canaries
  unlike anything else in this repository, for the whole of a real verification
  and a real escalation. Then every way either could have escaped is searched:
  each byte the run persisted, every log line it emitted, and the whole raised
  chain of every failure path the component can take. A gate subprocess is
  covered by construction — the `env-probe` fixture's gate dumps its own
  environment, so a scrubbing regression does not merely fail an assertion about
  a subprocess: it writes the master key into an `output_tail`, into the evidence
  store, and into the escalation message an operator is paged with.

- **FR-009: the judge is unreachable from anything but `run_judge`.** "Never a
  CI check" is an absence, and absence is not provable by running things. So it
  is checked structurally: exactly one module imports the judge library, every
  call into it sits inside the one `@activity.defn` that wraps it, and the
  surfaces a CI or merge system could actually pull on — the package's console
  scripts, its `__main__` blocks, and the gate names a target repo's
  `factory.yaml` is allowed to declare — have no spelling that reaches it. The
  last of those is the real fence: `KNOWN_GATES` is a closed set of three
  deterministic commands, so a repo cannot declare a `judge` gate even on
  purpose.

- **SC-002: no path to PASS with a failing gate or an empty write-scope diff.**
  Exhaustively, over the whole product of gate statuses, write scopes, artifact
  states and judge outcomes, rather than over a table of rows someone chose — a
  truth table is only as good as the row nobody thought to add. Then the same
  claim structurally (`compose_result` is the only thing in the component that
  decides a verdict) and behaviourally (a real repo whose test gate exits 3, with
  a judge scripted to call the work perfect, records FAIL and never spends a
  completion).

Written last (T035), against the finished component: unlike most test files here,
this one is expected to pass on arrival. A failure means something that was true
when it was written has since stopped being true.
"""

from __future__ import annotations

import ast
import logging
import re
import tomllib
import traceback
from contextlib import closing
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterator

import pytest
from temporalio.testing import ActivityEnvironment

from factory.activities import notify_activities, verify_activities
from factory.activities.notify_activities import (
    TELEGRAM_BOT_TOKEN_ENV,
    TELEGRAM_CHAT_ID_ENV,
    ExpireEscalationInput,
    SendEscalationInput,
    expire_escalation,
    send_escalation,
)
from factory.activities.verify_activities import (
    VERIFICATION_DB_PATH_ENV,
    CheckOutputInput,
    RecordVerificationInput,
    RunGatesInput,
    RunJudgeInput,
    SnapshotCriteriaInput,
    check_output,
    record_verification,
    run_gates,
    run_judge,
    snapshot_criteria,
)
from factory.config import WriteScope
from factory.notify import messages, service
from factory.notify.service import CallbackBridge
from factory.verify import diffcheck, factory_yaml, gates, store
from factory.verify.factory_yaml import KNOWN_GATES
from factory.verify.models import (
    CriteriaSet,
    GateResult,
    GateStatus,
    JudgeOutcome,
    JudgeScenarioFinding,
    JudgeVerdict,
    OutputCheck,
    OverallVerdict,
    Requirement,
    RequirementKind,
    Scenario,
    VerificationForm,
    compose_result,
    judge_required,
)
from tests.judge_proxy import (
    JUDGE_MODEL_ALIAS,
    JUDGE_PROXY_URL,
    JUDGE_VIRTUAL_KEY,
    FakeJudgeProxy,
    verdict_json,
)

#: The proxy credential the worker host holds — component 1's, still in the
#: environment while this component's judge authenticates with a per-attempt
#: virtual key beside it. No substring of it occurs anywhere else in this
#: repository, so "this string appears here" is never a coincidence.
MASTER_KEY = "sk-canary-8d3f21b7e0c94a56-litellm-master"

#: The bot credential this component adds. Shaped like a real Bot API token —
#: `<bot-id>:<secret>` — because that shape is what ends up inside the URL a
#: failing `telegram` call quotes back in its own error message.
BOT_TOKEN = "8102938475:CANARYb19f4ad7c3e05286af1d9be74c0a3f5e"

#: Where an escalation would go. Not a credential, but worker configuration all
#: the same, and it travels the same paths.
CHAT_ID = "-1009876543210"

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPONENT_ROOT = REPO_ROOT / "factory"
TESTS_ROOT = Path(__file__).resolve().parent
CORPUS = TESTS_ROOT / "fixtures" / "speckit"

#: The modules this component ships (plan.md § Source Code). Component 1's
#: `factory/usage/` has its own sweep in `tests/test_final_sweep.py`.
COMPONENT_MODULES = sorted(
    [
        *(COMPONENT_ROOT / "verify").rglob("*.py"),
        *(COMPONENT_ROOT / "notify").rglob("*.py"),
        COMPONENT_ROOT / "activities" / "verify_activities.py",
        COMPONENT_ROOT / "activities" / "notify_activities.py",
    ]
)

#: The one module allowed to call it. Everything else in the component reaches
#: verification through the activity, which is what makes "the judge runs in the
#: inner loop only" a property of the import graph (FR-009).
JUDGE_CALLER = COMPONENT_ROOT / "activities" / "verify_activities.py"

#: The two modules that read the bot token, and the only two (contracts/
#: activities.md: env only, inside the activity or the bridge process).
TOKEN_READERS = frozenset(
    {
        COMPONENT_ROOT / "activities" / "notify_activities.py",
        COMPONENT_ROOT / "notify" / "service.py",
    }
)

EPIC = "epic-sweep"
NODE = "node-verify"
ATTEMPT = 1
WORKFLOW_ID = "epic-sweep-interpreter"
SPEC_REF = "002-verification-gating/US2"
STARTED_AT = "2026-08-04T11:00:00Z"
FINISHED_AT = "2026-08-04T11:04:12Z"
CRITERIA_SHA = "5ca1ab1e" + "0" * 56

#: A tracked file in the fixture repo — editing it is how a node proves it worked.
TRACKED_FILE = "src/calc.py"


def module_id(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


# --- the criteria one node is dispatched against ----------------------------

SCENARIO = Scenario(
    scenario_id="US2-S2",
    steps=[
        "**Given** any deterministic gate fails",
        "**When** verification concludes",
        "**Then** the verdict is FAIL and the judge is not consulted",
    ],
    raw_text=(
        "2. **Given** any deterministic gate fails, **When** verification "
        "concludes, **Then** the verdict is FAIL, the judge is not consulted "
        "(cheapest-first), and gate output is preserved for the retry prompt."
    ),
)

CRITERIA = CriteriaSet(
    feature="002-verification-gating",
    spec_ref=SPEC_REF,
    requirements=[
        Requirement(
            key="US2",
            kind=RequirementKind.STORY,
            title="Two-tier verification of a node's diff",
            priority="P1",
            body="Deterministic gates first, a bounded judge second.",
            scenarios=[SCENARIO],
        )
    ],
    source_path="specs/002-verification-gating/spec.md",
    source_sha256=CRITERIA_SHA,
    snapshotted_at=STARTED_AT,
)


# --- fakes ------------------------------------------------------------------


class FakeBot:
    """Stand-in for `telegram.Bot` — records sends, never opens a socket."""

    def __init__(self) -> None:
        self.opened_with: list[str] = []
        self.sent: list[dict[str, Any]] = []
        self.fail_send: BaseException | None = None

    async def __aenter__(self) -> FakeBot:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def send_message(
        self,
        chat_id: Any = None,
        text: str = "",
        *,
        reply_markup: Any = None,
        **kwargs: Any,
    ) -> object:
        if self.fail_send is not None:
            raise self.fail_send
        self.sent.append({"chat_id": chat_id, "text": text, "markup": reply_markup})
        return object()


class FakeQuery:
    """The callback half of a Telegram update, recording what it was answered."""

    def __init__(self, data: str | None) -> None:
        self.data = data
        self.answers: list[str] = []
        self.edits: list[str] = []

    async def answer(self, text: str | None = None, **kwargs: Any) -> None:
        self.answers.append(text or "")

    async def edit_message_text(self, text: str, **kwargs: Any) -> None:
        self.edits.append(text)


class FakeUpdate:
    def __init__(self, data: str | None) -> None:
        self.callback_query = FakeQuery(data)


class UnreachableTemporal:
    """A Temporal client that is down — the bridge's signal-path failure."""

    def get_workflow_handle(self, workflow_id: str) -> Any:
        raise ConnectionRefusedError(f"no Temporal at localhost:7233 ({workflow_id})")


# --- the world one verification runs in -------------------------------------


@dataclass
class Component:
    """A worker host: both credentials in the environment, a scratch evidence
    store, real node worktrees, a scripted proxy and a bot that never dials."""

    env: ActivityEnvironment
    proxy: FakeJudgeProxy
    bot: FakeBot
    workspace: Path
    db_path: Path
    worktree: Callable[..., Path]

    async def run(self, fn: Any, request: Any) -> Any:
        return await self.env.run(fn, request)

    def touched_worktree(self, variant: str = "passing") -> Path:
        """A worktree a node has actually worked in — the ordinary case."""
        tree = self.worktree(variant)
        (tree / TRACKED_FILE).write_text(
            '"""The whole of the fixture repo\'s production code."""\n\n\n'
            "def add(left: int, right: int) -> int:\n"
            "    return left + right\n\n\n"
            "def subtract(left: int, right: int) -> int:\n"
            "    return left - right\n",
            encoding="utf-8",
        )
        return tree


@pytest.fixture
def component(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    node_worktree: Callable[..., Path],
) -> Component:
    """One worker host, credentials where FR-009 puts them: the environment.

    Both are set for every test in this file, including the ones that never go
    near a proxy or a bot. That is the point — a credential leaks through
    whichever path nobody was thinking about at the time, so it has to be
    available to leak on all of them.
    """
    proxy = FakeJudgeProxy()
    bot = FakeBot()
    db_path = tmp_path / ".factory" / "verification.db"

    monkeypatch.setenv("LITELLM_MASTER_KEY", MASTER_KEY)
    monkeypatch.setenv("LITELLM_PROXY_URL", proxy.base_url)
    monkeypatch.setenv(TELEGRAM_BOT_TOKEN_ENV, BOT_TOKEN)
    monkeypatch.setenv(TELEGRAM_CHAT_ID_ENV, CHAT_ID)
    monkeypatch.setenv(VERIFICATION_DB_PATH_ENV, str(db_path))

    monkeypatch.setattr(verify_activities, "judge_transport", lambda: proxy.transport)
    monkeypatch.setattr(verify_activities, "JUDGE_RETRY_BACKOFF_S", 0.0)

    def open_bot(token: str) -> FakeBot:
        bot.opened_with.append(token)
        return bot

    monkeypatch.setattr(notify_activities, "open_bot", open_bot)

    return Component(
        env=ActivityEnvironment(),
        proxy=proxy,
        bot=bot,
        workspace=tmp_path,
        db_path=db_path,
        worktree=node_worktree,
    )


# --- helpers ----------------------------------------------------------------


def judge_input(**overrides: Any) -> RunJudgeInput:
    fields: dict[str, Any] = {
        "criteria": CRITERIA,
        "diff_text": "diff --git a/src/calc.py b/src/calc.py\n+    return left - right\n",
        "virtual_key": JUDGE_VIRTUAL_KEY,
        "proxy_url": JUDGE_PROXY_URL,
        "model_alias": JUDGE_MODEL_ALIAS,
    }
    fields.update(overrides)
    return RunJudgeInput(**fields)


def passing_verdict() -> str:
    """A judge that calls the work perfect — the reply that makes SC-002 bite."""
    return verdict_json(
        scenarios={SCENARIO.scenario_id: True}, feedback="every step is satisfied"
    )


def send_request(**overrides: Any) -> SendEscalationInput:
    fields: dict[str, Any] = {
        "workflow_id": WORKFLOW_ID,
        "epic_id": EPIC,
        "node_id": NODE,
        "history_summary": "Attempt 1 — FAIL\n  gate test: FAIL (exit 3, 0.2s)",
    }
    fields.update(overrides)
    return SendEscalationInput(**fields)


def composed(**overrides: Any) -> Any:
    """One attempt's evidence, composed — override only what a test is about."""
    fields: dict[str, Any] = {
        "epic_id": EPIC,
        "node_id": NODE,
        "attempt": ATTEMPT,
        "form": VerificationForm.PHASE,
        "gate_results": [passing_gate()],
        "output_check": proved_output(),
        "judge": None,
        "criteria_sha256": CRITERIA_SHA,
        "spec_ref": SPEC_REF,
        "started_at": STARTED_AT,
        "finished_at": FINISHED_AT,
    }
    fields.update(overrides)
    return compose_result(**fields)


def parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def enclosing_functions(tree: ast.Module) -> dict[int, Any]:
    """Map every AST node to the innermost function it sits inside."""
    owner: dict[int, Any] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(node):
                owner.setdefault(id(child), node)
    return owner


def owner_name(owner: dict[int, Any], node: ast.AST) -> str:
    enclosing = owner.get(id(node))
    return enclosing.name if enclosing else "<module>"


# ============================================================================
# 1. The two credentials
# ============================================================================


async def test_no_byte_this_component_persists_carries_either_credential(
    component: Component,
) -> None:
    """One whole verification and one whole escalation, then sweep the disk.

    The gate is the `env-probe` variant, which dumps its own exported environment
    into its output. That output becomes a `GateResult.output_tail`, which is
    written to the evidence store, quoted into the escalation history and sent to
    the operator — so a scrubbing regression is not a subtle failure here. It is
    the master key, in a database file and in a Telegram message.
    """
    worktree = component.touched_worktree("env-probe")

    gate_results = await component.run(
        run_gates, RunGatesInput(worktree_path=str(worktree))
    )
    assert [gate.status for gate in gate_results] == [GateStatus.PASS]
    assert "--- exported environment ---" in gate_results[0].output_tail, (
        "the env-probe gate did not report its environment; this sweep proved nothing"
    )

    output = await component.run(
        check_output,
        CheckOutputInput(
            worktree_path=str(worktree), write_scope=WriteScope.WORKTREE.value
        ),
    )
    assert output.passed is True

    component.proxy.reply(passing_verdict())
    verdict = await component.run(run_judge, judge_input())
    assert verdict.outcome is JudgeOutcome.PASS

    passed = composed(gate_results=list(gate_results), output_check=output, judge=verdict)
    assert passed.verdict is OverallVerdict.PASS
    await component.run(record_verification, RecordVerificationInput(result=passed))

    # A second attempt whose gate failed, so the same environment dump is quoted
    # into the operator's message: `render_history` only reproduces the output of
    # gates that did not pass, and that is the path the token would ride out on.
    failed = composed(
        attempt=ATTEMPT + 1,
        gate_results=[replace(gate_results[0], status=GateStatus.FAIL, exit_code=1)],
        output_check=output,
    )
    assert failed.verdict is OverallVerdict.FAIL
    await component.run(record_verification, RecordVerificationInput(result=failed))

    with closing(store.connect(component.db_path)) as conn:
        history = messages.render_history(store.node_history(conn, EPIC, NODE))
    assert "--- exported environment ---" in history, (
        "the failing gate's output was not quoted into the history (SC-005)"
    )

    sent = await component.run(send_escalation, send_request(history_summary=history))
    assert sent.delivered is True
    await component.run(expire_escalation, ExpireEscalationInput(sent.escalation_id))

    written = [path for path in sorted(component.workspace.rglob("*")) if path.is_file()]
    assert component.db_path in written, "the run persisted no evidence store to sweep"

    for path in written:
        blob = path.read_bytes()
        for secret, name in ((MASTER_KEY, "master key"), (BOT_TOKEN, "bot token")):
            assert secret.encode() not in blob, (
                f"{name} found in {path.relative_to(component.workspace)}"
            )

    # The message an operator actually received, and the payload behind every
    # button on it: the last places the evidence passes through before Telegram.
    assert component.bot.sent, "nothing was ever sent; the message sweep proved nothing"
    for message in component.bot.sent:
        rendered = f"{message['text']}{message['markup']}"
        assert MASTER_KEY not in rendered and BOT_TOKEN not in rendered

    # The judge authenticates with the per-attempt virtual key, which is allowed
    # to travel; the master key sitting beside it in the environment is not.
    transcript = component.proxy.transcript()
    assert f"Bearer {JUDGE_VIRTUAL_KEY}" in transcript
    assert MASTER_KEY not in transcript and BOT_TOKEN not in transcript


# --- every way this component fails -----------------------------------------


async def a_spec_that_is_not_there(component: Component) -> object:
    return await component.run(
        snapshot_criteria,
        SnapshotCriteriaInput(
            specs_root=str(CORPUS), feature="999-no-such-feature", spec_ref=SPEC_REF
        ),
    )


async def a_spec_the_grammar_refuses(component: Component) -> object:
    return await component.run(
        snapshot_criteria,
        SnapshotCriteriaInput(
            specs_root=str(CORPUS), feature="014-fr-missing-modal", spec_ref=SPEC_REF
        ),
    )


async def a_worktree_that_vanished(component: Component) -> object:
    return await component.run(
        check_output,
        CheckOutputInput(
            worktree_path=str(component.workspace / "gone"),
            write_scope=WriteScope.WORKTREE.value,
        ),
    )


async def a_manifest_the_schema_refuses(component: Component) -> object:
    return factory_yaml.load_factory_config(
        component.worktree("unknown-gate") / "factory.yaml"
    )


async def a_repo_with_no_manifest(component: Component) -> object:
    repo = component.worktree("missing-manifest")
    return await component.run(run_gates, RunGatesInput(worktree_path=str(repo)))


async def a_gate_that_exits_nonzero(component: Component) -> object:
    repo = component.worktree("failing-gate")
    return await component.run(run_gates, RunGatesInput(worktree_path=str(repo)))


async def a_gate_that_prints_the_worker_environment(component: Component) -> object:
    repo = component.worktree("env-probe")
    return await component.run(run_gates, RunGatesInput(worktree_path=str(repo)))


async def a_proxy_that_stays_down(component: Component) -> object:
    component.proxy.fail_always(503)
    return await component.run(run_judge, judge_input())


async def a_proxy_that_refuses_the_virtual_key(component: Component) -> object:
    return await component.run(run_judge, judge_input(virtual_key="sk-wrong-key"))


async def a_proxy_breaking_its_own_protocol(component: Component) -> object:
    component.proxy.reply_payload({"not": "a completion"})
    return await component.run(run_judge, judge_input())


async def a_judge_talking_nonsense(component: Component) -> object:
    component.proxy.reply("I think it looks fine to me.")
    return await component.run(run_judge, judge_input())


async def a_result_that_cannot_be_attributed(component: Component) -> object:
    return await component.run(
        record_verification, RecordVerificationInput(result=composed(epic_id=""))
    )


async def an_escalation_the_store_refuses(
    component: Component, monkeypatch: pytest.MonkeyPatch
) -> object:
    obstruction = component.workspace / "not-a-directory"
    obstruction.write_text("", encoding="utf-8")
    monkeypatch.setenv(VERIFICATION_DB_PATH_ENV, str(obstruction / "verification.db"))
    return await component.run(send_escalation, send_request())


async def a_bot_that_quotes_its_own_token_back(component: Component) -> object:
    # What `telegram` actually raises on a rejected token: the request URL is
    # `https://api.telegram.org/bot<token>/sendMessage`, so the token is *inside*
    # the error message. Logging `exc` rather than `type(exc).__name__` in
    # `notify_activities._send` would publish it.
    component.bot.fail_send = RuntimeError(
        f"Unauthorized: POST https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    )
    return await component.run(send_escalation, send_request())


async def a_worker_with_no_bot_token(
    component: Component, monkeypatch: pytest.MonkeyPatch
) -> object:
    monkeypatch.delenv(TELEGRAM_BOT_TOKEN_ENV)
    return await component.run(send_escalation, send_request())


async def a_bridge_that_cannot_reach_temporal(component: Component) -> object:
    sent = await component.run(send_escalation, send_request())
    bridge = CallbackBridge(db_path=component.db_path, client=UnreachableTemporal())
    update = FakeUpdate(messages.callback_data(sent.escalation_id, "RETRY"))
    return (await bridge.handle(update), update.callback_query.answers)


async def a_button_press_on_an_unknown_escalation(component: Component) -> object:
    bridge = CallbackBridge(db_path=component.db_path, client=UnreachableTemporal())
    update = FakeUpdate("esc:0123456789ab:RETRY")
    return (await bridge.handle(update), update.callback_query.answers)


async def an_escalation_id_that_is_not_hex(component: Component) -> object:
    return messages.callback_data("not-an-id", "RETRY")


async def a_store_that_cannot_be_opened(component: Component) -> object:
    obstruction = component.workspace / "blocked"
    obstruction.write_text("", encoding="utf-8")
    return store.connect(obstruction / "verification.db")


async def an_expiry_against_an_unreadable_store(
    component: Component, monkeypatch: pytest.MonkeyPatch
) -> object:
    obstruction = component.workspace / "also-not-a-directory"
    obstruction.write_text("", encoding="utf-8")
    monkeypatch.setenv(VERIFICATION_DB_PATH_ENV, str(obstruction / "verification.db"))
    return await component.run(expire_escalation, ExpireEscalationInput("0123456789ab"))


#: Every way this component can fail or refuse. Some raise and some report — a
#: gate that failed is data, a worktree that vanished is an error — and the sweep
#: does not care which: it searches the exception chain, the returned value and
#: the log lines alike, because all three reach a human. A path added to the
#: component without a line here is a path whose output nobody has read.
FAILURE_PATHS: list[Callable[..., Awaitable[object]]] = [
    a_spec_that_is_not_there,
    a_spec_the_grammar_refuses,
    a_worktree_that_vanished,
    a_manifest_the_schema_refuses,
    a_repo_with_no_manifest,
    a_gate_that_exits_nonzero,
    a_gate_that_prints_the_worker_environment,
    a_proxy_that_stays_down,
    a_proxy_that_refuses_the_virtual_key,
    a_proxy_breaking_its_own_protocol,
    a_judge_talking_nonsense,
    a_result_that_cannot_be_attributed,
    an_escalation_the_store_refuses,
    a_bot_that_quotes_its_own_token_back,
    a_worker_with_no_bot_token,
    a_bridge_that_cannot_reach_temporal,
    a_button_press_on_an_unknown_escalation,
    an_escalation_id_that_is_not_hex,
    a_store_that_cannot_be_opened,
    an_expiry_against_an_unreadable_store,
]


def renderings_of(error: BaseException) -> Iterator[str]:
    """Every way this failure could reach a human: the formatted traceback of the
    whole chain, plus each link's own message, args and repr."""
    yield "".join(traceback.format_exception(type(error), error, error.__traceback__))

    seen: BaseException | None = error
    depth = 0
    while seen is not None and depth < 10:
        yield str(seen)
        yield repr(seen)
        yield str(seen.args)
        seen = seen.__cause__ or seen.__context__
        depth += 1


def wants_monkeypatch(fn: Callable[..., Any]) -> bool:
    code = fn.__code__
    return "monkeypatch" in code.co_varnames[: code.co_argcount]


@pytest.mark.parametrize("failure", FAILURE_PATHS, ids=lambda fn: fn.__name__)
async def test_no_failure_path_renders_either_credential(
    failure: Callable[..., Awaitable[object]],
    component: Component,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    observed: list[str] = []

    with caplog.at_level(logging.DEBUG):
        try:
            value = (
                await failure(component, monkeypatch)
                if wants_monkeypatch(failure)
                else await failure(component)
            )
        except BaseException as exc:  # noqa: BLE001 — the sweep reads whatever fell out
            observed.extend(renderings_of(exc))
        else:
            observed.append(repr(value))

    # An error path and a log line are the two places a credential travels by
    # accident: both are built from whatever was in hand, and both are read by
    # someone who is not thinking about secrets at the time (FR-009, SC-004).
    observed.append(caplog.text)
    observed.extend(repr(record.args) for record in caplog.records)
    assert any(observed), f"{failure.__name__} produced nothing to sweep"

    for rendering in observed:
        for secret, name in ((MASTER_KEY, "master key"), (BOT_TOKEN, "bot token")):
            assert secret not in rendering, f"{failure.__name__} leaked the {name}"


async def test_a_notifier_failure_that_quotes_the_token_still_leaves_a_row(
    component: Component, caplog: pytest.LogCaptureFixture
) -> None:
    """The token-in-the-error path, asserted for behaviour as well as for silence.

    A send that failed must still leave an expirable row (R11) and must still
    report `delivered=False`, so the workflow applies the fail-safe default
    without waiting out the hour. Swallowing the token must not also swallow the
    escalation.
    """
    component.bot.fail_send = RuntimeError(
        f"Unauthorized: POST https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    )

    with caplog.at_level(logging.DEBUG):
        sent = await component.run(send_escalation, send_request())

    assert sent.delivered is False
    with closing(store.connect(component.db_path)) as conn:
        pending = store.pending_escalations(conn)
    assert [record.escalation_id for record in pending] == [sent.escalation_id]

    # The class of the failure is diagnosis enough; its message is not ours to
    # publish, because Telegram put the token inside it.
    assert "RuntimeError" in caplog.text
    assert BOT_TOKEN not in caplog.text


#: A credential in a committed file is a leak no runtime test can catch, because
#: nothing has to run for it to be published.
_LITELLM_KEY_RE = re.compile(r"sk-[A-Za-z0-9_\-]{8,}")

#: `<bot-id>:<secret>` — the Bot API's token shape.
_BOT_TOKEN_RE = re.compile(r"\b\d{6,}:[A-Za-z0-9_\-]{30,}\b")


@pytest.mark.parametrize("path", COMPONENT_MODULES, ids=module_id)
def test_no_shipped_module_carries_a_credential_literal(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    found = _LITELLM_KEY_RE.findall(text) + _BOT_TOKEN_RE.findall(text)
    assert not found, f"{module_id(path)} contains what looks like a credential: {found}"


def code_strings(tree: ast.Module) -> set[str]:
    """Every string constant the module's *code* spells, docstrings excluded.

    This component is required to explain at length which credentials it does not
    touch, and saying so is not doing so.
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
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    }


@pytest.mark.parametrize("path", COMPONENT_MODULES, ids=module_id)
def test_this_component_never_names_the_master_key(path: Path) -> None:
    """001's credential is in the same process and is none of 002's business.

    The judge authenticates with the per-attempt virtual key that arrives in its
    dispatch (constitution V). A module here that could even *spell*
    `LITELLM_MASTER_KEY` would be a module that could read it, and the distance
    from "can read" to "wrote it into an error" is one refactor.
    """
    assert "LITELLM_MASTER_KEY" not in code_strings(parse(path)), (
        f"{module_id(path)} names the proxy master key; the judge is given a "
        "per-attempt virtual key and has no business reading component 1's "
        "credential (FR-009)"
    )


@pytest.mark.parametrize("path", COMPONENT_MODULES, ids=module_id)
def test_the_bot_token_is_named_only_where_it_must_be_read(path: Path) -> None:
    names_it = "TELEGRAM_BOT_TOKEN" in code_strings(parse(path))
    if path in TOKEN_READERS:
        assert names_it, (
            f"{module_id(path)} is supposed to read the bot token from the "
            "environment and no longer names it — has the credential moved?"
        )
    else:
        assert not names_it, (
            f"{module_id(path)} names the bot token; it is read inside the send "
            "activity and the bridge process only (FR-009)"
        )


def test_a_gate_subprocess_cannot_inherit_either_credential() -> None:
    """The allowlist, asserted against the two names that exist today…

    …and against one that does not: `scrubbed_env` is an allowlist precisely so
    the credential invented next quarter is dropped by a rule written this one
    (R3, constitution V).
    """
    assert "LITELLM_MASTER_KEY" not in gates.SCRUBBED_ENV_ALLOWLIST
    assert "TELEGRAM_BOT_TOKEN" not in gates.SCRUBBED_ENV_ALLOWLIST

    env = gates.scrubbed_env(
        {
            "PATH": "/usr/bin",
            "LITELLM_MASTER_KEY": MASTER_KEY,
            "TELEGRAM_BOT_TOKEN": BOT_TOKEN,
            "TELEGRAM_CHAT_ID": CHAT_ID,
            "SOME_FUTURE_CREDENTIAL": "sk-not-invented-yet",
        }
    )
    assert env == {"PATH": "/usr/bin"}


def test_the_credential_sweep_actually_read_the_component() -> None:
    """A parametrized sweep over an empty file list passes without asserting."""
    swept = {module_id(path) for path in COMPONENT_MODULES}
    assert {
        "factory/verify/models.py",
        "factory/verify/criteria.py",
        "factory/verify/factory_yaml.py",
        "factory/verify/gates.py",
        "factory/verify/diffcheck.py",
        "factory/verify/judge.py",
        "factory/verify/ladder.py",
        "factory/verify/store.py",
        "factory/notify/messages.py",
        "factory/notify/service.py",
        "factory/activities/verify_activities.py",
        "factory/activities/notify_activities.py",
    } <= swept
    assert {module_id(path) for path in TOKEN_READERS} <= swept


# ============================================================================
# 2. FR-009 — the judge is reachable from exactly one place
# ============================================================================


def imported_modules(tree: ast.Module) -> set[str]:
    """Every dotted module name the file imports, however it spells the import."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
    return found


def test_exactly_one_module_imports_the_judge() -> None:
    """FR-009 as a property of the import graph.

    The judge is the component's only LLM edge and its only outbound HTTP call.
    Everything else reaches it through one activity, so "the judge runs in the
    inner loop only" is enforced by what can see it, not by convention.
    """
    importers = {
        path
        for path in COMPONENT_MODULES
        if any(
            name == "factory.verify.judge" or name.startswith("factory.verify.judge.")
            for name in imported_modules(parse(path))
        )
    }
    assert importers == {JUDGE_CALLER}, (
        "the judge library is imported by "
        f"{sorted(module_id(path) for path in importers)}; only "
        f"{module_id(JUDGE_CALLER)} may reach it (FR-009)"
    )


#: Calling any of these is asking a model for an opinion, or preparing to.
JUDGE_ENTRY_POINTS = frozenset(
    {"run_judge", "build_prompt", "parse_verdict", "_complete"}
)


def test_every_judge_invocation_sits_inside_the_run_judge_activity() -> None:
    """One call site, and it is the one the contract names.

    `judge_required` decides whether the call happens at all, and it is pure; the
    call itself exists in exactly one place, so there is no second path by which
    a completion could be spent — and no plain function a merge-queue check could
    import and invoke (FR-009, SC-003).
    """
    tree = parse(JUDGE_CALLER)
    owner = enclosing_functions(tree)

    call_sites = {
        owner_name(owner, node)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in JUDGE_ENTRY_POINTS
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "judge"
    }

    assert call_sites == {"run_judge"}, (
        f"the judge is invoked from {sorted(call_sites)}; only the run_judge "
        "activity may invoke it (FR-009)"
    )

    wrapper = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "run_judge"
    )
    assert "activity.defn" in {
        ast.unparse(decorator) for decorator in wrapper.decorator_list
    }, (
        "run_judge is no longer an activity; the judge would then be callable as "
        "a plain function from anywhere (FR-009)"
    )


def test_a_target_repo_cannot_declare_a_judge_gate() -> None:
    """The fence that actually faces CI: `factory.yaml`'s closed gate vocabulary.

    Gates are what a target repo's own tooling runs and what a merge queue would
    reuse. The schema admits three deterministic names and rejects everything
    else with `CONFIG_ERROR`, so the judge has no slot in the one file a repo
    could use to smuggle it into CI (FR-009, D-008).
    """
    assert set(KNOWN_GATES) == {"test", "lint", "typecheck"}

    with pytest.raises(factory_yaml.FactoryConfigError) as excinfo:
        factory_yaml.parse_factory_config(
            "version: 1\nruntime: python:3.11\n"
            "gates:\n  judge: 'python -m factory.verify.judge'\n"
        )
    assert "judge" in str(excinfo.value)


MANIFEST_FILES = sorted((TESTS_ROOT / "fixtures" / "target_repo").rglob("*.yaml"))


def test_no_shipped_manifest_declares_a_command_that_reaches_the_judge() -> None:
    """The behavioural half: nothing in the fixture corpus even tries."""
    assert MANIFEST_FILES, "no manifests were scanned; this proved nothing"
    for path in MANIFEST_FILES:
        text = path.read_text(encoding="utf-8")
        for forbidden in ("factory.verify.judge", "run_judge", "factory-judge"):
            assert forbidden not in text, (
                f"{path.name} declares a gate command reaching the judge (FR-009)"
            )


def test_the_component_exposes_no_entry_point_that_reaches_the_judge() -> None:
    """Nothing exports the judge toward a CI runner or a merge system.

    Two surfaces, because those are the two a runner can pull on without
    importing anything: the console scripts the package installs, and the modules
    that do something when executed with `python -m`. This component adds exactly
    one runnable module — the escalation bridge — and it verifies nothing.
    """
    manifest = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    scripts: dict[str, str] = manifest.get("project", {}).get("scripts", {})
    for name, target in scripts.items():
        assert "judge" not in f"{name}{target}", (
            f"console script {name!r} → {target!r} exposes the judge (FR-009)"
        )
        assert "verify" not in f"{name}{target}", (
            f"console script {name!r} → {target!r} exposes verification (FR-009)"
        )

    runnable = {
        module_id(path)
        for path in COMPONENT_MODULES
        if any(
            isinstance(node, ast.If)
            and ast.unparse(node.test) == "__name__ == '__main__'"
            for node in parse(path).body
        )
    }
    assert runnable == {"factory/notify/service.py"}, (
        f"unexpected runnable modules in this component: {sorted(runnable)}"
    )


def test_the_reference_flow_is_not_production_code() -> None:
    """The retry loop ships as a documented pattern, not as a shipped workflow.

    `tests/reference_flow.py` is test support (T030): the WorkGraph interpreter
    component owns the production loop. A copy of it under `factory/` would be
    this component quietly acquiring an orchestrator — and with it, a second
    place the judge could be driven from.
    """
    assert not list(COMPONENT_ROOT.rglob("reference_flow.py"))
    for path in COMPONENT_MODULES:
        assert "workflow.defn" not in path.read_text(encoding="utf-8"), (
            f"{module_id(path)} defines a workflow; this component ships "
            "activities and libraries only (plan.md § Structure Decision)"
        )


def test_the_bridge_sends_one_signal_and_no_other() -> None:
    """The bridge is this component's only outbound orchestration call.

    Naming the signal in one place is what keeps a button press from becoming a
    second way to unlock an edge — the interpreter decides that from the recorded
    verdict (FR-005), never from a Telegram callback.
    """
    assert service.SIGNAL_NAME == "escalation_resolved"

    signalled = {
        ast.unparse(node.args[0])
        for node in ast.walk(parse(COMPONENT_ROOT / "notify" / "service.py"))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "signal"
        and node.args
    }
    assert signalled == {"SIGNAL_NAME"}


# ============================================================================
# 3. SC-002 — no path to PASS with a failing gate or an empty write-scope diff
# ============================================================================


def passing_gate(name: str = "test") -> GateResult:
    return GateResult(
        name=name,
        command=f"bash gates/{name}.sh",
        status=GateStatus.PASS,
        exit_code=0,
        duration_s=0.4,
        output_tail="ok",
    )


def gate_with(status: GateStatus, name: str = "lint") -> GateResult:
    return GateResult(
        name=name,
        command=f"bash gates/{name}.sh",
        status=status,
        exit_code=None if status in (GateStatus.TIMEOUT, GateStatus.CONFIG_ERROR) else 3,
        duration_s=1.5,
        output_tail=f"{name}: {status.value}",
    )


def proved_output(
    scope: WriteScope | str = WriteScope.WORKTREE,
    *,
    has_diff: bool = True,
    artifacts_present: bool | None = None,
) -> OutputCheck:
    """An `OutputCheck` whose `passed` came from the real rule, never from a
    literal — a fixture that hardcoded it would be testing itself."""
    return OutputCheck(
        write_scope=scope.value if isinstance(scope, WriteScope) else scope,
        has_diff=has_diff,
        expected_artifacts=["reports/findings.md"] if artifacts_present is not None else [],
        artifacts_present=artifacts_present,
        passed=diffcheck.decide_passed(
            scope, has_diff=has_diff, artifacts_present=artifacts_present
        ),
    )


def judge_verdict(outcome: JudgeOutcome) -> JudgeVerdict:
    return JudgeVerdict(
        outcome=outcome,
        findings=[
            JudgeScenarioFinding(
                scenario=SCENARIO.scenario_id,
                passed=outcome is JudgeOutcome.PASS,
                reasoning="scored against the dispatched scenario",
            )
        ],
        feedback="US2-S2: the diff does not show the gate ordering",
        judge_attempt=1,
        truncated_input=False,
        model_alias=JUDGE_MODEL_ALIAS,
    )


#: Every gate suite worth composing: none at all (the vacuous case a naive
#: verdict reads as "nothing failed"), one of each status, each non-PASS status
#: hiding behind a passing gate, and an all-green suite.
GATE_SUITES: list[tuple[str, list[GateResult]]] = [
    ("no-gates", []),
    *[(f"only-{status.value}", [gate_with(status)]) for status in GateStatus],
    *[
        (f"pass-then-{status.value}", [passing_gate(), gate_with(status)])
        for status in GateStatus
        if status is not GateStatus.PASS
    ],
    ("all-pass", [passing_gate("lint"), passing_gate("test")]),
]

#: Every output-check state the persona registry can produce, plus one it cannot.
OUTPUT_STATES: list[tuple[str, OutputCheck]] = [
    (
        f"{scope}/diff={has_diff}/artifacts={artifacts_present}",
        proved_output(scope, has_diff=has_diff, artifacts_present=artifacts_present),
    )
    for scope in (*[member.value for member in WriteScope], "scope-the-registry-lost")
    for has_diff in (True, False)
    for artifacts_present in (True, False, None)
]

JUDGE_STATES: list[tuple[str, JudgeVerdict | None]] = [
    ("never-ran", None),
    *[(outcome.value, judge_verdict(outcome)) for outcome in JudgeOutcome],
]

#: The scopes whose proof of work is the diff (FR-004) — spelled here as the
#: values that cross the activity boundary, which is what composition sees.
DIFF_SCOPE_VALUES = frozenset({WriteScope.WORKTREE.value, WriteScope.DOCS.value})


@pytest.mark.parametrize(
    "gate_results", [suite for _, suite in GATE_SUITES], ids=[name for name, _ in GATE_SUITES]
)
def test_composition_has_no_path_to_a_false_pass(
    gate_results: list[GateResult],
) -> None:
    """The whole product, not a table of rows someone chose.

    A truth table is only as good as the row nobody thought to add, and
    `compose_result` is the only thing standing between a green-looking attempt
    and an unlocked downstream edge (FR-005). So the claim is stated as the
    invariant SC-002 actually makes — PASS *iff* gates ran and all passed, the
    node proved it produced something, and the judge either agreed or never ran —
    and every combination of output state and judge outcome is checked against it.
    """
    gates_green = bool(gate_results) and all(
        gate.status is GateStatus.PASS for gate in gate_results
    )

    for output_label, output in OUTPUT_STATES:
        for judge_label, verdict in JUDGE_STATES:
            where = f"{output_label} + judge {judge_label}"
            result = composed(
                gate_results=gate_results, output_check=output, judge=verdict
            )

            judge_accepts = verdict is None or verdict.outcome in (
                JudgeOutcome.PASS,
                JudgeOutcome.UNAVAILABLE,
            )
            expected = (
                OverallVerdict.PASS
                if gates_green and output.passed and judge_accepts
                else OverallVerdict.FAIL
            )
            assert result.verdict is expected, where

            # The two failures SC-002 names, restated so a regression says which.
            if not gates_green:
                assert result.verdict is OverallVerdict.FAIL, (
                    f"{where}: PASS with a gate that did not pass"
                )
            if output.write_scope in DIFF_SCOPE_VALUES and not output.has_diff:
                assert result.verdict is OverallVerdict.FAIL, (
                    f"{where}: PASS on an empty write-scope diff (FR-004)"
                )

            # And the guard in front of the judge can never open on evidence that
            # has already decided a FAIL — which is what makes the skip
            # cheapest-first rather than a hopeful ordering (SC-003).
            if not gates_green or not output.passed:
                assert judge_required(gate_results, output, CRITERIA) is False, where


@pytest.mark.parametrize("scope", [*WriteScope, "scope-the-registry-lost", ""])
@pytest.mark.parametrize("has_diff", [True, False])
@pytest.mark.parametrize("artifacts_present", [True, False, None])
def test_the_anti_rubber_stamp_rule_is_exhaustive(
    scope: WriteScope | str, has_diff: bool, artifacts_present: bool | None
) -> None:
    """Nothing fails open, in either direction (FR-004, R7).

    A write scope passes on its diff and nothing else; a read scope passes on its
    declared artifact and nothing else; a scope the registry never defined passes
    on nothing at all.
    """
    passed = diffcheck.decide_passed(
        scope, has_diff=has_diff, artifacts_present=artifacts_present
    )

    if scope in (WriteScope.WORKTREE, WriteScope.DOCS):
        assert passed is has_diff
    elif scope is WriteScope.READ:
        assert passed is (artifacts_present is True)
    else:
        assert passed is False


def test_only_the_composer_decides_a_verdict() -> None:
    """`VerificationResult` is built in exactly two places, and one is a reader.

    `compose_result` applies the truth table; `store._result_from_row` rebuilds a
    row that was already composed. A third construction would be a second
    definition of what PASS means, which is the shape SC-002 fails in.
    """
    builders: dict[str, str] = {}
    for path in COMPONENT_MODULES:
        tree = parse(path)
        owner = enclosing_functions(tree)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "VerificationResult"
            ):
                builders[owner_name(owner, node)] = module_id(path)

    assert builders == {
        "compose_result": "factory/verify/models.py",
        "_result_from_row": "factory/verify/store.py",
    }, f"unexpected verdict constructions: {builders}"


def test_nothing_but_the_composer_writes_a_passing_verdict() -> None:
    """`OverallVerdict.PASS` may be compared to anywhere, and assigned in one place."""
    assignments: dict[str, str] = {}
    for path in COMPONENT_MODULES:
        tree = parse(path)
        owner = enclosing_functions(tree)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.keyword)
                and node.arg == "verdict"
                and "OverallVerdict.PASS" in ast.unparse(node.value)
            ):
                assignments[owner_name(owner, node)] = module_id(path)

    assert assignments == {"compose_result": "factory/verify/models.py"}, (
        f"a passing verdict is written in {assignments}"
    )


async def test_a_failing_gate_records_fail_and_never_spends_a_completion(
    component: Component,
) -> None:
    """SC-002 end to end, on a real repo whose `test` gate exits 3.

    The judge is scripted to call the work perfect, so a composition that
    consulted it — or that read "some gates passed" as green — would produce the
    exact false PASS this component exists to prevent. The proxy's empty request
    log is the other half: no completion was spent to learn what a two-second
    lint already knew.
    """
    worktree = component.touched_worktree("failing-gate")
    component.proxy.reply(passing_verdict(), times=3)

    gate_results = await component.run(
        run_gates, RunGatesInput(worktree_path=str(worktree))
    )
    output = await component.run(
        check_output,
        CheckOutputInput(
            worktree_path=str(worktree), write_scope=WriteScope.WORKTREE.value
        ),
    )

    assert [gate.status for gate in gate_results] == [
        GateStatus.PASS,
        GateStatus.FAIL,
        GateStatus.PASS,
    ]
    assert output.has_diff is True, "the node did work; only the gate failed"
    assert judge_required(gate_results, output, CRITERIA) is False

    result = composed(gate_results=gate_results, output_check=output, judge=None)
    assert result.verdict is OverallVerdict.FAIL

    await component.run(record_verification, RecordVerificationInput(result=result))
    with closing(store.connect(component.db_path)) as conn:
        stored = store.node_history(conn, EPIC, NODE)

    assert [row.verdict for row in stored] == [OverallVerdict.FAIL]
    assert stored[0].judge is None, "the judge never ran, and the row says so"
    assert component.proxy.calls == [], (
        "a completion was spent on a node a failing gate had already decided"
    )


async def test_a_clean_worktree_records_fail_however_green_everything_else_is(
    component: Component,
) -> None:
    """The other half of SC-002: every gate passes over an untouched worktree.

    This is the rubber stamp FR-004 exists to catch — a suite is just as green
    about work that was never done — so the judge is again scripted to agree, and
    the verdict is still FAIL.
    """
    worktree = component.worktree("passing")

    gate_results = await component.run(
        run_gates, RunGatesInput(worktree_path=str(worktree))
    )
    output = await component.run(
        check_output,
        CheckOutputInput(
            worktree_path=str(worktree), write_scope=WriteScope.WORKTREE.value
        ),
    )
    assert all(gate.status is GateStatus.PASS for gate in gate_results)
    assert output.has_diff is False and output.passed is False

    component.proxy.reply(passing_verdict())
    verdict = await component.run(run_judge, judge_input())
    assert verdict.outcome is JudgeOutcome.PASS

    result = composed(gate_results=gate_results, output_check=output, judge=verdict)
    assert result.verdict is OverallVerdict.FAIL

    await component.run(record_verification, RecordVerificationInput(result=result))
    with closing(store.connect(component.db_path)) as conn:
        stored = store.node_history(conn, EPIC, NODE)
    assert [row.verdict for row in stored] == [OverallVerdict.FAIL]


def test_the_verdict_sweep_covers_every_combination_it_claims_to() -> None:
    """The product is the assertion; an empty one would pass silently."""
    assert len(GATE_SUITES) == 1 + len(GateStatus) + (len(GateStatus) - 1) + 1
    assert len(OUTPUT_STATES) == (len(WriteScope) + 1) * 2 * 3
    assert len(JUDGE_STATES) == 1 + len(JudgeOutcome)
    assert {label for label, _ in OUTPUT_STATES} >= {
        "worktree/diff=False/artifacts=None",
        "docs/diff=False/artifacts=None",
        "read/diff=True/artifacts=False",
    }
