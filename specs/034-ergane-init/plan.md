# Plan: Ergane Init

All line references were re-read against the tree at `d13fc4a` on 2026-08-14,
after 040-manifest-rename landed. Grep the construct beside each anchor rather
than trusting the number — see trap 10.

This epic is unusual in how much of it is *new surface*. Three of the mechanisms
it needs have no precedent anywhere in `factory/` (trap 4), so the reuse
inventory below is short on purpose: what it lists is genuinely reusable, and
what it omits, it omits because a grep found nothing.

## What has landed since this plan was written

**US1 landed 2026-08-14** (`7055ea5`, PR #69, first attempt):
`factory/cli/init.py` — repo-root resolution and both refusals, the prompter
seam (`_prompter_factory` at `:42`, `_TerminalPrompter` at `:53`), the
`_TOP_LEVEL_KEYS`-derived interview validated by `parse_factory_config`, and
the closed write list. US2 onward consumes what landed, not this plan's
description of it; US1's tasks are provenance. Trap 4's worktree-detection
third is discharged (US1 landed it); its state-home and locking thirds still
stand. Trap 5 is discharged the same way — the seam it demands is the one US1
built.

**033/us1 landed the same day** (`5b4351a`, PR #68): XDG *config*-home
resolution now exists at `factory/controlplane/config.py:174`/`:190`. FR-006's
state-home resolver follows that pattern and `resolve_env_path`, and the two
resolvers must not drift apart — 033's trap 5 is the mirror of this warning.

**A prior us2 attempt was killed mid-flight on 2026-08-14** — the `rm -rf`
incident took the floor down; the work was never judged and never landed. Its
diff survives at `refs/heads/archive/factory/034-ergane-init/us2/b52cf465ec42`:
a partial registry/lock implementation. Reference material only, written
before this plan's current form — read it critically if at all; the tasks
bind, not the archive.

## Reuse inventory

| What | Where | Used by |
| --- | --- | --- |
| **The shared readiness seam** (NOT the activity) | `factory/activities/merge_activities.py:589` — grep `def onboard_target_repo` | US4 — the one function both the Temporal activity and the offline CLI already call; trap 2 |
| The pure judgment | `factory/mergequeue/onboard.py:49` — grep `def evaluate_repo` | US4 — extended with init's new checks, never forked |
| Its finding grammar | `factory/mergequeue/models.py:208` — grep `class Finding` (`check`, `passed`, `detail`) | US4 — init's new checks emit the same three fields |
| Its table-test style (no fakes at all) | `tests/test_onboard.py` — twelve cases, grep `def test_a_fully_conforming_repo` | US4 — the shape your new check cases take |
| The `gh` seam | `factory/mergequeue/gh.py:128` (`GhClient`), `:106` (`GhRunner` protocol) | US3 — script the runner; do not shell out to `gh` directly |
| The injectable-seam idiom | `merge_activities.py:296` — grep `_client_factory` | US1 (the prompter), US3 (the `gh` client) — a module-level callable a test rebinds |
| **The `repo` noun, which already exists** | `factory/cli/nouns/repo.py` (registration, order 43); `factory/cli/repo.py:74` — grep `def add_repo_parser` | US2, US5 — new verbs go *beside* `onboard` and `migrate-runtime-root`; trap 3 |
| The unified CLI error boundary | `factory/cli/errors.py:30` — grep `class OperatorError` | US1–US5 — every refusal in this spec is an `OperatorError` with a code |
| The manifest parser and its rejections | `factory/verify/factory_yaml.py:106` (`parse_factory_config`), `:386` (`load_factory_config`), `:87` (`FactoryConfigError`) | US1 — FR-004 validates *with this*, never with a second copy of the rules |
| **The two-name manifest resolver 040 landed** | `factory_yaml.py:341` (`resolve_manifest_path`), `:418` (`load_factory_config_with_name`), `:59`/`:65` (`MANIFEST_NAME`, `LEGACY_MANIFEST_NAME`) | US1, US4 — trap 1; the answer to "which manifest does this repo have" is already written |
| **The runtime-root resolver 040 landed** | `factory/workgraph/worktree.py:135` (`resolve_factory_root`), `:82`/`:85` (`DEFAULT_RUNTIME_ROOT`, `LEGACY_FACTORY_ROOT`), and `RuntimeRootChoice` | US4, US5 — trap 12; a repo mid-migration has `.factory/`, not `.ergane/` |
| **The env-variable resolution convention 040 set** | `factory/env.py` — grep `def resolve_env_path` | US2 — FR-006's state-home override is a new operator-facing variable and must follow this, not `os.environ.get` |
| Its top-level key list | `factory_yaml.py:82` — grep `_TOP_LEVEL_KEYS` (six keys: `version`, `runtime`, `gates`, `timeouts`, `standards`, `landing_branch`) | US1 — the interview's question list is derived from it, not hand-maintained; the six are why FR-005 is a six-question interview |
| The open-epic capacity read | `factory/activities/roadmap_activities.py:469` (`count_open_epics`), seam at `:465` (`_open_epics_provider`) | US5 — FR-011's refusal; read trap 6 first, it does not answer the per-repo question |
| The `input()` precedent, and its limits | `factory/cli/nouns/build.py:420`; its test at `tests/test_ergane_build.py:867` | US1 — one y/N works this way, a six-question interview does not; trap 5 |
| 030's session isolation fixture | `tests/conftest.py` — grep `_isolated_test_store` | US2 — the registry's test redirect belongs here, beside the store's; trap 8 |
| The source-scanning test precedent | `tests/test_gh_client.py` — grep `test_no_code_path_passes_delete_branch` | any story asserting "no call site does X" |

**Deliberately absent, re-verified by grep over `factory/` at `0bf0c93` on
2026-08-14:** state-home resolution and file locking (zero hits for
`XDG_STATE_HOME`, `fcntl`, `flock`, `filelock`) — still yours to introduce,
see trap 4. **No longer absent**: XDG *config* resolution (033/us1,
`factory/controlplane/config.py`), and worktree detection and `.gitignore`
writing (this spec's own US1, `factory/cli/init.py`). See "What has landed"
above.

## Traps

### Trap 1 — the manifest is named `ergane.yaml` by 040, not by you

**040 landed on 2026-08-14 (`41f0aa3`, `2f1688c`, `d13fc4a`).** This trap is no
longer a warning about the future; it is a map of what is already there, and
re-deriving any of it is how this epic wastes an attempt.

- `MANIFEST_NAME = "ergane.yaml"` (`factory_yaml.py:59`) and
  `LEGACY_MANIFEST_NAME` (`:65`). Both are constants. Change neither.
- `resolve_manifest_path(repo_root)` (`:341`) returns `(path, name)` and already
  encodes the whole policy: `ergane.yaml` wins, a lone `factory.yaml` loads with
  a deprecation, and when both exist the ignored one is named. It warns; you do
  not.
- `load_factory_config_with_name(repo_root)` (`:418`) is the same thing with the
  parse attached — the one US4 wants when it needs to say *which* manifest it
  judged.

**If you find yourself editing a manifest filename in this epic, stop** — you
are doing 040's work, and doing it in one place while the other sites fail
*quietly* is the exact defect 040 existed to prevent. Write `ergane.yaml`; call
the resolver; change no constant.

One live consequence for US4: this repository currently carries **both**
`ergane.yaml` and `factory.yaml` at its root, byte-identical, because 040 added
the new name without removing the old. So the "both present" branch is not a
hypothetical your tests invent — it is the state of the tree you are working in,
and a `--check` that treats it as a failure will fail against Ergane itself.

### Trap 2 — the readiness gathering is not the Temporal activity

The obvious move for US4 is to call `validate_target_repo`. It is
`@activity.defn` (`merge_activities.py:773`) and cannot be called from a CLI.
It is a three-line wrapper. The seam both doors already share is
`onboard_target_repo(client, target_repo)` at `merge_activities.py:590`, and
the offline path already goes through it — `factory/cli/repo.py` →
`factory.workgraph.cli.onboard_command`. FR-010's "one judgment, two doors" is
therefore *already true* for the 003 checks; your job is to add init's checks
to the same judgment, not to build a second one that agrees with it today and
drifts next month.

### Trap 3 — `ergane repo` exists, and it now has two verbs, one of which is the model

`factory/cli/nouns/repo.py` registers the noun; `factory/cli/repo.py:74`
(`add_repo_parser`) gives it `onboard` and — as of 040/US2 —
`migrate-runtime-root`. US2 adds `list` and `rebuild`, US5 adds `forget`. Do not
create a second noun, do not rename either verb, do not move them.

The two existing verbs are not equally worth copying:

- `repo onboard` (`:119`) delegates to the legacy
  `factory.workgraph.cli.onboard_command` and translates `_OperatorError` into
  `OperatorError`. **Inherited, not exemplary.**
- `repo migrate-runtime-root` (`:132`) is the shape your verbs take: it raises
  `OperatorError` directly with an explicit `code=`, it is a dry run unless
  given `--yes`, it is idempotent and says so when there is nothing to do, and
  it refuses while epics are running rather than racing them. US5's
  `repo forget --clean-runtime` is the same verb with a different noun-object;
  read it before writing.

Copy its **shape**, not its body — see trap 6 for the defect inside it.

### Trap 4 — three mechanisms this repository has never used

The greps above found no precedent for the state home or for file locking
(worktree detection has since landed with US1 — its bullet below is kept
because the reasoning matters if the code is ever touched). For the two that
remain there is nothing to copy and no house style to match, so each is a
decision you make and record in the commit message — though the archived us2
attempt (see "What has landed") contains one prior, unjudged answer worth a
critical skim:

- **State home (FR-006).** The registry lives outside every repo. Resolve
  `XDG_STATE_HOME` with the documented `~/.local/state` fallback, and make the
  root overridable by one environment variable — without that override the
  suite writes into the operator's real registry (trap 8).
- **Locking (FR-008).** `fcntl.flock` on the registry file is the least
  machinery that satisfies "exclusive". Test the *contended* case, not only the
  happy one: two writers, one lock, second one blocks or refuses. A lock only
  ever tested uncontended is a lock nobody has tested.
- **Worktree refusal (FR-001).** Do not test for a `.git` *file* — a submodule
  has one too. Compare the two git dirs; they are equal in a primary checkout
  and differ in a linked worktree. Verified, verbatim:

  ```
  MAIN: git-dir=.git  common=.git                       top=…/gwt/main
  WT:   git-dir=…/main/.git/worktrees/wt  common=…/main/.git  top=…/gwt/wt
  WT .git is a file
  ```

  Two things follow. `--show-toplevel` in a worktree returns the *worktree*, so
  "operate on the repo root found via git" (edge case 1) would cheerfully
  register a factory node's workspace — which is what AS6 refuses. And the
  primary checkout AS6 must *name* is the parent of `--git-common-dir`, so the
  refusal can be specific rather than generic.

### Trap 5 — a six-question interview cannot be a monkeypatched `input()`

The only precedent was `build.py:420`, one bare `input()` for a y/N, tested by
rebinding `builtins.input` (`tests/test_ergane_build.py:867`). That does not
scale to an interview with defaults, per-answer validation, and a re-run that
loads the existing manifest — which is why US1 put the prompter behind a
module-level seam in the `_client_factory` style, and **US1 has landed**:
`_prompter_factory` at `factory/cli/init.py:42`. This trap is now the record of
why the seam exists. Later stories that script an interview drive that seam;
none may reach for `builtins.input`.

### Trap 6 — "is an epic running against *this repo*" still has no answer, and the CLI path that asks the blunt question is broken

Two halves. Read both before writing US5.

**The question is still unanswerable per-repo.** `count_open_epics`
(`roadmap_activities.py:469`) lists open `epic-*` workflows across the
namespace, and `workflow_id()` is `f"epic-{epic_id}"` (`cli/nouns/build.py:91`)
— **no repo token anywhere in it**. FR-007 says the slug is *meant* to be the
namespace token; nothing weaves it in yet, and doing so is not this story's
scope. So US5's `--clean-runtime` refusal refuses when *any* epic is open, and
says so in its message and its commit. Do not write a per-repo filter over ids
that contain no repo: it would match nothing, pass every test you thought to
write, and delete a live epic's evidence the first time it mattered.

**The CLI-side helper now exists — and it does not work.** 040/US2 added
`_running_epic_ids()` (`factory/cli/repo.py:66`), which is genuinely the right
pattern and the one to reuse: it runs the existing activity outside a workflow
through `temporalio.testing.ActivityEnvironment`, so the CLI asks the same
question the roadmap asks without a second implementation. Reuse the pattern.

But it is reached through `_temporal_client_factory` (`:63`), which defaults to
`_open_client()` (`:49`), which calls `os.environ.get` at `:51`–`:52` in a module
that **never imports `os`**. Every test rebinds the seam, so nothing executes the
default. Measured on 2026-08-14 against a scratch repo holding only `.factory/`:

```
$ ergane repo migrate-runtime-root
ergane: unexpected error (name 'os' is not defined)
```

The suite was green — 2265 passed — through the merge queue and the judge.
Filed as `cli/migrate-runtime-root-cannot-run` (critical).

**Order check first — 043 probably got here before you.**
`043-runtime-root-integrity` precedes this epic in the agreed dispatch order
(043 → 011 → 033 → 034) and lands both halves of what follows: the `import os`
repair with an AST guard over the module (its US3), and the findings ledger
routed through the resolver (its US2). Before acting on items 2 and 3 below,
run the verb against a closed port (`TEMPORAL_ADDRESS=127.0.0.1:1`): if it
refuses with a transport error naming the address, 043 landed and both items
are already done — verify and move on, and do not re-fix landed work. The
instructions below bind only if the `NameError` is still live.

Three things follow, and the third is the one that costs you an attempt:

1. Reuse `_running_epic_ids`, but do not assume it runs. One test in your diff
   must reach the real `_open_client` — with the seam unrebound, pointed at a
   closed port — and assert it fails as a transport error rather than a
   `NameError`. That test fails today, which is the point.
2. Fixing the missing import is inside your blast radius and you should fix it,
   because US5 cannot otherwise honour FR-011. Name the finding in the commit.
3. **Do not fix it in isolation.** `doctor/findings-store-not-routed-through-runtime-root-resolver`
   (critical) records that the findings ledger still hardcodes
   `.factory/doctor.db` in four places (`cli/doctor.py:41`, `doctor/cli.py:40`,
   `doctor/probes.py:133`). Today the `NameError` is the only thing preventing a
   migration, and a migration silently abandons every recurrence count — the
   number that decides what gets promoted to the constitution. Repairing the
   crash without routing the ledger arms that trap. If you are not also fixing
   the ledger, say so in the commit and leave the migration verb refusing.

### Trap 7 — the judge sees the diff, never your terminal

Constitution VIII. Three of this spec's central claims are invisible in a diff:
`git log` byte-identical across init (SC-002), re-run is a no-op (SC-003, FR-005),
two exports byte-identical (US5's independent test). Each is met by a test in
the diff **plus its verbatim pasted output** in a comment block — not described,
not summarized. This has cost the factory twice: 027/US2 died four times on
criteria the judge could not check, and 028/US3's agent fixed its story
correctly and then failed for skipping the paste.

### Trap 8 — nothing stops a test from writing the operator's real state

030's guard refuses a real *evidence store* path under pytest. It does not know
about a registry, a `.gitignore`, or a scaffolded `ergane.yaml`. Every test here
builds its git repo under `tmp_path` and points the state-home override at
`tmp_path` too, and that override belongs in the same session fixture 030
landed (`tests/conftest.py`, grep `_isolated_test_store`) so it is on by default
rather than remembered per-test. A test that registers a repo into the
operator's live registry leaves a pointer to a directory that will not exist
tomorrow.

### Trap 9 — the workflow US3 scaffolds must declare exactly the gates, and no more

`evaluate_repo` emits `unknown_check:<name>` (`onboard.py:220`) for any required
check that is not a declared gate — that is what keeps the LLM judge out of CI,
and it fails closed. A generated workflow with a helpful extra job wired as a
required check therefore makes the repo fail its own `--check` one step later.
Job names equal gate names, one to one, nothing else required. And wire `gh`
through the `GhRunner` protocol (`gh.py:106`) with a scripted runner: the live
tier is opt-in and is not where this story is proven.

### Trap 11 — US6 has no seam to reuse, because the capability does not exist

Every other story in this spec extends something. US6 does not. Verified on
2026-08-13 against `0a47cc5`:

- `factory/cli/roadmap.py` registers exactly five verbs — `start`, `pause`,
  `resume`, `status`, `promote`. None creates a schedule.

> **Both bullets have decayed since 2026-08-13 — re-verified 2026-08-16 at
> `2a40d1d`.** There are now **six** verbs: `044-prompt-assembly-preflight/us2`
> landed `unpark` earlier the same day (`factory/cli/roadmap.py:150`). Still none
> creates a schedule, so the trap's conclusion holds — but do not use "five" as a
> fact about the tree.
>
> **"No seam to reuse" is also overstated.** `046-operator-status-cli` landed
> schedule *reads*: `factory/roadmap/discovery.py`, plus `pause`/`unpause`
> handling. US6 should interoperate with it deliberately rather than build
> beside it — in particular the created schedule's action workflow id must stay
> what `discovery` matches on, or `ergane roadmap status` will not find the
> schedule US6 just made. The implementing session found this and did exactly
> that; it is recorded here so the next reader does not rediscover it.
>
> A note on how this correction was made: the first check of the verb count was
> a single-line `grep` for `add_parser("<name>"` and it reported five, because
> `unpark`'s call is wrapped across two lines. The implementer's count was right
> and the operator's grep was wrong. Cheap reminder that a verification tool can
> be the thing that is broken.
- `grep -rn "create_schedule\|ScheduleSpec" --include=*.py factory/` returns
  **nothing**.
- The one live schedule, `ergane-roadmap`, was created by hand with the
  `temporal schedule` CLI and reports `CreatedAt 5 days ago`. Its arguments are
  a base64-encoded payload, which is why `max_concurrent_epics` has never been
  changed.

Two consequences. First, there is no existing shape to copy, so put the whole
create/reconcile/delete lifecycle behind one seam and script it in tests — this
spec's suite must not require a live Temporal (trap 8's discipline).

Second, and this is the trap: `roadmap promote` **signals a running roadmap
workflow**, and the roadmap does not run continuously — it is a schedule that
starts a workflow every few minutes and exits. Running `ergane roadmap promote`
against an idle floor fails with `no roadmap 'specs' is running here`. If you
reach for that verb as the model for "how the engine talks to the roadmap", you
will build against a workflow that is usually not there. The schedule is server
state; talk to it as server state.

The identifier is the other half. One namespace and one shared control plane
means the schedule id must carry the repo slug (FR-014) — the same token trap 6
records as missing from `workflow_id()`. Do not repeat that omission in a
surface being written from scratch.

### Trap 12 — a repo that has not migrated has `.factory/`, and US4 must not call that a failure

040/US2 made `.ergane/` the runtime root and left `.factory/` working, reachable
through `resolve_factory_root()` (`worktree.py:135`), which returns the path
*and* a `RuntimeRootChoice` saying which one it found. `DEFAULT_RUNTIME_ROOT` is
`.ergane` (`:82`), `LEGACY_FACTORY_ROOT` is `.factory` (`:85`).

This touches two stories:

- **US4's "`.ergane/` is gitignored" check.** A repo that has not run
  `migrate-runtime-root` has a populated `.factory/` and no `.ergane/` at all.
  A check that asserts `.ergane/` is ignored and stops there reports a failure
  the operator cannot act on and misses the directory actually holding their
  state. Ask the resolver which root this repo has, and require *that* one
  ignored — then, if it is the legacy one, emit a second finding naming
  `ergane repo migrate-runtime-root` as the remedy. That is a `Finding` in the
  same grammar, not a warning printed to the side.
- **US5's `--clean-runtime`.** It deletes a runtime root. Deleting the one whose
  name you assumed, rather than the one the resolver found, is a no-op on an
  unmigrated repo — and a silent one, which is worse than a refusal.

The operator's own checkout is the live example, now in the **split** state: at
`0bf0c93` it has `.ergane/` (holding `homes/`) *and* a populated `.factory/`
(all three databases) — precisely the layout 043's US2 exists to keep readable.
And if 043 landed before this epic, the migration verb works and the checkout
may have been fully migrated by the time you read this. Ask the resolver;
never assume either name.

### Trap 10 — anchors rot, and this tree is moving fast

Nineteen stories landed on 2026-08-13 and three more on 2026-08-14. Every
anchor above was re-read at `d13fc4a`; roughly a third had moved since this plan
was first written. Grep for the construct — `onboard_target_repo`,
`evaluate_repo`, `add_repo_parser`, `count_open_epics`, `_client_factory`,
`_isolated_test_store`, `resolve_factory_root`, `resolve_manifest_path` — and if
a citation here disagrees with the tree, the tree wins and you say so in the
commit message.

## Approach

### US1 — the scaffold: refuse, interview, write, and commit nothing

1. Resolve the repo root through git, and refuse two cases before any question
   is asked: not a repository (name `git init`), and a linked worktree (name the
   primary checkout, derived from `--git-common-dir`'s parent — trap 4).
2. Put the prompter behind a seam (trap 5). Derive the question list from the
   parser's own top-level keys (`factory_yaml.py:75`) so a schema that grows
   does not leave the interview behind.
3. Validate each answer as it is given, with `parse_factory_config` itself —
   FR-004 is "the installed parser decides", and a second copy of the rules in
   the interview is a second thing to keep in sync.
4. Write exactly the declared files, print every path written, and print the
   `git add` / `git commit` the operator will run. Nothing else. FR-002 is a
   closed list, and SC-002 checks it by comparing `git log` and `git status`
   either side of the run.
5. Re-run loads the existing manifest as defaults. Prove byte-identity on
   unchanged answers, and paste the proof (trap 7).

### US2 — the registry: a cache that is honest about being one

1. Resolve the state home once (trap 4), overridable, and hold `flock` for
   every mutation (FR-008) with a contended test.
2. Entries carry slug, absolute path, and derived scopes. Slug collision is
   refused naming the holder's path (FR-007).
3. `repo list` renders manifest status per entry — valid, invalid, missing —
   and never drops an entry to hide drift (AS5). `repo rebuild` verifies every
   entry, prunes dead ones, touches live ones never.
4. Both verbs are added to the existing parser (trap 3).

### US3 — wiring: idempotent, reported, and refused with the constraint named

1. Every act through the `GhClient` seam, each reporting applied or
   already-satisfied.
2. Refusals name the constraint at the point of refusal: visibility per D-007
   with both remedies, missing or unauthenticated `gh` with the exact login
   command and an offer to print the manual steps.
3. The scaffolded workflow defines one job per declared gate, named exactly
   after it, running exactly its command — and requires nothing else (trap 9).

### US4 — the check: init's facts, the 003 judgment

1. Call `onboard_target_repo` (trap 2) for the facts 003 already gathers.
2. Add init's checks as `Finding`s in the same grammar: the repo's *resolved*
   runtime root gitignored (trap 12 — ask `resolve_factory_root()`, do not
   assume `.ergane/`), registry entry present and pointing here, landing branch
   exists, control plane reachable (one summary finding delegating to 033's
   probes; when 033 has not landed, that finding fails honestly rather than
   being omitted).
3. One finding per check, no masking, non-zero exit on any failure. Prove SC-004
   by breaking each precondition one at a time and asserting exactly one
   finding flips.
4. A full `ergane init` ends by running this.

### US5 — leaving, and taking the records

1. `repo forget <slug>` removes the entry and nothing else; the tree is
   byte-identical after (AS1).
2. `--clean-runtime` refuses while any epic is open (trap 6), naming what it saw.
3. `--export <dir>` writes one JSONL per store plus a markdown digest, selected
   by slug, outside `.ergane/`, no secret values, committing nothing. Two
   exports against an untouched engine are byte-identical — pasted proof
   (trap 7). Without the flag, no file is written at all.

## Complexity Tracking

| Thing | Why it is not simpler |
| --- | --- |
| Five stories | US1 is usable alone (a repo can be scaffolded before the engine knows it exists); US2 is what every fleet surface needs; US3 and US4 are independent of each other and both merge-chained behind US2; US5 is P3 and blocks nothing. Collapsing them would put the GitHub-touching story in the same attempt as the file-writing one. |
| A prompter seam rather than `input()` | FR-005's byte-identity claim is the spec's most falsifiable promise and cannot be tested through a monkeypatched builtin (trap 5). |
| A registry at all, given the manifest is authoritative | You cannot enumerate committed facts you cannot find. The registry is explicitly a cache — FR-006 requires `rebuild` to make re-deriving it safe at any moment, which is the whole defence against it becoming a second source of truth. |
| Refusing on *any* open epic in US5 | The honest answer to a question the id scheme cannot yet answer per-repo (trap 6). A precise-looking filter over ids with no repo token would be worse than a blunt refusal. |

## Verification

`uv run pytest -q` green in the worktree before and after each story — safe from
any directory as of 030.

Green is necessary and not sufficient. Three claims need pasted evidence in the
diff rather than a passing assertion (trap 7): history untouched across init,
re-run byte-identity, export byte-identity. And US2's lock needs a contended
test, not a happy-path one — a lock is only proven by the writer it blocked.
