# 157-US1 qualification evidence

The story's diff-visible record: the red runs of the three test slices, the
green run on the declared gate, and the six fresh-session discovery
observations the acceptance scenarios name. Bytes charged against the same
64 KiB budget as the code (`DIFF_INPUT_LIMIT`, `factory/verify/diffbounds.py`).

## US1-S1 — canonical-content and compatibility contracts, red

Against the tree as received (no `AGENTS.md`, `CLAUDE.md` a regular file):

```
$ uv run pytest tests/test_operator_instructions.py -q
FAILED ...::test_the_canonical_orientation_exists_and_is_tracked
FAILED ...::test_the_compatibility_entry_point_is_tracked_as_a_symlink
FAILED ...::test_the_compatibility_entry_point_resolves_into_the_repository
FAILED ...::test_the_compatibility_entry_point_serves_the_canonical_bytes
FAILED ...::test_it_begins_with_the_dispatched_node_guard
FAILED ...::test_it_names_the_active_manifest_and_the_legacy_one
FAILED ...::test_the_manifest_it_applies_to_is_ergane_yaml
FAILED ...::test_it_carries_an_observation_versus_action_boundary
8 failed, 4 passed
```

The four passing are the contracts the current `CLAUDE.md` already satisfied
(authority map, its heading, the live-state commands, the guard-mutation
control); each red test fails on the clause it enforces — file type, guard as
first prose, the manifest pair, the observation heading. The four passing
tests pass on the same content after the move; the 19 sweeps of
`test_claude_md.py` pass before and after with no weakening (same extractors,
same required path set).

## US1-S2 — six-context discovery records, red

```
$ uv run pytest tests/test_operator_instructions.py -q
8 failed, 26 passed   # the 8 above still red; the 18 parser params green
```

The parser contracts pass at commit time because the records they parse were
committed in the same commit; the observation-contract tests fail only while
the orientation itself is missing (the S1 eight). The vacuity control
(`test_the_parser_actually_reads_the_records`) fails on a missing record,
proving the sweep reads.

## US1-S3 — semantic action boundary, red

```
$ uv run pytest tests/test_operator_instructions.py -q
12 failed, 36 passed   # the 8 above; +4 observation-section contracts red
```

Red because the observation section does not exist. The ten grant mutations
each prove the recipe-opener sweep fires (`test_a_granted_action_is_rejected`
was made to pass before the section existed, against mutated section text).

## Green on the final state

```
$ uv run pytest tests/test_operator_instructions.py tests/test_claude_md.py -q
67 passed in 0.22s

$ uv run pytest tests/test_claude_md.py -q
19 passed in 0.17s

$ uv run pytest tests/test_operator_instructions.py -q
48 passed in 0.13s
```

Full declared gate (`ergane.yaml` declares `uv run pytest -q`):

```
5987 passed, 58 skipped, 16 warnings in 604.90s (0:10:04)   # run 1, 14:04 UTC
5987 passed, 58 skipped, 15 warnings in 597.73s (0:09:57)   # run 2, after the commit
```

Collected: 6,045 now against 5,997 at the base commit — the delta is exactly
the 48 tests the new file adds. After run 2 the host's `/etc/resolv.conf`
mount lost its backing file (a host-level state change, reproduced with a bare
`bwrap` outside the repository and identical on the untouched base tree: the
18 boundary-suite failures that then appear are byte-identical on both trees
and predate this story's files — see the attempt archive note
`host-incident-resolv-bwrap.md`). The warnings are the pre-existing
deprecation/Temporal noise.

### The gate deadline, measured (2026-09-09, attempt 2)

The declared gate has no `timeouts:` block, so its deadline is the code
default `gate_timeout_s: 600` (`factory/verify/models.py:1209`), and the
suite's own duration now sits on that wall. Three runs against this tree:

```
bare host, alone                    PASS 5987/58   suite 599.45s   margin  0.55s
boundary (factory run_gates bwrap, tmpfs HOME), alone
                                    PASS 5987/58   suite 598.77s   margin  1.23s
boundary, overlapping another suite TIMEOUT at 600.3s (killed mid-run)
```

Attempt 1's gate TIMEOUT is this wall, not these files: the suite takes the
whole default deadline, and contention or the resolv.conf incident above tips
it over. The deadline is an operator declaration — spec 121's committed guard
(`test_this_repositorys_node_worktree_agrees_with_the_landing_branch`) fails
any node worktree whose `ergane.yaml` differs from the landing branch's copy,
so a node cannot declare `timeouts:` itself. Recorded for the operator:
raising `timeouts: {test: …}` in `ergane.yaml` on the landing branch is the
one-line fix, and it takes effect for every attempt after the next dispatch
pins its base ref.

## The six fresh-session discovery observations (2026-09-09)

Clients: `codex-cli 0.153.4` (standalone release, staged from the pinned
`rust-v0.153.4` GitHub release into the worktree's git-ignored `.cache/`) and
`Claude Code 2.1.261`. No credential stored, no `codex login` run, no trust
granted, no client configured; both drivers ran real turns through the
existing LiteLLM proxy on `ollama-cloud/glm-5.3-flash` — the gateway route the
plan declares. Marker = a hex-ish token planted in a scratch instruction file;
the client was asked to echo what its instructions contained, or NONE.

| # | client | shape | instruction file present | observed |
| --- | --- | --- | --- | --- |
| 1 | codex | repo root | `AGENTS.md` | **loaded** (marker echoed; one `AGENTS.md instructions for <cwd>` block) |
| 2 | codex | nested dir | parent's only | **not loaded** (reply `NONE`; no `agents_md.instructions` item, `world_state.agents_md` empty) |
| 3 | codex | git worktree root | worktree's own | **loaded**; with **symlink** → parent file: **resolved** |
| 4 | claude | repo root | symlinked `CLAUDE.md` | **loaded** (marker echoed through the symlink) |
| 5 | claude | nested dir | symlinked `CLAUDE.md` | **loaded** |
| 6 | claude | git worktree root | symlinked `CLAUDE.md` | **loaded**; absolute and relative targets both resolved (reply NONE with no instruction file in reach — a worktree does not see the parent checkout's file) |

Claude does not read `AGENTS.md` (probe: planted `AGENTS.md` alone → NONE), so
the compatibility entry point is load-bearing. Codex's worktree stop is the
node-guard contract: a worktree sees no ancestor policy, which is exactly the
shape a dispatched node runs in.

Token counts corroborate each claude observation: 16,634 input without any
instruction file, 16,715–17,008 with one (the delta is the file). The exact
prompts, replies and counts are the committed fixture records under
`tests/fixtures/operator-instructions/`, parsed by
`tests/test_operator_instructions.py`.

## Verification

- `git diff --check` clean over the story diff.
- No spec state changed (frontmatter untouched); constitution and decision log
  unchanged.
- No runtime store, registry, credential, service, or ref written: the probes
  used scratch homes under `/tmp` (removed after measurement) and the
  worktree's git-ignored `.cache/`.
- Story diff: 61,584 bytes measured with `git diff <base>..HEAD` against the
  65,536-byte refusal (`DIFF_REFUSAL_THRESHOLD`,
  `factory/verify/diffbounds.py`).