# Implementation Plan: the operator's manifest is not a frozen fixture

**Spec**: `specs/121-the-operators-manifest-is-not-a-frozen-fixture/spec.md`

Move the frozen assertions off the operator's live file and onto a committed
sample, and leave behind only the assertions that follow from the manifest being
valid.

## What already exists, and where

Every anchor below was read from the tree at `aef5257`, not recalled.

- **The two tests that pin.** `tests/test_factory_yaml.py`:
  - `test_erganes_own_manifest_loads` (`:454`) loads
    `REPO_ROOT / MANIFEST_NAME` at `:463` and asserts `config.version == 1` at
    `:465`, then `runtime`, `gates["test"]`, `standards` and `landing_branch`.
    Only the version assertion is the defect; the rest are either liveness
    checks or documented operator facts.
  - `test_v1_identity_against_erganes_own_manifest` (`:1660`) loads the same file
    at `:1667` and compares field-for-field against
    `FactoryConfig(version=1, ..., ladder=VerificationConfig(), ...)` at
    `:1669-1677`. **The `ladder=VerificationConfig()` line is what makes any
    declared ladder fail**, independent of the version.
- **The one that is fine and must survive.**
  `test_erganes_declared_standards_document_exists` (`:478`) loads the live
  manifest and asserts `(REPO_ROOT / config.standards).is_file()`. It asserts a
  property of *validity*, not of *choice*, and its docstring records why it must
  read the live file: "the one place that can catch a stale path before a live
  dispatch does is here." Do not touch it (FR-004).
- **The convention to copy, one file away.** `tests/test_forge_manifest.py:55-64`
  sets `OWN_MANIFEST = REPO_ROOT / MANIFEST_NAME` with the comment "the file
  US5-S4 says this story may not edit", and puts its parsing assertions against
  `FIXTURE_MANIFESTS`, globbed from `tests/fixtures/target_repo/manifests/`. Its
  comment on the glob is worth reading before writing the new sample: "globbed
  rather than listed so a fixture added later is covered by having been added.
  The corpus is asserted non-empty where it is used: a glob that stopped
  matching passes forever."
- **The corpus the sample joins.** `tests/fixtures/target_repo/manifests/` ships
  eleven manifests today — `bwrap.yaml`, `landing-branch.yaml`, `malformed.yaml`
  and eight more — each named for the one condition it demonstrates.
- **Why the stakes are higher than trunk.** `ergane.yaml` declares
  `test: "uv run pytest -q"`. A node's gate runs this suite inside its own
  worktree, so a red suite is a red *gate*, and every attempt of every epic
  fails. This is not a spec whose failure costs a push.

## Traps

**Trap 1 — do not delete the live-manifest load.** The obvious cheap fix is to
stop reading `REPO_ROOT / MANIFEST_NAME` anywhere. That deletes FR-004's
coverage, which is the one thing here that has genuine live value: a stale
`standards` path surfaces as `CONFIG_ERROR` on the first dispatched node, hours
in, and this test is what catches it in seconds. Keep reading the file; change
only what is asserted about it.

**Trap 2 — the version assertion is not the whole defect.** Fixing
`assert config.version == 1` alone leaves `ladder=VerificationConfig()` in the
identity test, and a declared ladder still fails. Both sites must move. US1-S1 is
the proof, and it is written as "the manifest declaring a ladder passes" rather
than "the version assertion is gone" for exactly this reason.

**Trap 3 — a passing suite is not the requirement; preserved coverage is.**
FR-007. Deleting `test_v1_identity_against_erganes_own_manifest` makes US1-S1
pass and silently drops the parser regression fixture that spec 023's US1-S2/S6
put there. The identity test must keep existing and keep comparing field for
field — against a committed sample whose value nobody has a reason to change.

**Trap 4 — the sample must actually be v1.** The regression fixture proves *v1
semantics never moved*. A sample copied from today's `ergane.yaml` after the
operator's ladder lands would be v2 and would prove something else. Write the
sample as a v1 manifest, and let its committed bytes be the frozen thing.

**Trap 5 — a new fixture is picked up by a glob you are not looking at.**
`test_forge_manifest.py`'s `FIXTURE_MANIFESTS` rglobs `*.yaml` under
`tests/fixtures/target_repo/`, so a manifest added anywhere beneath it joins that
corpus and is asserted against by tests this story never reads. Run the forge
manifest tests before assuming the sample is inert.

**Trap 6 — assertions about operator facts are not all defects.**
`test_erganes_own_manifest_loads` also asserts `gates["test"]`, `standards` and
`landing_branch`, and the comment at `:470-476` explains that the
`landing_branch` line deliberately asserts an operator action. Those are
load-bearing in a way the version is not: they are what a node reads to learn
what "green" means. FR-001 and FR-002 name *version* and *whole-config identity*
specifically. Do not widen the edit into a general deletion of everything the
test knows.

**Trap 7 — US1-S6 is a test about the tests, and it is the anti-recurrence
guard.** The finding has come back four times because each fix removed one
literal. A scenario that reads the assertions themselves — no live-manifest
assertion may name a value the operator chose — is what makes the fifth
recurrence fail a test instead of surprising an operator. It is the least
obvious task in the story and the one most likely to be skipped as
over-engineering. It is not.

## Sizing

One story, two edited tests, one new fixture. Small in lines and unusually high
in consequence: it is the difference between an operator being able to turn their
own dials and not.

If an attempt is editing `ergane.yaml`, changing the manifest schema, or touching
`personas.yaml`, it has gone outside the spec.

## Verification the operator will run, independent of the gate

The gate proves the suite is green with the manifest as it stands today. It
cannot prove the thing the spec is for, because that requires a manifest change
the spec deliberately does not make. Run this by hand after US1 lands:

```bash
eval "$(scripts/ergane-env.sh)"
# 1. the suite is green before the dial moves
uv run pytest -q tests/test_factory_yaml.py tests/test_forge_manifest.py
# 2. declare the ladder the suite used to refuse
python3 - <<'PY'
import pathlib
p = pathlib.Path("ergane.yaml")
t = p.read_text()
p.write_text(t.replace("version: 1", "version: 2") +
             "\nladder:\n  max_attempts: 2\n  promotion_cycles: 1\n"
             "  promotion_persona: opus-closer\n")
PY
# 3. green again — this is the assertion the whole spec exists for
uv run pytest -q tests/test_factory_yaml.py tests/test_forge_manifest.py
# 4. and the ladder is what was declared
python3 -c "
from pathlib import Path
from factory.verify.factory_yaml import parse_factory_config, resolve_manifest_path
p, n = resolve_manifest_path('.')
l = parse_factory_config(Path(p).read_text(), source=n).ladder
print(l.max_attempts, l.promotion_persona, l.promotion_cycles)"
git checkout ergane.yaml    # leave the operator's file as it was found
```

The demonstration succeeds when step 3 is green and step 4 prints
`2 opus-closer 1`. Before this spec, step 3 fails with two assertion errors —
`assert 2 == 1`, and a `FactoryConfig` identity mismatch on `version` and
`ladder`. Paste both runs of step 1/3 into the attestation; the pair is the
evidence, because either alone proves nothing.
