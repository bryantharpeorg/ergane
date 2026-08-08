"""The PR body renderer: what a landed node says about itself (plan.md § US1).

A node that reached ladder PASS opens a PR. The title and body are the only
thing the factory publishes to a repository the operator may later make public
(architecture §10), so this module is pure and its renderer's *output* is the
surface of a security constraint: no credential, proxy URL, or transcript path
may appear in a body that could end up in a public repo.

Two properties are load-bearing:

- **Determinism.** The body travels through workflow state under Temporal, so
  `render_pr_body` touches no clock, no random source, no filesystem — same
  inputs, identical bytes, every call (SC-001). The provenance line's "when" is
  passed in from the workflow's own `now`, never read here.
- **The inputs carry the secrets on purpose.** The caller hands over the proxy
  URL, the master key, the telegram token, and the transcript path precisely so
  this module can prove it drops them. A renderer that never saw a secret could
  not be trusted to redact it; one that sees and discards it is the guard that
  holds (architecture §10).

What the body carries is the node's public account of why it landed: the spec
reference (feature + requirement keys), the branch, the attempt count, the
per-gate results of the passing attempt, the judge's outcome (or the
`judge_unavailable` flag), and a provenance line. The verdict is a PASS by
construction — this runs only on the ladder's PASS — but the renderer quotes the
row's own `verdict` rather than assuming, so a mis-wired caller surfaces as a
body that says what it says.
"""

from __future__ import annotations

from collections.abc import Sequence

from factory.verify.models import VerificationResult

#: The provenance line's subject. The factory's automated landings are
#: attributable the same way its salvage commits are — to the machine, never to
#: a person who did not press a button (worktree.py's own identity).
LANDED_BY = "Ergane Factory"


def pr_title(*, epic_id: str, node_id: str, story_title: str) -> str:
    """`<epic>/<node>: <story title>` — the plan's exact title shape.

    This is the render end of the landing-attribution contract; the parse end is
    `factory.workgraph.landed._LANDING_RE`. A change to either side must change
    both (016-delta-derivation FR-001/FR-002, D-034).
    """
    return f"{epic_id}/{node_id}: {story_title}"


def render_pr_body(
    *,
    epic_id: str,
    node_id: str,
    branch: str,
    attempt: int,
    feature: str,
    requirement_keys: Sequence[str],
    result: VerificationResult,
    proxy_url: str,
    master_key: str,
    telegram_token: str,
    transcript_path: str,
) -> str:
    """The PR body for a passing node — deterministic, and secret-free.

    `proxy_url`, `master_key`, `telegram_token`, and `transcript_path` are
    accepted and deliberately never written: they exist in the inputs so the
    redaction is a property of this function's output, asserted by the tests,
    rather than an accident of what the caller chose not to pass. (They are
    read into locals to name them as present, then dropped.)

    The body is a markdown block: a header naming the node and the spec
    reference, the branch and attempt, the per-gate results, the judge's word,
    and the provenance line. Nothing else — no gate output tail, no judge
    feedback, no transcript path (a public PR is not a place to quote a
    private evidence store).
    """
    # The secrets are present in the inputs; naming them here is what makes the
    # redaction load-bearing rather than accidental. They are never rendered.
    _ = (proxy_url, master_key, telegram_token, transcript_path)

    lines = [
        f"## {epic_id}/{node_id}",
        "",
        f"Lands `{branch}` on ladder PASS.",
        "",
        f"- spec: `{feature}`",
        f"- requirements: {', '.join(requirement_keys)}",
        f"- attempt {attempt}",
        f"- verdict: {result.verdict}",
        "",
        "### Gates",
        *[f"- `{gate.name}`: {_gate_status(gate)}" for gate in result.gate_results],
        "",
        "### Judge",
        _judge_line(result),
        "",
        f"_Landed by {LANDED_BY}._",
        "",
    ]
    return "\n".join(lines)


def _judge_line(result: VerificationResult) -> str:
    """The judge's word, or the flag that says there was no judge agreement."""
    if result.judge is not None:
        return f"judge: {result.judge.outcome}"
    if result.judge_unavailable:
        return "judge_unavailable: PASS reached without judge agreement"
    return "judge: did not run"


def _gate_status(gate) -> str:  # type: ignore[no-untyped-def]
    """A gate's status as the operator reads it — a `StrEnum`'s value.

    A `GateResult` that crossed a Temporal payload boundary carries the status
    enum's string; reading `.value` only would fail on the serialized form, so
    this accepts either and renders the same. `verdict` in the body is the same
    way — it is a `StrEnum` whose value is what the operator reads.
    """
    from factory.verify.models import GateStatus

    status = gate.status
    return status.value if isinstance(status, GateStatus) else str(status)
