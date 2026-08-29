# Implementation Plan: the sandbox is portable and sealed

**Spec**: `specs/101-the-sandbox-is-portable-and-sealed/spec.md`

Tell the agent the rule as a runnable line, let a repository declare what its
gates need, and annotate the one failure signature that teaches the wrong lesson.

## What already exists, and where

- **The tmpfs `HOME`**: `factory/verify/gates.py:690-691` —
  `argv.extend(["--tmpfs", str(home)])` then `--setenv HOME`. The mount set is
  described at `:517` as "deliberately minimal: a read-only system tree, a
  tmpfs…". Read-only to this epic (FR-010).
- **The network posture**: `:810` — the boundary "deliberately does not unshare
  the network", which is why the download US1 tells the agent about *would*
  succeed if it happened at gate time. Read-only to this epic.
- **The existing bind, and the whole argument for US2**: `_cache_binds`
  (`:861-878`). Read the docstring in full before writing anything — it is this
  spec's rationale, written for one package manager. Note three things it already
  gets right and US2 must preserve: the bind is **writable** ("a read-only cache
  is worse than none, because the manager treats it as a corrupt one"), it is
  **conditional on existence** (`return [...] if cache.is_dir() else []`, which
  is FR-005 already implemented for uv), and it sets `UV_CACHE_DIR` beside itself
  because "the tmpfs HOME would otherwise send uv looking elsewhere" — which is
  FR-008 already implemented for uv.
- **Where the binds are consumed**: `:682-693` — `cache_binds = self._cache_binds()`,
  then the binds, then `argv.extend(["--setenv", "UV_CACHE_DIR", dest])`.
- **The sibling bind and its cautionary tale**: `_interpreter_binds` (`:880`),
  whose docstring records how a missing interpreter bind turned a read-only
  worktree into `failed to remove directory .venv/bin` rather than a clean error.
  Read-only here, but read it: it is the shape of what goes wrong when the
  boundary lacks something the host has.
- **The env allow-list**: `HOME` appears at `:114` in the boundary's environment
  handling; US2's declared variables must go through the same path.

## Traps

**Trap 1 — US1 ships a line, not a lesson. This is the whole story.** The
measurement is in the spec's frontmatter and it is unambiguous: an agent given
*no* guidance solved this in three attempts; an agent given the mechanism stated
correctly but incompletely failed 3/3 and stopped searching. A prompt addition
that explains the tmpfs and leaves the agent to derive the remedy is **worse than
nothing**. Write the executable form — the actual line that makes a toolchain
dependency survive into the gate — and keep it short enough that it reads as an
instruction rather than as background.

**Trap 2 — do not describe uv's answer as everyone's answer.** The runnable line
for a Python world is not the runnable line for a JavaScript one. If a single
universal line cannot be written, US1's guidance names the rule and points at the
declared-cache mechanism US2 adds, which *is* actionable. What it may never do is
name a mechanism and leave the recipe out (trap 1).

**Trap 3 — a declared bind is a hole in a verification boundary.** FR-007 bounds
it to the operator's home for a reason: a manifest that could bind `/` would make
the boundary decorative, and a target repository's manifest is written by whoever
controls that repository. Refuse at load time, name the path, and resolve
symlinks before deciding — a symlink inside home pointing outside it is the
obvious bypass.

**Trap 4 — preserve all three properties of the existing bind.** Writable,
conditional-on-existence, and paired with its environment variable. Each is
argued in the docstring and each was learned. A reimplementation that binds
read-only, or that fails when the path is missing, is a regression with a
rationale sitting three lines above it.

**Trap 5 — FR-006 is the regression surface.** Every existing manifest declares
no caches. The uv bind must keep happening for all of them, unchanged, which
means the new mechanism defaults to today's behaviour rather than replacing it.
Write that test over the supplied corpus.

**Trap 6 — US3's annotation must reach the retry.** An annotation added to a
record that the next attempt's prompt does not read is a comment. Follow the
existing path by which a gate's failure detail reaches the retry prompt
(`factory/workgraph/prompt.py` consumes gate results) and assert it end to end,
which is US3-S3.

**Trap 7 — signature matching, not output guessing.** US3 matches a known
install-a-toolchain signature. Keep the set small, explicit and anchored; a loose
match that annotates every failing gate with a HOME lecture is noise, and noise
in a retry prompt is the thing trap 1 warns about arriving by another route.

## Sizing

US1 is one prompt section and is the highest value-to-effort item in this
sprint — and the easiest to get wrong, in exactly one way (trap 1). US2 is the
epic's real work: a manifest key, a schema refusal, and a generalisation of a
function that currently returns one hardcoded path. US3 is small.

If an attempt is editing the tmpfs decision, the network posture, or
`_interpreter_binds`, it has gone outside the spec.

## Verification the operator will run, independent of the gate

The gate proves the binds are constructed. It cannot prove a browser survives to
gate time, because that needs a real browser and a real smoke gate. After US2
lands, in a target repository with a Playwright smoke gate declared:

```bash
eval "$(scripts/ergane-env.sh)"
# declare the browser cache in the target manifest, then run the gate alone:
uv run ergane verify <spec-dir> --target-repo <repo>      # or the gate runner directly
```

The demonstration succeeds when the smoke gate passes without the attempt having
re-downloaded anything, on a host whose cache is already warm. Paste the gate's
duration alongside the same gate's duration before the declaration — the
difference between a network-bound run and a warm one is the evidence, and it is
the same evidence `_cache_binds`' docstring cites for uv.
