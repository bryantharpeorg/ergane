"""The one place a model is allowed to have an opinion, and how it is fenced in.

Everything else in verification is deterministic; the judge is the single
bounded LLM edge (constitution IV), and it is bounded in four directions at
once. Each of those bounds is a way this component could otherwise be talked
into a false PASS, so each gets its own section here.

- **What goes in is exactly the node's criteria, verbatim.** The requirement
  body and every dispatched scenario arrive uncut, tagged with the ids the
  response must echo (FR-003). Criteria are the ground truth: a prompt that
  paraphrased or dropped one would move the goalposts silently, which is the
  same failure as a hallucinating parser one module upstream.
- **The diff is capped, and a cap is not a deletion.** Over 60 KiB the diff is
  truncated per file in proportion to what each file contributed, keeping every
  file's head and tail, with explicit `[... N lines truncated ...]` markers and
  the full file list retained (R6). The markers exist so the judge reads an
  elision as an elision instead of as missing implementation — an unmarked cut
  turns a large, correct node into a confident FAIL.
- **What comes back is parsed strictly, and the stricter reading wins.** Every
  dispatched scenario must appear exactly once; a `verdict: pass` alongside a
  `pass: false` finding is a RETRY, never a pass (R5). Holistic passing is the
  thing FR-003 exists to prohibit, and the cross-check is where the prohibition
  is actually enforced.
- **Garbage never becomes a pass, and never becomes unbounded spend.** A
  malformed response consumes one judge attempt and asks for another; on the
  last attempt it becomes FAIL carrying the parse failure as feedback (SC-002,
  SC-003). The HTTP layer retries a briefly-unreachable backend and then gives
  up with `JudgeUnavailableError` — the gates-only fallback is the verdict
  composer's decision, not one this module may take on its behalf.

Two credential facts are asserted rather than assumed. The judge authenticates
with the per-attempt virtual key component 1 minted for it, and the master key
sits in the process environment throughout these tests — so "the master key
never reaches the proxy" is checked against the recorded request bytes, not
against the absence of a line of code (FR-009, SC-004).

The fake proxy (`tests/judge_proxy.py`) replies only what a test scripts. That
is deliberate: a fake clever enough to compose a valid verdict would be a second
implementation of the schema, agreeing with the parser about exactly the shapes
this module exists to be suspicious of.

Written before `factory/verify/judge.py` exists (T016 precedes T020): until the
module lands, every test here fails at import.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Sequence

import httpx
import pytest

from factory.config import load_personas
from factory.verify.judge import (
    DEFAULT_MAX_JUDGE_RETRIES,
    DIFF_INPUT_LIMIT,
    MAX_HTTP_ATTEMPTS,
    SYSTEM_PROMPT,
    JudgeParseError,
    JudgeUnavailableError,
    build_prompt,
    dispatched_scenario_ids,
    parse_verdict,
    prepare_diff,
    run_judge,
)
from factory.verify.models import (
    CriteriaSet,
    JudgeOutcome,
    JudgeVerdict,
    Requirement,
    RequirementKind,
    Scenario,
    VerificationConfig,
)
from tests.judge_proxy import (
    JUDGE_MODEL_ALIAS,
    FakeJudgeProxy,
    fence,
    verdict_json,
)

# --- the criteria under judgment ---------------------------------------------
#
# Hand-built rather than parsed: US2's tests are independent of US1's parser
# (tasks.md § Dependencies), and hand-building is also the only way to hold the
# scenario text still while asserting it arrives verbatim.

SCENARIOS = [
    Scenario(
        scenario_id="US2-S1",
        steps=[
            "**Given** a target repo with a committed `factory.yaml`",
            "**When** the verifier runs",
            "**Then** each declared gate executes with exit-code semantics",
        ],
        raw_text=(
            "1. **Given** a target repo with a committed `factory.yaml` declaring "
            "runtime and test/lint/typecheck commands, **When** the verifier runs, "
            "**Then** each declared gate executes with exit-code semantics (0 = pass)."
        ),
    ),
    Scenario(
        scenario_id="US2-S2",
        steps=[
            "**Given** any deterministic gate fails",
            "**When** verification concludes",
            "**Then** the verdict is FAIL and the judge is not consulted",
        ],
        raw_text=(
            "2. **Given** any deterministic gate fails, **When** verification "
            "concludes, **Then** the verdict is FAIL, the judge is not consulted, "
            "and gate output is preserved for the retry prompt."
        ),
    ),
    Scenario(
        scenario_id="US2-S3",
        steps=[
            "**Given** a non-no-op node whose diff is empty",
            "**When** verification runs",
            "**Then** the verdict is FAIL regardless of gate results",
        ],
        raw_text=(
            "3. **Given** a non-no-op node whose diff is empty, **When** "
            "verification runs, **Then** the verdict is FAIL regardless of gate "
            "results (anti-rubber-stamp)."
        ),
    ),
]

SCENARIO_IDS = [scenario.scenario_id for scenario in SCENARIOS]

STORY = Requirement(
    key="US2",
    kind=RequirementKind.STORY,
    title="Two-tier verification of a node's diff",
    priority="P1",
    body=(
        "As the factory, when a node reports completion, I evaluate it with "
        "deterministic gates first and a bounded judge second, so that no node "
        "unlocks downstream work on an unverified claim."
    ),
    scenarios=SCENARIOS,
)

FUNCTIONAL = Requirement(
    key="FR-002",
    kind=RequirementKind.FUNCTIONAL,
    title=None,
    priority=None,
    body=(
        "The verifier MUST run every gate declared in the target repo's committed "
        "factory.yaml and record each gate's result."
    ),
    scenarios=[],
)

CRITERIA = CriteriaSet(
    feature="002-verification-gating",
    spec_ref="verification-gating/two-tier",
    requirements=[STORY, FUNCTIONAL],
    source_path="specs/002-verification-gating/spec.md",
    source_sha256="c0ffee" + "0" * 58,
    snapshotted_at="2026-08-04T09:15:00Z",
)

FR_ONLY_CRITERIA = CriteriaSet(
    feature="002-verification-gating",
    spec_ref="verification-gating/gates-only",
    requirements=[FUNCTIONAL],
    source_path="specs/002-verification-gating/spec.md",
    source_sha256="c0ffee" + "0" * 58,
    snapshotted_at="2026-08-04T09:15:00Z",
)

#: What a failing attempt hands the next one (FR-006). Quoted verbatim, so the
#: assertions can look for it character-for-character.
PRIOR_FEEDBACK = (
    "US2-S2 fails: run_gates() returns early on the first non-zero exit, so the "
    "typecheck gate never runs and its result is missing from the evidence."
)

#: The master key is in the worker environment throughout — that is the point.
MASTER_KEY = "sk-master-must-never-reach-the-judge"


# --- diff fixtures ------------------------------------------------------------


def unified_diff(path: str, *, added: int, removed: int = 0) -> str:
    """One file's section of a `git diff`, sized to order."""
    header = (
        f"diff --git a/{path} b/{path}\n"
        "index 1111111..2222222 100644\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        f"@@ -1,{max(removed, 1)} +1,{added} @@\n"
    )
    body = "".join(f"-{path} old line {index}\n" for index in range(removed))
    body += "".join(f"+{path} new line {index}\n" for index in range(added))
    return header + body


BIG = "src/big_module.py"
MEDIUM = "src/medium_module.py"
TINY = "src/tiny_module.py"

BIG_ADDED, BIG_REMOVED = 2000, 40
MEDIUM_ADDED = 1000
TINY_ADDED = 5

#: ~35 bytes a line across ~3000 lines: comfortably over the 60 KiB cap, with
#: file sizes far enough apart that "proportional" is distinguishable both from
#: "equal shares" and from "keep the first files and drop the rest".
BIG_DIFF = unified_diff(BIG, added=BIG_ADDED, removed=BIG_REMOVED)
MEDIUM_DIFF = unified_diff(MEDIUM, added=MEDIUM_ADDED)
TINY_DIFF = unified_diff(TINY, added=TINY_ADDED)
OVERSIZED_DIFF = BIG_DIFF + MEDIUM_DIFF + TINY_DIFF

SMALL_DIFF = unified_diff("src/gates.py", added=12, removed=3)


def content_lines(section: str) -> list[str]:
    """The `+`/`-` lines of a diff section — its content, minus its headers."""
    return [
        line
        for line in section.splitlines()
        if (line.startswith("+") and not line.startswith("+++"))
        or (line.startswith("-") and not line.startswith("---"))
    ]


def sections(diff_text: str) -> dict[str, str]:
    """Split a rendered diff into `{path: section}`, dropping the preamble."""
    found: dict[str, str] = {}
    for chunk in re.split(r"(?m)^(?=diff --git )", diff_text):
        header = re.match(r"diff --git a/(\S+) b/\S+", chunk)
        if header:
            found[header.group(1)] = chunk
    return found


def preamble(diff_text: str) -> str:
    """Everything before the first file section — the list and stat summary."""
    return diff_text.split("diff --git", 1)[0]


TRUNCATION_MARKER_RE = re.compile(r"\[\.\.\. (\d+) lines truncated \.\.\.\]")


def truncated_counts(section: str) -> list[int]:
    return [int(count) for count in TRUNCATION_MARKER_RE.findall(section)]


# --- helpers ------------------------------------------------------------------


def parse(
    content: str,
    *,
    ids: Sequence[str] = tuple(SCENARIO_IDS),
    judge_attempt: int = 1,
    truncated_input: bool = False,
) -> JudgeVerdict:
    return parse_verdict(
        content,
        ids,
        judge_attempt=judge_attempt,
        model_alias=JUDGE_MODEL_ALIAS,
        truncated_input=truncated_input,
    )


def all_pass(feedback: str = "every scenario is satisfied") -> str:
    return verdict_json(
        verdict="pass",
        scenarios=[(scenario_id, True) for scenario_id in SCENARIO_IDS],
        feedback=feedback,
    )


def user_message(criteria: CriteriaSet = CRITERIA, diff_text: str = SMALL_DIFF, **kwargs: Any) -> str:
    return build_prompt(criteria, diff_text, **kwargs).messages[1]["content"]


@pytest.fixture
def proxy(monkeypatch: pytest.MonkeyPatch) -> FakeJudgeProxy:
    """A fake `/chat/completions`, with the master key sitting in the env.

    The credential is set for every judge call in this module so that "the
    master key never reaches the proxy" is asserted in a process where it was
    available to leak (FR-009).
    """
    monkeypatch.setenv("LITELLM_MASTER_KEY", MASTER_KEY)
    return FakeJudgeProxy()


async def judge(
    proxy: FakeJudgeProxy,
    *,
    criteria: CriteriaSet = CRITERIA,
    diff_text: str = SMALL_DIFF,
    model_alias: str = JUDGE_MODEL_ALIAS,
    proxy_url: str | None = None,
    virtual_key: str | None = None,
    **kwargs: Any,
) -> JudgeVerdict:
    """Call `run_judge` against the fake, with no real backoff to wait out."""
    return await run_judge(
        criteria,
        diff_text,
        proxy_url=proxy.base_url if proxy_url is None else proxy_url,
        virtual_key=proxy.virtual_key if virtual_key is None else virtual_key,
        model_alias=model_alias,
        transport=proxy.transport,
        retry_backoff_s=0.0,
        **kwargs,
    )


def assert_credential_free(error: BaseException, *secrets: str) -> None:
    """No secret may appear anywhere in the raised chain (FR-009, SC-004)."""
    seen: BaseException | None = error
    depth = 0
    while seen is not None and depth < 10:
        for rendering in (str(seen), repr(seen), str(seen.args)):
            for secret in secrets:
                assert secret not in rendering, (
                    f"{secret!r} leaked into {type(seen).__name__}"
                )
        seen = seen.__cause__ or seen.__context__
        depth += 1


# --- prompt assembly ----------------------------------------------------------


def test_the_prompt_is_a_system_message_and_one_user_message() -> None:
    """One completion, two messages (R4) — no conversation, no agent loop."""
    prompt = build_prompt(CRITERIA, SMALL_DIFF)

    assert [message["role"] for message in prompt.messages] == ["system", "user"]
    assert prompt.messages[0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert prompt.truncated_input is False


def test_the_system_message_states_the_schema_it_demands_back() -> None:
    """Strict parsing is only fair if the shape was stated (judge.md § schema)."""
    for key in ("verdict", "scenarios", "pass", "reasoning", "feedback"):
        assert key in SYSTEM_PROMPT, f"the schema key {key!r} is never mentioned"
    for value in ("pass", "retry", "fail"):
        assert value in SYSTEM_PROMPT
    assert "JSON" in SYSTEM_PROMPT


def test_every_requirement_body_arrives_verbatim() -> None:
    """Criteria are the ground truth; a paraphrase is a different requirement."""
    user = user_message()

    assert STORY.body in user
    assert STORY.key in user
    assert STORY.title is not None and STORY.title in user
    assert FUNCTIONAL.body in user, "an FR is context the story is owed against"
    assert FUNCTIONAL.key in user


def test_every_scenario_arrives_verbatim_under_the_id_it_must_echo() -> None:
    """The response is matched on these ids, so the prompt has to carry them."""
    user = user_message()

    for scenario in SCENARIOS:
        assert scenario.raw_text in user
        assert scenario.scenario_id in user


def test_prior_feedback_is_carried_verbatim() -> None:
    """FR-006: the retry says what failed, in the words that said it."""
    assert PRIOR_FEEDBACK in user_message(prior_feedback=PRIOR_FEEDBACK)


def test_nothing_stands_in_for_absent_prior_feedback() -> None:
    """A first attempt is not told about a previous one that never happened."""
    assert PRIOR_FEEDBACK not in user_message()


def test_the_sections_arrive_in_the_order_the_contract_states() -> None:
    """Requirement, then scenarios, then prior feedback, then the diff (judge.md).

    Ordering is not cosmetic: the criteria have to be established before the
    thing being scored against them shows up, and the diff goes last because it
    is the only part that may have been cut.
    """
    user = user_message(diff_text=OVERSIZED_DIFF, prior_feedback=PRIOR_FEEDBACK)

    assert (
        user.index(STORY.body)
        < user.index(SCENARIOS[0].raw_text)
        < user.index(SCENARIOS[-1].raw_text)
        < user.index(PRIOR_FEEDBACK)
        < user.index("diff --git")
    )


def test_dispatched_scenario_ids_are_the_story_scenarios_in_order() -> None:
    assert dispatched_scenario_ids(CRITERIA) == SCENARIO_IDS
    assert dispatched_scenario_ids(FR_ONLY_CRITERIA) == []


def test_a_node_with_no_scenarios_has_nothing_for_the_judge_to_score() -> None:
    """An empty scenario list parses back as "every scenario passed" — a pass for
    free, on a node nobody scored. FR-only nodes are gates-plus-output-check by
    design (spec § Clarifications), so the mistake is refused at the door."""
    with pytest.raises(ValueError):
        build_prompt(FR_ONLY_CRITERIA, SMALL_DIFF)


# --- diff bounds --------------------------------------------------------------


def test_the_input_cap_is_60_kib() -> None:
    assert DIFF_INPUT_LIMIT == 60 * 1024


def test_a_diff_under_the_cap_arrives_whole() -> None:
    prepared = prepare_diff(SMALL_DIFF)

    assert prepared.truncated is False
    assert SMALL_DIFF in prepared.text
    assert SMALL_DIFF in user_message()


def test_an_oversized_diff_is_capped_and_flagged() -> None:
    assert len(OVERSIZED_DIFF.encode("utf-8")) > DIFF_INPUT_LIMIT

    prepared = prepare_diff(OVERSIZED_DIFF)

    assert prepared.truncated is True
    assert len(prepared.text.encode("utf-8")) <= DIFF_INPUT_LIMIT
    assert build_prompt(CRITERIA, OVERSIZED_DIFF).truncated_input is True


def test_truncation_is_disclosed_before_the_diff_begins() -> None:
    """An undisclosed cut reads as missing implementation, not as a cut (R6)."""
    user = user_message(diff_text=OVERSIZED_DIFF)

    assert "truncat" in preamble(user).lower()


def test_every_changed_file_survives_in_the_summary() -> None:
    """The file list and stat are never truncated: a file cut down to a stub
    still has to be visible as a file that changed, or the judge cannot see the
    shape of the diff it is scoring."""
    listing = preamble(prepare_diff(OVERSIZED_DIFF).text)

    assert f"{BIG} | +{BIG_ADDED} -{BIG_REMOVED}" in listing
    assert f"{MEDIUM} | +{MEDIUM_ADDED} -0" in listing
    assert f"{TINY} | +{TINY_ADDED} -0" in listing


def test_truncation_is_proportional_to_what_each_file_contributed() -> None:
    """Equal shares would gut a 2000-line rewrite to keep a 5-line touch-up whole
    in triplicate; keeping the first files whole would hide the last ones."""
    kept = sections(prepare_diff(OVERSIZED_DIFF).text)

    assert set(kept) == {BIG, MEDIUM, TINY}
    assert len(content_lines(kept[BIG])) > len(content_lines(kept[MEDIUM]))
    assert sum(truncated_counts(kept[BIG])) > sum(truncated_counts(kept[MEDIUM]))


def test_a_small_file_is_not_cut_down_to_a_stub() -> None:
    """A 5-line file costs nothing to carry whole, and a `[... 2 lines truncated
    ...]` marker inside one is pure noise where the judge needs signal."""
    kept = sections(prepare_diff(OVERSIZED_DIFF).text)

    assert not truncated_counts(kept[TINY])
    assert TINY_DIFF in prepare_diff(OVERSIZED_DIFF).text


def test_a_truncated_file_keeps_its_head_and_its_tail() -> None:
    """Head-only would hide the end of every long file, and the end is where a
    half-finished implementation usually is."""
    big = sections(prepare_diff(OVERSIZED_DIFF).text)[BIG]

    assert f"diff --git a/{BIG} b/{BIG}" in big
    assert f"-{BIG} old line 0" in big, "the head of the section"
    assert f"+{BIG} new line {BIG_ADDED - 1}" in big, "and its tail"


def test_the_marker_says_how_many_lines_went_missing() -> None:
    """Kept + stated-missing = what was there. A marker that undercounted would
    let the judge believe it had seen a file it mostly had not."""
    kept = sections(prepare_diff(OVERSIZED_DIFF).text)

    for path, original in ((BIG, BIG_DIFF), (MEDIUM, MEDIUM_DIFF)):
        counts = truncated_counts(kept[path])
        assert counts, f"{path} was cut, so it must say so"
        assert all(count > 0 for count in counts), "a marker for nothing is noise"
        assert len(content_lines(kept[path])) + sum(counts) == len(
            content_lines(original)
        )


def test_criteria_are_never_truncated_no_matter_the_diff() -> None:
    """The diff is evidence and the criteria are the standard; only evidence is
    ever abridged (R6)."""
    prompt = build_prompt(CRITERIA, OVERSIZED_DIFF * 3, prior_feedback=PRIOR_FEEDBACK)
    user = prompt.messages[1]["content"]

    assert prompt.truncated_input is True
    assert STORY.body in user
    assert FUNCTIONAL.body in user
    assert PRIOR_FEEDBACK in user
    for scenario in SCENARIOS:
        assert scenario.raw_text in user


def test_an_empty_diff_is_not_a_truncation() -> None:
    """The empty-diff verdict belongs to the output check (FR-004), which has
    already run by now; the judge simply gets nothing to read."""
    assert prepare_diff("").truncated is False
    assert build_prompt(CRITERIA, "").truncated_input is False


# --- strict parsing -----------------------------------------------------------


def test_a_raw_json_object_parses() -> None:
    verdict = parse(all_pass())

    assert isinstance(verdict, JudgeVerdict)
    assert verdict.outcome is JudgeOutcome.PASS
    assert [finding.scenario for finding in verdict.findings] == SCENARIO_IDS
    assert all(finding.passed for finding in verdict.findings)
    assert verdict.feedback == "every scenario is satisfied"


def test_one_fenced_block_parses_even_with_prose_around_it() -> None:
    """Models preface things. One fence is the contract; the wrapper is not."""
    content = f"Here is my assessment.\n\n{fence(all_pass())}\n\nHappy to expand."

    assert parse(content).outcome is JudgeOutcome.PASS


def test_a_fence_without_a_language_parses() -> None:
    assert parse(fence(all_pass(), language="")).outcome is JudgeOutcome.PASS


def test_two_fenced_blocks_are_malformed() -> None:
    """Which one is the verdict? Guessing is how a stale draft gets scored."""
    other = verdict_json(
        verdict="fail",
        scenarios=[(scenario_id, False) for scenario_id in SCENARIO_IDS],
        feedback="on reflection, no",
    )

    with pytest.raises(JudgeParseError):
        parse(f"{fence(all_pass())}\n\n{fence(other)}")


def test_prose_around_an_unfenced_object_is_malformed() -> None:
    """Accept the object raw or in one fence; anything else is malformed
    (judge.md). Fishing an object out of prose is a parser inventing a verdict."""
    with pytest.raises(JudgeParseError):
        parse(f"I think it passes. {all_pass()} Let me know.")


@pytest.mark.parametrize(
    "content",
    ["", "   ", "The diff looks fine to me.", "[]", '"pass"', "null", "42"],
    ids=["empty", "blank", "prose", "array", "string", "null", "number"],
)
def test_a_response_that_is_not_a_verdict_object_is_malformed(content: str) -> None:
    with pytest.raises(JudgeParseError):
        parse(content)


def test_broken_json_is_malformed() -> None:
    with pytest.raises(JudgeParseError):
        parse(all_pass()[:-3])


@pytest.mark.parametrize("missing", ["verdict", "scenarios", "feedback"])
def test_a_missing_top_level_key_is_malformed(missing: str) -> None:
    payload = json.loads(all_pass())
    del payload[missing]

    with pytest.raises(JudgeParseError) as excinfo:
        parse(json.dumps(payload))

    assert missing in str(excinfo.value)


def test_an_unknown_verdict_word_is_malformed() -> None:
    """`maybe` has no mapping, and the nearest guess would be the lenient one."""
    payload = json.loads(all_pass())
    payload["verdict"] = "maybe"

    with pytest.raises(JudgeParseError) as excinfo:
        parse(json.dumps(payload))

    assert "maybe" in str(excinfo.value)


def test_a_missing_scenario_is_malformed_and_named() -> None:
    """Silently scoring two of three scenarios is a partial verdict wearing a
    whole one's clothes (FR-003)."""
    content = verdict_json(
        verdict="pass",
        scenarios=[(scenario_id, True) for scenario_id in SCENARIO_IDS[:-1]],
        feedback="looks fine",
    )

    with pytest.raises(JudgeParseError) as excinfo:
        parse(content)

    assert SCENARIO_IDS[-1] in str(excinfo.value)


def test_an_invented_scenario_is_malformed_and_named() -> None:
    """A judge scoring criteria the node was never dispatched against has lost
    track of which spec it is reading."""
    content = verdict_json(
        verdict="pass",
        scenarios=[
            *[(scenario_id, True) for scenario_id in SCENARIO_IDS],
            ("US2-S9", True),
        ],
        feedback="looks fine",
    )

    with pytest.raises(JudgeParseError) as excinfo:
        parse(content)

    assert "US2-S9" in str(excinfo.value)


def test_a_scenario_scored_twice_is_malformed() -> None:
    """Two answers for one scenario is not an answer, whichever one wins."""
    content = verdict_json(
        verdict="pass",
        scenarios=[
            *[(scenario_id, True) for scenario_id in SCENARIO_IDS],
            (SCENARIO_IDS[0], False),
        ],
        feedback="looks fine",
    )

    with pytest.raises(JudgeParseError) as excinfo:
        parse(content)

    assert SCENARIO_IDS[0] in str(excinfo.value)


@pytest.mark.parametrize(
    "value", ["false", "yes", 1, None], ids=["quoted", "word", "int", "null"]
)
def test_a_non_boolean_pass_is_malformed(value: object) -> None:
    """`"pass": "false"` is truthy in Python. Coercing here is how a failing
    scenario becomes a passing one for free."""
    payload = json.loads(all_pass())
    payload["scenarios"][1]["pass"] = value

    with pytest.raises(JudgeParseError):
        parse(json.dumps(payload))


def test_a_finding_without_reasoning_is_malformed() -> None:
    """Reasoning is what makes a verdict reviewable; the schema demands it."""
    payload = json.loads(all_pass())
    del payload["scenarios"][0]["reasoning"]

    with pytest.raises(JudgeParseError):
        parse(json.dumps(payload))


def test_findings_come_back_in_dispatch_order() -> None:
    """Store rows and escalation messages read in the order the spec declares,
    not in whatever order the model happened to answer."""
    content = verdict_json(
        verdict="pass",
        scenarios=[(scenario_id, True) for scenario_id in reversed(SCENARIO_IDS)],
        feedback="fine",
    )

    assert [finding.scenario for finding in parse(content).findings] == SCENARIO_IDS


@dataclass(frozen=True)
class CrossCheck:
    """One claimed verdict, its per-scenario findings, and what must survive."""

    id: str
    claimed: str
    passed: tuple[bool, ...]
    outcome: JudgeOutcome


CROSS_CHECKS = [
    CrossCheck("all-pass-and-claimed-pass", "pass", (True, True, True), JudgeOutcome.PASS),
    CrossCheck(
        "claimed-pass-with-one-failure-is-a-retry",
        "pass",
        (True, False, True),
        JudgeOutcome.RETRY,
    ),
    CrossCheck(
        "claimed-pass-with-every-failure-is-a-retry",
        "pass",
        (False, False, False),
        JudgeOutcome.RETRY,
    ),
    CrossCheck("claimed-retry-stands", "retry", (True, False, True), JudgeOutcome.RETRY),
    CrossCheck(
        "claimed-retry-over-passing-findings-stands",
        "retry",
        (True, True, True),
        JudgeOutcome.RETRY,
    ),
    CrossCheck(
        "claimed-fail-stands-over-passing-findings",
        "fail",
        (True, True, True),
        JudgeOutcome.FAIL,
    ),
    CrossCheck(
        "claimed-fail-with-failures", "fail", (False, True, True), JudgeOutcome.FAIL
    ),
]


@pytest.mark.parametrize("case", CROSS_CHECKS, ids=[case.id for case in CROSS_CHECKS])
def test_the_stricter_interpretation_always_wins(case: CrossCheck) -> None:
    """FR-003 prohibits holistic passing, and this is where it is prohibited: the
    overall word and the per-scenario findings are both read, and whichever is
    harsher becomes the outcome."""
    content = verdict_json(
        verdict=case.claimed,
        scenarios=list(zip(SCENARIO_IDS, case.passed)),
        feedback="see per-scenario reasoning",
    )

    verdict = parse(content)

    assert verdict.outcome is case.outcome
    assert [finding.passed for finding in verdict.findings] == list(case.passed)


def test_the_verdict_carries_the_attempt_the_alias_and_the_truncation_flag() -> None:
    """Evidence-store columns, all three: which invocation this was, which
    registry alias answered, and whether it saw the whole diff."""
    verdict = parse(all_pass(), judge_attempt=2, truncated_input=True)

    assert verdict.judge_attempt == 2
    assert verdict.model_alias == JUDGE_MODEL_ALIAS
    assert verdict.truncated_input is True


def test_reasoning_is_carried_through_per_scenario() -> None:
    verdict = parse(all_pass())

    assert all(finding.scenario in finding.reasoning for finding in verdict.findings)


# --- the call itself ----------------------------------------------------------


async def test_the_request_is_the_chat_completion_the_contract_describes(
    proxy: FakeJudgeProxy,
) -> None:
    proxy.reply(all_pass())

    verdict = await judge(proxy)

    assert verdict.outcome is JudgeOutcome.PASS
    assert len(proxy.calls) == 1
    call = proxy.last
    assert call.method == "POST"
    assert call.path == "/chat/completions"
    assert call.body is not None
    assert call.body["model"] == JUDGE_MODEL_ALIAS
    assert call.body["temperature"] == 0
    assert call.body["max_tokens"] == 2000
    assert call.messages == build_prompt(CRITERIA, SMALL_DIFF).messages


async def test_a_proxy_url_with_a_trailing_slash_still_resolves(
    proxy: FakeJudgeProxy,
) -> None:
    """Operator-supplied URLs come both ways; neither may produce `//chat`."""
    proxy.reply(all_pass())

    await judge(proxy, proxy_url=f"{proxy.base_url}/")

    assert proxy.last.path == "/chat/completions"


async def test_the_call_authenticates_with_the_attempt_key_and_nothing_else(
    proxy: FakeJudgeProxy,
) -> None:
    """The judge's spend is attributable because it spends on its own key
    (constitution V); the master key is in this process's environment and must
    not appear anywhere in the bytes that left it (FR-009)."""
    proxy.reply(all_pass())

    await judge(proxy)

    assert proxy.last.headers["authorization"] == f"Bearer {proxy.virtual_key}"
    assert MASTER_KEY not in proxy.transcript()


async def test_prior_feedback_reaches_the_proxy_verbatim(proxy: FakeJudgeProxy) -> None:
    proxy.reply(all_pass())

    await judge(proxy, prior_feedback=PRIOR_FEEDBACK)

    assert PRIOR_FEEDBACK in proxy.last.user_message


async def test_a_truncated_diff_is_flagged_on_the_verdict(
    proxy: FakeJudgeProxy,
) -> None:
    """The flag is what tells an operator reading the stored row that the judge
    was working from an abridgement."""
    proxy.reply(all_pass())

    verdict = await judge(proxy, diff_text=OVERSIZED_DIFF)

    assert verdict.truncated_input is True
    assert TRUNCATION_MARKER_RE.search(proxy.last.user_message)


async def test_the_model_is_whichever_alias_the_registry_resolved(
    proxy: FakeJudgeProxy,
) -> None:
    """Code never names a model (constitution VII) — the alias is an argument,
    and the shipped registry's judge entry is what a caller passes."""
    alias = load_personas()["judge"].model
    proxy.reply(all_pass())

    verdict = await judge(proxy, model_alias=alias)

    assert proxy.last.body is not None
    assert proxy.last.body["model"] == alias
    assert verdict.model_alias == alias


# --- malformed responses: bounded, and never a pass ---------------------------


async def test_a_malformed_response_asks_for_another_attempt(
    proxy: FakeJudgeProxy,
) -> None:
    """It consumes one judge attempt and comes back RETRY — whether there is
    another one is the ladder's decision, not this module's (R5)."""
    proxy.reply("I'd say it passes, broadly.")

    verdict = await judge(proxy, judge_attempt=1)

    assert verdict.outcome is JudgeOutcome.RETRY
    assert verdict.findings == []
    assert verdict.judge_attempt == 1
    assert len(proxy.calls) == 1, "one response, one attempt — no hidden re-ask"


async def test_the_malformed_feedback_is_the_parse_failure_itself(
    proxy: FakeJudgeProxy,
) -> None:
    """The next attempt is told what was wrong with the last answer, in the
    parser's words — the same discipline the criteria parser follows."""
    content = verdict_json(
        verdict="pass",
        scenarios=[(scenario_id, True) for scenario_id in SCENARIO_IDS[:-1]],
        feedback="looks fine",
    )
    proxy.reply(content)

    verdict = await judge(proxy, judge_attempt=1)

    with pytest.raises(JudgeParseError) as excinfo:
        parse(content)
    assert str(excinfo.value) in verdict.feedback


@pytest.mark.parametrize("attempt", [1, 2])
async def test_malformed_below_the_cap_is_a_retry(
    proxy: FakeJudgeProxy, attempt: int
) -> None:
    proxy.reply("nope, not JSON")

    verdict = await judge(proxy, judge_attempt=attempt)

    assert verdict.outcome is JudgeOutcome.RETRY


async def test_the_last_judge_attempt_turns_malformed_into_fail(
    proxy: FakeJudgeProxy,
) -> None:
    """Garbage never becomes a pass (SC-002), and never becomes unbounded spend
    either (SC-003): 1 + 2 retries is the whole budget."""
    proxy.reply("nope, not JSON")

    verdict = await judge(proxy, judge_attempt=1 + DEFAULT_MAX_JUDGE_RETRIES)

    assert verdict.outcome is JudgeOutcome.FAIL
    assert verdict.findings == []
    assert verdict.feedback


async def test_a_tighter_judge_budget_fails_sooner(proxy: FakeJudgeProxy) -> None:
    """The cap is a deployment knob, so the first attempt can also be the last."""
    proxy.reply("nope, not JSON")

    verdict = await judge(proxy, judge_attempt=1, max_judge_retries=0)

    assert verdict.outcome is JudgeOutcome.FAIL


def test_the_judge_retry_budget_is_the_deployments() -> None:
    """Two constants for one number is one constant too many."""
    assert DEFAULT_MAX_JUDGE_RETRIES == 2
    assert DEFAULT_MAX_JUDGE_RETRIES == VerificationConfig().max_judge_retries


# --- an unreachable backend ---------------------------------------------------


async def test_a_transient_failure_is_retried(proxy: FakeJudgeProxy) -> None:
    """A proxy restart mid-verification is not the node's fault."""
    proxy.fail_next(503)
    proxy.reply(all_pass())

    verdict = await judge(proxy)

    assert verdict.outcome is JudgeOutcome.PASS
    assert len(proxy.calls) == 2


async def test_a_rate_limit_is_retried(proxy: FakeJudgeProxy) -> None:
    proxy.fail_next(429)
    proxy.reply(all_pass())

    assert (await judge(proxy)).outcome is JudgeOutcome.PASS
    assert len(proxy.calls) == 2


async def test_a_persistently_down_backend_gives_up_after_bounded_retries(
    proxy: FakeJudgeProxy,
) -> None:
    """`JUDGE_UNAVAILABLE` is the caller's cue to fall back to gates-only with the
    flag set (spec edge case) — a decision this module does not take, and an
    outcome it must never quietly turn into FAIL."""
    proxy.fail_always(503)

    with pytest.raises(JudgeUnavailableError) as excinfo:
        await judge(proxy)

    assert len(proxy.calls) == MAX_HTTP_ATTEMPTS
    assert 1 < MAX_HTTP_ATTEMPTS <= 5, "retry briefly, not forever (judge.md)"
    assert_credential_free(excinfo.value, MASTER_KEY, proxy.virtual_key)


async def test_a_rejected_credential_is_not_retried(proxy: FakeJudgeProxy) -> None:
    """A key the proxy refuses will be refused three times just as fast, and the
    error must not echo the credential that was refused."""
    proxy.reply(all_pass())

    with pytest.raises(JudgeUnavailableError) as excinfo:
        await judge(proxy, virtual_key="sk-wrong-attempt-key")

    assert len(proxy.calls) == 1
    assert_credential_free(
        excinfo.value, MASTER_KEY, proxy.virtual_key, "sk-wrong-attempt-key"
    )


async def test_a_transport_failure_is_unavailability_not_a_verdict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LITELLM_MASTER_KEY", MASTER_KEY)
    virtual_key = "sk-judge-attempt-do-not-log"

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(JudgeUnavailableError) as excinfo:
        await run_judge(
            CRITERIA,
            SMALL_DIFF,
            proxy_url="http://litellm.test",
            virtual_key=virtual_key,
            model_alias=JUDGE_MODEL_ALIAS,
            transport=httpx.MockTransport(refuse),
            retry_backoff_s=0.0,
        )

    assert_credential_free(excinfo.value, MASTER_KEY, virtual_key)


async def test_a_completion_with_no_message_is_unavailability(
    proxy: FakeJudgeProxy,
) -> None:
    """An empty `choices` is the backend breaking its own protocol, not the judge
    answering badly — charging it to the judge-retry budget would spend a node's
    attempts on someone else's outage."""
    proxy.reply_payload(
        {"id": "chatcmpl-fake", "object": "chat.completion", "choices": []}
    )

    with pytest.raises(JudgeUnavailableError):
        await judge(proxy)
