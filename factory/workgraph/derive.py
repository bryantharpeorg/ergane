"""The compiler: an epic spec's `## Work Graph` section in, a `WorkGraph` out.

A node this emits is a worktree, a virtual key, an agent attempt and a branch,
so a declaration misread here is all of those pointed at the wrong story. Two
properties keep that honest.

**It is pure** — text in, `WorkGraph` out, no filesystem and no registry (FR-011,
R7). The CLI has already read the spec; derivation never opens it again, which
is what makes `workgraph.json` a *compiled* artifact rather than a snapshot of
whatever the disk said at derive time. It is also why persona timeouts are not
resolved here (R8): baking a registry value into the artifact would make it
stale the moment an operator edits `personas.yaml`, so the node carries only the
author's explicit override and resolution happens at dispatch.

**It refuses by name, and emits nothing** (SC-006). The audience is an author who
has to go edit one line of one spec, so every rejection carries the offending
story and the rule slug from contracts/workgraph-schema.md § Shape rules — not
prose a caller has to grep. Rejections are *collected* rather than raised at the
first, because `factory-epic derive` prints them all at once and an author
fixing one typo per run, with the next revealed only after the fix, is the
failure mode collection exists to avoid.

Collection is staged, and the staging is the part worth reading. A defect
upstream makes every check downstream of it meaningless — a declaration that is
not a mapping has no `depends_on` to type-check, a story the spec never declared
has no edges worth resolving, and a self-dependency *is* a cycle, so reporting
both would send the author to two lines to fix one. So: the section and its YAML
must parse before anything is shaped, each declaration is shaped before it is
cross-validated, and the acyclic check runs only against a graph that survived
everything before it. Each defect yields exactly one rejection.

Cross-validation reads the spec with `factory.verify.criteria.parse_spec` — the
same parser `load_criteria` wraps, minus its file read. Sharing it is what makes
"a story the deriver accepts is a story `snapshot_criteria` will later resolve"
true by construction rather than by agreement between two readers of the same
markdown.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterator, Mapping, Sequence

import yaml

from factory.verify.criteria import (
    CriteriaParseError,
    HEADER_RE,
    mask_fences,
    parse_spec,
    section_end,
)
from factory.verify.models import RequirementKind
from factory.workgraph.models import (
    WorkGraph,
    WorkGraphDeclaration,
    WorkNode,
    find_cycle,
)

#: The section that declares the graph. A level-2 header, found with the
#: fence-masked scan the criteria parser uses: a `## Work Graph` quoted inside a
#: fenced block is prose *about* a work graph, and deriving an epic from it would
#: dispatch the example.
SECTION_HEADING = "Work Graph"
_SECTION_LEVEL = 2

#: A top-level key in the block. The criteria parser mints story keys as `US<n>`,
#: so anything else cannot name a story it found, whatever it looks like.
_STORY_ID_RE = re.compile(r"^US\d+$")

#: Every key a declaration may carry. `persona` and friends are post-bootstrap
#: grammar and are refused rather than ignored — silently dropping a key an
#: author wrote is how a spec comes to mean something other than it says.
_REQUIRED_KEYS = ("depends_on", "implements")
#: Optional keys. `depends_on_merged` (FR-009) is optional the way `timeout` is —
#: a declaration without it stays valid, unlike omitting a required edge.
_OPTIONAL_KEYS = ("timeout", "depends_on_merged")

#: The persona every derived node names in the minimal interpreter
#: (contracts/workgraph-schema.md § Derivation semantics).
IMPLEMENTER = "implementer"


@dataclass(frozen=True)
class Rejection:
    """One refused declaration: which story, which rule, and what is wrong.

    `rule` is the slug from the contract's shape-rule table and `story` the
    offending story key (`None` for the rules that are about the section as a
    whole, which no story owns). Both are structured rather than embedded in
    prose so the CLI can group them and tests can assert on them without
    matching sentences.
    """

    rule: str
    story: str | None
    problem: str

    def __str__(self) -> str:
        where = f"{self.story}: " if self.story else ""
        return f"{where}[{self.rule}] {self.problem}"


class DerivationError(ValueError):
    """A spec that does not compile, and every reason why (SC-006).

    Carries the whole list: emitting the well-formed nodes of a broken spec
    would be the worst outcome available — an epic that starts, dispatches the
    stories that parsed, and silently never builds the one that did not.
    """

    def __init__(self, rejections: Sequence[Rejection]) -> None:
        self.rejections = list(rejections)
        count = len(self.rejections)
        noun = "declaration" if count == 1 else "declarations"
        detail = "\n".join(f"  - {rejection}" for rejection in self.rejections)
        super().__init__(
            f"the `## {SECTION_HEADING}` section does not compile "
            f"({count} {noun} rejected):\n{detail}"
        )


@dataclass
class _Rejections:
    """The collector, and the staging discipline it exists to make readable."""

    collected: list[Rejection] = field(default_factory=list)

    def add(self, rule: str, story: str | None, problem: str) -> None:
        self.collected.append(Rejection(rule=rule, story=story, problem=problem))

    def raise_if_any(self) -> None:
        if self.collected:
            raise DerivationError(self.collected)


def derive_workgraph(
    spec_text: str,
    *,
    epic_id: str,
    feature: str,
    specs_root: str,
    target_repo: str,
) -> WorkGraph:
    """Compile one epic spec into the graph the interpreter runs (FR-011, R7).

    The four identity fields are the caller's — the deriver is handed text, not
    a path, so it does not know which directory the spec came from and must not
    guess. Everything else is read out of the spec: one node per story in spec
    order, ids lowercased, `requirement_keys` = `[story_key, *implements]`.

    Raises `DerivationError` carrying every rejection; nothing is emitted.
    """
    stories = _spec_stories(spec_text)
    declarations = _declarations(spec_text)
    _cross_validate(declarations, stories)

    return WorkGraph(
        epic_id=epic_id,
        feature=feature,
        specs_root=specs_root,
        target_repo=target_repo,
        nodes=[
            _node(declarations[key], story_key=key, feature=feature)
            for key in stories
        ],
    )


def _node(
    declaration: WorkGraphDeclaration, *, story_key: str, feature: str
) -> WorkNode:
    """One story, compiled (contracts/workgraph-schema.md § Derivation semantics).

    Every field here is load-bearing downstream: `id` names the branch, the
    worktree and the transcript directory; `requirement_keys` is the filter
    `snapshot_criteria` is later handed verbatim, story key first because that is
    the requirement the node is *for*; `spec_ref` is component 1's attribution
    string.
    """
    return WorkNode(
        id=story_key.lower(),
        story_key=story_key,
        persona=IMPLEMENTER,
        spec_ref=f"{feature}:{story_key}",
        requirement_keys=[story_key, *declaration.implements],
        depends_on=[dependency.lower() for dependency in declaration.depends_on],
        depends_on_merged=[
            dependency.lower() for dependency in declaration.depends_on_merged
        ],
        timeout_override_s=declaration.timeout,
    )


# --- the spec side: what the criteria parser found -----------------------------


def _spec_stories(spec_text: str) -> dict[str, list[str]]:
    """The spec's stories in file order, mapped to the FR keys it declares.

    Read with the criteria parser rather than a second scan of the same markdown:
    the deriver and the verifier must agree about what a story is, and the only
    way to guarantee that is for one of them to ask the other.
    """
    try:
        requirements = parse_spec(spec_text)
    except CriteriaParseError as error:
        raise DerivationError(
            [
                Rejection(
                    rule="spec",
                    story=error.offender,
                    problem=(
                        f"the spec itself does not parse ({error}), so there is "
                        "no story list to compile a graph against"
                    ),
                )
            ]
        ) from error

    functional = [
        requirement.key
        for requirement in requirements
        if requirement.kind is RequirementKind.FUNCTIONAL
    ]
    return {
        requirement.key: functional
        for requirement in requirements
        if requirement.kind is RequirementKind.STORY
    }


# --- the block side: section, YAML, shape --------------------------------------


def _declarations(spec_text: str) -> dict[str, WorkGraphDeclaration]:
    """Parse the section's one fenced block into per-story declarations.

    Raises before any cross-validation: a block that is not a mapping of
    declarations has nothing for the later rules to be about.
    """
    block = _work_graph_block(spec_text)
    rejections = _Rejections()

    declarations: dict[str, WorkGraphDeclaration] = {}
    for story_id, body in block.items():
        declaration = _declaration(story_id, body, rejections)
        if declaration is not None:
            declarations[declaration.story_id] = declaration

    rejections.raise_if_any()
    return declarations


def _work_graph_block(spec_text: str) -> Mapping[str, Any]:
    """The section's single fenced YAML block, loaded as a mapping.

    Exactly one section holding exactly one block: a section with two blocks is
    refused rather than resolved in the author's favour, because a deriver that
    silently took the first could not be told from a correct one by its output —
    only by the rule (tests/fixtures/README.md, `two_blocks`).
    """
    lines = spec_text.splitlines()
    in_code = mask_fences(lines)

    sections = list(_sections(lines, in_code))
    if len(sections) != 1:
        found = "no" if not sections else f"{len(sections)}"
        raise DerivationError(
            [
                Rejection(
                    rule="section_missing",
                    story=None,
                    problem=(
                        f"the spec must declare exactly one `## {SECTION_HEADING}` "
                        f"section; found {found}"
                    ),
                )
            ]
        )

    start, end = sections[0]
    blocks = list(_fenced_blocks(lines, in_code, start, end))
    if len(blocks) != 1:
        found = "none" if not blocks else f"{len(blocks)}"
        raise DerivationError(
            [
                Rejection(
                    rule="section_missing",
                    story=None,
                    problem=(
                        f"the `## {SECTION_HEADING}` section must hold exactly one "
                        f"fenced YAML block declaring the graph; found {found}"
                    ),
                )
            ]
        )

    try:
        loaded = yaml.safe_load("\n".join(blocks[0]))
    except yaml.YAMLError as error:
        raise DerivationError(
            [
                Rejection(
                    rule="mapping",
                    story=None,
                    problem=(
                        "the block must be a mapping of story id → declaration, "
                        f"and it is not valid YAML: {error}"
                    ),
                )
            ]
        ) from error

    if not isinstance(loaded, dict):
        raise DerivationError(
            [
                Rejection(
                    rule="mapping",
                    story=None,
                    problem=(
                        "the block must be a mapping of story id → declaration "
                        f"mapping, got {type(loaded).__name__}"
                    ),
                )
            ]
        )
    return loaded


def _sections(
    lines: Sequence[str], in_code: Sequence[bool]
) -> Iterator[tuple[int, int]]:
    """Half-open spans of every `## Work Graph` section body, fence-masked."""
    for index, line in enumerate(lines):
        if in_code[index]:
            continue
        header = HEADER_RE.match(line)
        if header is None:
            continue
        if len(header.group(1)) != _SECTION_LEVEL:
            continue
        if header.group(2).strip() != SECTION_HEADING:
            continue
        yield index + 1, section_end(lines, in_code, index, level=_SECTION_LEVEL)


def _fenced_blocks(
    lines: Sequence[str], in_code: Sequence[bool], start: int, end: int
) -> Iterator[list[str]]:
    """The content of each fenced block in `[start, end)`, delimiters dropped.

    A block is a run of masked lines, which the criteria parser's mask already
    computed — including the nesting rule that keeps a ```` ``` ```` quoted inside
    a longer fence inert. Prose between blocks is unmasked, so the runs are the
    blocks.
    """
    index = start
    while index < end:
        if not in_code[index]:
            index += 1
            continue
        run = index
        while run < end and in_code[run]:
            run += 1
        # The first and last lines of the run are the fences themselves; an
        # unclosed fence masks to end of file, so the trailing slice is empty
        # rather than wrong.
        yield list(lines[index + 1 : max(index + 1, run - 1)])
        index = run


def _declaration(
    story_id: Any, body: Any, rejections: _Rejections
) -> WorkGraphDeclaration | None:
    """Shape one declaration, or record why it has none (and compile nothing).

    Shape errors stop this declaration from being cross-validated at all: a
    `depends_on` that is a scalar has no edges to resolve, and reporting both
    "not a list" and "names no declared story" for one typo would send the author
    to two lines to fix one.
    """
    key = str(story_id)
    if not isinstance(body, dict):
        rejections.add(
            "mapping",
            key,
            f"declaration must be a mapping of {', '.join(_REQUIRED_KEYS)} "
            f"(and optionally {', '.join(_OPTIONAL_KEYS)}), got "
            f"{type(body).__name__}",
        )
        return None

    unknown = [name for name in body if name not in (*_REQUIRED_KEYS, *_OPTIONAL_KEYS)]
    if unknown:
        rejections.add(
            "unknown_key",
            key,
            f"declaration carries unknown key(s) {_quoted(unknown)}; the grammar "
            f"is {_quoted([*_REQUIRED_KEYS, *_OPTIONAL_KEYS])}",
        )
        return None

    lists: dict[str, list[str]] = {}
    for name in _REQUIRED_KEYS:
        if name not in body:
            rejections.add(
                name,
                key,
                f"declaration omits required key '{name}'; it is a list (which may "
                "be empty), never an implied one — an unhooked edge is invisible "
                "in the compiled graph",
            )
            continue
        value = body[name]
        if not isinstance(value, list) or not all(
            isinstance(item, str) for item in value
        ):
            rejections.add(
                name,
                key,
                f"'{name}' must be a list of ids, got {value!r}",
            )
            continue
        lists[name] = list(value)

    timeout = body.get("timeout")
    if timeout is not None and (
        isinstance(timeout, bool) or not isinstance(timeout, int) or timeout <= 0
    ):
        rejections.add(
            "timeout",
            key,
            f"'timeout' must be a positive integer of seconds, got {timeout!r}",
        )
        return None

    if len(lists) != len(_REQUIRED_KEYS):
        return None

    merged = body.get("depends_on_merged", [])
    if not isinstance(merged, list) or not all(isinstance(item, str) for item in merged):
        rejections.add(
            "depends_on_merged",
            key,
            f"'depends_on_merged' must be a list of ids, got {merged!r}",
        )
        return None

    return WorkGraphDeclaration(
        story_id=key,
        depends_on=lists["depends_on"],
        implements=lists["implements"],
        timeout=timeout,
        depends_on_merged=list(merged),
    )


# --- cross-validation: the block against the spec ------------------------------


def _cross_validate(
    declarations: Mapping[str, WorkGraphDeclaration], stories: Mapping[str, list[str]]
) -> None:
    """Every rule that needs both sides: coverage, ids, edges, FR keys, cycles.

    The acyclic check is last and conditional. A self-dependency is a cycle and a
    dangling edge is a hole in the relation, so running it over a graph that
    already failed here would report the same defect twice and, for a dangling
    edge, report a cycle that does not exist.
    """
    rejections = _Rejections()

    for story_id in declarations:
        if not _STORY_ID_RE.match(story_id) or story_id not in stories:
            rejections.add(
                "story_id",
                story_id,
                "declares a graph node for a story this spec does not declare",
            )

    for story_key in stories:
        if story_key not in declarations:
            rejections.add(
                "coverage",
                story_key,
                "the spec declares this story and the `## "
                f"{SECTION_HEADING}` section does not — every story is a node, and "
                "an undeclared one would be a silent orphan",
            )

    for story_key, declaration in declarations.items():
        if story_key not in stories:
            continue
        _check_edges(declaration, declarations, rejections)
        _check_implements(declaration, stories[story_key], rejections)

    rejections.raise_if_any()

    # FR-009: an edge gates on either verification or merge, never both. This is
    # checked after the individual edge rules so a story that is already broken
    # is not reported twice for the same overlap.
    for declaration in declarations.values():
        overlap = set(declaration.depends_on) & set(declaration.depends_on_merged)
        if overlap:
            rejections.add(
                "depends_on_merged",
                declaration.story_id,
                f"lists {_quoted(sorted(overlap))} in both `depends_on` and "
                "`depends_on_merged` — an edge gates on either verification or "
                "merge, never both (FR-009)",
            )
    rejections.raise_if_any()

    cycle = find_cycle(
        {
            story_id: [*declaration.depends_on, *declaration.depends_on_merged]
            for story_id, declaration in declarations.items()
        }
    )
    if cycle is not None:
        rejections.add(
            "acyclic",
            cycle[0],
            "these stories wait on each other and none can ever start: "
            + " → ".join(cycle),
        )
    rejections.raise_if_any()


def _check_edges(
    declaration: WorkGraphDeclaration,
    declarations: Mapping[str, WorkGraphDeclaration],
    rejections: _Rejections,
) -> None:
    """Both edge sets name declared stories, and never the story itself.

    `depends_on` unlocks on verification, `depends_on_merged` (FR-009) on merge —
    but each is a dependency edge, so each gets the same two rules. A self-edge in
    either set is a cycle of one; an edge to an undeclared story can never unlock.
    """
    if declaration.story_id in declaration.depends_on:
        rejections.add(
            "depends_on",
            declaration.story_id,
            "depends on itself, so it could never be dispatched",
        )
        return

    unknown = [
        dependency
        for dependency in declaration.depends_on
        if dependency not in declarations
    ]
    if unknown:
        rejections.add(
            "depends_on",
            declaration.story_id,
            f"depends on {_quoted(unknown)}, which no declaration names",
        )

    if declaration.story_id in declaration.depends_on_merged:
        rejections.add(
            "depends_on_merged",
            declaration.story_id,
            "depends on the merge of itself, so it could never be dispatched",
        )
        return

    unknown_merged = [
        dependency
        for dependency in declaration.depends_on_merged
        if dependency not in declarations
    ]
    if unknown_merged:
        rejections.add(
            "depends_on_merged",
            declaration.story_id,
            f"depends on the merge of {_quoted(unknown_merged)}, which no "
            "declaration names",
        )


def _check_implements(
    declaration: WorkGraphDeclaration,
    functional_keys: Sequence[str],
    rejections: _Rejections,
) -> None:
    """`implements` names FR keys this spec declares.

    An unknown key would travel into `requirement_keys` and reach
    `snapshot_criteria`, which refuses a key the spec does not declare — the same
    rejection, one dispatch later and with a virtual key already spent.
    """
    unknown = [key for key in declaration.implements if key not in functional_keys]
    if unknown:
        rejections.add(
            "implements",
            declaration.story_id,
            f"implements {_quoted(unknown)}, which this spec does not declare",
        )


def _quoted(values: Sequence[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)
