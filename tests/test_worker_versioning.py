"""082-US1: the worker declares which code it is — and, without the word, is today's.

Two properties, and the second is the one that can lose a floor.

**Engaged** (`ERGANE_WORKER_BUILD_ID` in the environment): the worker registers
as a version of deployment `ergane-worker`, build id = the revision 053 already
captures, and the four workflow definitions declare a versioning behavior —
PINNED for the epic, the escalation and the question, AUTO_UPGRADE for the
roadmap.

**Disengaged** (the variable absent — every floor that has not deployed US2):
no `deployment_config`, and *no defn declares a behavior at all*. That second
half is not tidiness. Probed on the dev server on 2026-08-22
(`specs/082-…/evidence/us1-t001-t002-probes.md`, part A), an unversioned worker
handed a defn that declares `versioning_behavior` cannot complete a single
workflow task:

    Error while completing workflow activation
      error=code: 'Client specified an invalid argument',
      message: "versioning behavior cannot be specified without deployment
                options being set with versioned mode"

The task retries forever and the epic never moves. So the environment gate has
to cover the decorator argument too, not only the `Worker(...)` keyword, and
`VersioningBehavior.UNSPECIFIED` is the disengaged value because the SDK treats
it as absent (it is 0, and `_workflow_instance.py` tests the field for truth).

**Why the engaged half runs in a subprocess.** The decorators are evaluated at
import, so the only way to observe a versioned registration is a process that
had the variable before it imported anything — which is exactly how systemd
starts the unit US2 will generate. Reloading the workflow modules in-process
would prove a shape no worker ever boots into.

The disengaged half needs no subprocess: this suite runs without the variable,
so `tests/test_worker.py` passing untouched beside these assertions *is* the
control (US1-S2).
"""

from __future__ import annotations

import json
import os
import pwd
import subprocess
import sys
import textwrap
from collections.abc import AsyncIterator, Mapping
from pathlib import Path

import pytest
from temporalio.common import VersioningBehavior, WorkerDeploymentVersion
from temporalio.testing import WorkflowEnvironment

from factory import worker as worker_module
from factory import versioning
from factory.versioning import (
    DEPLOYMENT_NAME,
    WORKER_BUILD_ID_ENV,
    VersioningRefused,
    requested_build_id,
    resolve_deployment_version,
    workflow_versioning_behavior,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


# --- the gate itself, as a pure function --------------------------------------


class TestTheGateIsExplicitEnvironment:
    """FR-001: versioning is engaged by the environment naming it, and nothing else."""

    @pytest.mark.parametrize("environ", [{}, {WORKER_BUILD_ID_ENV: ""}, {WORKER_BUILD_ID_ENV: "   "}])
    def test_absent_or_blank_is_disengaged(self, environ: Mapping[str, str]) -> None:
        assert requested_build_id(environ) is None

    def test_the_variable_names_the_build_id_it_expects(self) -> None:
        assert requested_build_id({WORKER_BUILD_ID_ENV: " 4d2f1ab "}) == "4d2f1ab"

    def test_this_suite_runs_disengaged_which_is_what_makes_it_the_control(self) -> None:
        """US1-S2: every other test in the repository is the unversioned worker."""
        assert versioning.ENGAGED_BUILD_ID is None
        assert WORKER_BUILD_ID_ENV not in os.environ


class TestDisengagedIsTodaysWorker:
    """US1-S2, the control: absent the variable, nothing about the worker moves."""

    def test_no_deployment_version_is_resolved(self) -> None:
        assert resolve_deployment_version(revision="4d2f1ab", requested="") is None
        assert resolve_deployment_version(revision=None, requested=None) is None

    def test_no_workflow_declares_a_versioning_behavior(self) -> None:
        """The half that would otherwise stall every workflow task (part A)."""
        assert (
            workflow_versioning_behavior(VersioningBehavior.PINNED, engaged=False)
            is VersioningBehavior.UNSPECIFIED
        )
        assert (
            workflow_versioning_behavior(VersioningBehavior.AUTO_UPGRADE, engaged=False)
            is VersioningBehavior.UNSPECIFIED
        )

    async def test_build_worker_constructs_exactly_todays_worker(self) -> None:
        """No `deployment_config`, and the 006/053 configuration untouched beside it."""
        async with await WorkflowEnvironment.start_time_skipping() as env:
            built = worker_module.build_worker(env.client)
            config = built.config()
            assert config.get("deployment_config") is None
            assert built.task_queue == worker_module.TASK_QUEUE
            assert list(config["workflows"]) == worker_module.WORKFLOWS
            assert list(config["activities"]) == worker_module.ACTIVITIES
            assert config["interceptors"]


class TestAnUnknowableRevisionRefusesByName:
    """US1-S5, trap 11: a wheel or an unpacked tree may not invent a build id."""

    def test_engaged_with_no_revision_refuses(self) -> None:
        with pytest.raises(VersioningRefused) as caught:
            resolve_deployment_version(revision=None, requested="4d2f1ab")
        message = str(caught.value)
        assert WORKER_BUILD_ID_ENV in message
        assert "4d2f1ab" in message
        assert "git" in message

    def test_engaged_on_the_wrong_revision_refuses(self) -> None:
        """Trap 8: the build id is the checkout's, so a mismatch is a deploy bug."""
        with pytest.raises(VersioningRefused) as caught:
            resolve_deployment_version(revision="beefc0d", requested="4d2f1ab")
        message = str(caught.value)
        assert "4d2f1ab" in message
        assert "beefc0d" in message

    def test_a_matching_revision_is_the_build_id(self) -> None:
        version = resolve_deployment_version(revision="4d2f1ab", requested="4d2f1ab")
        assert version == WorkerDeploymentVersion(
            deployment_name=DEPLOYMENT_NAME, build_id="4d2f1ab"
        )

    async def test_build_worker_refuses_rather_than_booting(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The refusal reaches process start, which is where an operator reads it."""
        monkeypatch.setattr(worker_module, "_WORKER_REVISION", None)
        monkeypatch.setattr(versioning, "ENGAGED_BUILD_ID", "4d2f1ab")
        async with await WorkflowEnvironment.start_time_skipping() as env:
            with pytest.raises(VersioningRefused):
                worker_module.build_worker(env.client)


# --- the engaged half: a process that had the variable before it imported ------

_CHILD = textwrap.dedent(
    '''
    """Boot the production registration the way systemd will, and report."""
    import asyncio, json, sys

    from temporalio.client import Client
    from temporalio.workflow import _Definition
    from temporalio.api.workflowservice.v1 import DescribeWorkerDeploymentRequest

    from factory import versioning, worker as worker_module
    from factory.escalation.question import QuestionWorkflow
    from factory.escalation.workflow import EscalationWorkflow
    from factory.roadmap.workflow import RoadmapWorkflow
    from factory.workgraph.workflow import EpicWorkflow

    CLASSES = {
        "EpicWorkflow": EpicWorkflow,
        "RoadmapWorkflow": RoadmapWorkflow,
        "EscalationWorkflow": EscalationWorkflow,
        "QuestionWorkflow": QuestionWorkflow,
    }


    async def main() -> None:
        mode = sys.argv[1]
        report = {
            "engaged_build_id": versioning.ENGAGED_BUILD_ID,
            "revision": worker_module._WORKER_REVISION,
            "behaviors": {
                name: (_Definition.must_from_class(cls).versioning_behavior or 0).name
                for name, cls in CLASSES.items()
            },
        }
        if mode == "register":
            address, namespace = sys.argv[2], sys.argv[3]
            client = await Client.connect(address, namespace=namespace)
            built = worker_module.build_worker(client)
            config = built.config()["deployment_config"]
            report["deployment"] = {
                "deployment_name": config.version.deployment_name,
                "build_id": config.version.build_id,
                "use_worker_versioning": config.use_worker_versioning,
            }
            report["versions"] = []
            async with built:
                for _ in range(120):
                    try:
                        described = await client.workflow_service.describe_worker_deployment(
                            DescribeWorkerDeploymentRequest(
                                namespace=namespace, deployment_name="ergane-worker"
                            )
                        )
                    except Exception:
                        await asyncio.sleep(0.5)
                        continue
                    info = described.worker_deployment_info
                    report["versions"] = [v.version for v in info.version_summaries]
                    if report["versions"]:
                        break
                    await asyncio.sleep(0.5)
        print("REPORT " + json.dumps(report))


    if __name__ == "__main__":
        asyncio.run(main())
    '''
)


def _boot(*argv: str, build_id: str | None) -> dict:
    """Run the child with the environment a versioned unit would give it."""
    environ = {k: v for k, v in os.environ.items() if k != WORKER_BUILD_ID_ENV}
    if build_id is not None:
        environ[WORKER_BUILD_ID_ENV] = build_id
    completed = subprocess.run(
        [sys.executable, "-c", _CHILD, *argv],
        cwd=REPO_ROOT,
        env=environ,
        capture_output=True,
        text=True,
        timeout=300,
    )
    line = next(
        (l for l in completed.stdout.splitlines() if l.startswith("REPORT ")), None
    )
    assert line, f"child produced no report\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
    return json.loads(line.removeprefix("REPORT "))


@pytest.fixture(scope="module")
async def dev_server() -> AsyncIterator[WorkflowEnvironment]:
    """A real dev server, because the time-skipping one has no deployment API.

    Probed 2026-08-22 (trap 13): `start_time_skipping()` will *run* a versioned
    worker, but `describe_worker_deployment` against it answers "Worker
    Versioning not yet supported in test server", so a registration cannot be
    read back there. `start_local()` runs the real server binary, which answers
    it. That binary resolves the current user at startup, so a bare environment
    (no `USER`, as under some sandboxes) makes it exit before it listens — set
    it from the uid rather than leave the test looking flaky.
    """
    os.environ.setdefault("USER", pwd.getpwuid(os.getuid()).pw_name)
    try:
        env = await WorkflowEnvironment.start_local()
    except RuntimeError as exc:  # the live guard's shape: temporalio raises bare
        pytest.skip(f"no dev server available: {exc}")
    try:
        yield env
    finally:
        await env.shutdown()


class TestEngagedTheWorkerRegistersItsRevision:
    """US1-S1: `ergane-worker` gains a version whose build id is this checkout's."""

    async def test_the_booted_worker_registers_and_can_be_read_back(
        self, dev_server: WorkflowEnvironment
    ) -> None:
        revision = worker_module._worker_revision()
        assert revision, "this test must run inside a git checkout"

        report = _boot(
            "register",
            dev_server.client.service_client.config.target_host,
            dev_server.client.namespace,
            build_id=revision,
        )

        assert report["engaged_build_id"] == revision
        assert report["deployment"] == {
            "deployment_name": DEPLOYMENT_NAME,
            "build_id": revision,
            "use_worker_versioning": True,
        }
        assert f"{DEPLOYMENT_NAME}.{revision}" in report["versions"]


class TestTheDeclaredBehaviors:
    """US1-S3/S4, FR-001/FR-002 — asserted where the decorator puts them."""

    @pytest.fixture(scope="class")
    def engaged(self) -> dict:
        return _boot("defns", build_id=worker_module._worker_revision())

    @pytest.fixture(scope="class")
    def disengaged(self) -> dict:
        return _boot("defns", build_id=None)

    def test_the_epic_the_escalation_and_the_question_are_pinned(
        self, engaged: dict
    ) -> None:
        """US1-S3: an epic finishes on the code it started with."""
        assert engaged["behaviors"]["EpicWorkflow"] == "PINNED"
        assert engaged["behaviors"]["EscalationWorkflow"] == "PINNED"
        assert engaged["behaviors"]["QuestionWorkflow"] == "PINNED"

    def test_the_roadmap_auto_upgrades_because_the_probe_said_so(
        self, engaged: dict
    ) -> None:
        """US1-S4/FR-002, and T001 is the reason it is not PINNED.

        Measured on the dev server: a PINNED workflow's continue-as-new inherits
        its version, so a pinned roadmap would carry the version it started on
        across every run boundary and hold a dead version open forever. The
        AUTO_UPGRADE counterpart adopted the newly-current version at its next
        workflow task and the version it left reached
        VERSION_DRAINAGE_STATUS_DRAINED on its own.
        """
        assert engaged["behaviors"]["RoadmapWorkflow"] == "AUTO_UPGRADE"

    def test_disengaged_no_workflow_declares_anything(self, disengaged: dict) -> None:
        """US1-S2 again, at the decorator: this is what part A says would stall."""
        assert disengaged["engaged_build_id"] is None
        assert set(disengaged["behaviors"].values()) == {"UNSPECIFIED"}
