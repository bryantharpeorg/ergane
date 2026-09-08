# Attempt 1 — US2: A Codex refusal is classified, not read as a silent success

## What changed

Three commits, tests first:

- `tests/test_155_us2_codex_refusal.py` (T009, new) — five tests committed
  observed-red. US2-S1: a Codex gateway attempt whose log carries the measured
  refusal ends `auth_failure`, never a diffless `agent_error`, through
  `run_agent_attempt` (the function production calls). US2-S2 both ways: the
  measured string replays as a named refusal, and the same run shape without
  the marker stays ordinary `AGENT_ERROR` — marker-driven, so the story's own
  failure keeps its class. US2-S3 both halves: a successful run whose
  cleartext reasoning quotes the refusal text stays `COMPLETED` (reasoning
  satisfies nothing), and a refused run whose reasoning streams beside the
  fatal line still ends `auth_failure` (reasoning defeats nothing). Driven
  with `tests/stub_codex.py` scripting the measured shape (exit 1, fatal lines
  beside/instead of reasoning), against the combined `stdout.log`.
- `factory/activities/agent_activities.py` (T010) — the activity layer had
  consumed the two Claude markers by import and gated the reclassification on
  `ROUTE_SUBSCRIPTION`, so a Codex refusal read as a diffless `AGENT_ERROR`
  even though US1 landed the measured marker (`CODEX_REFUSAL_MARKER`) and the
  per-CLI seam that declares it (`CodexAdapter._refusal_markers`) — the seam's
  docstring already promised an activity-layer reader that did not exist.
  `_classify_subscription_auth_failure(context, result)` became
  `_classify_auth_failure(adapter, result)`: the refusal markers are read off
  the adapter that ran (`_declared_refusal_markers` answers empty for an
  object outside the seam — never a default set, constitution IX's spirit at
  an inner seam), the one combined `stdout.log` is scanned, and there is no
  route gate — the measured Codex marker appears on every route's 401 (plan
  trap 2). `_raise_if_launch_refused` moved ahead of the classifier: the
  session-id marker sits on Claude's declared tuple, and a classification
  running first would have swallowed the non-retryable `AGENT_LAUNCH_FAILED`
  raise (107 FR-014). `tests/test_subscription_credential.py` updated to the
  renamed classifier — same two-step shape, same assertions.
- `specs/155-codex-runs-as-a-second-runner/evidence/us2-refusal-measurement.md`
  — the refusal shapes re-measured on `@openai/codex@0.153.4` (this attempt
  reproduced US1's recorded probe rather than inheriting it): exit 1, stdout
  empty, fatal lines on stderr, for no-credential (401 through api.openai.com),
  unset `env_key` (`ERROR: Missing environment variable: CODEX_GATEWAY_KEY.` —
  prevented by construction in production), and invalid gateway key (401
  through the LiteLLM proxy on localhost:4000). The stable route-independent
  substring is `unexpected status 401 Unauthorized`; a refused run still writes
  its rollout file, so the rollout is not evidence a turn ran.

## The red run (T009, against the tree as received)

Three of the five failed on exactly the defect (the other two are the
stay-correct controls that had to pass red):

```
FAILED tests/test_155_us2_codex_refusal.py::test_a_codex_auth_refusal_is_named_not_silent
FAILED tests/test_155_us2_codex_refusal.py::test_the_measured_string_replays_as_a_named_refusal
FAILED tests/test_155_us2_codex_refusal.py::test_reasoning_text_defeats_no_refusal
3 failed, 2 passed in 0.45s
E       AssertionError: assert <Termination....'agent_error'> == <Termination....auth_failure'>
```

## Gate

`uv run pytest -q` on the finished tree: **5858 passed, 58 skipped, 0 failed**
(515 s). A first full run against the same diff reported 4 failed + 2 errors
(`test_worker_versioning.py` dev-server boots, `test_us2_shipped_registry.py`
registry reads); all 23 pass in isolation with and without the diff, and the
first run's log carries a Temporal client retry storm to a refused
`127.0.0.1:42775` — another node's dev server competing for the port on this
shared host, not the diff. The re-run above is the clean gate.

## Environment incidents, recorded because they cost time

- Twice during the attempt the worktree's git registration
  (`.git/worktrees/us2` in the parent repo) was deleted out from under this
  node — `git worktree prune` run by some other host process (sibling
  registrations vanished and appeared in step with it). Both times the
  registration was recreated from the intact `us4` template (`commondir`,
  `gitdir`, `HEAD`; the second time without an `index`, which git then rebuilds
  from disk). All work was committed to the branch ref before each break, and
  the branch ref lives in the common git dir, so nothing was lost.
- The first registration rebuild used an empty `index` file, which git reads
  as "every tracked file deleted"; `git add -A` rebuilt it from the disk tree
  and the staged diff was exactly the attempt's own change.

## Story-diff size

`git diff 994dccc..HEAD` — 22,455 bytes against the 65,536-byte refusal
ceiling (constitution VIII / D-050), with the evidence artifact charged to the
same budget.