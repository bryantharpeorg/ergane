"""What one attempt is told, and what it is never told (FR-006, R9).

This is the one place the factory writes *to* an agent, and it is pure by
construction: text in, prompt out, no filesystem and no registry. Every read the
prompt depends on happens on the other side of the activity boundary
(`load_prompt_sources`), which is what makes the assembly unit-testable in the
literal sense FR-006 asks for — and what makes it deterministic, so SC-001's
replay guarantee extends to the prompt a replayed attempt is handed.

Four rules do the work here:

- **Nothing is summarized, paraphrased, or truncated.** The story's section, the
  whole plan and the task slice arrive exactly as they were authored, and prior
  failure evidence arrives byte-for-byte (002 FR-006) — a retry shown a summary
  of a traceback has been handed a description of the bug instead of the bug,
  and the tails are the whole reason a second attempt is worth spending.
  Bounding prompt size is the operator's authoring concern (story-sized slices),
  never a silent transform in here.

- **The slice is the scope fence.** A node is given its own story's tasks and no
  others. Carrying the whole `tasks.md` would invite an attempt to work a
  sibling's slice inside a worktree that is not the sibling's — precisely the
  failure that unlocking edges on PASS exists to prevent.

- **A missing input is a loud failure, never an omitted section.** The assembler
  invents no context: a story with no findable task slice, or a requirement key
  the spec does not declare, raises `PromptAssemblyError` naming the offender,
  which fails the dispatch before a key is issued.

- **The two loops are named as what they are** (FR-012). The inner ralph
  contract is advisory fast feedback; the outer 002 ladder is the verdict. An
  agent that reads its own green gates as a pass is reading the prompt wrong, so
  the prompt says so in as many words.

The prompt carries no credential, no proxy URL and no worker path: the agent's
world is its worktree plus the environment the adapter built for it
(contracts/adapter.md). The branch name appears because the agent is standing on
it; nothing above the worktree does.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Sequence

from factory.mergequeue.models import CheckFailure, ObservedOutcome, QueueOutcome
from factory.usage.models import Termination
from factory.verify.criteria import HEADER_RE, mask_fences, section_end
from factory.verify.models import (
    DiffSizeRefusal,
    GateResult,
    GateStatus,
    HygieneViolation,
    OutputCheck,
    VerificationResult,
)
from factory.workgraph.models import WorkNode
from factory.workgraph.worktree import branch_name


#: The three authored documents a prompt is assembled from, under
#: `<specs_root>/<feature>/`. Named here because the assembler's refusals name
#: them: a caller that catches one is told which file to send the operator to
#: without re-deriving it from the message text (044 FR-001).
SPEC_DOCUMENT = "spec.md"
PLAN_DOCUMENT = "plan.md"
TASKS_DOCUMENT = "tasks.md"


class PromptAssemblyError(ValueError):
    """An input the assembler refuses to work around, and which one it was.

    Raised before dispatch, so the epic spends nothing on an attempt that would
    have been told to implement a story it was never shown. The message names
    the node and the missing requirement or story, because the fix is an edit to
    one line of one authored document.

    `document` names that document. It is structured rather than left implicit
    in the prose because a caller that reports this refusal early — 044's
    offline validate layer, and the roadmap preflight behind it — must send the
    operator to a file, and sniffing the file out of the sentence would be a
    second grammar to keep in step with this one.
    """

    def __init__(self, message: str, *, document: str) -> None:
        super().__init__(message)
        self.document = document


@dataclass(frozen=True)
class AttemptEvidence:
    """One prior attempt's wreckage, as the next attempt is shown it.

    `termination` and `result` are the two halves of what went wrong and they
    answer different questions: an attempt that hit its deadline left different
    wreckage than one that ran to the end and failed its gates. `result` is None
    only when an attempt ended before verification could record anything — the
    block then says so rather than implying a clean run.
    """

    termination: Termination
    result: VerificationResult | None = None


@dataclass(frozen=True)
class LandingEvidence:
    """One queue rejection, as the recovery attempt is shown it (US2, plan.md § US2).

    The classified `outcome` (CHECKS_FAILED or CONFLICT), the queue history in
    order, and — for a conflict — the conflicted file list the debugger persona
    must resolve (FR-006). The history is reproduced verbatim, the same discipline
    002's prior-attempt evidence already applies: an agent re-driven on a summary
    of what the queue rejected would debug the summary, not the rejection.

    US2: `failing_checks` carries the per-check evidence (name, run URL, log
    tail, note) for a `CHECKS_FAILED` recovery. Default `()` keeps CONFLICT and
    pre-spec histories untouched.

    US3: `base_unmoved` is True when the recovery sync merged in nothing (the
    target head had not moved). The recovery prompt then states that the base
    was not stale, refuting the stale-base hypothesis (FR-013). Default
    `False` keeps pre-spec and moved-base histories unchanged.
    """

    outcome: QueueOutcome
    queue_history: tuple[ObservedOutcome, ...]
    conflicted_files: tuple[str, ...] = ()
    failing_checks: tuple[CheckFailure, ...] = ()
    base_unmoved: bool = False


@dataclass(frozen=True)
class OperatorAnswer:
    """The operator's reply to a question the node asked (008-US2, FR-003).

    The question the agent asked under `## OPERATOR QUESTION` and the answer the
    operator typed back, carried together so the next attempt reads the exchange
    as a whole. Both travel verbatim — the same discipline 002's prior-attempt
    evidence applies — and both ride a dedicated section distinct from the
    verification-evidence section: the answer is the operator's voice, not a
    gate tail or judge feedback, and a reply that is not the operator's (a guess
    the agent might paste in) is what FR-012's hole is fenced against.
    """

    question_text: str
    answer_text: str


@dataclass(frozen=True)
class PeerMessage:
    """One routed peer message, as the prompt renders it (017-US1, FR-002/003).

    The sibling of `OperatorAnswer` for the peer channel. `body` is the
    message text with its header split off — verbatim (FR-003); `sender` is the
    sending node's id as the prompt names it; `sender_epic_id` travels so a
    cross-epic message (US4) is attributed where it came from, not only what it
    said; `reply` is `None` for a message being *delivered* and the reply text
    for an exchange being *replayed* to the asker (FR-003).

    Text here enters prompts and parks nodes and is unreadable by gates and
    judge (FR-005): the judge reads `AttemptEvidence`, this type never reaches
    one, and the guard test holds that line as the code changes.
    """

    message_id: str
    sender_epic_id: str
    sender_node_id: str
    body: str
    reply: str | None = None


# --- the fixed sections -------------------------------------------------------

_ROLE = """## Role and scope

You are one node of the software factory's epic `{epic_id}`. Your node is
`{node_id}`: it implements user story {story_key} of that epic, and nothing else.

You are running inside a git worktree checked out on branch
`{branch}`. The worktree and the branch are yours alone — no other node writes
to them, and you write nowhere else. Work only the task slice below; a sibling
story's tasks belong to a sibling node, in a worktree that is not this one."""

_INNER_LOOP = """## The inner loop (advisory)

This is how to make progress with fast feedback. It is advice about method, not
the verdict on your work:

1. Work the tasks in your slice in the order they are written; do not skip ahead
   and do not start work the slice does not name.
2. Test first — write the failing test before the code that makes it pass.
3. Run the repository's own gate commands (the ones its `factory.yaml` declares)
   after each task, and keep them green.
4. Commit once per task, so the work stays legible in history and salvageable at
   any moment.
5. Stop when the slice is done, or when it is blocked and you cannot proceed —
   and say which.

Green gates here mean you have fast feedback, not that you are finished."""

_OUTER_LOOP = """## The outer loop (authoritative)

Verification runs after you stop, and it is independent of you: the
deterministic gates are run again, the worktree diff is checked for real output,
and a judge scores that diff against this story's acceptance scenarios, which
were snapshotted before you started. That verdict is the only one that counts.
Your own assessment of success carries no weight, and nothing you write in your
final message is read as a result.

Do not weaken tests, skip gates, or narrow acceptance criteria to reach a green
run. A diff that passes by deleting the check fails the outer loop."""

_OPERATOR_QUESTION = """## If you are blocked, ask the operator

If you hit a fork in the road you cannot resolve on your own — a design choice
the spec does not settle, a dependency the constitution has not approved, a
constraint you cannot satisfy and cannot safely relax — you may ask the operator
one kind of question, in one place, and the bar is high.

There are two ways to ask, and you should prefer the in-flight ferry when you
can keep working until the answer arrives: write your question to the file
`$ATTEMPT_ARCHIVE/question` (the attempt's archive directory, never the worktree —
salvage would commit a file you left in the worktree), then poll for an answer in
`$ATTEMPT_ARCHIVE/answer`. The monitor loop ferries your question to the operator
and the answer back, so your process and context stay alive while the answer
travels and you pay seconds of resumed work rather than a fresh dispatch and a
cold re-read of the worktree. Do not wait forever: if no answer arrives within
a bounded window you set yourself (a few minutes is right for a blocking fork —
long enough for a human to read and type, short enough not to stall the attempt),
give up the ferry and fall back to the marker path below, so a question never
becomes a hang. Never write ferry files anywhere but `$ATTEMPT_ARCHIVE`.

When the ferry is not right — you have no work to keep doing, or the window has
elapsed with no answer — write your question as a level-2 heading, exactly
`## OPERATOR QUESTION`, in your final message, followed by its body. The body
names the fork you are at, the options you considered, and your lean; it is for a
genuinely blocking fork only — not a check you could run yourself, not a doubt
the spec or plan already answers, and not a preference. A marker is not a
verdict and never passes your node: the work you committed is salvaged either
way, and the gates and judge are not consulted for a question because there is
nothing to grade. Ask only when proceeding without the answer would be wrong;
otherwise keep working."""

_STANDARDS = """## Standards

Read `{standards}` in this worktree before you write code, and obey it.
It is the target repository's standing instruction to every node that touches
it."""

_STORY_PREAMBLE = (
    "The story you implement and the functional requirements it is verified\n"
    "against, exactly as the specification declares them:"
)

_PLAN_PREAMBLE = (
    "The epic's implementation plan, whole — the context every node of this\n"
    "epic shares:"
)

_SLICE_PREAMBLE = (
    "Your tasks, verbatim from the epic's `tasks.md`. This is your entire scope:"
)

_EVIDENCE_PREAMBLE = (
    "Earlier attempts at this node did not pass. Their evidence is reproduced\n"
    "verbatim, oldest first — the last block is the attempt just made. Read it\n"
    "as what actually happened, not as a summary of it:"
)

_NO_EVIDENCE_RECORDED = (
    "No verification evidence was recorded for this attempt: it ended before "
    "verification ran."
)

_LANDING_PREAMBLE = (
    "Your branch was rejected by the merge queue after its last verification. "
    "This is why the queue refused it, reproduced verbatim from the queue "
    "history — read it as what actually happened, not as a summary of it:"
)

#: US3: appended when the sync merged in nothing — the stale-base hypothesis is
#: refuted, so the agent should read the failure as its own content.
_BASE_UNMOVED_NOTICE = (
    "The sync merged in nothing: the target head had not moved, so the base "
    "was not stale. The failure lives in this branch's own content."
)

#: 008-US2: the operator's answer to the question your previous attempt asked,
#: reproduced verbatim. The question is quoted first (what you asked), then the
#: answer (what the operator decided). Neither is summarized — the operator's
#: wording is the decision, the way a gate tail is the failure (FR-003).
_ANSWER_PREAMBLE = (
    "You asked the operator a question on your previous attempt, and the "
    "operator answered. Both are reproduced verbatim — the question you "
    "asked, then the answer the operator gave. Read the answer as the "
    "operator's decision and proceed on it."
)

#: 017-US1: the peer channel's preambles. The incoming message is a peer's
#: words, verbatim (FR-002); the reply is the answer to the question *you*
#: asked a peer, verbatim (FR-003). Neither is the operator's voice and neither
#: is the ladder's — the preambles say to proceed on a message that answers the
#: asker's own question, and never to mistake one for a verdict (FR-005).
_PEER_MESSAGE_PREAMBLE = (
    "A peer node of this epic sent you the message below, reproduced "
    "verbatim. It is the peer's words, not the operator's and not the "
    "ladder's. If it answers a question your work depends on, proceed on it; "
    "if it asks you one and you can answer in your final message, answer it "
    "under your own `## OPERATOR QUESTION` heading addressed back with a "
    "`To:` line naming the node that asked."
)

_PEER_REPLY_PREAMBLE = (
    "You asked a peer node of this epic a question on your previous attempt, "
    "and the peer replied. The reply is reproduced verbatim — the question "
    "you asked, then the reply the peer gave. Read the reply as the peer's "
    "answer and proceed on it; it is not the operator's decision and not a "
    "verdict."
)

_NOTHING_FAILED_LOUDLY = (
    "No failing gate output and no judge feedback were recorded for this "
    "attempt."
)

#: 045-US3: why an output-check failure comes with neither a failing gate nor
#: judge feedback beside it. `judge_required` skips the judge the moment this
#: check fails, by design — so an attempt shown only gates and judge feedback
#: was shown nothing at all, which is what `_NOTHING_FAILED_LOUDLY` used to say
#: to four consecutive attempts failing on a byte-identical `has_diff: false`.
_OUTPUT_CHECK_PREAMBLE = (
    "The output check refused this attempt before the judge was asked, which is "
    "why no judge feedback follows. What it recorded is the whole reason the "
    "attempt failed:"
)

#: FR-004's failure: the node produced nothing, and a green suite over an
#: untouched worktree says so in no other way.
_NO_DIFF_AGAINST_BASE = (
    "There is no diff against the base ref: nothing was committed to the node "
    "branch and nothing was left uncommitted in the worktree. Whatever this "
    "attempt did, none of it is in the tree the factory reads."
)

#: The read scope's failure (R7): its proof of work is a declared artifact.
_ARTIFACTS_MISSING = (
    "The declared artifacts are missing or empty. Every path this node was "
    "expected to produce:"
)

#: 045 FR-001's failure, rendered as the list of what to remove. The rule beside
#: each path is the actionable half: "which rule refused this?" is the question
#: the next attempt has to answer before it can shrink its diff.
_HYGIENE_REFUSED = (
    "The diff carries paths it may not carry, so it was refused rather than "
    "judged. Every offending path, with the rule that refused it — take these "
    "out of the diff:"
)

#: 045 FR-003's failure. Named files rather than a bare total, because "your
#: diff is 2.1 MB" starts a hunt that "`.ergane/homes/chat.json` is 1.4 MB"
#: ends. The wording stays clear of this component's forbidden vocabulary
#: (`tests/test_final_sweep.py`, D-021): a diff too large for one prompt is a
#: judgeability limit, and nothing here is a spending control.
_SIZE_REFUSED = (
    "The diff is larger than the judge may be shown, so it was refused unread "
    "rather than judged on an abridged copy. Its total, the limit it ran past, "
    "and the files that account for most of it, biggest first:"
)

#: The reachable residue: `decide_passed` refuses a write scope the persona
#: registry never defined, and records nothing else about it. Silence there
#: would be this story's own defect one branch further in.
_OUTPUT_CHECK_UNEXPLAINED = (
    "The check recorded no reason of a shape this prompt knows how to quote, "
    "which usually means the node ran under a write scope the persona registry "
    "does not define. The record itself is in the verification store for this "
    "attempt."
)

#: 084 FR-007. What a `DIRTIED_WORKTREE` gate has to be told about, and why the
#: paths come with it. The gate exited 0, so its own tail says the run was fine
#: and reads as evidence that nothing went wrong; the refusal is entirely in a
#: set of paths that lived only on `GateResult.worktree_writes` until this
#: story rendered them. The wording points at the gate command rather than at
#: the code the gate measured, because that is where the fix is — an agent
#: shown a green log under a red verdict will otherwise go looking in its own
#: work. It deliberately does not mention declaring the writes in a manifest:
#: the config gate parses a node's manifest with the worker's installed parser
#: rather than the worktree's, so advice to declare a key an older worker does
#: not know turns one refusal into a `CONFIG_ERROR` in 0.0s before any gate
#: runs (`factory.yaml:38-42` records 020/US1 dying four times to prove it).
_GATE_WROTE_INTO_THE_WORKTREE = (
    "changed the node worktree while it ran, and the judge's patch is assembled "
    "from that worktree afterwards — so this gate edited the evidence it was "
    "scored on, which is why it did not pass despite its exit code. Fix the "
    "gate command, not the code it measured. Every path it wrote:"
)

# --- section headings ---------------------------------------------------------

_STORY_HEADING = "## Story"
_PLAN_HEADING = "## Plan"
_SLICE_HEADING = "## Your task slice"
_EVIDENCE_HEADING = "## Prior attempt evidence"
_LANDING_HEADING = "## Landing rejection"
#: 008-US2: the dedicated section an operator's answer renders under (FR-003).
#: Distinct from `_EVIDENCE_HEADING` (the ladder's verdict) and from the agent's
#: own `## OPERATOR QUESTION` marker — the answer is neither the agent's question
#: nor the gates' verdict, so it has its own heading.
_ANSWER_HEADING = "## Operator answer"

#: 017-US1: the dedicated sections the peer channel delivers through (FR-002,
#: FR-003). Distinct from `_ANSWER_HEADING` (the operator's voice), from
#: `_EVIDENCE_HEADING` (the ladder's) and from the agent's own marker — a peer's
#: words are none of those, so they render under their own headings and the
#: two directions (incoming message, returning reply) are never confusable.
PEER_MESSAGE_HEADING = "## Peer message"
PEER_REPLY_HEADING = "## Peer reply"

# --- requirement keys ---------------------------------------------------------

#: A story key as the deriver mints it (`US1`); the number is what a heading
#: names, in the spec and in `tasks.md` alike.
_STORY_KEY_RE = re.compile(r"^US(\d+)$")

_FR_KEY_RE = re.compile(r"^FR-\d+$")

#: Any run of backticks, so a quoted gate tail can be fenced by something longer
#: than anything inside it — the tail travels verbatim or not at all.
_BACKTICKS_RE = re.compile(r"`+")


def build_attempt_prompt(
    *,
    node: WorkNode,
    epic_id: str,
    spec_text: str,
    plan_text: str,
    tasks_text: str,
    standards: str | None = None,
    prior_attempts: Sequence[AttemptEvidence] = (),
    landing_evidence: LandingEvidence | None = None,
    operator_answer: OperatorAnswer | None = None,
    peer_messages: Sequence[PeerMessage] = (),
) -> str:
    """Assemble one attempt's prompt (contracts/prompt-assembly.md § Prompt shape).

    Pure: the four texts, the optional standards *path* (not the document — the
    agent reads that in its own worktree, where `prepare_worktree` has already
    confirmed it exists), and the prior attempts already in workflow state are
    the whole input. Same inputs, same bytes.

    `landing_evidence` is the US2 recovery input: a queue rejection quoted into
    the attempt's prompt so the re-driven node is shown the outcome, the queue
    history and (for a conflict) the conflicted file list verbatim. Absent on a
    first dispatch, so an untouched graph assembles byte-identical prompts.

    `operator_answer` is 008-US2's return path: the question the previous
    attempt asked and the operator's verbatim answer, rendered under a
    dedicated section distinct from the verification-evidence section (FR-003).
    Absent unless the node was un-parked by an answer, so a question that
    expired (and re-entered the ladder as a FAIL) assembles no answer section —
    the operator never engaged, so there is nothing to carry.

    Raises `PromptAssemblyError` when the spec declares no section for one of the
    node's `requirement_keys`, or when `tasks.md` has no phase naming the node's
    story — the dispatch fails there, before a key is issued.
    """
    sections = _requirement_sections(node, spec_text)
    slice_text = _task_slice(node, tasks_text)

    parts = [
        _ROLE.format(
            epic_id=epic_id,
            node_id=node.id,
            story_key=node.story_key,
            branch=branch_name(epic_id, node.id),
        ),
        _INNER_LOOP,
        _OUTER_LOOP,
        _OPERATOR_QUESTION,
    ]
    if standards:
        parts.append(_STANDARDS.format(standards=standards))
    parts.append("\n\n".join([_STORY_HEADING, _STORY_PREAMBLE, *sections]))
    parts.append("\n\n".join([_PLAN_HEADING, _PLAN_PREAMBLE, plan_text.strip()]))
    parts.append("\n\n".join([_SLICE_HEADING, _SLICE_PREAMBLE, slice_text]))
    if landing_evidence is not None:
        parts.append(_landing_section(landing_evidence))
    if operator_answer is not None:
        parts.append(_answer_section(operator_answer))
    parts.extend(_peer_sections(peer_messages))
    if prior_attempts:
        parts.append(_evidence_section(prior_attempts))

    return "\n\n".join(parts) + "\n"


# --- the spec's own words (verbatim) ------------------------------------------


def _requirement_sections(node: WorkNode, spec_text: str) -> list[str]:
    """Each of the node's requirement keys as the spec wrote it, in node order.

    `requirement_keys` is the fence, fixed at derivation and identical to what
    the judge will later score against: the story plus the FRs it implements,
    and no sibling's business.
    """
    lines = spec_text.splitlines()
    in_code = mask_fences(lines)

    sections: list[str] = []
    seen: set[str] = set()
    for key in [node.story_key, *node.requirement_keys]:
        if key in seen:
            continue
        seen.add(key)
        sections.append(_requirement_text(node, key, lines, in_code))
    return sections


def _requirement_text(
    node: WorkNode, key: str, lines: Sequence[str], in_code: Sequence[bool]
) -> str:
    """One requirement's source text, or a refusal naming the key."""
    story = _STORY_KEY_RE.match(key)
    if story:
        text = _first_section(lines, in_code, _names_story(story.group(1)))
        if text is None:
            raise PromptAssemblyError(
                f"node '{node.id}': the specification declares no section for "
                f"user story {key}; an attempt cannot be told to implement a "
                "story it is not shown",
                document=SPEC_DOCUMENT,
            )
        return text

    if _FR_KEY_RE.match(key):
        text = _bullet(lines, in_code, key)
        if text is None:
            raise PromptAssemblyError(
                f"node '{node.id}': the specification declares no requirement "
                f"{key}, which this node was dispatched to implement",
                document=SPEC_DOCUMENT,
            )
        return text

    raise PromptAssemblyError(
        f"node '{node.id}': requirement key {key!r} is neither a user story "
        "(US<n>) nor a functional requirement (FR-<n>)",
        document=SPEC_DOCUMENT,
    )


def _names_story(number: str) -> Callable[[str], bool]:
    """Does this heading's text name user story `number`?

    Matched on the number the heading states, never on position: the spec's
    `### User Story 3 - ...` and `tasks.md`'s `## Phase 4: User Story 3 - ...`
    are the same story, and deleting a story renumbers neither.
    """
    pattern = re.compile(rf"\bUser Story\s+{number}(?!\d)")
    return lambda heading: pattern.search(heading) is not None


def _first_section_bounds(
    lines: Sequence[str], in_code: Sequence[bool], names: Callable[[str], bool]
) -> tuple[int, int] | None:
    """Where the first section whose heading `names` accepts starts and stops.

    Half-open, in line indices: `[start, end)`, `start` being the heading line
    itself. The section runs to the next heading at the same level or shallower,
    and the scan is fence-masked: a heading quoted inside a fenced block — the
    tasks template quotes its own — is text *about* a section, so it neither
    opens one nor ends the one it sits inside.

    Bounds rather than text, because two callers need two different things out
    of one scan. The assembler wants the words; 044's slice-coverage lint wants
    to know which lines of the whole document fell inside a slice and which fell
    outside every one. Cutting the text and then searching for it again would be
    a second answer to "where does this section stop", which is the duplication
    044 FR-004 exists to forbid.
    """
    for index, line in enumerate(lines):
        if in_code[index]:
            continue
        header = HEADER_RE.match(line)
        if header is None or not names(header.group(2)):
            continue
        return index, section_end(lines, in_code, index, level=len(header.group(1)))
    return None


def _first_section(
    lines: Sequence[str], in_code: Sequence[bool], names: Callable[[str], bool]
) -> str | None:
    """The first section whose heading `names` accepts, verbatim, or None."""
    bounds = _first_section_bounds(lines, in_code, names)
    if bounds is None:
        return None
    start, end = bounds
    return "\n".join(lines[start:end]).strip()


def _bullet(lines: Sequence[str], in_code: Sequence[bool], key: str) -> str | None:
    """One `- **FR-###**: ...` bullet with its continuation lines, verbatim.

    Verbatim rather than the criteria parser's normalized body: this text is
    quoted to the agent, and re-wrapping a requirement is the smallest possible
    version of paraphrasing one.
    """
    opener = re.compile(rf"^-\s+\*\*{re.escape(key)}\*\*:")
    for index, line in enumerate(lines):
        if in_code[index] or not opener.match(line):
            continue
        end = index + 1
        while (
            end < len(lines)
            and not in_code[end]
            and lines[end].strip()
            and lines[end][:1].isspace()
        ):
            end += 1
        return "\n".join(lines[index:end]).rstrip()
    return None


# --- the task slice (R9) ------------------------------------------------------


def task_slice_bounds(node: WorkNode, tasks_text: str) -> tuple[int, int]:
    """Which lines of `tasks.md` this node's slice is cut from, or a refusal.

    Half-open line indices into `tasks_text.splitlines()`, `start` being the
    phase heading itself. Public because the slice's *extent* is a fact about
    dispatch that a check running before dispatch needs: 044's slice-coverage
    lint answers "does this task line reach an agent, and which one" by asking
    where every slice begins and ends, and the only answer that cannot drift
    from dispatch is the one dispatch itself computes (044 FR-004).

    Raises `PromptAssemblyError` in exactly the two cases `_task_slice` does,
    with the same words — it is the same call.
    """
    story = _STORY_KEY_RE.match(node.story_key)
    if story is None:
        raise PromptAssemblyError(
            f"node '{node.id}': story key {node.story_key!r} is not a user story "
            "key (US<n>), so no task slice can be found for it",
            document=TASKS_DOCUMENT,
        )

    lines = tasks_text.splitlines()
    bounds = _first_section_bounds(
        lines, mask_fences(lines), _names_story(story.group(1))
    )
    if bounds is None:
        raise PromptAssemblyError(
            f"node '{node.id}': tasks.md declares no phase naming user story "
            f"{node.story_key}, so this node has no task slice to work (FR-006)",
            document=TASKS_DOCUMENT,
        )
    return bounds


def _task_slice(node: WorkNode, tasks_text: str) -> str:
    """The phase section of `tasks.md` whose heading names this node's story.

    The one input the grammar cannot make structural — a spec author can write a
    story and forget its phase — so it is the one input with an explicit failure
    rule: no findable slice, no dispatch.
    """
    start, end = task_slice_bounds(node, tasks_text)
    return "\n".join(tasks_text.splitlines()[start:end]).strip()


# --- landing rejection evidence (US2) -----------------------------------------


def _landing_section(evidence: LandingEvidence) -> str:
    """The recovery attempt's landing-rejection section (plan.md § US2).

    Names the classified outcome, then quotes the queue history in order, and —
    for a conflict — the conflicted file list the debugger persona must resolve
    (FR-006). History entries are rendered one per line; nothing is summarized or
    paraphrased (002's verbatim discipline, applied to the queue's word).

    US2: for `CHECKS_FAILED`, each failing check is quoted with its run URL and
    the verbatim fetched tail, or with the note that the log was unavailable.
    """
    blocks: list[str] = [_LANDING_HEADING, _LANDING_PREAMBLE]
    history = "\n".join(
        f"- {entry.at} {entry.outcome.value}" for entry in evidence.queue_history
    )
    blocks.append(f"Outcome: `{evidence.outcome.value}`\n\nQueue history:\n{history}")
    if evidence.failing_checks:
        check_blocks: list[str] = []
        for check in evidence.failing_checks:
            lines = [f"- **{check.name}**: {check.url}"]
            if check.log_tail:
                lines.append("  Failing log tail:")
                lines.extend(f"    {line}" for line in check.log_tail.splitlines())
            if check.note:
                lines.append(f"  {check.note}")
            check_blocks.append("\n".join(lines))
        blocks.append(
            "Failing required checks (name, run URL, and verbatim log tail):\n"
            + "\n".join(check_blocks)
        )
    if evidence.conflicted_files:
        files = "\n".join(f"- {name}" for name in evidence.conflicted_files)
        blocks.append(
            f"Conflicted files (resolve these conflict markers):\n{files}"
        )
    if evidence.base_unmoved:
        blocks.append(_BASE_UNMOVED_NOTICE)
    return "\n\n".join(blocks)


# --- operator answer (008-US2 FR-003) -----------------------------------------


def _answer_section(answer: OperatorAnswer) -> str:
    """The re-dispatch's operator-answer section (spec FR-003).

    The question the previous attempt asked and the operator's verbatim answer,
    under a heading distinct from the verification-evidence section. Both texts
    travel verbatim — the question is what the agent itself wrote, the answer is
    the operator's decision, and the agent must proceed on it (008 FR-010).
    """
    return "\n\n".join(
        [
            _ANSWER_HEADING,
            _ANSWER_PREAMBLE,
            f"Question:\n\n{_quote(answer.question_text)}",
            f"Answer:\n\n{_quote(answer.answer_text)}",
        ]
    )


# --- peer messages (017-US1 FR-002/FR-003) ------------------------------------


def _peer_message_section(message: PeerMessage) -> str:
    """One delivered peer message, verbatim, attributed (FR-002).

    The dedicated section the spec names: a peer's message is not an operator
    answer and not the ladder's evidence, so it renders under its own heading.
    The sender is named so the agent can address its reply back (FR-003); the
    body travels verbatim — a paraphrase would break the round trip the
    Independent Test asserts.
    """
    return "\n\n".join(
        [
            PEER_MESSAGE_HEADING,
            _PEER_MESSAGE_PREAMBLE,
            f"From: {message.sender_node_id} (epic {message.sender_epic_id}, "
            f"message {message.message_id})",
            f"Message:\n\n{_quote(message.body)}",
        ]
    )


def _peer_reply_section(message: PeerMessage) -> str:
    """One returned peer reply, verbatim, threaded (FR-003).

    The asker's side of the exchange: the message it asked and the reply the
    peer gave, rendered whole under the reply heading — the same shape the
    operator-answer section renders, for the peer's voice.
    """
    parts = [
        PEER_REPLY_HEADING,
        _PEER_REPLY_PREAMBLE,
    ]
    if message.reply is not None:
        parts.append(f"Your question:\n\n{_quote(message.body)}")
        parts.append(f"Reply:\n\n{_quote(message.reply)}")
    else:
        # A delivery and a reply share the type; a delivery with no reply yet
        # renders the message alone. Never reached by the caller that hands a
        # reply, but the section must not render an empty `Reply:` clause.
        parts.append(f"Message:\n\n{_quote(message.body)}")
    return "\n\n".join(parts)


def _peer_sections(messages: Sequence[PeerMessage]) -> list[str]:
    """Every buffered peer message for this attempt, arrival order.

    `reply is None` means the message is being *delivered* to this node
    (FR-002); a message carrying a reply is being *returned* to its asker
    (FR-003). One section each, in the order the routing buffered them.
    """
    sections: list[str] = []
    for message in messages:
        if message.reply is not None:
            sections.append(_peer_reply_section(message))
        else:
            sections.append(_peer_message_section(message))
    return sections


# --- prior failure evidence (002 FR-006) --------------------------------------


def _evidence_section(prior_attempts: Sequence[AttemptEvidence]) -> str:
    blocks = [
        _attempt_block(position, evidence)
        for position, evidence in enumerate(prior_attempts, start=1)
    ]
    return "\n\n".join([_EVIDENCE_HEADING, _EVIDENCE_PREAMBLE, *blocks])


def _attempt_block(position: int, evidence: AttemptEvidence) -> str:
    """One prior attempt: how it ended, what failed, and what the judge said.

    Failing gates only — a green gate's output is noise in a prompt whose whole
    job is to say what went wrong — and every tail is fenced by a run of
    backticks longer than any inside it, so quoting cannot swallow the quote.

    A gate that dirtied the worktree gets a second block beside its tail (084
    FR-007), because its tail cannot explain it: the command exited 0 and its
    output says so. The block sits inside the same loop and beside the same
    gate, so an attempt whose two gates each wrote different paths attributes
    each set to the command that wrote it — the whole point of attributing
    `worktree_writes` to a gate in the first place. It renders off the record's
    own field, so a gate that wrote nothing gains nothing: an empty fence under
    a heading is the noise this docstring's first sentence refuses.
    """
    result = evidence.result
    attempt = position if result is None else result.attempt

    head = f"### Attempt {attempt} — terminated `{evidence.termination.value}`"
    if result is None:
        return f"{head}\n\n{_NO_EVIDENCE_RECORDED}"

    parts = [f"{head}, verdict {result.verdict.value}"]
    for gate in result.gate_results:
        if gate.status is GateStatus.PASS:
            continue
        exited = "no exit code" if gate.exit_code is None else f"exit {gate.exit_code}"
        parts.append(
            f"Gate `{gate.name}` (`{gate.command}`) — {gate.status.value}, "
            f"{exited}:\n\n{_quote(gate.output_tail)}"
        )
        if gate.worktree_writes:
            parts.append(_gate_writes_block(gate))

    # Between the gates and the judge, because that is the order verification
    # produced it in (`workflow.py`: gates → check_output → judge_required).
    if not result.output_check.passed:
        parts.append(_output_check_block(result.output_check))

    judge = result.judge
    if judge is not None and judge.feedback.strip():
        parts.append(f"Judge — {judge.outcome.value}:\n\n{_quote(judge.feedback)}")

    if len(parts) == 1:
        parts.append(_NOTHING_FAILED_LOUDLY)
    return "\n\n".join(parts)


def _gate_writes_block(gate: GateResult) -> str:
    """What one gate wrote into the node worktree, quoted (084 FR-007).

    The gate is named again beside its command rather than left implied by
    position: two gates of one attempt can each carry writes, and "which
    command do I fix?" is the first question the next attempt has to answer.
    The paths are quoted the way a gate tail is — one per line, inside a fence —
    because a path is an instruction and a count is only a description.
    Straight off `gate.worktree_writes`, never re-derived here: the tree that
    was measured is gone by the time this renders, and a second opinion about
    it could only be a worse one.
    """
    listing = "\n".join(gate.worktree_writes)
    return (
        f"Gate `{gate.name}` (`{gate.command}`) {_GATE_WROTE_INTO_THE_WORKTREE}"
        f"\n\n{_quote(listing)}"
    )


def _output_check_block(check: OutputCheck) -> str:
    """What the output check refused, quoted rather than described (045 FR-005).

    The check is the only decider whenever it fails — `judge_required` skips the
    judge, correctly, so there is no second opinion to render — and before this
    block existed that made a failed check the one verdict the next attempt was
    never told. `033-ergane-install/us2` failed four times on a byte-identical
    `has_diff: false` and read "No failing gate output and no judge feedback
    were recorded" each time.

    Every recorded shape renders, and each renders its own evidence: an empty
    diff, missing artifacts, US1's offending paths with the rules that refused
    them, US2's total-limit-and-files. They compose rather than exclude, because
    `check_output` can record more than one of them for the same attempt and a
    block that stopped at the first would send the next attempt back for the
    second.

    Values come out of the record, never out of this module's constants — the
    limit especially. A refusal stored under a cap that has since moved has to
    be read under the cap it was refused by, which is why `DiffSizeRefusal`
    carries one at all.
    """
    reasons: list[str] = []

    if not check.has_diff:
        reasons.append(_NO_DIFF_AGAINST_BASE)

    if check.artifacts_present is False:
        declared = "\n".join(check.expected_artifacts) or "(none declared)"
        reasons.append(f"{_ARTIFACTS_MISSING}\n\n{_quote(declared)}")

    if check.hygiene_violations:
        reasons.append(
            f"{_HYGIENE_REFUSED}\n\n{_quote(_hygiene_listing(check.hygiene_violations))}"
        )

    if check.size_refusal is not None:
        reasons.append(
            f"{_SIZE_REFUSED}\n\n{_quote(_size_listing(check.size_refusal))}"
        )

    if not reasons:
        reasons.append(_OUTPUT_CHECK_UNEXPLAINED)

    head = f"Output check — FAILED, write scope `{check.write_scope}`:"
    return "\n\n".join([head, _OUTPUT_CHECK_PREAMBLE, *reasons])


def _hygiene_listing(violations: Sequence[HygieneViolation]) -> str:
    """One line per refused path, in the order the check recorded them."""
    return "\n".join(
        f"{violation.path} — {violation.rule}" for violation in violations
    )


def _size_listing(refusal: DiffSizeRefusal) -> str:
    """The refusal's own numbers: how far over, and what spent it.

    Bytes, the unit the cap is in — a file of forty very long lines can cost
    more of the budget than one of four hundred short ones, and a figure in the
    wrong unit sends the next attempt after the wrong file.
    """
    lines = [
        f"total: {refusal.total_bytes} bytes",
        f"limit: {refusal.limit_bytes} bytes",
    ]
    if refusal.largest_files:
        lines.append("largest files:")
        lines.extend(
            f"  {entry.path}: {entry.size_bytes} bytes"
            for entry in refusal.largest_files
        )
    return "\n".join(lines)


def _quote(text: str) -> str:
    """Fence `text` without altering a byte of it."""
    longest = max((len(run) for run in _BACKTICKS_RE.findall(text)), default=0)
    fence = "`" * max(3, longest + 1)
    body = text if text.endswith("\n") else text + "\n"
    return f"{fence}text\n{body}{fence}"
