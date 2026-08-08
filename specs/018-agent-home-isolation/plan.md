# Implementation Plan: Agent Home Isolation

**Branch**: `018-agent-home-isolation` | **Date**: 2026-08-08 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/018-agent-home-isolation/spec.md`

## Summary

One name in one allowlist, and the three things that hang off it. `attempt_env`
stops passing the worker's `HOME` and starts passing a per-node directory the
factory created under `FACTORY_ROOT`; the factory writes into that directory
whatever the agent CLI needs to start non-interactively, from its own constants;
and the credential sweep that already asserts what a child receives is extended
to hold the new rule. Evidence, salvage, personas, prompts and the judge are all
unchanged — the only thing that moves is the directory the agent calls home.

This plan is deliberately self-contained: the prompt assembler ships
spec/plan/tasks only, so every fact an implementer node needs is inlined, each
verified against the tree on 2026-08-08 — and T001 re-verifies them against the
tree that actually hosts the work, plus resolves the one input that could not be
verified at drafting time.

## Technical Context

**Language/Version**: Python 3.11+ (D-003); the worker host runs 3.13.

**Primary Dependencies**: none added. The change uses `pathlib`, `os`, and the
`asyncio` subprocess plumbing already in the adapter.

**Verified reuse inventory** (file:line as of 2026-08-08; T001 re-checks):

- **The allowlist itself**: `PASSTHROUGH_ENV: tuple[str, ...] = ("PATH",
  "HOME", "LANG", "TERM")` at `factory/workgraph/adapter.py:75`, consumed by
  `attempt_env(context, environ=None)` at `factory/workgraph/adapter.py:306`,
  whose body is `{"ANTHROPIC_BASE_URL": …, "ANTHROPIC_AUTH_TOKEN": …} | {name:
  source[name] for name in PASSTHROUGH_ENV if source.get(name)}`. The docstring
  states the design in one line worth preserving: the allowlist is a
  construction, so credentials are absent by omission rather than by redaction
  (constitution V). The comment above `PASSTHROUGH_ENV` describes `HOME` as
  "where it keeps its own session state" — accurate, and exactly why the fix is
  a different home rather than no home.
- **The path helpers to mirror**: `pid_file(factory_root, epic_id, node_id)` at
  `factory/workgraph/adapter.py:282` and `transcript_dir(factory_root, epic_id,
  node_id, attempt)` at `:270`, both under a "Paths on the worker host" banner —
  that block is where the new helper belongs, with the same signature shape and
  the same docstring discipline (say what the key is and why). The third of the
  family, `worktree_path(factory_root, epic_id, node_id)`, lives **not** in the
  adapter but at `factory/workgraph/worktree.py:134`; it is the keying precedent
  to copy, not a neighbour to sit beside.
- **`AttemptContext`** (`factory/workgraph/models.py:285`) already carries
  `worktree_path`, `session_id`, `proxy_url`, `virtual_key`, `model_alias`,
  `timeout_s` and the `(epic_id, node_id, attempt)` identity. It is the
  established way a per-attempt path reaches the adapter, and it is where the
  home path should ride.
- **The archive step**: `ClaudeCodeAdapter._archive_session`
  (`factory/workgraph/adapter.py:680-709`) resolves `Path(env["HOME"]) /
  ".claude" / "projects" / project_dir_name(worktree) /
  f"{context.session_id}.jsonl"`. It reads the **child's** env, not
  `os.environ`, and its docstring already says why: "From the *child's* `HOME`,
  because that is the home the transcript was written under." This composes with
  the change for free — which is a fact to prove in a test, not to assume in a
  review. Note its two silent returns: `if not home: return` and `if not
  source.is_file(): return`.
- **`project_dir_name(cwd)`** (`factory/workgraph/adapter.py:292`) reproduces
  the CLI's own `/home/a/b` → `-home-a-b` rule so the factory can find the file
  it archives. Unchanged by this spec: the rule is applied under a new root, not
  altered.
- **Salvage identity**: `_SALVAGE_IDENTITY` (`factory/workgraph/worktree.py:537`)
  sets `GIT_AUTHOR_NAME`/`GIT_AUTHOR_EMAIL`/`GIT_COMMITTER_NAME`/
  `GIT_COMMITTER_EMAIL` from `SALVAGE_AUTHOR_NAME = "Ergane Factory"` and
  `SALVAGE_AUTHOR_EMAIL = "factory@ergane.invalid"` (`:76-77`), passed as
  `env_extra` at `:271` and `:384`. The module docstring (`:46-51`) explains the
  reasoning — reading `user.name` from the host would attribute automated
  commits to a person who did not make them. Reuse these constants; do not
  invent a second identity.
- **The proof that salvage already survives a fresh home**: the autouse fixture
  `no_operator_git_identity` (`tests/test_worktree.py:104`) runs the whole
  worktree suite with `HOME` pointed at an empty directory and
  `GIT_CONFIG_GLOBAL`/`GIT_CONFIG_SYSTEM` silenced. Constitution VI is therefore
  not at risk from this change, and that is worth stating in the PR body.
- **The sweep to extend**:
  `tests/test_workgraph_sweep.py:957`,
  `test_the_virtual_key_is_read_into_exactly_one_environment_variable`. It
  asserts two things: that `virtual_key` is read in exactly `{"attempt_env"}`,
  and that the built environment equals exactly `{"ANTHROPIC_BASE_URL",
  "ANTHROPIC_AUTH_TOKEN", "PATH": "/usr/bin", "HOME": "/home/factory"}` given a
  worker environment that also holds `LITELLM_MASTER_KEY`,
  `TELEGRAM_BOT_TOKEN` and `SOME_FUTURE_CREDENTIAL`. This is not a stale
  assertion to delete — it is the credential guarantee, and the `HOME` line in
  it is the point of contact where the new rule gets written down.
- **Spawn shape**: `asyncio.create_subprocess_exec(*self.argv(context),
  stdin=PIPE, stdout=log, stderr=STDOUT, cwd=str(worktree), env=env,
  start_new_session=True)` at `factory/workgraph/adapter.py:469`. `env` is the
  whole environment — there is no inheritance behind it — so `attempt_env` is
  genuinely the only surface.
- **Evidence layout**: `transcript_dir` yields
  `<factory_root>/transcripts/<epic>/<node>/attempt-<n>/`, holding `stdout.log`
  (`STDOUT_LOG_NAME`, `:67`) and the copied session JSONL. `factory/verify/
  question.py` and `factory/activities/verify_activities.py:334` read
  `stdout.log` from that directory. None of it moves.

**Observed state of the operator's home on the worker host** (2026-08-08,
structural inspection only — no values read): `~/.claude.json` is 128,331 bytes
with top-level keys including `oauthAccount`, `userID`, `machineID`,
`customApiKeyResponses`, `mcpServers` (2 user-scope entries) and a `projects`
map; `~/.claude/` holds `CLAUDE.md`, `history.jsonl`, `projects/` (79
directories), `plugins/`, `session-env/`, `plans/`, `backups/`. This is the
surface the change removes from the child. It is *not* the surface the change
confines — see the boundary trap below.

**Storage**: one directory per node under `FACTORY_ROOT`, alongside the
worktree, the pid file and the transcripts that already live there. No store, no
schema, no state file.

**Testing**: `pytest`. US1 is unit-level against `attempt_env` and the new path
helper and needs no agent. US2 needs the stub-agent path the adapter tests
already use (`executable` is a constructor argument "for the tests' benefit —
a stub agent", `factory/workgraph/adapter.py:337-340`) plus a real `git commit`
in a fixture worktree under the child environment. US3 is a structural sweep in
the existing `tests/test_workgraph_sweep.py` idiom.

**Project Type**: single Python package. Changes are confined to
`factory/workgraph/adapter.py` (path helper, `attempt_env`, home creation and
seeding), `factory/workgraph/models.py` (one `AttemptContext` field), their
tests, and the two docs in US3.

## Constitution Check

- **I (build order)**: no component reordering; this is hardening on a landed
  component.
- **II (test-first)**: every task pairs a failing test with implementation.
- **III (dependencies)**: none added.
- **V (credentials)**: the change strengthens the principle it touches. The
  child environment stays a construction; the master key and the bot token stay
  absent by omission. The agent stops inheriting the operator's account
  credentials, which the allowlist was never written to consider.
- **VI (salvage)**: unaffected, and provably so — salvage carries its own
  identity and the worktree suite already runs on an empty `HOME`.
- **VII (persona routing)**: untouched; no model name is read or written here.

## Approach by story

### US1 — the home the factory owns (FR-001..003)

Add `home_path(factory_root, epic_id, node_id) -> Path` to the "Paths on the
worker host" block in `factory/workgraph/adapter.py`, returning
`Path(factory_root) / "homes" / epic_id / node_id` — same key as the worktree,
same neighbourhood as the transcripts. Add the resolved path to `AttemptContext`
beside `worktree_path`. Drop `"HOME"` from `PASSTHROUGH_ENV` and write it in
`attempt_env` from the context, so the child receives it as a constructed value
rather than a passed-through one. Create the directory in `run_attempt` next to
where the transcript directory and pid file are already prepared
(`factory/workgraph/adapter.py:386-389`), raising `AdapterError` naming the path
if it cannot be made.

Trap: **do not remove `HOME` from the child environment while removing it from
the passthrough tuple.** Those are two different edits and only the first is
wanted. `_archive_session` returns early on a missing home, so a child with no
`HOME` silently stops producing the session transcript, and the failure presents
as "this agent wrote no transcript" — a case the code treats as normal. The test
that catches this is an assertion on the archive's *contents*, not on the env.

Trap: `attempt_env` must not grow a `factory_root` parameter. The sweep at
`tests/test_workgraph_sweep.py:957` asserts the virtual key is read in exactly
one function, and the shape of that assertion is what keeps the credential
surface auditable. Put the resolved path on `AttemptContext` — that is what
`worktree_path` already does — so `attempt_env` keeps its two-argument signature
and its single responsibility.

Trap: key per node, not per attempt. `transcript_dir` takes `attempt` and
`pid_file` does not, for a stated reason: the pid file protects the worktree,
and there is exactly one worktree per node. The home is the same kind of thing.
A per-attempt home would also re-run whatever onboarding US2 discovers, once per
retry, which is a cost paid on exactly the attempts that are already going
badly.

### US2 — starting, committing, and being archived on it (FR-004..006)

Seed the home in the same place it is created, from module constants. T001
answered what that means, and the answer is *almost nothing*: on a bare home the
CLI started without prompting and wrote its own `.claude.json`, `plugins/`,
`projects/`, `sessions/` and `backups/`. So the only thing the factory must put
there is a git identity, and the only thing it must never put there is anything
of the operator's. Resist growing this story back to the size it looked before
the probe — an oversized story is this factory's most expensive failure mode,
and the seeding function should take no argument that could carry a path into
the operator's home.

Git identity: write `[user] name/email` into the home's `.gitconfig` from
`SALVAGE_AUTHOR_NAME`/`SALVAGE_AUTHOR_EMAIL`, imported from
`factory/workgraph/worktree.py` rather than re-declared. The agent's own commits
then carry the same attribution salvage uses, which is the honest answer: both
are the factory committing, and the constants already exist because that
question was already settled once.

Trap: **the shortcut that passes every test in this spec and undoes it.** When
the CLI will not start on a bare home, the fastest fix is to copy
`~/.claude.json` in, or to symlink a directory, or to seed from `os.environ`'s
home. Any of those restores `oauthAccount` and the whole inherited surface while
FR-001's assertions keep passing, because `HOME` would still be the factory's
path. FR-004 exists to forbid it, and US3's sweep is where it gets caught.
If the CLI genuinely cannot start without something the factory should not
fabricate, that is a blocking question for the operator (008's channel), not a
judgement call to make inside the attempt.

Trap: prove the archive composes. `_archive_session` reading the child's `HOME`
means it *should* just work, and "should just work" is how a silent evidence
loss ships. The acceptance is a completed attempt whose transcript directory
holds both files, asserted by reading the directory — not a unit test on the
path expression.

### US3 — the assertion and the boundary (FR-007..008)

Extend `test_the_virtual_key_is_read_into_exactly_one_environment_variable`
rather than working around it: it currently pins `"HOME": "/home/factory"` from
a passed-through worker value, and after this change the same assertion must
express that the home is the context's, not the environment's. Add the negative
case the sweep does not have today — build the env against a worker environment
whose `HOME` is a recognizable operator path and assert no value in the result
is under it.

Docs: `docs/architecture.md`'s adapter section gains the home; `docs/decisions.md`
gains a numbered entry claimed at landing.

Trap: **write the boundary or the entry is misleading.** Replacing `HOME`
changes what an agent loads. It does not confine what an agent can reach: there
is no filesystem sandbox, `--dangerously-skip-permissions` is unchanged, and an
agent that goes looking can still read anything the worker user can read,
including `~/.config` and the age key that decrypts the homelab secrets. That is
`hardening/agent-sandbox`'s scope and it stays open. A decision entry that reads
as "agents are now isolated" would let a future reader skip the epic that
actually isolates them.

## Complexity Tracking

None. One path helper, one dataclass field, one name moved from a passthrough
tuple to a constructed value, one seeding function, one extended sweep. No new
dependency, no store, no workflow change, no interpreter change, no change to
what any agent is asked to do.
