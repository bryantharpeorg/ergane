# Implementation Plan: a scaffolded repo arrives with the context its agents need

Every `file:line` below was read from `ergane-buildout` at `602a92c` on
2026-09-04 and verified to resolve to the symbol named. Do not trust an anchor
that has moved; re-read before editing.

## What already exists, and where

**The scaffold writer, and its own statement of what it writes.**
`factory/cli/init.py:1816` — `_write_scaffold` is four writes and a docstring
that says the list is closed:

```python
def _write_scaffold(repo_root: Path, manifest_text: str | None) -> None:
    """Write exactly the declared files and nothing else.
```

The manifest is `factory/cli/init.py:1826-1828`, the single `.gitignore` line is
`factory/cli/init.py:1830-1837`, `runtime_root.mkdir` is
`factory/cli/init.py:1839-1840`, `specs_root.mkdir` is
`factory/cli/init.py:1842-1843`, and the function ends at line 1843.

**It has three production callers, not one, and two of them are demonstrations.**
`grep -rn _write_scaffold --include=*.py` returns `factory/cli/init.py:1268`
(inside `init_command`), `factory/cli/install.py:1001` and
`factory/supervision/demo_driver.py:409`. The second scaffolds a repository
inside a `tempfile.TemporaryDirectory` (`factory/cli/install.py:995`) purely to
demonstrate `check_repo`, and deletes it when the block exits; the third is the
container demo driver's step 3 of 5 (`factory/supervision/demo_driver.py:408`),
against a throwaway repository it created two lines earlier
(`factory/supervision/demo_driver.py:403`). Neither is a repository a node is
ever dispatched against, and neither receives 057's seeded constitution either,
for the same reason. **This spec installs from `init` only**, and spec.md's
§ "What this spec is not" says so in writing. The reason to know all three
anyway: an implementer told "its one caller" will believe the install cannot
escape `init_command`, and will not notice that the two demos are unchanged by
design rather than by accident.

**Spec 057 landed a fifth output beside the scaffold on 2026-09-03, and it is
not inside that function.** `factory/cli/init.py:1263` assigns
`manifest_values["standards"]` unconditionally and `factory/cli/init.py:1273`
calls `_write_constitution`, which seeds `.specify/memory/constitution.md`, the
value of `DEFAULT_STANDARDS_PATH` (`factory/cli/init.py:1847`). **Read what the
comment above it actually says before repeating a story about it.**
`factory/cli/init.py:1254-1258` is about *resolution order* — "resolve the floor
and the standards path before any write" — and it states outright that "The
constitution is written as part of the scaffold". It does not say the write was
moved out of `_write_scaffold` for `--check`'s sake, and it could not: `--check`
never reaches either site, because `init_command` short-circuits at
`factory/cli/init.py:1148-1149` before the interview. So placement is a question
about the *writing* path only. Put the unit install beside `_write_constitution`
at `factory/cli/init.py:1273` rather than inside `_write_scaffold`, on the one
ground that survives reading the tree: `_write_scaffold`'s caller set is not
`init_command` alone, and this spec installs from `init` only.

**The only channel that reaches a dispatched agent, in the tree's own words.**
`factory/config.py:170` — `Persona` carries the finding as its docstring:

```python
    The `skills` field is parsed for validation and backward compatibility, but
    it is reserved and unused (062-US3 FR-009). No adapter invocation consumes
    it, because the factory constructs a per-node, factory-owned HOME at
    dispatch time (`factory/workgraph/adapter.py:339`) and home-scoped agent
    skills are therefore invisible to the node. Project-scoped skills committed
    at ``<repo>/.claude/skills/`` remain visible, because the node's worktree
    carries committed files.
```

The prose at `factory/config.py:177-179` is the load-bearing half. **The
citation inside that docstring has rotted**: the line it names in
`factory/workgraph/adapter.py` — three hundred and thirty-nine — is blank today,
and the code that used to sit there is now `HostAgentBackend`, not the HOME
construction. The per-node home is `factory/workgraph/adapter.py:815` —
`home_path`, and the environment that carries it is built at
`factory/workgraph/adapter.py:971`. Cite those two; do not "fix" the docstring,
which is not this spec's file.

**What a project skill has to look like to load at all.** A project skill is a
*directory*: this repository's own six are `.claude/skills/<name>/SKILL.md`, each
opening with YAML frontmatter carrying `name` and `description`
(`.claude/skills/spec-html/SKILL.md:1-3` is the exemplar to copy). A document
shipped as `skills/ergane.md`, or installed flattened to `<repo>/.claude/<doc>.md`,
satisfies every substring assertion anyone would write about its text and loads
in no agent. FR-004 fixes the payload's relative path and its frontmatter keys;
FR-005 requires the install to preserve that relative path.

**The dispatched node is a writer too, and the factory tells it apart from an
operator three ways.** The node runs `claude -p --dangerously-skip-permissions`
(`factory/workgraph/adapter.py:1195-1205`) with `cwd` set to its worktree
(`factory/workgraph/adapter.py:357`). Skipping permission prompts does not skip
a `PreToolUse` hook, and a committed `<repo>/.claude/settings.json` reaches the
node by exactly the mechanism this whole spec rests on — the worktree carries
committed files. The three markers the factory already sets, any of which
`--check` can read without a subprocess: the per-node `HOME` at
`factory/workgraph/adapter.py:815` — `home_path`, which
`factory/workgraph/adapter.py:947` — `attempt_env` puts in every child's
environment; the worktree path `factory/workgraph/worktree.py:289` —
`worktree_path`; and the branch `factory/workgraph/worktree.py:284` —
`branch_name`, which is the ledger row's own "operator branch" distinction made
literal. All three hang off a runtime root — but that root's **name** is not a fact.
`factory/workgraph/worktree.py:191` — `resolve_factory_root` returns an
`ERGANE_ROOT`/`FACTORY_ROOT` override verbatim
(`factory/workgraph/worktree.py:211-216`) and only falls back to
`factory/workgraph/worktree.py:93`'s `.ergane` or
`factory/workgraph/worktree.py:96`'s `.factory`. This floor's own root is set
from `scripts/ergane-env.sh:84`, and `factory/cli/repo.py:328` says in the
tree's own words that the root "may have been set by `ERGANE_ROOT`/`FACTORY_ROOT`
to something else entirely". What is fixed under any root is the *shape* the
factory builds beneath it — `homes/<epic>/<node>`, `worktrees/<epic>/<node>` —
and the branch name, which no environment variable moves. FR-021, trap 12.

**The packaged-data pattern, twice, and the difference between the two matters.**
`factory/config.py:81` — `_resolve_default_registry_path` resolves package data
`importlib.resources`-first at `factory/config.py:98` and falls back to the
development checkout. `factory/stack_packs.py:182` — `resolve_stack_packs` does
the same for a *directory* at `factory/stack_packs.py:196`, using
`PACKS_DIRNAME` (`factory/stack_packs.py:40`). The registry needs a
force-include because `personas.example.yaml` lives at the repo root; the packs
need none because they live inside `factory/`. `pyproject.toml:74-79` states the
rule in the tree's own words — adding a package-internal directory to the
force-include table "would install a second copy". FR-001. **Copy the packs, not
the registry**: this payload is a directory inside `factory/`, which is the
packs' case exactly, and FR-001 names `resolve_stack_packs` for that reason.

**The wheel test that proves shipping, and the harness it uses.**
`tests/test_057_us2_stack_pack.py:296` —
`test_every_shipped_pack_travels_in_the_wheel` builds a wheel with
`tests.test_distribution_install._build_wheel`, lists it with
`tests.test_distribution_rename._wheel_contents`, and asserts each resolved pack
appears at `factory/<PACKS_DIRNAME>/<name>`. Its docstring names the instruction
this spec inherits: "verify by inspecting a built wheel, never by reading the
build config". FR-001, US1-S1.

**That harness does not generalise, and the sentence in it that reads like a
guarantee is a statement about one hardcoded line.** `tests/test_distribution_install.py:39`
— `_build_wheel` populates the build copy from the **git index**:

```python
    subprocess.run(
        ["git", "checkout-index", "-a", "-f", "--prefix", f"{copy_root}/"],
```

and then carries one explicit copy per package-data path that must be visible
before it is committed — `personas.example.yaml`, `default_floor.md`,
`factory/constitution.py`, and 057/US2's own block at
`tests/test_distribution_install.py:70-75`:

```python
    # 057/US2: stack packs are package data and must travel in the wheel.
    shutil.copytree(
        FACTORY_DIR / "stack_packs",
        copy_root / "factory" / "stack_packs",
        dirs_exist_ok=True,
    )
```

`tests/test_057_us2_stack_pack.py:296`'s comment — that this harness "is the one
that copies the pack directory into the build tree rather than relying on
`git checkout-index`" — is true of *that copytree line*, not of the harness. A
brand-new payload directory under `factory/` has no such block, so the harness
will not see it until it is staged. US1 must add one. Trap 15.

**Pack data, its loader, and where a new key goes.**
`factory/stack_packs.py:50` — `StackPack` is a `NamedTuple` whose optional
fields (`tools`, `fallback`, `rationale`, `completion`) all default, and
`factory/stack_packs.py:141` — `_pack_from_data` validates each one by shape and
raises `ValueError` naming the source file. A `sources` list follows `tools`
(`factory/stack_packs.py:148` and `factory/stack_packs.py:157`) exactly. The
module's own docstring at `factory/stack_packs.py:13-17` states the rule the new
key must not break: "*Nothing here knows a pack's name.* Adding a pack is adding
a file (FR-010)", asserted by `tests/test_057_us2_stack_pack.py`. FR-011.

**What each shipped pack declares, decided here rather than invented by the
implementer.** `factory/stack_packs/python.yaml` declares `sources: [src,
tests]`; `factory/stack_packs/node.yaml` declares `sources: [src, lib, app,
test, tests]`; `factory/stack_packs/agnostic.yaml` declares **none**, for the
same reason its header gives for declaring no commands — "naming a plausible one
here would hand a repository a command that does not exist in it". These are
conventional layout roots for a toolchain, not a guess about one repository, and
FR-012's existence filter is what makes a wrong guess harmless: a declared root
the repository does not contain is dropped before it is ever derived. Note what
that means for *this* repository, so it is not discovered as a surprise: ergane's
markers select the Python pack, it has `tests/` and no `src/`, so its derived set
is `tests` alone and `factory/` is not covered. That is the honest answer and
FR-013 and FR-018 are what say it out loud; an operator who wants `factory/`
covered names it in a gate command *in path shape* (`uv run mypy factory/`), and
FR-013's listing is what tells them it took.

**The command tokenisers already exist, and they answer a different question.**
`factory/stack_packs.py:248` — `_command_words` returns every non-flag word in a
command; `factory/stack_packs.py:253` — `_leading_executable` returns the
executable or `None`. They were written for the cross-pack tool roster at
`factory/stack_packs.py:262` — `check_tool_hygiene`, which compares *executables*
between packs. FR-012 wants *paths*, and the two sets overlap without being the
same. Reuse `_command_words` for the tokenising; do not reuse
`check_tool_hygiene`'s conclusion. Note that `_command_words` returns a *set*,
so it loses order — FR-012's "value of a preceding flag" test needs the ordered
tokens, which is `shlex.split` the way `_leading_executable` already reads them.

**The gate commands themselves.** `factory/verify/models.py:291` —
`FactoryConfig` carries `gates: dict[str, str]` at
`factory/verify/models.py:310`: gate name to command string. That mapping and the
resolved stack pack are the whole input to FR-012.

**The shipped Python pack is the derivation's worst case, and it is real data.**
`factory/stack_packs/python.yaml` declares `test: uv run pytest -q`,
`lint: uv run ruff check .` and `type: uv run mypy .`. Two of those three name
`.` as their only path-shaped-looking argument and the third names nothing at
all. Read the file before writing the derivation; it is the fixture US3-S1 is
built from.

**Where the verb goes.** `factory/cli/repo.py:105` — `add_repo_parser` registers
`ergane repo`'s verbs; `onboard` is at `factory/cli/repo.py:113`, `list` at
`factory/cli/repo.py:138`, each with its own `set_defaults(run=...)`. The noun is
registered at `factory/cli/nouns/repo.py:8`. A new verb is one `verbs.add_parser`
block and one command function. FR-013 adds the verb (US3); FR-014 adds its
`--check` flag and the stdin path to the same block (US5), which is why US5's
edge is on US3's merge.

**What init prints, and where a line joins it.**
`factory/cli/init.py:1326-1331` is the `written:` block — manifest, `.gitignore`,
runtime root, then `_constitution_write_line`. FR-009's line goes there; FR-010's
and FR-018's sentences are reports, not writes, and belong after it beside
`_registration_line` (`factory/cli/init.py:1332`).

**The ignore rules that were already there.** `factory/cli/init.py:1830-1837`
is the only `.gitignore` line init writes, so a test that reads *that* entry
proves only half of FR-008. A repository whose own `.gitignore` already carries
`.claude/` — a common convention, since most tools treat it as local state —
takes the unit, is told it was written, and hands it to no node. Ask git rather
than re-implementing its matcher: `git -C <repo> check-ignore --stdin` answers
per path against the effective rules, including `.git/info/exclude` and any
nested `.gitignore`. FR-008's second half and FR-018's report. The operator's
only other symptom is init's own printed `git add` line failing wholesale on
ignored paths, with nothing tying that to the "written:" block above it.

**The staging line, which is a second way to make the unit invisible.**
`factory/cli/init.py:1364` — `_paths_to_commit` returns
`["ergane.yaml", ".gitignore", str(RUNTIME_ROOT)]` plus the workflow when it
exists, and `factory/cli/init.py:1342` prints it as the `git -C ... add ...`
line. An init that reports the unit as written (FR-009) and then tells the
operator to stage everything except it produces a committed repository whose
agent-context unit reaches no node — trap 7's failure by the neighbouring
mechanism. FR-020 requires the printed line to name the install record's files
individually **and the record itself**; naming `<repo>/.claude` as a directory
would sweep in whatever else the operator keeps there, `settings.local.json`
included. The record is committed for a reason FR-006 states: an operator-local
record leaves the next clone holding every payload file with a digest for none
of them, which is FR-005's fourth row — "kept", forever, for a file ergane wrote
itself.

**The scaffolding `init` never mentions.** `factory/doctor/scaffold.py:27` —
`scaffold_spec` produces a compiling trio from code and is called at
`factory/cli/nouns/spec.py:405`, inside `factory/cli/nouns/spec.py:390` —
`_new_command`. FR-010 is one sentence in a report; the work is knowing it is
true.

## Traps

**Trap 1 — The entry's first premise is already fixed, and re-fixing it is the
most likely way to waste this spec.** The triage was verified at `238b494` and
said `standards` is empty by default for a fresh repository. Spec 057 landed four
stories the same day (`8ee5e9c`, `5c43d4a`, `1027a05`, `602a92c`).
`factory/cli/init.py:1263` now assigns `standards` unconditionally,
`factory/cli/init.py:943-948` returns `DEFAULT_STANDARDS_PATH` for an empty
answer, and `factory/cli/init.py:1273` seeds the document. An implementer who
reads the finding's summary — "no CLAUDE.md, no .claude/settings.json, no
.claude/skills/, no .specify/" — and starts with `.specify/` will rebuild 057.
**Nothing in this spec touches the standards path, the constitution or the
manifest's `standards` key.** The half of the finding that is left is `.claude/`.

**Trap 2 — Do not add the payload to the force-include table.**
`pyproject.toml:80-84` is that table, and `pyproject.toml:74-79` explains in the
tree's own words why the stack packs are deliberately absent from it: they are
"already inside the wheel's import package, so hatchling ships them without being
told. Adding them here would install a second copy." The `default_floor.md` entry
at `pyproject.toml:84` is the opposite case — a repo-root file — and copying
*that* line is the tempting mistake. FR-001. The guarantee is held by US1-S1's
wheel test, not by the config.

**Trap 3 — A bare command word that happens to name a directory is not a path,
and `.` is only the loudest instance.** This is the trap that decides whether the
hook is usable. `factory/stack_packs.py:248` — `_command_words` splits on
`factory/stack_packs.py:47`'s `_WORD` pattern, `[A-Za-z0-9_.+@/-]+`, so
`uv run ruff check .` yields `.` and `npm --prefix web run build` yields `run`
and `build` alongside `web`. Every one of those resolves in some repository: `.`
is always the root, and a repository with a `build/` or a `run/` directory turns
a subcommand into a derived path. A derivation that keeps every token resolving
to an existing path therefore refuses every write in the repository from the
shipped Python pack alone — including the operator's specs, their manifest and
their fixtures, which spec.md's § "What this spec is not" promises are out of
reach — and, in the `npm` case, locks the operator out of `build/` for no reason
anyone can see. FR-012's rule is the answer and it is deliberately conservative:
a word is a path only when it exists **and** contains a separator, or is the
value of a preceding flag, or is one of the pack's declared source roots. `.` is
none of those; `build` and `run` are none of those; `web` is a flag's value;
`tests` is a declared root. US3-S1 and US3-S2 are the two reproductions. The
residual false positive is a flag value that is not a path — `pytest -k foo` in a
repository with a `foo/` directory — and it stays: FR-013's listing makes it
visible and FR-016's escape — `ERGANE_SKIP_GATE_PATH_CHECK=1` — makes it
survivable. Do **not** close it with a
name-based allowlist of flags, which is a guess about every tool that will ever
be a gate.

**Trap 4 — 087 rules this work out, it is still draft, and the supersession must
be written rather than assumed.**
`specs/087-the-operators-skills-arrive-with-the-cli/spec.md:52` says "A story
here that writes into a target repository is a defect even if it works", and
`specs/087-the-operators-skills-arrive-with-the-cli/spec.md:276` makes it FR-010.
Both were about *operator* skills — the ones under this repository's own
`.claude/skills/` — and remain right about those. This spec supersedes that
ruling for the target-repo unit alone; the supersession is stated in this trio's
frontmatter and in spec.md's § "What this spec is not". An implementer who finds
087 mid-story and stops has found a real contradiction and its resolution is
already written: do not stop, and do not edit 087.

**Trap 5 — `CLAUDE.md` is refused, not deferred.** The finding's own ranking puts
"a CLAUDE.md block, idempotent between sentinel markers" second, and an
implementer who has read the ledger row will be tempted to add one "while we are
here". D-025 (`docs/decisions.md:600-608`) put standards in the manifest's
`standards` key "because a committed file is adapter-agnostic — no reliance on
`CLAUDE.md` auto-loading", and `tests/test_claude_md.py` holds this repository's
own page to orientation only. No file this spec ships or writes may be named
`CLAUDE.md`, in this repository or in a target one.

**Trap 6 — 057's existence guard is the wrong model for a unit that must be
updatable.** `factory/cli/init.py:1862` — `_standards_document_exists` is
existence-only, and its docstring says why: "an empty file is a deliberate choice
and must not be overwritten". That is correct for a document the user rewrites in
prose and fatal for a versioned unit, because a unit guarded on existence can
never be updated — which is precisely what the finding asked for ("installed and
updated by init"). FR-006 and FR-007 need the recorded digest. Copying
`_standards_document_exists` and calling US2 done is a green story that ships a
one-time drop.

**Trap 7 — An ignored unit reaches no agent, and init already edits
`.gitignore`.** `factory/cli/init.py:1830-1837` appends `.ergane/` to the target
repository's `.gitignore`. The neighbouring, obvious-looking move — adding
`.claude/` beside it, because it looks like tool state — makes the entire unit
invisible to every dispatched node, since `factory/config.py:177-179` is explicit
that only committed worktree files reach one. FR-008 forbids it and requires a
test that asserts the absence, because this failure is silent: every gate passes,
the files exist on the operator's disk, and no agent ever sees them. FR-020 is
the same failure by the neighbouring mechanism — see the staging line above.
**And the entry init writes is not the only entry that can fire this trap**: a
target repository that already ignored `.claude/` before ergane arrived reaches
the same end state through rules init never wrote, which is why FR-008's second
half asks git for the *effective* answer (`git check-ignore`) and FR-018 makes
init say so. US2-S8.

**Trap 8 — A shipped `.py` file under `.claude/` is ungated in every repository
that receives it.** `pyproject.toml:87` is `testpaths = ["tests"]`, and the
finding's worked example is a session that landed 139 lines of Python under
`.claude/skills/` and offered four green gates that had collected none of it.
Shipping a helper script inside the payload reproduces that defect at scale, once
per install. FR-003 forbids it, which is also why FR-014's decision lives in the
`ergane` CLI rather than in a script the payload copies: the CLI is under
`factory/`, which the gates do compile.

**Trap 9 — A hook that fails closed locks the operator out; a hook that fails
silently is worse than none; and one of the three failure modes is not the
verb's to own.** FR-015 and FR-018 are the two halves the verb owns: an
unreadable manifest and a payload whose shape has changed must exit 0 **and say
so**, or the operator believes they are protected while every write passes; and a
repository whose derivation is legitimately empty (FR-012, US3-S3) gets a hook
that refuses nothing, which FR-018 makes init say at install time rather than
leaving it to be discovered. The third case is the one that has to be split in
two, because the halves do not behave alike. `ergane` **absent** from `PATH` is
not an exit code the verb can produce — its command never runs, the harness
shows its own hook error, and the write proceeds. `ergane` **present but older
than the verb** is the opposite and it is a lockout: see trap 16, which one
command measures. Do not answer either by shipping a wrapper script inside the
payload — that collides with trap 8 and FR-003 — and do not resolve any of them
by making the hook refuse.

**Trap 10 — The payload's stdin shape is an external contract, so commit a
fixture.** FR-015. `--check` parses a tool-call payload it does not own. An
implementer who reads the shape out of a live session and hardcodes it has
written a parser that will one day stop matching and start allowing everything,
with no test failing. The fixture makes that change fail
`tests/`, which is the only place a change of that kind can be caught.

**Trap 11 — Two stories edit `factory/cli/init.py`, and they are ordered.** US2
adds the install and its report lines; US4 adds more report lines to the same
block (`factory/cli/init.py:1326-1331`) and one file to US1's payload. That is
why US4's `depends_on_merged` names all four. An implementer given US4 before
US2 has merged will find no install to report on and will build one, duplicating
US2.

**Trap 12 — The hook this spec installs would refuse the factory's own
implementer nodes, and no environment variable can rescue that.** A dispatched
node runs with `cwd` set to a worktree that carries the committed
`<repo>/.claude/settings.json` (`factory/workgraph/adapter.py:357`), under
`--dangerously-skip-permissions` (`factory/workgraph/adapter.py:1195-1205`),
which suppresses permission prompts and not hooks. The node's entire job is to
write under the paths the manifest's gates compile, so without FR-021 every
production Write and Edit it makes is the refuse row of spec.md's table, and the
factory stops building in any repository that committed its own agent context.
The obvious escape does not work: `factory/workgraph/adapter.py:947` —
`attempt_env` is a built allowlist, not a filtered environment, and the
passthrough is the three names at `factory/workgraph/adapter.py:104`, so no
variable an operator exports reaches a node. FR-016's escape is therefore for the
operator and only the operator. Detect the node from what the factory already
sets — the per-node `HOME` (`factory/workgraph/adapter.py:815` — `home_path`), a
target inside `factory/workgraph/worktree.py:289` — `worktree_path`, or the
checked-out branch `factory/workgraph/worktree.py:284` — `branch_name`, which is
the ledger row's own qualifier made literal: "code under the paths your own gates
compile should not arrive **on an operator branch**".

**Key on the shape, never on the runtime root's name, and this is the half that
looks safe and is not.** `.ergane` (`factory/workgraph/worktree.py:93`) and
`.factory` (`factory/workgraph/worktree.py:96`) are *defaults*:
`factory/workgraph/worktree.py:191` — `resolve_factory_root` returns an
`ERGANE_ROOT`/`FACTORY_ROOT` override verbatim
(`factory/workgraph/worktree.py:211-216`), this floor sets one from
`scripts/ergane-env.sh:84`, and `factory/cli/repo.py:328` says so in the tree's
own words. A detector that looks for either literal passes every test written
against the defaults, ships green, and then classifies **every** dispatched node
on an overridden host as an operator — the whole catastrophe above, arrived at
through a green suite. Match `homes/<epic>/<node>` and `worktrees/<epic>/<node>`
as path tails, or the branch, and give US5-S3 a relocated-root assertion so the
mistake cannot pass.

**Trap 13 — A first install meets a `.claude/` the operator already has.** Every
repository that has ever been opened in an agent session has one: this one holds
six committed skills and a `settings.local.json`, and the finding's own worked
example is a session that wrote its own file into `.claude/skills/`. FR-007's
guard is keyed on a *recorded digest*, and on a first run there is no record — so
an implementer who reads FR-005 as an unconditional write silently destroys the
operator's own file at a payload path on the very run that was supposed to help
them, and every declared scenario stays green because they all presuppose ergane
installed the file first. The fourth row of spec.md's install table and US2-S6
are the reproduction: present with no record means kept, reported, and no digest
written. **The ordering matters and US2-S6 obeys it.** At US2's dispatch the
payload is what US1 shipped — the declaration and one
`skills/<name>/SKILL.md` — so the reproduction is that path plus a file of the
operator's own at a path the payload does not name, which must be left alone and
named nowhere. `settings.json` becomes a payload path only with FR-017, in US4,
so *its* pre-existing case is US4-S4 under FR-019. An implementer who repairs
US2-S6 by adding `settings.json` to the payload inside US2 is implementing an FR
US2 does not own, on the same declaration and payload directory T046 edits, and
US4 carries `depends_on_merged: [US1, US2, US3, US5]`, so the collision lands in
US4's own base. Trap 6 pushes hard in the opposite direction — it is about a file
*ergane installed* — and the two are not in conflict: the record is what tells
them apart.

**Trap 14 — A skill document that is not a `<name>/SKILL.md` directory loads in
nothing.** FR-004 and US1-S4. `skills/ergane.md` passes every substring test
anyone would write, ships in the wheel, installs without error, and reaches no
agent — and so does a correct document that FR-005 installs flattened, because
`factory/config.py:177-179`'s claim is about `<repo>/.claude/skills/` and nowhere
else. Copy the shape this repository already uses
(`.claude/skills/spec-html/SKILL.md:1-3`): a directory per skill, `SKILL.md`
inside it, YAML frontmatter with `name` and `description`. Assert the path and
the parsed frontmatter, not the prose.

**Trap 15 — The wheel harness copies the git index, so it cannot see a payload
directory nobody has staged.** `tests/test_distribution_install.py:39` —
`_build_wheel` runs `git checkout-index -a -f --prefix <copy>/` and then carries
one explicit `shutil.copy2`/`copytree` per package-data path that must be visible
before it is committed; 057/US2's is `tests/test_distribution_install.py:70-75`.
US1's payload is a brand-new directory under `factory/` with no such block, so
US1-S1's wheel test reports a packaging failure that is really a harness gap —
and the tempting repair is the one trap 2 forbids, adding the payload to
`pyproject.toml:80-84`, which would make the test pass and ship the second copy
the tree warns about at `pyproject.toml:74-79`. The correct repair is one
`copytree` block for the payload directory beside 057's, in
`tests/test_distribution_install.py`, which is a test file US1 alone touches.
Read the docstring at `tests/test_057_us2_stack_pack.py:296` as what it is: a
claim about that copytree line, not about the harness.

**Trap 16 — Exit 2 is `argparse`'s usage status, and a refusal that shares it
locks the operator out of every repository whose `ergane` is a version behind.**
Measured on this tree: `ergane repo gate-paths --check </dev/null` exits **2**
with `ergane repo: error: argument verb: invalid choice: 'gate-paths'`, because
the verb does not exist yet. Exit 2 is also the only status a `PreToolUse` hook
treats as a refusal. So a repository that commits the shipped `settings.json`
refuses every Write and Edit on any machine whose installed `ergane` predates
this spec — the ordinary rollout state, 0.5.0 being what is released — and after
any later rename of the verb or its flag. That is exactly the lockout trap 9
forbids, reached through the one failure mode trap 9's first draft did not
separate: present-but-older is not the same as absent. FR-014 gives the refusal
a status `argparse` cannot produce and FR-022 makes the declared command
translate it, tested against a stub `ergane` on `PATH` in both directions
(US4-S5, US5-S6). Do **not** "fix" this by having the verb print a sentinel the
hook greps for: the harness reads the exit status, and a second parser in a JSON
string is a third place for the contract to rot.

## Sizing

US1 touches `factory/agent_context.py` (new: the declaration reader and
resolver, ~90 lines), a new payload directory under `factory/` (one declaration
file, ~15 lines, plus one `skills/<name>/SKILL.md`, ~60 lines of prose), one new
test module beside `tests/test_057_us2_stack_pack.py` (~180 lines), and
`tests/test_distribution_install.py` for trap 15's `copytree` block (~6 lines).
It edits no existing *production* file and, by FR-001, does not edit
`pyproject.toml` either. Roughly 26 KB of diff.

US2 touches `factory/cli/init.py` and no other production file — the install
call beside `factory/cli/init.py:1273` (~70 lines with the record helper), the
`git check-ignore` report for FR-008's second half (~20 lines), the report lines
at `factory/cli/init.py:1326-1331`, and `_paths_to_commit` at
`factory/cli/init.py:1364` for FR-020 — plus its tests beside the existing init
suite (~290 lines). The two demonstration callers of `_write_scaffold`
(`factory/cli/install.py:1001`, `factory/supervision/demo_driver.py:409`) are out
of scope by spec.md's § "What this spec is not", which is why US2 still touches
one production file and not three. Roughly 30 KB.

US3 touches `factory/stack_packs.py` (one optional field and its validation, ~20
lines), the three shipped pack files under `factory/stack_packs/` (~9 lines
between them), a new derivation module (~110 lines) and `factory/cli/repo.py` for
the listing verb (~45 lines), plus tests (~280 lines). It does not touch
`factory/cli/init.py`. Roughly 35 KB.

US5 touches `factory/cli/repo.py` again for `--check` and its four exit paths
(~90 lines), one committed payload fixture (~20 lines) and its tests (~240
lines). Roughly 30 KB.

US4 touches the payload directory US1 created (one `settings.json`, ~20 lines)
and `factory/cli/init.py` for FR-018's lines and FR-019's report (~30 lines),
plus tests (~180 lines, FR-022's stub-`ergane` pair included). Roughly 20 KB.

US1 and US3 name no production file in common and are meant to run at the same
time; trap 15 adds `tests/test_distribution_install.py` to US1's list and US3
does not touch it, so the `concurrent_with` override survives. US2 and US4 both name `factory/cli/init.py`, and US3 and US5 both name
`factory/cli/repo.py`, which is what their `depends_on_merged` edges are for.

All five are inside the 64 KiB deterministic diff bound (D-050), and the split of
the old US3 into US3 plus US5 is what keeps the largest under it: measured on the
neighbours, `057-US4` landed at 63,932 bytes against a 65,536-byte refusal and
`057-US2` at 52,840, so a single story carrying the pack field, the derivation,
the listing verb, `--check`'s four exit paths, a fixture and all of their tests
was the one slice in this spec with no headroom. The pasted evidence each
verification task asks for is a short listing, not a transcript, and is counted
in the estimates above.

## Verification the operator will run, independent of the gate

Per constitution VIII and D-037 the judge sees the diff and the criteria only, so
runtime evidence must be committed as pasted output. Beyond that:

1. Build a wheel from the tree, unzip it, and confirm every payload file is
   present under `factory/` at its declared relative path — including that the
   skill document arrives as `skills/<name>/SKILL.md`. That is the only check
   that distinguishes "the files are in my checkout" from "a stranger's install
   carries them", which is the defect `tests/test_057_us2_stack_pack.py:296`
   exists for.
2. On a scratch repository, run `ergane init`. Confirm `<repo>/.claude/`
   holds the payload at the same relative paths, that `git status` shows those
   files as untracked and that `.gitignore` does not cover them — an ignored unit
   reaches no node. Then run the `git add` line init printed, verbatim, and
   confirm `git status --short` shows every installed file staged and nothing
   else in `.claude/` swept in with it (FR-020).
3. On a second scratch repository, write a `.claude/settings.json` and a
   `.claude/skills/<name>/SKILL.md` of your own *before* the first `ergane init`,
   then run it. Both must survive byte-for-byte and be reported as kept. This is
   trap 13 and it is the one an operator cannot undo.
4. Edit one installed payload file, run `ergane init` again, and confirm that
   file is unchanged, its siblings are updated, and both outcomes are named in
   the report.
5. Run `ergane repo gate-paths <repo>` against a repository declaring the shipped
   Python pack's gate commands. The repository root must not be listed, and a
   declared source root the repository does not contain must not be listed
   either. Then add a `build/` directory and an `npm --prefix web run build`
   gate and confirm `web` is listed and `build` is not. This is trap 3 run
   forwards and it is the falsifiable test of whether the hook is usable at all.
6. Commit the unit in that repository, dispatch one story against it, and confirm
   two things from the node: that `.claude/skills/` is present in its worktree,
   and that the node's own production writes were **not** refused — its diff
   contains the file it was dispatched to write. The claim at
   `factory/config.py:177-179` is what the whole spec rests on and it has never
   been exercised with a file ergane put there; FR-021 is what keeps that
   exercise from stopping the factory.
7. In an operator session in that repository, attempt a Write under a derived
   path and confirm the refusal names the gate; attempt one under `specs/` and
   confirm it is allowed; then export `ERGANE_SKIP_GATE_PATH_CHECK=1` (FR-016
   fixes that name, after the tree's own override at `scripts/hooks/pre-push:26`)
   and confirm the first attempt is allowed with a message.
8. Put an older `ergane` first on `PATH` — one that does not know the verb — and
   repeat step 7's first attempt. The write must be allowed. Then run the bare
   verb by hand and read its exit status: `argparse` answers 2, and the whole
   point of FR-014 and FR-022 is that the hook does not confuse that with a
   refusal. This is trap 16 run forwards.
9. Relocate the runtime root by exporting `ERGANE_ROOT` to a directory named
   neither `.ergane` nor `.factory`, dispatch one story, and repeat step 6. A
   node exemption keyed on the root's name passes every committed test and fails
   exactly here (trap 12).

Step 6 is the falsifiable test of the whole spec, in both of its halves. Step 7
is the one the finding was filed about.
