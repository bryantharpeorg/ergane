# Plan: 049-forge-seam

Refined against the tree at `4ce493d` on 2026-08-16. Every line anchor below was
opened and read by hand at that commit; re-check them if the tree moves before
dispatch. This spec implements D-046 — read that entry before the first commit,
and read `factory/notify/adapter.py` beside it, because 041/US1 is the shape
this seam copies.

Findings this spec **works around and deliberately does not close**:

| Finding | Sev | Bearing |
| --- | --- | --- |
| `ci/the-scripted-gh-fake-never-consumes-an-expectation` | warning | FR-004 refuses to build on `tests/fake_gh.py`; trap 3. Fixing it would change what seven unrelated test modules assert, so it is out of scope by name. |
| `ci/the-adapter-conformance-suite-is-a-hardcoded-list-of-one` | warning | FR-005 refuses to inherit 041's conformance shape; trap 9. This spec does not repair the messenger suite. |

Neither is a prerequisite. Both are named so an implementer meets them as
declared scope rather than as a confusing failure.

## What already exists, and where

| Thing | Location | Note |
| --- | --- | --- |
| The judgment | `factory/mergequeue/onboard.py:95` (`evaluate_repo`) | Pure, table-tested, no fakes at all. US2's whole surface. Its five checks are at `:174` (visibility), `:190` (queue), `:209` (manifest), `:225` (squash title), `:255`/`:272` (gate↔check parity). |
| The fact gathering | `factory/activities/merge_activities.py:589` (`onboard_target_repo`) | Already takes a client as a parameter. US1's whole surface. |
| GitHub payload readers | `merge_activities.py:696` (`_queue_from_rules`), `:729` (`_classic_contexts`) | These parse GitHub's rulesets and classic-protection JSON. They are GitHub implementation detail sitting in a shared activity module — move them, don't wrap them. |
| The `gh` boundary | `factory/mergequeue/gh.py:131` (`GhClient`) | Stays. It becomes the GitHub forge's subprocess layer. Its runner seam is `GhRunner` at `:109`. |
| The three client seams | `merge_activities.py:296`, `factory/workgraph/cli.py:70`, `factory/cli/init.py:80` | All three construct `GhClient` concretely. All three must resolve a forge instead, or the seam leaks through the one you forgot. |
| The wiring | `factory/mergequeue/wiring.py:258` (`wire_repo`) | 034/US3, landed 4ce493d. US4 makes it the GitHub implementation. Its refusal type is `WiringRefused` at `:78`; the D-007 refusal is `_require_public` at `:346`. |
| The classifier | `factory/mergequeue/classify.py:50` | Pure. The one GitHub literal is `"DIRTY"` at `:74`. |
| The poll record | `factory/mergequeue/models.py:138` (`PrSnapshot`), `:160` (`from_gh_json`) | Crosses the Temporal payload boundary — see trap 8. |
| The onboarding gate | `factory/workgraph/workflow.py:833` (`_onboard_target`) | Reads `profile.passed` and `profile.findings`. Nothing else. Do not touch it — see trap 2. |
| The messenger seam | `factory/notify/adapter.py` — protocol `:134`, registry `:171`, `register_adapter` `:174`, `resolve_adapter` `:209`, default `:57`, env override `:54` | The shape. Copy the structure; improve on its conformance coverage (trap 9). |
| The reference messenger | `factory/notify/service.py:300` (`_build_telegram`), `:311` (`register_adapter("telegram", …)`) | How a shipped implementation registers itself. |
| The landing grammar | `factory/workgraph/landed.py:38` (`_LANDING_RE`) | Already forge-tolerant: `(?:\(#\d+\))?` makes the PR-number suffix optional. Nothing here needs to change; say so rather than changing it. |
| The manifest loader | `factory/verify/factory_yaml.py:86` (`_TOP_LEVEL_KEYS`), `:165` (`_reject_unknown_keys`) | US5's surface. Six keys today: `version`, `runtime`, `gates`, `timeouts`, `standards`, `landing_branch`. |
| The diff ceiling | `factory/verify/diffbounds.py:38` (`DIFF_INPUT_LIMIT`) | 61,440 bytes, refused deterministically. See trap 10. |

### The test landscape, and what it is worth

| Thing | Location | Note |
| --- | --- | --- |
| `FakeGh` | `tests/fake_gh.py:62` | **A recorder, not a model — and an open finding**, `ci/the-scripted-gh-fake-never-consumes-an-expectation`. `__call__` at `:78-97` scans from index 0 every call and consumes nothing, so the first match answers that command forever and a second expectation for it is unreachable; its own docstring at `:81-83` promises "next unconsumed expectation". Seven test modules ride it, including nine `test_validate_target_repo_*` in `tests/test_merge_activities.py`. Do not build on it; do not fix it here. |
| `FakeGitHub` | `tests/test_ergane_init_wiring.py:113` | **A model of a repository, and the bar.** Mutable state at `:121-132`; a `PATCH` mutates `squash_merge_commit_title` and a `POST` stores a ruleset at `:214-238`; `_rules_for_branch` at `:267` *derives* GitHub's flat per-branch rule list from stored rulesets; write payloads are read back off the temp file production actually wrote (`:194-196`); `snapshot()` at `:292` and `mutations()` at `:304`. |
| The round trip that makes it honest | `tests/test_ergane_init_wiring.py:348` (`onboarding_profile`), asserted at `:367-396` | Wire the model, then run `onboard_target_repo` against **the same object** and assert `profile.passed`. This is the pattern FR-004 demands. |
| `evaluate_repo`'s table tests | `tests/test_onboard.py` (19 functions, pure, no fakes) | US2 rewrites what these assert; keep them pure. |
| 041's conformance | `tests/test_messenger_adapter.py:532`, `:546`, `:564` | Three "every registered adapter" tests, each `@pytest.mark.parametrize("name", ["telegram"])`. **A hardcoded list of one**, filed as `ci/the-adapter-conformance-suite-is-a-hardcoded-list-of-one`. FR-005 says do not copy this. |
| 041's parity test | `tests/test_messenger_adapter.py:923-948` | `assert over_fake == over_telegram`, then absolute assertions so a shared break cannot hide. This part *is* worth copying. |
| Merge-surface guards | `tests/test_mergequeue_sweep.py:52-58` (`COMMAND_MODULES`), `:106`, `:112`, `:126` | Swept set is `factory/mergequeue/**` + `merge_activities.py` + `worktree.py`. See trap 6. |
| Vocabulary sweep | `tests/test_final_sweep.py:97` (`COMPONENT_MODULES` = all of `factory/**/*.py`), `:462` (`ENFORCEMENT_WORDS`), `:588` (the test) | See trap 5. |
| Sole-author guard | `tests/test_ergane_init_check.py:409` (`GUARDED_SLUGS`), `:416` (`GUARDED_PREFIXES`), `:441` (the test), `:453` (`package = JUDGMENT.parents[1]`, i.e. all of `factory/`) | See trap 7. |
| Anti-vacuity precedent | `tests/test_final_sweep.py:644` | A sweep that asserts its own file list is non-empty. US6-S2 copies this. |

## The design, stated once

The interface carries **nine operations and no tenth**, split across three
stories. The rule that decides whether a tenth belongs: *an operation exists
only where a forge's own vocabulary differs; everything the factory decides
stays factory-side.* Nothing on the seam classifies, settles, judges, retries,
or expires — the same rule `factory/notify/adapter.py:1-38` states for the
messenger.

**Reading (US1)** — describe the repository (its address, its default branch,
and any findings only this forge can author); report the landing policy for a
branch (does it gate on named checks, which checks, will it land without a
human, does the landing commit take the proposal's title).

**Landing (US3)** — find an existing proposal for a head; open one; request
landing; observe one; withdraw a landing request; fetch failing-check evidence.

**Wiring (US4)** — apply a landing policy to a branch, reporting each act, or
refuse before writing.

`evaluate_repo` then asks Q1–Q5 (spec § *What the factory actually needs*) of
those two read records, and each forge answers in its own terms. GitHub's answer
to Q2/Q3 includes D-007's visibility, authored in the GitHub implementation.

## Settled, not a route choice: the forge lives in `factory/mergequeue/`

`factory/forge/` was considered and rejected by the operator. Four modules
consume the forge (`merge_activities.py`, `workgraph/cli.py`, `cli/init.py`,
`cli/repo.py`), so a top-level package reads well — but
`tests/test_mergequeue_sweep.py:52-58` sweeps `factory/mergequeue/**`, and the
three guards it runs there (no branch deletion `:106`, no forced push `:112`,
only the automatic merge form `:126`) were earned by incidents rather than by
taste. Moving the landing surface out drops all three silently, and "we will
widen the sweep" is a promise the next implementer inherits rather than a
property the tree holds. FR-017 makes the location a requirement: put the forge
in `factory/mergequeue/` and take the guards for free.

## Route choices left to the implementer

**How a forge contributes its own findings.** Two candidates. (a) The repository
description carries a tuple of `Finding` the shared judgment appends. (b) A
separate protocol operation returning forge-specific findings. Prefer (a) —
fewer operations, and it keeps a forge's answer arriving with the facts it
answers about. Either way the ordering of `TargetRepoProfile.findings` must
remain stable enough for `_render_onboard` (`factory/workgraph/cli.py:400`) to
stay readable; the operator preflight reads repo health first, parity second
(`onboard.py:119-122`).

**How the conflict fact reaches the classifier.** Add a field to `PrSnapshot`
with a default, set it in the GitHub forge's observation, and have `classify`
read it. Do **not** translate other forges into GitHub's `mergeStateStatus`
spelling — that makes GitHub's vocabulary the interchange format, which is the
same defect as renaming (trap 1). Keep `merge_state_status` on the record if you
like, as evidence; just stop deciding from it.

## Traps

**Trap 1 — renaming is not seaming.** A protocol whose operations are
`merge_queue_enabled()` and `squash_merge_commit_title()` has moved the coupling
behind an interface and removed nothing. The test: read each operation's name
and its return type, and ask whether an Azure DevOps implementation could answer
it without contortion. "Is the merge queue enabled" fails that test. "Does this
forge refuse to land into this branch until named checks pass, and which checks"
passes it. Every neutral question in spec § *What the factory actually needs*
was written that way on purpose; if you find one that still smells of GitHub,
that is a spec defect worth raising, not a naming preference.

**Trap 2 — `EpicWorkflow` must not change, and this is not a soft preference.**
`factory/workgraph/workflow.py` has zero GitHub facts in its code; the only
GitHub words in it are a comment at `:663` and a docstring at `:837`. It
consumes `TargetRepoProfile.passed` and `.findings`, and both survive this spec
unchanged. Every replay defect this repository has shipped (032, 038, 039) came
from a workflow edit. **If you conclude that the workflow must change, stop and
say so loudly in your attempt output rather than changing it** — that
conclusion means the seam was drawn in the wrong place and the spec is wrong,
and a quiet workflow edit converts a spec defect into a determinism defect
nobody finds for a week. Updating the two stale *prose* lines is fine and
expected; changing a line of code is not.

**Trap 3 — a fake that only records calls makes every test vacuous, and this
repository has one.** `tests/fake_gh.py:62` is filed as the open finding
`ci/the-scripted-gh-fake-never-consumes-an-expectation`. The mechanism, verified:
its docstring at `:81-83` promises the "next unconsumed expectation", and
`__call__` (`:78-97`) scans the list from index 0 on every call and consumes
nothing. So the first matching expectation answers that command *forever*, a
second expectation for the same command is unreachable, and — the sharp
consequence — **any idempotence claim tested through it cannot fail.** Seven
test modules ride it, including the nine `validate_target_repo` tests in
`tests/test_merge_activities.py`.

Two instructions follow, and they pull in opposite directions on purpose. **Do
not build on it**: your fake forge must be a model of a repository in the
`FakeGitHub` sense (`tests/test_ergane_init_wiring.py:113`) — reads served from
mutable state, writes changing that state, and the part that matters, **the
factory's own reader is what judges the result** (`:348`, asserted `:367-396`).
Your primary assertion is what `evaluate_repo` says about the model; a call log
is a secondary assertion at best. **And do not fix it** — repairing that loop
changes what seven unrelated test modules assert, inside an epic whose whole
claim is that nothing observable changed. It is out of scope by name.

**Trap 4 — the four-tests-that-could-not-fail pattern.** On 2026-08-15 an
operator read found four tests in this repository structurally unable to fail:
they asserted on things that were true before the change, or scanned a file list
that was empty. Both shapes are available to this spec. A conformance test
parametrized over a registered-forge list that is computed *after* the registry
is populated will pass with zero forges if the import that registers them never
ran; a source sweep over a glob that matches nothing passes forever. For every
test you write here, answer in one line in the test's docstring: **what edit
would make this fail?** — and where the answer is a mutation, write the control
(SC-003 is exactly that control for US2).

**Trap 5 — the shipped package cannot spell what GitHub's API requires.**
`tests/test_final_sweep.py:588` collects every function name, class name, `Name`,
`Attribute`, argument, keyword, alias **and string constant** in
`factory/**/*.py` (docstrings excluded), splits them into words, and refuses any
that intersects `ENFORCEMENT_WORDS` (`:462`): `budget`, `cap`, `caps`, `capped`,
`quota`, `throttle`, `breach`, **`enforce`, `enforced`, `enforcement`**,
`exceed`, `overspend` and their plurals. GitHub's rulesets API requires a field
literally named `enforcement`, and the existing workaround is that the payload
lives in a data file (`factory/mergequeue/merge_queue_ruleset.json`) and is never
spelled in Python — `factory/mergequeue/wiring.py:28-32` records why. Two
consequences: keep that data file's role intact when wiring moves, and **do not
name any new operation, class, field or string constant with one of those
words.** `apply_landing_policy` is fine; anything built on "enforce" is a green
implementation that fails the suite on vocabulary.

**Trap 6 — the merge-surface guards are scoped to a directory, so leaving it
disarms them.** `tests/test_mergequeue_sweep.py:52-58` sweeps
`factory/mergequeue/**` plus two named files. The guards it runs are the ones
that keep this factory from ever deleting a branch (`:106`), force-pushing
(`:112`), or issuing a merge that is not the automatic form (`:126`). Put a
single forge module outside that directory and all three stop covering it — a
passing suite that checks nothing, which is trap 4 wearing a different hat. The
location is settled above and required by FR-017; US6-S3 proves the guards
reached the forge *without this spec having added a path to the swept set*,
which is the assertion that distinguishes "covered by construction" from
"covered because someone remembered".

**Trap 7 — the sole-author guard scans all of `factory/`.**
`tests/test_ergane_init_check.py:441` asserts no module outside
`factory/mergequeue/onboard.py` constructs a guarded readiness finding, and
`:453` sets the scanned package to `factory/`, not `factory/mergequeue/`. The
good news, verified: `GUARDED_SLUGS` (`:409`) is
`{runtime_root_ignored, runtime_root_migration, registry_entry, landing_branch,
control_plane}` and `GUARDED_PREFIXES` (`:416`) is `("gate_check:",
"unknown_check:")` — **`visibility` is not guarded**, so US2 may move it into the
GitHub implementation without touching that test. What you must not do is move
`gate_check:` or `unknown_check:` out: they are the neutral parity question
(Q4), they stay in the shared judgment, and `:449`'s `assert GUARDED_SLUGS <=
judged` fails the moment the judgment stops building one.

**Trap 8 — records that cross the Temporal boundary need defaults.**
`PrSnapshot`, `Landing` and `ObservedOutcome` (`factory/mergequeue/models.py`)
are serialized into workflow histories and are replayed. Every field US3 adds
needs a default such that a history written before this spec deserializes and
classifies identically (`models.py:99-105` and `:132-134` are the precedent, both
added the same way). This is 045's trap 5, and it is why FR-010 says so
explicitly.

**Trap 9 — do not copy 041's conformance coverage; it is a filed defect.**
`ci/the-adapter-conformance-suite-is-a-hardcoded-list-of-one`. Its three "every
registered adapter" tests (`tests/test_messenger_adapter.py:532`, `:546`,
`:564`) are each `@pytest.mark.parametrize("name", ["telegram"])` — a hardcoded
list of one, so a second adapter ships having never been conformance-checked.
FR-005 requires parametrizing over `registered_forges()` (or the equivalent), so
a registration enrols itself, plus trap 4's anti-vacuity assertion that the
parametrization is non-empty — otherwise the fix inherits the defect in a new
shape. What *is* worth copying is `:923-948`: a behavioural
parity assertion (`over_fake == over_telegram`) followed by absolute assertions,
so a break shared by both sides cannot hide behind the equality.

**Trap 10 — US1 is the largest story here, the ceiling is real, and the first
budget to spend is evidence rather than scope.** `DIFF_INPUT_LIMIT` is 61,440
bytes (`factory/verify/diffbounds.py:38`), the refusal is deterministic, it
happens before a judge sees anything, and it costs a whole attempt. US1 carries
a protocol, a GitHub implementation, a repository-modelling fake, a conformance
suite, and T011's three seam deletions — more than any other story in this spec.

Sessions in this repository systematically under-estimate diff size, and the
measurements are recent enough to trust. Two stories landed on 2026-08-16 at
60,848 and 60,269 bytes — both inside a kilobyte of the limit, and the second
only fit because it removed five test cases that duplicated CLI-level coverage.
A third arrived at 130,182 bytes, 2.1× the limit, and its judge verdict covered
less than half of what it contained.

The useful lesson is from the one that fit: **it fit by trimming evidence, not
code.** Duplicated coverage, and transcripts pasted at greater length than they
needed to be. Spend that budget first — one assertion at the layer that owns the
behaviour beats the same assertion repeated at the CLI, and a pasted tool output
needs only the lines that carry the claim.

**If scope genuinely must go, split by door — never by phase.** Each slice
replaces *and* deletes one construction seam atomically: the seam introduced,
one door moved onto it, that door's old construction gone, all in one diff. The
next slice takes the next door. What you must not do is "introduce the seam now,
delete the old constructions in a follow-up story": that is trap 14's defect
stretched over two landings instead of two concurrent nodes, and it is *worse*
than the concurrent case, because between the two landings the tree genuinely
carries both and every reader has to know which one is live. Splitting by door
keeps trap 14 intact at every landing; splitting by phase breaks it at the first
one. 032 was killed at attempt four for mis-sized scope, so raising "this story
is oversized" early is cheap and staying silent is not.

**Trap 11 — `enqueue_pr` passes no strategy flag, and that is deliberate.**
`factory/mergequeue/gh.py:184-195`: a branch governed by a merge-queue ruleset
owns its merge method, and `gh` refuses the flag outright — proved live
2026-08-07. `LandingConfig.merge_method` (`models.py:233`) survives as the
operator's declared intent, which must match the queue's own configuration. Do
not "restore" the flag while moving the call behind the seam.

**Trap 12 — `auto_merge_requested` decides nothing, and must not start.**
`factory/mergequeue/classify.py:79-86`: a merge-queue PR reports
`autoMergeRequest: null` for its whole ride, and the old heuristic that read its
absence as a human dequeue killed 009-us1's landing four seconds before GitHub
merged it. When the observation record grows a neutral conflict fact, resist the
symmetry of also making "landing requested" a decisive neutral fact. The stall
guard is the bounded exit for every open wait.

**Trap 13 — a story that teaches the manifest a key must not spend it.**
The config gate parses a node's manifest with the *worker's installed* parser,
not the worktree's. A US5 diff that adds `forge` to `_TOP_LEVEL_KEYS`
(`factory/verify/factory_yaml.py:86`) **and** writes `forge: github` into this
repository's `ergane.yaml` is rejected at `CONFIG_ERROR` in 0.0s, before any
gate command runs, every attempt, forever. 020/US1 died four times proving this
and left the warning in `ergane.yaml:38-45`. Fixture manifests in `tests/` are
safe; this repository's own manifest is not. FR-015 and US5-S4 exist for this.

**Trap 14 — there are three client seams, not one, and a fourth one appearing
beside them is how nine tests died today.** `merge_activities.py:296`,
`factory/workgraph/cli.py:70` and `factory/cli/init.py:80` each construct a
`GhClient`; `factory/cli/repo.py:49` imports the second. Three test modules bind
them directly — `tests/test_merge_activities.py:133` and its twenty siblings,
`tests/test_ergane_ports.py:214`, and `tests/test_ergane_init_check.py:145`
and `:150`. That last one patches **two** of the three seams in a single test,
which means the suite has recorded that this boundary has more than one door for
as long as that test has existed, and nobody read it as a signal. It is the
cheapest evidence in this plan and it was sitting in plain sight.

The live incident, 2026-08-16: 034/US3 and US4 were correctly modelled as
independent and ran concurrently. Each added a module-level `_gh_client_factory`
to `factory/cli/init.py`, with a different signature, in a different region of
the file. **No textual conflict**, so the merge kept both, the second shadowed
the first, and nine tests died. It cost a rework cycle and left an assertion
that had become unfalsifiable by merge. This spec's straight chain exists partly
because of it — but a chain only removes the concurrency, not the pattern. When
you replace a seam, **delete the one you replaced in the same diff**; never let
two module-level factories for the same boundary coexist in one file, even
briefly. A migration that moves two doors and leaves the third is the same
defect spread over two stories instead of two nodes, and US6's path allowlist is
what finally makes a forgotten door visible.

**Trap 15 — the landing grammar is already fine; do not "fix" it.**
`factory/workgraph/landed.py:38` makes GitHub's `(#<pr>)` suffix optional
(`(?:\(#\d+\))?`), so a forge that appends nothing already parses. Q5 is about
the *title source setting*, not about the reader. A story that edits `_LANDING_RE`
is a story that broke `ergane spec landed` for every existing history.

## Verification the operator will run, independent of the gate

- Run `ergane repo onboard /home/admin/code/ergane` before and after each story
  and diff the two reports byte for byte (SC-001). The command is offline — no
  Temporal, no proxy (`factory/workgraph/cli.py:379`).
- Take the fake repository model to a state with gating removed and confirm
  readiness fails, then restore it and confirm it passes — the SC-003 control,
  run by hand as well as in the suite.
- After US3, watch one real landing all the way through the queue on this
  repository. A green suite has shipped a command that could not start; the
  landing path is the one thing in this spec that no test exercises against a
  real forge.
- After US5 lands, restart the worker before adding `forge:` to this
  repository's `ergane.yaml` — and add it as a separate operator commit, never
  inside a node's diff (trap 13).
