# Plan: The names an operator types

All line references were read against the tree at `46f7e8b` on 2026-08-13. Grep
the construct beside each anchor rather than trusting the number — see trap 6.

## Reuse inventory

| What | Where | Used by |
| --- | --- | --- |
| The manifest name constant | `factory/verify/factory_yaml.py:58` — grep `MANIFEST_NAME =` | US1 — becomes a resolution helper |
| The parser and its loader | `factory_yaml.py:99` (`parse_factory_config`), `:331` (`load_factory_config`) | US1 — the parse itself does not change, only how the path is found |
| **Literal readers that bypass the constant** | `factory/activities/merge_activities.py:612`; `factory/mergequeue/onboard.py:161` and `:165` — grep `"factory.yaml"` | US1 — trap 1, the whole reason this is not a `sed` |
| The one legitimate constant user | `factory/activities/agent_activities.py:666` (`load_factory_config(Path(target_repo) / MANIFEST_NAME)`), message at `:407` | US1 — the shape every reader should end up with |
| The runtime root default | `factory/workgraph/worktree.py:75` — grep `DEFAULT_FACTORY_ROOT =` | US2 |
| Root resolution sites | `factory/activities/agent_activities.py:163`; `merge_activities.py:310`, `:374`, `:485`; `factory/cli/nouns/build.py:556` — grep `FACTORY_ROOT_ENV` | US2, US3 |
| Store and ledger path resolution | `factory/activities/verify_activities.py:540`; `factory/activities/notify_activities.py:643`; `factory/activities/usage_activities.py:521` — grep `def _store_path`, `LEDGER_PATH_ENV` | US3 |
| The four environment names | `verify_activities.py:123`, `usage_activities.py:96`, `agent_activities.py:136`, `factory/verify/store.py` (`EVIDENCE_STORE_ALLOW_REAL_ENV`) | US3 |
| The operator's env script | `scripts/ergane-env.sh` — emits `export` lines, must be `eval`'d | US3 — FR-009 |
| **030's session isolation fixture** | `tests/conftest.py` — grep `_isolated_test_store` | US3 — FR-009; it sets the three path variables by name |
| **030's store guard** | `factory/verify/store.py` — grep `EVIDENCE_STORE_ALLOW_REAL_ENV` | US2, US3 — a test that opens a real store path is refused; your migration tests must use tmp roots |
| The source-scanning test precedent | `tests/test_gh_client.py` — grep `test_no_code_path_passes_delete_branch` | US1 — FR-004's assertion style, already used in this repo |
| Live capacity read (is an epic running?) | `tests/test_live_capacity.py` and the capacity activity it exercises — grep `capacity_read` | US2 — FR-006's refusal needs this question answered |

## Traps

### Trap 1 — editing the constant is not the rename

`MANIFEST_NAME` looks like the single point of truth and is not. Three sites
hardcode `"factory.yaml"`: `merge_activities.py:612` (the merge-queue
preflight's manifest check) and `onboard.py:161`/`:165` (the readiness
judgment's finding). Change only the constant and both keep looking for the old
name — and **both fail quietly**, as a manifest-missing finding rather than an
exception, so the suite can stay green while every fresh repo is judged unready.
FR-004 exists to make this impossible to repeat: one helper, and a test that
scans the source for the literal.

### Trap 2 — `factory_yaml` is a key, not a filename

`onboard.py:161` emits a finding whose check name is `factory_yaml`, and
`tests/test_onboard.py:76`/`:184` and `tests/test_merge_activities.py:573`
assert on it. The findings ledger compares by key across time, which is what
makes "recurrence 3" a fact rather than a recollection. Renaming the key would
silently reset that history. Rename the file; leave the key. FR-010 and US1-S5
hold you to it.

### Trap 3 — the runtime root on this host is 281 MB of live memory

`.factory/` here holds the verification store, the usage ledger, node worktrees
and transcripts — including the evidence for every epic this factory has ever
run. US2 is not a `mkdir`; it is a move with a refusal condition. If it runs
while an epic is in flight, the workflow's next store write lands in a directory
that is no longer where the reader looks. FR-006's refusal is the guard, and the
capacity read already answers "is an epic running".

### Trap 4 — do not rename the Python package

The tempting completion of this work is `git mv factory ergane`. Do not. It
touches every import in the tree, every test, every traceback in every stored
transcript, and buys an operator nothing — no one outside this repository types
a module path. The same applies to the `factory/<epic>/<story>` branch prefix:
those names are in landed history and in the merge queue's rulesets. FR-010 and
US1-S5 fence both.

### Trap 5 — a rename that forgets `tests/conftest.py` re-opens 030's leak

030 landed a session fixture that redirects `FACTORY_ROOT`,
`FACTORY_VERIFICATION_DB_PATH` and `FACTORY_LEDGER_PATH` into pytest's tmp base.
It sets those variables *by name*. Rename what the engine reads without updating
that fixture and the suite goes back to writing the operator's live store —
the exact defect 030 closed hours before this spec was written, and it would
come back silently because the fixture would still appear to be doing its job.
FR-009 pairs the two edits; US3-S4 checks it.

### Trap 6 — anchors rot, and this tree is moving fast

Fifteen stories landed on 2026-08-13 alone. `notify_activities._store_path`
moved ~58 lines in two days; `test_agent_activities`' delenv case moved ~150.
Grep for the construct — `MANIFEST_NAME`, `DEFAULT_FACTORY_ROOT`,
`FACTORY_ROOT_ENV`, `def _store_path`, `_isolated_test_store` — and if a
citation here disagrees with the tree, the tree wins and you say so in the
commit message.

### Trap 7 — the deprecation must be once per command, not once per read

`_store_path()` and its siblings are called on every activity. A warning emitted
inside the resolver fires dozens of times per epic and trains the operator to
ignore it. Resolve once and carry the answer, or gate the warning behind a
module-level "already said this" flag. FR-002 and FR-008 both say *once*.

### Trap 8 — the proof is part of the deliverable

US2's claim is that a migration loses no rows. That is invisible in a diff: the
judge sees the diff and the criteria, never a terminal (constitution VIII). So
the before-and-after row counts are committed as pasted output in a comment
block in the test file, verbatim. This has cost the factory twice — 027/US2 died
four times on unjudgeable criteria, and 028/US3's agent fixed its story
correctly and skipped the paste.

## Approach

### US1 — one resolution helper, and no literals left

1. Replace `MANIFEST_NAME` with a resolver in `factory/verify/factory_yaml.py`:
   given a repo root, return the manifest path and which name it found. Keep
   `MANIFEST_NAME` as the *preferred* name (`ergane.yaml`) and add
   `LEGACY_MANIFEST_NAME`.
2. Route all four readers through it — the three literal sites in trap 1 plus
   `agent_activities.py:666`.
3. Add the source-scanning test (FR-004), copying the shape of
   `test_no_code_path_passes_delete_branch` in `tests/test_gh_client.py`.
4. Emit the deprecation once (trap 7), naming the file and the new name.

### US2 — resolve the root, then move it

1. Turn `DEFAULT_FACTORY_ROOT` into a resolver with the same two-name shape,
   reporting which it chose.
2. Add the migration as an operator command under the existing `repo` noun or as
   a `doctor` fix — pick one, and say which and why in the commit; the plan does
   not care, but a migration hidden inside an unrelated verb would.
3. Refuse while an epic runs (FR-006), using the capacity read rather than a new
   mechanism.
4. Test with tmp roots only. 030's guard refuses a real store path under pytest,
   and pointing a test at `/home/admin/code/ergane/.factory` would now raise
   rather than corrupt — but do not rely on that as your safety net.

### US3 — new names, old names honored

1. Add `ERGANE_*` alongside each `FACTORY_*`, new name winning, one deprecation.
2. Update `scripts/ergane-env.sh` to export the new names.
3. Update 030's `_isolated_test_store` fixture to set whatever the engine now
   reads (trap 5) — and keep it setting the legacy names too, so a partially
   migrated tree cannot leak.

## Complexity Tracking

| Thing | Why it is not simpler |
| --- | --- |
| Two-name resolution rather than a hard switch | The engine manages repositories it does not own; `ergane-003-target` exists today. A hard switch breaks every managed repo on upgrade, which is the opposite of the portability principle this rename serves. |
| A migration command rather than "operators move it themselves" | 281 MB including the evidence store. An operator `mv` during a running epic corrupts the factory's memory with no warning; FR-006's refusal is the point. |
| Three stories rather than one | US2 moves live state and US3 touches the fixture that keeps the suite off the operator's store. Serial, so each lands behind a green suite and a merged predecessor. |

## Verification

`uv run pytest -q` green in the worktree before and after each story — safe from
any directory as of 030.

Green is necessary and not sufficient for US2: a migration that loses rows can
still leave a green suite if no test counts them. The pasted before/after counts
are the evidence; see trap 8.
