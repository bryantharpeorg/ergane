# Implementation Plan: a new repo gets a constitution

**Input**: [spec.md](spec.md) in this directory.

## Reuse inventory (RE-VERIFIED against the tree 2026-09-02 at `5fa87c2`)

**The 2026-08-18 inventory below had rotted in every line but one.** Sixteen
anchors were re-read; fifteen had moved, and only one of those was caught by
`ergane spec validate`, because the other fourteen still resolved to real,
non-blank, plausible lines. The worst case: line 251 of the init module was
cited as the standards prompt text and now resolves to a subprocess keyword
argument. An implementer sent to that line would have gone hunting, at the
operator's expense. That is the
defect class 072 exists to name, and the reason this pass happened at all is
that 072 landed the day before this refinement.

Every anchor below was read from `5fa87c2`. Do not trust one that has moved;
re-read before editing.

The write path, the interview, the optionality this spec removes, and a
one-branch ancestor of stack detection all still exist. This feature adds data
and a default, not a subsystem.

- **The interview's optional-key machinery** — `_OPTIONAL_KEYS`
  (`factory/cli/init.py:473`), whose members include `standards`
  (`factory/cli/init.py:475`); the standards prompt string in the `_PROMPTS`
  table at `factory/cli/init.py:443`, which reads "standards document path
  (optional)"; and `_ask_for_key` (`factory/cli/init.py:936`), whose docstring
  states the rule
  at `factory/cli/init.py:945` ("Empty answers for optional keys ... mean
  'omit'") and applies it at `factory/cli/init.py:955`. **This is the defect's
  location, and it is now narrower than it was in August — see trap 1.**
  `standards` stops being omittable-into-nothing: it keeps a default rather than
  becoming mandatory, so no existing caller is forced to answer.
- **Stack detection already exists, with one branch — under a new name and a new
  return type.** `_default_gate_command` is gone; it is now `_default_gates`
  (`factory/cli/init.py:591`), and it returns a **mapping**, not a rendered YAML
  line — its own docstring records the change at `factory/cli/init.py:596`. The
  body is unchanged in shape: `if (repo_root / "pyproject.toml").is_file()`
  (`factory/cli/init.py:600`) returns `{"test": "uv run pytest -q"}`
  (`factory/cli/init.py:601`), else nothing. US2 generalises exactly this — same
  question, same propose-and-override shape, driven by pack data instead of an
  `if`. Write against the dict.
- **The scaffold writer** — `_write_scaffold` (`factory/cli/init.py:1690`) and
  its single caller (`factory/cli/init.py:1190`), which already writes the
  manifest, the `.gitignore` entry and `.ergane/`
  (`RUNTIME_ROOT = Path(".ergane")` at `factory/cli/init.py:127`). The
  constitution is one more written artifact in a path that already knows how to
  create directories.
- **Manifest rendering and re-read defaults** — `_render_manifest`
  (`factory/cli/init.py:1035`), `_build_defaults`
  (`factory/cli/init.py:878`), and `_load_existing_defaults`
  (`factory/cli/init.py:605`), which loads an existing manifest's values as
  interview defaults so a re-run does not re-ask.
- **The readiness path** — `--check` judges through
  `factory/mergequeue/onboard.py:150` — `evaluate_repo`, extended rather than
  forked; the intent is
  documented at `factory/cli/init.py:29` (the one anchor in this inventory that
  did **not** move), and the fact-gathering is at `factory/cli/init.py:1855`.
  FR-012/FR-013 are new findings in that existing vocabulary, not a new report.
- **Package data shipping** — the force-include block is now at
  `pyproject.toml:73`, and it carries **three** entries, not one:
  `personas.example.yaml` (`pyproject.toml:74`) plus the two container
  confinement artifacts spec 104 added (`pyproject.toml:75-76`). The floor text
  and the stack packs ship the same way. That mechanism is what defect #103
  (`b63388c`) existed to fix: **an installed Ergane must carry its data files, or
  a stranger's install seeds nothing.** The pattern is now proven three times
  over, which is a stronger precedent than it was in August. Verify by inspecting
  a built wheel, never by reading the config.
- **The registry resolver as the precedent for reading package data** —
  `_resolve_default_registry_path` (`factory/config.py:81`): package data first
  via `importlib.resources`, development checkout second. Floor and pack data are
  resolved the same way, for the same reason.

## Traps (named so the implementer does not rediscover them)

- **TRAP 1, AND IT IS NEW: spec 120 landed on this exact code and fixed the
  OTHER half. Do not re-fix it, and do not overturn it.** `120-an-init-that-finds-
  a-manifest-keeps-it` landed 2026-09-01. Its FR-005 reordered the two branches in
  the non-interactive default path (`factory/cli/init.py:923-931`) because an
  early return for `_OPTIONAL_KEYS` was discarding the operator's *committed*
  `standards` value one line before it would have been used — "a wired repository
  came back declaring no standards document at all and every node it dispatched
  afterwards ran with none" (`factory/cli/init.py:920`).
  That is a **different defect** from this spec's, and the boundary between them
  is stated in 120's own comment at `factory/cli/init.py:927-931`: the remaining
  `None` is "reached only when the repository declared nothing for this key",
  annotated **"(FR-008: a fresh repository still gets nothing)"**.
  So: 120 stopped init destroying a declaration that existed. 057 gives a
  repository that never had one a document to point at. 120 also states, at
  `factory/cli/init.py:938-943`, that empty-answer-means-omit is "unchanged by
  120 US2 and deliberately so" — an operator shown their own value and answering
  empty is asking for it to go, and that must keep working. **Nothing in this
  spec may make an empty answer stop meaning omit.** What changes is what a
  repository that was never asked, or that answered empty on a fresh repo, ends
  up with on disk. An implementer who reads only the code and not this trap will
  either re-implement 120 or argue with it; both waste the attempt.
- **The floor is authored, not filtered.** Do not generate it by reading
  `.specify/memory/constitution.md` and dropping principles. Ergane's principle
  I carries the invariant rule ("each component ships as a small vertical slice
  with tests before the next begins") in a body that names specs 003/004/005 and
  D-024; principle III carries "no dependency without approval" in a body that
  is Ergane's own approved roster. A filtered copy seeds spec numbers into repos
  they mean nothing in. Write the floor as new generic text, once.
- **The Ergane-product principles must not travel** (FR-006). Determinism at the
  Core, Spend Is Attributed, Personas Over Model Tiers describe how Ergane is
  built and bind the factory, not its targets.
- **This repository is the dangerous test subject.** Ergane already has a
  constitution, and the natural way to test seeding is to run `init` here. That
  is the one place a bug overwrites the document every dispatched agent obeys.
  SC-002 exists for this: running `init` in this repository leaves
  `.specify/memory/constitution.md` byte-identical. Write that test first.
- **An empty file exists** (edge case list). Overwrite guards keyed on "is the
  file non-empty" will silently fill a deliberately empty standards file. The
  guard is existence, not content.
- **`.specify/memory/` will not exist** in a brownfield repo, so the write path
  creates parents — but it must not create them when it is *not* going to write,
  or `--check` leaves directories behind in a repo it promised to write nothing
  in (FR-012, FR-013 both say "writes nothing").
- **`forget` must leave the seeded file** (FR-015). This narrows a guarantee
  stated elsewhere — that `forget` leaves the tree byte-identical — and the
  narrowing has to be written where an operator reads it, not just implemented.
  A seeded constitution is the user's content; `ergane.yaml` and `.ergane/` are
  Ergane's bookkeeping. Only the second kind is removed.
- **Detection must not guess through ambiguity.** Two stack markers in one repo
  (`pyproject.toml` beside `package.json`) is a question, not a coin flip. The
  existing `_default_gates` (`factory/cli/init.py:591`) declines rather than
  guessing when it sees nothing; preserve that instinct when it sees too much.
- **A pack that names another stack's tool is worse than a missing pack**, because
  it looks authoritative. SC-003 asks for this to be checked mechanically —
  reading the packs is not evidence.
- **Optional must stay answerable.** Making `standards` mandatory would break
  every existing scripted walkthrough that omits it. It gains a default; it does
  not lose its optionality.
- **The 056 collision is RESOLVED — 056 landed, and so did 104.** The August plan
  warned that `056-the-factory-ships-as-a-package` owned `pyproject.toml` and
  would collide here. Both `056` and `104` have since landed and both edited the
  force-include block, which now sits at `pyproject.toml:73-76` with three
  entries. There is no in-flight competitor for that file. The standing advice
  survives the resolution: re-read the block rather than trusting these line
  numbers, because it has moved twice since this spec was drafted.
- **This is a default, not a decree, and the wording is the feature.** The
  operator's ruling on 2026-08-18 was that the seeded principles read as example
  templates. A wall of MUSTs in someone else's repository invites deletion of
  the whole file — including the two principles that would have saved them. Give
  each principle its *why* (FR-016) and phrase the mechanical two as
  consequences (FR-017): *criteria a judge cannot check against the diff will
  fail no matter how many attempts you spend*. Persuasion survives deletion;
  assertion does not. And nothing may re-impose a principle the user removed —
  FR-002 already forbids touching an existing document, so the trap is a later
  "helpful" repair path, not the write path.
- **A missing template source is a refusal, not a fallback** (FR-018). An
  operator who names a template and silently gets Ergane's instead has been lied
  to about whose standards their agents obey. Refuse at interview time, name the
  path. The nearby instinct — `_ask_for_key`'s empty-answer-means-omit at
  `factory/cli/init.py:955` — is right for an *absent* answer and wrong for a
  *wrong* one; keep the two cases apart. Trap 1 explains why that instinct is
  load-bearing and may not be weakened to make this case easier.

## New data and modules

- **Default floor text** — generic principles plus governance, carried as
  package data with a version, resolved `importlib.resources`-first. Each
  principle carries its own one-line *why* (FR-016), and the two that follow
  from the factory's mechanics are phrased as consequences rather than
  obligations (FR-017). That is a property of the authored text, so it is
  written once, in US1, and reviewed with the text — not added later.
- **Stack packs** — one data file per stack (Python and a language-agnostic
  fallback at minimum; the operator chose "scalable by tech stack or repo type",
  so the count is a shipping decision and the *mechanism* is the requirement).
  Each declares its marker files, toolchain, test/lint/type commands and
  dependency policy. FR-010: adding one touches no code.
- **Template source resolution** (US4) — supplied-then-shipped, one function,
  with the chosen source returned alongside the text so the composer can record
  it. The shipped default becomes one branch of this rather than the only path;
  writing US1 with the resolver's shape in mind costs nothing and saves US4
  rewriting the write path.
- **The composer** — floor + stack pack + an empty, named project section +
  governance, rendered once. Pure function of (floor, pack, project name,
  source), which is what makes US1, US2 and US4 testable without a repository.

## Evidence discipline

Criteria are judged from the diff alone (constitution VIII / D-037): no base
tree, no terminal, no commit message. Every criterion here is provable from
committed files — fixtures, the composed output, and the packs themselves — so
no story needs pasted runtime evidence. SC-002 is the exception to watch: prove
it with a test that asserts byte-identity against a fixture copy, not by
running `init` in the live checkout during a gate.

## Structure

US1: the write path in `factory/cli/init.py` (default for `standards`, the
overwrite refusal, the composer call, the `--check` finding for absence), plus
the floor data — worded per FR-016/FR-017 — and its resolver. US2: detection
generalised from `_default_gates` (`factory/cli/init.py:591`), the pack data, and
the interview's propose-and-override step. US3: the version marker in the composed output and
the advisory behind/unknown findings in `--check`. US4: template-source
resolution and the interview question that supplies it. All three later stories
merge-depend on US1 and share no file with each other — US2 in detection and
packs, US3 in the marker and `--check`, US4 in source resolution.

## Sizing

Four stories, none large. The floor and pack text are the bulk and they are
data, which compresses badly in a diff — if a story does not fit whole under
`DIFF_INPUT_LIMIT` (`factory/verify/diffbounds.py:47`, import it rather than
quoting it), say where you would split it: the natural seam is one pack per
story, and splitting on that costs nothing. Do not trim checks to fit.

US1 grew with the reframe: the floor text now carries a rationale per principle,
which is more prose in the same diff. If it stops fitting, the seam is the floor
text itself — ship the principles in one story and the governance section in
another — never the rationale, which is the thing the operator asked for.
