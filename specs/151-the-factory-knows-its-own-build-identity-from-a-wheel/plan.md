# Implementation Plan: the factory knows its own build identity from a wheel

Every `file:line` below was read from `ergane-buildout` at `602a92c` on
2026-09-04 and verified to resolve to the symbol named. Do not trust an anchor
that has moved; re-read before editing.

## What already exists, and where

**The version answer already exists and is already single.**
`factory/supervision/engine_identity.py:38` — `cli_version` is the tree's one
answer to "what version is this CLI", landed by 105 so that the CLI and the
container image could share one version. Its docstring says it falls back to the
literal `"unknown"` when the distribution is not installed, "which keeps the
banner and the handshake from raising". The resolver US1 adds sits beside it, in
that module, and calls it. The module is imported on the `build start` path and
its own docstring says heavier dependencies must not complicate that import;
respect that (FR-006, trap 10).

**The probe's git read, whole, and the two lines that raise.**
`factory/doctor/probes.py:161` — `_newest_factory_commit`:

```python
def _newest_factory_commit() -> tuple[int, str]:
    """Timestamp and sha of the newest commit touching `factory/`."""
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%ct %H", "--", "factory/"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise ServiceNotAnswering("git", reason=str(exc)) from exc
    line = result.stdout.strip()
    if not line:
        raise ServiceNotAnswering("git", reason="no commits touched factory/")
    timestamp_str, sha = line.split(" ", 1)
    return int(timestamp_str), sha
```

Two things to see. There is **no `cwd=` argument**, so this shells in the process
working directory (trap 2). And the pathspec is the literal `factory/`, relative
to that same directory — so anchoring the call on the package directory means the
pathspec has to change with it, or the read silently matches nothing and takes
the second raise at `factory/doctor/probes.py:174` — `_newest_factory_commit`
instead of the first. It has exactly one consumer,
`factory/doctor/probes.py:328` — `StaleWorkerProbe.gather`; nothing else in
`factory/` or `tests/` calls it.

**The snapshot names the git answer in its fields.**
`factory/doctor/probes.py:94` — `WorkerSnapshot`:

```python
@dataclass(frozen=True)
class WorkerSnapshot:
    """The stale-worker probe's snapshot."""

    worker_pid: int | None
    worker_start_timestamp: int | None
    newest_factory_commit_timestamp: int | None
    newest_factory_commit_sha: str | None
```

FR-011 is about these two names **and about the sentence they are rendered
into**. They are read in
`factory/doctor/probes.py:345` — `StaleWorkerProbe.evaluate`, which interpolates
them into the finding's summary at
`factory/doctor/probes.py:366` — `StaleWorkerProbe.evaluate`:

```python
                summary=(
                    f"factory worker pid {snapshot.worker_pid} started at "
                    f"{snapshot.worker_start_timestamp}, before newest `factory/` commit "
                    f"{snapshot.newest_factory_commit_sha} at "
                    f"{snapshot.newest_factory_commit_timestamp}"
                ),
                refs=[
                    f"process/start:{snapshot.worker_start_timestamp}",
                    f"git/timestamp:{snapshot.newest_factory_commit_timestamp}",
                    f"process/pid:{snapshot.worker_pid}",
                    f"git/commit:{snapshot.newest_factory_commit_sha}",
                ],
```

The `git/timestamp:` ref is `factory/doctor/probes.py:374` and the `git/commit:`
ref is `factory/doctor/probes.py:376`. Renaming the dataclass fields does not
touch any of this: see trap 14.

**`ServiceNotAnswering` takes a service and a reason, and both reach the
operator.** `factory/doctor/probes.py:34` — `ServiceNotAnswering` renders
`f"{service} is not answering"` plus the reason, and
`factory/cli/doctor.py:215` — `_run_one_probe` prints
`skipped ({exc.service} not answering)` followed by the exception text in
parentheses. So FR-010's "name both attempts" is satisfied by the `reason`
argument; the `service` token is the second half of the sentence the operator
reads and should stop saying `git` when git is only one of two things that were
tried.

**The exit-code arm is first and needs no edit.**
`factory/cli/doctor.py:188` — `_run_all_probes` ends with three arms; the skip
arm at `factory/cli/doctor.py:206` — `_run_all_probes` is the first of them, so
it wins over both the unexpected-error and the new-finding arms. It returns
`EXIT_TRANSPORT`, which `factory/cli/doctor.py` imports from
`factory.cli.errors`, where the value is `3` (`factory/cli/errors.py:26`). FR-009
says the diff must not touch this file: the exit code clears because nothing
skipped.

**`ergane --version`'s git block, and the placeholder.**
`factory/cli/main.py:132` — `_version_text`:

```python
    try:
        revision = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).resolve().parent,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except Exception:
        revision = "unknown"
```

That block is `factory/cli/main.py:136-144` — `try:` at 136,
`except Exception:` at 143 and the fallback assignment at 144. Cite the whole
range: an implementer who replaces `136-143` leaves the orphaned
`revision = "unknown"` behind. `revision` is interpolated into the first line at
`factory/cli/main.py:165` — `_version_text`. Note the comment above the endpoint
reads (048-US4, plan trap 12b): a broken config must not stop `--version`
answering, "it is the command run to find out what you have". FR-014 keeps that
property; the identity resolver must not raise into this function.

**The skew notice, whole.** `factory/cli/nouns/build.py:986` — `_skew_notice`:

```python
def _skew_notice(worker_revision: str | None, cli_revision: str | None) -> str | None:
    """A human-readable notice when the worker and CLI disagree, or None."""
    if worker_revision is None:
        return (
            f"worker revision is unknown (CLI revision {cli_revision or 'unknown'}); "
            "the worker predates this check or is not a git checkout"
        )
    if cli_revision is None:
        return None
    if worker_revision == cli_revision:
        return None
    return (
        f"worker is running different code: worker revision {worker_revision}, "
        f"CLI revision {cli_revision}"
    )
```

The first branch is the defect: on a packaged install `worker_revision` is always
`None`, so the first `return` fires on every call. The last `return` — the
revision-disagreement text — is what FR-017 requires unchanged. It is called at
`factory/cli/nouns/build.py:1173` beside `factory/cli/nouns/build.py:1171`, which
is where `_cli_revision` is read, both inside
`factory/cli/nouns/build.py:1119` — `_query_status`. `_query_status` prints the
notice to stderr as `f"ergane: {skew_notice}"` and returns `EXIT_OK`; that print
is what a US4 verification transcript captures.

**The worker's half of the wire.** `factory/worker.py:220` — `_worker_revision`
runs the same `git rev-parse --short HEAD` with `cwd=Path(__file__).resolve().parent`,
is captured once at import into `_WORKER_REVISION` (`factory/worker.py:240`), and
reaches the dispatch payload through the inbound interceptor: the guard at
`factory/worker.py:326` (`if getattr(original, "worker_revision", None) is None:`)
and the `replace(...)` at `factory/worker.py:327` that rebuilds the input. The
CLI never sets `worker_revision`, so that guard is true on every dispatch; FR-015's
new field is set on **that same `replace` call**, not on a second one and not
outside the guard, so the two values are written together or not at all. It lands
on `factory/workgraph/workflow.py:583` — `EpicInput`, is recorded by
`factory/workgraph/workflow.py:933` — `EpicWorkflow.run`, and is returned on
`factory/workgraph/workflow.py:689` — `EpicStatus` from
`factory/workgraph/workflow.py:910` — `EpicWorkflow.epic_status`. Those five
places are the shape FR-015's new field copies, with a default so an old payload
is still accepted.

**The offline way to prove "from a wheel" is already written.**
`tests/test_installed_layout.py:72` — `_installed_layout` builds
`<tmp>/site-packages/factory/` the way a wheel install does, and
`tests/test_installed_layout.py:93` — `_run_probe` runs a probe script in a
subprocess with `PYTHONPATH` naming that directory, `PATH=/usr/bin:/bin` and a
`HOME` under the temporary path. The module docstring states why the suite does
not build a real wheel: hatchling is not a dependency of this project's test
environment and fetching it "would put a network round trip inside a four-minute
gate". It also states the discipline that matters here — the probe script proves
*which* `factory` it imported before it proves anything else, so a leaked
checkout on `sys.path` cannot make the test pass for the wrong reason. Copy that
shape (trap 9).

## Traps

**Trap 1 — The hand-over names a dead call site; fixing it changes nothing.**
The source document points at `factory/doctor/cli.py:242` — `_run_probe`. That
function's only consumer is line 225 of its own module, and the only name the CLI
imports from `factory/doctor/cli` is `_resolve_store_path` — used at
`factory/cli/doctor.py:70` — `_store_path` and at
`factory/cli/nouns/spec.py:1258`. The live path is
`factory/cli/doctor.py:177` — `doctor_command` to
`factory/cli/doctor.py:188` — `_run_all_probes` to
`factory/cli/doctor.py:215` — `_run_one_probe`. An implementer who edits the dead
one will ship a story whose tests pass and whose behaviour is unchanged, because
`ergane doctor` never enters that module. FR-007 and FR-009 are about the live
path only. The dead module carries its own `EXIT_TRANSPORT` constant with the
value `2`; the live one is `3`. Reading the wrong module is how the wrong number
gets into a runbook.

**Trap 2 — The probe's git read is unanchored, and anchoring it means moving the
pathspec too.** `factory/doctor/probes.py:161` — `_newest_factory_commit` passes
no `cwd=`, so it questions the process working directory's repository — verified
during triage by executing it from a freshly initialised unrelated repository,
where it skips identically. The wrong move is to add `cwd=Path(__file__).resolve().parent`
and stop: the pathspec `-- factory/` is then relative to the *package* directory,
which contains no `factory/` subdirectory, so the command succeeds with empty
output and takes the "no commits touched factory/" raise at
`factory/doctor/probes.py:174` — `_newest_factory_commit` instead. The whole
probe is still lost and the test that "proves" the anchoring will have been
written against a mock. FR-002.

**Trap 3 — The skip is not cosmetic: it forces the exit code, and the arm is
first.** `factory/cli/doctor.py:206` — `_run_all_probes` returns `EXIT_TRANSPORT`
on any skip, ahead of the unexpected-error and new-finding arms, so
`ergane doctor` can never return `0` on a host where git does not answer. The
temptation is to "fix" this by making the skip arm forgiving. Do not: FR-009
requires the diff to leave `factory/cli/doctor.py` alone. If you find yourself
editing that file, the design is wrong — the exit code is a consequence of a
probe that no longer skips.

**Trap 4 — Git answers for a copy that is not the checkout, measured on this
floor.** `/home/admin/code/ergane/.venv/lib/python3.13/site-packages/factory`
exists on this host and sits *inside* the repository;
`git -C <that directory> rev-parse --short HEAD` returns `602a92c` — the
checkout's HEAD — for a directory that is an install artefact. Anchoring on the
package directory (FR-002) fixes the *wrong repository* case and does not fix
this one, because there is no honest way to fix it: a package inside a work tree
is inside that work tree. That is why FR-004 exists. An implementer will be
tempted to treat a git answer as authoritative and drop the source label as
redundant; the label is the only thing that lets a reader tell "this revision
describes the code you are running" from "this revision describes the repository
the code happens to sit in". It is also why the US1 fixture must place its copy
under the test's temporary path, which is outside every work tree, rather than
somewhere convenient inside the repository — a fixture built inside the tree
passes with the defect live.

**Trap 5 — N13 and N5 are two implementations, not one, and this floor has three
dated instances of declaring a half-fix whole.**
`factory/cli/nouns/build.py:966` — `_cli_revision` and
`factory/cli/main.py:132` — `_version_text` each shell
`git rev-parse --short HEAD` with `cwd=Path(__file__).resolve().parent` and each
swallows the failure its own way — one to `None`, one to the literal `"unknown"`.
They are separate code in separate files with separate consequences and the
ledger's separate keys are both correct. Specs 100, 092 and 118 each declared a
key whose defect they had only half reached; the tell was a `fixes:` list longer
than the FRs justified. Here US3 owns `_version_text` (FR-012..FR-014) and US4
owns `_cli_revision` (FR-019), and neither may declare the other done. FR-019 is
the requirement that keeps US4 honest: without it a diff could rewrite
`_skew_notice`, satisfy FR-016 through FR-018, and leave the fourth git shell in
`factory/cli/nouns/build.py` standing.

**Trap 6 — Do not change what `_worker_revision` returns.**
`factory/worker.py:220` — `_worker_revision` feeds two consumers: the query
answer, through the interceptor's `replace` at `factory/worker.py:327`, and
`factory/versioning.py:94` — `resolve_deployment_version`, which raises
`VersioningRefused` (`factory/versioning.py:60` — `VersioningRefused`) when
versioning is engaged and the revision is `None`. `factory/versioning.py` says
why in its own module docstring: "a version nobody can map back to a commit is a
version nobody can redeploy, and every epic pinned to it is stranded". The
obvious move for FR-016 — make `_worker_revision()` return a version string when
git has no answer — silently converts that refusal into a bad build id, and no
test in US4 would catch it. Add the identity in a **new** field beside
`worker_revision` (FR-015); leave the old one exactly as it is.

**Trap 7 — Every existing stale-worker test exercises `evaluate`, and the defect
is in `gather`.** `tests/test_doctor_probes.py:86` — `TestStaleWorkerProbe`
constructs a `WorkerSnapshot` by hand and calls `evaluate`; all four of its tests
pass today on a host where the probe is permanently skipping, because none of
them ever calls `gather`. A US2 test written in the same shape proves nothing at
all. US2-S1 and US2-S4 are the two that must drive `gather`, and US2-S1 must
drive it in a layout with no git answer — which is the point of trap 9's
technique. Note what US2-S1's control is and is not: it is a proof that the
*fixture* has no git answer, run in that layout. It is **not** a call on
`_newest_factory_commit`, because T015 removes that function — a control written
against deleted code either forces a dead helper to be kept alive or cannot be
read in the diff at all.

**Trap 8 — The CLI noun seam is package-level for a reason, and patching the
module object will not bind.**
`factory/cli/nouns/__init__.py:37` — `_cli_revision_for_tests` exists because
`factory.cli.main` discovers noun
modules by `exec_module`-ing each file into a fresh module object, so a
`monkeypatch` on the test file's imported `build` module does not reach the
object the parser's `set_defaults(run=...)` references.
`factory/cli/nouns/build.py:966` — `_cli_revision` already consults that seam
first, before shelling git. A US4 test that patches `factory.cli.nouns.build._cli_revision`
directly will look green in isolation and prove nothing about the command; put
the new identity behind the same package-level seam or reuse it. FR-019 requires
the seam to keep working, which is why `factory/cli/nouns/__init__.py` is a file
US4 may touch and is counted in its sizing.

**Trap 9 — Two landed techniques prove "from a wheel". Use the one your story
needs, know that the other one already runs your code, and invent no third.**
An earlier draft of this plan claimed there was only one; the tree holds both.

*(a) The offline one, which US1 and US2 use.*
`tests/test_installed_layout.py:72` — `_installed_layout` and
`tests/test_installed_layout.py:93` — `_run_probe` are the shape: a synthetic
`site-packages/factory` under `tmp_path`, a subprocess with `PYTHONPATH` naming
it, a scrubbed `PATH` and `HOME`, and a probe script that first asserts *which*
`factory` it imported. The package is 146 Python files and 3.3 MB excluding
`__pycache__`, so a `copytree` with `ignore=shutil.ignore_patterns("__pycache__")`
is affordable; copying only the modules under test is the alternative but the
transitive import closure of `factory/supervision/engine_identity.py` reaches
`factory/registry.py`, which imports `factory.controlplane.config` and
`factory.verify.factory_yaml`, so the "small" copy is not small. The docstring of
that test module states why *it* does not build a wheel: hatchling is not a test
dependency of this project's environment and fetching it would put a network
round trip inside a four-minute gate. Read that as a statement about that
module's own cost, not as a tree-wide ban — US1 and US2 need a fixture per case,
and a wheel build per case is unaffordable.

*(b) The real one, which is already landed and already runs US1's and US3's
code.* `tests/test_distribution_install.py:39` — `_build_wheel` copies the
tracked tree with `git checkout-index`
(`tests/test_distribution_install.py:49`), builds a wheel with `uv build --wheel`
(`tests/test_distribution_install.py:98`), and
`tests/test_distribution_install.py:163` — `_InstallFixture` installs it into a
clean virtual environment under `tmp_path` whose `PATH` holds no checkout. Two
landed tests then run the real console script out of that install:
`tests/test_distribution_install.py:207` — `test_clean_install_version_reports_built_version`, which asserts
`f"ergane {TEST_VERSION}" in result.stdout`
(`tests/test_distribution_install.py:218`), and
`tests/test_distribution_install.py:268` — `test_installs_alongside_unrelated_ergane_distribution`, which runs
`ergane --version` at `tests/test_distribution_install.py:323`. The first of
those is US3's defect, already automated and already green: it passes today
while the line it reads says `ergane 99.88.77 (unknown)`, because it asserts the
prefix and says nothing about the parenthetical. So it does not go red when US3
lands — but it *pins the prefix*: a first line that stops beginning
`ergane <version>` breaks a landed test. Know it is there before you redesign
that line.

What is refused is a **third** technique and a **second** wheel build. Do not
add one to US1, US2 or US3.

**Trap 10 — Do not add a second *version* lookup; that is the defect class. One
`distribution()` call is not that, and FR-003 needs it.**
`factory/supervision/engine_identity.py:38` — `cli_version` already wraps
`importlib.metadata.version("ergane-cli")` and already returns `"unknown"` on
failure. What must not be duplicated is **the version answer**: a resolver that
calls `importlib.metadata.version` again — because reaching for `cli_version()`
felt indirect — recreates in one story exactly the shape this spec exists to
collapse, several implementations of one question drifting apart. That is FR-006.
Read how US1-S5 makes it provable before you write that test, because the
obvious reading is a trap of its own: the literal text
`importlib.metadata.version` occurs **zero** times in that module.
`factory/supervision/engine_identity.py:45` holds
`from importlib.metadata import version` and
`factory/supervision/engine_identity.py:47` holds `return version("ergane-cli")`,
so a test that counts that string finds nothing, and the cheapest way to make it
find one is to add the dotted call FR-006 forbids. Count call sites over the
module's parsed syntax tree, following the from-import binding. And do not
"fix" `factory/supervision/container_project.py:157`, which binds the same
lookup as `_distribution_version` for the engine image: it is pre-existing, it
answers a different question, no story here owns that file, and FR-006 is scoped
to the resolver's own module for exactly that reason — an implementer who greps
the tree to check the FR will otherwise find an apparent violation and try to
repair it. What is explicitly **blessed** is exactly one
`importlib.metadata.distribution("ergane-cli")` call: FR-003's stamp comes from
the distribution's own on-disk files, and there is no way to reach those through
`cli_version()`, which returns a string. Expect that call in the diff; do not
read US1-S5 as forbidding it, and do not invent a clock-based stamp to avoid it —
see trap 11.

**Trap 11 — The distribution's stamp must come from the distribution, not from
the clock and not from the package's own mtime.** FR-003. `importlib.metadata`
resolves `ergane-cli` to a `.dist-info` directory whose files are written at
install time; on this host that directory is
`.venv/lib/python3.13/site-packages/ergane_cli-0.5.0.dist-info` and its metadata
file's mtime is the install moment. A stamp taken from `datetime.now()` makes
every worker look fresh and silently disables `ops/stale-worker` a second way; a
stamp taken from the imported module's own mtime is a copy artefact, not an
install. The property FR-003 is really asking for is the one the probe needs: a
reinstall of the same version must move the stamp. That is what the probe's own
note is about — read it as it is written, at
`factory/doctor/probes.py:378` — `StaleWorkerProbe.evaluate`:

```python
                notes=(
                    "The e5c5569 incident class: an activity-code fix dispatched by a "
                    "worker still running old code. Restart the worker before trusting "
                    "verification results."
                ),
```

`e5c5569` is a 2026-08-07 commit to `factory/mergequeue/gh.py`: a **checkout**
incident, on this floor, which the probe catches today. The note does not name an
upgrade and does not name a packaged install — an earlier draft of this plan and
of the triage document both claimed it did, and the line refutes them. New code
under a running worker is the class; on a packaged install that code arrives
through a reinstall rather than a commit, which the ledger already records as a
still-open CRITICAL row (a same-version reinstall replacing 534 lines across
three files under an identical version string). A stamp that does not move on
reinstall makes the probe blind to exactly that, so US1-S2's control — rewrite
the metadata file, the stamp moves; touch the package, it does not — is the
assertion that decides FR-003 inside the diff rather than in an operator's
terminal a week later.

**Trap 12 — The host's own `ergane-cli` distribution answers from inside the
fixture, and the control US1-S2 mandates would rewrite it.** This is trap 4's
reasoning carried to the distribution arm, where it has a second edge: a write.
The subprocess `tests/test_installed_layout.py:93` — `_run_probe` starts is
`sys.executable` with `PYTHONPATH` naming the synthetic `site-packages`, and
that interpreter still puts its own `site-packages` on `sys.path`, so
`importlib.metadata.distribution("ergane-cli")` resolves to
`.venv/lib/python3.13/site-packages/ergane_cli-0.5.0.dist-info` — measured by
execution on this host during this refinement, and present in any gate venv.
Two consequences, and a careless test passes on both. The positive half of
US1-S1 goes green for an ambient reason: a resolver that never looks at the
package directory and simply calls `importlib.metadata` satisfies it, which is
the "what would pass if production code did nothing" failure. And US1-S2's
control — rewrite the metadata file, the stamp moves — rewrites a `METADATA`
file inside the venv the gate itself runs from, outside `tmp_path`; this floor
already has a dated instance of a test-obeyed destructive write. The remedy is
one more line of fixture: write a synthetic
`ergane_cli-<version>.dist-info/METADATA` into `tmp_path/site-packages` beside
the package copy. `PYTHONPATH` precedes the interpreter's own `site-packages`
on `sys.path` and `importlib.metadata` returns the first match, so the synthetic
one wins — also verified by execution here. Then assert the resolved
distribution's own location lies under `tmp_path` **before** asserting anything
about the stamp and before rewriting anything. FR-003, T001.

**Trap 13 — Eight landed tests in two modules drive this skew path, and three of
them assert the sentence FR-018 deletes.** An earlier draft of this plan said
`tests/test_ergane_build_status_refusal.py` was *the* module that exercises
`ergane build status` end to end, and named six tests in it. Both counts were
short. Read the whole list before you move `_skew_notice`'s signature.

*Seven in `tests/test_ergane_build_status_refusal.py`*, landed by 053-US3 in the
same commit that created the package-level seam trap 8 cites. Its harness is
`tests/test_ergane_build_status_refusal.py:34` — `_invoke`, which runs the real
command, `tests/test_ergane_build_status_refusal.py:353` — `fake_revision_client`,
which stubs the client,
`tests/test_ergane_build_status_refusal.py:309` — `_query_document`, which
builds the wire document — **with no identity field, which is why FR-021 and
trap 15 exist** — and
`tests/test_ergane_build_status_refusal.py:366` — `_set_cli_revision`, which patches
the package-level seam. The seven are
`tests/test_ergane_build_status_refusal.py:375` — `test_skew_is_visible_when_worker_revision_differs`,
`tests/test_ergane_build_status_refusal.py:395` — `test_skew_is_visible_in_json_when_worker_revision_differs`,
`tests/test_ergane_build_status_refusal.py:419` — `test_skew_is_silent_when_revisions_match`,
`tests/test_ergane_build_status_refusal.py:440` — `test_skew_is_silent_in_json_when_revisions_match`,
`tests/test_ergane_build_status_refusal.py:459` — `test_skew_degrades_when_worker_revision_is_unknown`,
`tests/test_ergane_build_status_refusal.py:478` — `test_skew_degrades_in_json_when_worker_revision_is_unknown`
and
`tests/test_ergane_build_status_refusal.py:501` — `test_worker_revision_is_recorded_once_and_carried_not_recomputed`.
The `--json` half reads the notice under `skew_notice` at
`tests/test_ergane_build_status_refusal.py:412`,
`tests/test_ergane_build_status_refusal.py:455` and
`tests/test_ergane_build_status_refusal.py:495`.

*One in `tests/test_ergane_build.py`*, missed by the earlier draft entirely. The
test itself predates the skew work (`6cda411`, 019-US3), but its skew assertions
were added by the same `0ae48d6` that landed the seven above:
`tests/test_ergane_build.py:790` — `test_status_json_is_the_query_result_verbatim`
drives `build status --json`
through a live Temporal environment and a real worker, and asserts
`"skew_notice" in result.json` at `tests/test_ergane_build.py:811` and
`"unknown" in result.json["skew_notice"].lower()` at
`tests/test_ergane_build.py:812`. Its worker comes from
`tests/test_ergane_build.py:631` — `build_worker_for_test`, whose docstring says
it builds "a worker in tests without the production revision interceptor", so
`worker_revision` is `None` (asserted at `tests/test_ergane_build.py:810`) and
the new identity field will be defaulted-absent too. That is FR-018's row
exactly, and line 812 asserts the literal substring `unknown` inside the very
sentence FR-018 abolishes.

*Three assertions go red when T033 lands*, and the cheapest green for all three
is to keep today's fixed sentence — which leaves every new US4 test green while
silently un-doing FR-018:
`assert "worker revision is unknown" in result.stderr.lower()` at
`tests/test_ergane_build_status_refusal.py:474`,
`assert "unknown" in notice.lower()` at
`tests/test_ergane_build_status_refusal.py:497`, and
`assert "unknown" in result.json["skew_notice"].lower()` at
`tests/test_ergane_build.py:812`. Rewrite all three to the new text (T028).

The other five — the four revision tests and
`tests/test_ergane_build_status_refusal.py:501` — `test_worker_revision_is_recorded_once_and_carried_not_recomputed`, whose
`assert WORKER_REVISION_A in result.stderr` at
`tests/test_ergane_build_status_refusal.py:540` reads the same warning through
`_query_status` — are FR-017's own regression and their assertions stay
byte-identical, **but only under FR-021**: every one of them builds a document
with a bare `worker_revision` and no identity, so a rewrite that reads that
shape as "resolved nothing" turns all five red at once and tells you so far too
late. All eight also encode the two-argument
`_skew_notice(worker_revision, cli_revision)` shape that T033 changes, so all
eight have to be read before the signature moves. This is the diligence trap 7
performs for US2's analogous module, owed to US4 as well.

**Trap 14 — Renaming the snapshot's fields does not rename the sentence the
operator reads, and the sentence is where the lie lands.** FR-011. The two field
names are half of it; the other half is
`factory/doctor/probes.py:366` — `StaleWorkerProbe.evaluate`, whose summary
interpolates them into "before newest `factory/` commit {sha} at {timestamp}",
and the two refs at `factory/doctor/probes.py:374` and
`factory/doctor/probes.py:376`, which prefix them `git/timestamp:` and
`git/commit:`. On a distribution-sourced identity there is no revision — row two
of the spec's truth table — so an implementer who renames the dataclass and
stops ships a CRITICAL finding reading "before newest `factory/` commit None"
with a `git/commit:None` ref, on the one install shape this whole spec exists to
serve, and it is the finding the operator reads at step 3 of the verification
sequence below. Read T011 as it is now written: what may not drift is the key,
the category and the `Severity.CRITICAL` (FR-008). The summary and the refs are
FR-011's to change, and a test that pins them field-for-field is a test that
forbids the fix.

**Trap 15 — A worker running the old code sends a bare revision and no identity,
and that is every call until someone restarts it.** FR-021. The obvious way to
write `_skew_notice`'s new signature is to take two identities and treat a
missing one as "this side resolved nothing" — FR-018 — because that is what a
missing identity looks like from inside the function. It is wrong for the case
that dominates the calendar: for the whole window between this story landing and
an operator restarting the worker, the worker's payload carries a real
`worker_revision` and no identity at all, and reading it as FR-018 prints a
warning on every single call. That is the operator key's own symptom, reopened
one row over, and it would ship green because every *other* new test in phase 4
supplies both identities. It is also the shape of every landed test in trap 13:
`tests/test_ergane_build_status_refusal.py:309` — `_query_document` has no
identity field and nothing in US4 adds one to it. FR-021 says what to do
instead — a bare revision is a revision-only side, compared by revision when the
other side carries one and silent when the other side carries a version but no
revision, which is exactly today's behaviour in both cases; a side that resolved
nothing at all is still FR-018's. T029 is where it is proven.

## Sizing

**US1** adds a frozen dataclass and one resolver to
`factory/supervision/engine_identity.py` and touches no other production file.
Its tests are one new module built on the `tests/test_installed_layout.py`
technique, plus a fixture that initialises two throwaway git repositories for
US1-S3 and writes a synthetic `ergane_cli-<version>.dist-info/METADATA` into the
same `tmp_path/site-packages` the package copy goes into — so the distribution
the resolver finds is the fixture's and not the host's, and the file US1-S2
rewrites is the fixture's too (trap 12). It edits no landed test module, but one
landed module already rebuilds and runs what it writes:
`tests/test_distribution_install.py:39` — `_build_wheel` copies the tracked tree
with `git checkout-index` (`tests/test_distribution_install.py:49`), so anything
this story commits travels into that wheel, and the explicit `shutil.copy2`
block at `tests/test_distribution_install.py:57-79` — which exists for edits
that are not yet committed — already names
`factory/supervision/engine_identity.py`
(`tests/test_distribution_install.py:59-62`). US1's resolver therefore runs
inside the two real-install tests trap 9 names. Read them before assuming this
story touches no landed test.

**US2** rewrites `factory/doctor/probes.py:161` — `_newest_factory_commit` into a
call on the resolver, renames two fields on
`factory/doctor/probes.py:94` — `WorkerSnapshot`, and follows those two names
through `factory/doctor/probes.py:345` — `StaleWorkerProbe.evaluate`. It touches
`factory/doctor/probes.py` and — by FR-009 — **no other production file**, in
particular not `factory/cli/doctor.py`. Its tests amend
`tests/test_doctor_probes.py` (the four constructions in
`tests/test_doctor_probes.py:86` — `TestStaleWorkerProbe` move to the new field
names) and add one installed-layout module for the gather.

**US3** touches `factory/cli/main.py` only: the git block at
`factory/cli/main.py:136-144` becomes a resolver call and
`factory/cli/main.py:165` — `_version_text` renders from the identity. Its tests
are one new module — and one landed module it does not edit but must read.
`tests/test_distribution_install.py:39` — `_build_wheel` copies
`factory/cli/main.py` into the wheel it builds
(`tests/test_distribution_install.py:58`) and
`tests/test_distribution_install.py:207` — `test_clean_install_version_reports_built_version`
then runs `ergane --version`
out of a real install of it and asserts `f"ergane {TEST_VERSION}"` is in stdout
(`tests/test_distribution_install.py:218`). That assertion is the closest thing
in the tree to the operator's step 1 below, it passes today while printing
`(unknown)`, and it pins the first line's `ergane <version>` prefix (trap 9).

**US4** touches four production files: `factory/cli/nouns/build.py`
(`_skew_notice`, whatever replaces `_cli_revision` under FR-019, and the two
lines that feed the notice at `factory/cli/nouns/build.py:1171` and
`factory/cli/nouns/build.py:1173`), `factory/cli/nouns/__init__.py` (the
package-level seam at `factory/cli/nouns/__init__.py:37` — `_cli_revision_for_tests`,
kept or joined by one beside it — trap 8),
`factory/worker.py` (one new capture beside `factory/worker.py:240` and one value
added to the existing `replace` at `factory/worker.py:327`), and
`factory/workgraph/workflow.py` (one defaulted field on
`factory/workgraph/workflow.py:583` — `EpicInput`, one on
`factory/workgraph/workflow.py:689` — `EpicStatus`, one line in
`factory/workgraph/workflow.py:933` — `EpicWorkflow.run` and one in
`factory/workgraph/workflow.py:910` — `EpicWorkflow.epic_status`). Its tests
amend **two** landed modules, not one (trap 13):
`tests/test_ergane_build_status_refusal.py` — the seven landed 053-US3 skew
tests running from
`tests/test_ergane_build_status_refusal.py:375` — `test_skew_is_visible_when_worker_revision_differs`
to
`tests/test_ergane_build_status_refusal.py:501` — `test_worker_revision_is_recorded_once_and_carried_not_recomputed`,
two of which assert the sentence FR-018 deletes — and
`tests/test_ergane_build.py`, whose
`tests/test_ergane_build.py:790` — `test_status_json_is_the_query_result_verbatim`
asserts that same sentence a
third time at `tests/test_ergane_build.py:812`, over a worker deliberately built
without the revision interceptor
(`tests/test_ergane_build.py:631` — `build_worker_for_test`). It then adds one
test for the payload default, one for the legacy revision-only payload FR-021
decides, and one that drives
`factory/cli/nouns/build.py:1119` — `_query_status` over a stubbed status
document, built on the refusal module's
`tests/test_ergane_build_status_refusal.py:353` — `fake_revision_client` and
`tests/test_ergane_build_status_refusal.py:366` — `_set_cli_revision` helpers.

Over that corrected list, US2, US3 and US4 still name no production file in
common: US2 is `factory/doctor/probes.py` alone, US3 is `factory/cli/main.py`
alone, and US4's four files — `factory/cli/nouns/build.py`,
`factory/cli/nouns/__init__.py`, `factory/worker.py` and
`factory/workgraph/workflow.py` — appear in no other story. The only file all
four stories name is `factory/supervision/engine_identity.py`, and only US1
writes it. No test module is shared either: US1 and US3 both *read*
`tests/test_distribution_install.py` and neither edits it, so the
`concurrent_with` overrides stand.

All four are well inside the 64 KiB deterministic diff bound (D-050). The largest
is US4 at four production files, none of which takes more than a dozen changed
lines, and the pasted evidence each verification task asks for is a short
transcript rather than a log.

## Verification the operator will run, independent of the gate

Per constitution VIII and D-037 the judge sees the diff and the criteria only, so
runtime evidence is committed as pasted output. Beyond that:

1. In a scratch virtual environment, `pip install` the built wheel — or copy the
   package into a directory outside every git work tree — and run
   `ergane --version`. The first line must name a version and a stamp, and must
   not contain `(unknown)`.
2. Run `ergane doctor` in that same environment and read the **exit code** with
   `echo $?`. It must be `0` when nothing is wrong. Before this spec it is `3` on
   every run, because the stale-worker skip takes the first arm at
   `factory/cli/doctor.py:206` — `_run_all_probes` and that arm returns
   `EXIT_TRANSPORT`, which is `3` (`factory/cli/errors.py:26`). Do not expect
   `2`: that is the value of the same-named constant in
   `factory/doctor/cli.py`, the module trap 1 declares dead.
3. Start a worker in that environment, then reinstall the same version of the
   package under it, then run `ergane doctor` again. `ops/stale-worker` must now
   fire — the reinstall moved the stamp and the worker predates it. This is the
   packaged form of the incident the probe's note names — new code running under
   a worker that started before it — and it is the falsifiable test of the whole
   spec: it is the check that has never once run on the install shape this
   project recommends.
4. Run `ergane build status <epic-id>` in that environment against a running
   epic. No worker-revision warning may appear on stderr when the two sides
   agree: that is row two of the comparison table in `spec.md` § "The rule this
   spec is asking for" — both sides distribution-sourced, same version, FR-016 —
   and it is the row the operator key was filed on. Then run the same command
   from the checkout against a worker started from the packaged install. That is
   the **mixed** row, FR-020: a warning must appear and must name both sources
   and both values. Read the table before calling any observed outcome a defect;
   an earlier draft asserted this second outcome while no FR required it, which
   is how an operator ends up filing a finding against a story that met its own
   criteria. One precondition for that second run: the packaged worker must have
   been **restarted** since this spec landed. A worker still running the old code
   sends a bare revision and no identity, which is FR-021's row and is silent by
   design — read a silence there as the upgrade window, not as a defect.
   This is the live half of US4; the node's own evidence (T035) drives
   `_query_status` over a stubbed document instead, because a node worktree has
   no control plane and no packaged worker.
5. From the checkout, run `ergane doctor` with the process working directory set
   to an unrelated git repository (`cd /tmp/some-other-repo && ergane doctor`).
   The stale-worker probe must report the same verdict it reports from the
   repository root. Before this spec it skips there, which is trap 2 with the
   wheel removed from the story entirely.
