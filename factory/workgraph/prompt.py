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

from factory.mergequeue.models import ObservedOutcome, QueueOutcome
from factory.usage.models import Termination
from factory.verify.criteria import HEADER_RE, mask_fences, section_end
from factory.verify.models import GateStatus, VerificationResult
from factory.workgraph.models import WorkNode
from factory.workgraph.worktree import branch_name


class PromptAssemblyError(ValueError):
    """An input the assembler refuses to work around, and which one it was.

    Raised before dispatch, so the epic spends nothing on an attempt that would
    have been told to implement a story it was never shown. The message names
    the node and the missing requirement or story, because the fix is an edit to
    one line of one authored document.
    """


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
    """

    outcome: QueueOutcome
    queue_history: tuple[ObservedOutcome, ...]
    conflicted_files: tuple[str, ...] = ()


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

Write your question as a level-2 heading, exactly `## OPERATOR QUESTION`, in your
final message, followed by its body. The body names the fork you are at, the
options you considered, and your lean; it is for a genuinely blocking fork only —
not a check you could run yourself, not a doubt the spec or plan already answers,
and not a preference. A marker is not a verdict and never passes your node: the
work you committed is salvaged either way, and the gates and judge are not
consulted for a question because there is nothing to grade. Ask only when
proceeding without the answer would be wrong; otherwise keep working."""

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

_NOTHING_FAILED_LOUDLY = (
    "No failing gate output and no judge feedback were recorded for this "
    "attempt."
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
                "story it is not shown"
            )
        return text

    if _FR_KEY_RE.match(key):
        text = _bullet(lines, in_code, key)
        if text is None:
            raise PromptAssemblyError(
                f"node '{node.id}': the specification declares no requirement "
                f"{key}, which this node was dispatched to implement"
            )
        return text

    raise PromptAssemblyError(
        f"node '{node.id}': requirement key {key!r} is neither a user story "
        "(US<n>) nor a functional requirement (FR-<n>)"
    )


def _names_story(number: str) -> Callable[[str], bool]:
    """Does this heading's text name user story `number`?

    Matched on the number the heading states, never on position: the spec's
    `### User Story 3 - ...` and `tasks.md`'s `## Phase 4: User Story 3 - ...`
    are the same story, and deleting a story renumbers neither.
    """
    pattern = re.compile(rf"\bUser Story\s+{number}(?!\d)")
    return lambda heading: pattern.search(heading) is not None


def _first_section(
    lines: Sequence[str], in_code: Sequence[bool], names: Callable[[str], bool]
) -> str | None:
    """The first section whose heading `names` accepts, verbatim, or None.

    The section runs to the next heading at the same level or shallower, and the
    scan is fence-masked: a heading quoted inside a fenced block — the tasks
    template quotes its own — is text *about* a section, so it neither opens one
    nor ends the one it sits inside.
    """
    for index, line in enumerate(lines):
        if in_code[index]:
            continue
        header = HEADER_RE.match(line)
        if header is None or not names(header.group(2)):
            continue
        end = section_end(lines, in_code, index, level=len(header.group(1)))
        return "\n".join(lines[index:end]).strip()
    return None


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


def _task_slice(node: WorkNode, tasks_text: str) -> str:
    """The phase section of `tasks.md` whose heading names this node's story.

    The one input the grammar cannot make structural — a spec author can write a
    story and forget its phase — so it is the one input with an explicit failure
    rule: no findable slice, no dispatch.
    """
    story = _STORY_KEY_RE.match(node.story_key)
    if story is None:
        raise PromptAssemblyError(
            f"node '{node.id}': story key {node.story_key!r} is not a user story "
            "key (US<n>), so no task slice can be found for it"
        )

    lines = tasks_text.splitlines()
    text = _first_section(lines, mask_fences(lines), _names_story(story.group(1)))
    if text is None:
        raise PromptAssemblyError(
            f"node '{node.id}': tasks.md declares no phase naming user story "
            f"{node.story_key}, so this node has no task slice to work (FR-006)"
        )
    return text


# --- landing rejection evidence (US2) -----------------------------------------


def _landing_section(evidence: LandingEvidence) -> str:
    """The recovery attempt's landing-rejection section (plan.md § US2).

    Names the classified outcome, then quotes the queue history in order, and —
    for a conflict — the conflicted file list the debugger persona must resolve
    (FR-006). History entries are rendered one per line; nothing is summarized or
    paraphrased (002's verbatim discipline, applied to the queue's word).
    """
    blocks: list[str] = [_LANDING_HEADING, _LANDING_PREAMBLE]
    history = "\n".join(
        f"- {entry.at} {entry.outcome.value}" for entry in evidence.queue_history
    )
    blocks.append(f"Outcome: `{evidence.outcome.value}`\n\nQueue history:\n{history}")
    if evidence.conflicted_files:
        files = "\n".join(f"- {name}" for name in evidence.conflicted_files)
        blocks.append(
            f"Conflicted files (resolve these conflict markers):\n{files}"
        )
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

    judge = result.judge
    if judge is not None and judge.feedback.strip():
        parts.append(f"Judge — {judge.outcome.value}:\n\n{_quote(judge.feedback)}")

    if len(parts) == 1:
        parts.append(_NOTHING_FAILED_LOUDLY)
    return "\n\n".join(parts)


def _quote(text: str) -> str:
    """Fence `text` without altering a byte of it."""
    longest = max((len(run) for run in _BACKTICKS_RE.findall(text)), default=0)
    fence = "`" * max(3, longest + 1)
    body = text if text.endswith("\n") else text + "\n"
    return f"{fence}text\n{body}{fence}"
