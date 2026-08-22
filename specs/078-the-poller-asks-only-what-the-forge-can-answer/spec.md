---
state: landed
# Attested landed 2026-08-22. US1 4805fe74244e (#271), US3 2b08a25d64cc (#272),
# US2 c84869bbe578 (#273) -- all three observed on ergane-buildout.
#
# FLIPPED draft -> ready 2026-08-21 8:25 AM CT at the operator's instruction,
# after he read the rendered page. What the pre-dispatch review did, and the one
# thing it caught:
#
#   - ANCHORS: 49, all resolving against `origin/ergane-buildout` at 669006d.
#   - **THE FIRST PASS WAS AGAINST THE WRONG TREE.** Every anchor here was
#     originally verified by printing its line individually -- against the
#     operator checkout at 2776c37, which was FIVE COMMITS BEHIND origin.
#     `workflow.py` had grown 61 lines and `_poll_landing` had moved from 2590 to
#     2641. Across this spec and its three siblings, 36 anchors were wrong. They
#     were re-derived by matching each line's exact TEXT in the origin tree --
#     not by applying an offset, which would have been a guess -- so every
#     citation below is now known to name the same source line the drafter read.
#   - Twelve bare `:NN` references had no filename in their own paragraph. The
#     renderer classes that as ambiguous, and it is right: if the scan cannot
#     resolve the antecedent, neither can an implementer. All are now qualified.
#   - LOAD-BEARING CLAIMS RUN, NOT READ: `gh pr view 1 --json <bad-field>` on
#     gh 2.98.0 exits 1 with `Unknown JSON field:` and no "unknown flag", no
#     "unknown command", no "usage:" -- so `_gh_would_refuse` returns "" and the
#     contract test reports ACCEPTED. That output is pasted in the plan.
#
# Drafted 2026-08-21 ~7:40 AM CT by an operator session, at the operator's
# instruction, immediately before the first PyPI release since v0.1.0 and
# immediately before a repeat of the tharpebox install/build/uninstall
# experiment that produced the field reports of 2026-08-18 and 2026-08-19.
#
# WHY THIS ONE IS A RELEASE BLOCKER AND THE OTHERS ON ITS LIST ARE NOT. Every
# other defect queued behind this release already existed in v0.1.0. This one
# SHIPS WITH THE RELEASE. `baseRefOid` was added to the poller's field set by
# 069-US1, which landed on ergane-buildout on 2026-08-20 -- two days after
# v0.1.0 was cut. A v0.1.0 user who upgrades gets a landing poller that asks
# their `gh` a question their `gh` may refuse, and nothing anywhere -- not
# `install --verify`, not `ergane doctor`, not the suite -- checks whether it
# can answer.
#
# THE PROOF, RUN RATHER THAN READ, on this host at 2026-08-21 07:12 CT against
# gh 2.98.0:
#
#   $ cd /tmp && GH_TOKEN= gh pr view 1 --json definitelyNotAField
#   Unknown JSON field: "definitelyNotAField"
#   Available fields:
#     additions
#     assignees
#     author
#   ...
#   EXIT=1
#
# Lowercase that stderr and look for what the contract test looks for. There is
# no "unknown flag". There is no "unknown command". There is no "usage:". So
# `_gh_would_refuse` (tests/test_gh_argv_contract.py:186-192) returns the empty
# string, which its own caller reads as ACCEPTED. **The check built by 071-US2
# to close exactly this class of defect cannot see the refusal that actually
# happened on 2026-08-20.**
#
# WHAT ACTUALLY HAPPENED ON 2026-08-20, from the operator session that lost the
# evening to it: the host's `gh` was 2.45.0, whose compiled-in `--json` allow-list
# predates `baseRefOid`. `poll_pr` hard-failed. `_poll_landing` is a fire-and-
# forget `asyncio.ensure_future` task (`factory/workgraph/workflow.py:2637`)
# whose exception nothing observes -- `self._landing_tasks` is only ever iterated
# to CANCEL on kill (`:1369-1371`). So the poller died, no timer was left behind,
# the node sat at `ENQUEUED` forever, and `ergane build status` reported
# `ENQUEUED` the entire time. Two epics were parked before anyone looked at the
# forge by hand.
#
# THE APT DETAIL, because it will happen to the next operator too: adding
# GitHub's own apt repository silently no-ops on Ubuntu Pro, because the ESM pin
# (priority 510) outranks cli.github.com (500) and apt keeps reporting "already
# newest version". The fix that worked without root was `apt-get download
# gh=2.98.0`, `dpkg-deb -x`, binary into `~/.local/bin`. **Verify a CLI upgrade
# by running the command, never by reading `gh --version` from a shell whose
# PATH you have not checked.**
#
# WHAT IS NOT WRONG, so that no implementer rebuilds it:
#   - `baseRefOid` itself. 069-US1 needs it; without it every landing rejection
#     reads as the node's own fault and the free rebase never fires. Removing the
#     field to make the poller work is the wrong remedy and would silently undo a
#     landed story.
#   - `_run_json` (`factory/mergequeue/gh.py:461`). It correctly reports that it
#     got something that is not JSON. Loosening it converts one loud failure into
#     silence at every call site, including the correct ones.
#   - The evidence chain 025 and 071 built. Untouched here.
#
# Filed as:
#   mergequeue/the-gh-argv-contract-test-classifies-a-rejected-json-field-as-
#     acceptance-so-a-dead-poller-ships-green   (critical, open)
---

# Feature Specification: the poller asks only what the forge can answer

## The gap, stated precisely

The factory's landing poller asks `gh` for a fixed set of `--json` fields. `gh`
validates those field names against an allow-list compiled into the binary, so
the same command that works on one machine is refused on another purely because
of which `gh` is installed. When it is refused the poller dies, and it dies in
the one shape the factory cannot see: a background task whose exception nobody
reads, leaving a node reporting `ENQUEUED` with nothing polling it and no timer
that will ever fire.

Three separate defences should have caught this and all three are blind:

| Defence | What it checks | Why it missed |
| --- | --- | --- |
| The argv contract test (071-US2) | that `gh` accepts each argv | classifies refusals by matching stderr prose; a refused field says none of the three phrases |
| `install --verify` / `doctor` | the control plane | neither has ever looked at `gh` at all |
| `ergane build status` | node state | reads the record, and the record still says `ENQUEUED` |

## Why the prose classifier is the root defect and the field is not

It would be possible to close today's instance by pinning a minimum `gh` version
and stopping. That leaves the next field, the next flag and the next subcommand
exactly as invisible as this one was, and it leaves a test in the tree that
reports green on a refusal it watched happen. `gh` tells the truth in its exit
code every time; the test throws that away and re-derives a worse answer from
prose that varies by version, by locale and by subcommand.

## What this spec does not change

- The field set. `baseRefOid` stays. If a host's `gh` cannot answer, the remedy
  is to tell the operator, not to ask for less.
- `_run_json`, `poll_pr`'s parsing, or `PrSnapshot.from_gh_json`.
- The classifier, the rejection causes, or anything 069 landed.
- The recovery ladder or any budget.

## User Scenarios & Testing

### User Story 1 - A refused `gh` command fails the suite (Priority: P1)

As an operator, any command this factory issues that the installed `gh` refuses
— for any reason, not only an unknown flag — is caught by the test suite,
because the suite reads `gh`'s exit code instead of guessing from its prose.

**Why this priority**: P1 and it is the foundation. Until the check can see a
refusal, every other story here is a fix whose regression is undetectable.

**Independent Test**: run the contract check against an argv naming a `--json`
field the installed `gh` does not have, and assert the check fails.

**Acceptance Scenarios**:

1. **Given** an argv the installed `gh` refuses with a non-zero exit and a
   message matching none of "unknown flag", "unknown command" or "usage:",
   **When** the contract check classifies it, **Then** it is classified as a
   refusal — proven by a committed test using a real refused `--json` field.
2. **Given** an argv `gh` accepts but which cannot complete without credentials,
   **When** the check classifies it, **Then** it is classified as accepted —
   proven by a committed test. `gh` exits 4 when it needs authentication and
   that must stay a pass, or the check is unrunnable in CI. **This is the
   control**: a check that denies everything is as useless as one that accepts
   everything, and it is the easier of the two mistakes to make while fixing
   this.
3. **Given** the exact field set the poller sends (`factory/mergequeue/gh.py:68`),
   **When** the check runs, **Then** that field set is validated as a set, by
   the same code path the poller uses to build it — proven by a committed test.
   Enumerating methods is not enough: 071-US2 did enumerate them, and the
   argument it could not read was inside one of them.
4. **Given** the tree as it stands, **When** the corrected check is run against
   it with a `gh` old enough to refuse `baseRefOid`, **Then** it fails and names
   the field — proven by pasting the run. If no such `gh` is available on the
   host, simulate the refusal at the classifier boundary and say in the diff
   that that is what was done.
5. **Given** a host with no `gh`, no network and no token, **When** the check
   runs, **Then** it still runs and still catches a refused field — proven by a
   committed test. `gh` validates field names before it authenticates.
6. **Given** `gh` is absent from the host entirely, **When** the check runs,
   **Then** it skips on a real runtime condition rather than a `pytest` marker —
   nothing in this repository passes `-m` in CI or in the gate, so a marked test
   is an unrun test.

---

### User Story 2 - The operator learns their `gh` cannot answer before they dispatch (Priority: P1)

As an operator installing Ergane on a new host, a `gh` that cannot answer the
poller's questions is named as a refusal during install verification, with the
field and the remedy, rather than discovered as a parked epic hours later.

**Why this priority**: P1. US1 protects this repository's suite. This protects
the person who installed the release, on a host whose `gh` nobody chose. The
suite passing on the maintainer's machine is exactly the evidence that was
available on 2026-08-20 and it was worth nothing.

**Independent Test**: point the check at a `gh` that refuses one of the poller's
fields and assert install verification refuses by name.

**Acceptance Scenarios**:

1. **Given** an installed `gh` that refuses one of the poller's `--json` fields,
   **When** the operator runs install verification, **Then** it reports a
   failure naming the field, the installed version and what to do about it —
   proven by a committed test.
2. **Given** an installed `gh` that accepts every field, **When** verification
   runs, **Then** it passes and says which `gh` answered — proven by a committed
   test. A green line that does not say what it checked is how the last three
   readiness defects survived; see `verify/readiness-proves-a-thing-is-declared-
   not-that-it-works`.
3. **Given** no `gh` on the host at all, **When** verification runs, **Then** it
   reports a distinct, named condition rather than the same failure as a refused
   field — proven by a committed test. Absent and incapable are different
   remedies.
4. **Given** the check, **When** it runs, **Then** it exercises the actual field
   set the poller sends rather than a copy of it — proven by a committed test
   that changes the field set and watches the check follow. A second hand-written
   list is the defect this spec exists to end.
5. **Given** the real host, **When** the operator runs verification, **Then**
   paste its output into the diff, for a passing `gh` and for a refused one.
   Producing the refused case may mean pointing the check at a stub `gh` on
   `PATH`; that is acceptable and must be stated in the diff.

---

### User Story 3 - A landing poll that dies is visible (Priority: P1)

As an operator, a landing poller that stops for any reason leaves a node whose
state says so, rather than a node that reads `ENQUEUED` forever.

**Why this priority**: P1. US1 and US2 close today's cause. This closes the
shape that made the cause cost an evening: the factory could not tell the
difference between "the queue is still thinking" and "nothing is watching this
pull request any more".

**Independent Test**: make the poll activity raise, and assert the node's
reported state changes and names the reason.

**Acceptance Scenarios**:

1. **Given** a node whose landing poll activity raises, **When** the epic is
   asked for its status, **Then** the node does not report `ENQUEUED` — proven
   by a committed test.
2. **Given** the same, **When** the operator reads the status, **Then** the
   reason the poller stopped is named — proven by a committed test asserting the
   rendered status text, not the internal record.
3. **Given** a poll that fails once transiently and succeeds on the next beat,
   **When** it recovers, **Then** the node continues to land normally and no
   operator-visible failure is raised — proven by a committed test. **This is the
   control.** A remedy that treats one slow forge call as a dead poller has
   traded a silent hang for a false alarm on every network hiccup.
4. **Given** a kill arriving while a poller is being torn down, **When** the epic
   stops, **Then** the existing cancel-on-kill path behaves exactly as it does
   today (`factory/workgraph/workflow.py:1369-1371`) — proven by a committed
   test. This is the second control.
5. **Given** the failure path, **When** an implementer changes it, **Then** the
   diff does not convert a background poller into a foreground await. Riding the
   landing in the background is deliberate and load-bearing; the defect is the
   unobserved exception, not the concurrency.

## Requirements

### Functional Requirements

- **FR-001**: The `gh` argv contract check MUST classify a refusal by the
  process exit status, not by matching text in stderr.
- **FR-002**: The check MUST treat `gh`'s authentication-required exit as
  acceptance, so that it remains runnable with no token and no network.
- **FR-003**: The check MUST validate the `--json` field set the poller actually
  sends, derived from the same value the poller sends, not a copy.
- **FR-004**: The check MUST skip on a real runtime condition when `gh` is
  absent, never on a `pytest` marker.
- **FR-005**: Install verification MUST refuse, naming the field and the
  installed `gh` version, when the installed `gh` cannot answer the poller's
  field set.
- **FR-006**: Install verification MUST report an absent `gh` as a distinct
  named condition from an incapable one.
- **FR-007**: A passing `gh` capability check MUST state what it verified and
  which binary answered.
- **FR-008**: A node whose landing poller has stopped MUST NOT report a state
  that implies it is still being polled.
- **FR-009**: The reason a landing poller stopped MUST be readable from operator
  status output.
- **FR-010**: A transient poll failure MUST NOT be reported as a stopped poller.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004]
  persona: opus-closer
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-005, FR-006, FR-007]
  persona: opus-closer
US3:
  depends_on: []
  implements: [FR-008, FR-009, FR-010]
  persona: opus-closer
```

US1 and US2 both reach the poller's field set — US1 to validate it, US2 to
exercise it — so US2 waits for US1's lines to stop moving. The edge is
contention, not logic. US3 touches only the workflow and its own test, and
shares no file with either.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Paste the corrected contract check refusing a real bad `--json`
  field, showing the refusal it now sees.
- **SC-002**: Paste the control: an argv `gh` accepts but cannot complete
  without credentials, still classified as accepted.
- **SC-003**: Paste the check running with no token and outside any git
  repository, still catching a refused field.
- **SC-004**: Paste install verification failing against a `gh` that refuses a
  poller field, naming the field and the version.
- **SC-005**: Paste install verification passing against this host's `gh`, and
  the line that says which binary answered.
- **SC-006**: Paste the mutation for FR-003: change the poller's field set, run
  the check unchanged, and show it following the change.
- **SC-007**: Paste a node whose poller raised, showing the status output that
  now names it, alongside the same status before the change.

## Assumptions

- `gh` validates `--json` field names before performing network work or
  authenticating. Verified on gh 2.98.0 on 2026-08-21: exit 1 and the field
  list, with `GH_TOKEN` empty, outside any repository.
- `gh` exits 4 when a command is well-formed but unauthenticated. This is what
  071-US2 relied on and it is unchanged.
- The field set is the only version-sensitive part of the poller's argv today.
  US1-S3 is what turns that from an assumption into a measurement; if the check
  finds more, they are in scope.
</content>
</invoke>
