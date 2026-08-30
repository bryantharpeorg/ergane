# Implementation Plan: the last two fixtures that choose for the operator

**Spec**: `specs/123-the-last-two-fixtures-that-choose-for-the-operator/spec.md`

Two files, two stories, no shared surface. Every edit is under `tests/`.

## What already exists, and where

Read against `origin/ergane-buildout` at `62cc820`, not the working tree.

- **The pin**: `tests/test_poll_usage.py:59`, `PERSONA = "implementer"`. Fifteen tests in
  that file lease a virtual key against it.
- **The fix 122 already made, one file over**: `tests/test_usage_activities.py:74` carried
  the identical constant and 122/US2 removed it. Read that landed diff first — this story
  is the same edit in a file the earlier spec did not look at.
- **The register to follow**: `MODELS = ["anthropic/CHANGEME", "local/CHANGEME"]` sits
  beside the constant in both files. It is the suite's own placeholder vocabulary, and a
  fixture-owned persona name belongs in it.
- **The store-dependent test**:
  `tests/test_spec_declares_its_fixes.py::test_validate_reports_the_same_result_with_and_without_fixes`,
  failing with `assert 'fixes' in []` because the fixes layer skips when no store exists
  and runs when one does.
- **The measurement**, so it need not be reproduced: with `implementer` set to
  `agent: subscription`, the full suite reports **31 failed**; with it reverted, the same
  two files report **1 failed**. So fifteen belong to the pin and one is the store test.

## Traps

**Trap 1 — do not name another real persona.** FR-001 and US1-S3. Substituting `architect`
moves the pin: the next operator to change that persona's route breaks these tests instead.
The fixture needs a name it owns.

**Trap 2 — one constant, not fifteen tests.** `PERSONA` is module-level. Changing it once
fixes all fifteen. An attempt editing each test individually produces a diff several times
larger than necessary, and this repository refuses oversized diffs unjudged — 017/US1 was
refused at 2.4× the 64 KB ceiling on 2026-08-29 with its gate passing.

**Trap 3 — US1-S4 is the check that ends the class, and it will look like
over-engineering.** Seven occurrences have each been fixed by removing one literal. A
committed check that no fixture leases a key against a registry-read persona name is what
makes an eighth fail here. 122 shipped the same guard for the registry assertions and it
did not cover key-leasing fixtures; this one must.

**Trap 4 — both directions, or the store fix is not a fix.** US2-S1 and US2-S2. The test
must pass with a populated `.factory/doctor.db` present *and* absent. Seeding the real
store to make the operator's host green would deepen the dependency rather than remove it.

**Trap 5 — the absent-store path is correct.** FR-005. The fixes layer reporting
`not checked` when no store exists is what 089/US3 landed and is why a fresh target repo
can validate a spec declaring `fixes:`. Do not change it.

## Sizing

Two small stories. US1 is one constant plus the guard. US2 is fixture plumbing in one file.
Both should land first attempt.

If an attempt is editing `personas.yaml`, anything under `factory/`, or the fixes layer,
it has gone outside the spec.

## Verification the operator will run, independent of the gate

The gate proves the suite is green with the registry as it stands. It cannot prove this
spec's purpose, which needs a registry change the spec does not make:

```bash
eval "$(scripts/ergane-env.sh)"
cp personas.yaml /tmp/personas.bak
python3 - <<'PY'
import pathlib
p = pathlib.Path("personas.yaml"); t = p.read_text()
p.write_text(t.replace("  agent: claude-code\n  model: ollama-cloud/glm-5.3\n  fallback: local/qwen3.6-27b",
                       "  agent: subscription\n  model: claude-opus-5\n  fallback: null", 1))
PY
uv run pytest -q                       # expect: no failure outside the known live tiers
cp /tmp/personas.bak personas.yaml
```

The demonstration succeeds when that full run shows no non-live-tier failure. **Run the
whole suite, not a chosen subset** — scoping 122 from four predicted files is exactly how
this spec came to exist. Paste the run into
`specs/123-the-last-two-fixtures-that-choose-for-the-operator/attempt-report-<story>.md`.
