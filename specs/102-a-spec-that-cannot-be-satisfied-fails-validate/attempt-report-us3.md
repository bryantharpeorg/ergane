# Attempt report — 102 US3, the judge may not propose moving the bar

## T024 (FR-011) — `criteria_drift`'s hashing is unchanged by this story

It is unchanged, and the diff is the proof: this story touches
`factory/verify/remediation.py` (new), `factory/verify/judge.py`,
`factory/workgraph/prompt.py`, `factory/notify/messages.py` and one test module.
`criteria_drift` is computed in `factory/activities/verify_activities.py` by
re-hashing the spec file, and that module is not in the diff at all.

```
$ git diff --stat f8f3216
 factory/notify/messages.py                         |  30 ++
 factory/verify/judge.py                            |  16 +-
 factory/verify/remediation.py                      | 264 ++++++++++
 factory/workgraph/prompt.py                        |  12 +-
 .../test_102_us3_the_judge_may_not_move_the_bar.py | 544 +++++++++++++++++++++
 5 files changed, 864 insertions(+), 2 deletions(-)
```

Nothing here could move the hash even indirectly: the screening this story adds
runs on `JudgeVerdict.feedback` on its way into a *prompt*, and never rewrites the
verdict, the criteria snapshot, or the spec text the drift check re-hashes. The
recorded feedback is byte-identical to what the judge returned, which is asserted
by `test_the_evidence_store_round_trips_the_proposal_verbatim`.

## T025 — the operator's paired demonstration

### What this worktree can and cannot demonstrate

The plan's paired demonstration exercises the layer **US1** adds to
`spec validate`. The spec's work graph declares US3 independent of US1
(`depends_on: []` for both), so US1's layer is not in this worktree, and the pair
below is therefore *inconclusive for the refusal half* and conclusive for the
other half. Both runs are pasted rather than described, and neither is
paraphrased into the result US1 will produce.

The pair used two specs identical but for one Then-clause: `900-demo` asserts
"the font renders correctly in the browser", `901-demo` asserts "the test gate
passes" — a gate `factory.yaml` declares.

```
$ uv run ergane spec validate /tmp/us3demo/specs/900-demo --target-repo .
/tmp/us3demo/specs/900-demo/spec.md: frontmatter, work-graph derivation, persona registry, scenario coverage, prompt assembly and slice coverage all pass
exit=0

$ uv run ergane spec validate /tmp/us3demo/specs/901-demo --target-repo .
/tmp/us3demo/specs/901-demo/spec.md: frontmatter, work-graph derivation, persona registry, scenario coverage, prompt assembly and slice coverage all pass
exit=0
```

Run 2 is the half this worktree establishes and the half that must still hold
after US1 lands: a clause naming a declared gate validates cleanly, so 102 and
116 compose instead of cancelling. Run 1 does not refuse, because the layer that
would refuse it is a sibling node's work — not because the clause is provable.

### The demonstration this story actually owns

US3's own pair is the same feedback read by two audiences. The input is the
measured case, near enough: a correct refusal whose second remediation offered to
move the bar.

```
=== what the judge said (recorded verbatim on the verdict) ===
US1-S2 fails: the diff implements the geometry correctly, but nothing in it proves the rendered glyph advances as the scenario's Then step requires.
Two ways forward: commit the measured advance as an artifact the diff carries, or reconcile the scenario text with the implementation you produced.
US1-S3 cannot be satisfied by any diff: it asserts a font rendering in a browser, and no declared gate measures that.

=== what the next attempt's prompt carries ===
US1-S2 fails: the diff implements the geometry correctly, but nothing in it proves the rendered glyph advances as the scenario's Then step requires.
Two ways forward: commit the measured advance as an artifact the diff carries.
US1-S3 cannot be satisfied by any diff: it asserts a font rendering in a browser, and no declared gate measures that.

[A remediation proposing a change to the acceptance criteria was withheld from this prompt. The criteria are fixed for this node: satisfy them as written, or say why they cannot be satisfied — never edit them. The full text of what was withheld is recorded for the operator.]

=== what the operator's escalation shows ===
Attempt 1 — FAIL
  gate test: PASS (exit 0, 11.5s)
  judge: RETRY
── judge feedback ──
US1-S2 fails: the diff implements the geometry correctly, but nothing in it proves the rendered glyph advances as the scenario's Then step requires.
Two ways forward: commit the measured advance as an artifact the diff carries, or reconcile the scenario text with the implementation you produced.
US1-S3 cannot be satisfied by any diff: it asserts a font rendering in a browser, and no declared gate measures that.
── judge proposed changing a criterion (withheld from the retry) ──
Two ways forward: commit the measured advance as an artifact the diff carries, or reconcile the scenario text with the implementation you produced.
── judge reports a criterion cannot be satisfied ──
US1-S3 cannot be satisfied by any diff: it asserts a font rendering in a browser, and no declared gate measures that.
```

Three things in that output are the story:

1. `reconcile the scenario text` reached the operator and not the agent.
2. `US1-S3 cannot be satisfied by any diff` reached **both** — withholding it
   would silence the report US1 exists to catch earlier (trap 7).
3. The allowed remediation in the same sentence as the forbidden one —
   "commit the measured advance as an artifact" — survived. Running this
   demonstration is what found that: the first implementation was
   sentence-granular and threw the good remedy away with the bad one, so the
   screening now falls back to clause granularity inside an offending sentence.

## Gates

The declared gate for this repository is `test: uv run pytest -q`, run last after
every task of this slice was complete:

```
$ uv run pytest -q
5338 passed, 58 skipped, 7 warnings in 380.20s (0:06:20)
```

Sixteen of those are this story's, in
`tests/test_102_us3_the_judge_may_not_move_the_bar.py`. The suite was run once
before the clause-granularity refinement too (5336 passed, 49 skipped, 386.98s);
the count differs by the two tests that refinement added.
