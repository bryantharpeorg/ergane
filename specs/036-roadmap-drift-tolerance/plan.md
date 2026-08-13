# Plan: 036-roadmap-drift-tolerance

Scaffolded from `roadmap/drift-check-dies-on-spec-committed-after-landing`
(critical); refined 2026-08-13 against the tree at 8bdb425 by the operator
session that watched the defect kill run `roadmap-specs-2026-08-13T01:15:00Z`.

## Where the work is

Three seams, one story:

1. `factory/workgraph/landed.py` — `fingerprint(repo, rev, spec_dir, story_key)`
   shells `git show <rev>:specs/<dir>/spec.md` and currently propagates the
   failure. It gains the no-baseline result (FR-001).
2. `factory/activities/roadmap_activities.py` — `drift_for_spec` (defn near
   :251) compares pinned baselines against the current spec text; it skips
   no-baseline facts (FR-002). `_fingerprint_for_spec` at :227 is the thin
   wrapper the pin goes through.
3. `factory/roadmap/workflow.py:1176` — the `execute_activity(drift_for_spec…)`
   inside `_drift_resolver.resolve` is awaited bare. It gains the same
   degrade-don't-die treatment the dispatch stages already have (FR-003).

## Traps

1. **The catch must be `FailureError`, not `ApplicationError`.** A git failure
   surfaces from an activity as an `ActivityError` — the `_dispatch` clone
   stage (workflow.py, "1. Fresh clone…") already documents this and catches
   the base class. Mirror it.
2. **Notice spam.** The schedule fires a fresh run every 15 minutes; a bare
   notify on each failing pass means a Telegram message per fire. Route the
   FR-003 notice through 031's existing failure-notification machinery
   (`send_roadmap_notice` / its dedup discipline — read
   `tests/test_roadmap_failure_notifications.py` for the contract) rather
   than inventing a second channel.
3. **Use the scripted seam for the workflow scenario.** `_drift_runner`
   (roadmap_activities.py) exists so scheduler tests need no real clone.
   Scenario 4 scripts it to raise; do not build a git repo inside a workflow
   test.
4. **Scenario 1's fixture must reproduce the real commit order**: land a
   commit whose subject matches the landing grammar first, commit
   `specs/<dir>/spec.md` after, and point the reader at the landing commit.
   Do not attempt to reproduce against the live corpus or the 010 history.
5. **The verification component's sweep test forbids new `__main__` blocks
   and console scripts** in verification/notify modules. This story adds
   neither.
6. **FR-004 is a regression fence**: the pre-existing drift tests pass
   *unmodified*. If a change makes one need an edit, the change is wrong,
   not the test.
7. **Deliberately out of scope**: the sibling finding
   `hardening/self-landing-stales-the-running-worker` (worker restart after
   factory-code landings) is supervision work, not roadmap code — do not
   reach for it here.

## Post-landing operator steps (not the implementer's)

- Unpause the `ergane-roadmap` schedule (its Notes name this spec's finding).
- Restart the worker (this story changes factory code the worker imports).
