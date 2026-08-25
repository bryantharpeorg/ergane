"""The pre-dispatch preflight checks a graph cannot carry (US2 FR-004/005/006).

Two read-only facts a `WorkGraph` cannot hold, read from the proxy before any
epic dispatches: the model aliases the registry names for an epic's personas
are *served*, and the first-attempt key aliases that epic will mint do not
*collide* with a live key. Both are knowable before a single credential is
issued, and finding them at dispatch costs one message instead of attempts,
issued keys and a burned node.

044 adds a third fact with the same shape and no proxy at all: **every node of
the graph can assemble its attempt prompt** from the trio the epic's spec
directory holds. It belongs here because it is the same bargain — knowable
offline, ruinous at dispatch. On 2026-08-15 a four-node epic was dispatched
whose `tasks.md` phase headings named each story's title and never its key;
one tick later every node was dead, killed before any agent ran, and the price
of learning it was an epic. `check_prompt_assembly` is that lesson moved to
`ergane spec validate`, where it costs one command.

044 US2 gives it the second surface the alias checks already have, for the
reason validation alone was never enough: a `tasks.md` edited after a clean
`spec validate` still arrives broken, because dispatch reads the trio live.
`prompt_assembly_preflight` is the same check in the preflight's own
vocabulary, run before any node of an epic starts — by the roadmap (inside the
pre-dispatch activity, never in workflow code: the workflow cannot read files)
and by `ergane build start`. A spec whose prompts cannot assemble parks exactly
the way one whose aliases are unserved does, with nothing dispatched.

It is deliberately *not* a second reader of the authored markdown. It calls
`build_attempt_prompt` — the public assembler the dispatch path itself calls —
once per node and reports what it refuses. A check with its own copy of the
heading grammar would agree with dispatch right up until the day one copy was
edited, which is a worse position than having no check (044 FR-004).

044 US3 adds the complement, `slice_coverage_findings`, because a refusal is
only half the defect class. The same sweep that found the killed epic found a
`tasks.md` whose phases were numbered against a story list that had since moved:
three of its four nodes assembled a slice perfectly and were handed the *next*
story's task list, and only the fourth — which no heading named at all —
reported anything. A silent wrong answer is worse than a refusal, because
nothing says so and the attempt bills for the misunderstanding. So the lint asks
the second question assembly cannot: not whether a slice was found, but whether
the work the author wrote for a story is inside the slice that story's node will
be handed. It reads the slices through `task_slice_bounds` for the same reason
assembly reads through `build_attempt_prompt` — one grammar, one answer.

107 US4 adds the two facts the *landing* turns on, for the same bargain a third
time: which repository owns each node's worktree, and whether the branch the
landing will target is declared or inferred from whatever the target clone is
checked out on. Both are one git read; both were previously read for the first
time after the agent, the gate and the judge had been paid, and on 2026-08-24
seven of eight stories passed everything and then died in the landing path. They
belong here rather than in `_onboard_target` for the reason everything else here
does — this is the one module both dispatch surfaces already share — and because
the factory root they need is a worker-host fact a workflow cannot read.

This is the pure core shared by the two callers that run a preflight:

- `ergane build start` runs it in-process (CLI) before starting the workflow,
  so a misconfigured epic never becomes a workflow that has to be killed.
- the roadmap workflow (US2) runs it as an activity before starting each
  dispatchable spec's child epic, so a misconfigured spec *parks* with the
  finding verbatim rather than stalling the line (FR-006).

The split is the same one `factory/activities/merge_activities.py` draws for
onboarding: a pure library function (`check_aliases`) that both an offline
CLI path and an activity call, so the two surfaces cannot drift. The CLI owns
its own client/registry construction (it reads `personas.yaml` from its host
and dials the proxy from the environment); the activity owns its own. What
neither owns — the alias math, the finding wording, the read-failure shape —
lives here, once.

A proxy that does not answer is a **distinct** finding (`transport=True`)
naming the address tried — never a silent pass, and never conflated with
"not served" (FR-005). The caller decides what that means for an operator:
the CLI maps it to `EXIT_TRANSPORT`; the roadmap parks the spec with the
finding verbatim regardless, because a parked finding is what FR-006 demands
and a transport outage parks the same way an unserved alias does.

`PreflightFinding` is the same shape as 003's onboarding `Finding`
(check/passed/detail) so the two surfaces read alike; `transport` is the
FR-005 discriminator. It lived in the CLI until US2 gave it a second caller —
the roadmap pre-dispatch activity — so it moved here, and the CLI re-exports
it so nothing that imported the CLI's name changes.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from factory.activities.usage_activities import key_alias_for
from factory.config import Persona
from factory.registry import resolve_state_home
from factory.supervision.engine_identity import cli_version, engine_skew, read_identity
from factory.usage.litellm_client import LiteLLMClient, LiteLLMError
from factory.verify.criteria import mask_fences
from factory.verify.factory_yaml import (
    MANIFEST_NAME,
    FactoryConfigError,
    load_factory_config,
    resolve_manifest_path,
)
from factory.workgraph.models import WorkGraph
from factory.workgraph.prompt import (
    PLAN_DOCUMENT,
    SPEC_DOCUMENT,
    TASKS_DOCUMENT,
    PromptAssemblyError,
    build_attempt_prompt,
    task_slice_bounds,
)
from factory.workgraph.workflow import JUDGE_PERSONA
from factory.workgraph.worktree import (
    WorktreeError,
    _ownership_refusal,
    _worktree_ownership,
    landing_branch,
    worktree_path,
)


@dataclass(frozen=True)
class PreflightFinding:
    """One fact the preflight checked before dispatch (US2 FR-004/005/006).

    The same shape as 003's onboarding `Finding` (check/passed/detail) so the
    two surfaces read alike; a local type was defined only because 003 had not
    landed, and it must be swapped for the shared type the moment it is
    importable rather than kept as a near-duplicate.

    `transport` is the FR-005 discriminator: `True` when the proxy would not
    answer a preflight read (so the operator's move is to go look at the
    proxy), `False` when it answered and something the operator can fix in the
    registry or the credential store is wrong.
    """

    check: str
    passed: bool
    detail: str
    transport: bool = False


@dataclass(frozen=True)
class AssemblyFinding:
    """One node whose prompt will not assemble, and the document at fault.

    Three fields because an operator needs three things and the offline layer,
    the roadmap park and a future `--json` reader all need them apart rather
    than glued into a sentence: which node (so a graph of sixteen is not a
    search), which authored file to open, and the assembler's own refusal
    verbatim.

    `detail` is quoted, never paraphrased — it is the same discipline the
    prompt applies to gate tails. The refusal already names the node and the
    story, and an operator who is handed a summary of it has been handed a
    description of the defect instead of the defect.

    `node_id` is `None` for the findings that belong to no node: a document that
    could not be read at all is a fact about the trio, not about any one story.
    """

    document: str
    detail: str
    node_id: str | None = None

    def __str__(self) -> str:
        return f"{self.document}: {self.detail}"


def assembly_findings(
    graph: WorkGraph,
    *,
    spec_text: str,
    plan_text: str,
    tasks_text: str,
    standards: str | None = None,
) -> list[AssemblyFinding]:
    """Assemble every node's prompt and report each refusal (044 FR-001).

    Pure: three texts in, findings out. No filesystem, no registry, no proxy,
    no clock — which is what lets the roadmap run this inside an activity on the
    same bytes the dispatch activities loaded (FR-007) while the CLI runs it on
    the bytes it just read, with no risk that the two surfaces answer
    differently.

    Every node is attempted, and one node's refusal never stops the next: an
    author fixing one heading per run, with the second revealed only after the
    first is fixed, is the failure mode the deriver's collected rejections
    already exist to avoid. The 2026-08-15 epic had four broken nodes and needed
    one edit pass, not four.

    `standards` is the declared path, not the document, and is carried only so
    the assembled bytes are the bytes dispatch would assemble. Assembly has no
    failure mode that depends on it.
    """
    findings: list[AssemblyFinding] = []
    for node in graph.nodes:
        try:
            build_attempt_prompt(
                node=node,
                epic_id=graph.epic_id,
                spec_text=spec_text,
                plan_text=plan_text,
                tasks_text=tasks_text,
                standards=standards,
            )
        except PromptAssemblyError as exc:
            findings.append(
                AssemblyFinding(
                    document=exc.document, detail=str(exc), node_id=node.id
                )
            )
    return findings


def check_prompt_assembly(
    graph: WorkGraph,
    feature_dir: str | Path,
    *,
    spec_text: str | None = None,
) -> list[AssemblyFinding]:
    """Read the epic's trio off disk, then assemble every node's prompt.

    The reading half of the offline check: `<feature_dir>/spec.md`, `plan.md`
    and `tasks.md`, the three documents `load_prompt_sources` reads at dispatch.
    `spec_text` may be supplied by a caller that has already read `spec.md` —
    `ergane spec validate` derived the graph from it — so the bytes assembly is
    checked against are provably the bytes the graph was compiled from.

    A document that cannot be read is a **finding naming its path**, never an
    exception: this runs inside a refinement command, and an author who deleted
    a `plan.md` should be told so in the same sentence grammar as every other
    refusal rather than shown a stack trace (US1 scenario 4).

    When any document is missing, per-node assembly is skipped. A prompt cannot
    be assembled out of a file that is not there, and letting the loop run would
    bury the one fact that matters under one restatement of it per node.
    """
    directory = Path(feature_dir)
    texts: dict[str, str] = {}
    unreadable: list[AssemblyFinding] = []
    for document, already_read in (
        (SPEC_DOCUMENT, spec_text),
        (PLAN_DOCUMENT, None),
        (TASKS_DOCUMENT, None),
    ):
        if already_read is not None:
            texts[document] = already_read
            continue
        path = directory / document
        try:
            texts[document] = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            unreadable.append(
                AssemblyFinding(
                    document=document,
                    detail=(
                        f"cannot read {path}: {exc} — no node of this epic can "
                        "be handed a prompt until it is there"
                    ),
                )
            )

    if unreadable:
        return unreadable

    return assembly_findings(
        graph,
        spec_text=texts[SPEC_DOCUMENT],
        plan_text=texts[PLAN_DOCUMENT],
        tasks_text=texts[TASKS_DOCUMENT],
    )


#: The preflight check name the roadmap parks under and the CLI prints, in the
#: `model-aliases-served` house style: a hyphenated fact about the epic, stable
#: enough for an operator to grep a park history for. The offline validate layer
#: names the same check `prompt_assembly`, because a validate *layer* is named
#: the way the other four layers are; one check, two surfaces, and the wording
#: an operator acts on — the assembler's own refusal — is identical in both.
PROMPT_ASSEMBLY_CHECK = "prompt-assembly"


def prompt_assembly_preflight(
    graph: WorkGraph, feature_dir: str | Path
) -> list[PreflightFinding]:
    """Every node's prompt, assembled before dispatch, as preflight findings (FR-003).

    The same `check_prompt_assembly` the offline validate layer calls, in the
    vocabulary the roadmap and `ergane build start` already refuse in. Nothing is
    re-read and nothing is re-worded: this maps the assembler's refusal onto
    `PreflightFinding` and adds the one fact a park needs that a validate finding
    does not — that the refusal happened *instead of* dispatch.

    `passed=False` only, because a preflight finding is a refusal here: the
    alias checks emit nothing when they pass, and an empty list is what a caller
    reads as "every node can be handed a prompt".

    `transport` stays `False` for the same reason it is a discriminator at all
    (FR-005): it means the proxy would not answer. This check never asks it. A
    trio it cannot read is a fact about the spec directory the operator edits,
    not about a service the operator restarts, and `check_prompt_assembly`
    already reports that as a finding naming the path.
    """
    return [
        PreflightFinding(
            check=PROMPT_ASSEMBLY_CHECK,
            passed=False,
            detail=f"{finding.document}: {finding.detail}. Nothing was dispatched.",
        )
        for finding in check_prompt_assembly(graph, feature_dir)
    ]


# --- slice coverage: the tasks that reach no agent (044 US3) ------------------

#: A task id at the head of a list item, in the three shapes `tasks.md` writes
#: them: `- [ ] T001`, `- [X] T001`, `- [ ] **T001**`, and the bare `- T001`.
#: Anchored at the item, so a continuation line or a dependency note that
#: mentions an id in prose is not mistaken for the task itself.
_TASK_LINE_RE = re.compile(r"^\s*[-*]\s+(?:\[[^\]]*\]\s+)?\*{0,2}(T\d{3}[a-z]?)\b")

#: The two ways a task line names the story it belongs to. Both are in this
#: repository's own corpus — the template's tag, and the citation a task uses to
#: point at the acceptance scenario it covers. A third form found later is a
#: reason to widen this deliberately, not silently.
_STORY_TAG_RE = re.compile(r"\[US(\d+)\]")
_STORY_CITATION_RE = re.compile(r"\bspec\s+US(\d+)-")


@dataclass(frozen=True)
class CoverageFinding:
    """One task line's relationship to the slices, when that relationship is news.

    Two severities, because two different things are wrong and only one of them
    is an error. A task that names a story and falls outside that story's slice
    is a **defect** (FR-005): the author wrote work for a story, and no agent
    building that story will ever see it. A task inside no slice that names no
    story is **information** (FR-006): a setup or verification phase is a real
    convention in this corpus, its ids are the operator's own closing pass, and
    failing validation on them would fail specs that are correct.

    `task_ids` is a tuple because the informational finding groups every orphan
    into one line — an author reading five separate notes about the same
    `## Verification` phase learns nothing the list did not already say.
    """

    task_ids: tuple[str, ...]
    detail: str
    informational: bool = False
    story_key: str | None = None
    slice_keys: tuple[str, ...] = ()

    def __str__(self) -> str:
        return self.detail


@dataclass(frozen=True)
class _TaskEntry:
    """One task as authored: its id, the line it starts on, and its whole text.

    Whole text because the story reference is not reliably on the id's line —
    the tag usually is, the `spec US<n>-` citation frequently is not, since a
    task wide enough to matter wraps. `line` is the id's own line, and it is
    what decides which slice the task sits in: a task belongs where it starts.
    """

    task_id: str
    line: int
    text: str


def _task_entries(
    lines: Sequence[str], in_code: Sequence[bool]
) -> list[_TaskEntry]:
    """Every authored task in document order, continuations folded in.

    Fence-masked with the assembler's own `mask_fences` (044 plan trap 2): the
    tasks template quotes its own grammar, and a task quoted inside a fence is
    text *about* a task. It is never cut into a slice and never handed to an
    agent, so a lint that counted it would report a defect in a line that does
    not exist.
    """
    entries: list[_TaskEntry] = []
    index = 0
    while index < len(lines):
        if in_code[index]:
            index += 1
            continue
        match = _TASK_LINE_RE.match(lines[index])
        if match is None:
            index += 1
            continue
        start = index
        index += 1
        while (
            index < len(lines)
            and not in_code[index]
            and lines[index].strip()
            and lines[index][:1].isspace()
            and _TASK_LINE_RE.match(lines[index]) is None
        ):
            index += 1
        entries.append(
            _TaskEntry(
                task_id=match.group(1),
                line=start,
                text="\n".join(lines[start:index]),
            )
        )
    return entries


def _referenced_stories(text: str) -> list[str]:
    """The story keys a task names, deduplicated and in numeric order."""
    numbers = {
        int(number)
        for number in _STORY_TAG_RE.findall(text) + _STORY_CITATION_RE.findall(text)
    }
    return [f"US{number}" for number in sorted(numbers)]


def slice_coverage_findings(
    graph: WorkGraph, *, tasks_text: str
) -> list[CoverageFinding]:
    """Which authored tasks the slices drop, and which reach nobody (FR-005/006).

    Pure: a graph and one text in, findings out. The slices are not re-derived
    here — `task_slice_bounds` is the assembler's own scan, so the lines this
    calls "inside a slice" are exactly the lines dispatch would cut into one
    (FR-004). What this adds is the complement, which assembly cannot see: a
    slice that assembles is not a slice that contains the work.

    Three verdicts per task, and the two that are silent matter as much as the
    one that is not:

    - It names a story and sits in that story's slice, or it names none and sits
      in some slice: nothing. This is almost every task in the corpus.
    - It names a story and sits somewhere else: a defect, naming the id, the
      story and the slice it landed in. That covers both the phase-level
      Tests/Implementation split (the work falls into no slice at all) and the
      mis-numbered phase list (the work falls into the neighbouring story's).
    - It names nothing and sits in no slice: information.

    A task naming a story whose slice did not assemble is deliberately silent:
    `check_prompt_assembly` already refuses that node by name, and restating it
    once per task would bury the one fact the author has to act on under a list
    of consequences of it.
    """
    lines = tasks_text.splitlines()
    in_code = mask_fences(lines)

    bounds: dict[str, tuple[int, int]] = {}
    for node in graph.nodes:
        try:
            bounds[node.story_key] = task_slice_bounds(node, tasks_text)
        except PromptAssemblyError:
            continue

    findings: list[CoverageFinding] = []
    orphans: list[str] = []
    for entry in _task_entries(lines, in_code):
        inside = tuple(
            story_key
            for story_key, (start, end) in bounds.items()
            if start <= entry.line < end
        )
        referenced = _referenced_stories(entry.text)

        if not referenced:
            if not inside:
                orphans.append(entry.task_id)
            continue

        for story_key in referenced:
            if story_key in inside:
                continue
            if inside:
                landed = " and ".join(inside)
                findings.append(
                    CoverageFinding(
                        task_ids=(entry.task_id,),
                        story_key=story_key,
                        slice_keys=inside,
                        detail=(
                            f"task {entry.task_id} names story {story_key}, but it "
                            f"sits inside the task slice cut for {landed} — the "
                            f"node building {story_key} is never shown it, and the "
                            f"node building {landed} is shown it instead"
                        ),
                    )
                )
            elif story_key in bounds:
                findings.append(
                    CoverageFinding(
                        task_ids=(entry.task_id,),
                        story_key=story_key,
                        detail=(
                            f"task {entry.task_id} names story {story_key}, but it "
                            f"falls outside the task slice cut for {story_key} and "
                            "inside no other — no node is shown it"
                        ),
                    )
                )

    if orphans:
        findings.append(
            CoverageFinding(
                task_ids=tuple(orphans),
                informational=True,
                detail=(
                    "task ids inside no story's slice and naming no story, so they "
                    "reach no node: " + ", ".join(orphans) + " — expected in a "
                    "setup or verification phase the operator works by hand, a "
                    "defect anywhere else"
                ),
            )
        )
    return findings


def check_slice_coverage(
    graph: WorkGraph,
    feature_dir: str | Path,
    *,
    tasks_text: str | None = None,
) -> list[CoverageFinding] | None:
    """Read the epic's `tasks.md`, then report what its slices drop.

    `None` means **not checked**, and a caller must report it that way rather
    than as a pass: there is no `tasks.md` to locate a slice in, so the lint has
    no opinion (044 plan trap 5). It is not conflated with the empty list, which
    is the lint having looked and found nothing. `check_prompt_assembly` already
    emits the finding that names the unreadable path, so this returns quietly
    instead of duplicating it.
    """
    if tasks_text is None:
        path = Path(feature_dir) / TASKS_DOCUMENT
        try:
            tasks_text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None
    return slice_coverage_findings(graph, tasks_text=tasks_text)


# --- what the landing needs, asked before the build (107 US4) -----------------

#: The two checks in the `model-aliases-served` house style: a hyphenated fact
#: about the epic, stable enough for an operator to grep a park history for.
WORKTREE_OWNERSHIP_CHECK = "node-worktree-ownership"
LANDING_BRANCH_CHECK = "landing-branch-declared"


def worktree_ownership_findings(
    graph: WorkGraph, factory_root: Path | str
) -> list[PreflightFinding]:
    """Every node whose existing worktree belongs to another clone (FR-009).

    The predicate is US1's, imported rather than re-derived (plan R2): the tree
    already held three independent answers to "which repository owns this
    directory", and this is the report of the same fact `ensure()` refuses on, so
    a second derivation could disagree with the enforcement it is warning about.
    Both of its assertions matter here for the reason they matter there (plan
    trap 1) — the runtime root normally sits inside a clone, and git walks *up*,
    so a bare directory answers a legitimate `--show-toplevel` with exit 0.

    `factory_root` is the caller's to supply and is never read from the
    environment, because the two surfaces resolve different ones: `ergane build
    start` runs in the operator's shell and the roadmap's activity on the worker.
    On a deployment where those differ this arm reads a directory tree that is
    not the one the epic will build in, so the root it read is *part of the
    answer* — printed in every finding, so an operator can tell "checked and
    clean" from "checked the wrong disk" (plan R5). This is the cheap early
    report; `ensure()`, which runs beside the directory it judges, is the
    guarantee.

    One git call per *existing* directory and none for the rest: the first
    dispatch of every epic has no worktrees at all, and paying a subprocess per
    node to learn what `Path.is_dir()` already answered would tax the common path
    for nothing.

    Every offending node, never the first: a graph of sixteen with three foreign
    directories needs one cleanup pass, not three dispatches.
    """
    root = Path(factory_root)
    repo = Path(graph.target_repo)
    findings: list[PreflightFinding] = []
    for node in graph.nodes:
        path = worktree_path(root, graph.epic_id, node.id)
        if not path.is_dir():
            continue
        try:
            ownership = _worktree_ownership(repo, path)
        except WorktreeError:
            # Git would not answer — most often because the dispatched clone is
            # not on the host running this check. There is no identity to
            # compare against, and every remaining node would fail the same way,
            # so stop rather than repeat one infrastructure failure per node.
            # Unchecked, never a pass: `ensure()` still refuses on the worker.
            break
        if ownership.owned:
            continue
        findings.append(
            PreflightFinding(
                check=WORKTREE_OWNERSHIP_CHECK,
                passed=False,
                detail=(
                    f"node {node.id}, under the factory root this check read "
                    f"({root.resolve()}): "
                    f"{_ownership_refusal(repo, path, ownership)}"
                ),
            )
        )
    return findings


def landing_branch_findings(graph: WorkGraph) -> list[PreflightFinding]:
    """The landing branch, when it would be a guess rather than a declaration.

    `landing_branch` fails open on purpose — a target clone with a missing or
    malformed manifest keeps working by reading whatever branch the clone is
    checked out on — and that fallback is the ambient state constitution IX
    names: correct on the machine where it was written, wrong in the
    configuration nobody tried, and silent either way. Three times in eight days
    it opened a landing PR against an operator's working branch, each time after
    a full build had been paid for. So the branch is resolved here the way the
    landing resolves it, and the *arm that answered* is reported (FR-010).

    The value comes from `landing_branch` and from nowhere else, so no caller can
    end up with a branch this check did not see. What is asked separately is
    whether the repository's own manifest answered — the same
    `(FactoryConfigError, OSError)` pair `landing_branch` treats as "no
    declaration", so the two cannot disagree about which arm ran.

    A repository this host cannot read at all is silent rather than reported:
    there is no branch that "would be used", and a check that cannot see the
    clone must not be confused with one that read a broken manifest (plan R5).
    """
    repo = Path(graph.target_repo)
    complaint = _undeclared_landing_branch(repo)
    if complaint is None:
        return []
    try:
        branch = landing_branch(repo)
    except (WorktreeError, OSError, subprocess.SubprocessError):
        return []
    return [
        PreflightFinding(
            check=LANDING_BRANCH_CHECK,
            passed=False,
            detail=(
                f"the target repo {repo.resolve()} declares no landing branch "
                f"this check could read ({complaint}), so the landing would "
                f"target `{branch}` — inferred from that clone's checked-out "
                f"HEAD, not declared. Add `landing_branch: <branch>` to its "
                f"{MANIFEST_NAME} so the landing targets the branch the "
                "repository chose rather than the one it happens to be sitting "
                "on. Nothing was dispatched."
            ),
        )
    ]


def _undeclared_landing_branch(repo: Path) -> str | None:
    """The loader's own complaint when no manifest declared a branch, else `None`.

    Quoted rather than paraphrased, the same discipline the assembly findings
    apply to the assembler's refusal: an operator told "the manifest is
    unreadable" has been handed a description of the defect, and one told which
    key the parser refused has been handed the defect.
    """
    try:
        manifest_path, _ = resolve_manifest_path(repo)
        load_factory_config(manifest_path)
    except (FactoryConfigError, OSError) as error:
        return str(error)
    return None


def engine_skew_findings() -> list[PreflightFinding]:
    """Refuse dispatch when the running engine's version differs from this CLI.

    Reads the identity record from the host's supervision home — the same
    absolute path the container writes to because `compose.reference.yaml` passes
    `HOME` through and mounts the state root same-path.  No identity file is a
    silent pass: native engines and pre-105 containers have no record, and the
    check activates only on evidence.

    The refusal's `transport` is ``False`` because the operator's move is an
    upgrade, not a proxy restart.
    """
    identity = read_identity(resolve_state_home())
    sentence = engine_skew(identity, cli_version())
    if sentence is None:
        return []
    return [PreflightFinding(check="engine", passed=False, detail=sentence, transport=False)]


def landing_readiness_preflight(
    graph: WorkGraph, factory_root: Path | str
) -> list[PreflightFinding]:
    """Both landing preconditions, collected, for both dispatch surfaces (FR-011).

    One entry point so `ergane build start` and the roadmap's pre-dispatch
    activity cannot drift in *which* checks they run any more than they can drift
    in what those checks say — the split the module docstring draws is that the
    caller owns its host's facts (its factory root, its client, its registry) and
    this module owns the checks and the wording.

    Collected rather than short-circuited, like every other check here: an
    operator fixing one refusal per run is the failure mode, and it is dearer at
    this seam than at the others because each round trip is a dispatch that has
    to be started again.
    """
    return worktree_ownership_findings(graph, factory_root) + landing_branch_findings(
        graph
    )


def first_attempt_aliases(graph: WorkGraph) -> set[str]:
    """The aliases this epic's first attempts will mint (US2 FR-006).

    Each node's attempt-1 key (under its persona) and the judge's attempt-1 key
    (the judge scores while the node's key is live, on its own alias). These are
    the deterministic aliases the proxy would reject a duplicate of at dispatch
    — a collision knowable before any key is issued.
    """
    aliases: set[str] = set()
    for node in graph.nodes:
        aliases.add(key_alias_for(graph.epic_id, node.id, 1, node.persona))
        aliases.add(key_alias_for(graph.epic_id, node.id, 1, JUDGE_PERSONA))
    return aliases


def aliases_to_check(
    graph: WorkGraph, registry: Mapping[str, Persona]
) -> dict[str, set[str]]:
    """alias -> personas naming it, for the graph's LLM personas and the judge.

    A deterministic persona (`agent == "none"`) gets no key and mints nothing, so
    it contributes no alias. The judge is included even when no node names it,
    because it is always resolved and always mints a first-attempt key.
    """
    persona_names = {node.persona for node in graph.nodes}
    persona_names.add(JUDGE_PERSONA)
    named_by: dict[str, set[str]] = {}
    for name in persona_names:
        persona = registry.get(name)
        if persona is None or not persona.routes_through_gateway:
            continue
        for alias in (persona.model, persona.fallback):
            if alias:
                named_by.setdefault(alias, set()).add(name)
    return named_by


async def check_aliases(
    graph: WorkGraph, registry: Mapping[str, Persona], client: LiteLLMClient
) -> list[PreflightFinding]:
    """Run both preflight checks against a live proxy, returning every finding.

    The two reads are independent: a proxy that answers one endpoint but not
    the other gets a finding for the one it refused and a verdict for the one
    it answered, so the operator is told which is which rather than a single
    "preflight failed". A read failure is recorded with `transport=True` and the
    address tried, never a silent pass (FR-005).

    The caller owns the client and the registry — the CLI builds both from its
    host, the roadmap activity builds both from the worker host — so this
    function touches no environment and reads no files. Returns `[]` when every
    check passes.
    """
    findings: list[PreflightFinding] = []
    try:
        try:
            served = await client.list_model_ids()
        except LiteLLMError as exc:
            findings.append(
                PreflightFinding(
                    check="model-aliases-served",
                    passed=False,
                    transport=True,
                    detail=(
                        f"cannot read the model list from the proxy at "
                        f"{client.base_url}: {exc} — the aliases this epic names "
                        "cannot be confirmed served, so nothing was dispatched"
                    ),
                )
            )
        else:
            unserved = {
                alias: personas
                for alias, personas in aliases_to_check(graph, registry).items()
                if alias not in served
            }
            if unserved:
                _named = ", ".join(
                    f"`{alias}` ({' / '.join(sorted(personas))})"
                    for alias, personas in sorted(unserved.items())
                )
                findings.append(
                    PreflightFinding(
                        check="model-aliases-served",
                        passed=False,
                        detail=(
                            "the proxy does not serve every alias this registry "
                            f"names for the epic's personas: {_named}. Nothing "
                            "was dispatched."
                        ),
                    )
                )

        try:
            live = await client.list_key_aliases()
        except LiteLLMError as exc:
            findings.append(
                PreflightFinding(
                    check="first-attempt-key-aliases",
                    passed=False,
                    transport=True,
                    detail=(
                        f"cannot read the key list from the proxy at "
                        f"{client.base_url}: {exc} — a first-attempt alias "
                        "collision cannot be ruled out, so nothing was dispatched"
                    ),
                )
            )
        else:
            collisions = sorted(first_attempt_aliases(graph) & live)
            if collisions:
                findings.append(
                    PreflightFinding(
                        check="first-attempt-key-aliases",
                        passed=False,
                        detail=(
                            "a live key already holds an alias this epic's first "
                            "attempts will mint: "
                            + ", ".join(f"`{alias}`" for alias in collisions)
                            + ". Revoke that orphaned key (or let its TTL expire) "
                            "so the first attempt can mint it; nothing was "
                            "dispatched."
                        ),
                    )
                )
    finally:
        await client.aclose()

    return findings