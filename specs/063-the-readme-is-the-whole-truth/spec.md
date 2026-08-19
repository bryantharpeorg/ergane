---
state: ready
# Flipped draft -> ready 2026-08-19 ~12:15 AM CT at the operator's instruction.
# Ready is eligibility, not dispatch. No hard dependency. US3 extracts the
# alias derivation out of `LLMProbe.gather`, which 061/US1 also rewrites --
# whichever epic runs second must re-read that function rather than assume the
# shape it last saw. Both plans carry the trap.
#
# Drafted 2026-08-19 ~12:25 AM CT by an operator session, from a first-time
# install report filed by an agent installing `ergane-cli 0.1.0` from PyPI.
#
# The reporter's summary sentence is the brief for this spec: "a first install
# requires reading the source. Not the docs -- the source." To stand up a
# working gateway they read `factory/usage/litellm_client.py`,
# `factory/controlplane/verify.py` and `factory/personas.yaml` to learn which
# endpoints must answer and which model aliases must resolve. None of it is in
# the README.
#
# 054 built that README and a sweep to hold it true. The sweep has a hole, and
# the hole is shaped exactly like the defect that shipped through it. Verified:
#
#   `tests/page_holds_true.py:54`  ->  if not words or words[0] != "ergane": continue
#
# So a code span whose first word is a TYPO of the command name is not checked
# and fails -- it is SKIPPED. Two shipped through it in the same section:
#
#   README.md:105   nergane repo forget <repo-slug>
#   README.md:111   nergane worker uninstall
#
# `tests/test_claude_md.py` imports the same helper and carries the identical
# hole. This is the fifth instance of the presence-not-capability class -- the
# sweep asserts that the commands it recognised resolve, never that it
# recognised the commands that are there.
#
# Filed as findings before drafting:
#   ci/the-readme-command-sweep-cannot-see-a-typo
#   install/readme-omits-the-database-requirement-that-decides-whether-the-gateway-works
---

# Feature Specification: the README is the whole truth

**Created**: 2026-08-19

## The gap, stated precisely

054 established the right principle: a getting-started page that nobody checks
decays into a liability faster than no page at all, because a stale command reads
as authority. It built `README.md` and a committed sweep to hold every command
and path in it true.

The page then shipped two commands that do not exist and omitted the single
requirement that decides whether an operator's gateway works at all. Both
failures are the sweep's blind spots rather than the author's carelessness, and
both are fixable.

## The sweep cannot see a typo

`tests/page_holds_true.py:54` reads:

```python
if not words or words[0] != "ergane":
    continue
```

A code span beginning `nergane` is not a command that fails to resolve. It is not
a command at all, so it is skipped in silence. The guard that exists specifically
to prove every command the page names resolves is structurally blind to the
likeliest defect a page like this can have — a typo in the command name itself.

`README.md:105` and `README.md:111` are the proof, both in the "Leaving" section,
both reachable by a first-time operator doing exactly what the heading invites.

`tests/test_claude_md.py` imports the same helper and has the same hole.

## The page omits what an operator most needs

Three omissions, in descending order of what they cost:

**The gateway must be database-backed, and the page never says so.** Ergane mints
a virtual key per attempt, reads it back via `/key/info` and `/spend/logs/v2`,
and revokes it. Those endpoints are database-backed in LiteLLM. A proxy started
without `DATABASE_URL` answers `/v1/models` and `/v1/chat/completions` perfectly
and 404s all of it. The page says "a LiteLLM-shaped gateway" and stops. That one
missing sentence is the difference between a twenty-minute setup and an
expedition through three source files.

**Which model aliases the proxy must serve is stated nowhere.** The requirement
is every `model` and `fallback` in the persona registry, discoverable only by
reading `factory/controlplane/verify.py`.

**The page installs from source when a published package exists.** It documents
`git clone` → `uv venv` → `uv pip install -e .`. `ergane-cli` is on PyPI as of
056, and `uv tool install ergane-cli` is the natural path for a CLI. The two
flows also resolve the persona registry differently — checkout root versus
package data — which matters a great deal given 062.

## User Scenarios & Testing

### User Story 1 - The sweep cannot pass over a command it failed to recognise (Priority: P1)

As a maintainer, a typo in a command name in any checked page fails the build
instead of being skipped.

**Why this priority**: P1. Until this lands, every other fix to these pages is
protected by a guard with a hole in it, and the next typo ships the same way.

**Independent Test**: run the sweep over a fixture page containing a near-miss
command and assert it fails.

**Acceptance Scenarios**:

1. **Given** a page containing a code span whose first word is a near-miss of a
   known entrypoint — `nergane`, `ergane` misspelled, or a known noun with a
   leading or trailing character — **When** the sweep runs, **Then** it **fails**
   naming the unrecognised word — proven by a committed test over a fixture page.
2. **Given** a page containing a code span that is legitimately not an Ergane
   command — `git clone`, `uv venv`, `gh auth login` — **When** the sweep runs,
   **Then** it passes — proven by a committed test. A near-miss detector that
   flags every non-Ergane command makes the sweep unusable and will be disabled.
3. **Given** the diff, **When** `README.md` and `CLAUDE.md` are swept, **Then**
   both pass — proven by the committed sweep running over both, which requires
   `README.md:105` and `README.md:111` to be corrected in this diff.
4. **Given** the diff, **When** the near-miss logic is inspected, **Then** it
   lives in the shared helper `tests/page_holds_true.py` and both pages' suites
   use it — proven by a committed test asserting `tests/test_claude_md.py` and
   `tests/test_readme.py` exercise the same code path. Two extractors is how the
   pages drift apart, invisibly, with both suites green (054's trap 3).
5. **Given** the diff, **When** the near-miss test itself is inspected, **Then**
   it asserts the sweep **fails** on a bad fixture rather than asserting it
   passes on a good one — proven by reading the committed assertion. A guard
   nobody has watched fail is a guard nobody has tested.

---

### User Story 2 - The page states every prerequisite that decides whether the gateway works (Priority: P1)

As a new operator, I can read one page and know what my gateway must do, before
I build it.

**Why this priority**: P1. This is the omission that turned a twenty-minute
setup into a source-reading expedition, and it is one sentence.

**Independent Test**: assert the required statements are present, and that the
install command the page recommends is the one the package ships.

**Acceptance Scenarios**:

1. **Given** the diff, **When** the prerequisites section is read, **Then** it
   states that the gateway must be backed by a database, names the endpoints
   Ergane depends on, and says plainly that a config-only proxy answers
   `/v1/models` and 404s the rest — proven by a committed test asserting the
   statement is present.
2. **Given** the diff, **When** the prerequisites section is read, **Then** it
   states that the gateway must serve every `model` and `fallback` alias the
   persona registry declares — proven by a committed test.
3. **Given** the diff, **When** the installation section is read, **Then** it
   documents installing the published package as the primary path, and the
   source checkout as the path for working *on* Ergane — proven by a committed
   test asserting both are named and distinguished.
4. **Given** the diff, **When** the two install paths are described, **Then** the
   page states that they resolve the persona registry differently — proven by a
   committed test. An operator who installed from PyPI and reads checkout
   instructions edits a file nothing loads.
5. **Given** the diff, **When** every existing 054 sweep runs, **Then** all still
   pass: no secret value, no spec state, no story count, no spend figure, every
   path exists — proven by the committed tests already in
   `tests/test_readme.py`. This story adds to the page; it must not regress what
   holds it true.

---

### User Story 3 - The CLI can print what the gateway must serve (Priority: P2)

As an operator standing up a gateway, I can ask Ergane what it needs rather than
reading `verify.py` to find out.

**Why this priority**: P2. US2 removes the confusion by documenting it; this
story removes it by making the answer live, so it cannot go stale the way a
documented list would.

**Independent Test**: run the subcommand against a known registry and assert the
printed alias set.

**Acceptance Scenarios**:

1. **Given** a resolved persona registry, **When** `ergane install
   --requirements` runs, **Then** it prints every distinct `model` and `fallback`
   alias the gateway must serve — proven by a committed test asserting the output
   against a fixture registry.
2. **Given** the same, **When** the output is read, **Then** it also names the
   key-management endpoints the gateway must answer — proven by a committed test.
3. **Given** a registry with personas declared `agent: none`, **When** the
   command runs, **Then** those personas contribute no alias — proven by a
   committed test. They have no model by construction; 054's trap 5 already
   named this.
4. **Given** the diff, **When** the command's alias derivation is inspected,
   **Then** it is the same derivation `--verify` probes with, not a second one —
   proven by a committed test asserting both resolve identical sets from one
   fixture. A requirements list that disagrees with the probe is worse than none.
5. **Given** the diff, **When** `README.md` is read, **Then** it names this
   command in place of an inline alias list, so the page cannot go stale — proven
   by the committed sweep, which will resolve the command only if it exists.

### Edge Cases

- **A code span containing a shell pipeline or a heredoc.** The extractor takes
  the first word; make sure a pipeline beginning with a legitimate non-Ergane
  command does not trip the near-miss detector.
- **A page naming a command that is spelled correctly but does not exist yet.**
  Already handled — it resolves against `--help` and fails. Near-miss detection
  must not mask that clearer failure.
- **`--requirements` with no registry configured.** Print the requirement to
  configure one, naming the resolution order 062 establishes.
- **A deliberately fenced example of a wrong command**, e.g. documenting a
  common mistake. Out of scope; if it becomes necessary, an explicit opt-out
  marker beats loosening the detector.

## Requirements

### Functional Requirements

- **FR-001**: The shared sweep MUST fail on a code span whose first word is a
  near-miss of a known entrypoint.
- **FR-002**: It MUST NOT fail on legitimate non-Ergane commands.
- **FR-003**: The near-miss logic MUST live in `tests/page_holds_true.py` and be
  used by both pages' suites.
- **FR-004**: `README.md:105` and `README.md:111` MUST be corrected.
- **FR-005**: The README MUST state the gateway's database requirement and name
  the dependent endpoints.
- **FR-006**: The README MUST state that the gateway must serve every `model` and
  `fallback` alias the registry declares.
- **FR-007**: The README MUST document the published-package install as the
  primary path and the checkout as the path for working on Ergane, noting that
  they resolve the registry differently.
- **FR-008**: All existing 054 sweeps MUST continue to pass.
- **FR-009**: `ergane install --requirements` MUST print the distinct alias set
  and the required endpoints.
- **FR-010**: `--requirements` MUST derive aliases identically to `--verify`.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-005, FR-006, FR-007, FR-008]
US3:
  depends_on: [US2]
  implements: [FR-009, FR-010]
```

US2's edge on US1 is a **merge** edge for contention on `README.md`, but it is
close to a pass edge for a second reason worth stating: US1's story cannot pass
until the two `nergane` typos are corrected, and US2 rewrites the sections
around them. Landing US2 first would leave US1 fixing a page that has moved.

US3's edge on US2 is a **pass** edge. US3-S5 requires `README.md` to name
`ergane install --requirements` in place of an inline alias list, which means the
page must already have been reshaped by US2 — and the sweep will only resolve the
command once it exists.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Introducing a one-character typo into any command in `README.md`
  or `CLAUDE.md` fails the suite — evidenced by committed output of the
  deliberately-broken run.
- **SC-002**: Every command in `README.md` runs as written on a host meeting the
  stated prerequisites.
- **SC-003**: An operator can determine every gateway requirement from the README
  and `ergane install --requirements`, without opening a source file.
- **SC-004**: `--requirements` and `--verify` agree on the alias set for the same
  registry.

## Assumptions

- 062 may change how the registry resolves. If it has landed, `--requirements`
  reports the resolved registry and says which file it read; if not, it reports
  the packaged one. Either way it names the path.
- Near-miss detection is worth its false-positive risk because the failure it
  prevents — a copy-pasteable command that does not exist — lands on the newest
  possible reader. US1-S2 bounds the risk.
- The published package remains the recommended install path, per 056.
