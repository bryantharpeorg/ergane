"""The two guarantees no single module can prove about itself.

Every other test file here asks whether a module does its job. This one asks
whether the component, taken whole, still has the two properties the spec picked
as the ones an operator has to be able to trust blind:

- **SC-004 — the master key exists in the worker's environment and nowhere
  else.** Individual modules already assert this about their own errors, but a
  credential leaks through whichever path nobody thought to look at, so the sweep
  is exhaustive rather than representative: every failure path the component can
  take is driven to its exception and the whole raised chain — message, args,
  repr, and the rendered traceback of every `__cause__` behind it — is searched
  for the credential; then a full attempt lifecycle runs and every byte it
  persisted is searched too, ledger, sidecars, Temporal payloads and the
  operator's own CLI output alike. The canary master key appears nowhere else in
  this repository, so a single byte of it anywhere is a leak with no innocent
  explanation.

- **SC-005 — the component measures and does not act.** Absence is the hard
  thing to test: no assertion about behaviour can prove that a throttle *isn't*
  there, only that it did not fire on the inputs someone chose. So absence is
  checked structurally, over the parsed source: nothing branches on how much an
  attempt has spent (type guards excepted — asking whether a value is a number is
  not asking whether it is too large), no identifier or payload key in the
  component can even spell a cap, and `factory/usage/` imports nothing capable of
  acting on a running attempt — no signals, no processes, and no `temporalio`,
  so the library that measures an attempt has no vocabulary for failing one.
  Budget enforcement returns with spec 004 (D-021); until it does, these tests
  are what "deferred" means in code.

  The structural claim is then paired with the behavioural one it cannot make
  alone: the same lifecycle run at a trivial spend and at a runaway one produces
  the same sequence of proxy calls, byte for byte in the fake's request log.
  Magnitude changes the numbers in the row and nothing else in the world.

Written last (T028), against the finished component: unlike every other test
file here, this one is expected to pass on arrival. A failure means something
that was true when it was written has since stopped being true.
"""

from __future__ import annotations

import ast
import re
import sys
import traceback
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterator

import httpx
import pytest
from temporalio.converter import DataConverter
from temporalio.testing import ActivityEnvironment

from factory.activities import usage_activities
from factory.activities.usage_activities import (
    LEDGER_PATH_ENV,
    IssueKeyInput,
    TeardownInput,
    issue_attempt_key,
    poll_usage,
    teardown_attempt,
)
from factory.usage import cli
from factory.usage.ledger import ROLLUP_DIMENSIONS
from factory.usage.litellm_client import (
    MASTER_KEY_ENV,
    PROXY_URL_ENV,
    LiteLLMClient,
)
from factory.usage.models import KeyLease, Termination, UsageRecord, UsageSnapshot
from tests.conftest import FakeLiteLLM

#: The credential the worker host holds. Deliberately unlike anything else in
#: this repository — no substring of it occurs in source, fixtures or generated
#: keys — so "this string appears here" is never a coincidence (SC-004).
SECRET = "sk-canary-4f21bd8e6c0a47d9b3-master"

#: What a misconfigured worker offers instead. A rejected credential is still a
#: credential: the 401 it earns must not echo it back either (FR-009).
WRONG_SECRET = "sk-canary-000000000000000000-wrong"

EPIC = "epic-sweep"
NODE = "node-impl"
ATTEMPT = 1
PERSONA = "implementer"
SPEC_REF = "add-usage-tracking/final-sweep"
MODELS = ["anthropic/CHANGEME"]

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPONENT_ROOT = REPO_ROOT / "factory"
USAGE_PACKAGE = COMPONENT_ROOT / "usage"

#: Every module of the component, and the subset SC-005 names explicitly.
COMPONENT_MODULES = sorted(COMPONENT_ROOT.rglob("*.py"))
USAGE_MODULES = sorted(USAGE_PACKAGE.rglob("*.py"))


def module_id(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


# --- the world one attempt runs in ------------------------------------------


@dataclass
class Worker:
    """A worker host: the fake proxy, the credential in the environment, a
    scratch ledger, and the activity environment the orchestrator would use."""

    proxy: FakeLiteLLM
    env: ActivityEnvironment
    ledger_path: Path
    workspace: Path
    monkeypatch: pytest.MonkeyPatch

    async def issue(self, **overrides: Any) -> KeyLease:
        fields: dict[str, Any] = {
            "node_id": NODE,
            "epic_id": EPIC,
            "attempt": ATTEMPT,
            "persona": PERSONA,
            "spec_ref": SPEC_REF,
            "models": MODELS,
        }
        fields.update(overrides)
        return await self.env.run(issue_attempt_key, IssueKeyInput(**fields))

    async def poll(self, lease: KeyLease) -> UsageSnapshot:
        return await self.env.run(poll_usage, lease)

    async def teardown(
        self,
        lease: KeyLease,
        *,
        termination: Termination = Termination.COMPLETED,
        snapshot: UsageSnapshot | None = None,
    ) -> UsageRecord:
        return await self.env.run(
            teardown_attempt,
            TeardownInput(lease=lease, termination=termination, last_snapshot=snapshot),
        )

    def client(self, *, master_key: str = SECRET) -> LiteLLMClient:
        """A direct client, for the failure paths that live below the activities."""
        return LiteLLMClient(
            base_url=self.proxy.base_url,
            master_key=master_key,
            transport=self.proxy.transport,
        )

    def broken_client(self, handler: Callable[[httpx.Request], httpx.Response]) -> LiteLLMClient:
        """A client wired to a proxy that answers wrongly, or not at all."""
        return LiteLLMClient(
            base_url=self.proxy.base_url,
            master_key=SECRET,
            transport=httpx.MockTransport(handler),
        )


@pytest.fixture
def worker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Worker:
    """One worker host, credentials in the environment where FR-009 puts them.

    The activity seam supplies a transport only, so `from_env` still has to
    resolve the master key for anything to authenticate — which is what makes
    the deleted-variable and wrong-credential paths below reachable at all.
    """
    proxy = FakeLiteLLM(master_key=SECRET)
    ledger_path = tmp_path / ".factory" / "ledger.db"

    monkeypatch.setenv(PROXY_URL_ENV, proxy.base_url)
    monkeypatch.setenv(MASTER_KEY_ENV, SECRET)
    monkeypatch.setenv(LEDGER_PATH_ENV, str(ledger_path))
    monkeypatch.setattr(
        usage_activities,
        "open_client",
        lambda: LiteLLMClient.from_env(transport=proxy.transport),
    )

    return Worker(
        proxy=proxy,
        env=ActivityEnvironment(),
        ledger_path=ledger_path,
        workspace=tmp_path,
        monkeypatch=monkeypatch,
    )


def spend_on(proxy: FakeLiteLLM, key: str, *, tokens: int, spend: float) -> None:
    """One request against the attempt's key, as the running agent would make it."""
    proxy.add_spend_row(
        key,
        prompt_tokens=tokens,
        completion_tokens=tokens // 10,
        spend=spend,
        cache_read_tokens=tokens // 2,
    )


# --- SC-004: every failure path ---------------------------------------------


async def a_worker_host_with_no_proxy_url(worker: Worker) -> object:
    worker.monkeypatch.delenv(PROXY_URL_ENV)
    return await worker.issue()


async def a_worker_host_with_no_master_key(worker: Worker) -> object:
    worker.monkeypatch.delenv(MASTER_KEY_ENV)
    return await worker.issue()


async def a_rejected_credential_on_issue(worker: Worker) -> object:
    worker.monkeypatch.setenv(MASTER_KEY_ENV, WRONG_SECRET)
    return await worker.issue()


async def a_rejected_credential_on_poll(worker: Worker) -> object:
    lease = await worker.issue()
    worker.monkeypatch.setenv(MASTER_KEY_ENV, WRONG_SECRET)
    return await worker.poll(lease)


async def a_rejected_credential_on_the_spend_logs(worker: Worker) -> object:
    lease = await worker.issue()
    async with worker.client(master_key=WRONG_SECRET) as client:
        return await client.fetch_spend_log_rows(lease.key, issued_at=lease.issued_at)


async def a_rejected_credential_on_revocation(worker: Worker) -> object:
    lease = await worker.issue()
    async with worker.client(master_key=WRONG_SECRET) as client:
        return await client.revoke_key(lease.key)


async def a_proxy_that_will_not_mint_a_key(worker: Worker) -> object:
    worker.proxy.fail_next("/key/generate", status=503)
    return await worker.issue()


async def a_proxy_that_will_not_answer_a_poll(worker: Worker) -> object:
    lease = await worker.issue()
    worker.proxy.fail_next("/key/info", status=500)
    return await worker.poll(lease)


async def a_proxy_that_will_not_page_its_spend_logs(worker: Worker) -> object:
    lease = await worker.issue()
    worker.proxy.fail_next("/spend/logs/v2", status=500)
    async with worker.client() as client:
        return await client.fetch_spend_log_rows(lease.key, issued_at=lease.issued_at)


async def a_key_the_proxy_has_forgotten(worker: Worker) -> object:
    lease = await worker.issue()
    async with worker.client() as client:
        await client.revoke_key(lease.key)
        return await client.get_spend(lease.key)


async def a_proxy_that_cannot_be_reached(worker: Worker) -> object:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    async with worker.broken_client(refuse) as client:
        return await client.get_spend("sk-fake-1")


async def a_proxy_answering_html(worker: Worker) -> object:
    def gateway(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>502 Bad Gateway</html>")

    async with worker.broken_client(gateway) as client:
        return await client.get_spend("sk-fake-1")


async def a_proxy_reporting_an_unusable_spend(worker: Worker) -> object:
    def nonsense(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"info": {"spend": "quite a lot"}})

    async with worker.broken_client(nonsense) as client:
        return await client.get_spend("sk-fake-1")


async def a_dispatch_that_dropped_a_dimension(worker: Worker) -> object:
    lease = replace(await worker.issue(), persona="")
    return await worker.teardown(lease)


async def a_ledger_that_cannot_be_written(worker: Worker) -> object:
    lease = await worker.issue()
    obstruction = worker.workspace / "not-a-directory"
    obstruction.write_text("")
    worker.monkeypatch.setenv(LEDGER_PATH_ENV, str(obstruction / "ledger.db"))
    return await worker.teardown(lease)


#: Every way this component can fail. A path added to the component without a
#: line here is a path whose error nobody has read (SC-004).
FAILURE_PATHS: list[Callable[[Worker], Awaitable[object]]] = [
    a_worker_host_with_no_proxy_url,
    a_worker_host_with_no_master_key,
    a_rejected_credential_on_issue,
    a_rejected_credential_on_poll,
    a_rejected_credential_on_the_spend_logs,
    a_rejected_credential_on_revocation,
    a_proxy_that_will_not_mint_a_key,
    a_proxy_that_will_not_answer_a_poll,
    a_proxy_that_will_not_page_its_spend_logs,
    a_key_the_proxy_has_forgotten,
    a_proxy_that_cannot_be_reached,
    a_proxy_answering_html,
    a_proxy_reporting_an_unusable_spend,
    a_dispatch_that_dropped_a_dimension,
    a_ledger_that_cannot_be_written,
]


def renderings_of(error: BaseException) -> Iterator[str]:
    """Every way this failure could reach a human: the formatted traceback of
    the whole chain, plus each link's own message, args and repr."""
    yield "".join(traceback.format_exception(type(error), error, error.__traceback__))

    seen: BaseException | None = error
    depth = 0
    while seen is not None and depth < 10:
        yield str(seen)
        yield repr(seen)
        yield str(seen.args)
        seen = seen.__cause__ or seen.__context__
        depth += 1


@pytest.mark.parametrize("failure", FAILURE_PATHS, ids=lambda fn: fn.__name__)
async def test_no_failure_path_renders_the_master_key(
    failure: Callable[[Worker], Awaitable[object]], worker: Worker
) -> None:
    with pytest.raises(BaseException) as excinfo:
        await failure(worker)

    # An error path is the one place a credential travels by accident: it is
    # built from whatever was in hand, logged by default, and read by someone
    # who is not thinking about secrets at the time (FR-009, SC-004).
    for rendering in renderings_of(excinfo.value):
        for secret in (SECRET, WRONG_SECRET):
            assert secret not in rendering, (
                f"{failure.__name__} leaked a credential through "
                f"{type(excinfo.value).__name__}"
            )


# --- SC-004: every persisted byte -------------------------------------------


async def test_the_master_key_reaches_no_byte_the_component_persists(
    worker: Worker, capsys: pytest.CaptureFixture[str]
) -> None:
    lease = await worker.issue()
    spend_on(worker.proxy, lease.key, tokens=1_000, spend=0.05)
    snapshot = await worker.poll(lease)
    record = await worker.teardown(lease, snapshot=snapshot)

    # The ledger, its WAL and any sidecar SQLite left behind: everything the run
    # put on disk, not just the file it was aiming at.
    written = [path for path in sorted(worker.workspace.rglob("*")) if path.is_file()]
    assert worker.ledger_path in written, "the run persisted no ledger to sweep"
    for path in written:
        assert SECRET.encode() not in path.read_bytes(), (
            f"master key found in {path.relative_to(worker.workspace)}"
        )

    # Temporal payloads: activity inputs and outputs are persisted verbatim in
    # workflow history, which is why the credential may not ride on any of them.
    payloads = await DataConverter.default.encode(
        [
            IssueKeyInput(
                node_id=NODE,
                epic_id=EPIC,
                attempt=ATTEMPT,
                persona=PERSONA,
                spec_ref=SPEC_REF,
                models=MODELS,
            ),
            lease,
            snapshot,
            TeardownInput(
                lease=lease,
                termination=Termination.COMPLETED,
                last_snapshot=snapshot,
            ),
            record,
        ]
    )
    for payload in payloads:
        for blob in (bytes(payload.data), *payload.metadata.values()):
            assert SECRET.encode() not in blob, "master key found in a Temporal payload"

    # The virtual key is a different matter: model-constrained, TTL'd and now
    # revoked, it is allowed to travel (FR-009).
    assert lease.key != SECRET
    assert lease.key not in (SECRET, WRONG_SECRET)

    # And the operator's own view of the ledger.
    for dimension in ROLLUP_DIMENSIONS:
        assert cli.main(["--db", str(worker.ledger_path), "--by", dimension]) == 0
        assert cli.main(["--db", str(worker.ledger_path), "--by", dimension, "--json"]) == 0
    assert cli.main(["--db", str(worker.workspace / "absent.db"), "--by", "epic"]) == 3

    printed = capsys.readouterr()
    assert SECRET not in printed.out
    assert SECRET not in printed.err


#: A credential in a committed file is a leak that no runtime test can catch,
#: because nothing has to run for it to be published.
_CREDENTIAL_LITERAL = re.compile(r"sk-[A-Za-z0-9_\-]{8,}")

SHIPPED_FILES = sorted(
    [*COMPONENT_MODULES, REPO_ROOT / "personas.yaml", REPO_ROOT / "pyproject.toml"]
)


@pytest.mark.parametrize("path", SHIPPED_FILES, ids=module_id)
def test_no_shipped_file_carries_a_credential_literal(path: Path) -> None:
    found = _CREDENTIAL_LITERAL.findall(path.read_text(encoding="utf-8"))
    assert not found, f"{module_id(path)} contains what looks like a key: {found}"


# --- SC-005: nothing branches on how much was spent -------------------------

#: Names that answer "how much has this attempt used". Existence checks are not
#: on this list — `snapshot is not None` asks whether anything was measured, not
#: whether it was too much — because it is the *magnitude* a branch may not see.
USAGE_MAGNITUDES = frozenset(
    {
        "spend",
        "spend_usd",
        "cost",
        "usd",
        "budget",
        "max_budget",
        "soft_budget",
        "tokens",
        "total_tokens",
        "prompt_tokens",
        "completion_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
        "request_count",
        "requests",
    }
)

#: Words that describe acting on usage rather than recording it. `killed` is
#: deliberately absent: `Termination.KILLED` is something the orchestrator tells
#: this component happened, never something this component decides to do.
ENFORCEMENT_WORDS = frozenset(
    {
        "budget",
        "budgets",
        "cap",
        "caps",
        "capped",
        "quota",
        "quotas",
        "throttle",
        "throttled",
        "breach",
        "breached",
        "enforce",
        "enforced",
        "enforcement",
        "exceed",
        "exceeded",
        "overspend",
        "overspent",
    }
)

#: Modules that could reach out and touch a running attempt. `temporalio` is the
#: one that matters: without it, `factory/usage/` cannot fail, cancel or signal
#: an activity even by accident — measurement has no verb (SC-005).
FORBIDDEN_IN_USAGE = frozenset(
    {"signal", "subprocess", "multiprocessing", "ctypes", "temporalio"}
)

#: Constitution III: the approved roster, by import root. Anything else
#: third-party in this package is a dependency nobody approved. `telegram` is
#: `python-telegram-bot`, approved 2026-07-24 (D-022) for the notifier and first
#: imported by `factory/notify/`.
APPROVED_THIRD_PARTY = frozenset({"httpx", "telegram", "temporalio", "yaml"})


def parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def identifiers(node: ast.AST) -> set[str]:
    """Every name and attribute the expression touches."""
    found: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            found.add(child.id)
        elif isinstance(child, ast.Attribute):
            found.add(child.attr)
    return found


def branch_tests(tree: ast.Module) -> Iterator[ast.AST]:
    """Every expression the module makes a decision on."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.If, ast.IfExp, ast.While, ast.Assert)):
            yield node.test
        elif isinstance(node, ast.Compare):
            # Caught wherever it sits, including assigned to a name first.
            yield node
        elif isinstance(node, (ast.comprehension,)):
            yield from node.ifs


def magnitudes_inspected(test: ast.AST) -> set[str]:
    """Usage magnitudes a decision reads — excluding pure type guards.

    `isinstance(spend, float)` asks whether the proxy sent a number at all,
    which is validation; `spend > cap` asks whether it is too large, which is
    the enforcement this component does not have.
    """
    guarded: set[str] = set()
    for child in ast.walk(test):
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
            if child.func.id in {"isinstance", "issubclass"}:
                guarded |= identifiers(child)
    return (identifiers(test) & USAGE_MAGNITUDES) - guarded


@pytest.mark.parametrize("path", COMPONENT_MODULES, ids=module_id)
def test_no_decision_in_the_component_asks_how_much_was_spent(path: Path) -> None:
    for test in branch_tests(parse(path)):
        inspected = magnitudes_inspected(test)
        assert not inspected, (
            f"{module_id(path)}:{getattr(test, 'lineno', '?')} branches on "
            f"{sorted(inspected)} — usage is measured here, never acted on (SC-005)"
        )


def code_words(tree: ast.Module) -> set[str]:
    """Every word the module's *code* spells — identifiers, argument and payload
    keys, and string values. Docstrings are excluded: this component is required
    to explain at length that it does not enforce budgets, and saying so is not
    doing so. Comments never reach the AST at all.
    """
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }

    spelled: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            spelled.append(node.name)
        elif isinstance(node, ast.Name):
            spelled.append(node.id)
        elif isinstance(node, ast.Attribute):
            spelled.append(node.attr)
        elif isinstance(node, ast.arg):
            spelled.append(node.arg)
        elif isinstance(node, ast.keyword) and node.arg:
            spelled.append(node.arg)
        elif isinstance(node, ast.alias):
            spelled.extend(name for name in (node.name, node.asname) if name)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in docstrings:
                spelled.append(node.value)

    return {word.lower() for text in spelled for word in re.findall(r"[A-Za-z]+", text)}


@pytest.mark.parametrize("path", COMPONENT_MODULES, ids=module_id)
def test_the_component_cannot_even_spell_a_cap(path: Path) -> None:
    spoken = code_words(parse(path)) & ENFORCEMENT_WORDS
    # Payload keys are string constants, so this also holds the line that
    # matters most at the proxy boundary: `/key/generate`'s body has no way to
    # carry `max_budget`, and gains one only over this test (D-021, FR-004).
    assert not spoken, (
        f"{module_id(path)} speaks enforcement vocabulary {sorted(spoken)} outside "
        "its docstrings — caps are deferred to spec 004 (D-021)"
    )


def imported_roots(tree: ast.Module) -> set[str]:
    """The top-level package of every import in the module."""
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


@pytest.mark.parametrize("path", USAGE_MODULES, ids=module_id)
def test_the_usage_library_imports_nothing_that_could_stop_an_attempt(path: Path) -> None:
    reachable = imported_roots(parse(path)) & FORBIDDEN_IN_USAGE
    assert not reachable, (
        f"{module_id(path)} imports {sorted(reachable)} — the measuring library "
        "has no business being able to act on the attempt it measures (SC-005)"
    )


@pytest.mark.parametrize("path", USAGE_MODULES, ids=module_id)
def test_the_usage_library_never_reaches_for_a_process_control(path: Path) -> None:
    # The attribute half of the import check: `os` is imported legitimately, so
    # the ban has to be on what is asked of it.
    forbidden = {"kill", "terminate", "abort", "raise_signal", "_exit", "killpg"}
    reached = identifiers(parse(path)) & forbidden
    assert not reached, f"{module_id(path)} calls {sorted(reached)} (SC-005)"


@pytest.mark.parametrize("path", COMPONENT_MODULES, ids=module_id)
def test_the_component_imports_only_the_approved_roster(path: Path) -> None:
    outside = {
        root
        for root in imported_roots(parse(path))
        if root not in sys.stdlib_module_names
        and root != "factory"
        and root not in APPROVED_THIRD_PARTY
    }
    assert not outside, (
        f"{module_id(path)} imports unapproved dependencies {sorted(outside)} "
        "(constitution III)"
    )


def test_the_source_sweep_actually_read_the_component() -> None:
    # A parametrized sweep over an empty file list passes without asserting
    # anything; this is what keeps the four tests above from going quiet if the
    # layout moves.
    swept = {module_id(path) for path in COMPONENT_MODULES}
    assert {
        "factory/config.py",
        "factory/usage/models.py",
        "factory/usage/litellm_client.py",
        "factory/usage/aggregate.py",
        "factory/usage/ledger.py",
        "factory/usage/cli.py",
        "factory/activities/usage_activities.py",
    } <= swept
    assert {module_id(path) for path in USAGE_MODULES} <= swept


# --- SC-005: magnitude changes the row, and nothing else --------------------


async def lifecycle(
    worker: Worker, *, node_id: str, tokens: int, spend: float
) -> tuple[UsageRecord, list[str]]:
    """One whole attempt — dispatch, a beat, teardown — and what the proxy saw."""
    marker = len(worker.proxy.calls)

    lease = await worker.issue(node_id=node_id)
    spend_on(worker.proxy, lease.key, tokens=tokens, spend=spend)
    snapshot = await worker.poll(lease)
    record = await worker.teardown(lease, snapshot=snapshot)

    return record, worker.proxy.routes[marker:]


async def test_a_runaway_attempt_is_treated_exactly_like_a_cheap_one(
    worker: Worker,
) -> None:
    modest, modest_routes = await lifecycle(
        worker, node_id="node-cheap", tokens=1_000, spend=0.01
    )
    runaway, runaway_routes = await lifecycle(
        worker, node_id="node-runaway", tokens=1_000_000_000, spend=1_000_000.0
    )

    # The whole of SC-005 in one assertion: an attempt that spent a million
    # dollars produced the same five calls, in the same order, as one that spent
    # a cent. No warning, no revocation brought forward, no extra request of any
    # kind — and no exception, which is the failure mode enforcement would most
    # plausibly arrive as.
    assert runaway_routes == modest_routes
    assert runaway_routes == [
        "POST /key/generate",
        "GET /key/info",  # the heartbeat poll
        "GET /key/info",  # teardown's final read (R3 step 1)
        "GET /spend/logs/v2",
        "POST /key/delete",  # last, always (R3)
    ]

    # The magnitude reached the row, which is the component's entire job.
    assert runaway.spend_usd == pytest.approx(1_000_000.0)
    assert runaway.prompt_tokens == 1_000_000_000
    assert runaway.final_usage_confirmed is True

    # And the termination class is still the one the caller passed: nothing here
    # decided the attempt should have been killed.
    assert runaway.termination is Termination.COMPLETED
    assert modest.termination is Termination.COMPLETED


async def test_an_enormous_spend_still_only_gets_an_uncapped_key(
    worker: Worker,
) -> None:
    lease = await worker.issue()
    spend_on(worker.proxy, lease.key, tokens=10_000_000, spend=50_000.0)

    # Whatever the attempt goes on to spend, the key it was issued has no cap to
    # exceed — the fake rejects a capped `/key/generate` outright, so this is the
    # request as it was actually sent (D-021, FR-004).
    generated = worker.proxy.calls_to("/key/generate")
    assert len(generated) == 1
    assert generated[0].body is not None
    assert "max_budget" not in generated[0].body
    assert "soft_budget" not in generated[0].body
    assert worker.proxy.keys[lease.key]["max_budget"] is None

    # Polling a runaway attempt is a read and stays a read (SC-005).
    marker = len(worker.proxy.calls)
    snapshot = await worker.poll(lease)
    assert snapshot.spend_usd == pytest.approx(50_000.0)
    assert worker.proxy.routes[marker:] == ["GET /key/info"]
    assert lease.key in worker.proxy.keys
