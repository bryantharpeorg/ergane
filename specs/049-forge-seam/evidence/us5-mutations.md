# 049-US5 evidence

    $ uv run pytest -q
    2975 passed, 44 skipped, 6 warnings in 307.10s (0:05:07)

44 skips is the baseline (live tiers without credentials); this story adds none.
Six warnings, all pre-existing — see *The `.pyc` cache* below for why that number
moves between runs and why it is not this diff.

Re-run whole after rebasing onto `fb9f25a`, over 049-US3 (`6ca7211`) and
048-US4 (`c00c998`); the counts below are identical across both bases. One edit at a
time, applied to a green *committed* HEAD, run over
`tests/test_forge_manifest.py tests/test_factory_yaml.py tests/test_forge_seam.py
tests/test_ergane_init.py` (156 tests), reverted with `git checkout HEAD --`, the
worktree confirmed clean at the end. **Every run purges every `__pycache__` under
the worktree and executes with `PYTHONDONTWRITEBYTECODE=1`** — see below. Each
edit is the one its test's docstring names.

| edit | tests red |
|---|---|
| M1 `forge` is not a top-level key | 11 · declared-name refused ×5, S1 fixture, S2 refusal, corpus, both door tests, interview keys |
| M2 the absent key resolves something other than `github` | 11 · S3 default, corpus, scope fence, contract example, 2 schema-bump, door, 4 · `ergane init` |
| M3 an unregistered forge falls back to the default | 3 · S2 refusal, corpus, door refusal |
| M4 the refusal stops listing the registered forges | 1 · S2 refusal |
| M5 a declared non-name is treated as absent | 5 · declared-name refused (all five cases) |
| M6 the door ignores what the manifest declares | 2 · door builds declared, door refusal |
| M7 the door swallows every manifest refusal | 1 · door refusal |
| M8 the door re-raises every manifest refusal | 2 · broken-elsewhere, no-manifest |
| M9 the parser's constant and the dataclass default disagree | 4 · one-spelling, contract example, 2 schema-bump |
| M10 `DEFAULT_FORGE` and the parser's constant disagree | 9 · one-spelling and everything that resolves a forge |
| M11 `ergane.yaml` spends the key | 1 · scope fence (US5-S4) |
| M12 the key reaches the parser but not the interview | 8 · interview keys, 6 · `ergane init`, offered defaults |
| M13 the landing door builds a forge the repository never declared | 1 · every-door sweep |

Thirteen edits, thirteen kills, no survivors.

**The two mutations that pull opposite ways are the point of M7 and M8.** M7
(swallow every refusal) is the silent fallback US5-S2 forbids at the door; M8
(re-raise every refusal) makes a forge lookup the first place an operator meets
an unrelated manifest defect. Neither shortcut passes both tests, which is what
makes the rule — *a complaint about the `forge` key travels, every other
complaint belongs to the reader that owns it* — a tested rule rather than a
comment.

## The mutation that survived, and its re-test

An earlier battery's M9 was "remove the `path.is_file()` guard from
`_manifest_forge_name`", and it came back **green**. The guard was dead: an
absent manifest leaves `load_factory_config` as a `FactoryConfigError` with rule
`missing_manifest`, which the tolerance three lines below already answered with
the default. Two paths to one answer, and no test could hold the second. The
guard was deleted (`b676585`), the test now names the mutation that does kill it
(M8), and M9's slot was refilled with the dataclass-default half of the
three-way spelling pin.

That survival was later suspected of being a stale-`.pyc` artefact, so it was
reconstructed with bytecode out of play — caches purged, `PYTHONDONTWRITEBYTECODE=1`
— by putting the guard back and taking it out again:

    A. pre-fix code: the `path.is_file()` guard is present
      purged 14 __pycache__ dirs; PYTHONDONTWRITEBYTECODE=1
      _manifest_forge_name('/nonexistent-repo-for-m9') -> github
      156 passed in 0.84s

    B. M9 applied: the guard is removed (this is the shipped code)
      purged 0 __pycache__ dirs; PYTHONDONTWRITEBYTECODE=1
      _manifest_forge_name('/nonexistent-repo-for-m9') -> github
      156 passed in 0.83s

The survival is real: the function answers `github` either way and the same 156
tests pass either way. The guard was inert, and deleting it was right.

## The `.pyc` cache, and the warning count

CPython validates a cached `.pyc` on `(source mtime in whole seconds, source
size)` only, so two mutants of one file with the same size written inside one
wall-clock second let the second run execute the *first* one's bytecode. That
fails toward green — it reads as an under-kill — which is why every run above
purges the caches and forbids writing new ones.

The same mechanism explains a wobble that went unexplained on the first pass:
full-suite runs reported five warnings or six, seemingly at random. The sixth is
`tests/test_ergane_status.py:161`'s pre-existing `SyntaxWarning: invalid escape
sequence '\.'`, and a `SyntaxWarning` fires at **compile** time, so a run with a
warm `__pycache__` never sees it:

    $ find . -name __pycache__ -not -path ./.venv/* -exec rm -rf {} +
    $ uv run pytest -q tests/test_ergane_status.py
    .../tests/test_ergane_status.py:161: SyntaxWarning: invalid escape sequence '\.'
    21 passed, 1 warning in 1.76s

    $ uv run pytest -q tests/test_ergane_status.py     # caches now warm
    21 passed in 1.05s

Not this diff, and not a flake: a cold cache reports six, a warm one five.

## Scope fence (US5-S4, FR-015)

    $ git diff --stat $(git merge-base HEAD origin/ergane-buildout) -- ergane.yaml
    (no output)

M11 is the assertion's own control: adding `forge: github` to `ergane.yaml`
turns `test_this_repositorys_own_manifest_does_not_spend_the_key` red. In the
factory it fails earlier and far more expensively — the config gate parses a
node's manifest with the worker's *installed* parser, so the key is a
`CONFIG_ERROR` in 0.0s until this story lands and the worker restarts.
