# Implementation Plan: the on-ramp proves itself end to end

**Spec**: `specs/061-the-on-ramp-proves-itself-end-to-end/spec.md`

## What already exists, and where

- `factory/controlplane/verify.py:296` — `LLMProbe.gather`, which POSTs a
  one-token chat completion per distinct alias at :355. That is the whole probe.
  US1 extends it; it does not replace it. The per-distinct-alias behaviour is
  054/US3's work and must survive.
- `factory/discovery/llm_scanner.py:130–145` — the classification US1 must reuse.
  `EndpointClassification.DISPATCHABLE` when "/v1/models and /key/generate both
  answer"; `INFERENCE_ONLY` when the key-management API does not. 055 built this.
  Import it. Do not write a second one.
- `factory/usage/litellm_client.py` — `issue_key`, `revoke_key_by_tokens`, and
  the `/key/info` and `/spend/logs/v2` readers. 064/US3 has landed: `revoke_key`
  is now defined once, at :246, delegating to `revoke_key_by_tokens`.
- `factory/roadmap/models.py:398` — `read_roadmap`'s `root.iterdir()`. Its
  docstring at :378 commits to raising and yielding no partial roadmap on a
  corpus with any finding. US2 must not weaken that.
- `factory/cli/init.py:816` — `runtime_root.mkdir(exist_ok=True)`, where `specs/`
  creation belongs.
- `factory/cli/init.py:398` — `_PLACEHOLDERS`, whose comment already calls these
  placeholders, and which still declares `"gates": {"test": "true"}`. US3-S5
  makes the placeholder stop escaping. (Anchor re-verified 2026-08-21; 064/US2's
  landed edits moved it from :273.)
- `factory/mergequeue/onboard.py:258` — `_gate_check_finding`, which emits
  `required check '{gate}' exists` at :261. That is the line US3 changes.
  `factory/mergequeue/onboard.py:29` documents the `gate_check:<gate>` contract;
  update it in the same diff.
- 033's scripted-prompter walkthrough harness and 054/US2's injected host-probe
  seam are the models for US4's staging.

## Traps

These are named hazards, not advice. Trap 1 is the reason this spec exists.

**1. This entire spec is about the difference between asserting a declaration
and asserting a capability. Do not write presence tests for it.** The failure
mode is seductive because presence tests are what a diff can cheaply show. A test
asserting "the probe calls `/key/generate`" is the same class of check that
produced the bug it is fixing. Assert the *verdict changes* between a simulated
dispatchable endpoint and a simulated inference-only one. If your test would
still pass with the probe's return value hardcoded, you have written the defect
again.

**2. A probe that fails everything is not an improvement on one that passes
everything.** US1-S2 and US2-S2 and US3-S3 all exist to catch an
over-correction. Every story here has a positive cell; test it.

**3. Do not leak a key on the failure path.** FR-002. The probe mints, asserts,
revokes. If the assertion raises between mint and revoke, the key survives with
its TTL as the only bound. This repository has already filed
`interpreter/key-lease-leak-on-verify-raise` once. Use a `finally`, and test the
failure path explicitly — US1-S3 requires it.

**4. Absent, empty, and malformed are three states, not two.** US2's whole risk
is collapsing them. A missing root returns empty. An existing empty root returns
empty. A malformed corpus still raises naming every fault. And a root that is a
*file* is none of the above. Four cells; test four.

**5. `read_roadmap`'s loud-failure discipline is load-bearing.** Its docstring
commits to "emits nothing on failure", matching the deriver. A well-meaning
`try/except` around `iterdir()` that swallows real errors would satisfy US2-S1
and destroy US2-S3. Check for existence explicitly; do not catch broadly.

**6. The no-op gate finding must not fail `--check`.** US3-S4. An operator
evaluating Ergane without gates is making a choice. The requirement is that the
choice be *visible*, not that it be forbidden. A finding that blocks `--check`
turns a warning into a wall and will be worked around by editing the manifest to
a different no-op the detector does not know.

**7. US4 must assert the outcome, not the exit status.** US4-S3. This is the
whole point. Every stage of the reporter's install exited zero. The final
assertion is a landed pull request, read back from GitHub, not `returncode == 0`.

**8. US4's live-tier guard must catch what the client actually raises.** Nothing
passes `-m` in CI or in the gate, so markers are decorative. A dead Temporal port
surfaces as `RuntimeError` from `temporalio`, not as a connection error you might
expect. Prove the guard with `TEMPORAL_ADDRESS=127.0.0.1:1` before you trust it.

**9. US4 must not touch the operator's live store.** This repository has already
lost all three stores once to an agent's cleanup, and once to a test that
asserted the live store must not exist. Every path US4 writes lives beneath its
own temporary root, and US4-S5 asserts it. Do not resolve the runtime root from
the ambient environment inside the exercise.

**10. The gate and CI are different machines.** The boundary gate runs under
bwrap with `--clearenv`, no D-Bus, tmpfs `/tmp`, `USER` unset; a GitHub runner
has none of those constraints. Any test consulting real host state passes in one
and fails in the other *deterministically*, and the agent meeting it will call it
flaky. 042/US3 burned four attempts on exactly this. Simulate through seams.

**11. The judge sees the diff and the criteria. Nothing else.** SC-001 through
SC-004 are all runtime evidence and must be **committed as pasted output inside
the diff**.

**12. (Moot — US1 landed 2026-08-20.) 063 also edits `LLMProbe.gather`, and either epic may reach it first.**
063/US3 extracts the distinct-alias derivation out of `gather` into a shared
function so `ergane install --requirements` can reuse it. This spec's US1 rewrites
the same function to mint and revoke a key. The two are compatible in principle
and will collide in practice if either implementer assumes the shape they last
read. Re-read `factory/controlplane/verify.py` before editing it, and if the
derivation has already been extracted, extend the extracted function rather than
re-inlining it. `max_concurrent_epics` is 1, so they will not run simultaneously
— but "not simultaneous" is not "unchanged".

**13. Story edges.** US1 and US2 are landed. US3's edge to US2 and US4's edges
to US1/US2/US3 are all `depends_on_merged` — a code-needing edge must gate on
the dependency being in the dependent's base tree, not merely verified;
dispatching on a verified-only edge parked 073/us3 behind an operator question
on 2026-08-21. US4 also depends on 059 and 060, both confirmed landed.

**14. A FIXTURE THAT RUNS `git commit` MUST SET A GIT IDENTITY. THIS EXACT
DEFECT HAS ALREADY KILLED THIS EPIC TWICE.** Read this one before you write a
line; it is not a hypothetical and it is not a style note.

On 2026-08-19 this spec was dispatched, `us2` built cleanly, its own gates were
green in its worktree, and the required `test` check went red in CI with:

    FAILED tests/test_ergane_init_creates_specs.py::test_init_creates_specs_directory
      subprocess.CalledProcessError: Command '['git','-C',<tmpdir>,'commit',
      '--quiet','-m','initial commit']' returned non-zero exit status 128.

Exit 128 from `git commit` in a freshly `git init`-ed directory means **git has
no `user.email` / `user.name`**. The node was killed, and `us3` and `us4` died
with it at attempt 0, never having run. The epic was re-dispatched and died the
same way. Three of four stories, twice, for this.

WHY IT PASSES LOCALLY AND FAILS IN CI, which is the whole trap. Your sandbox's
per-node HOME is seeded with a `.gitconfig`
(`factory/workgraph/adapter.py:740`), so `git commit` finds an identity and the
fixture is green in front of you. **A GitHub Actions runner has no git
identity at all.** Your green local run is not evidence about CI; it is
evidence that the seeding works.

WHAT TO DO. Any fixture that creates a scratch repository and commits in it must
set the identity explicitly on that repository before committing — `git -C <dir>
config user.email` and `user.name`, or the equivalent `-c` flags on the commit
itself, or `GIT_AUTHOR_*`/`GIT_COMMITTER_*` in the subprocess environment. Pick
one and apply it to **every** such fixture you add, not only the one you were
thinking about. Do not rely on a global config, on `HOME`, or on anything the
host happens to provide.

WHY YOU MAY NOT SIMPLY BE TOLD THIS WHEN IT BREAKS. When this epic first died,
the recovery attempt received `log unavailable: could not list checks
(GH_REFUSED)` instead of the failing check's log. Spec 071 has since landed
(2026-08-20), so a red check's log should now reach recovery — but do not lean
on that as your safety net; the fix has not yet been exercised by a real
production failure. Get the identity right the first time.

**15. Your sandbox has no live prerequisites — the skip path is what runs in
your attempt.** The per-node HOME carries only a `.gitconfig`: no `gh`
credentials, no reachable Temporal, no gateway. US4's exercise cannot create a
scratch GitHub repository or land a pull request from inside the sandbox, and
you must not burn the attempt trying. Your in-attempt runtime evidence is the
skip-path transcript (US4-S4) and the simulated per-stage drives (US4-S2),
pasted into the diff. Of the Verification tasks, T035, T036, T038 and T039 all
need live prerequisites and are operator-run after landing — not your scope,
and their absence from your diff is not a gap. T037 is the exception: a scratch
local repository and the CLI suffice, so it is runnable in-sandbox and belongs
to US3's evidence.

## Sizing

Four stories, three small and one large.

US1, US2 and US3 are each a focused change to one or two functions plus
parametrised tests over a small matrix. None should need a second attempt.

**US4 is the risk.** It is a live, multi-stage, resource-creating exercise, and
this factory's history says stories like it are where attempts get burned. Two
mitigations are built into the spec: US4-S2 requires per-stage failure reporting
so a failure is diagnosable, and US4-S4 requires a clean skip so the exercise
does not become a permanently red check on hosts that cannot run it. If US4
starts to look like it needs more than one attempt, the right move is to split it
by stage rather than to widen the story.

SC-005 is the acceptance test for the *spec*, not just the story: revert any one
of the three fixes and US4 must fail. If it does not, US4 is measuring something
other than the composition.

## Verification the operator will run, independent of the gate

A green suite is evidence, not proof. Three of the four stories here exist
because a green suite was evidence of nothing.

- **Prove US1 by control, with two real proxies.** Start a LiteLLM with no
  `DATABASE_URL`, run `ergane install --verify`, confirm the `llm` check fails
  and names key management. Restart it with a database, confirm the check passes.
  Same binary, same config, one variable. That is SC-001 and it is the only check
  that distinguishes a working probe from a probe that always fails.
- **Prove US2 by watching the schedule.** On a fresh `ergane init`, let three
  ticks run and read `ActionCounts`. Zero `SkippedOverlap`. The reporter's
  measurement was `{"Total": 4, "SkippedOverlap": 3}`; the fix is visible in the
  same field.
- **Prove US3 by reading the default.** Run `ergane init` with defaults on a
  scratch repository and then `--check`, and confirm the gate is reported as a
  no-op. If the manifest no longer declares `true` at all, confirm that too —
  US3-S5.
- **Prove US4 by mutation, per SC-005.** Revert US1's fix, run the exercise,
  confirm it fails. Restore, revert US2's, confirm it fails. Restore, revert
  US3's. An end-to-end test that nobody has watched fail is an end-to-end test
  nobody has tested.
