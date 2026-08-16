# Implementation Plan: 051-first-run-defaults

Refined against the tree at `9112e5d`. Every anchor below was read by hand at
that commit. Where one has moved before you dispatch, re-read it — a plan citing
a function that has since moved sends you hunting at the operator's expense, and
this project shipped three specs today whose anchors had rotted.

## What already exists, and where

| Thing | Where | What it does today |
| --- | --- | --- |
| The interview's question text | `factory/cli/init.py:235` | `"landing_branch": "landing branch"` — the prompt label |
| The interview's default | `factory/cli/init.py:256` | `"landing_branch": "main"` in `_PLACEHOLDERS` — US1's whole target |
| The re-run path | `factory/cli/init.py:323` | `existing.get("landing_branch", _PLACEHOLDERS["landing_branch"])` |
| The manifest read | `factory/cli/init.py:497` | `manifest_values.get("landing_branch")`, consumed by `_wire` and the checks |
| The question generator | `factory/cli/init.py:380` | `for key in _TOP_LEVEL_KEYS:` — one question per manifest key |
| The readiness check | `factory/mergequeue/onboard.py:408` | `_landing_branch_finding`, called from `:329`; the PASS text is at `:424` |
| The install interview seed | `factory/cli/install.py:71` | `"namespace": "ergane"` |
| The code fallback | `factory/notify/service.py:111` | `DEFAULT_TEMPORAL_NAMESPACE = "factory"` |
| The unified resolver | `factory/controlplane/resolve.py` | `resolve_temporal_target()`, landed by 048/US4 |

Two facts make US1 much cheaper than it looks:

- **FR-004 is already built.** `:323` already prefers an existing manifest's
  `landing_branch` over the placeholder. Your derivation goes *underneath* that,
  as the fallback the placeholder currently occupies — not in front of it. Read
  `:323` before you write anything; a diff that reimplements it is a diff that
  breaks re-running init in a joined repository.
- **The readiness check already produces the good message.** `onboard.py:408`
  is where the FAIL text in the spec's Context comes from. US1 does not touch it.
  If you find yourself editing the check, you have solved the wrong half: the
  check is right, the offer is wrong.

## Route choices left to the implementer

- **How the current branch is read.** `git symbolic-ref --short HEAD` and
  `git rev-parse --abbrev-ref HEAD` differ on an empty repository and on a
  detached HEAD, and the difference is the whole of FR-002. Pick one, read what
  it does in both states, and let your test for scenario 3 be the thing that
  proves you picked correctly.
- **Where the single namespace literal lives (US2).** `service.py`'s constant
  becoming the source that `install.py` imports, or both importing from
  `controlplane`, are both defensible. What is not defensible is two string
  literals that happen to be equal — FR-007's test must assert one source, not
  two matching values.

## Traps

1. **The judge sees only your diff and the criteria** — no base tree, no commit
   message, no terminal (constitution VIII / D-037). SC-001 is a claim about a
   *machine*: it needs a committed transcript, in a file, or it does not exist.

2. **Measure exit codes without a pipe.** `cmd | head; echo $?` reports the
   pipe's status, not the command's. That error produced a false reading of
   `ergane install --verify` on 2026-08-16 and nearly became a filed finding.
   If you paste a transcript as evidence, capture `rc=$?` before any pipe.

3. **A test asserting the accepted value does not test the offer.** Scenario 1
   is about what the prompt *says* before the operator types. A test that scripts
   an answer and checks the manifest passes today, unchanged, because the
   operator's answer was always honoured. Assert the prompt text.

4. **The scripted interviews will break if you add a key, and there are nine of
   them.** `ergane init` generates its questions from `_TOP_LEVEL_KEYS`, and nine
   test files bind `_prompter_factory` to fixed answer lists. FR-010 forbids a new
   key precisely so you never meet this. If you see "prompter ran out of answers"
   in a file you never opened, you have added one. Filed as
   `init/adding-a-manifest-key-breaks-every-scripted-interview-in-the-suite`.

5. **An empty repository is not an error.** Scenario 3 exists because `git init`
   with no commit has no resolvable HEAD, and joining a repository before its
   first commit is a normal thing an operator does. A diff that raises there
   fails FR-002 and makes the product worse than the literal it replaced.

6. **US2 must not disturb 048/US4's precedence.** Environment over declaration
   over default, routed through one resolver, with an AST test asserting no
   connect site keeps its own copy of the contract. Run
   `test_no_connect_site_keeps_its_own_copy_of_the_temporal_contract` and quote
   it; it is the test your change is most likely to break silently.

7. **Read `factory/notify/service.py:679` before you start US2.** It still spells
   `os.environ.get(TEMPORAL_NAMESPACE_ENV) or DEFAULT_TEMPORAL_NAMESPACE`, which
   is the expression 048/US4 set out to delete everywhere. Either it is not a
   connect site by that test's definition, or it is a gap that test does not
   cover. Find out which and say so in your report — do not silently fix it as
   part of this story, and do not assume it is fine because the suite is green.

8. **The sweep in FR-009 must be able to fail.** A parametrized sweep over an
   empty file list passes forever without asserting anything.
   `tests/test_final_sweep.py:644` is the precedent and exists because that
   already happened here. Assert the file list is non-empty *and* names both
   modules. Run the point-at-nothing mutation **first**, not last: if the sweep
   stays green pointed at a path that does not exist, every other mutant you run
   is meaningless.

9. **Which namespace value wins is not yours.** FR-006 requires *one* literal.
   Whether it reads `ergane` or `factory` is an operator decision with a
   migration attached — this repository's own floor runs in `factory`, and
   changing the constant without a plan points its worker at an empty namespace.
   The Out of Scope section says so. If you reach dispatch without that decision
   made, stop and ask rather than picking.

10. **Purge `__pycache__` between mutants**, or run under
    `PYTHONDONTWRITEBYTECODE=1`. CPython validates a cached `.pyc` on
    `(mtime-in-whole-seconds, size)` only, so two same-size mutants written inside
    one wall-clock second make the second run execute the first's bytecode. It
    fails toward green and reproduces stably. Filed as
    `verify/mutation-batteries-can-test-stale-bytecode-when-a-mutation-preserves-file-size`.

11. **Do not quote warning counts as evidence.** A `SyntaxWarning` fires at
    compile time, so a warm cache reports fewer than a cold one on an identical
    tree. Quote `passed` and `skipped`; the skip count is load-bearing and the
    baseline is 44.

## Sizing

Small, and US1 is the smaller half. US1 is one placeholder becoming one read,
with a fallback and four tests. US2 is deleting one literal and importing the
other, plus a sweep. The 61,440-byte diff bound
(`factory/verify/diffbounds.py`, import `DIFF_INPUT_LIMIT` rather than quoting
it) should not bind on either; if it does, you have taken on more than the story
asked for.

## Verification the operator will run, independent of the gate

The reproduction from the spec's Context, on a machine whose git creates
`master`: build the wheel, install it into a clean container, `git init` a fresh
repository, run `ergane init` accepting every default, and read the
`landing_branch` line of the readiness report. A green suite is evidence, not
proof — this defect was found by running the thing on a machine that had never
seen the project, and that is the only place it is visible.
