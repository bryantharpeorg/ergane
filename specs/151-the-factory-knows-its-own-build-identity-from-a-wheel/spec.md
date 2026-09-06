---
state: draft
fixes:
  - doctor/the-stale-worker-probe-cannot-run-from-a-wheel-install
  - cli/the-worker-skew-check-keys-on-a-git-revision-a-wheel-cannot-have
  - cli/the-version-verb-prints-unknown-from-a-wheel
  - operator/the-worker-revision-warning-fires-permanently-on-a-packaged-install
# DRAFTED 2026-09-04 by the refinement workflow (refinement-2026-09-04) from
# docs/triage-2026-09-03-ergane-web-round3.md § "the-factory-knows-its-own-build-identity-from-a-wheel"
# (lines 381-400), against ergane-buildout at 602a92c. Every `file:line` in
# spec.md and plan.md was read from that commit and verified to resolve to the
# symbol named, not recalled.
#
# WHERE THIS CAME FROM. Four findings in the doctor's ledger, filed by three
# separate reporters across three weeks, that the round-3 triage proved to have
# one root: four surfaces each answer "what code is this?" by shelling git at
# the package, and an installed distribution has no git to answer. N17 came
# from the `ergane-web` round-2 hand-over, N13 from the same document, N5 from
# the Wolfenstein container corpus (as a re-report, where it acquired its real
# consequence), and the fourth from a consumer agent's 2026-08-19 build session
# and an operator session on this host the same afternoon. The refuter for N17
# says explicitly that they belong in one spec: fixing them separately is four
# passes over the same missing fact.
#
# WHAT IT COST, MEASURED. Not an outage — a permanent, silent loss of signal on
# the install shape the project recommends. `ops/stale-worker` is a CRITICAL
# check with exactly one producer, and on a packaged install the loss is not one
# verdict: the probe raises on its very first statement, and the skip forces a
# non-zero exit code on every `ergane doctor` run whatever else is healthy. The
# incident class the probe's own note names (
# `factory/doctor/probes.py:378` — `StaleWorkerProbe.evaluate` ) is `e5c5569` — "an
# activity-code fix dispatched
# by a worker still running old code" — new code arriving under a running
# worker. On a checkout that is caught. On a packaged install the same thing
# arrives through a reinstall rather than a commit, and the ledger already holds
# that shape as a still-open CRITICAL row:
# `install/a-same-version-reinstall-silently-reverts-operator-edits-and-the-version-string-names-two-different-codebases-a-week-apart`
# — 534 lines across three files replaced under an identical version string.
# The skew warning is the measured half: `ergane build status` printed
# `worker revision is unknown (CLI revision cb093ef); the worker predates this
# check or is not a git checkout` on EVERY call while an operator read 061's
# node states, and the only way that operator could confirm the running worker
# carried 065's fix was a `systemctl show` timestamp read by hand. The container
# corpus adds the third consequence: the CLI-to-engine handshake compares version
# STRINGS, so a buildout head 36 commits ahead calls itself the same version and
# a stale engine passes the check. No version surface in this product can
# currently distinguish a modified stack from the published one.
#
# WHAT THE TRIAGE CORRECTED IN THE SOURCE, AND THIS SPEC OBEYS. (a) The
# hand-over cites `factory/doctor/cli.py:242` — `_run_probe` as the site to fix.
# It is dead: its only consumer is line 225 of its own module, and the CLI
# imports only `_resolve_store_path` from it. The live handler is
# `factory/cli/doctor.py:177` — `doctor_command`. (b) `_newest_factory_commit`
# runs git with no `cwd=`, so "permanent from a wheel" is also true of a
# checkout when the process working directory is an unrelated repository —
# verified by execution during triage. (c) The skip forces the exit code at
# `factory/cli/doctor.py:206`, so `ergane doctor` can never return 0 on such a
# host; the document undersells this.
#
# WHY FOUR KEYS AND NOT TWO. This floor has three dated instances of a landed
# spec half-fixing a defect and declaring it whole (100, 092, 118), and the tell
# is a `fixes:` list longer than the FRs justify. Every key here was read from
# its ledger row, not from its name, and each is owned WHOLE by one story:
# the doctor key by US2 (FR-007..FR-011), the version key by US3
# (FR-012..FR-014), and the two skew keys by US4 (FR-015..FR-020) — they are the
# same warning described by its mechanism and by its consequence, and FR-016
# ends it while FR-017 keeps the case it was built for.
# `factory/cli/nouns/build.py:966` — `_cli_revision` and
# `factory/cli/main.py:132` — `_version_text` are two genuinely distinct
# implementations in two files, which is why both cli keys are declared rather
# than one.
#
# THE INGESTED SEVERITY ON THE DOCTOR KEY IS `info`, AND IT IS UNDER-SEVERE.
# It disables a CRITICAL check on the recommended install shape. Re-grading a
# ledger row is an operator act, not a refinement act, so the row is left alone
# and the mis-grading is recorded here instead: do not let triage read this one
# as cosmetic.
#
# NOT IN SCOPE. This spec does not change what the stale-worker probe compares
# once it has an identity — the worker's process start time against the stamp of
# the code it runs, exactly as today. It does not alter `ops/stale-worker`'s key
# or its `Severity.CRITICAL`. It adds no store. It does not change what
# `worker_revision` means to
# `factory/versioning.py:94` — `resolve_deployment_version`, which must keep
# refusing a `None` revision under engaged versioning. It does not touch the
# CLI-to-engine version handshake, which is the container corpus's other half
# and a separate spec.
#
# REPAIRED 2026-09-04 by the refinement workflow (refinement-2026-09-04), against
# ergane-buildout at 602a92c, after an adversarial review refuted the draft.
#
# WHAT THE REFUTATION CAUGHT. (1) The headline cost claim was inherited verbatim
# from the triage source and the anchored line refutes it:
# `factory/doctor/probes.py:378-382`
# names the `e5c5569` incident — an activity-code fix under a running worker, a
# CHECKOUT incident this floor has had — not "an upgrade only a packaged install
# can suffer". The claim appeared three times (this block, gap step 5, plan trap
# 11) and all three are re-argued on facts that hold: the raise, the forced exit
# code, and the ledger's own same-version-reinstall row. The design is unchanged.
# (2) Plan trap 10 forbade the exact call FR-003 requires; it now forbids a
# second VERSION lookup and blesses the one
# `importlib.metadata.distribution("ergane-cli")` call the stamp needs, and
# US1-S4 / T004 name `importlib.metadata.version` instead of "the underlying
# metadata lookup" so the criterion is decidable from the diff. (3) T034 asked a
# node for a live packaged-worker `ergane build status` run it cannot produce; it
# now drives `_query_status` over a stubbed status document, and the live run
# stays plan step 4. (4) US2-S1's control named a code path US2 deletes; it is
# now a proof that the fixture is an honest no-git layout. (5) FR-019 added: no
# FR required the CLI's own side of the skew comparison to come from the
# resolver, so a diff could satisfy every FR and leave the fourth git shell in
# `factory/cli/nouns/build.py` standing. (6) Anchors re-cited:
# `factory/worker.py:326` is the guard and `:327` the injection;
# `factory/cli/main.py:136-143` was one line short of the block it names and is
# now `136-144`. (7) `ergane doctor`'s skip exit code is `3`
# (`factory/cli/errors.py:26`), not `2` — the `2` lives in the module trap 1
# declares dead. (8) `factory/cli/nouns/__init__.py` added to US4's file list.
# Keys unchanged: still the same four, all open, none resolved.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04), against ergane-buildout at
# 602a92c, after a second adversarial review refuted the repaired draft — this
# time on the test tree, which the first pass verified unevenly while verifying
# the production tree exhaustively. Zero anchors had moved. Fixed, one clause
# per defect class. (1) THE MIXED COMPARISON ROW WAS DECIDED BY NO FR: one side
# git-sourced with a revision, the other distribution-sourced with a version and
# a stamp, same version, fell through FR-016, FR-017 and FR-018 — and plan step 4
# already answered it the opposite way from the strict reading; FR-020, US4-S7
# and a nine-combination comparison table in the rule section now decide it, and
# step 4 quotes the row instead of asserting an outcome no FR required.
# (2) US1'S DISTRIBUTION ARM HAD NO SYNTHETIC DISTRIBUTION: the host's real
# `ergane_cli-0.5.0.dist-info` is resolvable from inside the fixture's
# subprocess, so US1-S1's positive half passed for an ambient reason and US1-S2's
# mandated control would have rewritten a `METADATA` file inside the gate's own
# venv; trap 12, US1-S1, US1-S2 and T001 now require a synthetic dist-info under
# the temporary path and an assertion that the resolved distribution lies there,
# made before anything is rewritten. (3) FR-006'S PROVABILITY HOOK COULD NOT BE
# SATISFIED: the literal text `importlib.metadata.version` occurs zero times in
# `factory/supervision/engine_identity.py`, which reaches the lookup through the
# `from importlib.metadata import version` binding at
# `factory/supervision/engine_identity.py:45`, so a text count returned zero and
# the cheapest way to make it one was to add the very call FR-006 forbids; the
# count is now stated over the parsed syntax tree, FR-006 is scoped to the
# resolver's own module, and `factory/supervision/container_project.py:157` is
# named as pre-existing and out of scope rather than as an apparent violation.
# (4) THE LANDED SKEW TESTS WERE NAMED NOWHERE: `tests/test_ergane_build_status_refusal.py`
# holds six 053-US3 tests that drive this whole path, two of which assert the
# sentence FR-018 deletes; they are now trap 13, US4's sizing and T028.
# (5) A VERIFICATION TASK POINTED AT A FILE THAT DOES NOT DO WHAT IT WAS SAID TO
# DO: `tests/test_ergane_status.py` never drives `_query_status` — it mentions it
# only in an AST guard-sweep table — so T035 (was T034) now names that module's
# real harness. (6) US2-S3 CARRIED NO HONEST-LAYOUT CONTROL, so it was satisfiable
# by FR-002's anchoring alone with FR-003 unimplemented; it is now tied to US2-S1's
# fixture and control. (7) US4-S6 read as a source-text search that the seam
# comment at `factory/cli/nouns/build.py:969` would fail; it now asserts the
# absence of the invocation. Keys unchanged: the same four, all open, none
# resolved. Nothing was removed from the provenance above. state stays draft.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04), against ergane-buildout at
# 602a92c, after a third adversarial review refuted the repaired draft. Zero
# anchors had moved; every one was re-read. Both blocking defects were the same
# shape — a case the criteria left for the implementer to invent — and both are
# now decided. One clause per defect class. (1) FR-011 MADE ONLY THE FIELDS
# HONEST. The finding those fields feed still hard-codes git in the text an
# operator reads: the summary at `factory/doctor/probes.py:366` and the
# `git/timestamp:` and `git/commit:` refs at `factory/doctor/probes.py:374` and
# `factory/doctor/probes.py:376`. On a distribution-sourced identity the
# revision is `None` by this spec's own truth table, so the CRITICAL finding
# would have read "before newest `factory/` commit None" — the lie FR-011 exists
# to end, one layer out, on the exact install shape the spec serves. FR-011 now
# reaches the `FindingReport`, US2-S5 asserts summary and refs, T014 constructs
# and evaluates it, and T011's "must not drift" is narrowed to the key, the
# category and the severity so it cannot be read as pinning the git-claiming
# text FR-011 has to change. (2) THE LEGACY PAYLOAD WAS DECIDED BY NO FR. A
# worker still running the code that was there before this story answers a
# post-151 CLI with a bare `worker_revision` and no identity — every call for
# the whole upgrade window, and the shape
# `tests/test_ergane_build_status_refusal.py:309` — `_query_document` builds in
# all seven landed skew tests — and it fell through FR-016, FR-017, FR-018 and
# FR-020 alike. FR-021, US4-S8, two more rows in the comparison table and T029
# now decide it as a revision-only side, which is today's behaviour exactly, so
# closing the operator's permanent warning on a packaged install cannot open a
# new one on every un-restarted worker. US4 accordingly owns FR-015..FR-021; the
# "WHY FOUR KEYS AND NOT TWO" block above names the range as it stood then. (3) TWO TRAPS MADE FALSE EXCLUSIVE
# CLAIMS ABOUT THE LANDED TESTS. Trap 13 said
# `tests/test_ergane_build_status_refusal.py` is what exercises
# `ergane build status` end to end;
# `tests/test_ergane_build.py:790` — `test_status_json_is_the_query_result_verbatim`
# does too, and asserts on the
# very sentence FR-018 abolishes. Trap 9 said one offline technique for "from a
# wheel" exists; `tests/test_distribution_install.py:39` — `_build_wheel` builds
# and installs a real wheel and
# `tests/test_distribution_install.py:207` — `test_clean_install_version_reports_built_version`
# runs `ergane --version` out
# of it. Both traps, US1's, US3's and US4's sizing and T028 now name what is
# there. (4) SEVEN LANDED SKEW TESTS, NOT SIX:
# `tests/test_ergane_build_status_refusal.py:501` — `test_worker_revision_is_recorded_once_and_carried_not_recomputed`
# was unlisted and asserts the revision-disagreement text FR-017 keeps. (5) US1-S2's control could have gone
# red on clock granularity rather than on FR-003; T001 now sets the rewritten
# file's modification time explicitly. (6) T022 produced no diff evidence for
# US3-S3's endpoint clause; it now counts the resolutions. (7) FR-019 moved
# above FR-020 so the list reads in order. No task was renumbered: US4-S8 is
# carried by T029 beside US4-S7, so the ids named in the entries above still
# resolve. Keys unchanged: the same four, all open, none resolved. Nothing was
# removed from the provenance above. state stays draft.
---

# Feature Specification: the factory knows its own build identity from a wheel

**Created**: 2026-09-04
**Depends on**: nothing.

## The gap, stated precisely

Four surfaces ask the same question — *what code is this?* — and all four ask it
by shelling git at the installed package. A wheel has no git, so all four get
nothing, and the two that matter most fail in opposite directions: one goes
permanently silent, the other goes permanently loud.

The chain is seven steps:

1. The four implementations are separate code in four files:
   `factory/doctor/probes.py:161` — `_newest_factory_commit` (`git log -1
   --format=%ct %H -- factory/`),
   `factory/cli/nouns/build.py:966` — `_cli_revision`,
   `factory/cli/main.py:132` — `_version_text`, and
   `factory/worker.py:220` — `_worker_revision`. Three of them run the same
   `git rev-parse --short HEAD` and each swallows failure its own way.
2. Three degrade to a placeholder. `_cli_revision` returns `None`;
   `_version_text` sets `revision = "unknown"` at `factory/cli/main.py:144` and
   prints it in parentheses; `_worker_revision` returns `None`.
3. The fourth does not degrade — it raises.
   `factory/doctor/probes.py:171` — `_newest_factory_commit` raises
   `ServiceNotAnswering("git", ...)`, and that call is the **first** statement of
   `factory/doctor/probes.py:328` — `StaleWorkerProbe.gather`, ahead of
   `_discover_worker_pid` at
   `factory/doctor/probes.py:329` — `StaleWorkerProbe.gather`, so the exception
   escapes the whole probe before it has looked at anything.
4. A skipped probe forces the process exit code.
   `factory/cli/doctor.py:206` — `_run_all_probes` returns `EXIT_TRANSPORT` and
   it is the **first** of the three arms, so `ergane doctor` can never return
   `0` on a host where git does not answer, whatever else is healthy.
5. What is lost is total. `ops/stale-worker` has exactly one producer,
   `factory/doctor/probes.py:363` — `StaleWorkerProbe.evaluate`, and the
   incident class its note names at
   `factory/doctor/probes.py:378` — `StaleWorkerProbe.evaluate` is "the e5c5569 incident
   class: an activity-code
   fix dispatched by a worker still running old code" — new code arriving under
   a running worker. On a checkout that incident is caught. On a packaged
   install the same thing arrives through a reinstall rather than a commit —
   the ledger's still-open CRITICAL row about a same-version reinstall
   replacing 534 lines is that incident, filed — and there the check does not
   run at all.
6. The skew check inverts the same fact into noise.
   `factory/cli/nouns/build.py:988` — `_skew_notice` warns whenever the worker's
   revision is `None`, which on a packaged install is every call. The one signal
   built to say "the CLI and the worker disagree" says the same thing whether
   they agree or not, and gets filtered out by humans and agents alike.
7. And the git read is not even anchored. `_newest_factory_commit` passes **no**
   `cwd=`, so it questions whatever repository the *process working directory*
   sits in. Running `ergane doctor` from an unrelated checkout skips identically
   — so "permanent from a wheel" understates it: it is also wrong from a
   checkout.

**The missing fact is not a revision. It is an identity.** A wheel knows its own
version and knows when it was installed; a checkout knows its revision and when
that revision was made. Both are answers. Only one of them is being asked for.

## The rule this spec is asking for

**Build identity is resolved once — a version, a stamp and, when there is one, a
revision — from the imported package, with git as one source among several, and
every surface that reports it to an operator asks that resolver instead of
shelling git itself, so a packaged install gets a verdict, a version and a
comparison rather than a placeholder.**

Three of the four implementations in step 1 stop shelling git:
`_newest_factory_commit` (US2), `_version_text` (US3) and `_cli_revision` (US4,
FR-019). The fourth, `factory/worker.py:220` — `_worker_revision`, keeps its git
shell on purpose — see "What this spec is not" — and the identity travels beside
its value rather than replacing it.

The three cases, complete. "Package directory" means the directory holding the
`factory` package this process imported, never the process working directory:

| package dir inside a git work tree | distribution metadata resolvable | source | revision | stamp |
|---|---|---|---|---|
| yes | either | `git` | short sha | newest commit touching that directory — today's value, unchanged |
| no | yes | `distribution` | none | the installed distribution's own on-disk metadata |
| no | no | `unknown` | none | none — every surface degrades, and the skip names both attempts |

The third row is the only one in which anything is still lost, and it is the row
in which nothing could honestly be known. What changes there is the message: not
"git not answering", but what was tried and why each attempt failed.

**And the skew comparison is decided by what each side can report, not by
whether either side is a git checkout.** The CLI side arrives as one of three
shapes: a revision (with a version), a version and a stamp but no revision, or
nothing at all. The worker side arrives as one of four, because a worker still
running the code that was there before this story sends a bare `worker_revision`
and no identity at all — the shape
`tests/test_ergane_build_status_refusal.py:309` — `_query_document` builds, and
the shape of every call until that worker is restarted. All twelve combinations,
and the requirement that decides each:

| worker side | CLI side | notice |
|---|---|---|
| revision | revision | silent when the revisions are equal; today's byte-identical warning when they differ (FR-017) |
| version only | version only | silent when the versions are equal (FR-016); a warning naming both versions when they differ (FR-017) |
| revision | version only | a warning naming both sources and both values, because no revision comparison is possible (FR-020) |
| version only | revision | the same warning, mirrored (FR-020) |
| revision only, no identity | revision | compared by revision and nothing else, exactly as today: silent when the two are equal, today's byte-identical warning when they differ (FR-021, which routes the row to FR-017) |
| revision only, no identity | version only | silent, exactly as today (FR-021) |
| nothing | anything | a warning naming the worker as the side that could not be read, and the reason its identity carried (FR-018) |
| anything | nothing | a warning naming the CLI as that side, and the reason its identity carried (FR-018) |

The last two rows are the catch-all: they take precedence over every row above
them, because a side that resolved nothing cannot be compared with anything —
including over the two `revision only, no identity` rows, so a CLI that can say
nothing about itself is still named however old the worker is.

The two mixed rows are the ones an earlier draft left to the implementer, and
they are not hypothetical — a CLI run from the checkout against a worker started
from a packaged install is exactly that shape, and it is the run the operator
makes at `plan.md` § "Verification the operator will run" step 4. They warn,
because two sides reading their identity from different sources cannot be shown
to be running the same code; and warning there does not reintroduce the defect
this spec closes, which is the second row — both sides packaged and agreeing.

The two `revision only, no identity` rows are the upgrade window, and they are
not a corner either: they are **every** call this command makes until an
operator restarts the worker, and they are the shape all seven landed skew tests
in `tests/test_ergane_build_status_refusal.py` build. FR-021 decides them by
keeping today's behaviour exactly — a bare revision is a revision-only side —
because the obvious alternative, reading "no identity" as "resolved nothing" and
routing the row to FR-018, would close the operator key's permanent warning on
one install shape and reopen it on every worker that has not yet been restarted.

### What this spec is not

It is not a change to what the stale-worker probe compares. Once it has a stamp
it compares the worker's process start time against it, which is what it does
today; the key `ops/stale-worker` and its `Severity.CRITICAL` are untouched.

It is not a new store. The identity is resolved from what is already on disk —
a git work tree or an installed distribution's own metadata — and nothing is
written anywhere.

It is not a change to what `worker_revision` means.
`factory/versioning.py:94` — `resolve_deployment_version` refuses a `None` revision
under engaged versioning
on purpose, because a build id nobody can map back to a commit is a build id
nobody can redeploy. That refusal survives this spec intact.

It is not a removal of `factory/cli/nouns/build.py:966` — `_cli_revision`. That
surface keeps a name, keeps its `str | None` shape for the revision, and stays
reachable through the package-level seam at
`factory/cli/nouns/__init__.py:37` — `_cli_revision_for_tests`. What FR-019
removes is its *git shell*: the CLI's side of the skew comparison is read from
the resolver, the same identity `ergane --version` renders. Whether the function
survives as a thin wrapper or is replaced by a call that returns the whole
identity is the implementer's choice; what may not survive is a second
`git rev-parse` in that file.

It is not the CLI-to-engine version handshake. That comparison — which passes a
stale engine because two different trees call themselves the same version — is
the other half of the container corpus's finding and is not touched here.

## User Scenarios & Testing

### User Story 1 - One resolver answers "what code is this" (Priority: P1)

As the factory, I can say which build I am from an installed distribution as
well as from a checkout, and I can say which of the two I read it from.

**Why this priority**: P1 and it depends on nothing. It is the missing fact all
three remaining stories consume; without it each of them would grow its own
fallback and the defect class — four implementations of one question — would be
reproduced rather than closed.

**Independent Test**: Resolve the identity from a copy of the package placed
outside every git work tree, and from the checkout, and read the source, the
revision and the stamp each answer carries.

**Acceptance Scenarios**:

1. **Given** the `factory` package copied into a directory under the test's
   temporary path — outside every git work tree — beside a **synthetic**
   `ergane_cli-<version>.dist-info` written into that same directory, and
   imported from there, **When** the identity is resolved, **Then** it carries
   that distribution's version and a stamp derived from that distribution's own
   on-disk metadata, and names its source as the distribution rather than git.
   A committed test asserts this in a subprocess whose `PYTHONPATH` names the
   directory, and asserts **first** that the resolved distribution's own
   location lies under the temporary path: the host's installed `ergane-cli`
   distribution is still resolvable from that subprocess and answers otherwise,
   so without that assertion a resolver that never looks at the package
   directory at all satisfies this criterion. It asserts in the same test that
   the identity resolved from the checkout names git and carries the checkout's
   short revision — the pair is the evidence, because either half alone passes
   for the wrong reason.
2. **Given** that same distribution-sourced identity, **When** the stamp is
   compared against the synthetic distribution's own metadata file under the
   temporary path, **Then** they are equal, and the same committed test carries
   the control that decides FR-003: rewriting that metadata file moves the
   stamp, while touching a file inside the copied package does not — so a stamp
   taken from the clock or from the imported module's mtime fails the test
   rather than passing it. The rewrite sets that file's modification time
   explicitly to at least a second later rather than relying on the write's own
   clock, because the consumer compares whole seconds
   (`factory/doctor/probes.py:99`) and a rewrite inside one wall-clock second
   would otherwise fail the control for a reason that has nothing to do with
   FR-003. The file rewritten is the synthetic one and never the
   installed distribution the gate itself runs from, which the US1-S1 assertion
   about the resolved location is what makes certain.
3. **Given** the checkout, **When** the identity is resolved with the process
   working directory set to an unrelated git repository built by the fixture,
   **Then** the stamp and revision are the ones belonging to the package's own
   directory and not the unrelated repository's, proven by a committed test that
   asserts the two repositories report different values and that the resolver
   returned the package's.
4. **Given** a copy of the package outside every git work tree **and** no
   resolvable distribution metadata, **When** the identity is resolved, **Then**
   its source is the unknown one and it carries a reason naming both attempts —
   the git read and the distribution lookup — and why each failed, asserted
   against the reason string in a committed test.
5. **Given** the resolver, **When** it needs the version, **Then** it obtains it
   from `factory/supervision/engine_identity.py:38` — `cli_version` rather than
   performing a second version lookup, proven by a committed test that asserts
   the resolver's version equals `cli_version()` and that exactly one call site
   in `factory/supervision/engine_identity.py` resolves to `importlib.metadata`'s
   `version` — counted over the module's parsed syntax tree, following the
   `from importlib.metadata import version` binding at
   `factory/supervision/engine_identity.py:45`, because the literal text
   `importlib.metadata.version` appears nowhere in that module and a search for
   it returns zero. The single `importlib.metadata.distribution` call that
   FR-003's stamp requires is not a version lookup and is expected to appear in
   the diff.

### User Story 2 - The stale-worker probe returns a verdict instead of a permanent skip (Priority: P1)

As an operator running a packaged install, `ergane doctor` tells me whether my
worker is stale instead of telling me git is not answering.

**Why this priority**: P1 and it consumes US1. This is the CRITICAL check, it is
the one surface that raises rather than degrades, and it is the one whose loss
also forces a non-zero exit code on every run.

**Independent Test**: Gather the stale-worker probe from a package copy outside
every git work tree and read the snapshot; then run the probe driver over a
registry containing it and read the exit code.

**Acceptance Scenarios**:

1. **Given** the package copied outside every git work tree, **When**
   `StaleWorkerProbe.gather` runs, **Then** it returns a snapshot carrying a
   stamp rather than raising, asserted by a committed test that runs the gather
   in that layout and pastes the resulting snapshot as evidence. The control in
   the same test proves the fixture is an honest no-git layout rather than a
   lucky one: `git log -1 --format=%ct %H -- factory/` run in that layout
   returns no usable line, so the gather cannot be answering for an ambient
   reason.
2. **Given** that snapshot and a worker process whose start time precedes the
   stamp, **When** the probe evaluates, **Then** it files `ops/stale-worker`
   with today's key and `Severity.CRITICAL` unchanged, asserted field by field
   in a committed test, because the comparison is not what this story changes.
3. **Given** a probe registry whose probes all answer, **When** the driver runs
   in the same installed-layout fixture US2-S1 uses, carrying the same control —
   `git log -1 --format=%ct %H -- factory/` run in that layout returns no usable
   line — **Then** it returns the success exit code, and the diff contains **no
   edit** to `factory/cli/doctor.py`. The fixture and the control are load-
   bearing, not decoration: a node worktree is itself a git checkout, so a test
   that merely changes directory inside it goes green on FR-002's anchoring
   alone, with FR-003's distribution fallback entirely unimplemented, and the
   judge cannot tell the two apart from the diff. The exit code clears because
   nothing skipped, not because the arm at
   `factory/cli/doctor.py:206` — `_run_all_probes` learned about this spec.
4. **Given** neither a git answer nor resolvable distribution metadata, **When**
   the probe gathers, **Then** it still skips, and the refusal names both
   attempts and why each failed rather than naming git alone, asserted against
   the message text in a committed test.
5. **Given** the snapshot dataclass, **When** it carries a stamp that came from
   an installed distribution, **Then** the field it sits in is not named for a
   git commit **and** the `ops/stale-worker` finding built from it claims no
   commit either — its summary names the build stamp and the source it came
   from rather than a `factory/` commit, and none of its refs carries a `git/`
   prefix — asserted by a committed test that constructs the snapshot from
   distribution-sourced values without using any field whose name claims a
   commit, calls `evaluate`, and asserts on the finding's summary and refs.
   Renaming the fields alone is not enough: today's summary at
   `factory/doctor/probes.py:366` and refs at `factory/doctor/probes.py:374`
   and `factory/doctor/probes.py:376` would then render `commit None` to the
   operator, which is the same lie one layer out.

### User Story 3 - `ergane --version` names a build instead of printing `(unknown)` (Priority: P2)

As an operator, the command I run to find out what I have tells me what I have.

**Why this priority**: P2 and it consumes US1. It is the smallest of the three
consumers and the most visible; it is also the surface a consumer quoted when
reporting that no version surface in this product can distinguish a modified
stack from the published one.

**Independent Test**: Render the version text against each of the three
identities and read the first line.

**Acceptance Scenarios**:

1. **Given** an identity whose source is git and which carries a revision,
   **When** the version text is rendered, **Then** its first line is
   byte-identical to today's for the same version and revision, asserted against
   a literal expected string in a committed test, because a checkout must not
   notice this story.
2. **Given** an identity whose source is the installed distribution, **When**
   the version text is rendered, **Then** its first line names the version and
   the build stamp and contains no `(unknown)` parenthetical, asserted against
   the rendered string in a committed test.
3. **Given** an identity that could not be resolved at all, **When** the version
   text is rendered, **Then** it still returns its three lines without raising
   and still resolves no endpoints it did not already resolve, asserted in a
   committed test that supplies no control plane — the command run to find out
   what you have must answer from a broken host (048-US4).

### User Story 4 - The skew check compares what both sides can actually report (Priority: P2)

As an operator on a packaged install, the worker-skew warning fires when the
worker and the CLI disagree, and is silent when they agree.

**Why this priority**: P2 and it consumes US1. It owns two ledger keys — the
mechanism and its consequence — and it is the story that turns a signal which
currently fires on every single call back into a signal.

**Independent Test**: Render the skew notice for each combination of what the
two sides can report, and drive the worker's own advertisement through the
dispatch payload.

**Acceptance Scenarios**:

1. **Given** a worker and a CLI that both report no revision and the same
   version, **When** the skew notice is rendered, **Then** it is absent,
   asserted in a committed test — this is the case that fires on every call
   today and it is the whole of the consequence key.
2. **Given** a worker and a CLI that both report no revision and **different**
   versions, **When** the skew notice is rendered, **Then** it warns and names
   both versions, asserted against the rendered string in a committed test.
3. **Given** a worker and a CLI that both report revisions which differ,
   **When** the skew notice is rendered, **Then** the warning is byte-identical
   to today's, asserted against a literal expected string, because that is the
   case the check was built for and operators read it in runbooks.
4. **Given** one side that can report nothing at all, **When** the skew notice
   is rendered, **Then** it names which side could not be read and the reason
   the identity carried, rather than today's fixed sentence about predating the
   check, asserted against the rendered string in a committed test.
5. **Given** the worker's dispatch payload, **When** the worker advertises its
   build identity, **Then** the value carried in `worker_revision` is unchanged
   and `factory/versioning.py:94` — `resolve_deployment_version` still raises
   when the revision is `None` under engaged versioning, asserted in a committed
   test; the identity travels in a field beside it, defaulted so a payload
   written before this story is accepted unchanged.
6. **Given** the CLI's own side of the comparison, **When** the status command
   reads it, **Then** it comes from the resolved identity and `git rev-parse` is
   **invoked** nowhere in `factory/cli/nouns/build.py`, asserted by a committed
   test that parses the module and finds no subprocess call carrying that
   argument list — not by a search for the literal text, which the seam comment
   at `factory/cli/nouns/build.py:969` also matches, so a text search would fail
   an otherwise correct implementation; the package-level seam at
   `factory/cli/nouns/__init__.py:37` — `_cli_revision_for_tests` still
   overrides what the command reads, asserted in the same test.
7. **Given** one side whose identity is git-sourced and carries a revision and
   one whose identity is distribution-sourced and carries a version and a stamp
   but no revision, both having resolved and both reporting the same version,
   **When** the skew notice is rendered, **Then** it warns and names both
   sources and both values, asserted against the rendered string in a committed
   test for both orderings — worker git and CLI distribution, and the reverse.
   This is the row an earlier draft left undecided; it is what a CLI run from a
   checkout against a worker started from a packaged install actually looks
   like, and it is the row the operator's step 4 turns on.
8. **Given** a status document carrying a `worker_revision` and no build
   identity at all — the payload every worker still running the code that was
   there before this story sends, and the document
   `tests/test_ergane_build_status_refusal.py:309` — `_query_document` builds
   today — **When** the skew notice is rendered, **Then** the worker is treated
   as a revision-only side: with a CLI side carrying a revision the notice is
   absent when the two revisions are equal and byte-identical to today's warning
   when they differ, and with a CLI side carrying a version but no revision the
   notice is absent rather than FR-018's unreadable-side sentence. All three
   sub-cases are asserted in a committed test against a status document built
   **without** the new field, because that is what every worker sends until it
   is restarted and a rule that warns here reopens the operator key's defect on
   every un-restarted worker.

## Functional Requirements

- **FR-001**: A single build-identity resolver MUST answer, for the `factory`
  package this process imported, a version, a stamp timestamp, an optional
  revision, and the name of the source those came from.
- **FR-002**: The resolver's git read MUST be anchored on the imported package's
  own directory and MUST NOT depend on the process working directory, so an
  invocation from an unrelated repository cannot change the answer.
- **FR-003**: When the git read does not answer, the resolver MUST fall back to
  the installed distribution: the version from the distribution's metadata and
  the stamp from that distribution's own on-disk metadata, so a reinstall of the
  same version moves the stamp.
- **FR-004**: The resolved identity MUST name which source produced it, so a
  reader can tell a checkout answer from a distribution answer without inferring
  it from the shape of the values.
- **FR-005**: When neither source answers, the identity MUST report the unknown
  source and MUST carry a reason naming both attempts and why each failed.
- **FR-006**: The resolver MUST obtain the version from
  `factory/supervision/engine_identity.py:38` — `cli_version`, and after this
  story `factory/supervision/engine_identity.py` MUST hold exactly one call site
  resolving to `importlib.metadata`'s `version` — the existing one inside
  `cli_version`, reached through the `from importlib.metadata import version`
  binding at `factory/supervision/engine_identity.py:45`. The requirement is
  scoped to that module and not to the tree:
  `factory/supervision/container_project.py:157` binds the same lookup for the
  engine image, is pre-existing, and no story here owns that file. The one
  `importlib.metadata.distribution` call FR-003's stamp requires is not a
  version lookup and is permitted.
- **FR-007**: `factory/doctor/probes.py:328` — `StaleWorkerProbe.gather` MUST
  obtain its stamp from the resolver, and MUST return a snapshot rather than
  raising whenever the resolver produced an identity.
- **FR-008**: The probe's comparison MUST remain the worker's process start time
  against the stamp of the code it runs, and `ops/stale-worker` MUST keep its key
  and its `Severity.CRITICAL`.
- **FR-009**: A host with no git answer and nothing else wrong MUST get the
  success exit code from the probe driver, and the diff MUST NOT edit
  `factory/cli/doctor.py` — the exit code clears through the absence of a skip.
- **FR-010**: When the identity is unknown the probe MUST still skip, and the
  skip's reason MUST name both attempts rather than naming git alone.
- **FR-011**: The stale-worker snapshot's fields MUST be named for what they now
  hold — a stamp of the code this process imported — so a distribution-sourced
  value is never carried under a field claiming a git commit; and the
  `ops/stale-worker` finding those fields feed MUST make the same claim honestly
  in the text an operator reads. Today its summary at
  `factory/doctor/probes.py:366` — `StaleWorkerProbe.evaluate` says "before
  newest `factory/` commit <sha> at <timestamp>" and its refs at
  `factory/doctor/probes.py:374` and `factory/doctor/probes.py:376` carry
  `git/timestamp:` and `git/commit:`. When the identity is not git-sourced,
  neither the summary nor any ref may claim a commit: both MUST name the build
  stamp and the source it came from. The finding's key, its category and its
  `Severity.CRITICAL` are unchanged by this requirement (FR-008).
- **FR-012**: `ergane --version` MUST render from the resolved identity, and
  MUST NOT emit the `(unknown)` parenthetical when a version is known.
- **FR-013**: For an identity whose source is git, the first line of
  `ergane --version` MUST be byte-identical to today's for the same version and
  revision.
- **FR-014**: `ergane --version` MUST keep answering when no identity can be
  resolved, and MUST NOT resolve any endpoint it does not resolve today.
- **FR-015**: The worker MUST advertise its build identity beside
  `worker_revision` on the dispatch payload and in the query answer, defaulted so
  a payload written before this story is accepted unchanged; the value carried in
  `worker_revision` MUST NOT change, and
  `factory/versioning.py:94` — `resolve_deployment_version` MUST keep refusing a
  `None` revision under engaged versioning.
- **FR-016**: `factory/cli/nouns/build.py:986` — `_skew_notice` MUST return no
  notice when neither side reports a revision and both report the same version.
- **FR-017**: `_skew_notice` MUST still warn when the two sides disagree, whether
  they disagree by revision or by version, and its revision-disagreement text
  MUST be unchanged.
- **FR-018**: When one side can report nothing at all, `_skew_notice` MUST name
  which side and the reason its identity carried, rather than today's fixed
  sentence about predating the check.
- **FR-019**: The CLI's own side of the skew comparison MUST come from the
  resolved identity, and `factory/cli/nouns/build.py` MUST contain no
  `git rev-parse` invocation after this story; whatever replaces
  `factory/cli/nouns/build.py:966` — `_cli_revision` MUST stay overridable
  through the package-level seam at
  `factory/cli/nouns/__init__.py:37` — `_cli_revision_for_tests` or one added
  beside it.
- **FR-020**: When both sides resolved an identity but only one of them carries
  a revision, `_skew_notice` MUST warn and MUST name both sources and both
  values, because two sides that read their identity from different sources
  cannot be shown to be running the same code. This row is distinct from FR-016,
  which is both sides reporting no revision **and** the same version, and from
  FR-018, which is a side that resolved nothing at all.
- **FR-021**: A status payload that carries `worker_revision` and no build
  identity at all — the payload every worker still running the code that was
  there before this story sends, and therefore every call until that worker is
  restarted — MUST be treated as a revision-only side: compared by revision when
  the other side carries one, with FR-017's revision-disagreement text unchanged,
  and silent when the other side carries a version but no revision. Both are what
  happens today. It MUST NOT be routed to FR-018 on account of its missing
  identity: that warning would then fire on every call until the worker is
  restarted and reopen the defect the operator key was filed on. FR-018 still
  decides the row in which the *other* side resolved nothing at all.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005, FR-006]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-007, FR-008, FR-009, FR-010, FR-011]
  concurrent_with: [US3, US4]
US3:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-012, FR-013, FR-014]
  concurrent_with: [US2, US4]
US4:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-015, FR-016, FR-017, FR-018, FR-019, FR-020, FR-021]
  concurrent_with: [US2, US3]
```

Three `depends_on_merged` edges and no pass-edges. US2, US3 and US4 each consume
the resolver US1 adds, so each needs US1's code present in the branch it builds
on — that is a merge edge, not a pass edge, because nothing about US1's verdict
constrains the others beyond its code existing. They are declared rather than
left inferred (069-US2 FR-007).

The three consumers are mutually `concurrent_with` because they name no
production file in common: US2 is `factory/doctor/probes.py`, US3 is
`factory/cli/main.py`, US4 is `factory/cli/nouns/build.py`,
`factory/cli/nouns/__init__.py`, `factory/worker.py` and
`factory/workgraph/workflow.py`. The only file all four touch is the resolver's
module, and only US1 writes it — the other three read it. Declaring the override
rather than letting contention be inferred is what keeps the three consumers
from being serialised behind each other for a shared file that does not exist.
