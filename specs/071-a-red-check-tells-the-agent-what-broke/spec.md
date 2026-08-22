---
state: landed
fixes:
  - interpreter/ci-failure-never-reaches-an-agent
# ATTESTED landed 2026-08-19 10:12 PM CT. Both stories are observed-landed on
# ergane-buildout -- US1 at 476713a (PR #235, 01:49Z), US2 at 225cb31 (PR #236,
# 02:25Z) -- confirmed with `ergane spec landed --default-branch ergane-buildout`.
# The frontmatter had been left at `ready`, which made the board disagree with
# git. Bookkeeping only: a ready-and-observed-landed spec was already skipped by
# the dispatch predicate, so this narrows nothing and arms nothing.
#
# Flipped draft -> ready 2026-08-19 7:12 PM CT at the operator's instruction
# ("yes arm for build"), WITHOUT the adversarial pre-dispatch review that was
# made mandatory earlier the same evening. Recorded here rather than left
# implicit, because that rule exists for a measured reason: a twelve-agent
# review found 68 attempt-costing defects across the three specs drafted ninety
# minutes before this one.
#
# WHAT MAKES THIS A DEFENSIBLE EXCEPTION, stated so the exception does not
# quietly become the rule:
#   - Every line anchor in the plan was verified by printing that exact line
#     individually (`sed -n '<n>p' <file>`) rather than by counting `grep -A`
#     context -- which is precisely the step whose absence produced the 68.
#   - The remedy was run END TO END BY HAND against a real pull request before
#     the spec was written, and its output is pasted into the plan. No other
#     story on this floor has had its fix demonstrated before dispatch.
#   - US1 is roughly fifteen lines of production code.
# If this needs a second attempt, the cause is almost certainly trap 1 --
# rebuilding 025, which is built and works.
#
# Drafted 2026-08-19 ~7:15 PM CT by an operator session, from a root cause found
# by control the same evening while investigating why epic 061 lost three of its
# four stories.
#
# THIS ONE IS DIFFERENT FROM ITS NEIGHBOURS AND THE DIFFERENCE IS THE POINT.
# 067-070 are features. This is ten lines that restore a capability the factory
# was built to have, paid for, believes it has, and has never once had.
#
# WHAT WAS FOUND, and every line of it was run rather than read:
#
#   $ gh pr checks 226 --json name,state,link
#   unknown flag: --json
#   Usage:  gh pr checks [<number> | <url> | <branch>] [flags]
#   EXIT=1
#
# `factory/mergequeue/gh.py:210` issues exactly that command. `gh pr checks` has
# no `--json` flag and never has (checked against gh 2.45.0; `gh pr list` and
# `gh pr view` do have it, which is how the mistake reads as plausible). So the
# call fails on every host, every time, unconditionally -- and it is the FIRST
# HOP of the only path by which a failing CI check's log reaches a recovery
# agent. The log-fetching code behind it has never executed in production.
#
# WHAT THE AGENT GOT, verbatim from the archived recovery prompt at
# `.factory/transcripts/061-.../us2/attempt-2/*.jsonl`:
#
#     Failing required checks (name, run URL, and verbatim log tail):
#     - **test**:
#       log unavailable: could not list checks (GH_REFUSED)
#
# WHAT IT WOULD HAVE GOT, from the same PR, by hand, tonight:
#
#     FAILED tests/test_ergane_init_creates_specs.py::test_init_creates_specs_directory
#       - subprocess.CalledProcessError: Command '['git','-C',<tmp>,'commit',
#         '--quiet','-m','initial commit']' returned non-zero exit status 128.
#
# Exit 128 on `git commit` in a fresh temp repository is a missing `user.email`.
# One line. The agent instead rebuilt byte-identical code, `recovery_cycles` hit
# `max_recovery_cycles` (1), and us2 was KILLED taking us3 and us4 with it at
# attempt 0 -- neither had ever run.
#
# WHAT IS NOT WRONG, so that no implementer rebuilds it. Spec 025 landed its
# evidence-carrying half and it is correct end to end: the activity
# (`factory/activities/merge_activities.py:497`), the workflow's fetch
# (`factory/workgraph/workflow.py:2361`), `LandingEvidence.failing_checks`, the
# prompt render (`factory/workgraph/prompt.py:622`), and FR-013's `base_unmoved`
# -- which fired correctly on the night and told the agent, accurately, that the
# base had not moved. Every link works. One `gh` invocation upstream of them all
# is malformed, and the honest degradation that catches it
# (`factory/mergequeue/github_forge.py:220-222`) is what makes the whole chain
# look like a design choice rather than a defect.
#
# THE SECOND INSTANCE, in the same module, opposite spelling: `create_pr` at
# `factory/mergequeue/gh.py:172` calls `_run_json("pr","create",...)` with NO
# `--json`, and `gh pr create` prints a URL. `json.loads` raises every time. Both
# are live today. Both were invisible because nothing in this repository has ever
# run a real `gh` command and checked that its flags parse.
#
# FILED AS:
#   mergequeue/gh-pr-checks-is-called-with-a-json-flag-that-does-not-exist-...
#   mergequeue/no-test-ever-runs-a-real-gh-command-so-a-malformed-argv-is-invisible
#   interpreter/ci-failure-never-reaches-an-agent  (corrected; its previous
#     mechanism was wrong and would have sent an implementer to rebuild 025)
---

# Feature Specification: a red check tells the agent what broke

## The gap, stated precisely

When a node's pull request fails a required check, the factory is designed to
fetch that check's log and quote it into the recovery attempt's prompt, so the
agent fixes the thing that actually broke. The design is built. The wiring is
complete. It has never delivered a single line of log, because the first `gh`
command in the chain names a flag that does not exist.

The failure is invisible from every direction an operator normally looks. The
tests pass. The spec that built it reports landed. The prompt section renders and
names the failing check. The only trace is one line inside an archived agent
transcript — `log unavailable: could not list checks (GH_REFUSED)` — which nobody
reads unless a node has already died.

## Why a degradation is the wrong shape here

`failing_check_evidence` degrades rather than raising, and that is correct: a
recovery must not become a workflow failure because a forge call was slow. But a
degradation that fires *unconditionally* is not a degradation, it is the only
behaviour — and nothing measures how often the fallback path is taken. A remedy
that only fixes the command leaves the next malformed argv equally silent for
equally long.

## What this spec does not change

- The evidence chain built by 025. It works; do not rebuild it.
- `LandingEvidence`, its shape, or the prompt's rendering of it.
- `max_recovery_cycles`, the recovery ladder, or any budget. That the budget is
  1 and has no operator dial is a real and separate defect, filed separately, and
  widening scope into it here would make this spec unlandable tonight.
- The classification of rejections by cause. That is 069's story.

## User Scenarios & Testing

### User Story 1 - A recovery agent is told which test failed (Priority: P1)

As an operator whose node's pull request went red, the agent that gets one more
try is handed the failing check's log, so it fixes the defect instead of
rebuilding the same code.

**Why this priority**: P1, and it is the whole spec. This is the path that lost
three stories on 2026-08-19, and it has been dark since it was written.

**Independent Test**: ask the forge for a failing check's evidence with a client
whose `gh` rejects unsupported flags, and assert a real log comes back rather
than a `log unavailable` note.

**Acceptance Scenarios**:

1. **Given** a pull request with a failing required check, **When** the forge
   gathers its evidence, **Then** the returned record carries the check's name,
   its run URL and a non-empty log — proven by a committed test whose fake `gh`
   **refuses any argv the real `gh` would refuse**. A fake that answers every
   command is what let this defect ship, and a test written against one cannot
   fail.
2. **Given** the same, **When** the evidence is rendered into the recovery
   prompt, **Then** the prompt contains the log text — proven by a committed
   test asserting on the assembled prompt string, not on the intermediate record.
   The record being right is what everyone already believed.
3. **Given** a forge call that genuinely fails — a network error, a deleted run —
   **When** evidence is gathered, **Then** the degraded note is still returned
   and still names the reason, exactly as today — proven by a committed test.
   This is the control: a fix that removes the degradation has replaced a silent
   failure with a loud one and lost the reason the degradation exists.
4. **Given** the degraded path is taken, **When** it is taken, **Then** it is
   recorded somewhere an operator can see without opening an agent transcript —
   proven by a committed test asserting the record. A fallback nobody can count
   is how this went undetected for the life of the feature.
5. **Given** a check whose run link cannot be parsed into a run id, **When**
   evidence is gathered, **Then** that check degrades individually and the other
   checks still return their logs — proven by a committed test with two checks,
   one parseable and one not. Today's code already does this per-check; the fix
   must not collapse it to all-or-nothing.
6. **Given** the real host's `gh`, **When** the command this story issues is run
   against a real pull request with a real failing check, **Then** it returns the
   log — proven by pasting the command and its output into the diff. The judge
   sees only the diff; a claim that the command works is not the command working.

---

### User Story 2 - A `gh` command the CLI cannot parse fails the suite (Priority: P1)

As an operator, a command this factory issues to `gh` that `gh` would reject is
caught by the test suite on the day it is written, not by a dead node months
later.

**Why this priority**: P1. US1 fixes two known instances; this is what stops the
third. Two defects of this exact class are live in one module right now, and the
check that catches both is offline, needs no authentication and runs in seconds.

**Independent Test**: run every `GhClient` method's argv past the real `gh` and
assert none is rejected for an unknown flag or unknown command.

**Acceptance Scenarios**:

1. **Given** every command `GhClient` issues, **When** each argv is validated
   against the installed `gh`, **Then** none is rejected as an unknown flag or
   unknown command — proven by a committed test. It must cover **every** method,
   enumerated from the class rather than listed by hand, so a method added later
   is covered without anyone remembering to add it.
2. **Given** a deliberately malformed argv — a flag `gh` does not have — **When**
   the check runs, **Then** it fails, naming the command and the flag — proven by
   a committed test that constructs the bad argv on purpose. **This is the
   mutation control and it is the only thing that proves the check works.** A
   green suite is what shipped the defect; a check that has never been watched
   fail is worth nothing.
3. **Given** a host with no `gh`, or no network, or no authentication, **When**
   the check runs, **Then** it still runs and still catches an unknown flag —
   proven by a committed test. `gh` rejects unknown flags before it does any
   network work, which is what makes this cheap; a check that needs a token will
   be skipped in CI and will be worthless.
4. **Given** the check, **When** it is applied to the tree as it stands, **Then**
   it fails on `pr_checks` and on `create_pr` and on nothing else — proven by
   pasting its output before the fixes. If it fails on more, say so and fix
   those too; if it fails on fewer, it is not catching what it claims.
5. **Given** `create_pr` (`factory/mergequeue/gh.py:172`), which calls
   `_run_json` for a command that emits a URL rather than JSON, **When** the
   check passes, **Then** that call has been corrected too — proven by a
   committed test asserting the corrected behaviour. A story that leaves a known
   red in its own new test has not landed.
6. **Given** a `gh` that is absent from the host entirely, **When** the check
   runs, **Then** it skips by a real guard rather than a marker — proven by a
   committed test. Nothing in this repository passes `-m` in CI or in the gate,
   so a pytest marker is decorative and a marked test is an unrun test.

## Requirements

### Functional Requirements

- **FR-001**: The forge MUST obtain a failing check's name, run URL and log using
  `gh` commands and flags the installed `gh` accepts.
- **FR-002**: A failing required check's log MUST reach the recovery attempt's
  prompt.
- **FR-003**: A genuine forge failure MUST still degrade to a named note rather
  than raise, unchanged from today.
- **FR-004**: Taking the degraded path MUST be observable without reading an
  agent transcript.
- **FR-005**: Per-check degradation MUST remain per-check.
- **FR-006**: Every command `GhClient` issues MUST be validated against the
  installed `gh` by a test, enumerated from the class rather than hand-listed.
- **FR-007**: That validation MUST run without network access, authentication, or
  a repository, and MUST skip by a real guard when `gh` is absent.
- **FR-008**: `create_pr` MUST stop parsing `gh pr create`'s output as JSON.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-006, FR-007, FR-008]
```

Both stories edit `factory/mergequeue/gh.py`. The edge is a contention edge, not
a logical one — US2 does not need US1's behaviour, it needs US1's lines to have
stopped moving. Declaring stories independent while they share a file is the
defect 069/US2 exists to prevent, and it is not committed here.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Paste the new command run against a real pull request with a real
  failing check, and the log it returns, into the diff.
- **SC-002**: Paste the assembled recovery prompt's landing-rejection section for
  that same pull request, showing the log where `log unavailable` used to be.
- **SC-003**: Paste the control — a genuine forge failure still degrading with
  its reason named.
- **SC-004**: Paste the argv check's output against the tree BEFORE the fixes,
  showing it failing on `pr_checks` and `create_pr`.
- **SC-005**: Paste the same check's output after, showing it green.
- **SC-006**: Paste the mutation: introduce a flag `gh` does not have, show the
  check going red and naming it, then remove it.
- **SC-007**: Paste the argv check running with `GH_TOKEN` unset, showing it
  still catches an unknown flag.

## Assumptions

- The installed `gh` on any host running this factory supports `gh pr view
  --json statusCheckRollup`; verified on gh 2.45.0, where each rollup entry
  carries `name`, `conclusion`/`state` and `detailsUrl`, and `_parse_run_id`
  parses that `detailsUrl` unchanged.
- `gh` validates flags before performing network work. This is what makes FR-007
  affordable, and US2-S3 is the test that holds it true.
- The two known malformed calls are the only two. US2-S4 is what turns that
  assumption into a measurement; if the check finds more, they are in scope.
