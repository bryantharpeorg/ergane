# Implementation Plan: a boundary-only gate is a declaration, not a refusal

Every `file:line` below was read from `ergane-buildout` at `602a92c` on
2026-09-04 and verified to resolve to the symbol named. Do not trust an anchor
that has moved; re-read before editing.

## What already exists, and where

**The finding to soften is five lines and has no severity argument.**
`factory/mergequeue/onboard.py:364` — `_gate_check_finding` builds the passing
case at `factory/mergequeue/onboard.py:386` — `_gate_check_finding` and the
failing case at `factory/mergequeue/onboard.py:390` — `_gate_check_finding`:

```python
    else:
        findings.append(
            Finding(
                f"gate_check:{gate}",
                False,
                f"gate '{gate}' is declared in factory.yaml but the landing "
                f"branch requires no check named '{gate}' — add it to the "
                "branch's required checks so the forge runs the gate the "
                "factory declares",
            )
        )
```

No `severity=`, so it takes the dataclass default declared at
`factory/mergequeue/models.py:351` — `Finding`, which is `Severity.ERROR`.

**The precedent to copy is in the same module and already argues this spec's
case.** `factory/mergequeue/onboard.py:340` — `_noop_gate_finding` passes
`Severity.WARNING` explicitly as its fourth positional argument. Read its
docstring and the verdict comment at
`factory/mergequeue/onboard.py:231-234` before writing US2 — the latter says a
verdict that read the no-op finding as a refusal "would fail every repository
that had deliberately turned its gates off (061 FR-009)". That is this spec's
argument, already made, about a different noun. Spec 057 landed a second
instance of the same shape on 2026-09-03: `_standards_floor_finding`
(`factory/mergequeue/onboard.py:792` — `_standards_floor_finding`) reports a
behind-the-floor standards document as `Severity.WARNING` and says in its own
docstring that it is "information for the operator, never a blocker".

**The verdict is a conjunction and must not be touched.**
`factory/mergequeue/onboard.py:235` — `evaluate_repo` is `passed=not any(f.blocking
for f in findings)`, and `factory/mergequeue/models.py:363` — `blocking` is
`not self.passed and self.severity == Severity.ERROR`. Changing either of those is
how this story accidentally softens `unknown_check:` too. FR-008.

**The gate loop that runs the profile's checks** is
`factory/mergequeue/onboard.py:215` — `evaluate_repo` (`for gate in declared:`),
inside `factory/mergequeue/onboard.py:162` — `evaluate_repo`, whose signature
already carries `declared_gates` and 061-US3's `gate_commands`.

**The one seam every door shares.** `evaluate_repo` has exactly one caller:
`factory/activities/merge_activities.py:639` — `onboard_target_repo`. It loads the
manifest at `factory/activities/merge_activities.py:676` — `onboard_target_repo`,
derives `declared_gates` at `factory/activities/merge_activities.py:677` —
`onboard_target_repo` and `gate_commands` four lines later, and calls
`evaluate_repo` at `factory/activities/merge_activities.py:708` —
`onboard_target_repo`. The dispatch activity, `ergane init --check`
(`factory/cli/init.py:2289`) and `ergane repo onboard`
(`factory/workgraph/cli.py:532`) all reach onboarding through that one function,
so threading the list there is what makes the key real — and is the only
production edit US2 needs outside `onboard.py`. FR-010.

**And the offline way to drive that seam is already written — with a MODELLED
forge, not the real one.** Do not write a new forge fake; one already exists and
it is the exact shape US2 needs. `tests/fake_forge.py:160` — `FakeForge` answers
every forge question out of `tests/fake_forge.py:58` — `RepositoryModel`, whose
`tests/fake_forge.py:90` — `gate_on` is how a test says which checks the landing
branch requires; the repository underneath it comes from
`tests/target_repo.py:102` — `build_target_repo`. The worked example is
`tests/test_forge_readiness.py:68` —
`test_a_forge_reporting_no_visibility_passes_and_fails_when_gating_goes`: it
builds the repository, calls `onboard_target_repo(FakeForge(model), str(repo))`
at `tests/test_forge_readiness.py:90` and asserts `profile.passed is True` at
`tests/test_forge_readiness.py:92`, then clears the model's branches and re-runs
the *same* seam for the failing half — one object, one difference, two verdicts,
which is exactly the shape US2-S4 needs. It passes no `init_facts`, which
`factory/mergequeue/onboard.py:417` — `evaluate_init_facts` short-circuits to
`()`, so trap 8 costs nothing on this route. Both US2-S4 and US2-S5 build on
that family; trap 11 is the one thing it does not hand you for free.

**Copy that call, and do not copy its model.**
`tests/test_forge_readiness.py:57` — `_ready_model` gates the landing branch on
**every** declared gate (`tests/test_forge_readiness.py:61` passes the whole
`FIXTURE_GATES` tuple to `gate_on`), so `factory/mergequeue/onboard.py:385` —
`_gate_check_finding` takes its `matched` branch for all of them, appends only
passing parity findings, and the profile is `passed is True` on today's tree —
before this spec exists and whatever the manifest declares. US2's tests need the
opposite arrangement: the gate under test declared and *not* required, which is
the only shape in which the boundary-only line is what decides the verdict. A
model built like `_ready_model` gives US2-S4 a pair that does not differ and
US2-S5 a Then that was already true. Traps 9 and 10.

**Narrow the gate tuple, and change nothing else.** The model US2's tests need is
`_ready_model` with exactly one edit — the checks tuple:

```python
model = RepositoryModel(address="acme/app", default_branch="main")
model.gate_on(
    "main",
    tuple(g for g in FIXTURE_GATES if g != "lint"),   # the gate under test
    title_source=NEUTRAL_TITLE_SOURCE,
)
```

`FIXTURE_GATES` (`tests/test_forge_readiness.py:33`) is the three gates the
fixture declares and `NEUTRAL_TITLE_SOURCE` (`tests/test_forge_readiness.py:36`)
is the title source a non-GitHub forge would report. That keyword is not
decoration and it is not `_ready_model`'s to keep: without it,
`tests/fake_forge.py:90` — `gate_on` sets `landing_title_from_proposal=False`
(`tests/fake_forge.py:103`), and `factory/mergequeue/onboard.py:290` —
`_landing_title_finding` — called unconditionally at
`factory/mergequeue/onboard.py:208` — `evaluate_repo` — appends a `landing_title`
finding with no `severity=`, so it takes `Severity.ERROR`
(`factory/mergequeue/models.py:351` — `Finding`) and blocks. Both halves of the
pair then come back `passed=False` for a reason this spec is not about, and the
differential dies exactly as it does on the real-forge route. Trap 12.

**The route that looks identical and is not.**
`tests/test_114_us2_fixtures_onboard.py:252` — `onboarding_findings` and
`tests/test_114_us1_smoke_onboards.py:317` also drive `onboard_target_repo`
offline, and both are wrong for this story: they hand it the **real** forge
(`factory/activities/merge_activities.py:338` — `_forge`) over a repository with
no remote (`tests/test_live_epic.py:516` — `build_scratch_repo`). The forge
raises, `factory/activities/merge_activities.py:719` —
`_profile_from_forge_failure` returns a profile carrying a failing `repo_read`
finding and `passed=False` at `factory/activities/merge_activities.py:772`, and
**`evaluate_repo` is never called** — the manifest's list is not consulted at
all, before or after this story. The sibling test in that same file,
`tests/test_114_us1_smoke_onboards.py:346` —
`test_the_filter_is_what_clears_the_repository`, asserts `not profile.passed`
about that very call. A US2 test written that way is red for a reason this spec
is not about.

**FR-010's two-door claim already has a committed assertion.**
`tests/test_ergane_init_check.py:490` —
`test_both_doors_render_identical_parity_findings` drives the dispatch door
through `onboard_target_repo` and the init door through `check_repo`, and
asserts the same `(check, passed, detail)` triples in the same order, listing the
init-only checks — 057's `standards` and `standards_floor` among them — by name.
Extend that test with a case whose manifest declares the list rather than
restating it elsewhere: it is the cheapest diff-provable place FR-010's parity
can be shown, and it leaves `ergane repo onboard` as the one door the operator
still runs by hand (verification step 4). Assert that case on the finding's
**mark**, not on parity alone — the two doors render identical triples before
this story and after it, so a case that only re-asserts equality is green on a
diff that threads nothing. The wiring for a case that *can* fail is already
there: `tests/test_ergane_init_check.py:502` requires `test` and `typecheck`
over a manifest declaring `test` and `lint`, so `lint` is exactly a declared gate
the branch does not require, and its `gate_check:lint` finding is blocking today
through both doors.

**Both refusal sites are already driven, green, by a profile a test wrote by
hand.** The roadmap's onboarding is a replaceable seam:
`factory/activities/roadmap_activities.py:713` is the `_onboard` seam and it
defaults to `factory/activities/roadmap_activities.py:696` — `_onboard_profile`,
which calls the third door onto the shared function,
`factory/activities/merge_activities.py:777` — `validate_target_repo`. Tests
replace that seam rather than the manifest behind it:
`tests/test_roadmap_scheduler.py:299` — `RoadmapWorld.__init__` takes an
`onboarding_profile` and defaults it to `tests/test_roadmap_scheduler.py:251` —
`_passing_profile`, a `TargetRepoProfile` constructed with `passed=True`, and
`tests/test_roadmap_scheduler.py:965` —
`test_an_onboarding_failure_parks_the_spec` is the park case written the same
way. The epic side is identical:
`tests/test_interpreter.py:1045` — `ScriptedWorld.__init__` defaults
`onboard_profile` to a hand-built passing profile, and
`tests/test_interpreter.py:2458` — `test_a_passing_onboarding_profile_proceeds_to_normal_dispatch`
asserts the epic proceeds on it — a test that is green on today's tree, before
this spec exists. Those four are the seams US2-S4 should feed its derived
profiles through and the fixtures it must not copy whole. Trap 10.

**The manifest key vocabulary is a closed list.** `_V2_TOP_LEVEL_KEYS`
(`factory/verify/factory_yaml.py:134`) is `_TOP_LEVEL_KEYS + ("ladder", "verify")`,
and `factory/verify/factory_yaml.py:269` — `_reject_unknown_keys` refuses anything
outside it, choosing the list by version at
`factory/verify/factory_yaml.py:270` — `_reject_unknown_keys`. The new key goes in
that tuple or every manifest declaring it is refused. `FactoryConfig.gates` is at
`factory/verify/models.py:310` — `FactoryConfig`.

**FR-002's cross-check already exists, written for another key.**
`factory/verify/factory_yaml.py:431` — `_read_writes` reads a v2-shaped block and
refuses any entry naming a gate the manifest does not declare, at
`factory/verify/factory_yaml.py:459` — `_read_writes`, with the comment that makes
Trap 5's argument in the tree's own words: "A declaration that silently applied to
nothing would be worse than no declaration". It is called from the reader list
beside `_read_timeouts` at `factory/verify/factory_yaml.py:217`, which is where the
new reader belongs. Copy its shape; do **not** copy where its key is registered
(trap 4).

**The fact the whole argument rests on** is
`factory/verify/gates.py:1491` — `_run_gate_list_from_config`, where the boundary
gate loops over `config.gates.items()`, iterating every declared gate before a node
opens a pull request. Cite it in the spec's own reasoning; without it the argument
collapses.

## Traps

**Trap 1 — There is a NEAR MISS in the tree that must not be mistaken for a fix.**
`_LANDING_ONLY_CHECK_PREFIXES = ("gate_check:", "noop_gate:", "unknown_check:")`
already exists at `factory/workgraph/workflow.py:391`, with
`factory/workgraph/workflow.py:394` — `_is_landing_only_check` beside it. Its
**only** consumer is `if self._halt_after_pass:` at
`factory/workgraph/workflow.py:1214` — `_onboard_target`, which filters those
findings out — and `_halt_after_pass` is the demo path
(`factory/workgraph/workflow.py:779`, set at `factory/workgraph/workflow.py:948`).
**The reasoning that exempts this finding is already written in this tree and
reaches neither refusal site.** An implementer who finds it will be tempted to
widen its use; that would exempt `gate_check:` for every repository, including the
typo case, which is FR-007's whole point.

**Trap 2 — There are TWO refusal sites, and clearing one is invisible.** The
roadmap parks at `factory/roadmap/workflow.py:1262` — `_dispatch`; a child epic
re-evaluates the same profile and raises `GRAPH_INVALID` at
`factory/workgraph/workflow.py:1225` — `_onboard_target`. A fix tested only through
the roadmap looks complete and still refuses a manual `ergane build start`. FR-009
requires a test that both clear — and requires that they clear **through the
verdict**, not by either site learning about the new key. If you find yourself
editing either of *those two files*, stop: the design is wrong. (That prohibition
is about those two files only. Trap 9 is the file you must edit.)

**Trap 3 — Do not widen `blocking` or the verdict conjunction.** Both are shared by
`noop_gate:` and `unknown_check:`. FR-008 exists because the obvious shortcut —
teaching `factory/mergequeue/models.py:363` — `blocking` about gate names — changes
the severity of findings this spec is not about, and does it silently.

**Trap 4 — The new key must be refused on v1, and `writes` is the wrong model for
where to register it.** `factory/verify/factory_yaml.py:270` —
`_reject_unknown_keys` picks its known-set by version. The reader you are copying,
`factory/verify/factory_yaml.py:431` — `_read_writes`, has its key registered in
`_TOP_LEVEL_KEYS` (`factory/verify/factory_yaml.py:118`), which is the **v1** list:
copying the whole pattern registers `boundary_only_gates` in v1 as well, and every
test in US1 still passes because nothing asserts the v1 refusal until US1-S4 does.
Register the key in `_V2_TOP_LEVEL_KEYS` (`factory/verify/factory_yaml.py:134`)
only. FR-004.

Registering it anywhere else costs more than FR-004, and spec.md's "does not
touch `init --wire`" is a statement about the *interview*, not a promise that
`ergane init` is unaffected. `_KNOWN_KEYS` (`factory/cli/init.py:511`) is
literally `_V2_TOP_LEVEL_KEYS`, and `factory/cli/init.py:759` —
`_carried_forward` raises `OperatorError` naming every declared key outside it,
"which `ergane init` cannot write back" — so a key that lands in any other tuple
makes `ergane init` refuse outright on **every** manifest declaring it, and
`factory/cli/init.py:1064` — `_render_manifest`, which writes over `_KNOWN_KEYS`
by construction, would never write it back. That is 120's defect reproduced from
the other side, in its own words: "`factory/verify/factory_yaml.py` named
`ladder` twenty-nine times and `factory/cli/init.py` named it zero". Put the key
in `_V2_TOP_LEVEL_KEYS` and init carries it forward and rewrites it for free,
with no edit to `factory/cli/init.py`'s production code at all — one landed
*test* assertion moves, and trap 13 is where it is.

**Trap 5 — A list naming an undeclared gate is BLOCKING, and this is new
strictness.** FR-002. It is tempting to treat an unmatched name as harmless. It is
not: `boundary_only_gates: [typecheck]` where the gate is spelled `type-check`
silently exempts nothing while reading as though it exempts something, which is
the failure mode this whole spec exists to prevent — a manifest that says one
thing and a system that does another. The tree already made this argument for
`writes:` at `factory/verify/factory_yaml.py:459` — `_read_writes`; reuse its
wording rather than inventing a softer one.

**Trap 6 — Keep the blocking finding's text byte-identical.** FR-007. Operators
have this string in their runbooks and the consumer quoted it in a decision entry.
The story is about which gates reach it, not about what it says. The string is the
one at `factory/mergequeue/onboard.py:390` — `_gate_check_finding`; a reflow of
those four f-string fragments changes it.

**Trap 7 — The stale-declaration case must not block either.** FR-006. A gate that
is listed boundary-only and IS required is a manifest that has drifted, not a
repository that is broken. Blocking it would punish the operator who later did the
right thing with their ruleset.

**Trap 8 — A US2 fixture that builds `InitFacts` by hand now fails for a reason
this spec is not about.** Spec 057 landed on 2026-09-03 and added
`factory/mergequeue/onboard.py:753` — `_standards_finding` to
`factory/mergequeue/onboard.py:417` — `evaluate_init_facts`; it appends a
**blocking** `standards` finding when `standards_path` is empty or
`standards_exists` is false. A US2 test that constructs `InitFacts()` to prove
"the profile passes" will therefore get `passed=False`, and the wrong move is to
read that red as "the boundary-only branch did not work" and go edit the verdict
(trap 3) or the refusal sites (trap 2). Use `tests/test_onboard.py:280` —
`_init_facts`, which 057 already amended with `standards_path`/`standards_exists`,
or pass `init_facts=None`, which `evaluate_init_facts` short-circuits to an empty
tuple — which is what the `FakeForge` route above does by leaving the argument
unset.

**Trap 9 — The key must leave the schema, and the file that carries it is not
`onboard.py`.** FR-010. `evaluate_repo` never reads a manifest; its caller does.
An implementer who adds a `boundary_only_gates` parameter with an empty default,
writes every US2 test by passing the list straight to `evaluate_repo`, and stops
there gets a green gate, a passing judge, and a repository whose manifest key
changes nothing — the outage intact behind a landed story. Thread it at
`factory/activities/merge_activities.py:677` — `onboard_target_repo`, beside where
`declared_gates` and `gate_commands` are already derived from the same loaded
config, and prove it with US2-S5, whose test may not name the list itself and
must reach the seam through `tests/fake_forge.py:160` — `FakeForge`, not through
the real forge (see "The route that looks identical and is not"). And its
repository must leave the listed gate **unrequired** on the landing branch: with
every declared gate required, `factory/mergequeue/onboard.py:385` —
`_gate_check_finding` appends its passing parity finding and the profile passes
whether or not the seam threads anything, so the test goes green on a diff that
stopped at `onboard.py` — trap 10's waste wearing FR-010's face. Narrowing that
gate tuple is the *only* deliberate difference from `_ready_model`: the model
still passes `title_source=NEUTRAL_TITLE_SOURCE`, or the profile fails
`landing_title` and never passes at all (trap 12).

**Trap 10 — A passing profile the test wrote itself proves nothing, and the suite
is full of them.** FR-009, US2-S4. `tests/test_interpreter.py:2458` —
`test_a_passing_onboarding_profile_proceeds_to_normal_dispatch` already asserts a
child epic proceeds on a `TargetRepoProfile(..., passed=True)` the test built, and
`tests/test_roadmap_scheduler.py:251` — `_passing_profile` does the same for the
roadmap's park site; both are green today, before any of this lands. An
implementer who satisfies US2-S4 by injecting such a profile ships a test that a
diff touching no production file would also pass — the same waste trap 9 describes
from the other end. Derive the pair instead, through the modelled forge: one
repository from `tests/target_repo.py:102` — `build_target_repo`, one
`tests/fake_forge.py:58` — `RepositoryModel` built exactly as
`tests/test_forge_readiness.py:57` — `_ready_model` builds one with its gate
tuple narrowed and nothing else changed —
`model.gate_on("main", tuple(g for g in FIXTURE_GATES if g != "lint"),
title_source=NEUTRAL_TITLE_SOURCE)`, so the gate under test is declared and not
required while the model still answers the title question (trap 12) — and two
`version: 2` manifests differing only in the `boundary_only_gates` line, each run
through `onboard_target_repo(FakeForge(model), str(repo))` the way
`tests/test_forge_readiness.py:68` —
`test_a_forge_reporting_no_visibility_passes_and_fails_when_gating_goes` derives
its own pair at `tests/test_forge_readiness.py:90`. Then feed each **derived**
profile through the seams above and assert the listed one proceeds where the
unlisted one parks and raises. On today's tree — with US1 merged and this story
unwritten — the listed manifest's profile still carries the blocking
`gate_check:` finding, which is what makes the pair red before the change and
green after it. Do not derive the pair through
`onboard_target_repo(_forge(...), ...)`: that route never reaches
`evaluate_repo`, so both halves come back identically `passed=False` with a
`repo_read` finding, the differential collapses, and the test is red before the
change and red after it for a reason this spec is not about.

**Trap 11 — The fixture manifests are v1 and the new key is v2-only.**
`tests/target_repo.py:102` — `build_target_repo` commits the fixture's own
`ergane.yaml`, which declares `version: 1`, and
`tests/test_ergane_init_check.py:71` — `make_repo` writes a v1 body too. US1
registers `boundary_only_gates` in `_V2_TOP_LEVEL_KEYS`
(`factory/verify/factory_yaml.py:134`) and nowhere else (trap 4), so appending
the key to either fixture's manifest as it stands is refused by
`factory/verify/factory_yaml.py:269` — `_reject_unknown_keys` and arrives as a
failing `factory_yaml` finding — trap 8's shape from a second direction, a red
that says nothing about this story. Write the manifest US2's tests read: build
the repository with the fixture, then overwrite its `ergane.yaml` with a
`version: 2` body declaring the gates and, in the listed half, the list.
`factory/verify/factory_yaml.py:985` — `resolve_manifest_path` reads that file
off disk, so the rewrite needs no commit.

**Trap 12 — A model with no `title_source` fails `landing_title`, and that red is
not about this story.** This is the third member of trap 8's series — the reds a
US2 fixture collects for reasons the spec is not about, after the blocking
`standards` finding (trap 8) and the `factory_yaml` refusal a v1 manifest earns
(trap 11). `factory/mergequeue/onboard.py:290` — `_landing_title_finding` runs
unconditionally at `factory/mergequeue/onboard.py:208` — `evaluate_repo` and
appends `Finding("landing_title", False, ...)` with no `severity=`, so it blocks
(`factory/mergequeue/models.py:351` — `Finding`). `tests/fake_forge.py:90` —
`gate_on` reports a title source only when the caller passes one
(`tests/fake_forge.py:103` sets `landing_title_from_proposal=title_source is not
None`), which is why `tests/test_forge_readiness.py:57` — `_ready_model` passes
`NEUTRAL_TITLE_SOURCE` at `tests/test_forge_readiness.py:61` and reaches
`profile.passed is True` at `tests/test_forge_readiness.py:92`. An implementer
who reads "do not copy `_ready_model`" as "build a model from scratch" gets
`passed=False` in **both** halves of US2-S4's pair and an unreachable Then in
US2-S5 — the differential collapsing for the third time, wearing a third face,
after the hand-built profile (trap 10) and the real forge ("the route that looks
identical and is not"). The gate tuple is the only thing that may differ, and the
wrong move is to read the red as "the boundary-only branch did not work" and go
edit the verdict (trap 3) or a refusal site (trap 2).

**Trap 13 — Registering the key turns a LANDED test red, and that red is the
proof it landed in the right tuple.** FR-004, T005. `_KNOWN_KEYS`
(`factory/cli/init.py:511`) *is* `_V2_TOP_LEVEL_KEYS` — the same object, not a
copy — and 120 pinned what `ergane init` carries without asking:
`tests/test_120_rewrite_carries_forward.py:308` computes
`carried = [key for key in init_module._KNOWN_KEYS if key not in _TOP_LEVEL_KEYS]`
and `tests/test_120_rewrite_carries_forward.py:310` asserts it equals
`["ladder", "verify"]`. Adding `boundary_only_gates` to `_V2_TOP_LEVEL_KEYS`
makes that list three entries long, so the *correct* US1 diff is red on the
declared gate — `test: "uv run pytest -q"`, which is the whole suite — until that
assertion is updated to `["ladder", "verify", "boundary_only_gates"]`. Update it
in the same commit: the key is carried-not-interviewed by construction, and the
test's second assertion (`tests/test_120_rewrite_carries_forward.py:311`, that no
carried key has an interview prompt) still holds, because
`tests/test_forge_manifest.py:333` pins the prompt set to `_TOP_LEVEL_KEYS` and
this key is deliberately not in it. The wrong move is to read the red as "the key
is in the wrong tuple" and move it to `_TOP_LEVEL_KEYS`: that clears this test,
breaks FR-004, and fails `tests/test_forge_manifest.py:333` instead — a key in
the interview's tuple with no prompt raises `KeyError` mid-interview. Nothing
else in `factory/cli/init.py` needs an edit: `factory/cli/init.py:759` —
`_carried_forward` and `factory/cli/init.py:1064` — `_render_manifest` both
iterate `_KNOWN_KEYS` and are generic over it.

## Sizing

US1 is one entry in a tuple, one reader modelled on `_read_writes`, one field on
`FactoryConfig`, and tests. In production it touches
`factory/verify/factory_yaml.py` and `factory/verify/models.py`. It also amends
one landed test by one entry — `tests/test_120_rewrite_carries_forward.py:301` —
`test_the_interview_gains_no_question_for_a_carried_key`, whose carried-key
assertion at `tests/test_120_rewrite_carries_forward.py:310` grows because
`_KNOWN_KEYS` *is* `_V2_TOP_LEVEL_KEYS` (trap 13) — and adds one test module of
its own. Plan for that amendment: without it the correct diff is gate-red.

US2 is a severity branch inside `_gate_check_finding`, the list reaching it through
`evaluate_repo`, and one derivation in the shared seam, plus tests. It touches
`factory/mergequeue/onboard.py` and `factory/activities/merge_activities.py` — and,
by FR-009, **no other production file**, in particular neither
`factory/roadmap/workflow.py` nor `factory/workgraph/workflow.py`. Its tests live
in **five** files, and naming them is part of the sizing: (1) the table cases in
`tests/test_onboard.py`; (2) one new module for the seam, built on the modelled
forge the tree already has (`tests/fake_forge.py:160` — `FakeForge` over
`tests/target_repo.py:102` — `build_target_repo`, driven the way
`tests/test_forge_readiness.py:68` drives it but over a model that leaves the
listed gate unrequired) rather than on a fake written from scratch; (3) FR-010's
door parity extended in `tests/test_ergane_init_check.py:490` —
`test_both_doors_render_identical_parity_findings`; and (4) and (5) US2-S4's
derived pair, added beside the fixtures it must not copy in
`tests/test_roadmap_scheduler.py` and `tests/test_interpreter.py` (trap 10).
Those last two are time-skipping workflow suites already inside the declared
`test` gate, so the story adds cases to them and may not restate their fakes.

The two stories name no production file in common.

Both stories are well inside the 64 KiB deterministic diff bound (D-050): US1 is
under fifty production lines plus one test module, US2 under eighty production
lines plus one new test module and cases added to three existing ones, and the
pasted evidence each verification task asks for is two short reports, not a
transcript.

## Verification the operator will run, independent of the gate

Per constitution VIII and D-037 the judge sees the diff and the criteria only, so
runtime evidence must be committed as pasted output. Beyond that:

1. On a scratch repository, declare a gate in `ergane.yaml`, do **not** add a
   required check of that name to the landing branch, and run onboarding. Confirm
   today's blocking refusal.
2. Add that gate to `boundary_only_gates` and re-run. The profile must pass and
   still report the gate.
3. Misspell the entry and re-run. It must refuse, naming the entry.
4. Run `ergane init --check` against the repository from step 2, then
   `ergane repo onboard <path-to-that-repo>` (`factory/workgraph/cli.py:532`)
   against the same repository, and confirm all three doors — the dispatch
   activity from step 1, `init --check` and `repo onboard` — report the same
   verdict. The first two are held together by a committed test
   (`tests/test_ergane_init_check.py:490` —
   `test_both_doors_render_identical_parity_findings`); `repo onboard` is the
   door that must be run by hand: it calls the seam with **no** `init_facts`, the
   argument shape of trap 8, so it is the one door whose verdict can differ for a
   reason this spec is not about.
5. Dispatch a spec against the repository from step 2 through the roadmap, and
   start one by hand with `ergane build start`. Neither may park or raise.

Step 5 is the falsifiable test of the whole spec: it is the 11h40m outage, run
forwards.
