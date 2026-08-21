# US3 evidence: a gate that cannot fail, reported as one

SC-003 and T037 are observations of a running command, and the judge sees only
this diff (plan trap 11), so the observations are pasted here rather than
described.

Four things are shown, in the order they were run:

1. the tests red, before the implementation existed;
2. **SC-003 by control** — one manifest, one value changed, and the reported
   condition differing;
3. **T037** — `ergane init --non-interactive` on a scratch repository, and the
   manifest it wrote (FR-010);
4. one mutation per behaviour: the source edit that should make each test go
   red, and the run showing it did.

Everything here ran in the implementer's sandbox, which has no `gh`
credentials, no reachable Temporal and no gateway (plan trap 15). That shapes
§2 and §3 and is called out in each.

---

## 1. Red first

`tests/test_noop_gate.py` was written before any of the implementation, and the
first run could not even import — `Severity` did not exist yet, which is the
right reason for a test-first run to be red:

```
$ uv run pytest tests/test_noop_gate.py -q
==================================== ERRORS ====================================
___________________ ERROR collecting tests/test_noop_gate.py ___________________
ImportError while importing test module '.../tests/test_noop_gate.py'.
Traceback:
tests/test_noop_gate.py:54: in <module>
    from factory.mergequeue.models import Finding, Severity, TargetRepoProfile
E   ImportError: cannot import name 'Severity' from 'factory.mergequeue.models'
=========================== short test summary info ============================
ERROR tests/test_noop_gate.py
1 error in 0.18s
```

---

## 2. SC-003, by control: one value changed, two reported conditions

A real `ergane.yaml` on disk, read by the real 002 loader, judged by
`evaluate_repo`, and printed by `render_check` — the function `ergane init
--check` prints with. The only thing simulated is the forge: this sandbox has
no `gh` credentials, so a real `--check` short-circuits at `GH_REFUSED` before
the gate findings are reached (that transcript is §3). The forge here is
`tests.fake_forge.FakeForge`, a repository as state rather than a call
recorder, standing in for a branch that gates on a required check named `test`.

The three runs differ in exactly one character sequence: the gate command.

```
$ cat ergane.yaml | grep -A1 gates:
gates:
  test: "true"
$ ergane init --check   # rendered through render_check()
ergane readiness for <TMP>/judged (ergane.yaml)
  [PASS] gated_landing: main refuses a landing until its named checks pass
  [PASS] autonomous_landing: main completes a landing without a human
  [PASS] factory_yaml: manifest is valid
  [PASS] landing_title: a landing commit takes the proposal's title
  [WARN] noop_gate:test: gate 'test' is declared as 'true', a command that exits 0 without running anything — a gate that cannot fail, which is not a pass. Nothing 'test' is meant to check can refuse a landing, and if every gate this repository declares is like 'test', no gate can fail and this factory lands whatever an agent writes. Declare the command that decides this repository's green, or keep it and read this line as the choice it is
4 of 5 checks passed, 1 warned; nothing here refuses this repository
exit status: 0

$ cat ergane.yaml | grep -A1 gates:
gates:
  test: ":"
$ ergane init --check   # rendered through render_check()
ergane readiness for <TMP>/judged (ergane.yaml)
  [PASS] gated_landing: main refuses a landing until its named checks pass
  [PASS] autonomous_landing: main completes a landing without a human
  [PASS] factory_yaml: manifest is valid
  [PASS] landing_title: a landing commit takes the proposal's title
  [WARN] noop_gate:test: gate 'test' is declared as ':', a command that exits 0 without running anything — a gate that cannot fail, which is not a pass. Nothing 'test' is meant to check can refuse a landing, and if every gate this repository declares is like 'test', no gate can fail and this factory lands whatever an agent writes. Declare the command that decides this repository's green, or keep it and read this line as the choice it is
4 of 5 checks passed, 1 warned; nothing here refuses this repository
exit status: 0

$ cat ergane.yaml | grep -A1 gates:
gates:
  test: "uv run pytest -q"
$ ergane init --check   # rendered through render_check()
ergane readiness for <TMP>/judged (ergane.yaml)
  [PASS] gated_landing: main refuses a landing until its named checks pass
  [PASS] autonomous_landing: main completes a landing without a human
  [PASS] factory_yaml: manifest is valid
  [PASS] landing_title: a landing commit takes the proposal's title
  [PASS] gate_check:test: required check 'test' exists
all 5 checks passed
exit status: 0
```

Three readings of that, and the third is the one that keeps the first two from
being free:

- the no-op is a **distinct finding** (`noop_gate:test`) and the
  `gate_check:test` pass — the line that used to say "gates work" — is not in
  the report at all (US3-S1);
- the exit status is **0** in every case, including the two warned ones
  (US3-S4, FR-009): the choice is visible, not forbidden;
- the real command reports the **existing pass, unchanged**, byte for byte
  (US3-S3, plan trap 2). A detector that flagged everything would be no more
  useful than one that flagged nothing, and this is the cell that shows it does
  not.

The empty string — FR-008's third form — is absent from this transcript on
purpose. It cannot reach the gate↔check judgment through a manifest at all,
because `factory.verify.factory_yaml._read_gates` refuses an empty command
outright with the `gate_command` rule, and `--check` reports a failing
`factory_yaml` instead. That is a stricter answer than the no-op finding, not a
weaker one. It is covered at `evaluate_repo` — the function `--check` judges
with — by the parametrisation in `tests/test_noop_gate.py`, and the refusal
itself is asserted by
`test_an_empty_gate_command_is_refused_by_the_manifest_parser_first`, so the
reason for the split is a test rather than a claim in this file.

---

## 3. T037 / FR-010: what a fresh `ergane init` now declares

A scratch repository with no `pyproject.toml` — the case that used to fall
through to `_PLACEHOLDERS["gates"]` and get `test: "true"`. Run against an
isolated `ERGANE_STATE_HOME` and an `ERGANE_CONFIG_PATH` that does not exist,
so nothing here touched the operator's registry, control plane or schedules
(plan trap 9).

```
$ export ERGANE_STATE_HOME=<TMP>/state ERGANE_CONFIG_PATH=<TMP>/no-control-plane.toml
$ git init -b main --quiet . && git config user.email … && git config user.name …
$ git add -A && git commit --quiet -m "initial commit"
$ ergane init --non-interactive
applied default: version = 1
applied default: runtime = bwrap
applied default: gates = test: 'echo "ergane: declare gates.test in ergane.yaml" >&2; exit 1'
applied default: landing_branch = main
applied default: repo slug = "scratch"
joined <TMP>/scratch as slug 'scratch'
written:
  <TMP>/scratch/ergane.yaml
  <TMP>/scratch/.gitignore
  <TMP>/scratch/.ergane
registered: 'scratch' -> <TMP>/scratch
control plane: not readable — ControlPlaneConfigError: <TMP>/no-control-plane.toml: [config_missing] cannot be read (No such file or directory); run `ergane install` to create the control-plane config
schedule: failed ergane-roadmap-scratch — refused: the control plane could not be read, so no schedule was created …
github wiring: not attempted — re-run with `ergane init --wire` to
  queue the landing branch and require one check per declared gate
next, run:
  git -C <TMP>/scratch add ergane.yaml .gitignore .ergane
  git -C <TMP>/scratch commit -m "join ergane"

ergane readiness for <TMP>/scratch (ergane.yaml)
  [FAIL] repo_read: could not read the repo via its forge (GH_REFUSED): To get started with GitHub CLI, please run:  gh auth login
…
  [PASS] resolved_root: this report is about <TMP>/scratch
  [PASS] runtime_root_ignored: .ergane/ is ignored by git
  [PASS] registry_entry: registered as 'scratch' in <TMP>/state/ergane/repos.json
  [PASS] landing_branch: landing branch 'main' exists
  [FAIL] control_plane: the control plane could not be probed: …
  [FAIL] roadmap_schedule: no roadmap schedule 'ergane-roadmap-scratch' exists …
3 of 7 checks failed

$ cat <TMP>/scratch/ergane.yaml
version: 1
runtime: bwrap
gates:
  test: 'echo "ergane: declare gates.test in ergane.yaml" >&2; exit 1'
landing_branch: main
```

The line SC-003 was written to catch is the `gates:` line, and it no longer
says `true`. The `GH_REFUSED`, `control_plane` and `roadmap_schedule` failures
are the sandbox having no credentials, no control plane and no Temporal (plan
trap 15) — they are not this story's, and they are why §2 uses an injected
forge to reach the gate findings.

The value that replaced `true` is a gate that fails loudly and says what to
edit, rather than one that passes quietly. The choice was between a gate that
cannot fail and a gate that cannot pass, and only one of the two is safe to be
wrong about: `true` says "verified" about work nothing looked at.

---

## 4. Mutations: each behaviour watched going red

Each block is one edit to the shipped source, the run it produced, and the
revert. A test that cannot fail is the defect this repository has paid most
for, so each of the four behaviours is shown failing when the line that
implements it is removed.

MUTATIONS_PLACEHOLDER
