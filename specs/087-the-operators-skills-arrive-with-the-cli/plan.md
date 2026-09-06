# Implementation Plan: the operator's skills arrive with the CLI

Every `file:line` below was read from `ergane-buildout` at `602a92c` on
2026-09-04 and verified to resolve to the symbol named. Do not trust an anchor
that has moved; re-read before editing.

## What already exists, and where

**The payload, exactly.** Six directories under `.claude/skills/`, eleven
tracked files between them, 208 KB on disk:

```
.claude/skills/away-mode/SKILL.md
.claude/skills/build-metrics/SKILL.md
.claude/skills/build-metrics/reference/baseline-2026-08-19.md
.claude/skills/build-metrics/scripts/commit_sizes.py
.claude/skills/build-metrics/scripts/loc.py
.claude/skills/build-metrics/scripts/rework.py
.claude/skills/escalation-triage/SKILL.md
.claude/skills/findings-ingest/SKILL.md
.claude/skills/floor-status/SKILL.md
.claude/skills/spec-html/SKILL.md
.claude/skills/spec-html/render.py
```

Two of them are not a lone `SKILL.md`: `build-metrics` carries `scripts/` and
`reference/`, `spec-html` carries `render.py`. A payload rule that globs
`*/SKILL.md` ships four working skills and two broken ones. And a twelfth path
exists in the working tree that is **not** in that list —
`.claude/skills/spec-html/__pycache__/`, ignored by `.gitignore:2` — which is
trap 9.

**The packaged-data pattern exists twice already, and the directory case is the
one to copy.** The single-file case is `factory/config.py:98` —
`_resolve_default_registry_path`:

```python
    packaged = importlib.resources.files("factory") / REGISTRY_FILENAME
    if packaged.is_file():
        return Path(str(packaged))
    return Path(__file__).resolve().parents[1] / REGISTRY_FILENAME
```

Its docstring at `factory/config.py:82-97` records why the order is what it is:
a previous version walked up from `__file__` and produced
`cannot read persona registry .../site-packages/personas.yaml` on a real
install, because packaging shipped nothing to walk to.

The **directory** case — the shape this spec needs — is
`factory/stack_packs.py:196` — `resolve_stack_packs`:

```python
    packaged = importlib.resources.files("factory") / PACKS_DIRNAME
    if packaged.is_dir():
        for entry in sorted(packaged.iterdir(), key=lambda e: e.name):
            if entry.name.endswith(PACK_SUFFIX):
                data = yaml.safe_load(entry.read_text(encoding="utf-8")) or {}
                packs.append(_pack_from_data(str(entry), data))
```

**The wheel side is one table with four entries**, at `pyproject.toml:80`:

```toml
[tool.hatch.build.targets.wheel.force-include]
"personas.example.yaml" = "factory/personas.yaml"
"container/seccomp-ergane.json" = "factory/container/seccomp-ergane.json"
"container/ergane-engine.profile" = "factory/container/ergane-engine.profile"
"default_floor.md" = "factory/default_floor.md"
```

Read the comment above it before adding a fifth entry —
`pyproject.toml:74-79` says the stack packs are *deliberately absent* from the
table because they already live inside the import package, and that "adding them
here would install a second copy". `.claude/skills/` is the other case: it lives
outside the package, so it needs the entry, exactly as `personas.example.yaml`
does.

**The payload guard is in two places and only one of them is a test.** The
release workflow's validation step begins at `.github/workflows/release.yml:68`
and its one payload assertion is `.github/workflows/release.yml:83-86`:

```bash
          if ! unzip -l "${WHEEL}" | grep -q 'factory/personas.yaml'; then
            echo "VALIDATION-FAIL: personas.yaml missing from wheel" >&2
            exit 1
          fi
```

That guard runs only on a tag push and cannot be exercised by the declared
`test` gate. The committed half of the same idea is
`tests/test_057_us2_stack_pack.py:296` —
`test_every_shipped_pack_travels_in_the_wheel`, whose docstring carries the
instruction US1 must obey — "verify by inspecting a built wheel, never by
reading the build config" — and whose two helpers are already written:
`tests/test_distribution_install.py:39` — `_build_wheel` (which copies the data
directory into the build tree rather than relying on `git checkout-index`, so it
sees files that are present but not yet committed) and
`tests/test_distribution_rename.py:116` — `_wheel_contents`. US1-S1 is that test
with a different payload; US1-S2 is the workflow line beside it.

**The version answer already exists and it is not the revision.**
`factory/supervision/engine_identity.py:38` — `cli_version` reads
`importlib.metadata.version("ergane-cli")` and falls back to `"unknown"` only
when the distribution is not installed. The thing FR-007 forbids is beside it:
`factory/cli/main.py:132` — `_version_text` shells out to `git rev-parse --short
HEAD` and assigns `revision = "unknown"` at `factory/cli/main.py:144` on any
failure, which is every wheel install.

**Teardown is a table, and adding a step is adding one entry.** The ordered
tuple is at `factory/cli/uninstall.py:933`; the entry type is
`factory/cli/uninstall.py:188` — `Step`, whose three required fields are a name,
a read-only `survey` and an acting `perform`. The survey returns
`factory/cli/uninstall.py:160` — `StepSurvey`, which is "exactly one of three
things: a plan with subjects to act on, a `nothing_to_do` that says so by name
(FR-011), or a `refusal`", plus `notes` — "what the survey *established* rather
than what the step will do", which prints on `--check` and on a real run alike.
The one grammar every step speaks is `factory/cli/uninstall.py:609` — `_kept`
and `factory/cli/uninstall.py:613` — `_removed`; the comment at
`factory/cli/uninstall.py:362` says they are read from a step that does not own
them on purpose, "one labelled grammar for every path this verb keeps or
removes". US4 adds an entry, not a dialect.

**Ergane's own state directory, which is where a record belongs.**
`factory/cli/uninstall.py:617` — `_state_home` returns
`registry.resolve_state_home() / ERGANE_STATE_DIR` and its docstring settles the
`--purge` question for anything written under it.

**The per-node HOME, re-anchored.** `factory/workgraph/adapter.py:815` —
`home_path` derives `.factory/homes/<epic>/<node>`, and
`factory/workgraph/adapter.py:971` — `attempt_env` writes it into the child's
environment as the first key of the allowlist:

```python
    env: dict[str, str] = {
        "HOME": str(context.home_path),
    }
```

`factory/workgraph/adapter.py:104` states the rule in the passthrough comment —
`HOME` "is intentionally absent" from `PASSTHROUGH_ENV` because it is
constructed. This is the mechanism behind FR-010, and note that
`personas.yaml:31-36` still cites the *old* line for it — line 339 of
`factory/workgraph/adapter.py`, which is blank at 602a92c. Fixing that comment is not this spec's job and not in any story's
scope; do not wander into `personas.yaml` to correct it.

**The reserved word, and the shape of the ruling that resolves it.**
`personas.yaml:42` declares `skills` as "reserved and unused; parsed only for
backward compatibility"; `personas.yaml:62` still carries an example value;
`factory/config.py:363` — `_skills` is the validator that parses it into
nothing; and `tests/test_062_us3_skills.py:28` —
`test_skills_field_is_documented_as_reserved_and_construction_sites_are_explained`
fails the moment the registry header stops saying so. `CONTEXT.md` has no entry
for the word. The section that resolves words like this is `CONTEXT.md:212` —
§ "Flagged ambiguities" — and the entry to imitate is the four-sense `promote`
resolution at `CONTEXT.md:243-248`, which names the unqualified sense, gives each
other sense a phrase, and then explicitly exempts landed identifiers from the
prose ruling. That last clause is the model: the persona field is a landed
identifier and keeps its name.

**The CLI surface a verb attaches to.** Nouns are discovered by module at
`factory/cli/main.py:54` — `_discover_nouns_with_failures`, so a new noun is a
new file under `factory/cli/nouns/` exporting `NOUN`; the shape to copy is
`factory/cli/nouns/install.py:123` — `add_parser`.

**README already has a skills paragraph, and it is about somebody else's.**
`README.md:56` is "Spec Kit's authoring skills, installed into your agent, not
into this repository". FR-012's paragraph must not be mistaken for it or
appended to it — one is a prerequisite the operator installs from a third party,
the other is a payload Ergane ships. Both sweeps run over the file:
`tests/test_readme.py:107` — `test_every_path_the_file_cites_exists` and
`tests/test_readme.py:50` — `test_every_command_the_file_names_parses`.

## Traps

Named hazards. Each has already cost something, here or nearby.

**Trap 1 — the word `skills` is taken, and the ruling comes before the verb.**
`personas.yaml:42` reserves a per-persona `skills` field and
`tests/test_062_us3_skills.py:28` locks the reservation to the registry's own
header, so a change that quietly wires the field in fails there. A verb named
`ergane skills install` puts a second, louder meaning on that word permanently,
in the CLI surface, where it cannot be taken back. FR-011. The wrong move is to
name the noun first and write the ruling afterwards — a ruling that lands after
the name is a ruling about something already decided. The cheapest correct move
is the one the tree already models: add an entry to `CONTEXT.md:212` —
§ "Flagged ambiguities" in the shape of the `promote` entry
(`CONTEXT.md:243-248`), giving the unqualified word to the operator tooling and
naming the persona field as a landed identifier that keeps its name. Do that in
the same commit as the verb, or choose a name that does not collide.

**Trap 2 — the packaged-data pattern already exists twice; do not invent a
third, and do not collide the two names.** `factory/config.py:98` —
`_resolve_default_registry_path` is the file case and
`factory/stack_packs.py:196` — `resolve_stack_packs` is the directory case;
copy the second. FR-002. There is one specific wrong move: naming the resolver
module and the payload directory the same thing. A directory `factory/skills/`
and a module `factory/skills.py` cannot both be what
`importlib.resources.files("factory") / "skills"` means, and the failure is a
resolver that finds its own source file. Give them different names — the packs
precedent is a `factory/stack_packs/` directory beside a `factory/stack_packs.py`
module and it works only because the module wins the import and the directory is
reached by `importlib.resources` alone; do not rely on that subtlety, name them
apart.

**Trap 3 — a payload that stops shipping fails silently, and the workflow guard
is not a test.** `.github/workflows/release.yml:83-86` fails the release when
`factory/personas.yaml` is missing from the wheel, and that guard exists because
a wheel that builds is not a wheel that works. FR-003 extends it. But that step
runs on a tag push and the declared `test` gate never reaches it, so a story
that adds only the shell line has added nothing a gate can see. The committed
half is `tests/test_057_us2_stack_pack.py:296` —
`test_every_shipped_pack_travels_in_the_wheel`, which reads a built wheel. Write
both. The wrong move is to assert against `pyproject.toml` instead — that test
passes on a `force-include` entry that hatchling silently drops, which is the
exact failure being guarded against.

**Trap 4 — these are files in someone's home directory.** Install writes into
the operator's own `~/.claude/skills/`, outside any git repository and outside
anything Ergane owns. Two consequences the stories must face rather than
discover. **(a) An operator may have edited a skill.** A reinstall that silently
overwrites local edits is data loss in a directory the operator reasonably
considers theirs — FR-005, and FR-013 for the file Ergane never wrote at all.
**(b) Teardown must account for them.** 083 established the discipline and the
vocabulary — `factory/cli/uninstall.py:609` — `_kept`,
`factory/cli/uninstall.py:613` — `_removed`, and every step names what it did —
but it was written before anything wrote into `~/.claude/`. An install path with
no teardown path leaves orphans on a host that was told Ergane had left. FR-009.

**Trap 5 — a packaged install cannot read its own revision.**
`factory/cli/main.py:132` — `_version_text` derives the revision with
`git rev-parse --short HEAD` and falls back to the literal string `unknown` at
`factory/cli/main.py:144` when there is no checkout — which is every wheel
install. Verified 2026-08-22 against the published 0.3.0: `ergane 0.3.0
(unknown)`. So a staleness check keyed on revision compares `unknown` against
`unknown` and calls it a match, on every install, forever. Key it on
`factory/supervision/engine_identity.py:38` — `cli_version`. FR-007.

**Trap 6 — 139 supersedes this spec's target-repository ruling for one unit, and
that is not a contradiction to stop on.**
`specs/139-a-scaffolded-repo-arrives-with-the-context-its-agents-need/spec.md:216`
and
`specs/139-a-scaffolded-repo-arrives-with-the-context-its-agents-need/plan.md:305`
both state, in writing, that 139 owns the target-repository agent-context unit
and supersedes this spec's "a story here that writes into a target repository is
a defect even if it works" for that unit **alone**. 087 keeps the operator-side
install; the two write under different roots — `$HOME/.claude/skills/` here,
`<repo>/.claude/` there — and share no file. FR-010 is unchanged and binds this
spec's own scope. Two wrong moves, in opposite directions: an implementer here
who reads 139's work as licence to add a `--repo` target has widened FR-010 out
of existence, and an implementer here who meets 139 mid-story and stops has
found a real narrowing whose resolution is already written down. Do neither: do
not stop, and do not edit 139.

**Trap 7 — the count is a fact about the tree, and it has already rotted once.**
This spec was drafted on 2026-08-22 against **five** skills; `findings-ingest`
landed with 8edc028 and there are **six** at 602a92c. FR-001 therefore names the
directory rather than a number, and US1-S1's Then is written the same way. The
wrong move is to write `EXPECTED_SKILLS = ("floor-status", ...)` in a test or a
constant: the seventh skill lands, the tuple does not, and the wheel test goes
green while the payload is short by one. Derive the expected set from what the
repository ships, the way `tests/test_057_us2_stack_pack.py:296` —
`test_every_shipped_pack_travels_in_the_wheel` derives its own from
`resolve_stack_packs()` and asserts each resolved pack is present in the zip.

**Trap 8 — the destination is a function of the operator's home, not of where
the package landed, and XDG does not point at it.** An operator who installed
with `uv tool install` or `pipx` has the package in an isolated environment
whose location says nothing about where their agent reads skills — so a
destination derived from `__file__`, `sys.prefix` or the resolved package path
is wrong on exactly the installs this spec exists for. And `XDG_CONFIG_HOME` is
a live variable in this tree with a different job:
`factory/config.py:104-108` — `_xdg_config_home` honours it for the persona
registry. Claude Code's skills live at `~/.claude/skills/`, which is not under
`XDG_CONFIG_HOME`. FR-004. The wrong move is to "be consistent" by routing the
skills destination through `_xdg_config_home` — that writes them somewhere no
agent reads, and a skill written into a directory no agent reads is worse than a
refusal. Create the destination when it does not exist; do not refuse the first
install on a host whose operator has never run the agent.

**Trap 9 — `__pycache__` is inside the payload directory, and a wheel is the
only place you can see whether it travelled.** `.claude/skills/spec-html/`
contains a `__pycache__/` directory in the working tree, ignored by
`.gitignore:2` and therefore invisible to `git ls-files`. `force-include` copies
a source path into the wheel; whether hatchling applies its exclusion patterns
to a force-included directory is a question about hatchling's behaviour, not
about this repository, and the answer must be *read off a built wheel*. US1-S1's
Then asserts no `__pycache__` entry travels for exactly this reason. The wrong
move is to assume it is excluded because it is gitignored — the same assumption
`tests/test_057_us2_stack_pack.py:296`'s docstring already warns against for the
opposite case, where the harness must see an uncommitted file.

**Trap 10 — the record of what Ergane wrote may not live in the skills
directory, and may not be a timestamp.** FR-005, FR-006, FR-009 and FR-013 all
turn on one question: *did Ergane write these bytes?* A modification time cannot
answer it — a fresh checkout, a `cp -r`, a restore from backup and an edit all
move it — so the record is content digests, written when the verb writes. Two
wrong places to put it. **Inside `~/.claude/skills/`**: the agent reads that
directory, so a stray manifest there is a file the agent will try to make sense
of, and teardown then has to decide whether its own bookkeeping counts as a
skill. **Nowhere**: an implementer who compares the destination against the
shipped bytes alone cannot tell "the operator edited it" from "the operator has
an older version", so FR-005 keeps a stale skill forever and FR-006 reports a
write on every upgrade. Put it under Ergane's own state root,
`factory/cli/uninstall.py:617` — `_state_home`, whose docstring already settles
what `--purge` does with anything written there, and have US4 read it rather
than re-derive it.

## Sizing

**US1** touches `pyproject.toml` (one force-include entry), one new resolver
module under `factory/`, and `.github/workflows/release.yml` (one guard beside
the existing one). Its tests are one new module modelled on
`tests/test_057_us2_stack_pack.py:296` —
`test_every_shipped_pack_travels_in_the_wheel`, reusing
`tests/test_distribution_install.py:39` — `_build_wheel` and
`tests/test_distribution_rename.py:116` — `_wheel_contents` rather than building
a wheel by hand. Building a wheel in a test is the slow part; one build, several
assertions.

**US2** is the largest story and the one to watch against the 64 KiB
deterministic diff bound (D-050, `factory/verify/diffbounds.py`). In production
it touches one new noun module under `factory/cli/nouns/`, the install/record
half of US1's resolver module, `CONTEXT.md` (one entry in § "Flagged
ambiguities") and `README.md` (one bullet). Its tests are one new module driven
over a temporary home — never the operator's real one — plus the two `README.md`
sweeps, which are already parametrised and need no new test. Seven scenarios is
a lot for one node: keep the pasted evidence in its verification task to two
short runs, not a transcript.

**US3** touches the resolver module (the staleness answer) and the noun module
(one subcommand or flag). No new production file.

**US4** touches `factory/cli/uninstall.py` and nothing else in production: one
`Step` entry in the table at `factory/cli/uninstall.py:933`, its survey and its
perform, reading the record through the function US2 landed rather than
re-deriving it. Its tests go beside the existing teardown suite.

US3 and US4 share **no** production file — US3 stays in the resolver and the
noun, US4 stays in `factory/cli/uninstall.py` — which is what the Work Graph's
`concurrent_with: [US3]` on US4 records. US1 and US2 share the resolver module
and are sequenced by `depends_on_merged` for that reason as much as for
correctness.

## Verification the operator will run, independent of the gate

Per constitution VIII and D-037 the judge sees the diff and the criteria only,
so runtime evidence is committed as pasted output. Beyond that:

1. On a host with **no clone of this repository** — a fresh container or VM —
   `pip install ergane-cli` from the real index, then run the install verb, then
   start a Claude Code session there and confirm each skill resolves by name.
   This is the whole spec, run forwards, and it is the one step a checkout
   cannot fake.
2. Edit one installed skill by hand, re-run the verb, and confirm the edited one
   is named and kept while the others report as current. Then run
   `ergane uninstall --check` and confirm the skills step names the same file as
   kept before anything is removed.
3. Run the verb twice with nothing changed and confirm the second run reports a
   no-op rather than writes.
4. Put a file with a shipped skill's name at the destination that Ergane never
   wrote, run the verb, and confirm it is reported as a collision and left
   exactly as it was.
5. Install skills from one `ergane-cli` version, install a different version of
   the CLI, and run the check. It must name both **package** versions. Confirm
   with `ergane --version` that the revision half still reads `unknown` on that
   install — the value trap 5 says a check must never compare.
6. Run `ergane uninstall` to completion and confirm the host carries no Ergane
   skill files it did not have before, and that `CONTEXT.md` states the ruling on
   the word `skills` so no reader can confuse the persona field with the
   operator tooling.
