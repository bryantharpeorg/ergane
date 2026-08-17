---
state: landed
# Attested landed 2026-08-17 by an operator session, after `ergane spec landed
# specs/022-validate-calibration --default-branch ergane-buildout` observed its
# single story in git: US1 8ab5e61a223c. Factory-dispatched overnight via
# `ergane build start` on the delta graph, first attempt: real bwrap gate PASS
# and judge PASS inside the epic workflow, landed by the merge queue as PR #160.
# specs_root: specs
# target_repo: /home/admin/code/ergane-019-target
#
# Scaffolded 2026-08-09 11:10 PM CT by `ergane findings promote` from
# cli/scenario-coverage-fails-every-spec, then refined the same night. Second
# spec the ledger has ever produced; 010 was the first.
#
# This spec exists because of a requirement I wrote badly. FR-023 was added to
# 019 at 7:30 PM on 2026-08-09, nine hours after 020's us2 burned two attempts
# and the debugger rung on a scenario demanding an end-to-end `derive_delta`
# test that appeared zero times in its tasks file. The requirement generalised
# that single failure into a hard exit-1 rule, against a convention no tasks.md
# in the corpus has ever followed. 019's us2 implemented it faithfully and it
# landed clean. The defect is the requirement, not the code.
#
# The operator picked the fix from three options at 11:05 PM: demote, rather
# than backfill scenario references across seventeen tasks.md files, or narrow
# the rule to identifiers named in a scenario but absent from tasks.md. The
# narrowing is the better check and is deliberately NOT in scope here; it is a
# design problem worth its own spec, and this one is a calibration.
#
# Numbered 022: 010-014 stay reserved for audit-triage epics, 015 doctor, 016
# delta, 017 peer channel, 018 agent home isolation, 019 operator CLI, 020
# landing attribution, 021 roadmap operability.
depends_on_landed: [019-operator-cli]
---

# Feature Specification: `spec validate` Calibration

**Feature Branch**: `022-validate-calibration`

**Created**: 2026-08-09

**Status**: Drafted the night 019 landed, against the landed tree at `a10ab55`.

**Input**: One measurement. `ergane spec validate` exits 1 on **every spec in
the repository**, including 019, the spec that introduced the check:

| spec | unreferenced scenarios | exit |
| --- | --- | --- |
| 019-operator-cli | 31 | 1 |
| 016-delta-derivation | 20 | 1 |
| 021-roadmap-operability | 19 | 1 |
| 007-parallel-dispatch | 15 | 1 |
| 020-landing-attribution | 12 | 1 |
| 010-interpreter-bugfixes | 9 | 1 |

019's own `tasks.md` names exactly two scenario ids — `US1-S1` and `US1-S2` —
out of thirty-three the spec declares. Seventeen of seventeen specs fail.

A gate that refuses everything teaches operators to skip it, and a skipped gate
is worse than an absent one because it still costs the run time and still
appears in the report. The signal is worth keeping; the verdict is not.

## The distinction this spec turns on

`_check_scenario_coverage` at `factory/cli/nouns/spec.py:457` produces **two
different findings** through the same layer name, and they do not deserve the
same treatment:

- **A missing `tasks.md`** (`spec.py:396-403`). This is a structural defect. A
  spec with no task list cannot be implemented by anyone, and no convention
  about scenario references is involved. It stays exit 1.
- **Declared scenarios no task references** (`spec.py:408-414`). This is an
  advisory about a convention the corpus does not follow. It becomes reporting
  only.

Collapsing both into "scenario_coverage is now a warning" would silently retire
a real check. That is the single most likely way to get this spec wrong.

## User Scenarios & Testing

### User Story 1 - A coverage advisory that reports without refusing (Priority: P1)

An operator runs `ergane spec validate` on a spec before dispatching it. The
command names every acceptance scenario no task references, because that gap
has demonstrably cost a full attempt ladder, and it still exits 0 when that is
the only thing it found. The three checks that describe a spec the factory
genuinely cannot compile — frontmatter, work-graph derivation, persona registry
— keep the exit-1 verdict they have today, as does a spec with no `tasks.md`
at all.

**Why this priority**: There is one story because there is one file and one
decision. Splitting it would produce two nodes contending on
`factory/cli/nouns/spec.py`, which is a collision rather than a fan-out.

**Independent Test**: Run the command against this repository's own corpus.
Every spec that exits 1 today for scenario reasons alone exits 0 and still
prints its uncovered ids; every spec with a frontmatter, derivation or persona
defect still exits 1.

**Acceptance Scenarios**:

1. **Given** a spec whose only defect is acceptance scenarios no task
   references, **When** the operator runs `ergane spec validate` on it,
   **Then** the uncovered scenario ids are printed and the command exits 0.
2. **Given** that same spec, **When** the operator runs the command with
   `--json`, **Then** each finding in the report carries a severity field
   distinguishing an advisory from a refusal, and the document is otherwise
   unchanged.
3. **Given** a spec directory with no `tasks.md` at all, **When** the operator
   runs the command, **Then** it names the missing file and exits 1, because a
   spec with no task list is a structural defect and not a convention gap.
4. **Given** a spec with a frontmatter defect and uncovered scenarios together,
   **When** the operator runs the command, **Then** both findings are printed
   and the command exits 1, because the refusal-severity finding decides the
   verdict regardless of how many advisories accompany it.
5. **Given** a spec with no defects of any kind, **When** the operator runs the
   command, **Then** it prints its existing success line and exits 0.
6. **Given** this repository's own `specs/` corpus, **When** the operator runs
   the command over every spec directory in it, **Then** no spec exits 1 for
   uncovered scenarios alone.

## Functional Requirements

- **FR-001**: A validate finding MUST carry a severity distinguishing a
  **refusal** (the spec cannot be compiled or dispatched) from an **advisory**
  (worth reading before dispatch, not worth blocking on).
- **FR-002**: The command's exit code MUST be 1 when at least one refusal
  finding is present and 0 otherwise, regardless of how many advisories are
  present.
- **FR-003**: Uncovered acceptance scenario ids MUST be reported as an
  advisory.
- **FR-004**: A missing `tasks.md` MUST remain a refusal. It is reported
  through the same layer as FR-003 today and MUST NOT be demoted with it.
- **FR-005**: Frontmatter, work-graph derivation and persona-registry findings
  MUST remain refusals.
- **FR-006**: Advisory findings MUST be visually distinguishable from refusals
  in the human output, so that a reader can tell why a command that printed
  findings still exited 0.
- **FR-007**: The `--json` report MUST expose the severity of each finding. It
  remains a dump of what the command computed and MUST NOT re-derive or
  re-shape the document around the new field.
- **FR-008**: Every acceptance scenario in this spec MUST be referenced by at
  least one task in this spec's `tasks.md`, so that 022 passes the check it is
  calibrating.

## Assumptions

- The advisory is worth keeping at all. The alternative — deleting the check —
  was not chosen, because the gap it names cost 020's us2 two attempts and the
  debugger rung, and the judge caught it only after the money was spent.
- Narrowing the rule so that it fails on identifiers named in a scenario but
  absent from `tasks.md` is a better check than either the current one or this
  one. It is out of scope here and wants its own spec.
- No `tasks.md` in the corpus is edited by this spec. Backfilling scenario
  references across seventeen specs was explicitly declined.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005, FR-006, FR-007, FR-008]
```
