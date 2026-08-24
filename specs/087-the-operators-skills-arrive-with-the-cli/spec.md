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
---

# Feature Specification: the operator's skills arrive with the CLI

## The gap, stated precisely

Ergane owns five Claude Code skills. All five exist only in this repository's
own `.claude/skills/`, which means exactly one person on earth can use them: the
operator working inside a clone of this repo.

- `floor-status` — what the floor is doing now, with an ETA table from measured
  cycle times
- `escalation-triage` — turns an open escalation into a decision brief
- `build-metrics` — LOC, commit-size distribution, story rework rate
- `spec-html` — renders a spec trio as one page with anchors resolved live
- `away-mode` — a self-paced loop that keeps the floor moving unattended

Someone who runs `pip install ergane-cli` gets the CLI and none of them. They
get no error either — there is nothing to fail. The skills are simply absent,
and nothing in the tree tells them that five operator tools exist and are not
installed.

This is not a packaging oversight to be quietly patched. It is the difference
between shipping a CLI and shipping the way the CLI is meant to be driven.

## What this spec does not change

**Dispatched agents are out of scope, deliberately and by ruling.** The operator
was asked directly on 2026-08-22 and answered: *"i want them for the operator
using them not for the agents."*

This matters because the mechanism makes the two genuinely different features.
`personas.yaml:31-36` records the finding from 062/US3: the factory constructs a
per-node, factory-owned HOME at dispatch (`factory/workgraph/adapter.py:339`),
so a skill installed under the operator's `$HOME/.claude/skills/` is **invisible
to every dispatched node**. Only skills committed at `<repo>/.claude/skills/`
reach an agent, because worktrees carry committed files.

So an implementer who "helpfully" adds a `--repo` target is not extending this
spec, they are building the other one. A story here that writes into a target
repository is a defect even if it works.

## Traps

Named hazards. Each has already cost something, here or nearby.

### Trap 1 — the word `skills` is taken

`personas.yaml:42` declares a per-persona `skills` field as *"reserved and
unused; parsed only for backward compatibility"*, locked by
`tests/test_062_us3_skills.py`, which fails the moment anyone wires it into the
adapter without updating the documentation. `personas.yaml:62` still carries an
example value.

`CONTEXT.md` has **no entry for the word at all**, which is precisely the
condition that file exists to catch — it already documents four live senses of
"promote" and calls that resolution out as something that had cost money.

A verb named `ergane skills install` would put a second, louder meaning on a
word that already has a reserved one, permanently, in the CLI surface. **The
vocabulary ruling comes before the verb, not after it.** Either `CONTEXT.md`
distinguishes the two senses explicitly, or the verb takes a different name.

### Trap 2 — the packaged-data pattern already exists; do not invent a second

`factory/config.py:98` resolves shipped package data as
`importlib.resources.files("factory") / REGISTRY_FILENAME`, falling back to the
repo-root source only for a development checkout. The docstring at
`factory/config.py:86-97` records why: a previous version walked up from
`__file__` and produced `cannot read persona registry
.../site-packages/personas.yaml` on a real install, because packaging shipped
nothing to walk to.

The wheel side is `[tool.hatch.build.targets.wheel.force-include]` in
`pyproject.toml:66-67`, which already maps `personas.example.yaml` into
`factory/personas.yaml`.

Copy this. A second resolution mechanism for the same class of problem is how
the first bug comes back.

### Trap 3 — a payload that stops shipping fails silently

`.github/workflows/release.yml:61` greps the built wheel for
`factory/personas.yaml` and fails the release if it is missing. That guard
exists because a wheel that builds is not a wheel that works, and nothing else
would have noticed.

Skills added to the wheel need the same guard in the same place. Without it, a
`force-include` typo ships a CLI whose install verb finds nothing, and every
check upstream stays green.

### Trap 4 — these are files in someone's home directory

Install writes into the operator's own `~/.claude/skills/`, outside any git
repository and outside anything Ergane owns. Two consequences the stories must
face rather than discover:

1. **An operator may have edited a skill.** A reinstall that silently overwrites
   local edits is data loss in a directory the operator reasonably considers
   theirs.
2. **Teardown must account for them.** 083 established the discipline and the
   vocabulary — `factory/cli/uninstall.py:382-388` defines `_kept` and
   `_removed`, and every step names what it did — but it was written before
   anything wrote into `~/.claude/`. An install path with no teardown path
   leaves orphans on a host that was told Ergane had left.

### Trap 5 — a packaged install cannot read its own revision

`factory/cli/main.py:140-147` derives the revision with `git rev-parse --short
HEAD` and falls back to the literal string `unknown` when there is no checkout —
which is every wheel install. Verified 2026-08-22 against the published 0.3.0:
`ergane 0.3.0 (unknown)`.

Any staleness check must therefore compare **package versions**, not revisions.
A check keyed on revision reports `unknown` against `unknown` and calls it a
match, on every install, forever.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The skills ship inside the wheel (Priority: P1)

As an operator who installed `ergane-cli` from PyPI, the five skills are present
in my installation, so that a verb has something to install from.

**Why this priority**: P1 and first. Every other story reads what this one
ships. Landed alone it changes no behaviour an operator can see, which is the
point — it is inert payload until US2 exists.

**Independent Test**: build the wheel, unzip it, and find all five `SKILL.md`
files under the package.

**Acceptance Scenarios**:

1. **Given** a wheel built from this tree, **When** its contents are listed,
   **Then** every one of the five skills is inside it, each with its `SKILL.md`
   and any scripts and reference files it depends on — proven by pasted `unzip
   -l` output.
2. **Given** the release workflow, **When** a wheel is built with a skill
   missing, **Then** validation fails and nothing is uploaded — the guard at
   `release.yml:61`, extended, proven by a committed test or a pasted failing
   run.
3. **Given** a development checkout with no wheel built, **When** the resolver
   runs, **Then** it finds the skills at their source location — the same
   checkout fallback `factory/config.py:98-101` uses. **The control.**

### User Story 2 - One verb puts them where the operator's agent looks (Priority: P1)

As an operator, I run one command and the five skills appear in my own Claude
Code configuration, so that I can drive the factory the way it was meant to be
driven.

**Why this priority**: P1. This is the feature; US1 is its substrate.

**Independent Test**: on a host with no Ergane skills installed, run the verb,
then confirm all five resolve in a fresh agent session.

**Acceptance Scenarios**:

1. **Given** an operator with no Ergane skills installed, **When** the verb
   runs, **Then** all five are written under the operator's agent
   configuration, each named as it is written — proven by pasted live output.
2. **Given** an operator who already installed them and has changed one,
   **When** the verb runs again, **Then** the changed one is **not** silently
   overwritten: it is named, kept, and the operator is told how to take the new
   version deliberately. **Trap 4.1.**
3. **Given** an operator who already installed them and changed nothing,
   **When** the verb runs again, **Then** it is a clean no-op that says so
   rather than reporting five writes it did not perform.
4. **Given** any run, **When** it completes, **Then** the destination directory
   is stated in full. An operator must never have to guess which of several
   plausible config directories was written to.

### User Story 3 - The install says whether it is current (Priority: P2)

As an operator who upgraded `ergane-cli`, I can ask whether my installed skills
match the CLI I am now running, so that I do not debug a skill calling a flag
that no longer exists.

**Why this priority**: P2. The failure it prevents is real and confusing — a
skill shelling out to a CLI it predates — but it is a diagnosis aid, not the
feature.

**Independent Test**: install skills, install a different `ergane-cli` version,
run the check, observe it names the mismatch.

**Acceptance Scenarios**:

1. **Given** skills installed from one version and a CLI at another, **When**
   the check runs, **Then** it names both versions and says which skills are
   stale — **by package version, never by revision (Trap 5)**.
2. **Given** skills installed from the running version, **When** the check runs,
   **Then** it reports current, and says where it looked.
3. **Given** no skills installed at all, **When** the check runs, **Then** it
   says so plainly and names the verb that would install them — rather than
   erroring, and rather than reporting zero stale skills, which is technically
   true and useless.

### User Story 4 - Teardown removes what install wrote (Priority: P2)

As an operator running `ergane uninstall`, the skills this factory wrote into my
agent configuration are accounted for, so that "Ergane is off this host" is
true.

**Why this priority**: P2 by sequence, not by importance. It cannot be built
before US2 has written anything, and it is the story that keeps 083's promise
from becoming false.

**Independent Test**: install skills, run teardown, observe them named and
handled; run teardown again, observe it says there is nothing to do.

**Acceptance Scenarios**:

1. **Given** installed skills, **When** teardown runs, **Then** they are named
   in its output using the existing `_kept` / `_removed` vocabulary
   (`factory/cli/uninstall.py:382-388`) — consistent with every other step, not
   a new dialect.
2. **Given** a skill the operator modified after installing, **When** teardown
   runs, **Then** it is **kept and named as kept**, not removed — the operator's
   edits are theirs. **Trap 4.1 again, from the other end.**
3. **Given** no installed skills, **When** teardown runs, **Then** the step says
   it had nothing to do, as every other teardown step does.

### Edge Cases

- The operator's agent configuration directory does not exist yet — created, or
  refused with a reason? A skill written into a directory no agent reads is
  worse than a refusal.
- A skill name collides with something already installed that Ergane did not
  write. Never clobber; name the collision.
- `XDG_CONFIG_HOME` or an equivalent points the agent configuration somewhere
  non-default. `factory/config.py:104-108` already honours `XDG_CONFIG_HOME` for
  the registry; whatever this spec does must not contradict it.
- The operator installed with `uv tool install` or `pipx`, so the package lives
  in an isolated environment. The destination is a function of the *operator's
  home*, not of where the package landed.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The five skills MUST be included in the built wheel as package
  data, by the same `force-include` mechanism `pyproject.toml:66-67` already
  uses for the persona registry.
- **FR-002**: Resolution MUST use `importlib.resources` against the `factory`
  package with a development-checkout fallback, matching
  `factory/config.py:98-101`. A second mechanism MUST NOT be introduced.
- **FR-003**: The release workflow MUST fail the build when any shipped skill is
  absent from the wheel, in the same step as the existing payload guard at
  `.github/workflows/release.yml:56-66`.
- **FR-004**: A single verb MUST install all five skills into the operator's
  agent configuration and MUST print the absolute destination.
- **FR-005**: The verb MUST NOT overwrite a skill whose on-disk content differs
  from what Ergane last wrote. It MUST name it, keep it, and state how to take
  the new version deliberately.
- **FR-006**: The verb MUST be idempotent: a second run with nothing changed
  MUST report a no-op rather than reporting writes.
- **FR-007**: A check MUST report installed-versus-running staleness **by
  package version**. It MUST NOT key on the revision string, which is `unknown`
  on every packaged install (`factory/cli/main.py:140-147`).
- **FR-008**: The check MUST distinguish *no skills installed* from *all skills
  current*, and name the install verb in the first case.
- **FR-009**: `ergane uninstall` MUST account for installed skills as a declared
  step, using the existing disclosure vocabulary, and MUST keep any the operator
  has modified.
- **FR-010**: This feature MUST NOT write into a target repository or into a
  dispatched node's HOME. Operator scope only: a path that installs a skill
  anywhere a dispatched agent could read it MUST be refused.
- **FR-011**: Before any verb name is landed, the collision with the reserved
  per-persona `skills` field (`personas.yaml:42`, `tests/test_062_us3_skills.py`)
  MUST be resolved in `CONTEXT.md` — either by distinguishing the two senses
  explicitly or by choosing a name that does not collide.
- **FR-012**: `README.md` MUST tell an operator these skills exist and how to
  install them. `tests/test_readme.py` resolves every path the file cites, so
  any path named there must exist in the tree.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On a host with no clone of this repository, `pip install
  ergane-cli` followed by one command yields five working skills — proven by
  pasted live output from a cold environment, not from a checkout.
- **SC-002**: A wheel missing any skill fails the release workflow before
  upload.
- **SC-003**: Running the install verb twice changes nothing on the second run
  and says so.
- **SC-004**: A skill edited by the operator survives both a reinstall and a
  teardown, and is named as kept by each.
- **SC-005**: `ergane uninstall --check` names the skills among the things it
  would handle, before any teardown runs.
- **SC-006**: `CONTEXT.md` states the ruling on `skills`, and no reader can
  confuse the persona field with the operator tooling.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-004, FR-005, FR-006, FR-010, FR-011, FR-012]
US3:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-007, FR-008]
US4:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-009]
```

US1 is packaging and resolution; nothing an operator sees. US2 is the verb, and
everything after it reads what it wrote — so both US3 and US4 need it merged,
but they do not need each other and can run side by side.

The vocabulary ruling (FR-011) sits in US2 rather than in a story of its own
because it must land in the same change as the name it governs. A ruling that
lands after the verb is a ruling about something already decided.

## Assumptions

- The operator's agent is Claude Code, and its skills directory is
  `~/.claude/skills/`. If Ergane later supports other agent front-ends, the
  destination becomes a function of the front-end and this spec's single
  destination becomes a defect. Out of scope here; worth naming.
- The five skills are Ergane's own work and carry no third-party license
  obligation — true as of 838b9c3, which removed everything that did.
- Skills are small: 180 KB total measured 2026-08-22, against a 766 KB wheel.
  Shipping all five is not a size decision that needs making.
