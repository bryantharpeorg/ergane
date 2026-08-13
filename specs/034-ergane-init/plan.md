# Plan: Ergane Init

All line references were read against the tree at `bee1f5f` on 2026-08-13. Grep
the construct beside each anchor rather than trusting the number — see trap 10.

This epic is unusual in how much of it is *new surface*. Three of the mechanisms
it needs have no precedent anywhere in `factory/` (trap 4), so the reuse
inventory below is short on purpose: what it lists is genuinely reusable, and
what it omits, it omits because a grep found nothing.

## Reuse inventory

| What | Where | Used by |
| --- | --- | --- |
| **The shared readiness seam** (NOT the activity) | `factory/activities/merge_activities.py:590` — grep `def onboard_target_repo` | US4 — the one function both the Temporal activity and the offline CLI already call; trap 2 |
| The pure judgment | `factory/mergequeue/onboard.py:49` — grep `def evaluate_repo` | US4 — extended with init's new checks, never forked |
| Its finding grammar | `factory/mergequeue/models.py:208` — grep `class Finding` (`check`, `passed`, `detail`) | US4 — init's new checks emit the same three fields |
| Its table-test style (no fakes at all) | `tests/test_onboard.py` — twelve cases, grep `def test_a_fully_conforming_repo` | US4 — the shape your new check cases take |
| The `gh` seam | `factory/mergequeue/gh.py:128` (`GhClient`), `:106` (`GhRunner` protocol) | US3 — script the runner; do not shell out to `gh` directly |
| The injectable-seam idiom | `merge_activities.py:296` — grep `_client_factory` | US1 (the prompter), US3 (the `gh` client) — a module-level callable a test rebinds |
| **The `repo` noun, which already exists** | `factory/cli/nouns/repo.py` (registration, order 43); `factory/cli/repo.py:26` — grep `def add_repo_parser` | US2, US5 — new verbs go *beside* `onboard`; trap 3 |
| The unified CLI error boundary | `factory/cli/errors.py` — grep `class OperatorError` | US1–US5 — every refusal in this spec is an `OperatorError` with a code |
| The manifest parser and its rejections | `factory/verify/factory_yaml.py:99` (`parse_factory_config`), `:331` (`load_factory_config`), `:80` (`FactoryConfigError`) | US1 — FR-004 validates *with this*, never with a second copy of the rules |
| Its top-level key list | `factory_yaml.py:75` — grep `_TOP_LEVEL_KEYS` | US1 — the interview's question list is derived from it, not hand-maintained |
| The open-epic capacity read | `factory/activities/roadmap_activities.py:468` (`count_open_epics`), seam at `:462` (`_open_epics_provider`) | US5 — FR-011's refusal; read trap 6 first, it does not answer the per-repo question |
| The `input()` precedent, and its limits | `factory/cli/nouns/build.py:412`; its test at `tests/test_ergane_build.py:867` | US1 — one y/N works this way, a six-question interview does not; trap 5 |
| 030's session isolation fixture | `tests/conftest.py` — grep `_isolated_test_store` | US2 — the registry's test redirect belongs here, beside the store's; trap 8 |
| The source-scanning test precedent | `tests/test_gh_client.py` — grep `test_no_code_path_passes_delete_branch` | any story asserting "no call site does X" |

**Deliberately absent, verified by grep over `factory/`:** XDG or state-home
resolution (zero hits for `XDG_STATE_HOME`, `Path.home()` outside
`adapter.py:758`), file locking (zero hits for `fcntl`, `flock`, `filelock`),
git worktree detection (zero hits for `--git-common-dir`, `--show-toplevel`,
`is_inside_work_tree`), and `.gitignore` writing (one hit, and it is a comment).
See trap 4.

## Traps

### Trap 1 — the manifest is named `ergane.yaml` by 040, not by you

`MANIFEST_NAME = "factory.yaml"` (`factory_yaml.py:58`) is what the tree says
today, and three further call sites hardcode the literal. 040-manifest-rename
is in this spec's `depends_on_landed` precisely so that by the time you read
this, the parser resolves both names. **If you find yourself editing a manifest
filename in this epic, stop** — you are doing 040's work, and doing it in one
place while the other three sites fail *quietly* is the exact defect 040 exists
to prevent. Write `ergane.yaml`; call the resolver; change no constant.

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

### Trap 3 — `ergane repo` exists, and it already has a verb

`factory/cli/nouns/repo.py` registers the noun; `factory/cli/repo.py:26` gives
it `onboard`. US2 adds `list` and `rebuild`, US5 adds `forget`. Do not create a
second noun, do not rename `onboard`, do not move it. Note also what
`repo onboard` does and do not copy it: it delegates to the legacy
`factory.workgraph.cli.onboard_command` and translates `_OperatorError` into
`OperatorError`. New verbs raise `OperatorError` directly. The legacy path is
inherited, not exemplary.

### Trap 4 — three mechanisms this repository has never used

The greps above found no precedent for the state home, for file locking, or for
worktree detection. That means there is nothing to copy and no house style to
match, so each one is a decision you make and record in the commit message:

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

The only precedent is `build.py:412`, one bare `input()` for a y/N, tested by
rebinding `builtins.input` (`tests/test_ergane_build.py:867`). That does not
scale to an interview with defaults, per-answer validation, and a re-run that
loads the existing manifest. Put a prompter behind a module-level seam in the
`_client_factory` style (`merge_activities.py:296`) so a scripted interview is a
list of answers a test hands in. FR-005's claim — unchanged answers produce a
byte-identical manifest — is otherwise untestable, and it is the claim most
likely to be quietly false.

### Trap 6 — "is an epic running against *this repo*" has no answer today

`count_open_epics` (`roadmap_activities.py:468`) lists open `epic-*` workflows
across the namespace, and `workflow_id()` is `f"epic-{epic_id}"`
(`cli/nouns/build.py:83`) — **no repo token anywhere in it**. FR-007 says the
slug is *meant* to be the namespace token; nothing weaves it in yet, and doing
so is not this story's scope. So US5's `--clean-runtime` refusal refuses when
*any* epic is open, and says so in its message and its commit. Do not write a
per-repo filter over ids that contain no repo: it would match nothing, pass
every test you thought to write, and delete a live epic's evidence the first
time it mattered.

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

### Trap 10 — anchors rot, and this tree is moving fast

Nineteen stories landed on 2026-08-13 alone. Grep for the construct —
`onboard_target_repo`, `evaluate_repo`, `add_repo_parser`, `count_open_epics`,
`_client_factory`, `_isolated_test_store` — and if a citation here disagrees
with the tree, the tree wins and you say so in the commit message.

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
2. Add init's checks as `Finding`s in the same grammar: `.ergane/` gitignored,
   registry entry present and pointing here, landing branch exists, control
   plane reachable (one summary finding delegating to 033's probes; when 033 has
   not landed, that finding fails honestly rather than being omitted).
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
