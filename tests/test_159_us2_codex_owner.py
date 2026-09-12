"""US2: one declared Codex credential has one host-global owner."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import stat
from pathlib import Path
from dataclasses import replace

import pytest
from temporalio.converter import default as default_data_converter
from temporalio.client import WorkflowFailureError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner
from temporalio.worker import Worker

from factory.config import Persona
from factory.verify.ladder import next_action
from factory.verify.models import (
    AttemptRecord,
    JudgeOutcome,
    NextAction,
    OverallVerdict,
    VerificationConfig,
)
from factory.workgraph.workflow import EpicWorkflow
from factory.workgraph.models import WorkNode
from factory.workgraph.models import ResolvedPersona

from factory.workgraph.codex_credential import (
    CredentialAdmissionWorkflow,
    CredentialDeclaration,
    CredentialLease,
    CredentialOwnerTopology,
    CredentialOwnerAdmissionInput,
    CredentialOwnerAdmissionResult,
    CredentialOwnerRoots,
    CredentialOwnerBusy,
    GatewayProgressInput,
    MixedGatewayInput,
    MixedGatewayWorkflow,
    admit_codex_owner,
    gateway_credential_tick,
)


HOST = "operator-host"
OWNER_ID = "codex-production"
OPERATOR_UID = os.getuid()


def declaration(root: Path, generation: int = 1) -> CredentialDeclaration:
    return CredentialDeclaration(
        owner_id=OWNER_ID,
        source_path=root / "source-auth.json",
        generation=generation,
    )


def request(tmp_path: Path) -> CredentialOwnerAdmissionInput:
    return CredentialOwnerAdmissionInput(
        epic_id="epic-a",
        node_id="node-a",
        target_repo="sample-a",
        deployment_shape="bwrap",
        owner_id=OWNER_ID,
        source_path=str(tmp_path / "operator-state" / "source-auth.json"),
        host_id=HOST,
        operator_state_root=str(tmp_path / "operator-state"),
        operator_uid=OPERATOR_UID,
    )


async def test_two_epics_targets_and_shapes_resolve_one_host_owner(
    tmp_path: Path,
) -> None:
    """Different runtime callers collapse to the declared host owner path."""
    operator_root = tmp_path / "operator-state"
    roots = CredentialOwnerRoots(root=operator_root, host_id=HOST)
    targets = ["sample-a", "sample-b"]

    resolved = [
        roots.owner_directory(
            declaration(operator_root),
            epic_id=epic,
            target_repo=target,
            deployment_shape=shape,
        )
        for epic, target, shape in [
            ("epic-a", targets[0], "bwrap"),
            ("epic-b", targets[1], "host"),
        ]
    ]

    assert len({path.resolve() for path in resolved}) == 1
    owner = resolved[0]
    assert owner.parent == operator_root / HOST
    assert owner.name == OWNER_ID


async def test_owner_admission_admits_exactly_one_concurrent_waiter(
    tmp_path: Path,
) -> None:
    """A short owner transaction returns one lease and BUSY to the other."""
    operator_root = tmp_path / "operator-state"
    roots = CredentialOwnerRoots(
        root=operator_root, host_id=HOST, operator_uid=OPERATOR_UID
    )
    first = roots.owner_directory(declaration(operator_root))
    second = roots.owner_directory(declaration(operator_root))
    source = declaration(operator_root)
    lease = None
    try:
        lease, busy = await roots.admit_concurrently(first, second, source)

        assert lease is not None
        assert lease.owner_id == OWNER_ID
        assert busy is not None
        assert busy.retry_after_s > 0
        assert (first / "active-lease.json").exists()
        assert stat.S_IMODE(operator_root.stat().st_mode) == 0o700
        assert stat.S_IMODE(first.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE(first.stat().st_mode) == 0o700
    finally:
        if lease is not None and (first / "active-lease.json").exists():
            await roots.release(lease, owner_directory=first)


def test_readiness_refuses_another_host_for_one_identity(tmp_path: Path) -> None:
    """One owner cannot be declared on two hosts."""
    roots = CredentialOwnerRoots(
        root=tmp_path / "host-a", host_id=HOST, operator_uid=OPERATOR_UID
    )
    other_host = replace(roots, host_id="operator-host-b")
    topology = CredentialOwnerTopology(roots=(roots, other_host))

    assert topology.readiness_refusal(declaration(tmp_path)) == (
        "credential owner topology must declare one host"
    )


def test_readiness_refuses_duplicate_operator_roots(tmp_path: Path) -> None:
    """Two roots on one host do not become target-local serialization."""
    first = CredentialOwnerRoots(
        root=tmp_path / "operator-state-a", host_id=HOST, operator_uid=OPERATOR_UID
    )
    second = CredentialOwnerRoots(
        root=tmp_path / "operator-state-b", host_id=HOST, operator_uid=OPERATOR_UID
    )
    topology = CredentialOwnerTopology(roots=(first, second))

    refusal = topology.readiness_refusal(declaration(tmp_path))
    assert refusal == (
        "credential owner topology must declare one operator state root on that host"
    )


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        (0o750, "credential owner root must have 0700 permissions"),
        (0o755, "credential owner root must have 0700 permissions"),
    ],
)
async def test_admission_refuses_group_and_world_accessible_roots(
    tmp_path: Path, mode: int, expected: str
) -> None:
    """The owner root is checked before admission and never widened back."""
    operator_root = tmp_path / "operator-state"
    operator_root.mkdir(mode=mode)
    roots = CredentialOwnerRoots(
        root=operator_root, host_id=HOST, operator_uid=OPERATOR_UID
    )

    with pytest.raises(ValueError, match=expected):
        await roots.admit(
            roots.owner_directory(declaration(operator_root)),
            declaration(operator_root),
        )


async def test_admission_refuses_a_symlinked_owner_root(
    tmp_path: Path,
) -> None:
    """A symlink is not a durable private operator root."""
    operator_root = tmp_path / "operator-state"
    replacement = tmp_path / "replaced-state"
    replacement.mkdir(mode=0o700)
    operator_root.mkdir(mode=0o700)
    operator_root.rmdir()
    operator_root.symlink_to(replacement)
    roots = CredentialOwnerRoots(
        root=operator_root, host_id=HOST, operator_uid=OPERATOR_UID
    )

    with pytest.raises(
        ValueError, match="credential owner root must not be a symlink"
    ):
        await roots.admit(
            roots.owner_directory(declaration(operator_root)),
            declaration(operator_root),
        )


async def test_admission_refuses_a_wrong_owner_root(tmp_path: Path) -> None:
    """The declared operator identity is checked at admission, not trusted."""
    operator_root = tmp_path / "operator-state"
    operator_root.mkdir(mode=0o700)
    roots = CredentialOwnerRoots(
        root=operator_root, host_id=HOST, operator_uid=OPERATOR_UID + 1
    )

    with pytest.raises(
        ValueError,
        match="credential owner root must be owned by the declared operator identity",
    ):
        await roots.admit(
            roots.owner_directory(declaration(operator_root)),
            declaration(operator_root),
        )


async def test_admission_refuses_a_root_replaced_after_declaration(
    tmp_path: Path,
) -> None:
    """Declaration does not authorize a later replacement of the root."""
    operator_root = tmp_path / "operator-state"
    roots = CredentialOwnerRoots(
        root=operator_root, host_id=HOST, operator_uid=OPERATOR_UID
    )
    owner = roots.owner_directory(declaration(operator_root))
    held = await roots.admit(owner, declaration(operator_root))
    await roots.release(held, owner_directory=owner)

    replaced_state = tmp_path / "declared-state-backup"
    operator_root.rename(replaced_state)
    shutil.copytree(replaced_state, operator_root)

    with pytest.raises(
        ValueError, match="credential owner root was replaced after declaration"
    ):
        await roots.admit(owner, declaration(operator_root))


async def test_cancellation_while_busy_leaves_no_new_side_effects(
    tmp_path: Path,
) -> None:
    """A waiter cancelled before admission charges and stages nothing."""
    environment = await WorkflowEnvironment.start_time_skipping()
    try:
        operator_root = tmp_path / "operator-state"
        roots = CredentialOwnerRoots(
            root=operator_root, host_id=HOST, operator_uid=OPERATOR_UID
        )
        owner = roots.owner_directory(declaration(operator_root))
        held = await roots.admit(owner, declaration(operator_root))
        active = owner / "active-lease.json"
        held_lease = json.loads(active.read_text(encoding="utf-8"))
        worker = Worker(
            environment.client,
            task_queue="credential-cancellation",
            workflows=[CredentialAdmissionWorkflow],
            activities=[admit_codex_owner],
            workflow_runner=UnsandboxedWorkflowRunner(),
        )
        async with worker:
            handle = await environment.client.start_workflow(
                CredentialAdmissionWorkflow.run,
                request(tmp_path),
                id="cancelled-waiter",
                task_queue="credential-cancellation",
            )
            await asyncio.sleep(0.05)
            await handle.cancel()
            with pytest.raises(WorkflowFailureError):
                await handle.result()
        assert json.loads(active.read_text(encoding="utf-8")) == held_lease
        assert not (owner / "candidates").exists()
        assert not (owner / "staged").exists()
        assert not (owner / "attempt").exists()
        await roots.release(held, owner_directory=owner)
    finally:
        await environment.shutdown()


async def test_owner_payloads_round_trip_with_the_typed_converter(
    tmp_path: Path,
) -> None:
    """An older payload decodes with the newer owner fields defaulted."""
    encoded = default_data_converter().payload_converter.to_payload(request(tmp_path))
    body = json.loads(encoded.data)
    for field in ("host_id", "operator_state_root", "operator_uid"):
        assert field in body
        del body[field]
    encoded.data = json.dumps(body).encode()

    old_request = replace(
        request(tmp_path),
        host_id="",
        operator_state_root="",
        operator_uid=None,
    )
    result = CredentialOwnerAdmissionResult(
        lease=CredentialLease(owner_id=OWNER_ID, host_id=HOST, lease_id="lease-1")
    )
    converter = default_data_converter().payload_converter
    payload = encoded
    result_payload = converter.to_payload(result)
    decoded = [
        converter.from_payload(payload, CredentialOwnerAdmissionInput),
        converter.from_payload(result_payload, CredentialOwnerAdmissionResult),
    ]

    assert decoded == [old_request, result]
    assert isinstance(decoded[0], CredentialOwnerAdmissionInput)
    assert isinstance(decoded[1], CredentialOwnerAdmissionResult)


async def test_gateway_work_progresses_while_subscription_owner_is_busy(
    tmp_path: Path,
) -> None:
    """The mixed workflow keeps ticking gateway work during BUSY."""
    environment = await WorkflowEnvironment.start_time_skipping()
    try:
        owner_root = CredentialOwnerRoots(
            root=tmp_path / "operator-state",
            host_id=HOST,
            operator_uid=OPERATOR_UID,
        )
        owner = owner_root.owner_directory(declaration(tmp_path / "operator-state"))
        held = await owner_root.admit(owner, declaration(tmp_path / "operator-state"))
        worker = Worker(
            environment.client,
            task_queue="credential-mixed",
            workflows=[CredentialAdmissionWorkflow, MixedGatewayWorkflow],
            activities=[admit_codex_owner, gateway_credential_tick],
            workflow_runner=UnsandboxedWorkflowRunner(),
        )
        async with worker:
            gateway_ticks = await environment.client.execute_workflow(
                MixedGatewayWorkflow.run,
                MixedGatewayInput(
                    owner=request(tmp_path),
                    gateway=GatewayProgressInput(
                        epic_id="epic-b",
                        node_id="gateway-node",
                        attempt=1,
                        route="gateway",
                    ),
                ),
                id="mixed-credential",
                task_queue="credential-mixed",
            )
        assert gateway_ticks == 3
        await owner_root.release(held, owner_directory=owner)
    finally:
        await environment.shutdown()


async def test_effective_rung_owns_the_credential_not_the_original_persona(
    tmp_path: Path,
) -> None:
    """Retry and recovery route the owner by the current snapshot entry."""
    workflow_instance = EpicWorkflow()
    gateway = Persona(
        name="gateway-codex",
        agent="codex",
        model="model-gateway",
        fallback=None,
        skills=(),
        write_scope="worktree",
        needs_worktree=True,
        route="gateway",
    )
    subscription = replace(
        gateway,
        name="codex-subscription",
        route="subscription",
    )
    workflow_instance._personas = {
        "gateway-codex": gateway,
        "codex-subscription": subscription,
    }

    assert workflow_instance._is_subscription_node("gateway-codex") is False
    assert workflow_instance._is_subscription_node("codex-subscription") is True
    assert workflow_instance._is_subscription_node("unknown-codex") is False

    roots = CredentialOwnerRoots(
        root=tmp_path / "operator-state",
        host_id=HOST,
        operator_uid=OPERATOR_UID,
    )
    owner = roots.owner_directory(declaration(tmp_path / "operator-state"))
    first = await roots.admit(owner, declaration(tmp_path / "operator-state"))
    second = None
    try:
        with pytest.raises(CredentialOwnerBusy):
            await roots.admit(owner, declaration(tmp_path / "operator-state"))
        await roots.release(first, owner_directory=owner)
        second = await roots.admit(owner, declaration(tmp_path / "operator-state"))
        assert second.lease_id != first.lease_id
    finally:
        if second is not None:
            await roots.release(second, owner_directory=owner)


async def test_promotion_is_automatic_and_configuration_bounded() -> None:
    """The configured ladder grants the upper rung without a new approval."""
    history = [
        AttemptRecord(
            attempt=attempt,
            persona="gateway-codex",
            verdict=OverallVerdict.FAIL,
            judge_outcome=JudgeOutcome.RETRY,
        )
        for attempt in range(1, 4)
    ]
    configured = VerificationConfig(
        max_attempts=3,
        debugger_cycles=0,
        promotion_persona="codex-subscription",
        promotion_cycles=1,
    )
    absent = replace(configured, promotion_persona=None)
    disabled = replace(configured, promotion_cycles=0)

    assert next_action(history, configured) is NextAction.PROMOTE
    assert absent is not None and next_action(history, absent) is NextAction.ESCALATE
    assert disabled is not None and next_action(history, disabled) is NextAction.ESCALATE
    exhausted = [*history, AttemptRecord(attempt=4, persona="codex-subscription", verdict=OverallVerdict.FAIL)]
    assert next_action(exhausted, configured) is NextAction.ESCALATE

    workflow_instance = EpicWorkflow()
    workflow_instance._personas = {
        "gateway-codex": ResolvedPersona(
            persona="gateway-codex",
            model_alias="model-gateway",
            models=["model-gateway"],
            agent="codex",
            route="gateway",
        ),
        "codex-subscription": ResolvedPersona(
            persona="codex-subscription",
            model_alias="model-subscription",
            models=["model-subscription"],
            agent="codex",
            route="subscription",
        ),
    }
    node = WorkNode(
        id="node-a",
        story_key="US1",
        persona="gateway-codex",
        spec_ref="159-a-subscription-credential-has-one-durable-owner/us1",
        requirement_keys=["US1"],
        depends_on=[],
    )
    assert workflow_instance._rung_selection(
        NextAction.PROMOTE, node, configured
    ) == ("codex-subscription", "promotion rung")
    routing = workflow_instance._routing_for("codex-subscription", rung="promotion rung")
    assert routing.agent == "codex"
    assert routing.route == "subscription"
    assert routing.model_alias == "model-subscription"
