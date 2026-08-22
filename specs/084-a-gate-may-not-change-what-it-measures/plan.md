# Implementation Plan: a gate may not change what it measures

**Spec**: `specs/084-a-gate-may-not-change-what-it-measures/spec.md`

## What already exists, and where

**Every line number below was verified on 2026-08-21 by printing that exact line
individually** (`sed -n '<n>p' <file>`). Check each one anyway.

**The names are already decided.** The spec's "The names, ruled here so three
stories cannot disagree" fixes `GateResult.worktree_writes` (the paths),
`GateResult.writes_declared` (the manifest said so) and the manifest key
`writes:` — a top-level mapping from gate name to boolean. Three attempts touch
these and none of them sees the other two, so they are not yours to rename. Use
them exactly.

**The ordering that is the defect — `factory/workgraph/workflow.py`:**

- `:2114` — `gate_results = await workflow.execute_activity(`
- `:2116` — `RunGatesInput(worktree_path=prepared.path),`
- `:2122` — `output = await workflow.execute_activity(`
- `:2125` — `worktree_path=prepared.path,` — the same worktree the gates just ran in
- `:2129` — `base_ref=prepared.base_ref,`

Gates, then the diff, in one worktree, in that order. You are not changing this
ordering; you are making the first half report what it did to the second half's
subject.

**The gate runner — `factory/verify/gates.py`, 1363 lines:**

- `:1085` — `def run_gates(`. `:1094-1098` is the contract that constrains this
  spec: "One result per declared gate — a failure or a timeout never cancels the
  gates after it, because the contract promises the caller a complete picture."
- `:1119` — `worktree = Path(worktree)`; `:1126` — `backend = _resolve_gate_executor(`.
- `:1143` — `if isinstance(interpreted, _AcceptedConfig):` → `:1146` returns
  `_run_gate_list(...)`. `:1189` — `return _run_gate_list_from_config(` is the
  other exit. **Which one a repo takes is decided at `:1135` —
  `if candidate_path.exists():`, over the path built at `:1130`
  (`candidate_path = worktree / "factory" / "verify" / "factory_yaml.py"`)** — so
  Ergane's own nodes take `_run_gate_list` and every other target repo takes
  `_run_gate_list_from_config`. The field report came from the second path;
  your tests will run on the first. Neither is hypothetical.
- `:1244` — `def _run_gate_list(`. Its loop: `:1265` `for name, command in
  gates_view.items():`, `:1273` `peers = limiter.acquire()`, `:1275`
  `outcome = backend.run(invocation)`, `:1277` `limiter.release()`, `:1278`
  `results.append(_to_result(invocation, outcome, peers))`.
- `:1282` — `def _run_gate_list_from_config(`, the near-identical twin: `:1301`
  `for name, command in config.gates.items():`, `:1311` the same
  `backend.run(invocation)`, `:1314` the same `_to_result` append.
- `:1332` — `def _to_result(`. `:1348-1353` is the status mapping (`timed_out` →
  TIMEOUT/None, `exit_code == 0` → PASS/0, else FAIL/exit_code) and `:1355-1363`
  builds the `GateResult`, `concurrent_gates` included.
- `:1106-1109` — the limiter's docstring: a gate's "wall-clock bound measures the
  gate's own work and never the queue it waited in". Read it before you decide
  where the snapshots go.
- `:397` `class SubprocessGateExecutor:` / `:411` its `run`; `:490`
  `class BwrapGateExecutor:` / `:516` its `run`; `:595` `_build_argv`.
- `:628-630` — the bind decision: parent read-only, `binds.append(("--bind",
  str(worktree), str(worktree)))` for the leaf. Writable on purpose.
- `:318` — `def scrubbed_env(` — the env every gate subprocess gets, and the
  reason `factory.workgraph.worktree` imports this module (see trap 4).

**The result model — `factory/verify/models.py`:**

- `:70` `class GateStatus(StrEnum):`, `:78-81` its four members, and `:73-75` the
  reasoning you are following: `CONFIG_ERROR` "is a status rather than a raised
  error so it flows through the verdict truth table and fails the verification —
  never pass-by-default."
- `:277` `class GateResult:`; fields at `:295-300`; `:301`
  `concurrent_gates: int = 0` — **the worked example for adding a field without
  breaking a caller**, argued at `:285-292`.
- `:478` `def gates_passed(` and `:490-492` — `bool(gate_results) and all(gate.status
  == GateStatus.PASS ...)`. Any status that is not PASS already fails here, which
  is why FR-004 needs no edit to this function.
- `:505` `def judge_required(`, `:526` `def compose_result(` — downstream, untouched.

**That last claim was re-verified by a second reader on 2026-08-21**, on the
cross-spec critic pass, against the same tree. It is load-bearing for FR-004 and
cheap to doubt, so it has now been read out of the tree twice, independently:
`gates_passed` (`factory/verify/models.py:478-492`) refuses any status that is
not PASS, and `judge_required` (`factory/verify/models.py:505-524`) is built on
`gates_passed` at `factory/verify/models.py:520` and therefore inherits the
refusal. A new non-PASS `GateStatus` member needs no downstream edit at all.
- `:308` `class HygieneViolation:` (`:319` `path: str`, `:320` `rule: str`) and
  `:393` its list field. Read them, then leave them alone — the spec rules this
  is not that shape.

**The evidence codec — `factory/verify/store.py`:**

- `:668` `def _gate_to_dict(gate: GateResult) -> dict[str, Any]:` with `:676`
  `"concurrent_gates": gate.concurrent_gates,`
- `:680` `def _gate_from_dict(data: dict[str, Any]) -> GateResult:` with `:691`
  `concurrent_gates=data.get("concurrent_gates", 0),` — the absent-means-default
  read, comment included.

**The two renderers — US2's whole surface:**

- `factory/workgraph/prompt.py:678` `def _attempt_block(`, and `:693-695`:
  `for gate in result.gate_results:` / `if gate.status is GateStatus.PASS:` /
  `continue`. `:722-724` records what a silent failure cost last time.
- `factory/notify/messages.py:410` `def _gate_line(`, `:417-418` the contention
  marker rendered for the operator.

**The measurement's precedent — `factory/workgraph/worktree.py`:**

- `:996` `def diff(worktree, *, base_ref, limit=DIFF_READ_LIMIT) -> str:`
- `:1006-1007` — "ignored files stay out, so a target repo's `.gitignore` is what
  keeps generated noise from reaching the judge." **This sentence is FR-002.**
- `:1021` `with tempfile.TemporaryDirectory(prefix="ergane-diff-") as scratch:`,
  `:1025` `index = {"GIT_INDEX_FILE": str(Path(scratch) / "index")}`, `:1026`
  `_git(path, "add", "-A", env_extra=index)` — the scratch-index mechanism to
  copy.
- `:1042` `def trees_identical(` — comparing by tree id rather than by sha, the
  precedent for the comparison itself.

**The diff check, for the boundary you must not cross:**

- `factory/verify/diffcheck.py:156` `def check_output(` and `:171-176` — "the
  moment two places can decide a FAIL, the stored row and the retry prompt can
  disagree."
- `factory/verify/diffcheck.py:340` `def _changed_paths(` and
  `factory/verify/diffcheck.py:358` — `status = _git(worktree, "status",
  "--porcelain", "-z", "--untracked-files=all")`. Note what it does *not* pass.

**The manifest parser — US3's surface, `factory/verify/factory_yaml.py`:**

- `:86` `KNOWN_GATES = ("test", "lint", "typecheck")`
- `:103` `_TOP_LEVEL_KEYS = (` through `:112` — the eight keys v1 knows.
- `:115` `_V2_TOP_LEVEL_KEYS = _TOP_LEVEL_KEYS + ("ladder", "verify")` — **v2 is
  derived from v1's tuple, so adding your key at `:103-112` teaches both schemas
  and there is no second list to hunt for.**
- `:192` `_reject_unknown_keys(document, source, version)` and `:195`
  `timeouts = _read_timeouts(document, gates, source)` — the one load path, run
  for both versions. Your reader goes on the line after `:195`.
- `:242` `def _reject_unknown_keys(` and `:244` `unknown = [key for key in document
  if key not in known]` — an unrecognised key is a manifest error, not a warning.
- `:370` `def _read_timeouts(` — **the per-gate sibling-mapping precedent FR-009
  follows** — and `:386-393` (`for name, seconds in timeouts.items():` /
  `if name not in gates:` → `FactoryConfigError`) is **exactly** the unknown-gate
  refusal FR-011 asks for, message shape included.
- `:819` `def config_error_result(error: FactoryConfigError) -> GateResult:`,
  built at `:827-834` — how a manifest problem becomes a `GateResult`.
- `:856` `def _main(argv: list[str]) -> int:` and `:879`
  `print(json.dumps(dataclasses.asdict(config)))` — the candidate protocol's
  emitting half. A new `FactoryConfig` field is emitted here for free; nothing
  *reads* it for free (trap 16).

## Traps

**1. The check observes; it does not prevent.** `factory/verify/gates.py:630`
binds the node worktree writable deliberately, reason in the comment at
`:625-627`. Do not make it read-only. Neither reporter asked for prevention, and
prevention breaks every gate that writes a scratch file.

**2. Both gate-list runners, or the check is bypassable.**
`factory/verify/gates.py:1244` `_run_gate_list` and `:1282`
`_run_gate_list_from_config` are near-identical twins. Ergane's own nodes take
the first and every other target repo takes the second, so a check added to only
one is a check that works in your tests and not in the field — which is the exact
shape of the defect being closed.

**3. Both executors — free, if you put the check in the right place.** The
snapshot belongs around `backend.run(invocation)` —
`factory/verify/gates.py:1275` and `:1311` — which is the one line
`SubprocessGateExecutor` (`factory/verify/gates.py:397`) and `BwrapGateExecutor`
(`factory/verify/gates.py:490`) both pass through. A check written inside either
executor misses the other, and a check inside the bwrap container cannot see the
host's git at all.

**4. `factory/verify/gates.py` cannot import `factory.workgraph.worktree`.**
`factory/workgraph/worktree.py:88` is `from factory.verify.gates import
scrubbed_env`. The cycle is real and it will bite at import time, not at test
time. Copy the mechanism from `worktree.diff`
(`factory/workgraph/worktree.py:1021-1026`); do not copy the import. If the
helper wants a home, a new leaf module under `factory/verify/` that imports
nothing from `factory.workgraph` is the shape.

**5. `git status --porcelain` is not enough, and this is measured, not
asserted.** A gate that rewrites a file the agent had already modified produces
a byte-identical porcelain line before and after. A scratch-index tree hash sees
it. Probe run 2026-08-21 against a throwaway repo whose `.gitignore` names
`__pycache__/`:

```
base:            41550e0d1d1561a567c2386cd66050500e0771bb
after ignored:   41550e0d1d1561a567c2386cd66050500e0771bb   <- unchanged
after untracked: 23a425340c976150f9fbe57c2299ac764bb67e08
git diff-tree -r --name-only <base> <after>  ->  untracked_new.txt
```

`git add -A` into a throwaway `GIT_INDEX_FILE`, then `git write-tree`; compare
ids, and name the paths with `git diff-tree -r --name-only`.

**6. Ignored paths are out, and that is the ruling.** This repository's own gate
is `uv run pytest -q` (`factory.yaml`), and `.gitignore` names `__pycache__/`,
`*.pyc` and `.pytest_cache/`. A check that counted ignored paths would fail
every gate run Ergane has ever made, starting with the one verifying this story.
The justification is not convenience: `factory/workgraph/worktree.py:1006-1007`
says ignored files never reach the judge, so a gate that writes one cannot have
changed what the judge scores — and an ignored path that is force-added anyway is
already refused by `hygiene_violations` (`factory/verify/diffcheck.py:262-290`).

**7. A PASS-status gate is invisible to the next attempt.**
`factory/workgraph/prompt.py:694-695` `continue`s past every PASS. This is why
the spec rules that a dirtied gate is reported with a status that is not PASS,
rather than as a quiet boolean on a PASS row. Get this wrong and the node fails
with nothing in its prompt — the `033-ergane-install/us2` shape recorded at
`factory/workgraph/prompt.py:722-724`, four attempts on a byte-identical mystery.

**8. A new `GateResult` field has four homes, and `concurrent_gates` visited all
of them.** `factory/verify/models.py:301` (the field),
`factory/verify/gates.py:1355-1363` (`_to_result`), `factory/verify/store.py:676`
and `:691` (both codec halves, the read defaulted),
`factory/notify/messages.py:417-418` (the operator's line). A field that skips
the codec is lost the moment the row is stored and re-read, and the retry prompt
is built from stored evidence.

**9. `run_gates` never raises, and returns one result per declared gate.**
`factory/verify/gates.py:1094-1098`. An unreadable snapshot must become evidence
on a result, never an exception — the `CONFIG_ERROR` reasoning at
`factory/verify/models.py:73-75`. And a dirtied gate must not stop the loop.

**10. Keep the snapshot out of `duration_s` and out of the limiter's slot.**
`duration_s` comes from the executor's `ExecutionOutcome` and must keep measuring
the gate's command. Holding a host-wide limiter slot for a tree walk contradicts
`factory/verify/gates.py:1106-1109` directly. N gates need N+1 snapshots, not
2N: the "after" of gate k is the "before" of gate k+1.

**11. Do not add the new manifest key to this repository's `factory.yaml`.** The
config gate parses a node's manifest with the **worker's installed** parser, not
the worktree's, so a story that declares a brand-new key in its own manifest is
`CONFIG_ERROR` in 0.0s before any gate command runs. `factory.yaml`'s own
comment records 020/US1 dying four times proving it — `factory.yaml:38-42`.
Teach the parser (`factory/verify/factory_yaml.py:103-112`, `:242-244`, `:370`,
`:386-393`) and prove it with a fixture manifest under `tests/`.

**12. One decider per half.** `factory/verify/diffcheck.py:171-176`. The gate
half is decided by `gates_passed` (`factory/verify/models.py:478-492`); do not
teach `check_output` about gates, and do not add a second `passed` flag
anywhere.

**13. The adjacent finding is not scope.**
`verify/a-warm-pycache-suppresses-compile-time-warnings-so-warning-counts-are-not-comparable`
is the same surface with a different consequence. Leave it open.

**14. The judge sees the diff and the criteria, nothing else** (Constitution
Principle VIII). Every SC needs committed, pasted output. SC-002 and SC-003 in
particular are *comparisons* — both sides have to be in the diff or the
criterion is unprovable.

**15. One test file per story.**
- US1 → `tests/test_a_gate_that_writes_does_not_pass.py`
- US2 → `tests/test_the_next_attempt_is_told_what_the_gate_wrote.py`
- US3 → `tests/test_a_gate_may_declare_that_it_writes.py`

**16. US3's `writes:` key does not reach `_run_gate_list` by itself — trap 2
wearing a US3 hat, and this one is measured rather than warned about. It is now
also US3-S3, FR-012 and SC-011, so a story that skips it fails its own
criteria.**
`_run_gate_list_from_config` is handed the whole `FactoryConfig`
(`factory/verify/gates.py:1189-1195`), so a new field arrives there for free.
`_run_gate_list` is not. It is handed only `gates_view` and `timeouts_view`
(`factory/verify/gates.py:1144-1150`), lifted off `_AcceptedConfig`, whose
payload is two fields. `factory/verify/gates.py:181-186` declares three, but one
is the `kind: str = "accepted"` discriminator (`factory/verify/gates.py:184`),
leaving `gates: dict[str, str] | None` (`:185`) and
`timeouts: dict[str, int] | None` (`:186`) as everything the runner consumes —
populated
by `_interpret_candidate`, which reads exactly two keys out of the protocol
JSON: `factory/verify/gates.py:947-948` (`gates_view = document.get("gates")`,
`timeouts_view = document.get("timeouts", {})`), returned at
`factory/verify/gates.py:966-969`. So FR-009's declaration has to be carried
through **four** further sites — `_AcceptedConfig`
(`factory/verify/gates.py:181-186`), `_interpret_candidate`
(`factory/verify/gates.py:947-948` and `:966-969`), the `_run_gate_list(...)`
call at `factory/verify/gates.py:1146-1154`, and `_run_gate_list`'s own
signature at `factory/verify/gates.py:1244` — or it is dropped on the candidate
path in silence. That is the path Ergane's own nodes take, which makes it the
path US3's own verification runs on: get this wrong and a gate you declared as a
legitimate writer is still refused, on your own node, with a manifest that looks
correct. The emitting half needs no work —
`factory/verify/factory_yaml.py:879` is
`print(json.dumps(dataclasses.asdict(config)))`, so a `writes` field added to
`FactoryConfig` (`factory/verify/models.py:230`, beside `timeouts` at
`factory/verify/models.py:250`) is already in the JSON nobody is reading. Parsed,
stored, emitted, never read — which is precisely why US3 could otherwise have
gone green with the feature dead on Ergane's own runner. That failure shape is
filed as `verify/readiness-proves-a-thing-is-declared-not-that-it-works` and this
repository has filed it five times.

**17. SC-002's control is a fixture gate, not this repository's suite.** Read
literally, "this repository's own gate command, `uv run pytest -q`, run through
the new check" asks for the full suite invoked as a gate, inside a gate run,
inside the node's own gate run. Do not build that. This host has already been
OOM-killed by orphaned test servers from a single run
(`hardening/orphaned-test-servers-exhaust-host-memory`). Write a fixture gate
that produces the same ignored paths — `__pycache__/` and `.pytest_cache/` —
into a fixture repo whose `.gitignore` names them. The real suite control is the
operator's, out of band, and it is in the verification list at the foot of this
plan.

**18. The bwrap half of SC-004 may be a named skip, and a stub executor is what
carries the proof.** `BwrapGateExecutor` (`factory/verify/gates.py:490`) needs a
working `/usr/bin/bwrap` and namespace creation. The node agent is itself
sandboxed, so you may not have it — and a bare `SKIPPED` in a diff does not read
to a judge as evidence. Guard the bwrap case the way this repository already
guards every bwrap test — `_bwrap_available()` at
`tests/test_us4_boundary.py:165`, the early-return shape at
`tests/test_us4_boundary.py:208`, `:264` and `:321`, sixteen such skips recorded
at `tests/test_sandbox_mount_set.py:156` — and paste the skip line *with the
guard quoted beside it*. Then add a third executor: a stub implementing the
`GateExecutor` seam and neither shipped class. The stub runs on every host and it
proves what the criterion is actually for — that the check sits at
`backend.run(invocation)` (`factory/verify/gates.py:1275` and
`factory/verify/gates.py:1311`) rather than inside any executor. That is trap 3,
made provable on a host that cannot run bwrap.

## Sizing

**US1 is large — the largest of the three by some distance.** A snapshot helper
that cannot import the module it is copied from, two loops, one status, one
field, two codec halves, and eight scenarios of which three are controls. Split
it further only if you must; the pieces are not independently useful.

**US2 is small.** Two renderers, three tests, no new data.

**US3 is medium, and larger than it reads.** A schema key, its refusal path, the
candidate-protocol pass-through, the runner honouring it, and the evidence
recording it. Two of those are traps rather than lines of work: trap 11 turns a
careless manifest edit into an instant `CONFIG_ERROR`, and trap 16 is four
pass-through sites without which the key never reaches the runner your own node
uses. Those four sites are now scored: US3-S3, FR-012 and SC-011 exist precisely
so this story cannot go green without them.

**The most likely cause of a second attempt is trap 3 or trap 6.** Trap 3
because putting the check inside an executor looks natural and passes its own
test; trap 6 because a check that counts ignored paths turns this repository's
own gate red and reads, to the agent, as its own code being broken.

## What else is in flight, and why none of it collides

Checked 2026-08-21 on the cross-spec critic pass, which read 083 and 085 beside
this one: none of `factory/verify/gates.py`, `factory/verify/models.py`,
`factory/verify/store.py`, `factory/verify/factory_yaml.py`,
`factory/workgraph/prompt.py` or `factory/notify/messages.py` — this spec's whole
edit surface — is an edit target in either of those specs. 084 may dispatch
alongside either without file contention. The contention that does exist is
internal and already expressed in the Work Graph: US2 and US3 both merge-depend
on US1, and share no file with each other.

## Verification the operator will run, independent of the gate

- **Add a `compileall` gate to a throwaway target repo with no `__pycache__`
  ignore rule, and run a node against it.** That is the field report, reproduced
  exactly, and the run must fail naming the `.pyc` files.
- **Run an ordinary Ergane epic with no manifest change at all** and confirm
  `uv run pytest -q` still passes. The control, and the one that says whether
  this landed or bricked the floor.
- **Add a `sed -i` gate that rewrites a source file the agent touched** and
  confirm the refusal names it — the case the whole CRITICAL severity rests on.
- **Declare that gate's writes in the manifest** and confirm it passes with the
  paths still visible in the evidence.
