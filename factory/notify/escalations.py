"""Starting an escalation, and asking Temporal what is waiting on the operator.

041-US2. The client side of `EscalationWorkflow`: the two things a *process*
does with one, kept out of the workflow module because neither runs in workflow
scope and one of them cannot (`secrets` is not deterministic).

- **`start_escalation`** mints the correlation id and uses it as the workflow
  id (FR-004, plan trap 3). A workflow id has to exist before `start_workflow`,
  so the starter mints it; the workflow reads it back from `workflow.info()`
  rather than being handed it twice. A workflow *parent* starting a child uses
  `factory.notify.workflow.child_correlation_id()` instead, which is
  replay-safe.

- **`open_escalations`** answers "what is waiting on me" from running
  workflows, not from a store scrape (FR-008). That distinction is the point of
  making escalation a workflow type, and the two ways a scrape gets it wrong are
  both live facts rather than hypotheticals: a row settled by a channel that
  answered out of band is invisible to a pending-row query while its workflow is
  still waiting, and fourteen rows sat pending on 2026-08-14 with nothing behind
  them at all.

The listing is two reads on purpose. Temporal's visibility index says which
escalations are running; each workflow's own query says what it is asking and
until when. Visibility is eventually consistent and can name an execution that
has already finished or never resolves, so the query is what decides — an
escalation is open when its own workflow says it has no resolution yet.
"""

from __future__ import annotations

import logging
import secrets
from typing import Any

from temporalio.client import (
    WorkflowQueryFailedError,
    WorkflowQueryRejectedError,
)
from temporalio.service import RPCError

from factory.notify.workflow import (
    CORRELATION_ID_HEX,
    ESCALATION_STATUS_QUERY,
    EscalationRequest,
    EscalationWorkflow,
    OpenEscalation,
)

logger = logging.getLogger(__name__)

#: The visibility query that means "escalations a human still has to answer".
#:
#: Pinned as a literal for the reason `roadmap_activities._list_open_epics`
#: pins its own: Temporal's visibility grammar wants the title-case status name,
#: and the SDK's `WorkflowExecutionStatus` enum does not round-trip to it by
#: `.name`, `.value` or `str()`. The `WorkflowType` clause is not optional
#: either — without it this enumerates every workflow in the namespace, epics
#: included.
RUNNING_ESCALATIONS_QUERY = (
    'WorkflowType = "EscalationWorkflow" AND ExecutionStatus = "Running"'
)


def mint_correlation_id() -> str:
    """A fresh correlation id, from a process that is not a workflow.

    12 hex digits: the width that lets `esc:<id>:<choice>` fit inside Telegram's
    64-byte `callback_data` without ever carrying a workflow id (002 R11). The
    workflow-scope sibling is `factory.notify.workflow.child_correlation_id`,
    which mints the same width deterministically.
    """
    return secrets.token_hex(CORRELATION_ID_HEX // 2)


async def start_escalation(
    client: Any,
    request: EscalationRequest,
    *,
    task_queue: str,
    escalation_id: str | None = None,
) -> Any:
    """Start one escalation and hand back its handle.

    The handle's `id` is the correlation id, which is also what a press carries
    and what `ergane escalations list` shows — one id, minted here, for the
    whole lifecycle. Callers that already recorded a row (042's probe writes one
    before it can reach Temporal) pass its id in rather than minting a second.

    The caller names the task queue: this module has no opinion about which
    worker serves an escalation, and importing the epic's queue constant here
    would make the transport's client depend on the interpreter.
    """
    return await client.start_workflow(
        EscalationWorkflow.run,
        request,
        id=escalation_id or mint_correlation_id(),
        task_queue=task_queue,
    )


async def open_escalations(client: Any) -> tuple[OpenEscalation, ...]:
    """Every escalation still waiting on a human, oldest deadline first (FR-008).

    Sourced from running workflows. A row that some channel settled while its
    workflow is still waiting is still open, and a pending row with no workflow
    behind it is not an escalation at all — which is exactly the pair of facts a
    `SELECT ... WHERE resolution IS NULL` gets backwards.
    """
    open_now: list[OpenEscalation] = []
    for escalation_id in await _running_escalation_ids(client):
        status = await _escalation_status(client, escalation_id)
        if status is not None and status.resolution is None:
            open_now.append(status)
    return tuple(
        sorted(open_now, key=lambda item: (item.expires_at, item.escalation_id))
    )


async def _running_escalation_ids(client: Any) -> tuple[str, ...]:
    """The ids Temporal's visibility index reports as running escalations."""
    found: list[str] = []
    async for execution in client.list_workflows(RUNNING_ESCALATIONS_QUERY):
        found.append(execution.id)
    return tuple(found)


async def _escalation_status(
    client: Any, escalation_id: str
) -> OpenEscalation | None:
    """Ask one escalation what it is waiting for, or `None` if it cannot say.

    `None` covers every way an id from the visibility index can fail to resolve
    into an answer — an execution that has been terminated, one whose run has
    aged out, one the index reported a beat after it closed. None of them is an
    error worth failing an operator's list over: the whole point of the list is
    the escalations that *did* answer.
    """
    try:
        document = await client.get_workflow_handle(escalation_id).query(
            ESCALATION_STATUS_QUERY
        )
    except (RPCError, WorkflowQueryFailedError, WorkflowQueryRejectedError) as exc:
        logger.debug(
            "escalation %s did not answer its status query (%s)",
            escalation_id,
            type(exc).__name__,
        )
        return None
    return _as_open_escalation(document)


def _as_open_escalation(document: Any) -> OpenEscalation:
    """One query result, however the converter handed it back.

    A query with no declared result type comes back as a plain mapping (the
    shape `ergane build status` reads); a typed one comes back as the dataclass.
    Both are accepted so the reader does not depend on which.
    """
    if isinstance(document, OpenEscalation):
        return document
    return OpenEscalation(
        escalation_id=document["escalation_id"],
        epic_id=document["epic_id"],
        node_id=document["node_id"],
        question=document["question"],
        expires_at=document["expires_at"],
        resolution=document.get("resolution"),
    )
