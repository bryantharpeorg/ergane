# 049-US5 evidence

    $ uv run pytest -q
    2883 passed, 44 skipped, 5 warnings in 297.72s (0:04:57)

44 skips is the baseline (live tiers without credentials); this story adds none.
Five warnings, all pre-existing deprecations — `controlplane/config.py:177`,
`workgraph/worktree.py:156` and `:178`, `factory_yaml.py`'s legacy-name path.
One earlier full run, on the pre-`1ff351c` tree, reported six; every run since
reports five and the sixth was never identified. Nothing this diff adds calls
`warnings.warn`.

One production edit at a time, applied to a green *committed* HEAD, run over
`tests/test_forge_manifest.py tests/test_factory_yaml.py tests/test_forge_seam.py
tests/test_ergane_init.py` (155 tests), reverted with `git checkout HEAD --` and
the worktree confirmed clean at the end. Each edit is the one its test's
docstring names.

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

**One mutation came back green on its first run, and it changed the code.** The
first M9 was "remove the `path.is_file()` guard from `_manifest_forge_name`" —
all 155 green. The guard was dead: an absent manifest leaves
`load_factory_config` as a `FactoryConfigError` with rule `missing_manifest`,
which the tolerance three lines below already answered with the default. Two
paths to one answer, and no test could hold the second. The guard was deleted
(`1ff351c`), `test_a_repository_with_no_manifest_still_resolves_the_default_forge`
now names the mutation that does kill it — M8 — and M9's slot was refilled with
the dataclass-default half of the three-way spelling pin. The numbers above are
that second run.

**The two mutations that pull opposite ways are the point of M7 and M8.** M7
(swallow every refusal) is the silent fallback US5-S2 forbids at the door; M8
(re-raise every refusal) makes a forge lookup the first place an operator meets
an unrelated manifest defect. Neither shortcut passes both tests, which is what
makes the rule — *a complaint about the `forge` key travels, every other
complaint belongs to the reader that owns it* — a tested rule rather than a
comment.

## Scope fence (US5-S4, FR-015)

    $ git diff --stat $(git merge-base HEAD origin/ergane-buildout) -- ergane.yaml
    (no output)

M11 is the assertion's own control: adding `forge: github` to `ergane.yaml`
turns `test_this_repositorys_own_manifest_does_not_spend_the_key` red. In the
factory it fails earlier and far more expensively — the config gate parses a
node's manifest with the worker's *installed* parser, so the key is a
`CONFIG_ERROR` in 0.0s until this story lands and the worker restarts.
