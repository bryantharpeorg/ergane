# 0.6 attestation packet specification review

The user explicitly approved story/spec audit packets in 0.6.0 on 2026-09-10.
The feature is now specified, not implemented. Work is local on
`codex/167-attestation-packets`, based on buildout a654fca and the earlier
release brief b284dc0; no ready-state, workflow, service, credential or public
artifact was changed by this pass.

## Implementation allocation

| Spec | Stories | Contract |
| --- | ---: | --- |
| 134 | 5 | Declared artifacts; safe bounded capture; immutable dispatch/capture identity and freshness; durable read-only reader |
| 135 | 3 | Existing usage-correctness companion; confirmation predicate, held spend correction, legacy flag repair |
| 167 | 6 | Invocation/usage identity; full judge history and resolution; portable packet/export; lifecycle generation; spec rollup; team CI attachment |

160's four current-Codex-evidence stories were already in the migration and are
not counted again.167 requires landed134 and160; it does not need135's held
spend reversal to expose incomplete source measurements honestly. This is14
planned additional slices if all three usage stories remain together. The prior
3–5 additional-day estimate is still provisional, not a promised release date.

The release requirement includes tokens, configured and actual ladders,
builder/scorer identities, every retained judge evaluation and feedback,
criterion-linked resolution, actual gate results and exact changed-file refs,
plus team-selected integration/UAT/security/quality/coverage/SBOM reports.
Archives are private-by-default, portable and immutable. Checksums are integrity
evidence, not signing or compliance certification. The full generic124 hook
framework and a new hosted service remain outside scope.

## Validation performed

All three complete trios were read, updated and validated against the isolated
source tree. The existing source's read-only findings resolver was pointed at
the operator's actual findings store to avoid a silently skipped fixes check.

| Spec | Layers checked | Skipped | Findings | Scenarios | Derived nodes |
| --- | ---: | ---: | ---: | ---: | ---: |
| 134 | 12 | 0 | 0 | 36 | 5 |
| 135 | 12 | 0 | 0 | 15 | 3 |
| 167 | 11 | 0 | 0 | 29 | 6 |

167 has no `fixes:` declaration, hence no fixes layer applies. All80 scenarios
have task references. Every derived graph has zero inferred contention edges:
the needed merge ordering is explicit.134 retains US1→US2→US3→US5→US4;
135 retains US1→US2 and US1→US3;167 is US1→US2→US3→US4→US5→US6.
Operator-only qualification tasks are intentionally outside implementer slices.

Actual commands, from the isolated worktree, with `N` naming the full spec
directory (one invocation per trio):

```bash
ERGANE_ROOT=/home/admin/code/ergane/.factory /home/admin/code/ergane/.venv/bin/ergane spec validate specs/N --target-repo /home/admin/code/ergane/.factory-tmp/167-attestation-packets --specs-root specs --json
/home/admin/code/ergane/.venv/bin/ergane spec derive specs/N --target-repo /home/admin/code/ergane/.factory-tmp/167-attestation-packets --specs-root specs -o /tmp/ergane-packet-trios-zTLtjT/N.json --json
git diff --check
```

The actual derived files use134.json,135.json and167.json in that unique scratch
directory. They are diagnostics, not dispatch artifacts for the production
target. The user's older untracked134 graph was not overwritten or deleted.
No product tests were invented or counted as implemented feature coverage:
these results validate the spec/parser/graph contracts, not working packets.

The first pass exposed stale134/135 source anchors and abbreviated167 scenario
references the checker could not count. These were corrected. Line hints were
mapped only across unchanged source lines from602a92c to a654fca; the changed
manifest-key declaration and current usage writer were re-read separately.
Historical spec frontmatter and old measured counts remain historical.

## Remaining normal gates

All three trios remain draft. Before dispatch, re-read landed134/160 interfaces
where relevant, refresh against the selected target base, and re-evaluate the
largest slices against the64KiB code+tests+evidence limit.135 retains its
pre-existing spend-contract decision hold: D-055 is the latest inspected entry,
and no decision authorizes that reversal. Do not invent a decision or interpret
release inclusion as clearing the hold; record a real decision or explicitly
split its held story before readying135.

Factory implementation still requires test-first behavior tests, deterministic
gates, the independent inner-loop judge and native merge-group checks. Release
qualification must inspect a real configured-rung build, all expected new-run
usage and judge history, cleanup/restart survival, later team attachments and
offline story/spec exports. Missing expected measurements are a qualification
gap, even when the schema correctly represents unknowns. Onboarding refresh and
final release qualification remain prerequisites to main promotion/publication.
