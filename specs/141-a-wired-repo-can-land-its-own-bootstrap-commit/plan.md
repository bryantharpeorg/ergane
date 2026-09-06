# Implementation Plan: a wired repo can land its own bootstrap commit

Every `file:line` below was read from `ergane-buildout` at `602a92c` on
2026-09-04 and verified to resolve to the symbol named. Do not trust an anchor
that has moved; re-read before editing.

## What already exists, and where

**The branch is read in one place, and the manifest is already in hand twenty-two
lines above it.** `factory/activities/merge_activities.py:639` —
`onboard_target_repo` loads the manifest at
`factory/activities/merge_activities.py:676` — `onboard_target_repo`, derives
`declared_gates` and `gate_commands` from it, and then asks for the policy of a
branch that came from somewhere else entirely:

```python
    try:
        policy = forge.landing_policy(repository.default_branch)
    except ForgeError as error:
        # A repo the factory cannot read is not dispatchable.
        return _profile_from_forge_failure(
```

`repository.default_branch` is `gh repo view`'s `defaultBranchRef.name`, read at
`factory/mergequeue/github_forge.py:85` — `describe_repository`. The declared
value it should have used is `config.landing_branch`
(`factory/verify/models.py:319` — `FactoryConfig`), parsed at
`factory/verify/factory_yaml.py:514` — `_read_landing_branch`, whose docstring
states the rule this story is applying: "D-009's 'declared, never auto-detected'
rule applied to the one branch fact the factory otherwise guesses at."

**Nothing downstream needs teaching.** `factory/mergequeue/github_forge.py:137` —
`landing_policy` sets `branch=branch` on the record it returns, and
`factory/mergequeue/onboard.py:246` — `_gated_landing_finding` interpolates
`policy.branch` into its own text. Change the argument and every finding's
sentence becomes true; edit no finding at all. FR-003.

**The lander already does it this way, and named the derivation.**
`factory/workgraph/worktree.py:1442` — `resolve_landing_base` reads the manifest
first and falls back to the clone's checked-out branch, and its docstring calls
itself "the one derivation … so no caller can end up with a branch whose
provenance a second reader would disagree about". Onboarding is the caller that
disagrees. D-051 and Principle IX (`docs/decisions.md:1255-1267`) decided this in
August and the promotion did not sweep this site.

**Three sentences in the tree state the behaviour US1 removes.** The module
docstring at `factory/mergequeue/wiring.py:41-47`; the operator-facing remedy at
`factory/mergequeue/wiring.py:559` — `_divergence_step`:

```python
        f"the queue was wired on the declared landing branch '{landing_branch}', but "
        f"{owner_repo}'s default branch is '{default_branch}'. Onboarding reads the "
        f"queue for the default branch, so every epic start will keep failing until "
        f"the two agree. Either:\n"
        f"  gh repo edit --default-branch {landing_branch}\n"
        f"or set landing_branch to '{default_branch}' in ergane.yaml.",
```

and `docs/architecture.md:668-673`, which describes the merge-queue rule being
read "on the default branch". All three go in US1's diff. `_divergence_step`
keeps existing and keeps reporting — its own docstring says silence is the trap —
but it reports a fact, not a failure, and it stops offering the two remedies that
throw the declaration away.

**The workflow renderer is twenty-four lines and emits three steps per gate.**
`factory/mergequeue/wiring.py:143` — `render_gates_workflow` builds each job, with
the bare checkout at `factory/mergequeue/wiring.py:162` —
`render_gates_workflow`, and prepends the module constant `_WORKFLOW_HEADER`
(`factory/mergequeue/wiring.py:124-140`), whose only word about toolchains is the
`TODO(operator)` at `factory/mergequeue/wiring.py:131-132`. The header is one
string shared by every job; the derived setup is per gate and belongs in the job
blocks, not in the header.

**The roster shape to copy already exists, with its argument written out.**
`factory/verify/gate_annotation.py:86-95` is `INSTALL_SIGNATURES`, a tuple of
`InstallSignature(tool, pattern)` with each tool's exact phrase as a
word-boundary regex, and the module docstring at
`factory/verify/gate_annotation.py:28-33` argues why a loose match over "install"
or "not found" is the wrong trade — in this repository's own measured words.
Copy the shape and the argument.

**The ruleset body is data, and deliberately so.**
`factory/mergequeue/wiring.py:566` — `_ruleset_payload` loads
`factory/mergequeue/merge_queue_ruleset.json`, sets the branch condition and the
required contexts, and returns it. The data file arms the rule at
`factory/mergequeue/merge_queue_ruleset.json:4` and declares no bypass at all;
`grep -rn 'bypass_actor' factory/` returns nothing. The reason the arming field
lives in JSON rather than Python is stated at
`factory/mergequeue/wiring.py:57-61` and repeated at
`factory/mergequeue/github_forge.py:244-246`: this package's own vocabulary sweep
reserves that word (trap 5).

**The bypass entry US3 adds is not a design choice; it is a transcription.** It
was read from this repository's own live ruleset on 2026-09-04 with
`gh api repos/bryantharpeorg/ergane/rulesets/20538625`, and this is the array
that came back, verbatim:

```json
"bypass_actors": [
  {"actor_id": null, "actor_type": "OrganizationAdmin", "bypass_mode": "always"}
]
```

That is the configuration that admits the operator's daily direct pushes to
`ergane-buildout`, and the exact field `--wire` omits. The operator's own
landing-mechanism probe reached the same array from the other side on 2026-09-04:
a probe ruleset carrying required checks and **no** bypass entry refused a direct
push outright with `409 — Required status check "probe-check" is expected`, and
the note it produced says any recreate payload must carry `bypass_actors` forward
"or every operator push starts bouncing". Three fields, three literal values, one
entry. FR-011 requires that array field-for-field. Trap 13 is why it may not be
paraphrased, widened or trimmed, and trap 14 is what it costs.

**Idempotence is read-then-decide, and the comparison is where a new field
breaks it.** `factory/mergequeue/wiring.py:589` — `_ruleset_satisfies` compares
every top-level field but `rules` with a bare inequality:

```python
    for key, value in desired.items():
        if key == "rules":
            continue
        if current.get(key) != value:
            return False
```

A `bypass_actors` list that a forge echoes back re-ordered, or with per-entry
keys filled in that the request did not send, fails that comparison and turns
every re-run into a write. This is measured, not hypothetical: the read-back
quoted above carries `"actor_id": null` inside its entry, so a template that
declared `{"actor_type": ..., "bypass_mode": ...}` alone would compare unequal
against what GitHub returns on every single run. FR-011 closes that particular
gap by declaring the entry with all three fields; FR-013 closes the general one,
because ordering and future forge-filled keys remain. FR-013, trap 7.

**Everything needed to drive all four stories offline is already in one test
module.** `tests/test_ergane_init_wiring.py:115` — `FakeGitHub` is a mutable
model of one repository driven through the `gh` argv surface;
`tests/test_ergane_init_wiring.py:352` — `wired` runs a whole `ergane init
--wire` against it with a scripted interview;
`tests/test_ergane_init_wiring.py:368` — `onboarding_profile` runs
`onboard_target_repo` over the same model, and its docstring is the licence for
using it here — "`EpicWorkflow._onboard_target`'s judgment verbatim, run against
the wired model. Nothing here knows what the wiring intended to do";
`tests/test_ergane_init_wiring.py:376` — `wiring_report` cuts the `--wire` report
out of stdout so an assertion cannot pass on the readiness check's words. Do not
write a second model.

## Traps

**Trap 1 — The branch fix is one argument, and the temptation is to make it
five.** FR-003. `factory/mergequeue/onboard.py:162` — `evaluate_repo` has no
branch parameter and must not gain one: the branch already travels on
`LandingPolicy.branch` (`factory/mergequeue/github_forge.py:137` —
`landing_policy`) and `factory/mergequeue/onboard.py:246` —
`_gated_landing_finding` already interpolates it. An implementer who adds
`landing_branch=` to `evaluate_repo` and threads it into
`factory/mergequeue/onboard.py:364` — `_gate_check_finding` so the text can name
the branch will touch three call sites, rewrite a finding, and collide head-on
with trap 3. The whole production change for FR-001 is which value is passed at
`factory/activities/merge_activities.py:698` — `onboard_target_repo`.

**Trap 2 — The manifest's default is not "no answer", and the fallback must key
on the load failing rather than on the value.**
`factory/verify/factory_yaml.py:514` — `_read_landing_branch` returns `"main"`
when the key is absent, so `FactoryConfig` cannot tell "declared `main`" from
"silent" — and must not, because the spec's fourth table row says silent *means*
`main`. The wrong move, and it looks conservative, is a fallback shaped like
`config.landing_branch if config.landing_branch != "main" else
repository.default_branch`: it reinstates the whole defect for every repository
that declared `main` deliberately, and every test in US1 still passes because
none of them declares `main`. The only fallback FR-002 allows is the
`except FactoryConfigError` arm at
`factory/activities/merge_activities.py:683` — `onboard_target_repo`, where
`config` was never bound at all.

**Trap 3 — Spec 128 owns `factory/mergequeue/onboard.py`; do not open it — and
the file you *will* collide with is a different one.** 128 is `a boundary-only
gate is a declaration, not a refusal`, drafted on this floor against the same
module, and its US2 edits `factory/mergequeue/onboard.py:390` —
`_gate_check_finding` and `factory/mergequeue/onboard.py:162` — `evaluate_repo`'s
signature. This spec needs neither. FR-003 states that as a requirement rather
than as advice because the cost is not tidiness: two drafts editing the same
function produce two diffs that cannot both land, and the second one to arrive
loses a ladder rung to a conflict it did not cause.

Fencing `onboard.py` is only half the trap, and the half that is free. The
collision that will actually happen is in the seam file this spec *does* open:
128's own tasks place its derivation at
`factory/activities/merge_activities.py:677` — `onboard_target_repo`, "beside
where `declared_gates` and `gate_commands` already come off the same config", and
its argument at `factory/activities/merge_activities.py:708` —
`onboard_target_repo`. T006 binds the declared landing branch into those same
three lines and changes the argument at
`factory/activities/merge_activities.py:698` — `onboard_target_repo`, ten lines
above 128's. The `try` block at
`factory/activities/merge_activities.py:676-681` — `onboard_target_repo` is one
contiguous region both drafts insert into: they cannot both apply cleanly, and
the loser is whichever arrives second. The rule, stated in spec.md's **Depends
on** line so an operator meets it before dispatch: **US1 of this spec lands
first** — it is one binding and one argument, and it is the half that unparks a
repository already past bootstrap — and 128-US2 rebases onto it. If you are
reading this in a worktree where 128-US2 has already landed, expect an
unfamiliar `boundary_only_gates` binding beside yours in that block; add to it,
do not revert it, and do not move it.

**Trap 4 — One live test asserts today's defect as intended behaviour, and it must
be inverted rather than deleted.** `tests/test_ergane_init_wiring.py:609` —
`test_a_landing_branch_that_is_not_the_default_is_wired_and_the_divergence_reported`
wires `release` over a default of `main`, then asserts at
`tests/test_ergane_init_wiring.py:640-642` that the profile fails with
`gated_landing`, under the comment "And the warning is true: the factory's gate
reads `main` and still fails." Its docstring says the same in prose. It is also
the only fixture in the tree that wires a non-default landing branch, so deleting
it removes the coverage US1 exists to add. Change the assertions and the two
comments; keep the fixture. Its assertion at
`tests/test_ergane_init_wiring.py:637` on `gh repo edit --default-branch` is the
one FR-004 removes.

**Trap 5 — The entry offered two arms and one of them is refused by a test in a
module this spec never names.** The scope sentence reads "created non-blocking
(or with the wiring identity as a bypass actor)". The non-blocking arm requires
Python under `factory/` to spell the arming field's name, and
`tests/test_final_sweep.py:614` — `test_the_component_cannot_even_spell_a_cap`
parses every `factory/**/*.py` and refuses that word. It is not only an
identifier check: `tests/test_final_sweep.py:601` — `code_words` collects
function and class names, `ast.Name` ids, attribute names, argument names,
keyword-argument names, import aliases **and every non-docstring string
constant**, so `payload["enforcement"] = "disabled"` and
`_ARMING_KEY = "enforcement"` both fail, in `factory/mergequeue/wiring.py`, over
a test file nothing in this trio would otherwise open. Comments never reach the
AST and JSON is not Python — which is exactly why the field is spelled only in
`factory/mergequeue/merge_queue_ruleset.json` today, as
`factory/mergequeue/wiring.py:57-61` explains. FR-011 puts the bypass in the same
data file for the same reason, and FR-012 makes the constraint a requirement so
it is met on purpose rather than discovered by a red suite.

**Trap 6 — "activated only once a check has been observed" needs a question the
seam refuses to grow, and the cheap local substitute reproduces the deadlock.**
`factory/mergequeue/forge.py:291` — `apply_landing_policy` says in its own
docstring that the three properties are fixed rather than arguments and that
"only *which* branch and *which* checks vary, which is why they are the only
parameters"; `factory/mergequeue/forge.py:178` — `Forge` says eleven operations
"and no twelfth", held structurally by `tests/test_forge_seam.py:115` —
`test_the_forge_protocol_declares_exactly_the_seam_operations`. So an
implementer who adds a `has_check(branch, name)` operation to answer "observed"
fails that test. The local substitute is worse than a red test:
`factory/mergequeue/wiring.py:169` — `existing_gate_jobs` reads
`.github/workflows/*.yml` off the operator's disk, and
`factory/mergequeue/wiring.py:237` — `scaffold_gates_workflow` has just written
that file to disk (the directory is created one line above at
`factory/mergequeue/wiring.py:236`), so on a second `--wire` run disk says "the
checks exist" while the forge has never seen the commit. Arming on that answer is the reported deadlock
with one extra step in front of it. This spec therefore takes the bypass arm and
says so in spec.md; do not build the phase.

**Trap 7 — The offline model echoes the request back, so an idempotence test over
it cannot see the churn a real forge causes.**
`tests/test_ergane_init_wiring.py:272` — `_create_ruleset` stores the posted body
verbatim and adds only an `id`, and the update branch at
`tests/test_ergane_init_wiring.py:248-251` does the same on a re-wire's PUT, so
`factory/mergequeue/wiring.py:592` — `_ruleset_satisfies`
compares a dict against itself no matter how naive the comparison is, and a
bypass list compared with `!=` passes green through the fake and issues an
`update_ruleset` on every real run. FR-013's test must hand the comparison a
stored payload directly, shaped the way a forge returns one — entries re-ordered
and each carrying the per-entry keys the forge fills in. `actor_id` is the
measured example of such a key and it is **not** an example of a key to leave
out of the request: the read-back quoted in § "What already exists, and where"
carries it, FR-011 requires the template to declare it, and the general case
FR-013 must survive is a key the forge adds *later* to a shape this factory
already declares in full. The regression this trap protects is
`tests/test_ergane_init_wiring.py:489` —
`test_rewiring_reports_already_satisfied_and_changes_nothing`, whose assertions
at `tests/test_ergane_init_wiring.py:512-513` compare the model's whole state
across a re-run and require that no mutating call was issued at all.

**Trap 8 — Re-rendering the workflow changes what a re-run reports for every
already-wired repository, and that is the correct outcome.**
`factory/mergequeue/wiring.py:210-223` — `scaffold_gates_workflow` compares the
desired text to the committed one byte-for-byte and takes the "exists and
differs; it was NOT overwritten" branch when they disagree. After US2, every
repository carrying a file rendered by an earlier version gets that branch
instead of "already satisfied". The wrong move is to make the renderer overwrite
it, or to widen the comparison until an old file counts as matching: the
docstring at `factory/mergequeue/wiring.py:203-204` states the rule — "Written,
never committed: the repo's history belongs to its operator." US2-S5 pins the
attention branch as the intended outcome by committing the *old* text as a
fixture, which is also what stops a do-nothing diff passing that scenario.

**Trap 9 — Derive from the command a gate runs, never from the gate's name, and
mind which schema version fixes the names.** Gate names are the operator's *in
schema v2*, where the reserved-name set at `factory/verify/factory_yaml.py:168`
holds only four words; at schema v1 —
`factory/verify/factory_yaml.py:357-366`, the version
`tests/test_ergane_init_wiring.py:342` — `answers` scripts and the one
`factory/mergequeue/wiring.py:154-155` names in its own comment — every gate name
outside `KNOWN_GATES` (`factory/verify/factory_yaml.py:92`) is refused by the
loader before the renderer is ever reached. Those two constants are cited in bare
`path:NN` form on purpose, not by oversight: both are module-level assignments,
and `factory/cli/nouns/spec.py:825` — `_symbol_spans` collects spans only from
`FunctionDef`, `AsyncFunctionDef` and `ClassDef`, so the dash-symbol form over a
constant is a guaranteed "is not defined in that file" refusal. Do not "fix" them
into it. The operative instruction holds under
both: a gate called `test` may run `make check`, and at v2 a gate called `smoke`
may run `uv run pytest`, so the roster keys on the command. The practical
consequence for the tests is that any US2 case driven through the `wired` fixture
must use a v1-legal gate name, while a case that calls
`factory/mergequeue/wiring.py:143` — `render_gates_workflow` directly takes a
plain mapping and is unconstrained. Choosing a `smoke:` or `check:` gate for a
fixture-driven case costs an iteration to a refusal that never reaches the code
under test. And the
match must be a word-boundary phrase, not a substring: `pytest -k "uv run"` names
no toolchain, and the argument against widening is already written in this
repository's own words at `factory/verify/gate_annotation.py:28-33` — "a loose
match annotates every failing gate with a `HOME` lecture, and a retry prompt full
of confident irrelevant advice is the failure US1 exists to avoid, arriving
through a second door."

**Trap 10 — The job id is the check name and the check name is the contract, so
setup goes inside each job.** `factory/mergequeue/wiring.py:127-129` states it in
the file the operator reads — "rename a job here and the factory refuses to
dispatch against this repo" — and `factory/mergequeue/wiring.py:154-156` repeats
it beside the code. The tidy-looking design, one shared `setup` job the gate jobs
depend on, creates a check named `setup` that no gate declares, and
`factory/mergequeue/onboard.py:402` — `_unknown_check_finding` then fails the
repository the wiring just wired. `tests/test_ergane_init_wiring.py:460` —
`test_the_generated_jobs_produce_no_unknown_check_finding` is the test that
catches it; keep it green. Setup steps go between the checkout step and the run
step of the gate's own job.

**Trap 11 — The printed step list is hand-numbered strings.**
`factory/mergequeue/wiring.py:113-121` — `manual_steps` returns f-strings whose
numbers are typed into the text. Reordering the entries without retyping the
numbers yields a list reading `1, 2, 4, 5, 3`, and nothing in the suite catches
it today. The two tests that touch the list cover one command each and neither
reads a number: `tests/test_ergane_init_wiring.py:763` —
`test_manual_steps_renders_the_auto_merge_command` asserts only that some entry
carries `allow_auto_merge=true`, once with a resolved slug and once with the
placeholder, and `tests/test_wiring_us2.py:129` —
`test_refusal_carries_complete_manual_steps` holds the tree's only assertion on
`squash_merge_commit_title=PR_TITLE`. So FR-018 needs **both** green and
unmodified — :763 alone is not the control for both strings, and an implementer
who reads it as one will reword the squash command with nothing to stop them.
FR-015 requires positions and numbers to agree, which is why US4-S1 asserts over
the returned list rather than over prose.

**Trap 12 — Two of the four keys are the same defect, and a later audit will read
that as padding.** `mergequeue/wiring-creates-the-ruleset-before-the-workflow-the-ruleset-requires`
and `init/wire-creates-a-bootstrap-deadlock-against-the-commit-it-tells-you-to-make`
are two open rows for one mechanism, filed by two independent runs, and both are
declared. The floor's dated lesson is the opposite failure — a spec declaring
more keys than its FRs justify, closing a defect that is still running — so the
justification is written out here: US3 (FR-011 to FR-014) and US4 (FR-015 to
FR-018) together fix that one mechanism whole, the push and the instructions that
lead to it, and eight requirements are enough for two rows describing one thing.
Do not drop either key to make the list look proportionate.

**Trap 13 — The bypass entry is transcribed from a read-back, and no gate in this
repository can tell you if you invented it instead.** FR-011. The array is quoted
verbatim in § "What already exists, and where": one entry, `actor_id` null,
`actor_type` `OrganizationAdmin`, `bypass_mode` `always`. Every field is
load-bearing and the temptation is to drop the two that look redundant. Reproduce
the failure before deciding: `tests/test_ergane_init_wiring.py:272` —
`_create_ruleset` stores whatever JSON the POST carried and hands it straight
back (and the PUT branch at `tests/test_ergane_init_wiring.py:248-251` does the
same on a re-wire), so
`{"actor_type": "OrganizationAdmin", "bypass_mode": "always"}` with no `actor_id`
passes US3-S1, US3-S3, US3-S4 and US3-S5 green, and so would
`{"actor_type": "RepositoryAdmin"}`, a value GitHub does not define. The fake
cannot refuse a payload; it can only echo one. The first thing that can refuse it
is the live POST at the operator's verification step 2, which happens **after**
the story has landed, and its symptom is `--wire` refusing on every repository —
a regression strictly worse than the deadlock this story exists to remove. So:
copy the three fields, do not paraphrase them, do not substitute an actor type
this plan does not quote, and if the live POST is refused, the fix is a second
read-back and a follow-up story, never a guess edited into the JSON.

**Trap 14 — `always` is the mode that works and the mode that already cost this
floor a red trunk; ship it knowing which.** FR-011 and FR-016. The ledger row
`verify/an-operator-push-to-the-landing-branch-bypasses-the-required-check-and-can-red-the-trunk-every-node-builds-on`
is open and critical, and it is this exact configuration: with an
`OrganizationAdmin: always` bypass on `ergane-buildout`, the operator commit
`c9dea78` was pushed straight past the `test` required check carrying four
failing tests, both 075 nodes independently detected and repaired someone else's
red trunk inside their own stories, and one Opus attempt was plausibly lost to
it. That row's remedy (a) is "make operator changes to the landing branch go
through the same PR + merge queue path every node uses" — the opposite of what
FR-011 writes into every wired repository. The narrower `pull_request` mode was
considered and refused for one reason: it is not what this trio's own printed
steps instruct. US4 tells the operator to *push* the bootstrap commit
(FR-015, FR-017), and a mode that only bypasses on a proposal merge would make
those instructions false again — the precise defect this spec is named after.
Taking the narrower mode is therefore a different spec, one that rewrites US4's
instructions into "open a proposal and merge it", and it must be measured against
a live forge before it is written, because no gate here can falsify a mode value
either (trap 13). What this story owes instead is honesty: the relaxation is
stated in spec.md § "What this spec is not", the row is deliberately absent from
`fixes:`, and FR-016 makes the report name the actor class and the mode so no
operator learns about the bypass from a surprise. Do **not** quietly add that key
to `fixes:` because the story touched the same field.

## Sizing

US1 touches `factory/activities/merge_activities.py` (the branch derivation and
the argument), `factory/mergequeue/wiring.py` (the `_divergence_step` text and
the module docstring) and `docs/architecture.md` (one sentence). Its tests are
edits to `tests/test_ergane_init_wiring.py` plus one new case for the unreadable
manifest. It does **not** touch `factory/mergequeue/onboard.py` (trap 3) and does
not touch `factory/roadmap/workflow.py` or `factory/workgraph/workflow.py`: both
refusal sites clear through the verdict.

US2 touches `factory/mergequeue/wiring.py` only — the roster, the per-job
derivation inside `render_gates_workflow`, and the header constant — with tests
in `tests/test_ergane_init_wiring.py`.

US3 touches `factory/mergequeue/merge_queue_ruleset.json` (the bypass
declaration) and `factory/mergequeue/wiring.py` (`_ruleset_satisfies`, and a
comment where `_ruleset_payload` builds the body), with tests in
`tests/test_ergane_init_wiring.py`.

US4 touches `factory/mergequeue/wiring.py` only — `manual_steps`, the two
`WiringStep` details in `_queue_step`, and the applied detail in
`scaffold_gates_workflow` — with tests in `tests/test_ergane_init_wiring.py`.

**No two stories are file-disjoint**, which is why every pair carries a declared
merge edge rather than a waiver: all four edit `factory/mergequeue/wiring.py` and
all four add cases to `tests/test_ergane_init_wiring.py`. The regions differ —
US1 is the docstring and lines around 557, US2 is 124-166, US3 is 566-611, US4 is
104-121 and 505-541 — so the collisions are merge-order collisions rather than
design overlap, and landing them in the declared order is the whole remedy.

Every story is well inside the 64 KiB deterministic diff bound (D-050). The
largest is US2 at roughly a hundred production lines plus one test block; the
pasted evidence each verification task asks for is one rendered file and one
short report, not a transcript. Nothing here commits a lockfile.

## Verification the operator will run, independent of the gate

Per Constitution VIII and D-037 the judge sees the diff and the criteria only, so
runtime evidence is committed as pasted output.

**One of these is a pre-dispatch check, and doing it after landing is the whole
risk.** FR-011 pins the posted array to a *read* of this repository's live
ruleset. Nothing in this trio proves the *write* path: whether a rulesets POST
accepts `"actor_id": null` for `OrganizationAdmin`, or demands an integer. If it
demands an integer, US3 lands green and `--wire` then refuses on every
repository — strictly worse than the deadlock it removes (trap 13). So before
this spec is flipped, POST that exact array to a throwaway ruleset on a scratch
organization repository —
`gh api -X POST repos/<owner>/<scratch>/rulesets --input <body>.json` — and read
it back. Paste the accepted body into § "What already exists, and where" beside
the read-back. If GitHub refuses it, FR-011 and US3-S1 change on the operator's
desk rather than after a story has landed.

Beyond that, on a scratch repository the operator owns in an organization:

1. Run `ergane init --wire` against a fresh public repository whose declared
   `landing_branch` is not its GitHub default. Read the printed step list and
   confirm the commit-and-push step precedes the ruleset step.
2. Read the created ruleset with `gh api repos/<owner>/<repo>/rulesets/<id>` and
   confirm its `bypass_actors` array is field-for-field the array quoted in
   § "What already exists, and where" — that the POST was accepted at all, and
   that GitHub stored what was sent rather than dropping it. **This is the only
   falsifier of FR-011 anywhere in the process** (trap 13): the offline model
   echoes any JSON, so a wrong payload lands green. Then push the bootstrap
   commit directly, as an organization administrator. It must be accepted. That
   single push is the whole of N9 and C-16, run forwards; on the two reported
   targets it was refused four times. Run the same push once more from an account
   holding repository-admin rights only: it must be refused, and that refusal is
   the narrowing spec.md § "What this spec is not" declares rather than a
   surprise.
3. Open the scaffolded `.github/workflows/ergane-gates.yml` and confirm each job
   installs what its own gate command needs, and that the gate whose command
   matched nothing says so by name.
4. Run `ergane repo onboard <clone>` (`factory/workgraph/cli.py:532` —
   `onboard_command`) and `ergane init --check` (`factory/cli/init.py:2289` —
   `check_repo`) against that repository and confirm both report the same
   verdict, read for the declared branch. Those are two of the three doors into
   `onboard_target_repo`; the third is the dispatch activity in step 5.
5. Dispatch a spec against it through the roadmap and start one with
   `ergane build start`. Neither may park (`factory/roadmap/workflow.py:1262` —
   `_dispatch`) nor raise `GRAPH_INVALID`
   (`factory/workgraph/workflow.py:1225` — `_onboard_target`).
6. Re-run `ergane init --wire` unchanged and confirm it reports the ruleset
   already satisfied and issues no write — the property trap 7 exists to protect,
   and the one the offline model cannot prove.

Step 2 and step 5 are the falsifiable pair: step 2 is the bootstrap the reporters
could not complete, and step 5 is the epic start N10's reporter abandoned the
two-branch model to get past.
