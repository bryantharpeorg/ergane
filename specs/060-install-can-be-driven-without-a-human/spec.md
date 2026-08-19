---
state: landed
# LANDED, attested 2026-08-19 1:20 PM CT. US1 2a8e65e730f5 (#210), US2
# 4efef8a8dc08 (#211), US3 5aa0aae85fa8 (#212) -- all three observed on
# ergane-buildout. Every story passed on its first attempt, but this epic cost
# $44.61 against 059's $12.58 for the same story count, and US1 alone took 50
# minutes of wall time against 059's 19-25 minute stories.
#
# US2 landed LAST despite being second, because PR #211 came up `DIRTY`. The
# cause is worth recording, because the topology that produced it is declared
# and will recur: US2 has a PASS edge on US1, so its branch was built on US1's
# node branch and carried US1's four commits; US1 then landed as a SQUASH, same
# content, no shared ancestry. Git saw `factory/cli/install.py` modified twice
# from one merge base and refused. The factory recovered it on its own -- the
# poller classified `DIRTY` as CONFLICT and the debugger persona synced -- which
# is the first observed proof that path works end to end.
#
# The spec's own Work Graph note claimed "US3 shares nothing with either... it
# edits factory/controlplane/config.py and the notify registry, while US1 and
# US2 edit factory/cli/". That was WRONG: US3's diff also touched
# `tests/test_ergane_install_walkthrough.py`, which US2 touched too. It landed
# before US2 so no second conflict fired, but the claim was asserted from the
# plan rather than checked against a diff. `depends_on` models what a story
# needs to EXIST, never what it will TOUCH.
#
# Flipped draft -> ready 2026-08-19 ~12:15 AM CT at the operator's instruction.
# Ready is eligibility, not dispatch. 061 declares a hard `depends_on_landed` on
# this spec, so it is on the critical path even though it reads as convenience.
#
# Drafted 2026-08-18 ~11:55 PM CT by an operator session, from a first-time
# install report filed by an agent installing `ergane-cli 0.1.0` from PyPI.
#
# The reporter is itself the evidence: an agent harness that allocates a PTY but
# cannot answer prompts could not run either command, and its two workarounds
# were both bad in instructive ways.
#
#   For `install`: it hand-wrote `~/.config/ergane/config.toml` by reading the
#   parser source, then validated it by importing `load_controlplane_config`
#   directly. So the config schema was reverse-engineered from the code that
#   rejects it, which is the most expensive possible way to learn a format.
#
#   For `init`: it piped `/dev/null`, which silently accepted EVERY default --
#   including `gates: {test: 'true'}`. That is the second defect this spec
#   fixes and it is not the same as the first: EOF on stdin currently reads as
#   consent, when it is the absence of consent.
#
# Verified against the tree before drafting: no `--non-interactive`, `--config`
# or `--from-file` flag exists anywhere in `factory/cli/`. Both commands
# interview one question at a time through `factory.cli.init._prompter()`.
#
# The seam this spec needs already exists. `factory/cli/install.py:25` says so:
# the prompter is 034/US1's seam, "reused rather than reinvented: a second
# prompter convention one epic later is the drift". 033 already ships a
# scripted-prompter walkthrough harness that 055/US3's tests reuse. This spec
# is largely a matter of giving that seam a documented public entry point.
#
# Ordering: this spec should land BEFORE 061. 061's end-to-end story cannot be
# automated without a non-interactive install, which is the whole reason this
# one is ranked P1 rather than treated as the convenience it looks like.
#
# Filed as findings before drafting:
#   cli/install-and-init-cannot-be-driven-without-a-human
#   install/escalation-cannot-be-declared-off
---

# Feature Specification: install can be driven without a human

**Created**: 2026-08-18

## The gap, stated precisely

`ergane install` and `ergane init` can only be run by a person sitting at a
terminal answering questions one at a time. There is no flag to supply the
answers, no file to read them from, and no way to say "use the documented
defaults and fail if there is no safe one".

That is a problem for scripted provisioning. It is a much larger problem for
this project specifically, because **the on-ramp cannot be tested end to end
until it can be run without a human**, and the absence of that test is what let
a stranger's install accumulate thirteen defects. This spec is ranked as
infrastructure for 061 rather than as convenience for operators.

Spec Kit, which this project depends on conceptually, added exactly this flag
with exactly this justification: required for agent harnesses that allocate a
PTY but cannot send arrow-key input.

## The second defect, which is not the same as the first

The reporter piped `/dev/null` into `ergane init` and it succeeded, accepting
every default. That is worse than refusing.

EOF on stdin is not an answer. It is the *absence* of an answer, and treating it
as blanket consent is how the reporter ended up with a fully wired autonomous
factory whose only quality gate was the shell builtin `true` (see
`factory/cli/init.py:275`, where the value is declared as a *placeholder* — its
own comment calls it one — and then escapes into a live manifest).

So this spec has two obligations that pull in opposite directions and must both
be met: make the commands runnable without a human, and stop them from being
*accidentally* runnable without a human. An explicit `--non-interactive` is
consent. A closed stdin is not.

## Why escalation belongs in this spec

`KNOWN_ESC_ADAPTERS = ("telegram", "webhook")` (`factory/controlplane/config.py:51`)
offers no way to declare "no escalation". For an interactive trial install that
is friction: the operator must go create a Telegram bot before the control plane
will verify. For a *non-interactive* install it is a hard blocker, because there
is no safe default for a question whose every answer requires standing up a
third-party service first.

`telemetry` already degrades cleanly to none by omission. Escalation should
degrade the same way, loudly — a verification finding stating that escalations
will be dropped — rather than being unrepresentable.

## User Scenarios & Testing

### User Story 1 - Install runs from a file, with no terminal (Priority: P1)

As an operator provisioning a host from a script, or an agent harness with no
way to answer prompts, I can supply every interview answer up front and have
`ergane install` write the same config the interview would have written.

**Why this priority**: P1. It is the enabling half of the spec and the
precondition for 061.

**Independent Test**: run the install command with a supplied answer file
through the existing prompter seam and assert the written config is byte-identical
to the one the scripted interview produces from the same answers.

**Acceptance Scenarios**:

1. **Given** an answer file naming every interview field, **When** `ergane
   install --from-file <path>` runs with stdin closed, **Then** it writes
   `~/.config/ergane/config.toml` without reading stdin — proven by a committed
   test asserting the file is written and that the prompter was never invoked.
2. **Given** the same answers supplied interactively and by file, **When** both
   run, **Then** the two written configs are identical — proven by a committed
   test comparing the outputs of the scripted-prompter walkthrough and the
   file-driven path. Two paths that write different configs are two products.
3. **Given** an answer file missing a field for which a documented default
   exists, **When** install runs, **Then** the default is applied and the
   applied default is reported in the command's output — proven by a committed
   test asserting both the resulting value and the report line. A default that
   is applied silently is the `/dev/null` defect wearing a flag.
4. **Given** an answer file missing a field for which **no** safe default
   exists, **When** install runs, **Then** it exits non-zero naming the missing
   field and does not write a partial config — proven by a committed test
   asserting the exit status, the named field, and the absence of the file.
5. **Given** an answer file containing a literal credential where an environment
   variable name belongs, **When** install runs, **Then** it is refused by the
   existing secret-shape guard with the same wording the interactive path uses —
   proven by a committed test. The file path must not become a way around a
   check the interview enforces.
6. **Given** the diff, **When** the answer file's format is inspected, **Then**
   it is documented in-tree with a complete worked example — proven by a
   committed test asserting the documented example parses and drives a
   successful install. The reporter reverse-engineered this schema from the
   parser that rejects it; nobody should have to do that twice.

---

### User Story 2 - Init runs non-interactively, and a closed stdin is not consent (Priority: P1)

As an operator or harness joining a repository without a terminal, I can run
`ergane init --non-interactive` and get documented defaults; and if I close
stdin *without* that flag, the command refuses rather than silently accepting
everything.

**Why this priority**: P1. The refusal half is a live footgun — it is how the
reporter shipped a no-op gate into a working factory — and it is cheap to fix
alongside the flag.

**Independent Test**: run init with stdin closed, with and without the flag, and
assert opposite outcomes.

**Acceptance Scenarios**:

1. **Given** stdin closed and **no** `--non-interactive` flag, **When** `ergane
   init` runs, **Then** it exits non-zero naming the unanswerable question, and
   writes no manifest — proven by a committed test asserting the exit status and
   that no `ergane.yaml` was created. This is the `/dev/null` defect, inverted.
2. **Given** `--non-interactive`, **When** `ergane init` runs with stdin closed,
   **Then** it completes using documented defaults and prints each default it
   applied — proven by a committed test asserting the manifest contents and the
   report lines.
3. **Given** `--non-interactive` and a field with no safe default, **When** init
   runs, **Then** it exits non-zero naming the field — proven by a committed
   test.
4. **Given** the diff, **When** `--non-interactive` and per-field overrides are
   combined, **Then** the explicit value wins over the default — proven by a
   committed test asserting precedence for at least the gates and landing-branch
   fields.
5. **Given** the diff, **When** the defaults `--non-interactive` applies are
   inspected, **Then** each is the value the interactive path documents as its
   default, resolved from one shared source rather than a second table — proven
   by a committed test asserting the two paths agree field by field. A second
   defaults table drifts from the first, invisibly, because both suites stay
   green.

---

### User Story 3 - Escalation can be declared off, and says so (Priority: P2)

As an operator evaluating Ergane locally, I can declare that I want no
escalation adapter and have the control plane verify, while being told plainly
that escalations will be dropped.

**Why this priority**: P2 — it unblocks a trial install and removes the only
interview question with no answerable default, but the factory works without it
if the operator has a Telegram bot.

**Independent Test**: parse a config declaring `adapter = "none"`, verify it, and
assert the finding.

**Acceptance Scenarios**:

1. **Given** a config declaring `escalation.adapter = "none"`, **When** it is
   parsed, **Then** it is accepted — proven by a committed test.
2. **Given** that config, **When** `ergane install --verify` runs, **Then** it
   emits a finding stating that escalations will be dropped and naming what that
   means operationally: a node that would have asked a question fails instead of
   waiting — proven by a committed test asserting the finding's presence and its
   text.
3. **Given** that config, **When** verification completes, **Then** the finding
   does **not** fail the run — proven by a committed test asserting the exit
   status. It is a declared choice, not a defect; `telemetry` already degrades
   this way by omission and escalation should match it.
4. **Given** the diff, **When** the adapter registry is inspected, **Then**
   `"none"` is known to the config's roster and to `factory.notify.adapter`'s
   registry in both directions — proven by the existing conformance suite, whose
   contract at `factory/controlplane/config.py:48` is that a name in one and not
   the other is a defect.

### Edge Cases

- **`--from-file` and `--non-interactive` together.** The file supplies what it
  has, documented defaults fill the rest, and unfillable fields still refuse.
  Define this explicitly rather than letting flag order decide it.
- **A TTY is present but `--non-interactive` was passed.** Honour the flag. The
  operator asked.
- **The answer file exists but is empty.** Identical to `--non-interactive` with
  no overrides — not an error, and not blanket consent to unfillable fields.
- **Escalation declared `none` while a Telegram token is also configured.** The
  explicit adapter choice wins; do not silently upgrade to telegram because a
  credential happens to be present.

## Requirements

### Functional Requirements

- **FR-001**: `ergane install` MUST accept `--from-file <path>` supplying
  interview answers.
- **FR-002**: `ergane install` and `ergane init` MUST accept `--non-interactive`.
- **FR-003**: Under either flag, a field with a documented default MUST take that
  default, and the applied default MUST be reported in output.
- **FR-004**: Under either flag, a field with no safe default MUST cause a
  non-zero exit naming the field, with no partial artifact written.
- **FR-005**: Without `--non-interactive`, an unreadable stdin MUST cause a
  non-zero exit naming the unanswerable question, never acceptance of defaults.
- **FR-006**: The file-driven and interactive paths MUST resolve defaults from
  one shared source.
- **FR-007**: The secret-shape guard MUST apply to file-supplied values exactly
  as it does to typed ones.
- **FR-008**: The answer-file format MUST be documented in-tree with a worked
  example that is itself exercised by a test.
- **FR-009**: `escalation.adapter` MUST accept `"none"`.
- **FR-010**: `"none"` MUST produce a non-failing verification finding stating
  that escalations will be dropped and what that costs.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-003, FR-004, FR-006, FR-007, FR-008]
US2:
  depends_on: [US1]
  implements: [FR-002, FR-005]
US3:
  depends_on: []
  implements: [FR-009, FR-010]
```

US2's edge on US1 is a **pass** edge, not merely a contention edge: US2 requires
the shared defaults source that US1 establishes (FR-006), and building
`--non-interactive` against a defaults table that does not exist yet is how a
second table gets written — the exact outcome FR-006 forbids.

US3 shares nothing with either. It edits `factory/controlplane/config.py` and
the notify registry, while US1 and US2 edit `factory/cli/`. It may run
concurrently.

## Success Criteria

### Measurable Outcomes

- **SC-001**: A complete install and init can be driven on a fresh host with
  stdin closed throughout, producing a config and manifest that
  `ergane install --verify` and `ergane init --check` both accept — evidenced by
  terminal output committed in the diff.
- **SC-002**: Running either command with stdin closed and no flag exits
  non-zero and writes nothing — evidenced by committed output.
- **SC-003**: The documented answer-file example drives a successful install
  without modification.
- **SC-004**: An operator with no Telegram bot and no webhook sink can complete
  install and verification.

## Assumptions

- The existing prompter seam (`factory.cli.init._prompter_factory`, 034/US1) is
  the correct injection point, and 033's scripted-prompter walkthrough harness is
  the correct test vehicle. This spec adds a public entry point to machinery that
  already exists rather than building a parallel one.
- The answer file's format follows the config it produces rather than inventing a
  third schema.
- Declaring no escalation is a legitimate operating mode for evaluation and for
  hosts where a human is watching the journal directly. This spec does not make
  it the default.
