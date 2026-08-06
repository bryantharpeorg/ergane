"""The one place a model is allowed to have an opinion, and the fence around it.

Everything else in verification is deterministic; the judge is the single bounded
LLM edge (constitution IV), reached as one chat completion rather than an agent
(R4). It is bounded in four directions, and each bound is here because without it
this module is a way to talk the factory into a false PASS:

- **The criteria go in verbatim.** Requirement bodies and every dispatched
  scenario arrive uncut, tagged with the ids the response must echo back
  (FR-003). Criteria are the standard being applied; paraphrasing one would move
  the goalposts as silently as a hallucinating parser upstream.
- **The diff is capped, and a cap is not a deletion.** Over `DIFF_INPUT_LIMIT`
  the diff is truncated per file in proportion to what each file contributed,
  keeping every file's head and tail behind an explicit
  `[... N lines truncated ...]` marker, with the file list always complete (R6).
  The markers are what let the judge read an elision as an elision; an unmarked
  cut turns a large, correct node into a confident FAIL.
- **The response is parsed strictly, and the stricter reading wins.** Every
  dispatched scenario must appear exactly once, and a `verdict: pass` next to a
  `pass: false` finding is a RETRY (R5). Holistic passing is what FR-003 exists
  to prohibit, and `parse_verdict` is where the prohibition is enforced.
- **Garbage becomes neither a pass nor unbounded spend.** A malformed response
  consumes one judge attempt and asks for another; on the last attempt it becomes
  FAIL carrying the parse failure as feedback (SC-002, SC-003).

Two things this module deliberately does not decide. It never falls back to a
gates-only verdict: a backend that stays down through `MAX_HTTP_ATTEMPTS` raises
`JudgeUnavailableError`, and whether that becomes a PASS with `judge_unavailable`
set belongs to the verdict composer. And it never reads a credential from the
environment — the per-attempt virtual key component 1 minted for persona `judge`
arrives as an argument, so the master key sitting in the same worker process has
no path into these bytes (FR-009, constitution V).

Prompt assembly, diff preparation and verdict parsing are pure functions, split
out from the one coroutine that does I/O so the interesting half is testable
without a proxy at all.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any, Sequence

import httpx

from factory.verify.models import (
    CriteriaSet,
    JudgeOutcome,
    JudgeScenarioFinding,
    JudgeVerdict,
    VerificationConfig,
)

#: Diff bytes the judge may be shown (R6). ~15k tokens: comfortable beside the
#: criteria and instructions in any cheap-tier model's context.
DIFF_INPUT_LIMIT = 60 * 1024

#: Judge invocations per verification cycle are 1 + this (SC-003). Sourced from
#: `VerificationConfig` rather than restated — that field is the knob an operator
#: edits, and a second literal here would let tuning it silently do nothing.
DEFAULT_MAX_JUDGE_RETRIES: int = VerificationConfig().max_judge_retries

#: HTTP attempts for one judge invocation. Bounded low on purpose: this retries a
#: proxy that is restarting, not a model that is thinking. A backend still down
#: after three tries is an outage, and the ladder has better things to do than
#: wait it out.
MAX_HTTP_ATTEMPTS = 3

#: Base of the exponential pause between HTTP attempts; tests pass 0.0.
DEFAULT_RETRY_BACKOFF_S = 0.5

#: Generous, because a judge model on a cold local backend can be slow, but not
#: unbounded — the activity's own timeout should never be the first thing to fire.
DEFAULT_TIMEOUT_S = 120.0

#: Cap on the verdict object the judge writes back (R4). A verdict that needs
#: more than this is not a verdict.
MAX_OUTPUT_TOKENS = 2000

COMPLETIONS_PATH = "/chat/completions"

#: Statuses worth trying again: a proxy mid-restart, a rate limit, a wedged
#: upstream. Everything else (401 on a rejected key, 400 on a bad body) will be
#: refused just as fast three times as once.
RETRYABLE_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})

#: A file smaller than this is carried whole even when the diff is over cap: it
#: costs almost nothing, and a `[... 2 lines truncated ...]` marker inside a
#: five-line file is pure noise where the judge needs signal.
SMALL_FILE_FLOOR = 2 * 1024

_REDACTED = "<redacted>"

_VERDICT_WORDS: dict[str, JudgeOutcome] = {
    "pass": JudgeOutcome.PASS,
    "retry": JudgeOutcome.RETRY,
    "fail": JudgeOutcome.FAIL,
}

#: How harsh each outcome is, so "the stricter reading wins" is a `max`.
_STRICTNESS: dict[JudgeOutcome, int] = {
    JudgeOutcome.PASS: 0,
    JudgeOutcome.RETRY: 1,
    JudgeOutcome.FAIL: 2,
}

SYSTEM_PROMPT = """You are a verification judge in an automated software factory.

You are given a requirement, its acceptance scenarios, and the diff a coding \
agent produced for one node of work. Score the diff against each acceptance \
scenario individually. A scenario passes only if the diff demonstrably satisfies \
every one of its Given/When/Then steps; if the evidence is not in the diff, the \
scenario does not pass. Never pass a scenario because the change looks \
reasonable overall.

Respond with ONLY this JSON object, and nothing before or after it:

{
  "verdict": "pass" | "retry" | "fail",
  "scenarios": [
    {"scenario": "<the exact scenario id you were given>",
     "pass": true,
     "reasoning": "<what in the diff satisfies or fails the steps>"}
  ],
  "feedback": "<actionable text that names every failing scenario>"
}

Rules:
- Include exactly one entry per scenario id you were given: no extras, none
  missing, and reuse the ids character-for-character.
- "pass" must be a JSON boolean, and every entry must carry "reasoning".
- Use "pass" only when every scenario passed; "retry" when the work is close and
  your feedback would let the next attempt finish it; "fail" when the diff is not
  on the way to satisfying the requirement.
- The diff may be abridged. A "[... N lines truncated ...]" marker means those
  lines were elided to fit an input limit, not that the agent omitted them; say
  so in your reasoning rather than failing a scenario for evidence inside an
  elision.
"""

#: Shown instead of a diff when there is none. The empty-diff verdict belongs to
#: the output check (FR-004), which has already run by the time the judge is
#: consulted; here it is only context.
EMPTY_DIFF_NOTE = "(the node's worktree diff is empty)"

TRUNCATION_NOTICE = (
    f"This diff is larger than the {DIFF_INPUT_LIMIT}-byte judge input limit and "
    "has been abridged: each file kept its head and its tail, in proportion to "
    "how much of the diff it was, and every elision is marked "
    "`[... N lines truncated ...]`. The file list above is complete and was not "
    "truncated. Elided lines are missing from this prompt, not from the work.\n\n"
)

_SECTION_SPLIT_RE = re.compile(r"(?m)^(?=diff --git )")
_FILE_HEADER_RE = re.compile(r"^diff --git a/(\S+) b/(\S+)")
_FENCE_RE = re.compile(r"```[^\n`]*\n(.*?)```", re.DOTALL)


class JudgeParseError(ValueError):
    """The judge answered, but not with a verdict this module can read.

    Carries the reason in its message because that message is what the next
    judge attempt is shown (R5) — the same discipline the criteria parser
    follows: name the offender, so the retry has something to act on.
    """


class JudgeUnavailableError(RuntimeError):
    """The judge could not be reached — an outage, not a verdict.

    Deliberately not a FAIL: charging a node's attempt to someone else's downtime
    is the mirror image of the false PASS this component exists to prevent. The
    caller maps it to `JUDGE_UNAVAILABLE` and composes a gates-only verdict with
    the flag set (contracts/judge.md).
    """


@dataclass(frozen=True)
class PreparedDiff:
    """A diff sized to the judge's input cap, and whether that cost anything."""

    text: str
    truncated: bool


@dataclass(frozen=True)
class JudgePrompt:
    """The two messages of one judge invocation, plus what the diff cost.

    `truncated_input` rides along to the verdict and into the evidence store, so
    an operator reading a stored row can tell a judgment made on the whole diff
    from one made on an abridgement.
    """

    messages: list[dict[str, str]]
    truncated_input: bool


# --- prompt assembly (pure) ---------------------------------------------------


def dispatched_scenario_ids(criteria: CriteriaSet) -> list[str]:
    """Every scenario id this node was dispatched against, in spec order.

    The response is matched against exactly this list, and the order it is in is
    the order findings come back in — evidence rows and escalation messages read
    in the order the spec declares them, not in whatever order a model answered.
    """
    return [
        scenario.scenario_id
        for requirement in criteria.requirements
        for scenario in requirement.scenarios
    ]


def build_prompt(
    criteria: CriteriaSet,
    diff_text: str,
    *,
    prior_feedback: str | None = None,
) -> JudgePrompt:
    """Assemble the judge's system + user messages (contracts/judge.md).

    Sections arrive in one order and it is not cosmetic: the requirement and its
    scenarios establish the standard before the diff being measured against it
    shows up, prior feedback says what the last attempt got wrong (FR-006), and
    the diff goes last because it is the only part that may have been cut.

    Raises `ValueError` when the node has no scenarios: an empty dispatched list
    would parse back as "every scenario passed", handing out a free pass on a
    node nobody scored. FR-only nodes are gates-plus-output-check by design.
    """
    scenario_ids = dispatched_scenario_ids(criteria)
    if not scenario_ids:
        raise ValueError(
            f"{criteria.spec_ref}: no acceptance scenarios were dispatched, so "
            "there is nothing for the judge to score — verify this node on its "
            "gates and output check instead"
        )

    prepared = prepare_diff(diff_text)

    blocks: list[str] = [
        "# Requirements under verification",
        "",
        f"Feature: {criteria.feature}",
        f"Spec ref: {criteria.spec_ref}",
    ]
    for requirement in criteria.requirements:
        heading = f"## {requirement.key}"
        if requirement.title:
            heading += f" — {requirement.title}"
        if requirement.priority:
            heading += f" (Priority: {requirement.priority})"
        blocks += ["", heading, "", requirement.body]

    blocks += [
        "",
        "# Acceptance scenarios",
        "",
        "Score each of these on its own and echo its id exactly as written here.",
    ]
    for requirement in criteria.requirements:
        for scenario in requirement.scenarios:
            blocks += ["", f"## {scenario.scenario_id}", "", scenario.raw_text]

    if prior_feedback:
        blocks += [
            "",
            "# Feedback on the previous attempt",
            "",
            "This node has already been rejected once. What was said then, verbatim:",
            "",
            prior_feedback,
        ]

    blocks += ["", "# Diff produced by the node", "", prepared.text]

    return JudgePrompt(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "\n".join(blocks)},
        ],
        truncated_input=prepared.truncated,
    )


# --- diff bounds (pure) -------------------------------------------------------


@dataclass(frozen=True)
class _Section:
    """One file's slice of a unified diff, with its own stat line."""

    path: str | None
    text: str
    added: int
    removed: int

    @property
    def size(self) -> int:
        return len(self.text.encode("utf-8"))


def prepare_diff(diff_text: str, *, limit: int = DIFF_INPUT_LIMIT) -> PreparedDiff:
    """Fit `diff_text` under `limit`, disclosing anything that had to go (R6).

    Under the cap the diff is passed through untouched behind its file list. Over
    it, each file gets a share of the budget in proportion to its size — with a
    floor so small files are carried whole — and spends that share on its head
    and its tail, because a half-finished implementation is usually at the end of
    a file and head-only truncation would hide exactly that.
    """
    if not diff_text.strip():
        return PreparedDiff(text=EMPTY_DIFF_NOTE, truncated=False)

    preamble, sections = _split_sections(diff_text)
    if not sections:
        # Not git's output (or one raw patch body): treat the whole thing as a
        # single unnamed section so the cap still applies to it.
        sections = [_Section(None, preamble, *_count_changes(preamble))]
        preamble = ""

    listing = _file_listing(sections)
    whole = listing + preamble + "".join(section.text for section in sections)
    if len(whole.encode("utf-8")) <= limit:
        return PreparedDiff(text=whole, truncated=False)

    # The listing and any preamble are never abridged — the point of the listing
    # is that a file cut down to a stub is still visible as a file that changed.
    head_block = listing + TRUNCATION_NOTICE + preamble
    allowance = max(limit - len(head_block.encode("utf-8")), 0)
    grants = _allocate([section.size for section in sections], allowance)

    rendered = [
        _render_section(section, grant) for section, grant in zip(sections, grants)
    ]
    return PreparedDiff(
        text=head_block + "".join(rendered),
        truncated=any(
            rendered_text != section.text
            for rendered_text, section in zip(rendered, sections)
        ),
    )


def _split_sections(diff_text: str) -> tuple[str, list[_Section]]:
    """Split a unified diff into its leading text and one section per file."""
    preamble = ""
    sections: list[_Section] = []

    for chunk in _SECTION_SPLIT_RE.split(diff_text):
        if not chunk:
            continue
        header = _FILE_HEADER_RE.match(chunk)
        if header is None:
            # Only the leading chunk can lack a `diff --git` header; git emits
            # nothing there, but a caller may have prefixed a summary.
            preamble += chunk
            continue
        sections.append(_Section(header.group(1), chunk, *_count_changes(chunk)))

    return preamble, sections


def _count_changes(text: str) -> tuple[int, int]:
    """`(added, removed)` content lines, ignoring the `---`/`+++` file headers."""
    added = removed = 0
    for line in text.splitlines():
        if line.startswith(("+++", "---")):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            removed += 1
    return added, removed


def _file_listing(sections: Sequence[_Section]) -> str:
    """The always-complete file list and stat summary that heads the diff."""
    named = [section for section in sections if section.path]
    if not named:
        return ""
    lines = [f"Changed files ({len(named)}):"]
    lines += [
        f"  {section.path} | +{section.added} -{section.removed}" for section in named
    ]
    return "\n".join(lines) + "\n\n"


def _allocate(sizes: Sequence[int], allowance: int) -> list[int]:
    """Split `allowance` bytes across sections in proportion to their sizes.

    Smallest first, so a file that fits inside its share hands the surplus to the
    files that did not — which is what keeps a 5-line touch-up whole instead of
    gutting a 2000-line rewrite to carry it in triplicate. `SMALL_FILE_FLOOR`
    lifts the smallest files over the line, scaled down when there are so many
    files that the floor could not be paid for all of them.
    """
    floor = min(SMALL_FILE_FLOOR, allowance // len(sizes)) if sizes else 0

    grants = [0] * len(sizes)
    remaining = max(allowance, 0)
    remaining_size = sum(sizes)

    for index in sorted(range(len(sizes)), key=lambda i: sizes[i]):
        size = sizes[index]
        share = (remaining * size) // remaining_size if remaining_size else 0
        # Bounded by what is left, so the grants can never sum past the whole.
        grant = min(size, max(share, floor), remaining)
        grants[index] = grant
        remaining -= grant
        remaining_size -= size

    return grants


def _render_section(section: _Section, grant: int) -> str:
    """One file's diff, whole if it fits in `grant` bytes and head+tail if not."""
    if section.size <= grant:
        return section.text

    lines = section.text.splitlines(keepends=True)
    # The marker's own bytes come out of the grant: an elision that pushed the
    # prompt over the input limit would be a limit that does not hold.
    available = max(grant - len(_marker(len(lines)).encode("utf-8")), 0)
    head_allowance = available // 2

    # Always keep the `diff --git` line, whatever is left: a section that lost
    # its header is a change the judge cannot attribute to a file.
    head = 1
    used = len(lines[0].encode("utf-8"))
    while head < len(lines):
        line_size = len(lines[head].encode("utf-8"))
        if used + line_size > head_allowance:
            break
        used += line_size
        head += 1

    tail = 0
    tail_allowance = available - used
    while head + tail < len(lines):
        line_size = len(lines[-(tail + 1)].encode("utf-8"))
        if line_size > tail_allowance:
            break
        tail_allowance -= line_size
        tail += 1

    dropped = len(lines) - head - tail
    if dropped <= 0:
        return section.text

    return (
        "".join(lines[:head])
        + _marker(dropped)
        + "".join(lines[len(lines) - tail :] if tail else [])
    )


def _marker(dropped: int) -> str:
    return f"[... {dropped} lines truncated ...]\n"


# --- strict verdict parsing (pure) --------------------------------------------


def parse_verdict(
    content: str,
    scenario_ids: Sequence[str],
    *,
    judge_attempt: int,
    model_alias: str,
    truncated_input: bool = False,
) -> JudgeVerdict:
    """Read the judge's response, or refuse it (R5, contracts/judge.md).

    Strict in both directions: the object is accepted raw or inside exactly one
    fenced block and nowhere else, and every dispatched scenario must be scored
    exactly once with a real boolean and real reasoning. Then the claimed overall
    verdict is cross-checked against the findings and the stricter of the two
    wins — which is the whole of FR-003's prohibition on holistic passing.

    Raises `JudgeParseError` naming what was wrong; the caller turns that into a
    judge retry or, on the last attempt, a FAIL carrying it as feedback.
    """
    ids = list(scenario_ids)
    if not ids:
        raise ValueError(
            "parse_verdict was given no dispatched scenarios: an empty list "
            "would read every response as a unanimous pass"
        )

    payload = _extract_object(content)

    for key in ("verdict", "scenarios", "feedback"):
        if key not in payload:
            raise JudgeParseError(
                f"the judge's response is missing the required key {key!r}"
            )

    claimed = payload["verdict"]
    word = claimed.strip().lower() if isinstance(claimed, str) else None
    if word not in _VERDICT_WORDS:
        raise JudgeParseError(
            f"the judge returned the verdict {claimed!r}; expected one of "
            "'pass', 'retry', 'fail'"
        )

    feedback = payload["feedback"]
    if not isinstance(feedback, str):
        raise JudgeParseError(
            f"the judge's feedback is a {type(feedback).__name__}, not text"
        )

    findings = _parse_findings(payload["scenarios"], ids)
    implied = (
        JudgeOutcome.PASS
        if all(finding.passed for finding in findings)
        else JudgeOutcome.RETRY
    )
    outcome = max(_VERDICT_WORDS[word], implied, key=lambda o: _STRICTNESS[o])

    return JudgeVerdict(
        outcome=outcome,
        findings=findings,
        feedback=feedback,
        judge_attempt=judge_attempt,
        truncated_input=truncated_input,
        model_alias=model_alias,
    )


def _extract_object(content: str) -> dict[str, Any]:
    """The one JSON object in the response, or a refusal to guess which it was."""
    stripped = content.strip()
    if not stripped:
        raise JudgeParseError("the judge returned an empty response")

    blocks = _FENCE_RE.findall(content)
    if len(blocks) > 1:
        raise JudgeParseError(
            f"the judge returned {len(blocks)} fenced blocks; exactly one JSON "
            "verdict object was asked for, and guessing which one is the verdict "
            "is how a stale draft gets scored"
        )

    candidate = blocks[0] if blocks else stripped
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise JudgeParseError(
            f"the judge's response is not the JSON verdict object: {exc}"
        ) from exc

    if not isinstance(payload, dict):
        raise JudgeParseError(
            f"the judge returned a JSON {type(payload).__name__}, not the verdict object"
        )
    return payload


def _parse_findings(
    raw: Any, ids: Sequence[str]
) -> list[JudgeScenarioFinding]:
    """Exactly one finding per dispatched scenario, in dispatch order."""
    if not isinstance(raw, list):
        raise JudgeParseError(
            f"the judge's 'scenarios' is a {type(raw).__name__}, not a list of "
            "per-scenario findings"
        )

    scored: dict[str, JudgeScenarioFinding] = {}
    for position, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise JudgeParseError(f"scenario finding #{position} is not an object")

        scenario = item.get("scenario")
        if not isinstance(scenario, str):
            raise JudgeParseError(f"scenario finding #{position} names no scenario")
        if scenario not in ids:
            raise JudgeParseError(
                f"the judge scored {scenario!r}, which this node was not "
                f"dispatched against; the dispatched scenarios are {', '.join(ids)}"
            )
        if scenario in scored:
            raise JudgeParseError(
                f"the judge scored {scenario!r} twice; two answers for one "
                "scenario is not an answer"
            )

        passed = item.get("pass")
        if not isinstance(passed, bool):
            raise JudgeParseError(
                f"{scenario!r} was scored {passed!r}, which is not a JSON boolean"
            )

        reasoning = item.get("reasoning")
        if not isinstance(reasoning, str) or not reasoning.strip():
            raise JudgeParseError(
                f"{scenario!r} was scored without reasoning; a verdict nobody can "
                "review is not evidence"
            )

        scored[scenario] = JudgeScenarioFinding(
            scenario=scenario, passed=passed, reasoning=reasoning
        )

    missing = [scenario_id for scenario_id in ids if scenario_id not in scored]
    if missing:
        raise JudgeParseError(
            f"the judge did not score {', '.join(missing)}; every dispatched "
            "scenario must be scored individually"
        )

    return [scored[scenario_id] for scenario_id in ids]


# --- the call itself ----------------------------------------------------------


async def run_judge(
    criteria: CriteriaSet,
    diff_text: str,
    *,
    proxy_url: str,
    virtual_key: str,
    model_alias: str,
    prior_feedback: str | None = None,
    judge_attempt: int = 1,
    max_judge_retries: int = DEFAULT_MAX_JUDGE_RETRIES,
    transport: httpx.AsyncBaseTransport | None = None,
    timeout: float = DEFAULT_TIMEOUT_S,
    retry_backoff_s: float = DEFAULT_RETRY_BACKOFF_S,
) -> JudgeVerdict:
    """Score `diff_text` against `criteria` with one bounded chat completion.

    `virtual_key` is the per-attempt key component 1 minted for persona `judge`,
    and `model_alias` is that persona's registry alias — both arguments, because
    this module neither reads credentials from the environment nor knows a model
    name (constitution V, VII).

    A response this module cannot read is not an error: it comes back as a
    RETRY verdict carrying the parse failure as feedback, or — once
    `judge_attempt` has reached `1 + max_judge_retries` — as FAIL, because
    garbage never becomes a pass and never becomes unbounded spend.

    Raises `JudgeUnavailableError` when the proxy could not be reached, and
    `ValueError` when the node has no scenarios to score.
    """
    prompt = build_prompt(criteria, diff_text, prior_feedback=prior_feedback)

    content = await _complete(
        prompt,
        proxy_url=proxy_url,
        virtual_key=virtual_key,
        model_alias=model_alias,
        transport=transport,
        timeout=timeout,
        retry_backoff_s=retry_backoff_s,
    )

    try:
        return parse_verdict(
            content,
            dispatched_scenario_ids(criteria),
            judge_attempt=judge_attempt,
            model_alias=model_alias,
            truncated_input=prompt.truncated_input,
        )
    except JudgeParseError as exc:
        exhausted = judge_attempt >= 1 + max_judge_retries
        return JudgeVerdict(
            outcome=JudgeOutcome.FAIL if exhausted else JudgeOutcome.RETRY,
            findings=[],
            feedback=_malformed_feedback(exc, exhausted=exhausted),
            judge_attempt=judge_attempt,
            truncated_input=prompt.truncated_input,
            model_alias=model_alias,
        )


def _malformed_feedback(exc: JudgeParseError, *, exhausted: bool) -> str:
    """What the next attempt — or the evidence store — is told went wrong."""
    tail = (
        "No judge attempts remain, so this counts as a failure rather than a pass."
        if exhausted
        else "Answer again with only the JSON verdict object described above."
    )
    return f"The judge's response could not be read: {exc} {tail}"


async def _complete(
    prompt: JudgePrompt,
    *,
    proxy_url: str,
    virtual_key: str,
    model_alias: str,
    transport: httpx.AsyncBaseTransport | None,
    timeout: float,
    retry_backoff_s: float,
) -> str:
    """POST the one completion and return the assistant's text (R4).

    Retries a briefly unreachable backend and then gives up: this is the only
    loop in the judge path, and it is bounded by `MAX_HTTP_ATTEMPTS` so an
    outage cannot quietly become an unbounded spend or an unbounded wait.
    """
    body: dict[str, Any] = {
        "model": model_alias,
        "temperature": 0,
        "max_tokens": MAX_OUTPUT_TOKENS,
        "messages": prompt.messages,
    }

    reason = "no request was attempted"
    async with httpx.AsyncClient(
        base_url=proxy_url.rstrip("/"),
        headers={"Authorization": f"Bearer {virtual_key}"},
        transport=transport,
        timeout=timeout,
    ) as client:
        for attempt in range(1, MAX_HTTP_ATTEMPTS + 1):
            try:
                response = await client.post(COMPLETIONS_PATH, json=body)
            except httpx.HTTPError as exc:
                reason = _scrub(f"{type(exc).__name__}: {exc}", virtual_key)
            else:
                if response.status_code < 400:
                    return _assistant_content(response)
                reason = f"HTTP {response.status_code}: {_proxy_message(response, virtual_key)}"
                if response.status_code not in RETRYABLE_STATUSES:
                    break

            if attempt < MAX_HTTP_ATTEMPTS:
                await asyncio.sleep(retry_backoff_s * 2 ** (attempt - 1))

    # Outside the client and outside every `except`, so no chained exception can
    # carry a credential out with it (FR-009, SC-004).
    raise JudgeUnavailableError(f"the judge's chat completion did not succeed: {reason}")


def _assistant_content(response: httpx.Response) -> str:
    """The assistant message of a chat completion, or an outage.

    A 200 without a message is the backend breaking its own protocol, not the
    judge answering badly — charging it to the judge-retry budget would spend a
    node's attempts on someone else's failure.
    """
    try:
        payload: Any = response.json()
    except ValueError:
        raise JudgeUnavailableError(
            "the proxy answered the chat completion with a non-JSON body"
        ) from None

    choices = payload.get("choices") if isinstance(payload, dict) else None
    first = choices[0] if isinstance(choices, list) and choices else None
    message = first.get("message") if isinstance(first, dict) else None
    content = message.get("content") if isinstance(message, dict) else None

    if not isinstance(content, str):
        raise JudgeUnavailableError(
            "the proxy returned a chat completion with no assistant message"
        )
    return content


def _proxy_message(response: httpx.Response, *secrets: str) -> str:
    """The proxy's own explanation of a failure, scrubbed and bounded."""
    try:
        body: Any = response.json()
    except ValueError:
        body = None

    detail: Any = None
    if isinstance(body, dict):
        error = body.get("error")
        detail = error.get("message") if isinstance(error, dict) else error
        if detail is None:
            detail = body.get("detail")
    if detail is None:
        detail = response.text

    return _scrub(str(detail), *secrets)[:500]


def _scrub(text: str, *secrets: str) -> str:
    """Remove credentials from text on its way into an error.

    A well-behaved proxy never echoes the key it refused, but an error path is
    the one place a credential must not arrive by accident, so the guarantee is
    enforced here rather than assumed of the server.
    """
    for secret in secrets:
        if secret:
            text = text.replace(secret, _REDACTED)
    return text
