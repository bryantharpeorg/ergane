# Implementation Plan: the factory ships as a package

**Input**: [spec.md](spec.md) in this directory.

## Reuse inventory (verified against the tree 2026-08-18 — every anchor read)

- **The distribution declaration** — `pyproject.toml:2` (`name = "ergane"`),
  version at `:3`, description at `:4`. The console script is
  `pyproject.toml:13-14` (`ergane = "factory.cli.main:main"`).
- **The package-data force-include** — `pyproject.toml:44-45`
  (`"personas.yaml" = "factory/personas.yaml"`), with `packages = ["factory"]`
  at `:27` and the `.py.base` exclusion at `:32`. This block is the fix for the
  "wheel ships no persona registry" defect (`b63388c`, #103); it is load-bearing
  and must survive untouched.
- **The version seam** — `factory/cli/main.py:131-137` (`_version_text`), where
  `version("ergane")` names the *distribution*, and the `except Exception`
  branch substitutes the literal `"0.1.0"`. The `--version` flag is registered
  at `main.py:117`.
- **The registry resolver that proves an install works** —
  `factory/config.py:44-65` (`_resolve_default_registry_path`): package data
  first via `importlib.resources.files("factory") / REGISTRY_FILENAME`, then the
  development-checkout walk to `parents[1]`. US2's whole point is exercising the
  first branch, which only happens where there is no repo above the install.
- **The build backend** — hatchling (`pyproject.toml:22-24`). `uv build --wheel`
  produces `dist/ergane-0.1.0-py3-none-any.whl` today: 598 KB, 121 files.
- **Existing CI** — `.github/workflows/test.yml` is the only workflow. There is
  no release workflow; US3 adds the first one.

## Traps (named so the implementer does not rediscover them)

- **Do not rename the import package.** `factory/` stays `factory/`. This is the
  spec's central decision (FR-002) and the operator declined the alternative
  explicitly. A diff that renames directories or rewrites imports is wrong even
  if it is green, and it will not fit the judge: the rewrite was measured at
  1,309 import lines and ~141,000 diff bytes against a 65,536-byte ceiling.
- **The version fallback fails toward green.** Changing `pyproject.toml:2`
  without changing `main.py:135` leaves `--version` printing a hardcoded
  `"0.1.0"` forever, with no error anywhere. A test that asserts `--version`
  "prints a version" passes against exactly this bug. FR-005/FR-006 exist to
  kill both halves: one declared source, and an unknown that says so.
- **Prove the version by making the two disagree.** The only test that
  distinguishes "read from metadata" from "read from a literal" is one where the
  metadata version is not the literal. Asserting equality against `0.1.0` proves
  nothing while `0.1.0` is also the fallback.
- **`importlib.metadata` names a distribution, not a module.** After this change
  the string in `version(...)` is `"ergane-cli"` while the import above it stays
  `factory`. The two names differing is the normal state of a Python package,
  not a mistake to tidy up.
- **Package data is not automatic.** hatchling ships `.py` files and nothing
  else unless told; `pyproject.toml:44-45` is the telling. Any restructuring of
  the build table must be checked by inspecting the built wheel's contents, not
  by reading the config.
- **An install test must escape the checkout.** `_resolve_default_registry_path`
  falls back to walking to `parents[1]`, so a test run from inside this
  repository can find `personas.yaml` even when packaging is broken — which is
  how the original defect survived. The temporary environment must sit where no
  parent directory holds a `personas.yaml`.
- **Publishing is irreversible and is not the agent's to do** (FR-011). PyPI
  never permits reuse of a name-and-version pair. US3 builds and validates the
  release path; the first real publish is an operator act on a tag. No workflow
  this epic adds may publish from a branch, a pull request, or a dispatched
  attempt.
- **057 edits `pyproject.toml` too.** It force-includes its floor text and stack
  packs through the same block at `pyproject.toml:44-45` that carries
  `personas.yaml`, and US1 of *this* spec owns that file. This is a file
  collision, not a dependency, so nothing in either work graph will stop it:
  two in-flight worktrees there is a merge-queue conflict where the second
  lander rebases blind. Land one before dispatching the other, and if you are
  the second, re-read the block rather than trusting the plan's line numbers.
- **The word "factory" is five things.** The branch namespace
  `factory/<epic>/<node>` (`factory/workgraph/worktree.py:240`, archive form at
  `:1219`) is parsed by 020/029 landing attribution; the Temporal namespace is
  `factory`; the runtime root is `.factory/`; the import package is `factory`;
  and the English word means the whole system. **None of them change here.**
  SC-003 checks the first by comparing `ergane spec landed` output across the
  change.

## Evidence discipline

Criteria are judged from the diff alone (constitution VIII / D-037): the judge
sees no base tree, no terminal, and no commit message. US2's proof is a command
run in a temporary environment, so **its output must be committed as pasted
text** — including the interpreter path, which is what shows a reader it was not
the development checkout. A criterion that depends on an uncommitted terminal
cannot be scored and will fail.

## Structure

US1: `pyproject.toml` (distribution name, single-sourced version) and
`factory/cli/main.py` (`_version_text`), plus tests that pin the unchanged
names. US2: one new test that builds, installs into a clean environment and
exercises the packaged registry path, plus its committed evidence. US3:
metadata keys in `pyproject.toml` and a new release workflow under
`.github/workflows/`. US2 and US3 touch disjoint files and both merge-depend on
US1, which owns the two files they would otherwise contend for.

## Sizing

Small. US1 is two files plus tests; US2 is one test plus evidence; US3 is a
metadata block plus one workflow file. Nothing here approaches the 65,536-byte
judge ceiling (`factory/verify/diffbounds.py:42` — import `DIFF_INPUT_LIMIT`,
do not quote it). If a story does not fit whole, say where you would split it
rather than trimming checks.
