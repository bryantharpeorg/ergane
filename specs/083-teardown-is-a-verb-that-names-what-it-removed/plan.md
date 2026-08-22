# Implementation Plan: teardown is a verb that names what it removed

**Spec**: `specs/083-teardown-is-a-verb-that-names-what-it-removed/spec.md`

## What already exists, and where

**Every line number below was verified on 2026-08-21 by printing that exact line
individually** (`sed -n '<n>p' <file>`). Check each one anyway.

**US1 — the critical's surface, `factory/cli/repo.py`:**

- `:307` — `def repo_forget_command(args: argparse.Namespace) -> int:`
- `:308-323` — its docstring, stating the ordering contract: *every refusal is
  taken before any act*, `--export` before `--clean-runtime`, `--clean-runtime`
  last. FR-003's refusal joins the front of that list; nothing else moves.
- `:337` — `runtime_root = runtime_root_for(entry.path)` — the resolution under
  test, and the one that stays.
- `:344-345` — `if clean_runtime:` / `_refuse_while_epics_run(slug)` — the exact
  place FR-003's refusal belongs beside.
- `:385-387` — the act and the print, ending
  `print(f"emptied {runtime_root} ({emptied} entr{'y' if emptied == 1 else 'ies'})")`.
  **The path is already printed.** Do not rebuild this.
- `:388-393` — the legacy-root disclosure: `left {legacy} alone; it is a second
  runtime root this repo never migrated, and only the resolved one is emptied`.
  **This is the shape US1 copies** — the verb already knows how to name a root it
  did not touch, just not for the override case.
- `:400` — `def runtime_root_for(repo: Path) -> Path:`, and `:403-410`, the
  paragraph that refuses the environment on purpose, ending `the environment is
  not consulted here for that reason, and the result is a child of 'repo' by
  construction rather than by check.` Read it before writing a line of US1.
- `:424` — `def _refuse_export_inside_runtime_root(destination: Path, runtime_root: Path) -> None:`
- `:436` — `def _refuse_while_epics_run(slug: str) -> None:`
- `:458` — `def _refuse_unsafe_removal(root: Path) -> None:` — the D-045-shaped
  guard, whose docstring argues in the tree that an acknowledgment escape hatch
  for a deletion is "a door with no user". That is why FR-003 has no `--anyway`.
- `:487` — `def _empty_runtime_root(root: Path) -> int:`
- `:66-71` — the import block. **`RuntimeRootChoice` (`:69`) and
  `resolve_factory_root` (`:70`) are already imported here.** US1 adds no import.
- `:529` — `root, choice, source = resolve_factory_root()` and `:531` — `if
  choice is RuntimeRootChoice.OVERRIDE:`, whose refusal at `:534-537` reads
  `f"{source} is set to {root}; ..."`. **The precedent for detecting and naming
  an override, inside this very file.** US1 reuses that detection and discloses
  where migrate refuses.

**US1 — the resolver, `factory/workgraph/worktree.py`:**

- `:133` — `class RuntimeRootChoice(StrEnum):`, with `OVERRIDE = "override"` at
  `:138`.
- `:145` — `def resolve_factory_root(`, returning
  `tuple[Path, RuntimeRootChoice, str | None]` (`:147`).
- `:165-170` — the override branch, ending
  `return override, RuntimeRootChoice.OVERRIDE, source`. **The path, the choice
  and the variable name are all three already returned.** FR-002 needs no new
  detection code, only the reporting.

**US1 — the committed test that pins today's behaviour:**

- `tests/test_ergane_repo_forget.py:287` —
  `def test_clean_runtime_empties_the_entrys_root_and_not_the_environments(`
- `:296-298` — its docstring sentence, which begins mid-line at `:296`: `A
  --clean-runtime that asked resolve_factory_root() — which reads exactly those
  variables — would empty the decoy and leave this repo's root full.`
- `:314-318` — the assertions, including `assert result.code == EXIT_OK` and
  `assert (decoy / "doctor.db").exists()`. The test seeds the entry's root, so
  `emptied > 0` and FR-003's refusal does not fire on it. **It must stay green
  and must not be edited.**

**US2 — `factory/supervision/units.py`:**

- `:56` — `SLICE_UNIT = "ergane.slice"`; `:57-61` name the other five units.
- `:74-77` — the comment explaining that neither the slice nor the probe
  *service* is enabled, because the slice is pulled in by `Slice=` lines. **This
  is deliberate on the install side.**
- `:81` — `ENABLE_TARGETS = (WORKER_UNIT, BRIDGE_UNIT, TEMPORAL_UNIT, PROBE_TIMER)`
- `:245` — `def generated_files(layout: InstallLayout) -> tuple[GeneratedFile, ...]:`
- `:259` — `GeneratedFile(SLICE_UNIT, _slice_text(layout), units),` — the slice
  **is** written by install and **is** removed by uninstall; only the stop is
  missing.
- `:471` — `class UninstallReport:`, with `removed: tuple[str, ...]` at `:474`
  and `kept: tuple[str, ...]` at `:475`. **The names are already on the object.**
- `:477` — `def render(self) -> str:`, whose `:478` is
  `lines = [f"removed {len(self.removed)} file(s)"]` — the whole defect — while
  `:479` already renders `kept` by name. Only `removed` is reduced to a count.
- `:466` — the sibling line in `InstallReport.render`:
  `lines += [f"  left alone (not written by ergane): {n}" for n in self.kept]`
  — match its voice.
- `:528` — `def uninstall(`
- `:539-545` — the open-epic refusal, read before any command is issued. Correct;
  keep it first.
- `:549-554` — `for name in ENABLE_TARGETS:` issuing
  `systemctl --user disable --now <name>`, with the comment at `:551-553`
  explaining that disabling *before* deleting is deliberate.
- `:556-566` — the removal loop and the manifest unlink; `:568` —
  `runner(("systemctl", "--user", "daemon-reload"))`

**US2 — the CLI surface, `factory/cli/nouns/worker.py`:**

- `:29` — `def _uninstall(_args: argparse.Namespace) -> int:`
- `:30-31` — `report = uninstall(resolve_layout())` then `print(report.render())`.
- `:60` — `remover = verbs.add_parser("uninstall", help="remove exactly what install wrote")`

**US3 — where the code goes. Two files, and the plan names both:**

- **The noun shim: `factory/cli/nouns/uninstall.py`.** Thirteen lines, copied
  from `factory/cli/nouns/repo.py` — a `Noun(...)` literal with `name`,
  `summary`, `order` and `add_parser`, and nothing else. `class Noun:` is at
  `factory/cli/nouns/__init__.py:25`. Pick an `order` beside the other lifecycle
  verbs: `factory/cli/nouns/install.py:166` is `order=5`,
  `factory/cli/nouns/worker.py:67` is `order=6`, `factory/cli/nouns/init.py:11`
  is `order=10`, and `factory/cli/nouns/repo.py:11` is `order=43`.
- **The logic: `factory/cli/uninstall.py`**, a new module beside
  `factory/cli/init.py`, `factory/cli/install.py`, `factory/cli/repo.py` and
  `factory/cli/roadmap.py`. That is the house split — every noun shim under
  `factory/cli/nouns/` delegates its `add_parser` to a module in `factory/cli/`,
  which is where the command bodies live. `factory/cli/nouns/repo.py:6` imports
  `add_repo_parser` from `factory.cli.repo`; the new shim imports
  `add_uninstall_parser` from `factory.cli.uninstall` the same way.
- **The seam is a module-level step table in `factory/cli/uninstall.py`**, not
  an argument threaded through the command. One frozen record per step carrying
  (a) the step's name, (b) a **survey** callable that only reads — is a repo
  registered, are units installed, what would be removed — and (c) a **perform**
  callable that acts. `--check` calls surveys and never touches perform. The
  real run calls survey then perform. Tests replace the whole table with
  recording records; that is the one seam US3 adds, and it is entirely inside
  the new module. See "The ruling on composition" below for why it is there and
  not underneath the three commands.
- `factory/cli/main.py:5` — `factory/cli/nouns/`; adding one is adding a file,
  removing one is deleting it,` — the discovery contract, in the module
  docstring.
- `factory/cli/main.py:65` — `for module_info in pkgutil.iter_modules([package_path]):`
- `factory/cli/nouns/repo.py` — thirteen lines, the whole shape of a noun module
  that delegates its parser to a `factory/cli/` module. Copy it.
- `factory/cli/nouns/install.py:130-132` — `"--verify"`, `action="store_true"`,
  help `skip the interview: probe the declared subsystems and report one finding
  per check`.
- `factory/cli/init.py:343-345` — `"--check"`, `action="store_true"`, help
  `judge this repository's readiness and exit; writes nothing`. **`writes
  nothing` is the promise FR-010 has to keep.**

**US3 — the steps teardown composes:**

- `factory/cli/roadmap.py:123` — `pause = verbs.add_parser("pause", help="pause dispatch")`
- `factory/cli/roadmap.py:310` — `async def roadmap_pause_command(...)`, whose
  docstring at `:311-319` says a schedule-owned roadmap pauses at the schedule
  and a run with no schedule the client can name is *signalled* with a caveat on
  stderr. `:328-330` is that path. Read it before wiring step one.
- `factory/cli/repo.py:307` — the forget command, step two.
- `factory/supervision/units.py:528` — `uninstall(`, step three.
- The two open-epic seams are **not** the same function, and US3 needs both.
  `factory/cli/repo.py:96` — `async def _running_epic_ids() -> set[str]:` — is
  what `_refuse_while_epics_run` calls at `factory/cli/repo.py:445`, through the
  module-level `_temporal_client_factory` at `factory/cli/repo.py:93`; it takes
  no injection parameter, so the committed tests replace it by monkeypatching
  the module attribute (`tests/test_ergane_repo_forget.py:90`). Uninstall reads
  a *different* one: `factory/supervision/units.py:622` —
  `def _open_epic_ids() -> tuple[str, ...]:` — which `uninstall()` already
  accepts as an override through its `open_epics` parameter at
  `factory/supervision/units.py:532`. T033's step table therefore has one real
  parameter to pass and one module attribute to patch, not one shared seam.

## The ruling on composition — read this before writing US3

The draft named this problem in US3's Sizing and declined to solve it. Declining
is what made SC-006 unprovable, so it is ruled here.

**The three steps have three incompatible shapes.** All three verified:

- `roadmap_pause_command(args: argparse.Namespace) -> int`
  (`factory/cli/roadmap.py:310`) — connects inline through `_connect()`
  (`factory/cli/roadmap.py:189`), which calls `Client.connect` at
  `factory/cli/roadmap.py:193`. `grep -n "Client.connect" factory/cli/roadmap.py`
  returns that one line and nothing else: **there is no module-level client
  seam in that file.** It is `async`, and `factory/cli/roadmap.py:125` wraps it
  for argparse with `_run_async` (`factory/cli/roadmap.py:180`, which is
  `asyncio.run(command(args))` at `:184`). It prints to stdout.
- `repo_forget_command(args) -> int` (`factory/cli/repo.py:307`) — synchronous,
  with a real module-attribute seam at `factory/cli/repo.py:93`
  (`_temporal_client_factory`) that the committed tests replace
  (`tests/test_ergane_repo_forget.py:90`).
- `uninstall(layout, *, run=None, open_epics=None)`
  (`factory/supervision/units.py:528`) — not a command at all, with real
  injection *parameters* at `factory/supervision/units.py:531` and `:532`.

**THE RULING: teardown calls those three as they stand, behind its own step
table. It does not extract a library layer beneath them, and it does not edit
`factory/cli/roadmap.py`.**

Each record's `perform` builds the `argparse.Namespace` that step needs and
calls the existing entry point — `asyncio.run(roadmap_pause_command(ns))` for
step one, in the same shape `factory/cli/roadmap.py:180-184` already uses;
`repo_forget_command(ns)` for step two; `uninstall(resolve_layout())`
(`factory/supervision/units.py:165`) for step three. Teardown captures each
step's stdout and folds it into its own report.

Three reasons, in the order they matter:

1. **It is what makes `--check` conclusive.** FR-010 asks for a dry run that
   performed nothing. With the seam in teardown's own table, `--check` proves it
   by never reaching a `perform` at all — a substituted recording table that
   stays empty is the whole evidence, and it needs no Temporal fake, no systemd
   fake and no filesystem fake to be believed. With the seam pushed down into
   the three commands, the proof becomes three separate negative assertions
   against three different fakes, one of which (`factory/cli/roadmap.py`) does
   not exist and would have to be built.
2. **It avoids the 085 collision.** Trap 14. Adding the missing client seam to
   `factory/cli/roadmap.py` is the one edit that puts this story in the same
   file 085's US3 is rewriting, in the same landing window.
3. **It keeps the blast radius inside the new module.** Extracting a library
   layer means refactoring three live call paths that operators use directly.
   FR-017 and US3-S6 are the control that says those three did not move; a
   library extraction is a diff that has to argue its way past that control
   instead of trivially satisfying it.

**What this rules OUT, so nobody re-litigates it in an attempt:** no new seam in
`factory/cli/roadmap.py`; no `_pause_command_factory`-style module attribute
added to any of the three modules; no lifting of `roadmap_pause_command`'s body
into a `factory/roadmap/` helper. If an implementer becomes convinced the ruling
cannot be executed, that is an operator decision about landing order — say so
and stop, rather than opening `factory/cli/roadmap.py`.

**US4 — state, config and the refs:**

- `factory/registry.py:159` — `def resolve_state_home() -> Path:`; `:175` —
  `xdg = os.environ.get("XDG_STATE_HOME")` in `_xdg_state_home`.
- `factory/registry.py:68` — `DEFAULT_REGISTRY_REL = Path("ergane") / "repos.json"`
- `factory/controlplane/config.py:201` — `def resolve_config_path() -> Path:`;
  `:202` — its docstring line `Return the config path: env override, then
  XDG_CONFIG_HOME, then HOME.`; `:218` — `xdg = os.environ.get("XDG_CONFIG_HOME")`.
- `factory/cli/nouns/install.py:125` — the install help naming
  `~/.config/ergane/config.toml` as what install writes.
- `factory/locking.py:46` — `def lock_path_for(target: str | Path) -> Path:`;
  `:49` — `return path.with_name(path.name + ".lock")`.
- `factory/locking.py:68` — `handle = os.open(lock_file, os.O_CREAT | os.O_RDWR, 0o600)`
  and `:82-85` — the two nested `finally` blocks: `:83` unlocks
  (`fcntl.flock(handle, fcntl.LOCK_UN)`), `:85` closes (`os.close(handle)`).
  **Nothing unlinks the lock file, ever.** That is the whole mechanism behind the surviving
  `config.toml.lock`; `factory/cli/install.py:271`, `:357` and `:451` are the
  three sites that create it.
- `factory/workgraph/worktree.py:238-240` — `def branch_name(epic_id, node_id)`
  returning `f"factory/{epic_id}/{node_id}"`.
- `factory/workgraph/worktree.py:480` — `SALVAGE_REF_ROOT = "refs/salvage"`;
  `factory/workgraph/worktree.py:470` — the comment giving the full shape
  `refs/salvage/<epic_id>/<node_id>/attempt-<n>-<sha12>`;
  `factory/workgraph/worktree.py:483` — `def salvage_ref_namespace(epic_id, node_id)`,
  which is `SALVAGE_REF_ROOT/<epic>/<node>` and therefore **per node**.

**US4 — the ruling on what FR-015 prints. `ergane build salvage` cannot answer
this question, so teardown must not name it.**

The draft's FR-015 said teardown "MUST name the command that lists them" and
cited nothing but `SALVAGE_REF_ROOT`. The verb that exists is
`ergane build salvage` — `salvage_command` at `factory/cli/nouns/build.py:1244`,
parser at `factory/cli/nouns/build.py:1512`, whose description at
`factory/cli/nouns/build.py:1515-1518` reads *"Read-only. For every node of a
compiled graph, report the node's branch and tip, every per-attempt salvage ref
(refs/salvage/<epic>/<node>/attempt-<n>-<sha12>)…"*. Its first act is
`graph = load_workgraph(args.graph)` (`factory/cli/nouns/build.py:1263`): **it
is keyed by a compiled graph, and it reports one epic's nodes.** It cannot
enumerate every salvage ref on a host, which is the question a departing
operator is asking.

So teardown prints the raw incantations, verbatim, and does not name
`ergane build salvage`:

```
git for-each-ref refs/heads/factory/
git for-each-ref refs/salvage/
```

That is the same read the engine itself makes — `_read_salvage_refs`
(`factory/workgraph/worktree.py:810`) is one `for-each-ref`
(`factory/workgraph/worktree.py:823`), narrowed to a node's namespace. Teardown
counts with the same call, unnarrowed, and prints the command it used. An
operator can paste it; a test can run it. Both halves of FR-015 are then
falsifiable from the diff: the counts, and the two literal strings.

## Traps

**1. Do not adopt the environment override as the deletion target. This is the
whole spec.** The filed finding asks for exactly that and the finding is wrong.
`factory/cli/repo.py:403-410` documents the refusal and names the date this
repository lost its runtime root to a process acting on a root it had been
handed. `tests/test_ergane_repo_forget.py:287` is a committed test asserting the
current behaviour with a decoy `ERGANE_ROOT`. An implementer who "fixes the
finding" turns that test red, and turning it green again by editing it is how
2026-08-14 happens twice.

**2. The path is already printed.** `factory/cli/repo.py:387`. The finding says
the verb "must PRINT the path it actually cleaned" and it has done so all along.
What is missing is (a) any signal that this is a *different* root from the one
dispatch used and (b) any treatment of `0 entries` as suspicious. A diff that
adds a path print has closed nothing.

**3. Do not add `SLICE_UNIT` to `ENABLE_TARGETS`.** `factory/supervision/units.py:81`,
with `:74-77` explaining that the slice is pulled in by the `Slice=` lines and
enabling it would declare a `WantedBy` systemd then has to reconcile. That is a
statement about *install*. US2 stops the slice during *uninstall*, after the
enabled units are disabled, and US2-S4 is the control that proves install did
not move.

**3a. `factory/supervision/units.py:78-80` is a stale comment and contradicts the
line under it. Do not act on it.** It reads `TEMPORAL_UNIT ... is deliberately
not in this tuple`, and `:81` plainly contains `TEMPORAL_UNIT`. The tuple is
correct and `:74-77` is the comment that describes it; `:78-80` describes a shape
this file no longer has. T017 asserts all four names including
`ergane-temporal.service`, which is what `:81` holds today — an implementer who
reconciles the comment by editing the tuple turns the control red and changes
install, which is trap 3. Leave both the tuple and the comment exactly as they
are; correcting a stale comment is not this spec's diff.

**4. The refusal goes before the act, on every path.** The ordering contract at
`factory/cli/repo.py:308-323` and the open-epic refusal at
`factory/supervision/units.py:539-545` both exist because a half-teardown cannot
be told from a whole one afterwards. FR-003's new refusal is computed from
reads — resolver triple, `is_dir()`, emptiness — and all of them are safe before
the schedule delete. Put it beside `factory/cli/repo.py:344-345`, not down at
`factory/cli/repo.py:385`.

**5. There is no escape flag for FR-003.** `factory/cli/repo.py:458`'s docstring
argues the case in the tree: D-045 has an acknowledgment variable because a
sanctioned live smoke must open a real store, and "a door with no user is only a
way in." The refusal names two remedies that cost nothing — unset the override
and re-run, or drop `--clean-runtime` because there is nothing to clean. Adding
`--force` re-creates the silent-success path through a different door.

**6. A disclosure that always fires stops being read.** FR-004 and US1-S4. The
legacy-root line at `factory/cli/repo.py:388-393` is valuable because it appears
only when there is a second root. The override line must be the same: no
override, no line, output
byte-identical to today's. This is why US1 carries two controls and not one.

**7. `roadmap pause` can report success without having stopped dispatch.**
`factory/cli/roadmap.py:311-319` says so itself: a run with no schedule the
client can name is *signalled*, with the caveat on stderr rather than in the
output the operator asked for. US3-S5 makes that a refusal for teardown
specifically. Teardown may not read a warning on stderr as a completed step —
this is the same "success message for a thing that did not happen" the whole
spec exists to close.

**8. Teardown can delete the installation it is running from, and there is a
real check for that — not a principle.** `resolve_layout()`
(`factory/supervision/units.py:165`) already derives the two paths that *are*
"this installation", by construction rather than by literal: `install_root` from
`Path(__file__).resolve().parent.parent.parent`
(`factory/supervision/units.py:182`) — the repository root in a checkout,
`site-packages` in a wheel — and the interpreter from `sys.executable`
(`factory/supervision/units.py:186`). FR-018 is one containment test against
those two, taken before any step acts, in the shape of `_refuse_while_epics_run`
(`factory/cli/repo.py:436`): it either appears in the diff or it does not.

The hazard is not hypothetical. `--purge` empties the state home, and
`supervision_home()` (`factory/supervision/units.py:155`) puts everything
supervision generates *under* that state home — so a state home an operator has
pointed somewhere unfortunate is one `--purge` away from the field report
happening again. `install/restarting-the-worker-deletes-the-operator-cli` is an
open critical of exactly this family and **this spec does not close it**; the
`uv tool` installation stays out of scope (spec Assumptions). FR-018 bounds
teardown. It does not fix install.

**9. `--purge` faces the same override hazard US1 rules on.**
`factory/registry.py:159` and `factory/controlplane/config.py:201` both honour
environment overrides, and `--purge` deletes what they return. Trap 1's ruling
applies: decide which root is emptied, state it in the code, and disclose the
other. FR-014's implementer must write that decision down; the spec's
Assumptions section says so explicitly.

**10. The lock file is never unlinked by anything.** `factory/locking.py:68`
creates it with `O_CREAT`; `:83` unlocks and `:85` closes. So `repos.json.lock`
and `config.toml.lock` are permanent once created. US4-S3 is the test; do not fix
this by making `exclusive_lock` unlink on exit, which would race two processes
that both hold the path open.

**11. `kept` is already rendered by name; only `removed` is not.**
`factory/supervision/units.py:479` versus `:478`. US2 is a smaller diff than it
looks: the names are on the dataclass at `:474`, the renderer discards them, and
`InstallReport.render`'s sibling line at `:466` is the voice to match.

**12. The judge sees the diff and the criteria, nothing else** (Constitution
Principle VIII). Every SC needs committed, pasted output. SC-002 and SC-005 in
particular are *controls* — they are only evidence if the paste shows the
unchanged thing, so paste the before and the after, not a sentence saying they
match.

**13. One test file per story.**
- US1 → `tests/test_clean_runtime_names_the_root_it_did_not_clean.py`
- US2 → `tests/test_worker_uninstall_prints_its_manifest.py`
- US3 → `tests/test_teardown_owns_the_ordering.py`
- US4 → `tests/test_teardown_names_what_it_kept.py`

Do not extend `tests/test_ergane_repo_forget.py`. US1 needs its 287 untouched
and green, and a story that edits the file holding its own control invites the
judge to wonder which way the green went.

**14. Spec 085 is rewriting `factory/cli/roadmap.py` in the same landing window,
and this spec must not touch that file.**
`085-a-schedule-that-has-not-run-does-not-say-running`'s US3 rewrites two lines
in it: `factory/cli/roadmap.py:432` — `state = "paused" if
location.schedule_paused else "running"`, inside `_render_disposition` at
`factory/cli/roadmap.py:424` — and `factory/cli/roadmap.py:448` — `f"roadmap:
{'paused' if status.paused else 'running'}",` inside `_render_status` at
`factory/cli/roadmap.py:446`. **Both are US3 stories at the tail of their
chains**, so they land in the same window if the two epics run together. Nothing
in either work graph can stop a file collision — the factory schedules within a
spec, not across two — so the only thing keeping this window clean is this spec
staying out of that file. 085 has been told the same, and its plan records that
083 ruled itself out here; if this spec edits the file anyway, 085's anchors move
under it silently.

The temptation is specific, and it is why this trap is scope rather than a
footnote. `factory/cli/roadmap.py` has **no injectable Temporal client seam**:
`_connect()` at `factory/cli/roadmap.py:189` calls `Client.connect` inline at
`factory/cli/roadmap.py:193`, and `grep -n "Client.connect"
factory/cli/roadmap.py` returns that one line and nothing else. Compare
`factory/cli/repo.py:93` — `_temporal_client_factory: Callable[[],
Awaitable[Client]] = _open_client` — a real module-attribute seam that the
committed tests replace (`tests/test_ergane_repo_forget.py:90`). An implementer
trying to make teardown's pause step testable will notice the asymmetry and add
to `factory/cli/roadmap.py` the seam that file is missing. **Do not.**

The ruling above puts the seam in teardown's own step table, which needs no
change to `factory/cli/roadmap.py` at all: US3 *imports*
`roadmap_pause_command` (`factory/cli/roadmap.py:310`) and edits nothing. If you
believe the ruling cannot be executed, that is an operator decision about
landing order — say so and stop. Do not resolve it by editing the file, and do
not resolve it by rebasing blind onto whatever 085 landed there.

## Sizing

**US1 is small and is the highest-value story in the spec.** The resolver triple
already exists, both `resolve_factory_root` and `RuntimeRootChoice` are already
imported into the file, the disclosure has a working precedent eight lines away,
and the refusal has a working precedent in the same function. The work is one
comparison, one conditional print, one refusal, and five tests. A second attempt
here almost certainly means trap 1 — an implementer who read the finding instead
of the plan and retargeted the deletion.

**US2 is small.** One `render()` rewrite, one extra systemd command in the
uninstall sequence, and the control. The likely cause of a second attempt is
trap 3: reaching for `ENABLE_TARGETS` because it is the tuple the loop iterates.

**US3 is medium and is the largest story here.** Two new files —
`factory/cli/nouns/uninstall.py` (thirteen lines) and `factory/cli/uninstall.py`
(the step table, the report, the refusals) — a `--check` that must genuinely do
nothing, the refusal propagation, and two controls.

The draft called the `--check` the risk *because* the three existing commands
are written for direct invocation and have three different injection shapes.
That is still true and it is no longer an open question: **"The ruling on
composition" above settles it** — the seam is the step table in
`factory/cli/uninstall.py`, `perform` is never reached under `--check`, and none
of the three commands is reshaped. An implementer who re-opens that question
will end up in `factory/cli/roadmap.py`, which is trap 14 and the most expensive
way to fail this story.

The remaining second-attempt risks, in order: **trap 14** (editing
`factory/cli/roadmap.py` and colliding with 085 at landing), **trap 7**
(`roadmap pause` reporting success for a run it only signalled), and FR-017's
control (a diff that satisfies teardown by moving the three commands beneath
it). FR-018's refusal is small — one containment test against two values
`resolve_layout()` already returns.

**US4 is medium.** Two removal paths with opposite defaults, the lock-sibling
sweep, and the ref enumeration. Trap 9 is the second-attempt risk: an
implementer who empties whatever `resolve_state_home()` returns without ruling on
the override has reproduced the critical in a new place.

## Verification the operator will run, independent of the gate

- **Export `ERGANE_ROOT` at a scratch directory with a file in it, register a
  throwaway repo whose `.ergane` is empty, and run
  `repo forget --clean-runtime`.** That is the field case. It must refuse, and
  the registry entry must still be there afterwards.
- **Run the same thing with the entry's root populated.** It must empty the
  entry's root, name the override's root, and leave the override's file alone.
- **Run it with no override at all** and diff the output against today's. Any
  new line is a regression of FR-004.
- **`worker uninstall` on a real host with `systemctl --user list-units
  'ergane*'` before and after.** The slice must not be loaded afterwards, and
  every name in the report must be one the before-listing showed.
- **`ergane uninstall --check` on a live host, then `ls` everything it named.**
  Nothing may have moved. Then run it for real and `ls` again.
- **After a real `--purge`, look for `.lock` files** under the state home and
  `~/.config/ergane/`. That single `config.toml.lock` is what started this story.
- **Run `ergane roadmap pause`, `ergane repo forget` and `ergane worker
  uninstall` directly after US3 lands** — not through teardown. FR-017's
  control. If any of the three changed shape, the story satisfied itself by
  moving the ground under three other verbs.
- **`git diff --stat` the US3 branch against its base and confirm
  `factory/cli/roadmap.py` is not in it.** Trap 14. One line in that file is a
  landing-window collision with 085's US3, and it is cheaper to see it in the
  diff than in the merge queue.
- **Paste the two commands FR-015 prints into a shell** —
  `git for-each-ref refs/heads/factory/` and `git for-each-ref refs/salvage/` —
  and compare their line counts against the counts teardown reported. A command
  that is printed but does not return the enumerated set is the defect FR-015
  was rewritten to close.
