---
state: landed
# ATTESTED landed 2026-08-19 5:05 PM CT by an operator session, on git evidence,
# after the epic completed 3/3 on the roadmap. `ergane spec landed
# specs/062-the-registry-belongs-to-the-operator --default-branch ergane-buildout`
# reports, on cb093ef:
#
#   US1 landed at 0fff7060a011 (observed)   PR #215, 2026-08-19 2:32 PM CT
#   US2 landed at 1813e484d0b5 (observed)   PR #217, 2026-08-19 3:58 PM CT
#   US3 landed at 539a38a06534 (observed)   PR #219, 2026-08-19 3:46 PM CT
#
# Attested because the roadmap reads THIS frontmatter, not git. Left at `ready`,
# a fully-landed spec stays dispatchable and takes the next epic slot -- which is
# what 056 did on this same roadmap earlier today. The attestation is what stops
# the scheduler re-picking finished work.
#
# NOT attested: that the work is good. Only that it landed. Trap 4's precedence
# chain -- which registry THIS repository resolves -- has not been exercised by an
# operator independently of the gate.
#
# Flipped draft -> ready 2026-08-19 ~12:15 AM CT at the operator's instruction.
# Ready is eligibility, not dispatch. No hard dependency, but read this spec's
# trap 4 before dispatching: the precedence chain it introduces can change which
# registry THIS repository resolves, and this repository is what builds it.
#
# Drafted 2026-08-19 ~12:15 AM CT by an operator session, from a first-time
# install report filed by an agent installing `ergane-cli 0.1.0` from PyPI.
#
# Verified against the tree before drafting:
#
#   - `factory/config.py:44` resolves the registry as PACKAGE DATA. Its own
#     comment explains why, and the reason is good: an installed wheel carries
#     the registry inside the package so `importlib.resources` finds it with no
#     repo above it. That mechanism is correct and this spec keeps it.
#   - `load_personas(path)` accepts a path parameter and NO CALLER PASSES ONE.
#     Verified across every call site: `roadmap_activities.py:334`,
#     `spec.py:408`, `workgraph/cli.py:100`, `agent_activities.py:260` and
#     `:331` all call `load_personas()` bare. The override seam exists in the
#     signature and is reachable from nowhere.
#   - `personas.yaml`'s own header reads "Current wiring (2026-08-06, Bryan)"
#     and hardcodes `ollama-cloud/*` aliases, a `local/*` alias, and dated
#     homelab rationale about which vendor judges which vendor's output.
#   - `Persona.skills` is parsed and validated at `factory/config.py:212` and
#     `.skills` is read NOWHERE in the package. All three construction sites --
#     `workgraph/cli.py:584`, `cli/nouns/build.py:234`, `cli/nouns/spec.py:61`
#     -- pass `skills=()`.
#
# The existing finding `install/the-wheel-ships-no-persona-registry-so-an-
# installed-ergane-cannot-dispatch` was resolved by 056 force-including the file
# as package data. This spec is the NEXT problem, not a repeat of that one: the
# registry now ships, and what ships is one operator's private wiring in a
# location the package manager overwrites.
#
# Filed as findings before drafting:
#   install/persona-registry-ships-one-operators-wiring-with-no-override-path
#   interpreter/persona-skills-are-parsed-validated-and-never-read
---

# Feature Specification: the registry belongs to the operator

**Created**: 2026-08-19

## The gap, stated precisely

`personas.yaml` is the file this project calls the operator's dial. Its header
invites the reader to edit it freely, and Constitution Principle VII makes it
load-bearing: nodes are routed by persona, a persona resolves to a model through
this registry, and code never hardcodes a model name.

For an operator who installed from PyPI, that file is at:

```
~/.local/share/uv/tools/ergane-cli/lib/python3.13/site-packages/factory/personas.yaml
```

Two things follow, and each is independently disqualifying.

**It is not theirs.** The shipped registry hardcodes one operator's homelab
wiring — `ollama-cloud/*` aliases, a `local/*` alias, and a header dated
2026-08-06 naming the operator and the reasoning behind which vendor judges
which vendor's output. A new operator inherits five model aliases that cannot
resolve on their machine, and `ergane install --verify` fails the `llm` probe
against every one of them. Since the file also declares itself the only place a
model name may appear, they must find it and edit it before anything works.

**Editing it is destroyed by the next upgrade.** `uv tool upgrade ergane-cli`
replaces the package directory. There is no warning and no backup. The operator's
dial is inside the thing the package manager owns.

The override seam is almost there and reaches nothing. `load_personas(path)`
takes a path; no caller passes one. The parameter exists in the signature and is
unreachable from the CLI.

## What this spec does not change

The package-data resolution mechanism stays. `factory/config.py:44` explains why
it exists — an installed wheel has no repo above it, so `importlib.resources` is
the only thing that reliably finds the shipped file — and 054's trap 4 records
that reading the registry by repo-root path works in a checkout and fails in the
installed package. That is a real hazard and this spec does not reintroduce it.

What changes is that package data becomes the **last** resort rather than the
only one, and what ships there becomes an example rather than a configuration.

## The second half: a field nobody reads

`Persona.skills` is parsed, validated, and read by nothing. An operator reading
the registry reasonably concludes the architect is getting `codebase-design` and
the judge is getting `code-review`. Neither is. All three construction sites pass
an empty tuple.

That matters more than a dead field usually would, because it interacts with a
fact the docs do not state: since 018 gave each node a factory-owned HOME that
deliberately does not expose the operator's home
(`factory/workgraph/adapter.py:339`), **home-scoped agent skills are invisible to
nodes**, while **project-scoped skills committed at `<repo>/.claude/skills/` are
visible**, because worktrees carry committed files. An operator planning around
`skills:` is planning around the one mechanism that does not work, while the one
that does goes undocumented.

## User Scenarios & Testing

### User Story 1 - The registry resolves from the operator's own config directory (Priority: P1)

As an operator, I can put a persona registry at `~/.config/ergane/personas.yaml`
and have every command use it, so my edits survive an upgrade.

**Why this priority**: P1. Without it, every new operator's first edit is made in
a file the package manager will overwrite.

**Independent Test**: resolve the registry with each precedence layer present in
turn and assert which file wins.

**Acceptance Scenarios**:

1. **Given** `$ERGANE_PERSONAS_PATH` set to a readable registry, **When** any
   command loads personas, **Then** that file is used — proven by a committed
   test asserting the resolved path.
2. **Given** no environment override and a registry at
   `~/.config/ergane/personas.yaml`, **When** personas load, **Then** that file
   is used in preference to the packaged one — proven by a committed test.
3. **Given** neither, **When** personas load, **Then** the packaged registry is
   used, resolved through `importlib.resources` exactly as today — proven by a
   committed test asserting resolution still works with no repository above the
   package (054's trap 4).
4. **Given** the diff, **When** the resolver is inspected, **Then** it follows
   the same precedence shape the control-plane config already uses at
   `factory/controlplane/config.py:202` — env override, then `XDG_CONFIG_HOME`,
   then `HOME` — proven by a committed test asserting `XDG_CONFIG_HOME` is
   honoured rather than `~/.config` being hardcoded.
5. **Given** every call site, **When** they are inspected, **Then** each reaches
   the resolver rather than calling `load_personas()` with no argument and
   getting package data by default — proven by a committed test asserting that
   an override set in the environment changes what
   `factory/activities/agent_activities.py`, `factory/workgraph/cli.py`,
   `factory/cli/nouns/build.py`, `factory/cli/nouns/spec.py` and
   `factory/activities/roadmap_activities.py` each resolve. A resolver five call
   sites bypass is a resolver that does not exist.
6. **Given** an override path that does not exist or does not parse, **When**
   personas load, **Then** it fails naming the path and the fault, rather than
   silently falling back to the packaged registry — proven by a committed test.
   A silent fallback would send an operator to debug their model aliases while
   the file they edited was never read.

---

### User Story 2 - The shipped registry is an example, and install seeds the operator's copy (Priority: P1)

As a new operator, the registry I am asked to edit contains no other operator's
credentials-adjacent wiring, and `ergane install` puts a copy where my edits will
survive.

**Why this priority**: P1 and inseparable from US1. A precedence chain whose last
resort is one person's homelab is a precedence chain that still fails on a fresh
machine.

**Independent Test**: inspect the shipped file's contents; run install and assert
the seeded copy.

**Acceptance Scenarios**:

1. **Given** the diff, **When** the packaged registry is read, **Then** it
   contains no provider-specific alias belonging to a particular deployment, and
   no operator's name or dated homelab rationale — proven by a committed test
   asserting the shipped file contains none of the `ollama-cloud/`, `local/` or
   `anthropic/` alias prefixes currently hardcoded.
2. **Given** the diff, **When** the packaged registry is read, **Then** it
   documents the shape a persona must have and states plainly that its aliases
   are placeholders the operator must replace — proven by a committed test
   asserting the guidance text is present.
3. **Given** a fresh host, **When** `ergane install` runs, **Then** it writes
   `~/.config/ergane/personas.yaml` if none exists, and reports the path it
   wrote — proven by a committed test.
4. **Given** an existing `~/.config/ergane/personas.yaml`, **When** `ergane
   install` runs again, **Then** it does not overwrite it — proven by a
   committed test asserting the file's contents are unchanged. The whole point
   of the file is that it survives; an installer that clobbers it on re-run
   defeats the spec.
5. **Given** a registry whose aliases are still the shipped placeholders,
   **When** `ergane install --verify` runs, **Then** the `llm` finding says the
   registry has not been configured yet, rather than reporting five unknown
   aliases as five separate gateway faults — proven by a committed test. The
   current failure mode sends the operator to debug their proxy when the problem
   is that they have not chosen models.
6. **Given** the diff, **When** this repository's own `personas.yaml` is
   inspected, **Then** the operator's real wiring still resolves for this
   repository — proven by a committed test. This spec must not break the factory
   that is building it.

---

### User Story 3 - `skills` either works or says it does not (Priority: P2)

As an operator reading the registry, the `skills` field either reaches the agent
or is marked as reserved and unused, so I do not plan around configuration that
has no effect.

**Why this priority**: P2. Nothing is broken by the field being dead; what is
broken is the operator's model of the system, and the cost lands later.

**Independent Test**: either assert the declared skills reach the adapter
invocation, or assert the field is documented as reserved and the parser says so.

**Acceptance Scenarios**:

1. **Given** the diff, **When** a persona declaring `skills` is dispatched,
   **Then** either those skills reach the adapter invocation — proven by a
   committed test asserting they appear in the constructed invocation — or the
   field is documented as reserved and unused, with the three construction sites'
   `skills=()` explained rather than incidental.
2. **Given** the diff, **When** the registry's documentation is read, **Then** it
   states which skill scopes a node can actually see: home-scoped skills are
   invisible because the node's HOME is factory-owned
   (`factory/workgraph/adapter.py:339`), and project-scoped skills committed at
   `<repo>/.claude/skills/` are visible because worktrees carry committed files —
   proven by a committed test asserting both statements are present.
3. **Given** the chosen resolution, **When** `skills` is declared by a persona,
   **Then** the behaviour is the documented one and a test would fail if it
   silently reverted — proven by a committed test. Whichever way this story is
   resolved, the failure mode to prevent is the field quietly going dead again.

### Edge Cases

- **`XDG_CONFIG_HOME` set but unwritable.** Install must report the failure
  rather than falling back to writing inside the package.
- **The override path is a directory.** Distinct from missing; name the fault.
- **A checkout and an installed package on the same machine.** Working in this
  repository must keep using this repository's registry; the resolver's
  precedence decides it and US2-S6 holds it.
- **An operator who deliberately wants the packaged example.** Pointing the
  environment override at the packaged path must work.

## Requirements

### Functional Requirements

- **FR-001**: The registry MUST resolve as `$ERGANE_PERSONAS_PATH`, then
  `XDG_CONFIG_HOME`/`HOME`-relative `ergane/personas.yaml`, then package data.
- **FR-002**: Every call site MUST reach that resolver.
- **FR-003**: An override that is present but unreadable or unparseable MUST fail
  naming the path and fault, never fall back silently.
- **FR-004**: Package-data resolution via `importlib.resources` MUST continue to
  work with no repository above the package.
- **FR-005**: The packaged registry MUST contain no deployment-specific aliases,
  operator names or dated rationale.
- **FR-006**: The packaged registry MUST document the persona shape and state
  that its aliases are placeholders.
- **FR-007**: `ergane install` MUST seed `~/.config/ergane/personas.yaml` when
  absent and MUST NOT overwrite it when present, reporting the path either way.
- **FR-008**: `--verify` MUST report an unconfigured registry as one condition,
  not as one gateway fault per placeholder alias.
- **FR-009**: `skills` MUST either reach the adapter invocation or be documented
  as reserved and unused.
- **FR-010**: The registry documentation MUST state which skill scopes a node can
  see.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004]
US2:
  depends_on: [US1]
  implements: [FR-005, FR-006, FR-007, FR-008]
US3:
  depends_on: []
  implements: [FR-009, FR-010]
```

US2's edge on US1 is a **pass** edge. Seeding `~/.config/ergane/personas.yaml`
is pointless until something reads it, and shipping a neutral packaged registry
before the precedence chain exists would break every command on this repository
until US1 landed. Order is correctness here, not contention.

US3 shares nothing: it edits `factory/config.py`'s `skills` handling and the
adapter invocation, not the resolver. It may run concurrently with either.

## Success Criteria

### Measurable Outcomes

- **SC-001**: On a fresh host, `uv tool install ergane-cli` then `ergane install`
  produces a registry at `~/.config/ergane/personas.yaml`; editing it and running
  `uv tool upgrade ergane-cli` leaves the edits intact — evidenced by committed
  transcript.
- **SC-002**: A new operator can configure models without opening any file inside
  `site-packages`.
- **SC-003**: `ergane install --verify` against an unedited registry reports one
  actionable condition naming the registry, not five unknown-alias faults.
- **SC-004**: This repository's own epics continue to dispatch against its own
  registry, unchanged.

## Assumptions

- The control-plane config's precedence pattern
  (`factory/controlplane/config.py:202`) is the right one to mirror; a second
  precedence convention in the same product would be its own defect.
- Seeding on install is preferable to seeding on first use, because install is
  where the operator is already being told what was written.
- US3's resolution is the implementer's to choose between wiring and declaring,
  provided the choice is documented and held by a test. Wiring it is more useful;
  declaring it is honest. Silence is neither.
