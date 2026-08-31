# Attempt 1 — US3: the roadmap dial is reconciled against the file

## T024 — the operator's demonstration

The plan's § *Verification the operator will run* asks for a target repo with a
configured, commented manifest: a clean tree, `sha256sum ergane.yaml`, `ergane
init --wire --non-interactive`, the checksum again, `git diff --stat`, and
`ergane init --check`.

**Two substitutions, stated first.**

1. **The repository is a scratch one, not the operator's floor.** Everything
   below runs in `/tmp/us3-demo/repo` with `ERGANE_STATE_HOME`,
   `ERGANE_CONFIG_PATH` and `ERGANE_ROOT` pointed at `/tmp/us3-demo/state`, so
   the run touches no registry, no control-plane config and no repository of
   the operator's. Its `ergane.yaml` is hand-written and committed, and it
   declares one key from every group a rewrite has to carry — `standards`, the
   `roadmap` dial, a `ladder` block, a `verify` list — under 14 lines of prose
   that no emitter in this tree can reproduce.
2. **No schedule is published.** `127.0.0.1:7233` is open and it is the
   operator's live Temporal, holding the real `ergane-roadmap` schedules; the
   `temporal` CLI is not on this host's PATH, so the throwaway-namespace route
   the 034 evidence used is not available either. Creating a schedule for a
   `/tmp` directory on that server is the exact accident
   `tests/test_ergane_init_schedule.py` records having paged the operator once.
   So the init runs below have **no control-plane config**, which makes init
   refuse to publish — the documented 050/FR-001 path, and a *failed step*
   rather than a lost scaffold — and the reconciliation report itself, which is
   what US3 changes, is produced in § 4 through the production `_schedule` with
   only the Temporal transport bound to the in-memory `FakeScheduleServer`.

Everything below is pasted tool output.

### 1. The checksum demonstration

```text
$ git -C /tmp/us3-demo/repo stash list && git -C /tmp/us3-demo/repo status --short
(both empty: clean tree)

$ sha256sum ergane.yaml   # before
8ab3caa126c245e035e2382459283678c5ec4ab2d955d4173899209033391c2d  ergane.yaml

$ uv run ergane init --wire --non-interactive /tmp/us3-demo/repo
ergane: github wiring needs an authenticated GitHub CLI, and `gh` refused: You are not logged into any GitHub hosts. To log in, run: gh auth login
  [manual wiring steps]
the repo-local half of init is complete and unchanged in /tmp/us3-demo/repo:
  gates workflow: applied
    wrote .github/workflows/ergane-gates.yml, one job per declared gate (test); commit it — the queue cannot require a check nothing produces
applied default: repo slug = "repo"
EXIT=1

$ sha256sum ergane.yaml   # after
8ab3caa126c245e035e2382459283678c5ec4ab2d955d4173899209033391c2d  ergane.yaml

$ git diff --stat
(empty)

$ git status --short
?? .github/
?? .gitignore
```

**The two checksums match and `git diff --stat` is empty**, which is what the
demonstration was for. `gh` is unauthenticated on this host, so `--wire` refuses
at the forge boundary and exits 1 — and that refusal is itself US1-S2's point
seen from the other side: the manifest is untouched, the workflow file is still
written, and the manual steps are printed. `.github/` and `.gitignore` are new
untracked files, not modifications; nothing tracked changed.

### 2. The same command with the forge half not attempted, run to completion

```text
$ uv run ergane init --non-interactive /tmp/us3-demo/repo
applied default: repo slug = "repo"
joined /tmp/us3-demo/repo as slug 'repo'
kept: /tmp/us3-demo/repo/ergane.yaml is valid and was left unchanged
written:
  /tmp/us3-demo/repo/.gitignore
  /tmp/us3-demo/repo/.ergane
registered: 'repo' -> /tmp/us3-demo/repo (already recorded)
control plane: not readable — ControlPlaneConfigError: /tmp/us3-demo/state/control-plane.toml: [config_missing] cannot be read (No such file or directory); run `ergane install` to create the control-plane config
schedule: failed ergane-roadmap-repo — refused: the control plane could not be read, so no schedule was created — [...] — and `ergane install` is what creates it; a schedule for this repository would otherwise have gone to Temporal at localhost:7233 in namespace 'ergane' (built-in default)
github wiring: not attempted — re-run with `ergane init --wire` to
  queue the landing branch and require one check per declared gate
EXIT=0

$ sha256sum ergane.yaml   # after the second run
8ab3caa126c245e035e2382459283678c5ec4ab2d955d4173899209033391c2d  ergane.yaml
```

`kept: … is valid and was left unchanged` is US1 talking, and the checksum is
the same for the third time. The `schedule: failed` line is substitution 2: no
control-plane config, so nothing was published.

### 3. `init --check`, and what the manifest still declares

```text
$ uv run ergane init --check /tmp/us3-demo/repo
ergane readiness for /tmp/us3-demo/repo (ergane.yaml)
  [PASS] resolved_root: this report is about /tmp/us3-demo/repo
  [PASS] registry_entry: registered as 'repo' in /tmp/us3-demo/state/ergane/repos.json
  [PASS] landing_branch: landing branch 'main' exists
3 of 7 checks failed
EXIT=1
```

The three failures are `repo_read` (no `gh` auth), `control_plane` and
`roadmap_schedule` (no control-plane config) — every one of them an artefact of
the two substitutions above, and none of them about the manifest, which the
check loaded and did not complain about. Reported rather than tidied away: the
plan asked that `--check` still pass, and on a scratch host with no forge login
and no control plane it cannot, so this is the honest state instead of a green
line.

What the file still says after three runs of the verb that used to flatten it:

```text
$ uv run python -c "…load_factory_config('/tmp/us3-demo/repo/ergane.yaml')…"
standards        = docs/STANDARDS.md
roadmap.cadence_s= 900
ladder           = 4 1
verify_order     = ('gates', 'diff_check')

$ grep -c '^\s*#' /tmp/us3-demo/repo/ergane.yaml
14
```

Before this spec the same sequence removed `standards`, the whole `ladder`
block and every one of those comment lines, and `init --check` called the result
valid.

### 4. The report US3 changes, all three scenarios

Production `_schedule` → `desired_for_repo` → `apply_schedule`, against the
same committed manifest; only `_schedule_client_factory` is the in-memory fake,
per substitution 2.

```text
$ uv run python /tmp/us3-demo/report.py
--- US3-S1  manifest declares cadence_s: 900, schedule runs every 300s
schedule: updated ergane-roadmap-repo — reconciled to the manifest — cadence_s: schedule has 300, manifest declares 900

--- US3-S2  manifest and schedule both say 900s
schedule: unchanged ergane-roadmap-repo — already satisfied; nothing changed

--- US3-S3  the same manifest with its roadmap block removed
schedule: created ergane-roadmap-repo — created, starting roadmap-specs every 300s over /tmp/us3-demo/repo/specs (note: LITELLM_PROXY_URL is unset, so child epics cannot issue keys)
  ergane.yaml declares no roadmap dials, so the cadence and concurrency above are Ergane's defaults rather than this repository's declaration — add a `roadmap:` block to steer them
```

S1 names both numbers and reconciles to the declared one; S2 says the two agree
and writes nothing; S3's second line is the whole of the change — `every 300s`
is `RoadmapDials()`'s fallback, and before this story it reached the operator's
transcript in the position where every other number on that line came off their
file.

### 5. The three claims, red on the parent commit

The production change reverted, the tests left alone:

```text
$ git checkout HEAD~1 -- factory/cli/init.py
$ uv run pytest tests/test_120_reconciled_against_the_manifest.py -q
E  AssertionError: schedule: failed ergane-roadmap-app — the manifest just written did not
   load: …/app/ergane.yaml: [missing_manifest] cannot be read (No such file or directory);
   every target repo must commit a ergane.yaml declaring its gates
FAILED …::test_a_legacy_named_manifest_is_still_the_manifest_it_reconciles_against
FAILED …::test_the_dial_is_read_from_the_manifest_init_judged_not_from_disk_after
FAILED …::test_a_manifest_declaring_no_dial_is_reported_as_declaring_none
3 failed, 4 passed, 1 warning in 0.99s

$ git checkout HEAD -- factory/cli/init.py
$ uv run pytest tests/test_120_reconciled_against_the_manifest.py -q
7 passed, 1 warning in 0.33s
```

The four that pass either way are US3-S1's ordinary vehicle and the three
controls — US1 already fixed the plain disagreement, and they are pinned so it
stays fixed. The three that flip are what this story adds: the manifest init
judged is the object reconciled against, a manifest the resolver finds under its
legacy name is still that manifest, and an undeclared dial is named rather than
filled in.

The quoted failure is worth reading twice. `_schedule` asked `repo_root /
MANIFEST_NAME` while every other reader in the tree — `_existing_manifest` and
`--check` both — asks `resolve_manifest_path`, so on a repository still
committing `factory.yaml` the reconciliation reported that a manifest it had
never been asked about could not be read, three lines above a check that named
the drift in that same file correctly. One verb, two readers, two answers about
one file, which is the shape FR-010 is written against.

### 6. The declared gate

```text
$ uv run pytest -q
5551 passed, 58 skipped, 7 warnings in 418.82s (0:06:58)
```

## What this story did not change

The spec says US3 is not a reconciliation feature, and it is not. A repository
declaring no dial still gets `RoadmapDials()` on its schedule — the same
cadence, the same two concurrency bounds — and
`test_saying_so_does_not_change_what_the_schedule_gets` holds it there. What
changed is that the operator is told where those numbers came from.

Nor is the pre-write manifest used where a write *was* the request. Trap 7 asks
for the file as it stood before any write, and on the non-interactive path that
is the whole story: nobody was asked anything, so the file is the only thing
speaking, and the manifest `init_command` already loaded is handed down. When
init does write a manifest the caller passes `kept=None` and the reconciliation
reads the file back, because there the write is the declaration — an operator
who has just answered the interview asked for those dials, and 034/US6-S2
(`test_declared_dials_reach_the_schedule_and_a_re_run_reconciles_them`) is the
landed requirement that says so.
