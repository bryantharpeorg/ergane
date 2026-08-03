# Contract: LLM Judge

The judge is one bounded chat completion, not an agent (research R4). It runs only
after all deterministic gates pass (FR-003), on a per-attempt virtual key minted by
component 1 for persona `judge`.

## Transport

```
POST {LITELLM_PROXY_URL}/chat/completions
Authorization: Bearer <judge attempt virtual key>
{
  "model": "<judge persona's registry alias>",
  "temperature": 0,
  "max_tokens": 2000,
  "messages": [ {"role": "system", ...}, {"role": "user", ...} ]
}
```

OpenAI-compatible endpoint — works uniformly across every backend the proxy
fronts. The model alias comes from `personas.yaml`; code never names a model.

## Prompt assembly (pure function, `factory/verify/judge.py`)

**System message** (fixed template): you are a verification judge; score the diff
against each acceptance scenario **individually**; a scenario passes only if the
diff demonstrably satisfies every GIVEN/WHEN/THEN step; REMOVED requirements are
verified by absence (no surviving behavior contradicting the removal); respond with
ONLY the JSON object described below.

**User message**, in order:

1. Requirement header(s) + full requirement body (verbatim, never truncated).
2. Every `#### Scenario:` with its steps, verbatim, each tagged with its exact
   description string (the response must echo these strings).
3. `prior_feedback` when this is a judge-initiated retry (verbatim, FR-006).
4. The diff: unified format, capped at 60 KiB with proportional per-file head+tail
   truncation and explicit `[... N lines truncated ...]` markers (research R6);
   full file list + diffstat always included. Truncation is disclosed in the
   prompt and flagged `truncated_input` in the verdict.

## Response schema (strict)

```json
{
  "verdict": "pass | retry | fail",
  "scenarios": [
    {"scenario": "<exact dispatched description>", "pass": true, "reasoning": "..."}
  ],
  "feedback": "actionable text; MUST name each failing scenario"
}
```

Parsing rules (`factory/verify/judge.py`, pure):

- Accept the object raw or inside one fenced code block; anything else is
  **malformed**.
- Every dispatched scenario must appear exactly once; extra or missing scenarios →
  **malformed**.
- Cross-check: any `pass: false` forces the overall outcome to `retry` (or `fail`)
  even if `verdict` says `pass` — the stricter interpretation always wins (FR-003;
  holistic passing prohibited).
- Malformed responses consume one judge attempt (spec edge case). After the cap,
  the judgment is `FAIL` with the parse failure as feedback — garbage never
  becomes a pass (SC-002).

## Bounds (SC-003)

- ≤ 1 + 2 judge invocations per verification cycle (`max_judge_retries = 2`),
  within the node's total attempt cap (default 3).
- HTTP failures retry briefly in-activity; persistent unavailability surfaces as
  `JUDGE_UNAVAILABLE` → verdict falls back to deterministic-gates-only with
  `judge_unavailable = true` and an operator notification (spec edge case).
- The judge is NEVER invoked from CI or the merge queue (FR-009, D-008) — nothing
  in this contract is reachable from component 3's required checks.

## Attribution (constitution V)

Caller sequence per judge attempt: component 1 `issue_attempt_key(persona=judge)` →
`run_judge` → component 1 `teardown_attempt`. Judge spend therefore lands in the
usage ledger attributed to the node's epic/spec-ref with persona `judge`.
