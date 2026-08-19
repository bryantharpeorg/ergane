# Implementation Plan: an agent can start on any host

**Spec**: `specs/067-an-agent-can-start-on-any-host/spec.md`

## What already exists, and where

Every line below was read on 2026-08-19. Check each against the tree before you
rely on it — 060 proved that a plan citing a moved anchor costs the attempt.

**US1 — the two mount sets:**

- `factory/workgraph/adapter.py:427-431` — the agent boundary's system tree. The
  comment at `:427-428` reads `# Minimal system tree: read-only /usr plus the
  symlinks Ubuntu uses` / `# on aarch64. No /lib64 on this host.` **That comment
  is the defect's documentation. Delete it; do not preserve it.**
- `factory/verify/gates.py:586-590` — the gate boundary's system tree, inside
  `_build_argv` (`:579`). Byte-identical to the above including the comment.
- `factory/workgraph/adapter.py:318` — a second copy of the same claim in prose,
  in a docstring: "there is no `/lib64` on this aarch64 host." Also stale.
- `factory/verify/toolchain.py:1-30` — **read this docstring before writing any
  code.** It states the rule this story applies, and states it about this exact
  failure mode: literals that "carried two things that are not facts about
  software, only facts about one machine on one afternoon." It also establishes
  the refusal contract US1-S6 wants: `ToolchainError` raised *before* the
  sandbox forks, naming the tool and where it looked.
- `factory/workgraph/adapter.py:432-436` and `factory/verify/gates.py:591-595` —
  the pseudo-filesystem entries (`--proc`, `--dev`, `--tmpfs`) immediately after.
  Those are genuinely host-independent. Leave them alone.
- `ordered_binds` — referenced from both files, emits binds shallowest-first.
  The system-tree entries are `--symlink` and `--ro-bind` emitted directly into
  `argv` *before* `binds` is collected. Keep that ordering: a symlink emitted
  after a bind that covers its path is a different bug.

**US2 — the ladder:**

- `factory/verify/ladder.py:122-130` — `_attempts_spent`, which counts every
  record whose `persona` is not `DEBUGGER_PERSONA`. This is where a launch
  failure gets charged.
- `factory/verify/ladder.py:63-97` — `next_action`. Note `allowed =
  config.max_attempts + len(escalations)` at `:88`.
- `factory/verify/models.py:645-647` — `max_attempts: int = 3`,
  `max_judge_retries: int = 2`, `debugger_cycles: int = 1`.
- `factory/workgraph/adapter.py` — where the sandbox is forked and its failure
  becomes a result. Find the actual fork site rather than assuming; the argv
  builder and the launcher are not the same function.

**US3 — the compiled artifact:**

- `factory/workgraph/cli.py` and `factory/cli/nouns/spec.py` — the two derive
  entry points. `specs_root` is written into the artifact by whichever one the
  operator used; both must resolve.
- `target_repo` is already an absolute worker-host path in practice. Confirm
  before claiming it in a test — the spec asserts it *should* be, not that it is.

## Traps

**1. A test asserting a `/lib64` literal is architecture-dependent and will lie.**
This host is aarch64 and has no `/lib64`. A test asserting the argv contains
`/lib64` fails here; one asserting it does not fails on the machine the defect
was reported from. **Every assertion must be against a SUPPLIED layout** — a
fake root, a tmp tree, or an injected seam — asserting the argv *follows what it
was given*. US1-S1 and US1-S2 are written that way deliberately. If your test
reads the real `/`, it is testing this machine, which is how the bug shipped.

**2. Do not fix this by adding `/lib64` to the literal list.** That is the same
defect with a wider constant, and it breaks the un-merged-`/usr` host in the
opposite direction — binding a path that is not there is `bwrap: Can't find
source path`, from a process that already forked. US1-S2 exists to catch exactly
that over-correction. Read the host.

**3. One implementation, two callers.** FR-003. The two boundaries drifted into
identical wrongness because they are two copies. If your diff leaves two
derivations, you have reproduced the cause while fixing the symptom.

**4. Delete the stale comment and the stale docstring sentence.** Both
`adapter.py:427-428` and `gates.py:586-587`, plus the prose at `adapter.py:318`.
A comment asserting a fact about one host is what made this invisible for
months; leaving it above corrected code is worse than leaving it above broken
code.

**5. "Did the agent start" is the distinction, not "did it fail early".** US2-S4.
An agent that emitted one token and then died IS an attempt. A fix keyed on
elapsed time, exit code, or transcript size below some threshold will
mis-classify real failures and stop charging them, which silently doubles every
node's budget. Key it on whether the agent process was ever entered.

**6. An unbudgeted retry path needs its own bound.** US2-S5. Moving launch
failures off the attempt budget without a separate limit converts a bounded
expensive failure into an unbounded free one. That is a worse outage, and it is
the failure mode a reviewer will look for first.

**7. Determinism, if you touch workflow code.** The ladder is called from
workflow code (`factory/workgraph/workflow.py:1436`). No clocks, no environment
reads, no filesystem there. Host discovery for US1 happens in the sandbox
builder, which runs in an activity — that is where the filesystem read belongs,
and it must not migrate into the workflow.

**8. US3 refuses at read time as well as resolving at write time.** FR-008 and
FR-009 are two halves and a diff with only the first passes the easy scenario
and leaves every already-written artifact broken silently.

**9. One test file per story, named here.**
- US1 → `tests/test_sandbox_mount_set.py`
- US2 → `tests/test_launch_is_not_an_attempt.py`
- US3 → `tests/test_graph_paths_are_absolute.py`
If you need a file assigned to another story, the edge declaration is wrong —
say so rather than editing across the line. 060 shared a test file between two
stories that declared themselves disjoint and only landing order saved it.

**10. The judge sees the diff and the criteria, nothing else.** SC-001 through
SC-005 all require committed output. Paste the argvs, the counts and the command
output into the diff. A description of what you observed is not evidence of it.

**11. You cannot test this on the architecture that has the bug.** No x86_64 host
is available. That is not a reason to skip proof — it is the reason trap 1 is
trap 1. The supplied-layout test is *stronger* than a real-host test would be,
because it exercises both branches on any machine. Say so in the commit rather
than apologising for the absence.

## Sizing

Three small, fully independent stories.

US1 is a loop over four paths and a shared helper, plus deleting two comments.
The production change is perhaps thirty lines. Its entire difficulty is trap 1.

US2 is a classification and a counter change. Its difficulty is trap 5 — getting
"did the agent start" onto a signal that is actually available at that point in
the code, rather than onto a proxy.

US3 is two `Path.resolve()` calls and a validation. The smallest story in the set.

## Verification the operator will run, independent of the gate

- **Prove US1 by control.** Build both argvs against a layout with `/lib64` and
  one without, and diff them. They must differ by exactly that entry. Then remove
  the host-derivation and confirm the tests fail.
- **Prove US2 by control.** Fail a launch before output; assert the count did not
  move. Then let an agent start and fail; assert it did. One without the other
  proves nothing.
- **Prove US3 end to end.** Derive from a directory other than the repository
  root with a relative specs root, then dispatch from a third directory.
