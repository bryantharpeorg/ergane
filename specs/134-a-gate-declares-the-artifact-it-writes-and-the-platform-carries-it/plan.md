# Implementation Plan: a gate declares the artifact it writes and the platform carries it

## Sizing refinement — 2026-09-11

The release additions grew US3 from nine to eleven scenarios, including the full
link/special-file/race matrix and two-phase freshness observation. The older
size comparison does not measure this expanded implementation. Re-measured
landed diffs are 55,374 bytes for084US1, 52,117 for101US2, 38,197 for087US2 and
38,067 for087US4, against the65,536-byte judge input bound. These are comparison
measurements, not a fabricated size prediction for unbuilt code. Split at the
source-reading boundary to give both implementation and behavioral evidence
their own bounded review, retaining every existing requirement and scenario.

Add **US6**, after US2 and before US3. Existing story numbers remain unchanged.
US6 owns `factory/verify/artifact_capture.py`, its typed observation/capture
results, and `tests/test_134_bounded_artifact_capture.py`. It takes an explicit
worktree root, normalized relative path and byte limit. It performs bounded
handle-based regular-file observation/capture with link/special-file refusal
and pre/post metadata/digest comparison. It never resolves an operational root,
writes durable artifacts, runs a gate, imports a workflow, or changes a verdict.
Internal bounded bytes may be returned to the in-process collector; they must
never become fields of a Temporal activity result.

The source boundary also supplies the **pre-gate** observation. Do not substitute
the existing git snapshot: ignored reports are absent from that snapshot, yet
must still have honest freshness provenance. Limit pre-gate reads as well as
post-gate reads. A refused or unavailable baseline stays unknown/refused, never
becomes a claim that the report was newly produced. Caller-supplied observations
and capture results must distinguish absent, permitted, oversized, unsafe and
unstable outcomes without inferring a producer from presence.

US3 keeps `GateArtifact`, the `GateResult.artifacts` field, destination plumbing,
and integration in `_run_watched`. It calls the US6 boundary before and after
the gate, applies the existing named stored-byte bound, and publishes only a
stable permitted result. It does not add a second `Path.read_bytes`/copy path
that bypasses US6. US3-S10/S11 remain integration requirements: reuse the real
file fixtures and parameterized cases from US6 to prove the actual collector
turns every refusal into artifact metadata without changing the gate verdict.
No source-safety scenario is replaced by a mock that simply returns refusal.

The full source matrix, its implementation and evidence now land in US6; US3's
diff adds carriage and integration assertions against that existing boundary.
Do not duplicate the matrix's fixture implementation or paste whole artifacts
as evidence. Each story still receives all required tests; this split changes
ownership and order, not coverage or acceptance. FR-020/FR-022 appear on both
nodes because primitive correctness and actual collector use are both required.

US5/US4 retain immutable capture persistence and explicit reader identity. Their
release-refined scenario counts are seven and four. The current order is
US1→US2→US6→US3→US5→US4. The older five-story sizing and file-map paragraphs
below remain dated provenance, superseded by this section. Derive a fresh
six-node graph and revalidate against the eventual dispatch base. Do not alter
the user's stale untracked graph or the judge's diff budget.

## Release refinement — 2026-09-10

Included in approved 0.6 packet scope; 167 consumes this carrier. Citation line
hints outside spec frontmatter were mechanically mapped from unchanged source
lines at602a92c to a654fca; the changed v2-key declaration was re-read at its
current line144. This refresh does not redate the older measurements below.
This section
supersedes earlier storage/path-only safety assumptions. Historical
anchor/provenance paragraphs below remain dated observations, not a claim of
fresh dispatch readiness. Revalidate all citations against the eventual landed
base before dispatch; do not use the stale untracked four-node graph in the
operator clone. Derive into a fresh isolated output path and preserve that file.

US3 also owns FR-020/FR-022: enforce containment/type on opened source handles,
reject symlink swaps/hardlink aliases/special files, and bound actual reads, not
just the initial stat. Record capture refusal independently of gate exit. Compare
pre-gate and captured metadata/digests to describe observed freshness; unchanged
preexisting bytes are carried but not claimed newly produced. A mid-read change
is explicit refusal, not a partial report. The packet consumer cannot undo an
unsafe read that happened before export, so do not defer safety to 167.

US5 also owns capture persistence under FR-021. Add dispatch plus immutable
capture identity to the supplied logical namespace and store a content digest;
old input defaults must remain loadable without claiming newly complete
attribution. New workflow inputs supply dispatch deterministically, never
environment/filesystem reads. A gate-list/capture invocation has stable identity
across activity redelivery, distinct from a repeated ordinal. Publish blobs
atomically outside the watched worktree; same identity+bytes is idempotent and
different bytes must never replace old evidence. No artifact bytes enter Temporal
payloads. Carry metadata in the existing gate JSON codecs, not a SQL migration.
Retain an immutable per-capture metadata manifest beside each stored capture,
with a bounded reference in the gate JSON. A later verification-row upsert may
replace its latest gate result, so older capture manifests must remain directly
addressable by declared dispatch/capture identity rather than reachable only
through that latest row. US4 resolves that explicit identity through the same
artifact storage boundary; do not build a second collector or scan worktrees.

US4's reader accepts explicit dispatch/capture selection and returns digest,
capture status and freshness. An old-style request remains supported only when
unambiguous; no silent coalescing of redispatches. Five story numbers and merge
order stay unchanged. Reassess US3's code+tests+evidence size before readiness;
split under a new story number if the safety cases erase its 64 KiB margin.

The remainder records the older refinement and measured mechanisms.

Every `file:line` below was read from `ergane-buildout` at `602a92c` on
2026-09-04 and verified to resolve to the symbol named. Do not trust an anchor
that has moved; re-read before editing.

**Count, so the next refiner knows what "re-read" has to mean here.** Measured
over the three files with fenced code masked, this trio carries **54 unique
anchors across 172 backticked citations**, 157 of them written in the
`path.py:NN` — `symbol` form. Only **113** of those are what the symbol tier
actually reads, and the gap is worth knowing before you trust a green run:
`_check_symbol_anchors` applies its regex one line at a time, so a citation whose
symbol half wraps onto the following line is invisible to it, and it strips
spec.md's frontmatter before it looks at anything — every citation in that block
is unchecked by construction, which is why the mis-cited `worktree_writes` line
survived a refinement. The 15 bare citations are the honest ones: module constants
(`_V2_TOP_LEVEL_KEYS`, `DEFAULT_VERIFICATION_DB_PATH`, `DEFAULT_RUNTIME_ROOT`,
`DIFF_INPUT_LIMIT`), one SQL line inside a string, and `.gitignore`, where symbol
form would be a refusal rather than a check. Every one of the 54 was re-read with
`sed` at `602a92c`. A green `ergane spec validate` is not "the anchors are good";
it is "113 of 172 citations landed inside the span of the symbol they name".

**Three of this spec's anchors had already moved before it was drafted, one of
its instructions was wrong when it was, and one anchor was still mis-cited after
the first refinement.** The `expected_artifacts` call the hand-over placed at line
2314, and a later re-measurement placed at 2433, is really inside `_verify`
(`factory/workgraph/workflow.py:2714` — `_verify`). The 2026-09-03 draft told the
implementer to hang the new declaration on `VerificationConfig`
(`factory/verify/models.py:1224` — `VerificationConfig`), which is the
**retry-ladder** configuration and carries no gate at all; the class that carries
`gates`, `timeouts` and `writes` is `FactoryConfig`
(`factory/verify/models.py:291` — `FactoryConfig`). And the refined spec cited
`worktree_writes` at `factory/verify/models.py:415` — `GateResult`, which is in
fact `output_tail`'s line; the field is at `factory/verify/models.py:417` —
`GateResult`. All three resolved green through `ergane spec validate` the whole
time, which is the point: a citation that lands on a real symbol, or inside the
right class, is not a citation that means what it says.

**And the first refinement settled the storage question the wrong way.** It said
the destination was "composed by `_verify`, which already knows the epic, the node
and the attempt". `_verify` (`factory/workgraph/workflow.py:2700` — `_verify`) is
Temporal workflow code: it knows the identity and may not read the environment or
the filesystem to turn it into a path. That correction is trap 7, and it is the
one that moved a story boundary.

## What already exists, and where

**The decoy.** `expected_artifacts` / `artifacts_present`
(`factory/verify/models.py:563` — `OutputCheck`) live on the output check, and
their one production caller passes an empty list literally
(`factory/workgraph/workflow.py:2714` — `_verify`):

```python
                base_ref=prepared.base_ref,
                expected_artifacts=[],
```

Their docstring (`factory/verify/models.py:527` — `OutputCheck`) says what they
are for: "Read scopes have nothing to diff, so they are judged on
`expected_artifacts` existing and being non-empty instead". That is the
anti-rubber-stamp check for read-scope nodes, not this feature.

**The manifest's gate grammar cannot hold a path.** `_read_gates`
(`factory/verify/factory_yaml.py:340` — `_read_gates`) requires each gate's value
to be a non-empty **string** — the command. So a sibling top-level key is the only
shape that does not break every existing manifest, and it must be added to
`_V2_TOP_LEVEL_KEYS` (`factory/verify/factory_yaml.py:144`) or
`_reject_unknown_keys` (`factory/verify/factory_yaml.py:281` —
`_reject_unknown_keys`) refuses it:

```python
#: Keys that only schema v2 recognises; v1 refuses them as unknown (US1-S6).
_V2_TOP_LEVEL_KEYS = _TOP_LEVEL_KEYS + ("ladder", "verify", "boundary_only_gates")
```

**There is already a sibling key of exactly this shape, and it is the model to
copy.** `caches:` (101 FR-004) is a list of mappings with a fixed key set, read by
`_read_caches` (`factory/verify/factory_yaml.py:761` — `_read_caches`) into
`CacheDeclaration` (`factory/verify/models.py:241` — `CacheDeclaration`). Read
that reader before writing US1: it does the entry-is-a-mapping refusal, the
unknown-key-inside-an-entry refusal, the empty-list refusal and — the part US1
needs most — a **path bound**, refusing at load time a declared path that escapes
the boundary it is allowed to name. `CacheDeclaration.path` is a `str`, not a
`Path`, and that is not an accident; see trap 5.

Copy its four refusal shapes and **invert its bound**, keeping yours lexical.
`_read_caches` refuses a *relative* path, calls `expanduser()`, calls `.resolve()`
and requires the result to be under `Path.home()`; its own docstring says the
filesystem touch is a deliberate departure — "This reader touches the filesystem,
and the departure is deliberate" — from a module of pure functions over text.
FR-012 wants the mirror image: repo-relative required, absolute refused, escape
judged against the repository root. Do not reach for `.resolve()` to judge it. The
manifest parser runs wherever the candidate CLI is invoked (`_main`,
`factory/verify/factory_yaml.py:1216` — `_main`), so a resolved comparison decides
the escape against whatever directory the reading process happens to sit in —
parse-time host-dependence a tmp-dir test cannot see, in a module whose other
readers are pure. Refuse an absolute path, and refuse any path whose normalised
segments leave the repository root, with no filesystem call at all. The names,
`artifacts:` and the closed type set, are US1's to define — see § Sizing.

**Where the declaration lands.** `FactoryConfig` (`factory/verify/models.py:291` —
`FactoryConfig`) is the parsed manifest: `gates`, `timeouts`, `writes: dict[str,
bool]`, `standards`, `landing_branch`, `roadmap`, `forge`, `ladder`,
`verify_order`, `diff_refusal_bytes`, `caches`. This is where an `artifacts` field
belongs. `VerificationConfig` (`factory/verify/models.py:1224` —
`VerificationConfig`) is the retry ladder and is the wrong class.

**`writes:` is a per-gate boolean, not a path allow-list.** `_read_writes`
(`factory/verify/factory_yaml.py:443` — `_read_writes`) returns `dict[str, bool]`
— "the gates this repo declares as legitimate writers" — and the demotion is one
line in `_to_result` (`factory/verify/gates.py:1583` — `_to_result`):

```python
    elif snapshot_error:
        status, exit_code = GateStatus.DIRTIED_WORKTREE, 0
    elif worktree_writes and not writes_declared:
        status, exit_code = GateStatus.DIRTIED_WORKTREE, 0
```

That branch is `factory/verify/gates.py:1629` — `_to_result`. There is no set of
paths to add one to; US2 is a **per-path
exemption** inside this decision, and it must sit below the `snapshot_error`
branch, not above it.

**The watch is blind to git-ignored paths, on purpose.** `snapshot_tree`
(`factory/verify/worktree_snapshot.py:83` — `snapshot_tree`) hashes the worktree
through `git add -A` into a throwaway index and `changes_between`
(`factory/verify/worktree_snapshot.py:100` — `changes_between`) diffs two of those
trees, so `worktree_writes` is "tracked content and unignored new paths only — the
same set `worktree.diff` puts in front of the judge"
(`factory/verify/models.py:395` — `GateResult`). A repository that git-ignores its
`coverage.xml` — most do — never triggers the demotion at all.

**Two runners reach one watched body, and one snapshot is handed forward.**
`_run_watched` (`factory/verify/gates.py:1511` — `_run_watched`) is where the
snapshot, the change comparison and `_to_result` all happen, and it is called by
exactly two callers: `_run_gate_list` (`factory/verify/gates.py:1416` —
`_run_gate_list`), which runs from a JSON view, and `_run_gate_list_from_config`
(`factory/verify/gates.py:1467` — `_run_gate_list_from_config`), which runs from an
in-process `FactoryConfig`. `run_gates` (`factory/verify/gates.py:1225` —
`run_gates`) chooses between them by whether the worktree carries its own manifest
parser — every Ergane node does. The closing snapshot is the next gate's opening
one:

```python
    after = snapshot_tree(invocation.cwd, env=env)
    change = changes_between(invocation.cwd, before, after, env=env)
```

`factory/verify/gates.py:1553` — `_run_watched`, returning `result, after` at
`factory/verify/gates.py:1566` — `_run_watched`, because "the 'after' snapshot is
returned so it becomes the next gate's 'before': N gates cost N+1 snapshots, not
2N, and every path is attributed to exactly one gate". Anything written into the
worktree between those two lines and the next gate's start is attributed to the
next gate. See trap 9.

**The JSON route drops any field it was not told to lift.** `_interpret_candidate`
(`factory/verify/gates.py:1045` — `_interpret_candidate`) reads `gates`,
`timeouts` and `writes` out of the candidate's stdout into `_AcceptedConfig`
(`factory/verify/gates.py:205` — `_AcceptedConfig`), whose docstring is the whole
warning:

```python
    "The subset the runner consumes" is the whole hazard: a field the manifest
    parser reads and the parser CLI emits still arrives here as nothing unless
    it is named. `writes` is carried for that reason (084 FR-012)
```

The emitter half needs nothing: `_main` (`factory/verify/factory_yaml.py:1216` —
`_main`) prints `json.dumps(dataclasses.asdict(config))` at
`factory/verify/factory_yaml.py:1239` — `_main`. The reader half is an allow-list.

**The per-gate result shape, and the boundary it crosses.** `GateResult`
(`factory/verify/models.py:374` — `GateResult`) has nine fields; `output_tail`
(`factory/verify/models.py:415` — `GateResult`) is bounded at 32 KiB, as its
docstring says at `factory/verify/models.py:379` — `GateResult`, and
`worktree_writes` is the field below it at `factory/verify/models.py:417` —
`GateResult`. A list of these is what the `run_gates` **activity** returns
(`factory/activities/verify_activities.py:263` — `run_gates`), so every field on
it is serialised into a Temporal payload. Its input dataclass is `RunGatesInput`
(`factory/activities/verify_activities.py:217` — `RunGatesInput`) — `worktree_path`,
`factory_yaml_path`, `timeout_overrides`, and nothing else — constructed at
`factory/workgraph/workflow.py:2700` — `_verify` with one argument.

**Where a host location comes from in this repository, and it is never the
workflow.** The workflow's only argument is `EpicInput`
(`factory/workgraph/workflow.py:578` — `EpicInput`): a graph, a proxy url, the
ladder's dials, and no runtime root. `PreparedWorktree`
(`factory/workgraph/worktree.py:264` — `PreparedWorktree`) says why in its own
docstring — "captured here because the workflow cannot run git itself
(constitution IV)". Two activities resolve a host location instead, and **only one
of them reaches the engine's runtime-root resolver**. Read both before writing
US5, because the difference between them is the whole of FR-017. The model to copy
is `factory_root`:

```python
def factory_root() -> Path:
    """The worker host's state directory (plan.md § Storage).

    Relative by default, so it resolves against the worker's working directory
    exactly the way 001's ledger and 002's evidence store do.  Honors the legacy
    `FACTORY_ROOT` env name and reports it once per process.
    """
    root, _choice, _source = worktrees.resolve_factory_root(FACTORY_ROOT_ENV)
```

`factory/activities/agent_activities.py:179` — `factory_root`, which calls
`resolve_factory_root` (`factory/workgraph/worktree.py:191` —
`resolve_factory_root`), the one engine resolver.

`_store_path` (`factory/activities/verify_activities.py:634` — `_store_path`) is
the other activity, and it models only *where* — resolution happens activity-side,
never in the workflow. It is not the model for *how*, and an implementer who reads
it expecting one is handed the wrong pattern: it calls `resolve_env_path`
(`factory/env.py:47` — `resolve_env_path`), a generic two-name environment reader
that never touches `resolve_factory_root`, and falls back to the hardcoded literal
`DEFAULT_VERIFICATION_DB_PATH = ".factory/verification.db"`
(`factory/activities/verify_activities.py:128`). That is a legacy root plus a
private env pair — the fifth-resolver shape trap 7 forbids, already in the file
US5 edits. Take the *site* from `_store_path` and the *resolver* from
`factory_root`.

`worktree_path` (`factory/workgraph/worktree.py:289` — `worktree_path`) is the
naming convention for anything under the resolved root: "Never inside the target
clone: factory state there would read as agent work in 002's diff check (FR-004),
and salvage would commit it." Read that docstring as what it means and
not as a path-prefix rule: on this host the runtime root *is* inside the clone,
and it is git-ignored, which is what keeps it out of the diff check. Trap 15.

**Persistence is a JSON column and two codecs.** `gate_results` is
`TEXT NOT NULL, -- JSON: list[GateResult]` (`factory/verify/store.py:216`), written
by `_gate_to_dict` (`factory/verify/store.py:1091` — `_gate_to_dict`) and read by
`_gate_from_dict` (`factory/verify/store.py:1105` — `_gate_from_dict`), which
defaults every field added since the row was written. `_gate_to_dict` emits every
field it knows unconditionally, so a row written after this spec necessarily gains
an artifact key — which is why US3-S7, US5-S5 and US5-S6 are worded as equality in
every field that existed before, not as equality of the row. Adding a field to
`GateResult` and to those two functions is the whole of persistence; no schema
migration is needed. The exported readers a consumer already imports are
`node_history` (`factory/verify/store.py:873` — `node_history`) and
`attempt_timings` (`factory/verify/store.py:944` — `attempt_timings`), over a
connection from `connect_readonly` (`factory/verify/store.py:401` —
`connect_readonly`). US4's reader belongs beside them.

**The judge's prompt already renders gate results, and there is one function that
does it.** `_gate_blocks` (`factory/verify/judge.py:430` — `_gate_blocks`), landed
by 116, names each gate's fields explicitly — name, status, exit code, command,
and a bounded tail for a gate that did not pass. It is the function an implementer
"finishing the job" would add an artifact line to, and it is the one FR-011's
control has to be asserted against. See trap 13.

**The producer half already exists in a real consumer**, emitting Cobertura
`coverage.xml`, vitest JSON and audit JSON at stable paths, specifically so a
platform collector can take them unchanged.

## Traps

**Trap 1 — `expected_artifacts` IS A DECOY WITH EXACTLY THE RIGHT NAME.** It is
the first thing an implementer will find and the obvious thing to extend. Its
docstring (`factory/verify/models.py:527` — `OutputCheck`) is explicit that it is
the anti-rubber-stamp check for read-scope nodes, and its one production caller
passes `[]` inside `_verify` (`factory/workgraph/workflow.py:2714` —
`_verify`). **Reusing it produces a spec
that appears to land and changes nothing**, because the field is inert at its only
call site. FR-006 names a new carrier — `GateResult.artifacts` — for that reason.

**Trap 2 — THE CONFIG WITH THE RIGHT-SOUNDING NAME IS THE WRONG CLASS, AND THE
PREVIOUS DRAFT OF THIS PLAN FELL FOR IT.** `VerificationConfig`
(`factory/verify/models.py:1224` — `VerificationConfig`) is "per-deployment caps
for the retry ladder" — `max_attempts`, `max_judge_retries`, `gate_timeout_s`. It
holds no gate names and reaches no gate runner. The parsed manifest, with `gates`,
`timeouts` and `writes` on it, is `FactoryConfig` (`factory/verify/models.py:291` —
`FactoryConfig`). FR-001 lands there. A declaration parked on `VerificationConfig`
would parse, store, round-trip and never be read by anything that runs a gate.

**Trap 3 — `writes:` IS A BOOLEAN PER GATE, NOT A LIST OF PATHS, AND THE BLANKET
FIX PASSES EVERY OBVIOUS TEST.** FR-004, FR-005. An implementer reading "reaches
the gate's write allow-list" will go looking for a path set to append to and will
not find one: `_read_writes` (`factory/verify/factory_yaml.py:443` —
`_read_writes`) returns `dict[str, bool]` and the decision is `worktree_writes and
not writes_declared` (`factory/verify/gates.py:1629` — `_to_result`). Two wrong
moves are within reach and **both are green under every scenario except one**:
setting `writes_declared` true for a gate that declared an artifact, and writing
the branch as `elif worktree_writes and not writes_declared and not
artifact_paths:`. Either excuses **every** path that gate wrote — which silently
retires 084's watch for every artifact-emitting gate in the fleet — and the first
also lies on the record, because `writes_declared` means "the manifest named this
gate in its `writes:` block". The reproduction that catches both is US2-S6: one
gate, one declared artifact path written, one undeclared unignored path written,
`DIRTIED_WORKTREE` expected. The right move is to subtract this gate's declared
artifact paths from the set the demotion tests, leaving `worktree_writes` and
`writes_declared` untouched, and to do it **below** the `snapshot_error` branch so
an unreadable tree still demotes (US2-S5).

**And that subtraction is string equality against git's own spelling, which is the
third wrong move and the quietest.** The set it subtracts from is filled by
`changes_between` (`factory/verify/worktree_snapshot.py:100` — `changes_between`)
from `git diff-tree -r --name-only -z`, which prints one normalised
worktree-root-relative path per entry and never a `./` prefix or a `..` segment. A
manifest that declares `./coverage.xml`, or `reports/../coverage.xml`, passes US1's
path bound as written (neither is absolute, neither escapes the root) and collects
perfectly, because `Path(worktree) / "./coverage.xml"` opens the right file — and
then misses the subtraction by a prefix, so the gate is demoted for writing the very
artifact it declared. That is the self-defeat US2 exists to prevent, reached through
a spelling instead of through a blanket exemption. The two spellings are made
identical **at load time**, in US1's reader (FR-012, US1-S8): normalise what you
accept. Do not loosen the comparison here — a fuzzy match would start excusing paths
the manifest never named, which is the first wrong move wearing a different hat.

**Trap 4 — A SCENARIO WRITTEN OVER A GIT-IGNORED ARTIFACT PASSES WITH NO
PRODUCTION CODE AT ALL.** `snapshot_tree`
(`factory/verify/worktree_snapshot.py:83` — `snapshot_tree`) runs `git add -A`, so
ignored paths never enter the tree it hashes, and `worktree_writes` is "tracked
content and unignored new paths only" (`factory/verify/models.py:395` —
`GateResult`). Most repositories git-ignore `coverage.xml`. Write US2's fixture
over an **unignored** path or the story's headline test is green before it starts.
The same fact points the other way for US3: collection must **read the declared
path from disk**, never from `worktree_writes`, or every git-ignored artifact —
the common case — silently collects nothing.

**Trap 5 — THE DECLARATION REACHES THE RUNNER THROUGH JSON, AND THE READER IS AN
ALLOW-LIST.** FR-013, FR-014. `_main` (`factory/verify/factory_yaml.py:1216` —
`_main`) emits the whole config with `dataclasses.asdict`, so the emitter needs no
change — but two things follow. First, `_interpret_candidate`
(`factory/verify/gates.py:1045` — `_interpret_candidate`) lifts only the fields it
names into `_AcceptedConfig` (`factory/verify/gates.py:205` — `_AcceptedConfig`),
so a field added to `FactoryConfig` and threaded only through
`_run_gate_list_from_config` (`factory/verify/gates.py:1467` —
`_run_gate_list_from_config`) is parsed, emitted and never read on the route every
Ergane node actually takes; the unit tests still pass. Second, whatever the
declaration is made of must survive `json.dumps`: `CacheDeclaration.path`
(`factory/verify/models.py:241` — `CacheDeclaration`) is a `str` and not a `Path`
for this reason, and a type field must be a `StrEnum` like `GateStatus` or a plain
`str` — a plain `Enum` raises inside `_main`, which the caller cannot distinguish
from a crashed parser and which falls back silently.

**Trap 6 — THE BYTES MAY NOT TRAVEL ON THE RESULT.** FR-016. `GateResult` is the
return type of the `run_gates` activity
(`factory/activities/verify_activities.py:263` — `run_gates`), so anything on it is
serialised into a Temporal payload, and an SBOM is routinely megabytes. Carrying
bytes there converts a large artifact into a failed activity — a feature that adds
evidence becoming one that breaks builds, which is this spec's recurring hazard.
The record carries a reference: the declared path, the type, presence, the size,
and the location the bytes were written to.

**Trap 7 — THE COMPONENT THAT KNOWS THE ATTEMPT MAY NOT RESOLVE A PATH, AND THE
LAST REFINEMENT TOLD AN IMPLEMENTER TO MAKE IT.** FR-017. The previous plan said
the destination was "composed by `_verify`, which is the code that already knows
the epic, the node and the attempt". `_verify` (`factory/workgraph/workflow.py:2700`
— `_verify`) is Temporal workflow code. It has the identity and nothing to turn it
into: `EpicInput` (`factory/workgraph/workflow.py:578` — `EpicInput`) carries no
runtime root, and workflow code may not read the environment or the filesystem —
the same constitution IV rule `PreparedWorktree`
(`factory/workgraph/worktree.py:264` — `PreparedWorktree`) cites for capturing a
git fact in an activity. An implementer told to compose it there reaches one of
two wrong answers, and **the first one passes every scenario in this spec**:
compose under `prepared.path`, where the bytes are destroyed with the worktree —
which is gap step 4, the thing this spec exists to end; or hardcode `.ergane` under
`request.graph.target_repo` (`factory/workgraph/models.py:265` — `WorkGraph`),
which is wrong under an `ERGANE_ROOT` / `FACTORY_ROOT` override and wrong on the
legacy `.factory` root this repository is actually running
(`factory/activities/verify_activities.py:128`). Those two reasons are the whole
of it. A previous draft of this trap gave a third — that factory state inside the
target clone is forbidden by `worktree_path`'s docstring — and that reason is
false of this deployment; see trap 15, which is why FR-017 no longer asks for it.
**The activity resolves; the workflow passes identity.** `_store_path`
(`factory/activities/verify_activities.py:634` — `_store_path`) and `factory_root`
(`factory/activities/agent_activities.py:179` — `factory_root`) are the two
in-repo models of *where* that resolution happens, and only `factory_root` models
*how*: it calls `resolve_factory_root` (`factory/workgraph/worktree.py:191` —
`resolve_factory_root`), the one engine resolver. `_store_path` reaches
`resolve_env_path` (`factory/env.py:47` — `resolve_env_path`) and a hardcoded
`.factory/verification.db` instead, which is the shape FR-017 must not copy. Use
`resolve_factory_root` — do not write a fifth one. One
more thing that resolver will not do for you: it returns a **relative** `.ergane`
when no override is set, which is the class four ledger findings and spec 129 are
about. Make the composed destination absolute before a byte is written, and record
the absolute location (US5-S3).

**Trap 8 — A DESTINATION PARAMETER ADDED ONLY WHERE IT IS USED NEVER ARRIVES.**
FR-017, FR-018. `_run_watched` is four frames below the activity. The destination
has to cross `run_gates` (`factory/verify/gates.py:1225` — `run_gates`), then
whichever runner that call chose — `_run_gate_list`
(`factory/verify/gates.py:1416` — `_run_gate_list`) or
`_run_gate_list_from_config` (`factory/verify/gates.py:1467` —
`_run_gate_list_from_config`) — and only then `_run_watched`
(`factory/verify/gates.py:1511` — `_run_watched`), the way `writes_declared`
already does: "decided by the two runners, which is where the manifest is, and
passed down rather than looked up here". A parameter added to `_run_watched` alone
compiles, unit-tests green and collects nothing in production. US3 threads all
four frames with an empty default meaning "collect nothing", which is what every
caller written before this spec passes; US5 is the story that supplies a value.

**Trap 9 — THE COLLECTOR MUST NOT WRITE INSIDE THE WORKTREE IT IS WATCHING.**
FR-018. `_run_watched` takes its closing snapshot at
`factory/verify/gates.py:1553` — `_run_watched` and hands it forward as the next
gate's opening snapshot (`factory/verify/gates.py:1566` — `_run_watched`). Copy an
artifact's bytes into a directory under the worktree after that line and the next
gate is charged with the write and demoted to `DIRTIED_WORKTREE` — this spec's own
recurring hazard, a feature that adds evidence becoming one that breaks builds, in
its purest form. The destination is outside the worktree by construction under
FR-017; US3-S8 is the two-gate control that proves the collector did not put it
there anyway.

**Trap 10 — `opaque` is not a fallback, it is a type.** FR-008. It is tempting to
treat an unrecognised artifact as an error or to drop it. The whole reason the type
set includes `opaque` is that an artifact the platform does not understand must
still be carried and still be attributable — otherwise every new format is a
platform change before a consumer can use it.

**Trap 11 — Declared-and-absent is a record, not a silence.** FR-007. A gate that
declares `coverage.xml` and does not write it has told the operator something. The
easy implementation collects what exists and omits the rest, which makes "the gate
did not emit it" indistinguishable from "nobody declared it".

**Trap 12 — An oversized artifact is recorded, not truncated.** FR-015. The
tempting symmetry is `output_tail`, which keeps the last 32 KiB
(`factory/verify/models.py:379` — `GateResult`) — correct for a log and wrong for
an artifact, because half an SBOM is not a smaller SBOM, it is a corrupt one. Above
the bound, record present, record the true size, store nothing.

**Trap 13 — DO NOT TOUCH THE JUDGE, AND THE FUNCTION YOU MUST NOT TOUCH HAS A
NAME.** FR-011. The judge's prompt already renders gate results: `_gate_blocks`
(`factory/verify/judge.py:430` — `_gate_blocks`), landed by 116, walks each
`GateResult` and writes out the fields it names. It is three lines of temptation
away from listing an artifact, and admitting one is a change to what the judge may
see, which constitution VIII and D-037 govern and which deserves its own decision
entry. An implementer who "finishes the job" there has made a constitutional change
inside a collection story. US3-S9 is the control, and it is asserted against
`_gate_blocks` by name so that adding a line there fails a test rather than passing
a review.

**Trap 14 — The acceptance target is a consumer's existing files, unchanged.** The
producer half is already built at stable standard paths in a real target
repository. The best proof this spec works is that those files are captured with
**no edit to that repository**. Design the declaration so that is true; if a
consumer would have to move a file or rename it, the shape is wrong.

**Trap 15 — THE RUNTIME ROOT IS ROUTINELY INSIDE THE TARGET CLONE, AND A
CONTAINMENT GUARD WOULD BREAK EVERY GATE RUN IN THIS FACTORY.** FR-017. Measured
on the host that will build this spec: `scripts/ergane-env.sh` emits
`ERGANE_ROOT=$HOME/code/ergane/.factory`, the target repository for this factory's
own epics is `/home/admin/code/ergane`, and both `.ergane/` and `.factory/` exist
there and are git-ignored (`.gitignore:17-18`). The node worktrees themselves live
at `.factory/worktrees/<epic>/<node>` — `worktree_path`
(`factory/workgraph/worktree.py:289` — `worktree_path`) composes exactly that. And
with no override set, `resolve_factory_root` (`factory/workgraph/worktree.py:191` —
`resolve_factory_root`) returns a bare **relative** path — `DEFAULT_RUNTIME_ROOT`
(`factory/workgraph/worktree.py:93`), or the legacy `.factory` when only that
directory exists — which absolutises against the worker's working directory, and
this worker's working directory is the clone again: the installed user unit
`ergane-worker.service` sets `WorkingDirectory=/home/admin/code/ergane` (read on
this host, line 11; it is not a file in this repository, so it carries no anchor). So "under the resolver's root" and "outside
the target clone" are **contradictory** here, and the wrong way out of the
contradiction is the forbidden move in trap 7: invent a location outside the
clone, which is a fifth resolver wearing a disguise. `worktree_path`'s "Never
inside the target clone" means "never inside a checkout whose diff is scored" —
the ignore rules, not the path prefix, are what keep factory state out of 002's
diff. Two consequences for the implementer. First, assert containment against the
**node worktree** and nothing else; a test that pins the destination outside the
clone passes on a tmp root and fails in production. Second, do not add a guard
that raises when the composed destination is under the target repository:
`RunGatesInput` (`factory/activities/verify_activities.py:217` — `RunGatesInput`)
carries no target-repository path to compare against, and a guard invented from
one would refuse every gate run on this host — this spec's recurring hazard, a
feature that adds evidence becoming one that breaks builds.

**Trap 16 — A REQUIRED MAPPING KEY MUST REFUSE BEFORE IT IS INDEXED.** US1-S9,
FR-002. `FactoryConfigError` (`factory/verify/factory_yaml.py:190`) is the
manifest's data boundary: the parser CLI translates it to its declared rejection
code. PR #523's first US1 candidate checked unknown keys and then read
`entry["gate"]`, `entry["type"]`, and `entry["path"]` directly. A valid-YAML
entry missing any one of those fields therefore escaped as raw `KeyError`, exit
1 and a traceback even though every declared test passed. Follow `_read_caches`
(`factory/verify/factory_yaml.py:761` — `_read_caches`): read a required field
with `.get`, validate its presence/type, and raise the typed refusal naming the
entry and field before any later gate, type or path check. T066 must exercise the
library and CLI faces so catching the exception in only one caller cannot pass.

## Sizing

**US1** — `factory/verify/factory_yaml.py` (`artifacts` in `_V2_TOP_LEVEL_KEYS`, a
reader modelled on `_read_caches` with its bound inverted and its accepted path
normalised to git's spelling, trap 3) and
`factory/verify/models.py` (the `ArtifactType` `StrEnum`, the
`ArtifactDeclaration` record and the `FactoryConfig` field). Nine scenarios, all
of them table-driven parse-or-refuse-or-normalise, so the test file is wide and
shallow. Small.

**US1 owns the four type names, and US3 reuses them.** The closed set —
`sbom`, `coverage`, `scan`, `opaque` — is defined once, as an `ArtifactType`
`StrEnum` in `factory/verify/models.py` beside `CacheDeclaration`
(`factory/verify/models.py:241` — `CacheDeclaration`), because US1's reader is the
half that produces the refusal naming the permitted types (US1-S2) and because a
`StrEnum` survives `dataclasses.asdict` plus `json.dumps` for the same reason
`GateStatus` (`factory/verify/models.py:73` — `GateStatus`) does (trap 5). US3
puts that same enum on `GateArtifact` rather than minting a second spelling; two
copies of a four-name set is two things to keep in step and one refusal message
that can disagree with the record it describes.

**US2** — `factory/verify/gates.py` only: the lift in `_interpret_candidate`, the
field on `_AcceptedConfig`, the declaration parameter through both runners into
`_run_watched`, and the per-path exemption inside `_to_result`. Small, and the
risk is in the fixture, not the diff (traps 3 and 4).

**US3** — `factory/verify/models.py` (`GateArtifact` and the `GateResult` field,
reusing US1's `ArtifactType`) and `factory/verify/gates.py` (the destination parameter
across four frames and the collection call in `_run_watched`), plus one test file
for nine scenarios and the pasted evidence. Two production files, and the largest
test file in the trio. **Paste one artifact's record as evidence, not four**: the
committed evidence for T034 is a single collected record and a single
declared-and-absent record, not a dump per type.

**US5** — `factory/activities/verify_activities.py` (the identity fields on
`RunGatesInput` and the destination composed beside `_store_path`),
`factory/workgraph/workflow.py` (the identity passed from `_verify`, and nothing
else) and `factory/verify/store.py` (the two codecs). Six scenarios. Three
production files but three small diffs.

**US4** — `factory/verify/store.py` only: one exported function beside
`node_history`, and a test file with three scenarios. Smallest story in the trio.

**Why US3 and US5 are two stories.** Before this split US3 owned five production
files, eight scenarios and the pasted evidence, and the destination plumbing this
plan now requires would have gone into it as well. The measured comparables on this
branch are 084-US1 at 55,374 bytes, 084-US3 at 49,371, 101-US2 at 52,117 and
057-US4 at 63,932 against `DIFF_INPUT_LIMIT = 64 * 1024`
(`factory/verify/diffbounds.py:47`, D-050) — the last of those landed with 1,604
bytes of margin. A story that has to be hoped through the bound is a story that was
sized by wishing. The cut is at the seam the story already had: what a gate's
result carries and how it is filled (US3), against where the bytes go and how the
row survives (US5).

The file map: US3 shares `factory/verify/models.py` with US1 and
`factory/verify/gates.py` with US2; US5 shares `factory/verify/store.py` with US4;
US3 and US5 share nothing. Every pair that shares a file has a merge edge between
them, so the graph's contention inference has nothing to add.

One cross-spec note the operator should hold: spec 128, drafted the same day, also
adds a v2 sibling key and also touches `factory/verify/factory_yaml.py` and
`factory/verify/models.py`. If both epics run at once, expect a textual conflict in
`_V2_TOP_LEVEL_KEYS` and in `FactoryConfig`'s field list. It is a one-line conflict
in each and the merge queue is where it belongs; it is not a reason to serialise
the two specs.

**One artifact the operator MUST clear before dispatch, and it is not optional.**
This spec directory carries a `workgraph.json` compiled on 2026-09-04, before the
refinement that added US5 and FR-012 through FR-019, and it now contradicts the
trio it sits beside. Measured against the file on disk: it declares four nodes
(`us1`..`us4`), its requirement keys stop at FR-011, **US5 does not exist in it at
all**, and `us4` merges after `us3` rather than after `us5`. Eight requirements —
FR-012 through FR-019 — appear in no node, so a dispatch from it would land US3
inert (it collects into a destination parameter that no story supplies) and would
never dispatch the story that supplies it.

The reason this is a live hazard and not a tidiness note is that one entry point
does not re-derive. The roadmap re-derives through its `derive_spec` activity and
`ergane spec derive` re-derives by definition, so both read the trio; but
`ergane build start` calls `load_workgraph(args.graph)`
(`factory/cli/nouns/build.py:852` — `start_command`) and dispatches whatever is on
disk. The file is also untracked and **not** git-ignored, so a `git add` on this
directory commits the stale graph alongside the spec.

Two ways to clear it, either is fine: delete
`specs/134-a-gate-declares-the-artifact-it-writes-and-the-platform-carries-it/workgraph.json`,
or re-derive it with `ergane spec derive` once this trio is final. Deleting is not
a departure from house convention — the landed sibling 126 tracks `spec.md`,
`plan.md`, `tasks.md` and an `evidence/` directory and no compiled graph at all,
while 97 older spec directories still track one, which is the open ledger key
`ci/workgraph-artifacts-tracked-inconsistently` in one sentence. And D-025 is not
a reason to leave it: what D-025 says is that a `workgraph.json` is "never
hand-authored and never inferred", and deleting a stale one or re-deriving it is
neither — D-034 retired hand-trimmed remainder graphs on exactly that reading. A
previous version of this paragraph cited D-025 as grounds for inaction and
under-counted the missing requirement keys as five; both are corrected here.

This refinement pass is not permitted to remove it — the pass may write only
`spec.md`, `plan.md` and `tasks.md` in this directory — so the deletion is an
operator action, and § Verification the operator will run names it again before
its first numbered step.

## Verification the operator will run, independent of the gate

**Before any of it, and before any dispatch: clear the stale `workgraph.json`
this directory carries** — delete it, or re-derive it with `ergane spec derive`.
It was compiled before US5 and FR-012..FR-019 existed, `ergane build start` loads
a compiled graph off disk without re-deriving, and it is untracked but not
git-ignored. § Sizing has the measurement.

Per constitution VIII and D-037 the judge sees the diff and the criteria only, so
runtime evidence must be committed as pasted output. Beyond that:

1. On a target repository that already emits a coverage file at a stable path,
   declare it in the manifest **without changing anything else in that
   repository**.
2. Confirm the declared path is one the repository does not git-ignore, then run
   an attempt. The gate must not be demoted for writing it. Repeat with the path
   git-ignored: the gate must still pass and the artifact must still be collected.
3. Run an attempt whose gate writes its declared artifact **and** one undeclared
   unignored path. The gate must be demoted, and both paths must appear in its
   `worktree_writes`: the exemption is per path, and a run where this gate passes
   means 084's watch has been retired for every artifact-emitting gate.
4. Read the attempt's record through the exported reader. The artifact must be
   there with its type, its producing gate and a stored location; that location
   must be an absolute path, must not be under the node worktree, and must hold the
   same bytes the gate wrote. It **may** sit inside the target clone — on this host
   the runtime root is `/home/admin/code/ergane/.factory`, git-ignored, and the node
   worktrees are under it (trap 15); what is being checked is that the bytes came
   from the resolver's root and outlive the worktree, not that they left the clone. Then delete the node worktree and read it again — the
   bytes must still be there, because "readable per attempt afterwards" is half of
   what the declared ledger keys asked for.
5. Run an attempt with two gates, the first of which emits a declared artifact.
   The second gate's status and `worktree_writes` must be what they are with
   nothing declared.
6. Declare an artifact the gate does not write, run again, and confirm the record
   says declared-and-absent rather than saying nothing.
7. Declare an artifact larger than the stored-bytes bound and confirm the record
   carries its true size and no stored location, and that nothing truncated was
   written.
8. Confirm a repository declaring no artifacts produces a stored row that reads
   back identical, in every field that existed before this spec, to the one it
   produced before the change.

Step 1's "without changing anything else" is the falsifiable test of the whole
spec: a consumer has already built the producer half at standard paths on the
explicit expectation that a platform collector could take it unchanged, and if it
cannot, this spec has solved a different problem.
