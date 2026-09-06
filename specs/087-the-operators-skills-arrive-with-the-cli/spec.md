---
state: draft
# DRAFTED 2026-08-22 ~10:15 PM CT in the operator session, immediately after
# 838b9c3 removed the two vendored third-party skill collections. That commit
# answered "what should this repository stop shipping". This spec answers the
# question it left open: how the five skills Ergane *does* own reach the
# operator who installs `ergane-cli`.
#
# NOT REFINED. No anchor sweep has been run against this tree. Every file:line
# below was read on 2026-08-22 and is a starting point for refinement, not a
# verified citation. Refine before dispatch.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04-tail, cross-batch): a completeness
# critic read this directory against the rest of the batch and found it held
# spec.md alone. The refinement this file's own hold asks for had never reached
# disk: no plan.md, no tasks.md, and `ergane spec validate` refusing five ways —
# tasks.md missing, plan.md and tasks.md unreadable ("no node of this epic can be
# handed a prompt until it is there"), and two dead anchors. plan.md and tasks.md
# are now written, every citation in all three files was re-read from
# ergane-buildout at 602a92c, and the hold above is DISCHARGED by this entry
# rather than deleted: provenance is appended to, so the sentence that says no
# sweep has been run stays where it was written and this line is what supersedes
# it. state stays draft.
#
# WHERE THIS CAME FROM. 838b9c3 removed two vendored third-party skill
# collections from `.claude/skills/` and left the question of Ergane's own
# skills unanswered. The operator was asked on 2026-08-22 who the skills are
# for and answered: "i want them for the operator using them not for the
# agents." That answer is the ruling in § "What this spec is not", and it is
# the reason this spec has no target-repository story.
#
# WHAT IT COST, MEASURED. Nothing has failed yet, and that is the finding. A
# stranger who runs `pip install ergane-cli` gets the CLI and no skills, gets no
# error either, and has nothing in the tree telling them six operator tools
# exist. The one guard that catches a missing payload — `unzip -l | grep` in the
# release workflow — knows about a single file. Measured at 602a92c: six skill
# directories, 208 KB on disk, against a wheel the same repository builds at
# roughly 766 KB. Size is not the decision that needs making.
#
# THE SWEEP MOVED TWO ANCHORS AND ONE FACT. `factory/workgraph/adapter.py:339`,
# cited for the per-node factory-owned HOME, is a BLANK line at 602a92c — the
# surrounding code is now `HostAgentBackend`. The construction it meant is
# `factory/workgraph/adapter.py:815` — `home_path`, carried into the child at
# `factory/workgraph/adapter.py:971` — `attempt_env`; both are written in the
# machine-checked symbol form below so the next drift is caught by validate
# rather than by an implementer. `release.yml:61` resolved to no file: the
# workflow is `.github/workflows/release.yml` and its payload guard has since
# moved to line 83. `pyproject.toml:66-67` is now comment prose; the
# `force-include` table starts at `pyproject.toml:80`.
#
# AND THE PAYLOAD GREW. This file was drafted against five skills. At 602a92c
# there are SIX — `findings-ingest` landed with 8edc028 — so a spec that says
# "five" hands an implementer a wrong payload set and a hard-coded count that
# will rot again. The enumeration is corrected, the count is stated as a fact
# about the tree rather than a constant, and FR-001 now names the directory
# rather than a number. plan.md trap 7 is the reproduction, and US1-S1's
# Then is written against the directory the repository ships rather than
# against a number a test would have to be edited to keep true.
#
# HOUSE STYLE, FROM 126 ONWARD. `## Success Criteria` and `## Assumptions` are
# dropped and their content folded: SC-001 and SC-005 became operator
# verification steps in plan.md, SC-002/003/004/006 were already scenarios or
# became US2-S5 and US4-S4, and the three assumptions became § "What this spec
# is not" and plan.md traps 8 and 9. `### Edge Cases` is gone the same way — the
# collision case is now FR-013 and a row of the truth table, the XDG and
# `uv tool install` cases are trap 8. The five traps moved to plan.md, where
# traps live, and gained five more.
#
# NOT IN SCOPE, AND ONE NARROWING WRITTEN FROM THE OTHER SIDE. This spec still
# installs nothing into a target repository and nothing a dispatched node can
# read. `specs/139-a-scaffolded-repo-arrives-with-the-context-its-agents-need`
# supersedes that ruling for the target-repository agent-context unit ALONE, in
# writing, three times in its own trio, and defers the reciprocal note to "when
# 087 is next refined". This is that refinement, so the note is written here: §
# "What this spec is not" and plan.md trap 6 carry it. FR-010 is UNCHANGED and
# still governs this spec's own scope, which is the operator's home and nothing
# else. The two share no file.
---

# Feature Specification: the operator's skills arrive with the CLI

**Created**: 2026-08-22
**Depends on**: nothing. It reads packaging and teardown machinery that is
already landed, and no other spec's work.

## The gap, stated precisely

Ergane owns six Claude Code skills. All six exist only in this repository's own
`.claude/skills/`, which means exactly one person on earth can use them: the
operator working inside a clone of this repo.

The chain is five short steps, and nothing in it raises:

1. The six are committed files under a dot-directory —
   `.claude/skills/away-mode/SKILL.md:1`,
   `.claude/skills/build-metrics/SKILL.md:1`,
   `.claude/skills/escalation-triage/SKILL.md:1`,
   `.claude/skills/findings-ingest/SKILL.md:1`,
   `.claude/skills/floor-status/SKILL.md:1` and
   `.claude/skills/spec-html/SKILL.md:1`. Six is a fact about the tree at
   602a92c, not a constant: it was five on 2026-08-22 and `findings-ingest`
   landed with 8edc028.
2. A wheel carries what lives inside the `factory` package plus exactly what the
   force-include table at `pyproject.toml:80` names, and that table's four
   entries are `personas.example.yaml`, two container artifacts and
   `default_floor.md` (`pyproject.toml:81-84`). `.claude/skills/` is neither
   inside the package nor in the table.
3. So there is nothing to resolve, and no resolver that would look. The two that
   exist are `factory/config.py:98` — `_resolve_default_registry_path`, which
   resolves one packaged **file**, and `factory/stack_packs.py:196` —
   `resolve_stack_packs`, which resolves one packaged **directory**. Neither
   knows the word.
4. Someone who runs `pip install ergane-cli` therefore gets the CLI and none of
   the skills. They get no error either — there is nothing to fail — and nothing
   in the installed tree tells them six operator tools exist and are absent.
5. The guard that exists for exactly this failure sees one file:
   `.github/workflows/release.yml:83` greps the built wheel for
   `factory/personas.yaml` and fails the release when it is missing. A payload
   that never shipped in the first place is invisible to it.

This is not a packaging oversight to be quietly patched. It is the difference
between shipping a CLI and shipping the way the CLI is meant to be driven:

- `floor-status` — what the floor is doing now, with an ETA table from measured
  cycle times
- `escalation-triage` — turns an open escalation into a decision brief
- `build-metrics` — LOC, commit-size distribution, story rework rate
- `spec-html` — renders a spec trio as one page with anchors resolved live
- `findings-ingest` — absorbs an external corpus into the doctor's ledger as
  identity-keyed findings
- `away-mode` — a self-paced loop that keeps the floor moving unattended

## The rule this spec is asking for

**Every skill this repository ships travels inside the wheel; one verb puts them
under the operator's own agent configuration and names where it put them; and
neither that verb nor teardown ever overwrites or deletes a file the operator
has changed.**

The install verb's cases, complete. The comparison is against a record of what
Ergane last wrote, never against a timestamp:

| at the destination | Ergane's record | result |
|---|---|---|
| absent | — | **written**, reported as installed |
| present, bytes match the record | present | **no-op**, reported as current |
| present, bytes match the record, shipped bytes differ | present | **rewritten**, reported as updated |
| present, bytes differ from the record | present | **left untouched**, reported as kept, with the deliberate way to take the new version named |
| present | **absent** — Ergane never wrote it | **left untouched**, reported as a collision |

Teardown reads the same record and answers the same way: what matches is
removed, what differs is kept and named, what Ergane never wrote is never
touched.

### What this spec is not

**Dispatched agents are out of scope, deliberately and by ruling.** The operator
was asked directly on 2026-08-22 and answered: *"i want them for the operator
using them not for the agents."*

This matters because the mechanism makes the two genuinely different features.
`personas.yaml:31-36` records the finding from 062/US3: the factory constructs a
per-node, factory-owned HOME at dispatch — `factory/workgraph/adapter.py:815` —
`home_path` derives it and `factory/workgraph/adapter.py:971` — `attempt_env`
hands it to the child — so a skill installed under the operator's
`$HOME/.claude/skills/` is **invisible to every dispatched node**. Only skills
committed at `<repo>/.claude/skills/` reach an agent, because worktrees carry
committed files. So an implementer who "helpfully" adds a `--repo` target is not
extending this spec, they are building the other one. A story here that writes
into a target repository is a defect even if it works.

**One narrowing of that ruling is already written, from the other side.**
`specs/139-a-scaffolded-repo-arrives-with-the-context-its-agents-need` states in
its frontmatter, in its own § "What this spec is not"
(`specs/139-a-scaffolded-repo-arrives-with-the-context-its-agents-need/spec.md:216`)
and in its plan
(`specs/139-a-scaffolded-repo-arrives-with-the-context-its-agents-need/plan.md:305`)
that it supersedes the sentence above for the **target-repository agent-context
unit alone**. 087 keeps the operator-side install; 139 owns what a scaffolded
repository arrives with. They share no file: this spec writes under the
operator's own `$HOME`, 139 under `<repo>/.claude/`. FR-010 below is unchanged
and binds this spec's own scope. An implementer who meets 139's work and reads
it as a contradiction of FR-010 has found a narrowing that is already written
down, not a defect.

**It is not a second resolution mechanism.** The packaged-data pattern exists
twice already and this spec copies it rather than inventing a third.

**It is not a front-end abstraction.** The destination is Claude Code's
`~/.claude/skills/`, because that is the agent the operator runs. If Ergane
later supports another front-end the destination becomes a function of the
front-end and this spec's single destination becomes a defect — worth naming,
out of scope here.

**It is not a licensing question.** The six skills are Ergane's own work and
carry no third-party obligation, true as of 838b9c3, which removed everything
that did.

## User Scenarios & Testing

### User Story 1 - The skills ship inside the wheel (Priority: P1)

As an operator who installed `ergane-cli` from PyPI, the skills are present in my
installation, so that a verb has something to install from.

**Why this priority**: P1 and first. Every other story reads what this one
ships. Landed alone it changes no behaviour an operator can see, which is the
point — it is inert payload until US2 exists.

**Independent Test**: build the wheel, read its listing, and confirm every
skill directory the repository ships is inside it with its `SKILL.md`.

**Acceptance Scenarios**:

1. **Given** a wheel built from this tree, **When** its contents are listed,
   **Then** every skill directory the repository ships is inside it, each with
   its `SKILL.md` and any scripts and reference files it depends on, and no
   `__pycache__` entry travels with them — proven by a committed test that reads
   a built wheel rather than the build configuration, and by pasted `unzip -l`
   output.
2. **Given** the release workflow's wheel validation step
   (`.github/workflows/release.yml:68`), **When** a wheel is built with a skill
   missing, **Then** validation fails and nothing is published — the guard at
   `.github/workflows/release.yml:83` extended to the skills payload, proven by
   a committed test asserting the guard names the skills path, and by pasted
   output of the failing check run against a deliberately stripped wheel.
3. **Given** a development checkout with no wheel built, **When** the resolver
   runs, **Then** it returns the same skills from their source location, by the
   same checkout fallback `factory/config.py:98-101` uses. **The control**: this
   is green from the first commit and must not be made to fail.

### User Story 2 - One verb puts them where the operator's agent looks (Priority: P1)

As an operator, I run one command and the skills appear in my own Claude Code
configuration, so that I can drive the factory the way it was meant to be driven.

**Why this priority**: P1. This is the feature; US1 is its substrate.

**Independent Test**: point the verb at a scratch home with no Ergane skills in
it, run it, and read what landed and what it reported.

**Acceptance Scenarios**:

1. **Given** an operator home with no Ergane skills installed, **When** the verb
   runs, **Then** every shipped skill is written under that home's agent
   configuration and each is named as it is written — proven by a committed test
   over a temporary home and by pasted output of a real run.
2. **Given** a skill installed earlier and since changed on disk, **When** the
   verb runs again, **Then** that skill is **not** overwritten: it is named,
   kept, and the output states how to take the new version deliberately, while
   the unchanged skills beside it are handled normally.
3. **Given** every installed skill matching the record and the shipped bytes,
   **When** the verb runs again, **Then** it reports a no-op naming each skill as
   current, rather than reporting writes it did not perform.
4. **Given** any run, **When** it completes, **Then** the absolute destination
   directory is printed. An operator must never have to guess which of several
   plausible configuration directories was written to.
5. **Given** a file at the destination with a shipped skill's name that Ergane
   has no record of writing, **When** the verb runs, **Then** it is left
   untouched and reported as a collision naming the path, and the run does not
   fail for the skills beside it.
6. **Given** `CONTEXT.md`, **When** this story lands, **Then** its § "Flagged
   ambiguities" (`CONTEXT.md:212`) carries an entry distinguishing the reserved
   per-persona `skills` field from the operator tooling, in the shape the
   `promote` entry at `CONTEXT.md:243-248` already uses, and the verb's name
   agrees with that ruling.
7. **Given** `README.md`, **When** this story lands, **Then** it tells an
   operator these skills exist and names the command that installs them, and
   every path it cites resolves — `tests/test_readme.py:107` —
   `test_every_path_the_file_cites_exists` and `tests/test_readme.py:50` —
   `test_every_command_the_file_names_parses` both run over the file.

### User Story 3 - The install says whether it is current (Priority: P2)

As an operator who upgraded `ergane-cli`, I can ask whether my installed skills
match the CLI I am now running, so that I do not debug a skill calling a flag
that no longer exists.

**Why this priority**: P2. The failure it prevents is real and confusing — a
skill shelling out to a CLI it predates — but it is a diagnosis aid, not the
feature.

**Independent Test**: write a record naming one package version, run the check
against a CLI reporting another, and read what it names.

**Acceptance Scenarios**:

1. **Given** skills recorded as installed from one package version and a CLI
   reporting another, **When** the check runs, **Then** it names both versions
   and says which skills are stale — keyed on the package version from
   `factory/supervision/engine_identity.py:38` — `cli_version`, never on the
   revision string.
2. **Given** skills recorded as installed from the running package version,
   **When** the check runs, **Then** it reports current and states the directory
   it looked in.
3. **Given** no skills installed at all, **When** the check runs, **Then** it
   says so plainly and names the verb that would install them — rather than
   erroring, and rather than reporting zero stale skills, which is technically
   true and useless.

### User Story 4 - Teardown removes what install wrote (Priority: P2)

As an operator running `ergane uninstall`, the skills this factory wrote into my
agent configuration are accounted for, so that "Ergane is off this host" is true.

**Why this priority**: P2 by sequence, not by importance. It cannot be built
before US2 has written anything, and it is the story that keeps 083's promise
from becoming false.

**Independent Test**: seed a record and matching files under a scratch home, run
teardown, read the lines; run it again against the emptied home and read them
again.

**Acceptance Scenarios**:

1. **Given** installed skills matching the record, **When** teardown runs,
   **Then** they are removed and named in its output using the existing
   `_kept` / `_removed` vocabulary (`factory/cli/uninstall.py:609` — `_kept`,
   `factory/cli/uninstall.py:613` — `_removed`) — consistent with every other
   step, not a new dialect.
2. **Given** a skill the operator modified after installing, **When** teardown
   runs, **Then** it is **kept and named as kept** with its reason, not removed
   — the operator's edits are theirs.
3. **Given** no installed skills, **When** teardown runs, **Then** the step says
   it had nothing to do, as every other teardown step does.
4. **Given** installed skills and `ergane uninstall --check`, **When** the survey
   runs, **Then** the skills step names what it would remove and what it would
   keep, before anything is removed — the disclosure `StepSurvey`
   (`factory/cli/uninstall.py:160` — `StepSurvey`) exists to make, proven by a
   committed test and by pasted `--check` output.

## Functional Requirements

- **FR-001**: Every skill directory the repository ships under `.claude/skills/`
  MUST be included in the built wheel as package data, by the same
  `force-include` mechanism `pyproject.toml:80-84` already uses for the persona
  registry and the container artifacts. The requirement names the directory, not
  a count: the payload was five skills on 2026-08-22 and is six at 602a92c.
- **FR-002**: Resolution MUST use `importlib.resources` against the `factory`
  package with a development-checkout fallback, following
  `factory/stack_packs.py:196` — `resolve_stack_packs` for the directory case and
  `factory/config.py:98-101` for the fallback. A third mechanism MUST NOT be
  introduced.
- **FR-003**: The release workflow MUST fail the build when any shipped skill is
  absent from the wheel, in the same validation step as the existing payload
  guard at `.github/workflows/release.yml:83-86`.
- **FR-004**: A single verb MUST install every shipped skill into the operator's
  agent configuration and MUST print the absolute destination. The destination
  MUST be derived from the operator's home, not from where the package was
  installed, and MUST be created when it does not exist.
- **FR-005**: The verb MUST NOT overwrite a skill whose on-disk content differs
  from what Ergane last wrote. It MUST name it, keep it, and state how to take
  the new version deliberately.
- **FR-006**: The verb MUST be idempotent: a second run with nothing changed MUST
  report a no-op naming each skill as current rather than reporting writes.
- **FR-007**: A check MUST report installed-versus-running staleness **by package
  version**, read from `factory/supervision/engine_identity.py:38` — `cli_version`.
  It MUST NOT key on the revision string, which is `unknown` on every packaged
  install (`factory/cli/main.py:132-144`).
- **FR-008**: The check MUST distinguish *no skills installed* from *all skills
  current*, and name the install verb in the first case.
- **FR-009**: `ergane uninstall` MUST account for installed skills as a declared
  step in the table at `factory/cli/uninstall.py:933`, using the existing
  disclosure vocabulary, MUST keep any the operator has modified, and MUST
  survey them on `--check` before removing anything.
- **FR-010**: This feature MUST NOT write into a target repository or into a
  dispatched node's HOME. Operator scope only: a path that installs a skill
  anywhere a dispatched agent could read it MUST be refused.
- **FR-011**: Before any verb name is landed, the collision with the reserved
  per-persona `skills` field (`personas.yaml:42`, `factory/config.py:363` —
  `_skills`, locked by `tests/test_062_us3_skills.py:28` —
  `test_skills_field_is_documented_as_reserved_and_construction_sites_are_explained`)
  MUST be resolved in `CONTEXT.md` § "Flagged ambiguities" (`CONTEXT.md:212`) —
  either by distinguishing the two senses explicitly or by choosing a name that
  does not collide.
- **FR-012**: `README.md` MUST tell an operator these skills exist and how to
  install them. `tests/test_readme.py:107` —
  `test_every_path_the_file_cites_exists` resolves every path the file cites and
  `tests/test_readme.py:50` — `test_every_command_the_file_names_parses` parses
  every command, so any path named there must exist and any command must parse.
- **FR-013**: A file at the destination bearing a shipped skill's name that
  Ergane has no record of writing MUST be left untouched by both the verb and
  teardown, and named as a collision. Never clobber what this factory did not
  write.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-004, FR-005, FR-006, FR-010, FR-011, FR-012, FR-013]
US3:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-007, FR-008]
US4:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-009]
  concurrent_with: [US3]
```

US1 is packaging and resolution; nothing an operator sees. US2 is the verb, and
everything after it reads what it wrote — so both US3 and US4 declare
`depends_on_merged: [US1]`'s successor, `US2`, as a merge-edge (069-US2 FR-007:
declared, not left inferred). Neither US3 nor US4 needs the other: US3 adds the
staleness answer beside the resolver and the verb, US4 adds one entry to the
teardown step table and reads the record through the function US2 landed, so
they touch no production file in common and `concurrent_with: [US3]` on US4
records that as the author's judgment rather than leaving a contention edge to be
inferred from a shared import.

The vocabulary ruling (FR-011) sits in US2 rather than in a story of its own
because it must land in the same change as the name it governs. A ruling that
lands after the verb is a ruling about something already decided.
