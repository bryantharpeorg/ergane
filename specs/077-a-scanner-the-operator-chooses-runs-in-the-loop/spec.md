---
state: draft
# Drafted 2026-08-20 ~6:00 PM CT by an operator session, at the operator's
# direction: "I want to add a way to factor in code quality in the scan as well
# ... perhaps the agent loop validates on both judge and a deterministic
# sonarqube style quality scan and either of those being too low can send it
# back for more work", then refined by two explicit decisions and one
# requirement added mid-draft.
#
# THE OPERATOR'S THREE DECISIONS, stated here so no implementer re-litigates
# them and no reviewer reads this spec as timid:
#
#   1. RECORD-ONLY FIRST. The scan runs, computes, and records. It does NOT
#      change a verdict. Thresholds come from a later spec, set against the
#      distribution this one measures. Chosen over gating-on-day-one because
#      dispatch rework is at 37.9% and flat across three weeks, so a new way to
#      fail would arrive as noise indistinguishable from signal.
#   2. DETERMINISTIC RULES ONLY, when gating eventually arrives. Lint
#      violations, type errors and security patterns -- checks where satisfying
#      them and gaming them are the same act. Complexity, duplication and
#      maintainability index are recorded and trended, never made to fail a
#      story. COVERAGE IS EXCLUDED ENTIRELY; see "What this spec refuses to
#      measure".
#   3. THE INTEGRATION IS A HOOK, NOT A HARDCODE. Added mid-draft: "i want these
#      integrations to be done in some sort of hook system so that they're
#      optional and easily swappable". This is why US3 exists and why the
#      registry, not the scanner, is the deliverable.
#
# WHAT WAS CHECKED BY RUNNING IT, 2026-08-20:
#
#   $ gh repo view --json visibility,nameWithOwner
#   {"nameWithOwner":"bryantharpeorg/ergane","visibility":"PUBLIC"}
#
# That answers the operator's open question ("github i believe also has code
# scanners now too, im not sure if theres a way to use theirs or if that
# requires a better account"). It does not require a better account: CodeQL code
# scanning is free for public repositories. It is nonetheless the WRONG SHAPE
# for this spec, and the reason is timing, not money -- see "Why GitHub's
# scanner is a backstop and not a step".
#
#   $ for t in ruff radon xenon pylint mypy bandit jscpd diff-cover; do ... done
#   all eight: not installed
#
# So no candidate scanner is present on this host, and Constitution III admits
# none of them. US1 exists to measure before that approval is spent.
#
# HELD AT DRAFT. 067-069 were flipped straight to `ready` and a twelve-agent
# pre-dispatch review then found 68 attempt-costing defects. That review is the
# rule now. This spec goes to `ready` only after it comes back clean.
#
# THE PRE-DISPATCH REVIEW RAN 2026-09-04 AND THE SPEC DID NOT COME BACK CLEAN.
# It came back with twenty validate refusals and five instructions that had gone
# wrong in the tree, all repaired below. The hold above is unchanged and the flip
# is still the operator's: this refinement is not permitted to write `ready`.
#
# THE ADVERSARIAL RE-READ OF THAT REPAIR RAN 2026-09-04 AND REFUTED IT ON SIX
# BLOCKING DEFECTS. They are repaired in the REPAIRED entry below. The hold
# stands: this spec is still `draft` and still the operator's to flip.
#
# A SECOND ADVERSARIAL RE-READ RAN 2026-09-04 AND REFUTED IT AGAIN, ON THREE
# BLOCKING DEFECTS AND EIGHT MINOR ONES. All three blockers were claims about
# mechanism rather than moved lines: this repository's manifest is `ergane.yaml`
# and the trio named the deprecated `factory.yaml` five times; FR-026's "outside
# the node worktree" is not what `_resolve_target_git_dir` guarantees on both its
# branches; and the `quality:` block had no `command:` key for the command FR-014
# requires the adapter to run. All are repaired in the second REPAIRED entry
# below. The hold is still the hold. This spec is `draft` and the flip is the
# operator's; the review this hold asks for has now run three times and this pass
# is not permitted to answer it.
#
# A THIRD ADVERSARIAL RE-READ RAN 2026-09-04 AND REFUTED IT ON THREE MORE
# BLOCKING DEFECTS AND TEN MINOR ONES. All three blockers were again claims
# about mechanism rather than moved lines, and each was settled by running the
# tree rather than by reading it: `uvx` is not carried into the gate boundary at
# all -- `_toolchain_binds` ro-binds four executable LEAVES and never their
# directory -- so US1's own FR-001 and FR-002 could not both be satisfied;
# `_VERIFY_STEPS` is *also* what `_read_verify` returns when a manifest declares
# no `verify:` key, and this repository's `ergane.yaml` declares none, so growing
# that one tuple would have moved this repository's own `loop_digest` and failed
# US2's own scenario; and the `command:` key the second repair added had no
# stated way to learn the path the adapter picks, which is the operator's third
# decision made concrete and it was unbuilt. All are repaired in the third
# REPAIRED entry below. The hold is still the hold: this spec is `draft`, the
# review this hold asks for has now run four times, and this pass is not
# permitted to answer it.
#
# REFINED 2026-09-04 by the refinement workflow (refinement-2026-09-04); every
# anchor in spec.md, plan.md and tasks.md re-read from ergane-buildout at
# 602a92c with `sed -n`, not recalled.
#
# WHERE THIS CAME FROM. The operator's own request, quoted at the top of this
# block, plus the gap the two existing instruments leave: a gate is a verdict
# with no number on it and a judge is a metered opinion. Nothing in the loop
# measures.
#
# WHAT IT COST, MEASURED. Not this defect -- this is a want, not a recurrence --
# but the argument for record-only-first is measured and is in the tree:
# `factory/verify/diffbounds.py:41-47` records a limit set as "a comfort margin,
# not a measurement", whose first false positive refused a fully-green story
# four times at 61,725 bytes. That is what a threshold set before the
# distribution is known costs, and it is why US5 exists and why gating is a
# separate spec.
#
# WHAT CHANGED IN THIS REFINEMENT, MEASURED. Every anchor in the trio was
# re-read. The citation counts this block twice advertised were themselves wrong
# both times: the 51/118 pair the first repair pass wrote was plan.md's
# occurrence count mistaken for the trio's, and the 89/211 pair the second wrote
# was measured against a draft rather than against the files it shipped beside.
# They are restated in the third REPAIRED entry, measured after the final write
# by one grep for backticked path-colon-line tokens across the three files, and
# this sentence is why a reader should check them rather than believe them. Two
# resolved unchanged
# (`factory/notify/adapter.py:70` and `factory/controlplane/config.py:51`);
# every other one had moved, most of them by hundreds of lines, because eight
# specs landed on `factory/verify/` between 2026-08-20 and 2026-09-02. Validate
# refused twenty times across them, three of those from the symbol tier, and
# passed the rest -- which is the recorded lesson about the anchor tiers, met
# again.
#
# FIVE INSTRUCTIONS HAD GONE WRONG, AND THEY ARE THE EXPENSIVE PART.
#   (a) `SCHEMA_VERSION` is 13, not 6; US6 makes it 14. The plan told an
#       implementer to write a migration for a store six versions behind.
#   (b) 117 changed the upsert key to five columns including `dispatch`, and
#       made `_RESULT_COLUMNS` positional -- a new column added in the wrong
#       order hands every field of every row to the wrong attribute and raises
#       nothing. FR-022 and a new trap now say so.
#   (c) `verify_order` does not sequence the loop. It feeds `loop_digest` and
#       nothing else; the steps are hardcoded in `_verify`. US2 adding a step
#       name therefore executes nothing, and the wiring is US6's. New FR-027.
#   (d) 101 made the gate boundary manifest-selected and falls back to the host
#       subprocess executor when bwrap is absent, so "run it in the real
#       sandbox" is now a thing a spike can silently fail to do. FR-002 makes
#       the backend a recorded fact.
#   (e) The dispatch pin (FR-010) has a named home the plan never mentioned:
#       `EpicInput.verify_order`. That entry named three `EpicInput`
#       constructors and undercounted the chain; the repair below anchors the
#       two carriers between the manifest and them.
#
# TWO HAZARDS THE NEIGHBOURS ADDED, NOW DECLARED SCOPE. `worktree.diff` stages
# with `git add -A` and `salvage` commits the same set, so ANY file a scanner
# leaves in the node worktree is committed, judged, and counted against the diff
# refusal threshold. A single real SARIF file would refuse the story unjudged.
# That is new FR-026 and trap 2. And FR-004's "commit a real SARIF artifact"
# was itself unbuildable for the same reason: US1's artifacts are now bounded
# by construction.
#
# ONE SCENARIO CONTRADICTED THE SPEC'S OWN RULE. US2-S3 justified its ordering
# rule as "so a red scan can skip a metered judge exactly as a red gate already
# does" -- which is gating, in a record-only spec. The rule is kept; the reason
# is now the seam a later spec needs, and a red scan skips nothing.
#
# NO `fixes:` KEY IS DECLARED, DELIBERATELY. The ledger was read at 602a92c and
# holds no open finding this spec's FRs would close whole. A key naming a defect
# these requirements only touch would let triage credit it and stop counting.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04): the TMPDIR SARIF seam replaced
# with the one writable non-worktree bind that survives the boundary, and the
# false "no network / --clearenv" premise replaced with what the boundary
# actually does; the scanner closed set given one home in US2 and US3's task
# reduced to conformance; the dispatch chain re-anchored through
# `load_loop_config` and `ReadLoopConfigResult` instead of three constructors;
# FR-027 given the guard its own truth table implied; US4-S3's tautological
# verdict comparison rewritten to compare the whole recorded row; FR-004's
# artifacts given a byte bound rather than a scan bound; US4 split into US4
# (scoping) and new US6 (record and wire); four anchors whose prose overshot
# the line corrected; the refinement's own two counts corrected.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04, second adversarial re-read): the
# trio named `factory.yaml` as this repository's manifest and never named
# `ergane.yaml`, which is the file `MANIFEST_NAME` actually resolves and the only
# one carrying `version: 2` and a `ladder:` block -- every citation moved and a
# new trap 16 names the stale v1 legacy file still in the root; FR-026's
# "outside the worktree" absolute replaced with the invariant
# `_resolve_target_git_dir` really delivers on both its branches, with US3's two
# fixture shapes stated rather than left to guess; the `quality:` block given the
# `command:` key FR-014's "declared command" had no declarer for, and the closed
# set stated as the ADAPTER names `sarif`/`none` so US1's recommendation lands in
# `command:` instead of in a constant US2 cannot see; FR-010's "each `EpicInput`
# construction" narrowed to the two that read a manifest, with
# `factory/workgraph/cli.py:675` — `_start_epic` named out of scope; four
# anchors moved onto the
# line their sentence is about; US5 given a section, a precedent and an honest
# sizing row; US6-S1 given the workflow harness precedent it lacked; US2 given
# the sizing argument the plan applied to its sibling and not to it; the
# refinement's own anchor counts re-measured.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04, third adversarial re-read): `uvx`
# replaced by `uv tool run` in FR-001, US1-S1, US1-S7 and four tasks, with new
# trap 17 naming the leaf-bind mechanism that keeps `uvx` out of the boundary
# and the unconditionally bound uv cache that makes `uv tool run` cheap inside
# it; `_VERIFY_STEPS`'s second role as the absent-key default declared, as
# FR-005's second half, US2-S5's order assertion, new trap 18 and a split T021 --
# this repository declares no `verify:` key, so the obvious implementation would
# have moved its own digest; the whole content chain converted from pass-edges
# to merge-edges, the form 092, 101, 117 and 126 all use, because a dependent
# dispatched before its predecessor lands gets a base without the constant,
# module or column it must build on; trap 15's second admissible move struck,
# since FR-009 forbids it in terms, and fenced with new US2-S10 whose Then is
# the pasted before/after digest T031 already produced; the `command:`-to-SARIF
# seam named at last -- one exported environment variable on the invocation's
# `env` -- in FR-007, FR-014, US3-S2, T010, T033, T041, T045 and T078, because a
# path the factory computes and never tells the command about is the one
# spelling of the operator's third decision that cannot work; FR-026 and US3-S7
# tightened from the shared parent `.git` to a path unique to the worktree,
# since that directory is one per repository and the node cap has run at two;
# FR-016's deadline given the source it lacked, so US3 does not invent a
# manifest key inside a block US2 already landed; FR-004's artifact set bounded
# at two here rather than by the implementer at commit time against a threshold
# that refuses the story unjudged; US6-S2 folded into US6-S1 and that story's
# scenarios renumbered, so no scenario stands that a test-only diff satisfies
# alone; US2's Sizing row given the two landed test files that unpack
# `load_loop_config`'s tuple positionally; the plan's claim that a US3 fixture
# meets the ordinary-repository branch withdrawn, because none does; and
# twenty-one anchors rewritten into the machine-checked symbol form.
#
# NO `fixes:` KEY IS ADDED, AGAIN DELIBERATELY. The ledger was read once more at
# 602a92c -- 520 rows -- and still holds no open finding these twenty-seven
# requirements would close whole. The three nearest are the attestation-surface
# feedback rows, and they belong to draft spec 134, not here.
#
# ANCHOR CITATIONS AFTER THIS WRITE, MEASURED: 121 unique `path:line` citations
# across 324 backticked occurrences -- spec.md 27 of 38, plan.md 118 of 177,
# tasks.md 85 of 109 -- counted by one grep for backticked path-colon-line
# tokens over the three files as they now stand, not as they were drafted.
#
# NOT IN SCOPE. No verdict moves, anywhere: `compose_result` does not gain a
# parameter and `OverallVerdict` composition is untouched. No threshold, in the
# manifest schema or the models or behind a disabled flag. No coverage metric.
# No new package in `pyproject.toml` or `uv.lock`. No change to `personas.yaml`,
# gate execution, the retry ladder or the merge queue. A manifest that does not
# name `quality` behaves byte-identically to today.
---

# Feature Specification: a scanner the operator chooses runs in the loop

**Created**: 2026-08-20
**Depends on**: nothing.

## The gap, stated precisely

Verification has exactly two instruments, and neither one measures the code.

1. A **gate** is deterministic and binary. It reports that `pytest` exited 1,
   with 32 KiB of tail. Its record is `factory/verify/models.py:362` —
   `GateResult`, and every field it carries at
   `factory/verify/models.py:398-406` is a fact about the *run* rather than
   about the *code*: `name`, `command`, `status`, `exit_code`, `duration_s`,
   `output_tail`, and since 084 `concurrent_gates`, `worktree_writes` and
   `writes_declared`. There is nowhere to put "this diff added a function whose
   cyclomatic complexity is 19 where the file's base was 7". Every gate answer
   is a verdict already; nothing survives it a later run could compare against.
2. A **judge** measures, but it is an LLM. It is metered, it is
   non-deterministic across runs, and its output is a scenario-by-scenario
   opinion about acceptance criteria. Asking it "is the complexity acceptable"
   spends money to get an answer that will not reproduce, on a question a parser
   can settle for free.
3. Between them sits the whole of code quality, and nothing occupies it. The
   verification phase at `factory/workgraph/workflow.py:2559` — `_verify` runs
   gates, then the diff check, then — only if it can still matter — the judge.
   There is no fourth call, and no store column to put a fourth answer in:
   `factory/verify/store.py:711` is `_RESULT_COLUMNS`, the complete list a
   verification row is written from, and its twenty-three entries run
   `factory/verify/store.py:712-734`.

## A gate is the wrong place to put a threshold

The nearest workaround is a gate — `gates: {quality: "..."}`, non-zero exit
means FAIL. It needs no factory change at all, and it is the honest fallback if
this spec is never built. Three things make it unsuitable as the destination:

1. **Gate commands are read from the node's own worktree.** The verification
   loop is pinned at dispatch from the operator clone so a node cannot move it
   — `factory/workgraph/workflow.py:562` — `EpicInput` says exactly that about
   `verify_order` — but gate commands are deliberately left on the worktree side
   to preserve the CI backstop. A threshold on the worktree side is a threshold
   the agent being measured can edit.
2. **A gate result has no score.** Nothing to trend, nothing to ratchet against,
   nothing that reaches `ergane findings` or the rework trend.
3. **A gate is already a verdict.** There is no way to express "run this, record
   what it says, and change nothing" — which is precisely the first phase the
   operator asked for.

## Why GitHub's scanner is a backstop and not a step

GitHub code scanning is free here — the repository is public. It is still the
wrong instrument for the ladder, for a reason that has nothing to do with
licensing: **it is asynchronous and it lives after the fact.** It runs in
Actions, on a pushed ref, and uploads SARIF that lands in the Security tab
minutes later. The loop needs an answer in the node's worktree, before the pull
request exists, while the ladder still has an attempt to spend.

Its natural home is exactly where the merge-group build already sits: a
post-merge deterministic backstop that catches what the loop missed. That is
worth having and it is not this spec.

The CodeQL *CLI* does run locally and synchronously and would be admissible as
an adapter under US3 — at the cost of a large pack download and a multi-minute
scan, which US1 is what measures.

## SARIF is the seam, not a bespoke plugin protocol

Every candidate — ruff, semgrep, bandit, the CodeQL CLI, and GitHub's own
upload path — converges on one format: SARIF 2.1.0, the OASIS standard GitHub
code scanning ingests. That is unusually lucky and this spec should spend it.

So the adapter contract is not "implement our interface". It is **run a command
against the worktree; leave SARIF behind on a path that survives the boundary
the command ran inside; the factory reads it.** The factory is what says
*where*: the adapter puts the destination it chose on one environment variable,
`ERGANE_QUALITY_SARIF`, and the operator's `command:` line references it
(FR-014). A path the factory computes and never tells the command about is the
one spelling of this contract that cannot work, and nothing else in the schema
names an output path. A scanner that emits SARIF is
swappable by editing the `command:` line of the `quality:` block in this
repository's manifest — `ergane.yaml`, which is what `MANIFEST_NAME`
(`factory/verify/factory_yaml.py:71`) resolves; the `factory.yaml` still sitting
beside it is the deprecated v1 legacy file and no reader consults it while
`ergane.yaml` exists — and installing a binary. `scanner:` names the *adapter*,
not the tool: `sarif` for anything that emits SARIF, `none` for off. Only a
scanner that needs real logic — one that talks to a server API, say, or a
SonarQube instance, whose native export is not SARIF — needs a Python adapter,
and the registry in US3 is where it registers.

**"Survives the boundary" is a measured constraint, not a phrase.** The gate
boundary this factory selects mounts a private tmpfs over `/tmp`
(`factory/verify/gates.py:678` — `_build_argv`) and sets no `TMPDIR` of its own,
so a SARIF file written under `/tmp` is destroyed with the namespace and the
factory never sees it. The writable binds outside the node worktree are the
declared caches (`factory/verify/gates.py:718` — `_build_argv`) and whatever
`factory/verify/gates.py:1018` — `_resolve_target_git_dir` returns, bound
`--bind` at `factory/verify/gates.py:704` — `_build_argv`, and the second is the
one the adapter can rely on without a manifest declaration. What that function
returns is *git metadata* rather than "somewhere outside the worktree": for a
linked worktree — what every node is — it is the parent repository's `.git`, and
for an ordinary repository it is `<worktree>/.git`. Both are invisible to
`git add -A`, which is the property the adapter needs. One caution rides with
the first branch: that `.git` is **one directory shared by every node worktree
of that parent repository**, and this floor has run the node cap at two, so a
fixed filename there is two concurrent nodes scoring each other's findings.
FR-026 therefore requires a path unique to the worktree being scanned. FR-026
names both; plan trap 2 shows the arithmetic.

## What this spec refuses to measure

**Coverage.** Named here as declared scope so no implementer adds it as an
obvious omission and no reviewer files it as a gap.

The same agent writes the code and the tests. A coverage number is the one
quality metric whose cheapest satisfying move is to write tests that assert
nothing, and this repository has already shipped four tests found structurally
unable to fail. A coverage gate does not detect that failure mode; it rewards
it. The judge, which reads what a test actually asserts, is the correct
instrument, and it already exists.

**Aggregate scores, as a gate.** Cyclomatic complexity, duplication ratio and
maintainability index are recorded by this spec and trended by US5. They are
excluded from any future gating decision because their cheapest satisfying moves
are `_helper_1`/`_helper_2` and a premature abstraction over two things that
should have stayed apart — both of which make the code worse while making the
number better.

## The rule this spec is asking for

**A repository may name a quality scanner in its verification loop; what that
scanner reports is written down as evidence and is never read as a verdict.**

The five cases, complete. Every row's verdict is the verdict the same attempt
would have reached with no scanner configured at all — that column is the rule:

| `quality` in `verify:` | the scan | scoped findings | verdict | quality evidence |
|---|---|---|---|---|
| absent | never invoked | — | today's, byte-identically | NULL |
| present | ran | none | today's | empty report, with scanner name and version |
| present | ran | four hundred | today's | four hundred scoped findings |
| present | failed, timed out, wrote unparseable output, or could not carry its artifact back across the boundary | — | today's | `scanner_unavailable`, with the reason |
| present | never invoked, because the gates or the diff check already failed | — | today's | NULL |

The fourth and fifth rows are different facts and must stay distinguishable: a
scanner that could not scan is not a scanner that found nothing, and neither is
a scan that never happened. The fifth row is a fact about the loop rather than
about the scanner, and it is only reachable because FR-027 gives the scan the
same green-so-far guard the judge already has at
`factory/verify/models.py:977` — `judge_required`.

### What this spec is not

It is not a threshold. Not in the manifest schema, not in the models, not behind
a disabled flag, not commented out. The follow-on spec adds them against the
distribution this one measures.

It is not a change to the verdict. `compose_result` gains no parameter, so no
future one-line edit can make a scan fail a story by accident. `ladder`,
`personas.yaml`, gate execution and the merge queue are untouched.

It is not a new mandatory dependency. A manifest that does not name `quality`
imports no scanner module, installs nothing, and resolves to a configuration
identical to today's.

It is not two scanners. One scanner per loop, by construction. The follow-on
spec may compose; this one may not.

## User Scenarios & Testing

### User Story 1 - The operator learns which scanners survive this sandbox (Priority: P1)

Before Constitution III approval is spent on a dependency, somebody runs the
candidates and writes down what happened.

**Why this priority**: every later story's shape depends on facts nobody has.
Whether `ruff` emits SARIF under the flag its docs claim, what a scan costs in
wall-clock on a real node diff, and — the one that decides everything — whether
a scanner can hand its SARIF back across the gate boundary at all. The boundary
is not the one folklore describes: it leaves network egress open on purpose
(`factory/verify/gates.py:549` — `BwrapGateExecutor`) and binds a resolver and
trust roots so egress works (`factory/verify/gates.py:888` — `_resolver_binds`),
it never passes `--clearenv`, and what it *does* restrict is the filesystem —
`/tmp` is a private tmpfs (`factory/verify/gates.py:678` — `_build_argv`) and
the only writable places outside the worktree are the declared caches and the
parent repository's `.git`. So "needs the network" disqualifies nothing here,
and "cannot get its artifact back to the host" disqualifies everything.

**Independent Test**: the committed research note names each candidate, the
exact command run, the exit code, the wall-clock, which gate backend executed
it, whether SARIF came back well-formed, and which destination the artifact
survived on; one bounded SARIF artifact from each surviving candidate is
committed beside it.

**Acceptance Scenarios**:

1. **Given** no scanner is installed on this host and none is on the approved
   roster, **When** the spike runs candidates through `uv tool run <tool>` —
   never `uvx`, which no bind carries into the boundary — without editing
   `pyproject.toml`, **Then** the note carries the pasted output of
   `git diff --stat -- pyproject.toml uv.lock` showing no change, and the
   evidence is still produced.
2. **Given** a candidate scanner, **When** it is run through the gate boundary
   this repository's manifest selects rather than through a bare
   `subprocess.run`, **Then** the note records the class name of the backend
   that actually executed it, pasted from the run, and a candidate executed by
   the host fallback rather than by the sandbox is recorded as **not measured**
   in those words.
3. **Given** a candidate that claims SARIF support, **When** its output is
   parsed, **Then** the note records the flag that actually worked with the
   command pasted verbatim, because a documented flag that does not exist is
   this repository's most expensive recurring defect class.
4. **Given** several surviving candidates, **When** their SARIF artifacts are
   committed, **Then** exactly two are committed — the recommended candidate's
   and one contrasting candidate's — each reduced to `runs[].results` plus only
   the rules those results name and held under 8 KiB, every other survivor is
   recorded as counts alone, and the note carries the pasted byte count of each
   unreduced document beside the pasted byte count of the story's whole diff and
   the refusal threshold it must stay under. Two, fixed here, rather than one per
   survivor: a story that discovers its own size at commit time discovers it by
   being refused unjudged.
5. **Given** the spike completes, **When** it recommends a default scanner,
   **Then** the recommendation cites the wall-clock pasted from each run,
   because a scanner slower than the gates it follows changes the loop's
   economics.
6. **Given** the backend this repository's manifest selects, **When** a probe
   command writes one byte to `$TMPDIR`, one to `/tmp`, and one to the node's
   own metadata directory under the parent repository's `.git`, **Then** the
   note carries a pasted host-side `ls -l` of all three taken after the
   executor returned, so which destination survives the boundary is a
   measurement rather than a reading of the mount set — this is the fact US3's
   FR-026 is built on.
7. **Given** a candidate that fails inside the boundary, **When** the note
   records why, **Then** it distinguishes a filesystem refusal (a path no bind
   carries) from a wall-clock overrun, and does not record "needs the network"
   as a disqualification, because egress is open by design and the spike's own
   `uv tool run` invocations depend on it.

---

### User Story 2 - A loop can name a quality step, and one that does not costs nothing (Priority: P1)

`verify:` grows a fourth step name, and the dispatch payload carries it.

**Why this priority**: nothing else can land without the step existing, and the
"costs nothing when absent" half is what keeps the factory portable into a
brownfield repo that wants none of this.

**Independent Test**: a v2 manifest declaring `verify: [gates, diff_check,
quality, judge]` resolves and the epic dispatch payload built from it carries
the scanner; one omitting `quality` resolves to a configuration byte-identical
to today's and imports no scanner module.

**Acceptance Scenarios**:

1. **Given** a v2 manifest with `quality` in `verify:`, **When** it is parsed,
   **Then** the step is accepted and appears in the resolved order.
2. **Given** a manifest placing `quality` before `gates`, and separately one
   placing it before `diff_check`, **When** each is parsed, **Then** each is
   refused, and a committed test asserts the refusal is the **ordering**
   refusal — its message names the step it must follow — rather than the
   unknown-step refusal `factory/verify/factory_yaml.py:915` — `_read_verify`
   already raises for any name outside `_VERIFY_STEPS`. Two assertions, because
   one refusal passing does not prove the other exists.
3. **Given** a manifest placing `judge` before `quality`, **When** it is parsed,
   **Then** it is refused with the ordering message and not the unknown-step
   one: the deterministic step is ordered before the metered one so the
   follow-on gating spec has a seam to use. In *this* spec a red scan skips
   nothing, because a scan changes no verdict.
4. **Given** a manifest whose `scanner:` names something outside the closed set
   — `ruff`, say, which is a tool name and belongs in `command:` — **When** it
   is parsed, **Then** it is refused with the admissible names listed, and the
   closed set the refusal reads is the one that lives beside the parser in
   `factory/verify/factory_yaml.py` — there is exactly one, it holds the
   *adapter* names `sarif` and `none` that FR-014 and FR-015 fix, and US3's
   conformance test holds the registry to it in both directions.
5. **Given** a manifest with no `quality` step, **When** the loop resolves,
   **Then** the resolved *order* is still exactly `(gates, diff_check, judge)`,
   the resolved configuration equals today's, and a committed test asserts the
   module path `factory.verify.scanner` is absent from `sys.modules` afterwards.
   The order half is neither a formality nor a fence: `_VERIFY_STEPS` is both the
   admissible set and the value
   `factory/verify/factory_yaml.py:924` — `_read_verify` returns for an absent
   `verify:` key, and this repository's own `ergane.yaml` declares none — so the
   obvious implementation of FR-005, growing that one tuple, fails this scenario
   and moves every such repository's `loop_digest` on its way past. The
   `sys.modules` half is named by path so it becomes load-bearing the moment US3
   creates that module.
6. **Given** two manifests differing only in their scanner name, **When** each
   resolves, **Then** their `loop_digest` values differ — a PASS is a claim
   relative to a named definition of verified, and the scanner is part of that
   name.
7. **Given** one manifest body declaring `quality:`, loaded twice — once under
   `version: 2` and once under `version: 1` — **When** each is loaded, **Then**
   the v2 load parses and the v1 load is refused as an unknown top-level key.
   Both halves in one committed test: the v1 half alone passes today, before any
   change, so only the pair can fail a diff that registered the key in the
   version-independent tuple.
8. **Given** an operator clone whose manifest names a scanner, **When** the epic
   is dispatched by the roadmap, **Then** a committed test drives the whole
   carrier chain — `load_loop_config`'s returned tuple, the
   `ReadLoopConfigResult` the activity builds from it, and the `EpicInput` the
   roadmap constructs at `factory/roadmap/workflow.py:1296` — `_dispatch` — and
   asserts the
   scanner arrives on the payload beside `verify_order`; a second assertion
   covers the CLI path, whose manifest read at
   `factory/cli/nouns/build.py:826` — `start_command` reaches its one
   `EpicInput` at `factory/cli/nouns/build.py:931` — `_start_epic`. Two
   constructions, not three: the third in the tree,
   `factory/workgraph/cli.py:675` — `_start_epic`, reads no manifest at all. A
   manifest key that
   stops at `FactoryConfig` is a key production never reads.
9. **Given** a `quality:` block naming `scanner: sarif` and carrying no
   `command:`, **When** it is parsed, **Then** it is refused by name — the
   `sarif` adapter has nothing to run without one, and FR-014's "declared
   command" has no other declarer anywhere in the schema — and the same test
   asserts the identical block *with* a `command:` parses, so the refusal is
   proven to be about the missing key rather than about the block.
10. **Given** this repository's own `ergane.yaml`, which names no `quality`
    step, **When** this story's diff is read, **Then** it carries the
    `loop_digest` value pasted from before the change beside the one pasted from
    after it, shown equal. This is the only committed proof that neither the
    step tuple nor the digest dict moved a repository that asked for nothing,
    and it is why no implementation of FR-009 may reach its second half by
    bumping `loop_digest`'s `schema_version` keyword: that moves every digest on
    the floor at once, and a digest is a recorded claim about what "verified"
    meant.

---

### User Story 3 - A scanner is an adapter resolved by name (Priority: P1)

The hook system itself. This is the story the operator asked for.

**Why this priority**: it is the difference between shipping a SonarQube
integration and shipping the ability to swap one out. The factory already has
this pattern twice — `factory/notify/adapter.py` and
`factory/mergequeue/forge.py` — and both are lazy-import registries held to a
config's closed set in both directions by a conformance suite.

**Independent Test**: a scanner registered under a name is returned by
`resolve_scanner(name)`; resolving a name outside the closed set raises with the
registered names listed; the module imports no scanner's dependencies at import
time.

**Acceptance Scenarios**:

1. **Given** the scanner registry, **When** the module is imported, **Then** no
   candidate scanner's package appears in `sys.modules` — resolution is lazy,
   exactly as the messenger registry is, so a factory with no scanner installed
   still starts.
2. **Given** the built-in `sarif` adapter and the `command:` the manifest's
   `quality:` block declares (FR-007), **When** it is invoked against a
   worktree, **Then** a committed test asserts the `GateInvocation` the adapter
   built carries `ERGANE_QUALITY_SARIF` on its `env`, holding the same absolute
   path the adapter then reads, *before* asserting that parsed findings come
   back — an adapter that computes a path, never tells the command, and reads a
   fixture that was already there passes the second assertion on its own, which
   is the failure this scenario exists to catch. Driven by a committed fixture
   SARIF file, with no real scanner installed, and with no knowledge in the
   adapter of which tool produced it.
3. **Given** the built-in `none` scanner, **When** it is invoked, **Then** it
   returns an empty report and executes no command, so "configured but disabled"
   is expressible without editing `verify:`.
4. **Given** a scanner that exits non-zero, one that exceeds its deadline, and
   one that writes malformed SARIF, **When** each is invoked, **Then** each
   returns a report recording `scanner_unavailable` with the reason and
   **nothing raises** — three separate assertions, because one passing does not
   prove the other two exist.
5. **Given** the closed set US2 landed in `factory/verify/factory_yaml.py` and
   the registry's keys, **When** the conformance test runs, **Then** they match
   in both directions, so a name the parser admits always resolves and a name it
   refuses never reaches the registry. The test adds the second direction; it
   does not add a second closed set.
6. **Given** a directory with **no `.git` entry at all**, which is the only
   shape for which `factory/verify/gates.py:1018` — `_resolve_target_git_dir`
   returns `None` — an ordinary `git init` repository returns its own `.git`
   directory, not `None` — so the boundary carries no metadata destination,
   **When** the `sarif` adapter is invoked, **Then** the report records
   `scanner_unavailable` naming the missing destination rather than an empty
   report, and a committed test drives it with exactly that fixture — a boundary
   that cannot carry the artifact back must never be indistinguishable from a
   clean scan.
7. **Given** a **linked** worktree built with `git worktree add` against a
   parent repository — the shape every node has, and the shape the fixture must
   take — **When** the `sarif` adapter is invoked against it, **Then** the SARIF
   path it directs the command to write is under the directory
   `factory/verify/gates.py:1018` — `_resolve_target_git_dir` resolves, which
   for that shape is the parent repository's `.git` and therefore outside the
   worktree entirely; that the path is unique to this worktree, asserted by
   building a **second** linked worktree against the same parent and showing the
   two destinations differ, because that one `.git` is shared by every node of
   the repository and this floor has run the node cap at two; and that
   `git status --porcelain` in the worktree is empty with its tracked file
   listing unchanged — anything the
   scanner leaves where a diff can see it is staged by `git add -A`, committed
   by salvage, judged, and counted against the diff refusal threshold, and
   anything it leaves under `/tmp` is gone before the factory can read it.

---

### User Story 4 - A report is scoped to the lines this attempt touched (Priority: P1)

**Why this priority**: scoping is the whole difference between a measurement of
this attempt and a measurement of the repository's history. It is also the half
of the old US4 that has no factory state in it at all, which is why it is its
own story.

**Independent Test**: given a unified diff and a SARIF document as fixtures, the
scoping function returns exactly the findings on lines the diff touched, and the
excluded ones are returned as excluded rather than dropped.

**Acceptance Scenarios**:

1. **Given** a scan reporting findings across the whole repository, **When** the
   report is scoped, **Then** only findings on lines this attempt's diff touched
   survive — a node does not inherit the debt of every node before it. A finding
   on a path the diff renamed survives under the new path only.
2. **Given** an attempt that adds a new file, **When** the report is scoped,
   **Then** every finding in that file survives, because all of it is new.
3. **Given** a SARIF result with no `physicalLocation`, and separately one whose
   path does not resolve inside the worktree, **When** the report is scoped,
   **Then** each is recorded and excluded from the scoped set, and neither is
   mapped to line 1 or to a nearest-matching file.
4. **Given** a SARIF `artifactLocation.uri` written as an absolute path, one
   written as a `file://` URI and one written worktree-relative, **When** each
   is normalised, **Then** all three resolve to the same worktree-relative path
   and a committed test asserts it for all three spellings — different tools
   choose differently and a mis-mapped finding poisons the very distribution
   this spec exists to measure.

---

### User Story 5 - The recorded scans are queryable, so thresholds can be measured (Priority: P2)

**Why this priority**: without it, the record-only phase produces a table nobody
reads and the follow-on spec sets its thresholds by guess — which is the exact
failure this sequencing was chosen to avoid. The diff limit was set as "a
comfort margin, not a measurement", and its first false positive refused a
fully-green story four times.

**Independent Test**: a command reports finding counts per attempt, per rule and
per story over a date range, against a store seeded with known rows.

**Acceptance Scenarios**:

1. **Given** a store seeded with recorded scans, **When** the operator asks for
   the distribution, **Then** they get counts per rule, ordered by frequency,
   over a selectable window.
2. **Given** the same store, **When** the operator asks per story, **Then** they
   get findings per attempt, so "did the second attempt improve" is answerable.
3. **Given** rows written before this spec, whose quality column is NULL,
   **When** the query runs, **Then** they are reported as unmeasured rather than
   as zero findings — a zero here would silently halve any average the follow-on
   spec sets a threshold from.
4. **Given** a window in which the scanner name changed, **When** the query
   runs, **Then** the change is named in the output, because counts either side
   of it are not comparable.

---

### User Story 6 - The scoped report is recorded, and changes nothing (Priority: P1)

**Why this priority**: this is where record-only becomes a fact about the code
rather than a promise in a spec. It is numbered last and runs fifth: it is the
half of the original US4 split out at refinement, and a split takes a new
number rather than renumbering its sibling.

**Independent Test**: two attempts identical but for their scan — one clean, one
with four hundred findings — produce byte-identical verification rows apart from
the quality column, and the same number of judge invocations.

**Acceptance Scenarios**:

1. **Given** two attempts with the same gate results, the same diff check and
   the same criteria, one whose scan reports four hundred findings and one whose
   scan is clean, **When** each is driven through
   `factory/workgraph/workflow.py:2559` — `_verify`, **Then** a committed test
   asserts the two recorded `VerificationResult` rows are equal field for field
   except the quality column, and that the judge was invoked the same number of
   times in both — comparing the `OverallVerdict` alone proves nothing, because
   that enum has two values and FR-019 already forbids `compose_result` from
   seeing the report. The same test also asserts by signature inspection that
   `factory/verify/models.py:998` — `compose_result` takes no quality
   parameter. That half passes against today's untouched tree, so it is a
   regression fence and not a proof, and it rides on this scenario rather than
   standing as one of its own: a scenario a test-only diff satisfies is a
   scenario the judge can pass while nothing was built.
2. **Given** a completed scan, **When** the verification row is written, **Then**
   it carries the scoped findings, the scanner name, and the scanner's own
   version string, so a later change in finding counts can be attributed to the
   code rather than to a scanner upgrade.
3. **Given** an attempt whose gates failed, **When** the row is written, **Then**
   the quality evidence is NULL and no scan was invoked — a different fact from
   a scan that ran and found nothing, mirroring how `judge_verdict` is NULL when
   the judge never ran.
4. **Given** a redelivered activity replaying into the same workflow run,
   **When** the row is upserted, **Then** a committed test reads the **quality
   column** back and asserts the redelivery replaced the first write's evidence
   rather than duplicating or losing it, matching on the five-column key that
   includes `dispatch`; a second dispatch of the same attempt carries its own
   quality evidence on its own row. The five-column key already holds for every
   other column, so only the quality column makes this assertion new.
5. **Given** a dispatched verify order that names `quality` on a green attempt,
   one that names `quality` on an attempt whose gates failed, and one that does
   not name it at all, **When** the verification phase runs, **Then** the scan is
   invoked exactly once in the first case, after the diff check, and not at all
   in the other two — a step name that executes nothing is a digest change
   wearing a feature's clothes, and a scan on already-failed work is spend with
   nothing to attribute it to.

## Functional Requirements

- **FR-001**: The spike MUST run each candidate scanner ephemerally through
  `uv tool run`, never through `uvx`, MUST NOT add any dependency to
  `pyproject.toml` or `uv.lock`, and MUST commit the pasted `git diff --stat`
  proving it. The spelling is a requirement rather than a preference: the
  boundary FR-002 makes the run happen inside binds `uv` as a single read-only
  file rather than its directory, and `uvx` is a separate binary beside it, so
  `uvx` does not exist in there and every candidate would be disqualified for a
  path no bind carries — the exact false measurement FR-002 exists to prevent,
  on the one story whose output decides whether the rest are buildable.
- **FR-002**: The spike MUST run each candidate through the gate boundary the
  manifest selects rather than a bare subprocess, and MUST record which backend
  class actually executed it; a candidate executed by the host fallback MUST be
  recorded as not having been measured against the boundary.
- **FR-003**: The spike MUST record, per candidate, the exact command, the exit
  code, the wall-clock, the SARIF flag that actually worked, whether well-formed
  SARIF was produced, and which destination the artifact survived on. It MUST
  NOT record "needs the network" as a disqualification.
- **FR-004**: The spike MUST commit at most two SARIF artifacts — the
  recommended candidate's and one contrasting candidate's — each reduced to
  `runs[].results` plus only the rules those results name and held under 8 KiB;
  every other surviving candidate MUST be recorded as counts alone. It MUST
  state each unreduced document's byte count and the story's whole diff size so
  a reader can see it stays under the diff refusal threshold. The bound is fixed
  at two here rather than left to the implementer at commit time, because the
  only bound available then is the refusal that spends the story unjudged.
- **FR-005**: `quality` MUST be an admissible `verify:` step name in schema v2,
  **and** the order a manifest declaring no `verify:` key resolves to MUST NOT
  change. Those are one requirement because one tuple answers both questions
  today: `factory/verify/factory_yaml.py:924` — `_read_verify` returns
  `_VERIFY_STEPS` verbatim for an absent key, and `ergane.yaml` here declares no
  `verify:`, so a repository that never asked for a scanner would otherwise be
  dispatched with one in its order and a moved digest under it.
- **FR-006**: `quality` MUST be refused when ordered before `gates` or before
  `diff_check`, and `judge` MUST be refused when ordered before `quality`; each
  refusal MUST be distinguishable from the unknown-step refusal.
- **FR-007**: A `quality:` configuration block MUST carry `scanner:`, a name
  held to a closed set, and `command:`, the command line that scanner runs. The
  closed set holds the **adapter** names FR-014 and FR-015 fix — `sarif` and
  `none` — never a tool name, matching the `KNOWN_ESC_ADAPTERS` precedent at
  `factory/controlplane/config.py:51`; a tool such as `ruff` or `semgrep` is what
  an operator writes in `command:`. A `scanner:` outside the closed set MUST be
  refused with the admissible names listed. `scanner: sarif` with no `command:`
  MUST be refused. The `command:` string MAY reference the destination
  environment variable FR-014 exports; nothing else in this schema names an
  output path, and no third key is added to carry one. `scanner: none` runs
  nothing, so a `command:` left beside it
  MUST be carried unread rather than refused, which keeps "configured but
  disabled" a one-word edit. That closed set MUST live in
  `factory/verify/factory_yaml.py`, beside the parser that enforces it, and
  there MUST be exactly one of it in the tree.
- **FR-008**: A manifest omitting `quality` MUST resolve to a configuration
  equal to today's, and MUST import no scanner module.
- **FR-009**: The resolved scanner MUST contribute to `loop_digest` and
  `loop_summary`, and a repository that names no scanner MUST keep the digest it
  has today.
- **FR-010**: The resolved `quality:` block MUST ride on the epic dispatch
  payload beside `verify_order`, carried from the operator clone through every
  link of the existing chain — the loop-config read, the roadmap activity's
  result, and the two `EpicInput` constructions that read a manifest
  (`factory/roadmap/workflow.py:1296` — `_dispatch` and
  `factory/cli/nouns/build.py:931` — `_start_epic`) —
  and MUST NOT be re-read from the node worktree. The tree's third construction,
  `factory/workgraph/cli.py:675` — `_start_epic`, reads no manifest and passes neither
  `verify_order` nor `diff_refusal_bytes`; it MUST stay on `EpicInput`'s
  defaults for that same reason and is out of scope.
- **FR-011**: `quality:` MUST be registered as a schema-v2-only top-level key,
  so a v1 manifest declaring it is refused as an unknown key.
- **FR-012**: Scanners MUST be resolved by name from a registry, with the
  scanner's own dependencies imported lazily at resolve time.
- **FR-013**: The registry's keys and the closed set FR-007 places in
  `factory/verify/factory_yaml.py` MUST be held equal in both directions by a
  conformance test, which adds no second closed set of its own.
- **FR-014**: A built-in `sarif` adapter MUST run the `command:` the manifest's
  `quality:` block declares (FR-007) against the worktree and parse the SARIF
  the command was directed to write, without knowledge of the producing tool.
  "Directed" MUST be one named environment variable, `ERGANE_QUALITY_SARIF`,
  which the adapter sets to the absolute destination FR-026 fixes on the `env`
  of the invocation it builds (`factory/verify/gates.py:269` —
  `GateInvocation`) and which the operator's `command:` references. The boundary
  runs that command with that environment and passes no `--clearenv`
  (`factory/verify/gates.py:614` — `run`), so the variable survives into the
  namespace. An adapter that computes a path and never tells the command about
  it satisfies every other word of this requirement and produces nothing.
- **FR-015**: A built-in `none` scanner MUST return an empty report and execute
  no command.
- **FR-016**: A scanner that fails, exceeds its deadline, emits unparseable
  output, or runs inside a boundary that carries no writable destination for its
  artifact MUST produce a `scanner_unavailable` report carrying the reason, and
  MUST NOT raise. The deadline MUST be the one a gate with no `timeouts:` entry
  already gets — `factory/verify/models.py:1201` — `VerificationConfig`, whose
  `gate_timeout_s` rides on the same dispatched config — and MUST NOT be
  declared by a new manifest key: `timeouts:` maps *gate* names to seconds and
  refuses a name the manifest does not declare as a gate, so a scanner deadline
  key would widen the two-key block FR-007 fixes and US2 has already landed.
- **FR-017**: Findings MUST be scoped to lines the attempt's diff touched; all
  findings in a file the attempt created are in scope; a renamed path is in
  scope under its new name only.
- **FR-018**: A finding with no location, or whose path does not resolve inside
  the worktree, MUST be recorded and excluded from the scoped set, and MUST NOT
  be mapped to a line or a file it did not name; absolute, `file://` and
  relative URI spellings MUST normalise to the same worktree-relative path.
- **FR-019**: The composed verdict MUST NOT depend on the quality report, and
  `compose_result` MUST NOT receive it as a parameter.
- **FR-020**: The verification row MUST carry the scoped findings, the scanner
  name, and the scanner's version string, taken at scan time from the SARIF
  document's own `runs[].tool.driver.version` rather than from a second
  invocation of the tool, and recorded as absent when the document carries none.
  No manifest key declares it.
- **FR-021**: Quality evidence MUST be NULL when the scan did not run,
  distinguishably from a recorded empty report.
- **FR-022**: Quality evidence MUST upsert on the existing five-column
  verification key, `dispatch` included, and the new column MUST be appended
  last in both the fresh-store DDL and the positional column tuple.
- **FR-023**: An operator command MUST report finding distribution per rule, per
  story, and over a selectable window.
- **FR-024**: Rows whose quality column is NULL MUST report as unmeasured, never
  as zero.
- **FR-025**: A scanner-name change within a queried window MUST be named in the
  output.
- **FR-026**: The `sarif` adapter MUST direct its command's SARIF output to a
  path **unique to the worktree being scanned**, under the git metadata
  directory `factory/verify/gates.py:1018` — `_resolve_target_git_dir` resolves
  for that worktree, which the executing boundary carries writable at the same
  absolute path inside and out and the host can read after the command returns;
  it MUST leave nothing the worktree's own `git status --porcelain` reports, and
  MUST NOT choose a path under `/tmp` or `TMPDIR`. Uniqueness is a requirement
  rather than an implementer's good instinct: that function's linked-worktree
  branch resolves to ONE directory shared by every node of the parent
  repository, so a fixed filename there is two concurrent nodes overwriting each
  other. The node's own metadata subdirectory — the `worktrees/<name>` path that
  worktree's `.git` file already points at — is per-node by construction. The
  invariant it relies on is *git metadata*, not "outside the
  worktree": on a linked worktree — what every node is — that directory is the
  parent repository's `.git` and is outside, while on an ordinary repository it
  is `<worktree>/.git` and is inside; `git add -A` stages neither.
- **FR-027**: The scan MUST be invoked from the verification phase exactly when
  the dispatched verify order names `quality` **and** the gates and the diff
  check have both passed, after the diff check; it MUST NOT be invoked
  otherwise.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004]
US2:
  depends_on: []
  concurrent_with: [US1]
  implements: [FR-005, FR-006, FR-007, FR-008, FR-009, FR-010, FR-011]
US3:
  depends_on: []
  depends_on_merged: [US2]
  concurrent_with: [US1]
  implements: [FR-012, FR-013, FR-014, FR-015, FR-016, FR-026]
US4:
  depends_on: []
  depends_on_merged: [US3]
  concurrent_with: [US1]
  implements: [FR-017, FR-018]
US6:
  depends_on: []
  depends_on_merged: [US4, US2]
  concurrent_with: [US1]
  implements: [FR-019, FR-020, FR-021, FR-022, FR-027]
US5:
  depends_on: []
  depends_on_merged: [US6]
  concurrent_with: [US1]
  implements: [FR-023, FR-024, FR-025]
```

US1 is genuinely independent: it adds no production code and its output is a
research note. Every other story therefore declares `concurrent_with: [US1]`:
US1's tasks *cite* `ergane.yaml`, `factory/verify/factory_yaml.py`,
`factory/verify/gates.py` and `factory/verify/diffbounds.py`, and the later
stories *edit* some of those, but a citation is not a write — US1's whole diff
lands under this spec's own `research/` directory, so none of them contend with
it. US1 is not a *precondition* of US3 either: US3's destination for the SARIF
artifact is derived in plan.md from the mount set in the tree, and US1-S6 is the
pasted confirmation of that derivation rather than the source of it. If US1 lands
first and contradicts it, the plan is wrong and US3 is re-planned; the graph does
not encode a wait that would serialise a research note ahead of production code.

Everything else is a **content** chain, and every edge in it is therefore a
merge-edge rather than a pass-edge. `depends_on` is ordering only — CONTEXT.md
defines it as carrying no guarantee that the predecessor's code is present, and
`docs/architecture.md` repeats it — while each of these dependents needs its
predecessor's code inside its own base pin: US3's conformance test **imports**
the closed-set constant US2 lands rather than restating it, US4 scopes the
report US3's adapter returns, US6 reads US4's scoper and invokes it through the
field US2 put on the dispatch payload, and US5 reads the store column US6 adds.
A dependent dispatched onto a base without those cannot write its story at all,
so each declares an empty `depends_on` and a `depends_on_merged` — the form
092, 101, 117 and 126 all use for exactly this shape.

US6 is numbered after US5 and runs before it. It is the second half of the story
that was numbered US4 before this refinement, split because that story carried
seven requirements across five production files with two pasted-evidence blocks
— the shape this repository's most expensive story had. The two halves share no
production file: US4 is one new module and its tests, US6 is the store, the
workflow call site and the activity plumbing. A split takes a new number, so US5
keeps the number it had and US6 takes the next one.

US6 names **both** `US4` and `US2` in `depends_on_merged`, and the second name
does a second job beside its content one: US2 and US6 both edit
`factory/workgraph/workflow.py`, so a race would see whichever landed second
rejected for the other's change. `ergane spec validate` infers that contention;
declaring it makes the wait a decision instead of an accident. US4 names only
`US3`, because after the split it touches no file US2 touches.

The chain is the reason this spec is six stories rather than three. Collapsing
US2 into US3 was considered and rejected: a parser change and a registry are
different enough that a single agent doing both is the shape that produced this
repository's most expensive story.
