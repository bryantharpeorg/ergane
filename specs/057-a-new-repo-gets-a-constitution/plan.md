# Implementation Plan: a new repo gets a constitution

**Input**: [spec.md](spec.md) in this directory.

## Reuse inventory (verified against the tree 2026-08-18 — every anchor read)

The write path, the interview, the optionality this spec removes, and even a
one-branch ancestor of stack detection all exist. This feature adds data and a
default, not a subsystem.

- **The interview's optional-key machinery** — `factory/cli/init.py:262`
  (`_OPTIONAL_KEYS = ("timeouts", "standards", "roadmap", "forge")`), the prompt
  text at `:251` (`"standards": "standards document path (optional)"`), and
  `_ask_for_key` at `:419` where `optional = key in _OPTIONAL_KEYS` and an empty
  answer means omit (`:428` documents this). **This is the defect's location.**
  `standards` stops being omittable-into-nothing: it keeps a default rather than
  becoming mandatory, so no existing caller is forced to answer.
- **Stack detection already exists, with one branch** —
  `factory/cli/init.py:329` (`_default_gate_command`): if `pyproject.toml` is a
  file, propose `test: "uv run pytest -q"`, else `None`. US2 generalises exactly
  this — same question (what is this repo built with), same shape (propose, let
  the operator override), driven by pack data instead of an `if`.
- **The scaffold writer** — `_write_scaffold` at `factory/cli/init.py:801` and
  its caller at `:514`, which already writes the manifest, the `.gitignore`
  entry and `.ergane/` (`RUNTIME_ROOT = Path(".ergane")` at `:85`). The
  constitution is one more written artifact in a path that already knows how to
  create directories and report what it wrote (`:539`).
- **Manifest rendering and re-read defaults** — `_render_manifest` at `:462`,
  `_build_defaults` at `:394`, `_load_existing_defaults` at `:336` (which loads
  an existing manifest's values as interview defaults, so a re-run does not
  re-ask). `standards` already round-trips through `:410-411`.
- **The readiness path** — `--check` judges through `onboard.evaluate_repo`,
  extended rather than forked (documented at `factory/cli/init.py:29`), with the
  fact-gathering at `:951`. FR-012/FR-013 are new findings in that existing
  vocabulary, not a new report.
- **Package data shipping** — `pyproject.toml:44-45` force-includes
  `personas.yaml` into the package. The floor text and the stack packs ship the
  same way, and that mechanism is exactly what defect #103 (`b63388c`) existed
  to fix: **an installed Ergane must carry its data files, or a stranger's
  install seeds nothing.** Verify by inspecting a built wheel, never by reading
  the config.
- **The registry resolver as the precedent for reading package data** —
  `factory/config.py:44-65` (`_resolve_default_registry_path`): package data
  first via `importlib.resources`, development checkout second. Floor and pack
  data are resolved the same way, for the same reason.

## Traps (named so the implementer does not rediscover them)

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
  existing `_default_gate_command` returns `None` rather than guessing when it
  sees nothing; preserve that instinct when it sees too much.
- **A pack that names another stack's tool is worse than a missing pack**, because
  it looks authoritative. SC-003 asks for this to be checked mechanically —
  reading the packs is not evidence.
- **Optional must stay answerable.** Making `standards` mandatory would break
  every existing scripted walkthrough that omits it. It gains a default; it does
  not lose its optionality.
- **056 edits `pyproject.toml` too.** US1 of this spec force-includes the floor
  text and the stack packs through the same block at `pyproject.toml:44-45` that
  carries `personas.yaml`; US1 of 056 owns that whole file for the distribution
  rename. This is a file collision, not a dependency, so neither work graph will
  stop it — two in-flight worktrees there is a merge-queue conflict where the
  second lander rebases blind. Land one before dispatching the other, and if you
  are the second, re-read the block rather than trusting these line numbers.
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
  `factory/cli/init.py:428` — is right for an *absent* answer and wrong for a
  *wrong* one; keep the two cases apart.

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
generalised from `_default_gate_command`, the pack data, and the interview's
propose-and-override step. US3: the version marker in the composed output and
the advisory behind/unknown findings in `--check`. US4: template-source
resolution and the interview question that supplies it. All three later stories
merge-depend on US1 and share no file with each other — US2 in detection and
packs, US3 in the marker and `--check`, US4 in source resolution.

## Sizing

Four stories, none large. The floor and pack text are the bulk and they are
data, which compresses badly in a diff — if a story does not fit whole under
`DIFF_INPUT_LIMIT` (`factory/verify/diffbounds.py:42`, import it rather than
quoting it), say where you would split it: the natural seam is one pack per
story, and splitting on that costs nothing. Do not trim checks to fit.

US1 grew with the reframe: the floor text now carries a rationale per principle,
which is more prose in the same diff. If it stops fitting, the seam is the floor
text itself — ship the principles in one story and the governance section in
another — never the rationale, which is the thing the operator asked for.
