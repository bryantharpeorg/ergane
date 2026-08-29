---
state: ready
fixes:
  - verify/the-gate-boundary-gives-the-gate-a-tmpfs-home-and-nothing-tells-the-agent
# DRAFTED 2026-08-28 by the operator session, against ergane-buildout at 8bb2d4b.
# Slot reserved — empty and untracked — by the spec-routing session 2026-08-23.
#
# THE BOUNDARY IS CORRECT AND IT IS PYTHON-SHAPED. `HOME` inside the gate
# boundary is a tmpfs (`factory/verify/gates.py:690-691`), which is the right
# design: it is what makes a gate's writes visible and its environment
# reproducible. The consequence is that anything an attempt installs into `HOME`
# is gone by gate time, and only the worktree persists.
#
# THE FACTORY ALREADY KNOWS THIS, FOR ONE LANGUAGE. `_cache_binds`
# (`factory/verify/gates.py:861`) binds the uv cache writable into the boundary,
# and its docstring gives the reason in full: "`HOME` inside the boundary is a
# tmpfs, so a package manager finds an empty cache and re-downloads everything a
# sync touches — on a host whose cache is already warm, that turns a two-second
# gate into a network-bound one, and on a host without egress it turns a passing
# gate into a failing one." Every word of that is true of npm, of a browser
# download cache, of any package world. The implementation is
# `cache = Path.home() / ".cache" / "uv"` — one literal path. Schema v2 exists so
# a repo can declare `unit` and `smoke` gates, i.e. so a repo can have a
# JavaScript world; only the Python world's cache crosses the boundary.
#
# MEASURED. Three of four gates green on the first try; the smoke gate failed
# with Playwright's "Looks like Playwright was just installed… npx playwright
# install". The agent had already anticipated it with a postinstall hook, which
# works in the attempt and fails in the gate. The boundary does have egress
# (`:810`, "deliberately does not unshare the network"), so the download would
# succeed — it just never happens. The agent cannot see any of this. It observes:
# I ran the install, my shell has the browser, the gate says install it. The
# natural next attempt is to install it again, harder.
#
# THE HARD-WON RULE THAT SHAPES US1. A second dispatch of the same story was
# given the mechanism, stated correctly but incompletely, in the standards
# document the factory injects into every prompt. The undocumented agent solved
# it in three attempts by finding the complete fix itself. The half-documented
# agent put the variable where the text said and did not vary it across three
# attempts, failing 3/3 — with the browser physically present in its worktree,
# because the tool reads that variable from the environment on every invocation.
# Guidance that names the mechanism without the recipe replaces the agent's
# search with a wrong anchor: it looks authoritative, it came from the standards
# document, and it is almost right, which is the worst kind. **So US1 ships the
# executable line, not the principle.** A spec that lands a paragraph of
# explanation here has made the factory measurably worse.
#
# NOT IN SCOPE. This spec does not make the boundary writable, does not give the
# gate the attempt's `HOME`, does not change the tmpfs decision, and does not
# unshare or add network. It does not touch `_interpreter_binds` (`:880`), whose
# own bug is recorded and fixed. It does not add a gate.
---

# Feature Specification: the sandbox is portable and sealed

**Created**: 2026-08-28
**Depends on**: nothing outside this spec.

## The gap, stated precisely

The gate boundary is a good sandbox with one language's assumptions compiled
into it. Three consequences, in the order they cost an attempt:

1. **The agent is never told the rule.** Nothing in the attempt prompt says that
   `HOME` at gate time is a tmpfs distinct from the attempt's, so a cache warmed
   during the attempt is gone and only the worktree persists.
2. **Only Python's cache crosses.** A repository with a JavaScript world gets a
   boundary that re-downloads on every gate run, or fails where the host would
   have passed.
3. **The failure message recommends the fix that cannot work.** The gate passes
   the tool's own advice through unqualified — "just run the install" — which is
   precisely the thing that will not persist.

## The rule this spec is asking for

**A target repository declares the caches its gates need, the boundary carries
them, and the agent is told — in a line it can execute — what does not survive to
gate time.**

### What this spec is not

It is not a loosening of the boundary. The tmpfs `HOME` stays; this spec makes
what crosses it declarable rather than hardcoded.

It is not a paragraph of explanation for agents. It is one executable line. The
measurement behind that constraint is in the frontmatter and it is the most
expensive lesson this repository has bought.

It is not a package-manager integration. The factory does not learn what npm is;
it learns to carry a path a repository names.

## User Scenarios & Testing

### User Story 1 - The agent is told what does not survive, as a line it can run (Priority: P1)

As an operator, an agent meets the tmpfs-HOME rule as declared scope rather than
as an unwinnable gate failure.

**Why this priority**: P1 and it depends on nothing. It is the cheapest fix in
the epic — one sentence in a place the agent already reads — and it converts an
unwinnable-looking failure into a solvable one.

**Acceptance Scenarios**:

1. **Given** an attempt being prepared, **When** its prompt is assembled,
   **Then** the prompt states that `HOME` at gate time is a tmpfs distinct from
   the attempt's and that only the worktree persists — proven by a committed
   test.
2. **Given** that prompt, **When** its guidance is inspected, **Then** it carries
   a concrete, executable instruction for making a toolchain dependency survive
   into the gate, not a description of the mechanism — proven by a committed
   test that asserts the guidance contains a runnable form.
3. **Given** a repository that declares no gates needing a cache, **When** its
   prompt is assembled, **Then** the guidance is still present and still short —
   proven by a committed test. The rule is a property of the boundary, not of the
   repository.

### User Story 2 - A repository declares the caches its gates need (Priority: P1)

As an operator, my JavaScript repository's package cache crosses the boundary the
same way the Python one already does.

**Why this priority**: P1. Without it, US1 tells an agent about a constraint the
factory could have removed, and every non-Python target repository pays the same
two-to-nine attempts.

**Acceptance Scenarios**:

1. **Given** a manifest declaring a cache path, **When** a gate runs, **Then**
   that path is bound writable into the boundary — proven by a committed test.
2. **Given** a manifest declaring a cache path that does not exist on the host,
   **When** a gate runs, **Then** the gate runs anyway and the absence is
   reported — proven by a committed test. The existing uv bind already behaves
   this way and the reason is the same: a missing cache is not a broken
   configuration.
3. **Given** a manifest declaring no caches, **When** a gate runs, **Then** the
   uv cache is bound exactly as it is today — proven by a committed test. The
   Python default is not removed by making caches declarable.
4. **Given** a manifest declaring a cache path outside the operator's home,
   **When** the manifest is loaded, **Then** it is refused naming the path —
   proven by a committed test. A declared bind is a hole in a verification
   boundary and its blast radius must be bounded.
5. **Given** a declared cache, **When** the gate's environment is inspected,
   **Then** any environment variable the declaration names is set beside the
   bind — proven by a committed test. Binding a cache the tool cannot find is
   the failure `UV_CACHE_DIR` already exists to prevent.

### User Story 3 - A toolchain failure is annotated, not echoed (Priority: P2)

As an operator, when a gate fails with a package manager telling the agent to
install something, the factory adds what the agent cannot see rather than passing
the advice through.

**Why this priority**: P2. US1 and US2 remove most of the cause; this catches the
rest, and it is the difference between an agent searching and an agent repeating.

**Acceptance Scenarios**:

1. **Given** a gate failure whose output matches a known install-a-toolchain
   signature, **When** the failure detail is recorded, **Then** the boundary's
   `HOME` fact is appended to it — proven by a committed test.
2. **Given** a gate failure matching no such signature, **When** the detail is
   recorded, **Then** it is unchanged from today — proven by a committed test.
3. **Given** an annotated failure, **When** the next attempt's prompt is
   assembled, **Then** the annotation reaches it — proven by a committed test.
   An annotation the retry never sees is a comment.

## Work Graph

```yaml
US1:
  implements: []
  depends_on: []
US2:
  implements: []
  depends_on: []
US3:
  implements: []
  depends_on: []
  depends_on_merged: [US2]
```

US1 changes the prompt assembly; US2 changes the boundary's binds and the
manifest schema; US3 changes the gate's failure detail and shares
`factory/verify/gates.py` with US2, so it is serialised behind it on file
ownership. US1 is independent of both.

## Requirements

- **FR-001**: The attempt prompt MUST state that `HOME` at gate time is a tmpfs
  distinct from the attempt's and that only the worktree persists.
- **FR-002**: That guidance MUST be executable rather than descriptive — a line
  an agent can run, not a mechanism it must interpret.
- **FR-003**: The guidance MUST be present regardless of what a repository
  declares.
- **FR-004**: The manifest MUST accept declared cache paths, each optionally
  naming an environment variable, and the boundary MUST bind each writable.
- **FR-005**: A declared cache absent from the host MUST NOT fail the gate, and
  MUST be reported.
- **FR-006**: A manifest declaring no caches MUST bind the uv cache exactly as
  today.
- **FR-007**: A declared cache path outside the operator's home directory MUST be
  refused at load time, naming the path.
- **FR-008**: An environment variable named by a declaration MUST be set beside
  its bind.
- **FR-009**: A gate failure matching a known install-a-toolchain signature MUST
  carry the boundary's `HOME` fact in its detail, and that detail MUST reach the
  next attempt's prompt.
- **FR-010**: Every story MUST leave the tmpfs `HOME` decision
  (`factory/verify/gates.py:690-691`), the network posture (`:810`) and
  `_interpreter_binds` (`:880`) unchanged.

## Success Criteria (summary)

- A repository with a browser-driven smoke gate passes it on the first attempt on
  a warm host, because its cache crosses the boundary.
- An agent that meets the tmpfs rule meets it as declared scope with a runnable
  remedy, and does not spend three attempts installing harder.
- The boundary is no less sealed than it is today: what crosses it is declared,
  bounded to the operator's home, and refused otherwise.
