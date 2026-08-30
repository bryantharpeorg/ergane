# Implementation Plan: the suite does not choose the operator's builder

**Spec**: `specs/122-the-suite-does-not-choose-the-operators-builder/spec.md`

Three files, three stories, no shared surface. Every edit is under `tests/`;
nothing in `factory/` changes.

## What already exists, and where

Every anchor was read against `origin/ergane-buildout` at `c94b547`, not the
working tree — those differ whenever the roadmap is paused, and that difference
already invalidated one sweep on 2026-08-29.

- **The registry assertion**: `tests/test_us2_shipped_registry.py:344-345`.
  Two lines: `assert registry["implementer"].model` then
  `assert "/" in registry["implementer"].model`. The first is the real check and
  is kept. The second is the defect.
- **The comment above it** (`:338-343`) already states the rule this spec
  enforces, names `ci/test-suite-pins-the-operator-dial`, and cites the 037
  recurrence. Read it before editing — it is the argument, already written, for
  the change you are making.
- **The fixture persona**: `tests/test_usage_activities.py:74`,
  `PERSONA = "implementer"`, feeding `ALIAS` on `:76` and used by thirteen
  tests in that module.
- **The models constant beside it**: `MODELS = ["anthropic/CHANGEME",
  "local/CHANGEME"]` (`:77`) — the suite's own placeholder aliases. A persona
  name chosen for the tests belongs in the same register as these.
- **The 089 tests**: `tests/test_089_validate_checks_fixes.py` and
  `tests/test_089_promote_declares_fixes.py`. Three of their tests resolve a
  findings store the way the findings verbs do, which lands on
  `.factory/doctor.db`.
- **The measured failure**, so the implementer does not have to reproduce it:
  with `implementer` set to `agent: subscription`, `model: claude-opus-5`, the
  affected files report **28 failed, 35 passed**; with the registry reverted,
  **3 failed, 8 passed** in the 089 files alone. So 25 failures belong to the
  two pins and 3 are the ledger defect.

## Traps

**Trap 1 — do not delete the first assertion.** FR-002 and US1-S3. `assert
registry["implementer"].model` catches a registry entry that failed to resolve,
which is a real defect this suite should keep catching. Only the shape check
goes.

**Trap 2 — a subscription persona is not a malformed one.** The tempting reading
of "assert it loads" is "assert it has a model string that looks like an alias".
`claude-opus-5` is a legitimate model for `agent: subscription`; the registry
already ships `opus-closer` in exactly that form. Any new check must pass on it.

**Trap 3 — US2 is one constant, and the temptation is to touch thirteen tests.**
`PERSONA` is module-level. Changing it once fixes all thirteen. An attempt
rewriting each test individually has misread the story and will produce a diff
several times larger than it needs to be — which on this repo means a size
refusal before the judge ever sees it.

**Trap 4 — do not name another *real* persona.** Substituting `architect` for
`implementer` moves the pin rather than removing it: the next operator who
changes the architect's route breaks these tests instead. The fixture needs a
persona it owns. The `CHANGEME` aliases one line below are the register to
follow.

**Trap 5 — keep the no-key coverage.** FR-005 and US2-S4. Somewhere the suite
must still assert that a subscription persona mints no virtual key, because that
is the actual behaviour the old `PERSONA` pin was accidentally exercising. Move
it deliberately; do not let it evaporate.

**Trap 6 — the 089 tests fail in one direction and must pass in both.** US3-S1
and US3-S2. They are green today on a machine with no `.factory/doctor.db` and
red on one with a populated ledger. A fix that only makes the operator's host
green, by seeding the real store, has made them depend on the real store harder.
Build the store under `tmp_path`.

**Trap 7 — the absent-store path is correct and is not the bug.** FR-007. The
fixes layer reporting `not checked` when no store exists is deliberate, is what
089/US3 landed, and is the reason a fresh target repo can validate a spec that
declares `fixes:`. Do not "fix" it to refuse.

**Trap 8 — US1-S4 is the anti-recurrence guard and is the least obvious task
here.** This defect class has recurred six times, and every previous fix removed
one literal and left the mechanism. A test that reads this suite's own
assertions about the shipped registry, and fails if any constrains a vendor or
route, is what turns the seventh occurrence into a red test instead of a blocked
operator. It will look like over-engineering. It is not.

## Sizing

Three small stories, deliberately independent so they land in one round. US2 is
the largest by blast radius and the smallest by diff — one constant. US1 is one
deleted line plus the guard. US3 is fixture plumbing in two files.

If an attempt is editing `personas.yaml`, anything under `factory/`, or the
fixes layer itself, it has gone outside the spec.

## Verification the operator will run, independent of the gate

The gate proves the suite is green with the registry as it stands. It cannot
prove the thing this spec is for, because that needs a registry change the spec
deliberately does not make. Run this by hand after all three land:

```bash
eval "$(scripts/ergane-env.sh)"
cp personas.yaml /tmp/personas.bak
python3 - <<'PY'
import pathlib, re
p = pathlib.Path("personas.yaml"); t = p.read_text()
t = t.replace("  agent: claude-code\n  model: ollama-cloud/glm-5.3\n  fallback: local/qwen3.6-27b\n  skills: [implement, tdd]",
              "  agent: subscription\n  model: claude-opus-5\n  fallback: null\n  skills: [implement, tdd]", 1)
p.write_text(t)
PY
uv run pytest -q tests/test_us2_shipped_registry.py tests/test_usage_activities.py \
  tests/test_089_validate_checks_fixes.py tests/test_089_promote_declares_fixes.py
cp /tmp/personas.bak personas.yaml     # leave the operator's file as it was found
```

The demonstration succeeds when that run is green with a subscription
implementer. Before this spec the same sequence reports **28 failed**. Paste
both runs into `specs/122-the-suite-does-not-choose-the-operators-builder/attempt-report-<story>.md`;
the pair is the evidence, because a suite that was already green proves no fix
and one green only afterwards proves no regression was avoided.
