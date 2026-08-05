"""The one process that has to know about all of it — and the seam that proves it.

`factory/worker.py` is four lines of Temporal boilerplate around a list, and the
list is the entire risk. Every other test in this repository fakes the world:
`tests/test_interpreter.py` registers a scripted activity under each *real* name,
so a rename in an activity surface breaks it — but nothing there, and nothing in
`tests/test_epic_cli.py`, notices an activity that is defined, invoked, and never
*registered*. That failure has no test-time symptom at all. It has a runtime one:
the epic starts, the workflow schedules the activity, nobody polls for it, and the
node hangs until its schedule-to-close timeout expires with a key issued against
work no process is doing. The gap is exactly the thing a worker exists to close,
so this file closes it mechanically rather than by inspection.

"Mechanically" is the whole point, and it means one thing here: the list of
activities the interpreter invokes is never written down in this file. It is read
out of `factory/workgraph/workflow.py`'s own syntax tree — every
`workflow.execute_activity` / `start_activity` call, its first argument resolved
through the workflow module's namespace to the `@activity.defn` name Temporal will
actually dispatch on. A future task that wires the judge (T035) or adds an
activity for reading a worktree diff does not have to remember to update this
test: the scan finds the new call, and the assertion fails until the worker
registers it.

Three claims, in the order a missing registration would bite:

- **Everything the workflow invokes is registered**, by dispatch name, not by
  Python identity — the name is what crosses the wire.
- **All four activity surfaces are registered whole** (agent, usage, verify,
  notify), not merely the subset today's workflow happens to call. `run_judge` is
  the live example: 002 ships it, the interpreter's judge branch is still unwired
  (T035), and the worker that will have to serve it should already be serving it.
- **Temporal itself accepts the set** — the registration is handed to a real
  `Worker` against a real (time-skipping) server, so duplicate names, a callable
  that is not an activity, or a workflow class Temporal rejects fail here rather
  than on a worker host at 3am.
"""

from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path
from typing import AsyncIterator

import pytest
from temporalio import activity, workflow as workflow_api
from temporalio.testing import WorkflowEnvironment

import factory.worker as worker_module
from factory.workgraph import workflow as workflow_module
from factory.workgraph.workflow import TASK_QUEUE, EpicWorkflow

#: The call sites that put an activity on a task queue. `start_activity` is in
#: here because the agent attempt uses it — it is the cancellable form (the kill
#: path awaits its handle), and a scan that only knew `execute_activity` would
#: have missed the single longest-running activity in the component.
_INVOCATIONS = frozenset(
    {
        "execute_activity",
        "execute_activity_method",
        "execute_local_activity",
        "start_activity",
        "start_local_activity",
    }
)

#: One name per component surface, asserted to be among what the scan found. The
#: scan is the mechanism; these are the smoke alarm on the mechanism. A refactor
#: that moved dispatch behind a helper the scan cannot see would otherwise turn
#: every assertion below into a vacuous truth about an empty set.
_SURFACE_ANCHORS = {
    "run_agent_attempt": "agent",
    "issue_attempt_key": "usage",
    "record_verification": "verify",
    "send_escalation": "notify",
}

#: Where the factory's activities live. Globbed rather than listed so a fifth
#: surface is covered the day it exists.
_ACTIVITY_PACKAGE = "factory.activities"


# --- reading the workflow's own syntax ----------------------------------------


def _activity_name(fn: object) -> str:
    """The name Temporal dispatches `fn` on, from its `@activity.defn`."""
    return activity._Definition.must_from_callable(fn).name


def _resolve(node: ast.expr) -> object:
    """Resolve an `execute_activity` first argument to the thing it names.

    Two shapes reach here: a bare name (`resolve_graph`), which the workflow
    imported and this looks up in that module's namespace, and a dotted one
    (`usage_activities.poll_usage`). A string literal never does — those are
    handled by the caller, since a literal *is* already the dispatch name.
    """
    if isinstance(node, ast.Name):
        return getattr(workflow_module, node.id)
    if isinstance(node, ast.Attribute):
        return getattr(_resolve(node.value), node.attr)
    raise AssertionError(
        "the workflow invokes an activity through an expression this scan cannot "
        f"resolve ({ast.dump(node)}); registration can no longer be checked "
        "mechanically — teach this test the new shape before landing it"
    )


def _invoked_activity_names() -> set[str]:
    """Every activity `factory/workgraph/workflow.py` schedules, by name."""
    tree = ast.parse(inspect.getsource(workflow_module))
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in _INVOCATIONS:
            continue
        if not (isinstance(node.func.value, ast.Name) and node.func.value.id == "workflow"):
            continue
        assert node.args, (
            "an activity invocation with no arguments in workflow.py: "
            f"line {node.lineno}"
        )
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            names.add(first.value)
        else:
            names.add(_activity_name(_resolve(first)))
    return names


def _defined_activity_names() -> dict[str, str]:
    """Every `@activity.defn` in `factory/activities/`, mapped to its module."""
    package = importlib.import_module(_ACTIVITY_PACKAGE)
    root = Path(package.__file__).parent
    defined: dict[str, str] = {}
    for path in sorted(root.glob("*.py")):
        if path.name == "__init__.py":
            continue
        module = importlib.import_module(f"{_ACTIVITY_PACKAGE}.{path.stem}")
        for _, member in vars(module).items():
            definition = (
                activity._Definition.from_callable(member)
                if callable(member)
                else None
            )
            # `from_callable` answers for re-exports too, so keep only the
            # activities this module actually defines.
            if definition is not None and getattr(member, "__module__", None) == module.__name__:
                defined[definition.name] = module.__name__
    return defined


def _registered_activities() -> list[object]:
    """The worker's activity registration, as the module publishes it."""
    registration = list(worker_module.ACTIVITIES)
    assert registration, "factory.worker registers no activities at all"
    return registration


def _registered_names() -> set[str]:
    return {_activity_name(fn) for fn in _registered_activities()}


# --- the registration set ------------------------------------------------------


def test_the_scan_finds_all_four_surfaces() -> None:
    """The mechanism itself, before anything is asserted through it.

    Every claim below is `<something> <= registered names`, and a scan that
    silently found nothing would make all of them pass. So the scan is checked
    first, against one name from each component the interpreter composes.
    """
    invoked = _invoked_activity_names()
    missing = {
        f"{name} ({surface})"
        for name, surface in _SURFACE_ANCHORS.items()
        if name not in invoked
    }
    assert not missing, (
        f"the workflow-source scan found {sorted(invoked)}, which is missing "
        f"{sorted(missing)} — either dispatch moved behind an indirection this "
        "test cannot follow, or the interpreter stopped calling a surface"
    )


def test_the_interpreter_workflow_is_registered() -> None:
    """`EpicWorkflow` is the one workflow type in the factory (D-002)."""
    workflows = list(worker_module.WORKFLOWS)
    assert EpicWorkflow in workflows, (
        f"factory.worker registers {workflows}, which does not include "
        "EpicWorkflow — nothing would poll for the epic `factory-epic start` "
        "creates"
    )
    names = {workflow_api._Definition.must_from_class(cls).name for cls in workflows}
    assert "EpicWorkflow" in names


def test_the_worker_polls_the_queue_the_cli_starts_on() -> None:
    """One queue constant, stated once (contracts/cli.md).

    `factory-epic start` names `TASK_QUEUE` when it creates the workflow; a
    worker polling anything else produces an epic that is started, visible in the
    Web UI, and never picked up — the failure mode that looks most like a bug in
    the interpreter and is least like one.
    """
    assert worker_module.TASK_QUEUE == TASK_QUEUE == "workgraph"


def test_every_activity_the_workflow_invokes_is_registered() -> None:
    """The claim this file exists for (T027), derived rather than transcribed."""
    invoked = _invoked_activity_names()
    registered = _registered_names()
    missing = invoked - registered
    assert not missing, (
        f"the workflow schedules {sorted(missing)} but the worker registers "
        f"{sorted(registered)} — a node reaching one of those activities would "
        "hang with its key issued until the schedule-to-close timeout expired"
    )


def test_all_four_activity_surfaces_are_registered_whole() -> None:
    """The worker serves the components, not the subset today's workflow calls.

    `run_judge` is the reason this is stated separately: 002 ships it, the
    interpreter's judge branch is still unwired (T035), and the worker that will
    serve it the moment that lands should not also need editing that day.
    """
    defined = _defined_activity_names()
    registered = _registered_names()
    missing = {name: defined[name] for name in defined.keys() - registered}
    assert not missing, (
        f"these activities are defined but unregistered: {sorted(missing.items())}"
    )


def test_registered_activities_are_real_and_unambiguous() -> None:
    """Every entry is an `@activity.defn`, and no name is claimed twice.

    Temporal raises on both, but only when a worker is constructed — which on a
    worker host is process start, not import. Named here, the error says which
    callable.
    """
    seen: dict[str, object] = {}
    for fn in _registered_activities():
        definition = activity._Definition.from_callable(fn)
        assert definition is not None, (
            f"{fn!r} is registered as an activity but carries no @activity.defn"
        )
        assert definition.name not in seen, (
            f"two callables are registered as '{definition.name}': "
            f"{seen.get(definition.name)!r} and {fn!r}"
        )
        seen[definition.name] = fn


def test_importing_the_worker_connects_to_nothing() -> None:
    """Import is inert: the registration is data, and `main` is what runs.

    Every test above imports this module. If import-time work dialed Temporal,
    they would all depend on a server being up, and the worker would be
    untestable exactly where it is most worth testing.
    """
    assert callable(worker_module.main)
    imported = {
        (statement.module, alias.name)
        for statement in ast.walk(ast.parse(inspect.getsource(worker_module)))
        if isinstance(statement, ast.ImportFrom)
        for alias in statement.names
    }
    # The notify bridge's environment contract, dialed by the CLI too, so the
    # factory has one deployment story rather than one per process (R12).
    assert ("factory.notify.service", "TEMPORAL_ADDRESS_ENV") in imported
    assert ("factory.notify.service", "TEMPORAL_NAMESPACE_ENV") in imported


# --- and Temporal's own opinion of it -----------------------------------------


@pytest.fixture
async def env() -> AsyncIterator[WorkflowEnvironment]:
    environment = await WorkflowEnvironment.start_time_skipping()
    try:
        yield environment
    finally:
        await environment.shutdown()


async def test_temporal_accepts_the_registration(env: WorkflowEnvironment) -> None:
    """The set is handed to a real worker against a real server, and it polls.

    Construction is where Temporal validates a registration — activity
    definitions, duplicate names, the workflow class — and running is where it
    proves the queue is pollable. Both happen here with the *production* set, no
    scripted activity anywhere near it.
    """
    built = worker_module.build_worker(env.client)
    assert built.task_queue == TASK_QUEUE
    async with built:
        assert built.is_running
