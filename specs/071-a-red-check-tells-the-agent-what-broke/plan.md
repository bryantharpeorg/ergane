# Implementation Plan: a red check tells the agent what broke

**Spec**: `specs/071-a-red-check-tells-the-agent-what-broke/spec.md`

## What already exists, and where

**Every line number below was verified on 2026-08-19 by printing that exact line
individually** (`sed -n '<n>p' <file>`), not by reading `grep -A` context and
counting the offset. That distinction is why this section exists: three specs
drafted six hours before this one carried anchors off by one to three lines
throughout, and a pre-dispatch review found 68 defects rated
would-cost-an-attempt. Check each one anyway before you rely on it.

**The defect, and it is two lines:**

- `factory/mergequeue/gh.py:208` — `def pr_checks(self, pr_number: int) -> tuple[PrCheckEntry, ...]:`
- `factory/mergequeue/gh.py:210` — `payload = self._run_json(`, whose arguments on
  the following line are `"pr", "checks", str(pr_number), "--json", "name,state,link"`.
  **`gh pr checks` has no `--json` flag.** This call cannot succeed anywhere.
- `factory/mergequeue/gh.py:172` — `payload = self._run_json(` inside `create_pr`,
  with **no** `--json` at all. `gh pr create` prints a URL. Same class, opposite
  spelling, equally always-fails.
- `factory/mergequeue/gh.py:373` — `def _run_json(self, *args: str) -> dict[str, Any] | list[Any]:`
- `factory/mergequeue/gh.py:376` — `payload = json.loads(result.stdout)`
- `factory/mergequeue/gh.py:378` — `raise GhError(` with `GH_REFUSED` and the
  message `f"gh {' '.join(args)} returned non-JSON output"`. This is where both
  defects surface, which is why both present as `GH_REFUSED` rather than as a
  usage error.

**The chain that already works and must not be rebuilt:**

- `factory/mergequeue/github_forge.py:211` — `def failing_check_evidence(`
- `factory/mergequeue/github_forge.py:218` — `try:` around the `pr_checks` call.
- `factory/mergequeue/github_forge.py:220-222` — the `except GhError` that returns
  one empty `CheckFailure` per name with the note
  `log unavailable: could not list checks ({error.kind})`. **This is the honest
  degradation that hid the defect.** Keep it; it is FR-003.
- `factory/mergequeue/github_forge.py:234` — `run_id = _parse_run_id(entry.link)`,
  and `:243` — the per-check `except GhError`. This per-check structure is FR-005
  and already correct.
- `factory/activities/merge_activities.py:497` — `async def fetch_check_failure(...)`,
  and `:509` — `return forge.failing_check_evidence(request.pr_number, request.check_names)`.
- `factory/workgraph/workflow.py:2360` — `failing_checks: tuple[CheckFailure, ...] = ()`
- `factory/workgraph/workflow.py:2361` — `if sync.clean and last == QueueOutcome.CHECKS_FAILED:`
  **Read this gate.** Evidence is fetched only on a CLEAN sync after
  `CHECKS_FAILED`. A conflicted sync routes to the debugger with conflicted files
  instead, which is a different and working path. Do not widen this.
- `factory/workgraph/prompt.py:622` — `if evidence.failing_checks:`, `:623-624`
  the rendering loop. This produced the correct section on the night; the section
  was correct and empty.

**The tests, and why they did not catch it:**

- `tests/test_gh_client.py:233` — `def test_pr_checks_parses_name_state_and_link()`.
  It is a good test. It passes. It asserts the argv is exactly
  `("pr","checks","7","--json","name,state,link")` — the argv that cannot run.
  `FakeGh` answers whatever it is scripted to answer, so the test pins the defect
  in place rather than catching it. **Read this test before you touch anything:
  fixing `pr_checks` makes it fail, and updating it is part of the work, not a
  regression.**
- `tests/test_gh_client.py:102` — `def test_create_pr_uses_base_head_title_and_body_file_never_draft()`,
  the same shape for the second defect.
- `tests/fake_gh.py` — the fake. US1-S1 asks for a fake that refuses argv the real
  `gh` would refuse; decide deliberately whether that belongs in `FakeGh` itself
  (every existing test then inherits it, which is the point) or in a new fake.
  Changing `FakeGh` will move other tests. That is a feature, but budget for it.

**The proven remedy, run end to end by hand on 2026-08-19 against PR #226:**

```
$ gh pr view 226 --json statusCheckRollup \
    --jq '.statusCheckRollup[] | {name, state:(.conclusion//.state), link:(.detailsUrl//.link)}'
{"link":"https://github.com/bryantharpeorg/ergane/actions/runs/32308139069/job/96245263389",
 "name":"test","state":"FAILURE"}

$ python -c "from factory.mergequeue.github_forge import _parse_run_id; print(_parse_run_id(LINK))"
32308139069

$ gh run view 32308139069 --log-failed | tail -3
... FAILED tests/test_ergane_init_creates_specs.py::test_init_creates_specs_directory
    - subprocess.CalledProcessError: ... 'commit' ... exit status 128.
    1 failed, 3693 passed, 64 skipped in 380.15s
```

`_parse_run_id` handles the `detailsUrl` shape unchanged — verified by calling it
on that exact string. `run_failed_log` is untouched. **The change is one command.**

## Traps

**1. Do not rebuild 025.** The single largest way to lose this attempt is to read
"the CI log never reaches the agent" and start building evidence carrying. It is
built. The activity, the workflow fetch, `LandingEvidence.failing_checks`, the
prompt render and FR-013's `base_unmoved` all work and all fired correctly on the
night this was found. Your diff should touch `gh.py`, `github_forge.py`, and
tests. If it is editing `prompt.py` or `workflow.py`, stop and re-read this.

**2. `statusCheckRollup` entries are not uniform.** A check run carries
`conclusion` and `detailsUrl`; a commit status carries `state` and `targetUrl`;
required checks that never started may carry neither. Handle the shapes you find
rather than the one shape you saw in an example, and let an unrecognised entry
degrade per-check (FR-005) instead of failing the batch. Get the real payload for
a PR with a mixed rollup before you decide the mapping.

**3. Keep the degradation.** FR-003 and US1-S3. The temptation on discovering
that a fallback fired every time is to delete the fallback. `failing_check_evidence`
must still return a named note when the forge genuinely fails; a raise here turns
a slow network into a dead node. The control test is what proves you kept it.

**4. `_run_json` is not the villain.** It correctly reports that it got non-JSON.
Both defects are callers that ask it for JSON from commands that do not emit
JSON. Do not "fix" `_run_json` to tolerate non-JSON — that would convert two loud
failures into silence everywhere it is used, including the calls that are
correct. `find_existing_pr` (`gh pr list --json`) and `poll_pr` (`gh pr view
--json`) are correct today; `gh pr list` and `gh pr view` both support `--json`,
verified.

**5. The mutation control is the story, not decoration.** US2-S2 and SC-006. This
entire defect existed because a well-written test passed against a fake. A check
that has never been watched fail proves nothing about the next malformed argv. If
you write the argv check and cannot make it go red on purpose, you have written
the same class of test again.

**6. Enumerate the methods; do not list them.** US2-S1. A hand-written list of
commands is a list that goes stale the first time someone adds a method — which
is precisely how this arrived. Derive the set from the class.

**7. No network, no token, no repository.** FR-007. `gh` rejects unknown flags
during argument parsing, before it authenticates or resolves a repository, so
`gh pr checks 1 --json x` fails on the flag alone in a directory that is not a
git repository with no `GH_TOKEN` set. Prove that (SC-007) rather than assuming
it, because the whole affordability of the check rests on it.

**8. Guard, do not mark.** US2-S6, and the open finding
`live-tier-skips-by-guard-not-marker`: nothing in this repository passes `-m` in
CI or in the gate, so a `pytest.mark` is decorative and a marked test is an unrun
test. If `gh` may be absent, skip on a real condition checked at runtime.

**9. `create_pr` is in scope here and only here.** It is a separately filed open
finding, and ordinarily out of scope — but US2's own check goes red on it, and a
story that lands a new red test has not landed. Fix it as part of US2. `gh pr
create` prints the URL on stdout; the number can be derived from that URL, or
`find_existing_pr(head)` can be called immediately after. Choose one and say why
in the diff.

**10. The two stories share `factory/mergequeue/gh.py`.** The declared
`depends_on_merged` edge is what keeps them from racing. Do not treat them as
concurrent because their subject matter differs; the file is what collides. If
you are US2 and `gh.py` does not look as the plan describes, US1 has landed and
you should re-read it rather than assume.

**11. The judge sees the diff and the criteria, nothing else.** Constitution
Principle VIII. SC-001 through SC-007 all require committed, pasted output. A
terminal you ran and did not commit did not happen. Redact nothing here — none of
this output carries a secret — but do check, because `gh` can echo a token in an
error.

**12. One test file per story.**
- US1 → `tests/test_check_evidence_reaches_the_agent.py`
- US2 → `tests/test_gh_argv_contract.py`
Both stories will also edit `tests/test_gh_client.py`, which is unavoidable —
US1's fix breaks the test at `:233` and US2's breaks the one at `:102`. That
shared edit is the reason for the merge edge; make the edit minimal and confined
to the assertion that names the argv.

## Sizing

**US1 is small — perhaps fifteen lines of production code.** One `gh` invocation
replaced, one payload mapping, and the existing per-check loop left alone. Its
risk is entirely trap 1 (rebuilding 025) and trap 2 (the rollup's shapes). The
remedy is already proven end to end by hand, which is the least uncertain a story
in this repository has been in some time.

**US2 is medium and its value is greater than US1's.** The check itself is short.
What makes it medium is enumerating the command surface honestly, making the
mutation control real, and fixing `create_pr` when the check finds it.

**Neither story should need a second attempt.** If either does, the most likely
cause is trap 1 for US1 and trap 5 for US2.

## Verification the operator will run, independent of the gate

- **Take a real red pull request and read the assembled prompt.** Not the record,
  not the test — the prompt string the agent would receive. That is the only
  measurement that would have caught this defect, and it is the one nobody ran
  for the life of the feature.
- **Watch the argv check fail on purpose.** Add a flag `gh` does not have, run it,
  see it red, remove it. A green run of a new check proves the check ran, not
  that it works.
- **Run the argv check with `GH_TOKEN` unset, in `/tmp`.** If it needs a token or
  a repository it will be skipped in CI and this whole story bought nothing.
- **Count the degraded path.** After FR-004 lands, cause one real forge failure
  and confirm it is visible without opening a transcript.
