"""Landed facts and pinned fingerprints: the reader side of delta derivation.

Two pure functions over a target clone:

- `landed_facts(repo, spec_dir, default_branch)` scans the default branch's
  history once, anchors attributions to this spec's `epic_id` (the `spec_dir`
  itself), and returns every story's current landing commit. A story with no
  reachable attributed commit falls back to the spec's attesting commit when
  the frontmatter says `state: landed` — per story, not per spec (FR-002).

- `fingerprint(repo, rev, spec_dir, story_key)` reads the spec at an exact
  revision via `git show rev:specs/<dir>/spec.md`, parses its criteria and work
  graph, and returns a structural hash of the story's judgeable content. The
  working tree never leaks in (FR-003).

Both delegate git invocations to `factory/workgraph/worktree.py`, whose
`_git` helper and `WorktreeError` naming are the template. The reader takes
a repo path and never touches a global git directory.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Mapping, Sequence

import yaml

from factory.verify.criteria import HEADER_RE, mask_fences, parse_spec, section_end
from factory.verify.models import RequirementKind
from factory.workgraph.worktree import WorktreeError, _git, _has_remote

#: The landing attribution grammar: `<epic_id>/<node_id>: <STORY_KEY> (#<pr>)`.
#: Rendered by `factory.mergequeue.messages.pr_title`; GitHub appends `(#<pr>)`.
#: The reader anchors on the epic id so commits from other epics do not leak in.
_LANDING_RE = re.compile(
    r"^(?P<epic_id>[^/\s]+)/(?P<node_id>[^:\s]+):\s*(?P<story_key>US\d+)\s*(?:\(#\d+\))?\s*$"
)

#: How `git log` separates hash from subject.
_LOG_SEP = "\t"


class LandedKind(StrEnum):
    """Whether a landing commit is observed by grammar or supplied by attestation."""

    OBSERVED = "observed"
    ATTESTED = "attested"


@dataclass(frozen=True)
class LandedFact:
    """One story's current landing: key, commit, provenance kind."""

    story_key: str
    commit: str
    kind: LandedKind


@dataclass(frozen=True)
class Fingerprint:
    """A story's judgeable content pinned at a revision.

    `digest` is a structural hash: sorted, whitespace-normalized text of the
    story's scenarios, the FR bodies it implements, and its work-graph
    declaration. A reflowed paragraph changes nothing; a changed criterion,
    FR body, or declaration changes it.
    """

    story_key: str
    revision: str
    digest: str


# --- landed facts ------------------------------------------------------------


def landed_facts(
    repo: str | Path,
    spec_dir: str,
    *,
    default_branch: str,
) -> dict[str, LandedFact]:
    """Per-story landed facts for one spec, newest attributed landing wins.

    The scan is one `git log` pass over the default branch. Non-matching subjects
    are silently ignored — the grammar is the contract. Attestation is the
    fallback and is applied per story: any story with no reachable attributed
    commit, in a spec whose frontmatter is attested `state: landed`, baselines at
    the commit that introduced the attestation with `kind=ATTESTED`.
    """
    repo_path = Path(repo)
    epic_id = spec_dir

    # Ensure we read the freshest reachable default-branch head.
    head = _resolve_default_head(repo_path, default_branch)

    # One batch scan over the default branch's history, newest first.
    observed: dict[str, LandedFact] = {}
    for commit, subject in _git_log_subjects(repo_path, head):
        match = _LANDING_RE.match(subject)
        if match is None or match.group("epic_id") != epic_id:
            continue
        story_key = match.group("story_key")
        if story_key not in observed:
            observed[story_key] = LandedFact(
                story_key=story_key,
                commit=commit,
                kind=LandedKind.OBSERVED,
            )

    # Attestation fallback is per story, not per spec: gap-fill only stories that
    # did not have a reachable attributed commit. The attesting commit is the one
    # that introduced the frontmatter `state: landed`.
    frontmatter = _frontmatter_at(repo_path, head, spec_dir)
    if frontmatter.get("state") == "landed":
        attesting = _attesting_commit(repo_path, head, spec_dir)
        if attesting is not None:
            requirements = _spec_requirements_at(repo_path, head, spec_dir)
            for story_key in _story_keys(requirements):
                if story_key not in observed:
                    observed[story_key] = LandedFact(
                        story_key=story_key,
                        commit=attesting,
                        kind=LandedKind.ATTESTED,
                    )

    return observed


def _resolve_default_head(repo: Path, default_branch: str) -> str:
    """The current default-branch head, fetched if a remote exists.

    Mirrors `capture_base_ref`: a clone's own HEAD is stale exactly when a
    landing just happened, so resolve against `origin/<default_branch>` after a
    fetch, falling back to local HEAD only for remote-less repos.
    """
    if _has_remote(repo, "origin"):
        _git(repo, "fetch", "--quiet", "origin")
        ref = f"origin/{default_branch}"
    else:
        ref = default_branch
    try:
        return _git(repo, "rev-parse", ref).strip()
    except WorktreeError as exc:
        raise WorktreeError(
            f"cannot resolve default branch '{default_branch}' in {repo}: {exc}"
        ) from exc


def _git_log_subjects(repo: Path, head: str) -> list[tuple[str, str]]:
    """All commits reachable from `head`, each as (sha, subject)."""
    output = _git(
        repo,
        "log",
        "--format=%H" + _LOG_SEP + "%s",
        head,
        "--",
    )
    results: list[tuple[str, str]] = []
    for line in output.splitlines():
        if not line:
            continue
        commit, sep, subject = line.partition(_LOG_SEP)
        if sep != _LOG_SEP:
            continue
        results.append((commit, subject))
    return results


def _frontmatter_at(repo: Path, rev: str, spec_dir: str) -> dict:
    """The parsed YAML frontmatter of the spec at `rev`, or {} if absent."""
    text = _spec_text_at(repo, rev, spec_dir, missing_ok=True)
    if text is None:
        return {}
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            yaml_text = "\n".join(lines[1:index])
            try:
                loaded = yaml.safe_load(yaml_text)
            except yaml.YAMLError:
                return {}
            if isinstance(loaded, dict):
                return loaded
            return {}
    return {}


def _attesting_commit(repo: Path, head: str, spec_dir: str) -> str | None:
    """The commit that introduced the spec's `state: landed` attestation.

    The attesting commit is the one whose own spec file first carries the
    attestation and whose parent (if any) does not. Walking history newest-first
    would return the most recent commit whose file still says `landed`, which is
    wrong: any later edit that preserves `state: landed` is not a new attestation.
    Returns None if no commit introduces the attestation.
    """
    for commit, _subject in _git_log_subjects(repo, head):
        frontmatter = _frontmatter_at(repo, commit, spec_dir)
        if frontmatter.get("state") != "landed":
            continue
        try:
            parent = _git(repo, "rev-parse", f"{commit}^").strip()
        except WorktreeError:
            # Root commit: it is the introduction if it attests.
            return commit
        parent_frontmatter = _frontmatter_at(repo, parent, spec_dir)
        if parent_frontmatter.get("state") != "landed":
            return commit
    return None


def _spec_requirements_at(repo: Path, rev: str, spec_dir: str) -> list:
    """`parse_spec` over the spec file at `rev`."""
    text = _spec_text_at(repo, rev, spec_dir, missing_ok=False)
    if text is None:
        return []
    try:
        return parse_spec(text)
    except Exception:
        return []


def _story_keys(requirements: Sequence) -> list[str]:
    """Story requirement keys in file order."""
    return [
        requirement.key
        for requirement in requirements
        if getattr(requirement, "kind", None) is RequirementKind.STORY
    ]


# --- fingerprints ------------------------------------------------------------


def fingerprint(
    repo: str | Path,
    rev: str,
    spec_dir: str,
    story_key: str,
) -> Fingerprint:
    """Structural fingerprint of one story at an exact revision.

    Reads `git show <rev>:specs/<dir>/spec.md`. The result is pure against that
    revision's content; any working-tree edit is invisible. Raises
    `WorktreeError` with a named finding if the spec file is absent at the
    revision.
    """
    repo_path = Path(repo)
    text = _spec_text_at(repo_path, rev, spec_dir, missing_ok=False)
    if text is None:
        raise WorktreeError(
            f"fingerprint refused: specs/{spec_dir}/spec.md does not exist at {rev}"
        )

    scenarios, fr_bodies, declaration = _story_parts(text, story_key)
    digest = _structural_digest(
        {
            "story_key": story_key,
            "scenarios": scenarios,
            "fr_bodies": fr_bodies,
            "declaration": declaration,
        }
    )
    return Fingerprint(story_key=story_key, revision=rev, digest=digest)


def _story_parts(
    spec_text: str, story_key: str
) -> tuple[list[str], dict[str, str], str | None]:
    """The three fingerprint components for a story.

    Returns (scenario raw texts, FR-key -> body, declaration YAML text).
    """
    requirements = parse_spec(spec_text)
    story = None
    functional: dict[str, str] = {}
    for requirement in requirements:
        if requirement.kind is RequirementKind.FUNCTIONAL:
            functional[requirement.key] = _normalize(requirement.body)
        if requirement.key == story_key:
            story = requirement

    scenarios: list[str] = []
    if story is not None:
        scenarios = [_normalize(scenario.raw_text) for scenario in story.scenarios]

    declaration = _declaration_text(spec_text, story_key)

    implements: list[str] = []
    if declaration is not None:
        block = _work_graph_block(spec_text)
        if isinstance(block, dict):
            body = block.get(story_key)
            if isinstance(body, dict):
                implements = body.get("implements", [])

    implemented_bodies = {
        key: body for key, body in functional.items() if key in implements
    }
    return scenarios, implemented_bodies, declaration


def _declaration_text(spec_text: str, story_key: str) -> str | None:
    """The raw YAML text of one story's work-graph declaration, if present."""
    try:
        block = _work_graph_block(spec_text)
    except Exception:
        return None
    if not isinstance(block, dict):
        return None
    body = block.get(story_key)
    if body is None:
        return None
    try:
        return yaml.safe_dump({story_key: body}, sort_keys=True, default_flow_style=False)
    except yaml.YAMLError:
        return str(body)


def _work_graph_block(spec_text: str) -> dict | None:
    """The parsed YAML mapping inside the `## Work Graph` section."""
    lines = spec_text.splitlines()
    in_code = mask_fences(lines)
    for index, line in enumerate(lines):
        if in_code[index]:
            continue
        header = HEADER_RE.match(line)
        if header is None or len(header.group(1)) != 2:
            continue
        if header.group(2).strip() != "Work Graph":
            continue
        end = section_end(lines, in_code, index, level=2)
        blocks = list(_fenced_blocks(lines, in_code, index + 1, end))
        if len(blocks) != 1:
            return None
        try:
            loaded = yaml.safe_load("\n".join(blocks[0]))
        except yaml.YAMLError:
            return None
        if isinstance(loaded, dict):
            return loaded
        return None
    return None


def _fenced_blocks(
    lines: Sequence[str], in_code: Sequence[bool], start: int, end: int
) -> list[list[str]]:
    """Fence-masked block runs, identical to the criteria/derive scanners."""
    blocks: list[list[str]] = []
    index = start
    while index < end:
        if not in_code[index]:
            index += 1
            continue
        run = index
        while run < end and in_code[run]:
            run += 1
        blocks.append(list(lines[index + 1 : max(index + 1, run - 1)]))
        index = run
    return blocks


def _structural_digest(payload: dict) -> str:
    """A stable, whitespace-tolerant hash of the fingerprint components."""
    text = _normalize(_serialize(payload))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _serialize(value: object) -> str:
    """JSON-ish canonical text: lists and dicts rendered deterministically."""
    if isinstance(value, dict):
        items = sorted(value.items())
        return "{" + ", ".join(f"{_serialize(k)}: {_serialize(v)}" for k, v in items) + "}"
    if isinstance(value, list):
        return "[" + ", ".join(_serialize(v) for v in value) + "]"
    if isinstance(value, str):
        return value
    return str(value)


def _normalize(text: str) -> str:
    """Collapse whitespace without changing the words or their order."""
    return " ".join(text.split())


# --- git helpers -------------------------------------------------------------


def _spec_text_at(repo: Path, rev: str, spec_dir: str, *, missing_ok: bool) -> str | None:
    """The spec file's text at `rev`, or None if missing and `missing_ok`."""
    path = f"specs/{spec_dir}/spec.md"
    try:
        return _git(repo, "show", f"{rev}:{path}")
    except WorktreeError as exc:
        if missing_ok and "does not exist" in str(exc):
            return None
        # If the commit itself is unreachable, re-raise with the original detail.
        raise
