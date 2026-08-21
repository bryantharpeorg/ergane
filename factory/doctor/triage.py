"""What the ledger can prove about itself, and what it can only suggest.

`ergane findings triage` sorts every open and regressed finding into exactly one
class (FR-004) so an operator returning to a two-hundred-row ledger can act on
it without reading every row. The whole module is a *read*: it opens no write
transaction, runs no sweep, and the verb that drives it deliberately does not
reuse `factory/cli/doctor.py`'s `_with_store` wrapper, which resolves promoted
findings on the way past (FR-013).

The classes, in the order a finding is offered to them — the order is the
design, because "exactly one class" is only well-defined once precedence is:

1. **fixed** (FR-005) — a `state: landed` spec declares the key under `fixes:`,
   and the finding's `last_seen` is at or before the commit that *first*
   introduced that attestation.
2. **seen after fix** (FR-006) — the same declaration, a later sighting. This is
   the top of the operator's queue, and keeping it out of the closable pile is
   most of why this module exists.
3. **needs a human, undated** (FR-007) — a declaration whose landing commit
   cannot be dated. A spec can say `state: landed` in a working tree with the
   flip uncommitted, and then no commit says so. An undated claim is not a
   proof, and the tempting fallbacks (file mtime, an `# ATTESTED landed …`
   comment, "assume it landed before today") each silently manufacture one.
   Note the asymmetry with the prose scan below: that comment block is read as
   *text a human wrote a key into*, never as a date, and a mention only ever
   makes a candidate — the one class `--apply` may not act on.
4. **fragmented** (FR-009) — two or more keys of three or more segments sharing
   their first two segments *and* one `source`. Decidable from the ledger's own
   keys without reading a single spec, which is why it is offered before the
   prose class: a member count that could be stolen by an unrelated spec's
   prose is not a member count.
5. **candidate** (FR-008) — no `fixes:` declares it, but a landed spec's prose
   names it. Reported separately from the fixed class and naming *every* spec
   whose prose contains it, because naming is not fixing: on the corpus this
   spec was written against, one key was named by six specs — two as their fix,
   one in an out-of-scope list, one as background, and one in a note saying the
   finding is *regressed*. Any rule that read prose as a declaration would have
   closed a live regression.
6. **cold** (FR-010) — older than the threshold and seen exactly once.
7. **needs a human** (FR-011) — everything else.

Two matching rules carry weight beyond their size. Keys are matched **exactly or
on segment boundaries, never as a bare substring**: today no key in the store is
a strict prefix of another, so `key in text` happens to be safe, and the day the
detector's keys shorten to their class it stops being — in a different story,
where nobody would be looking for it. And the fragmentation prefix is defined by
*segment count*, not by splitting on the last slash: most keys in a real store
are exactly `category/slug`, and grouping by everything-before-the-last-slash
would report every category as a fragmented class.

Spec state is read from the operator's **working tree**, which is where every
other spec reader in this repository reads it. That is a known defect class of
its own (`roadmap/dispatch-is-decided-by-the-operators-working-tree`) and fixing
it is out of scope here, so the report says which tree it read instead of
leaving the operator to assume the branch.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path
from typing import Callable, Iterable, Sequence

import yaml

from factory.doctor.models import Finding, Status
from factory.roadmap.models import SPEC_NAME, _split_frontmatter

#: FR-010's default: a finding untouched for a fortnight, seen exactly once.
DEFAULT_COLD_DAYS = 14

#: The state value that makes a spec's `fixes:` a declaration (FR-005), and the
#: string whose introduction dates the landing.
LANDED_STATE = "landed"
_ATTESTATION = f"state: {LANDED_STATE}"

#: Where spec state was read from. Stated in the report because the answer is a
#: known defect class, not a detail (spec Assumptions).
SPEC_STATE_SOURCE = "working tree"

#: How long a `git log` over one spec file may take before it is treated as
#: undated. A hung git is an undated landing, not a hung sweep.
_GIT_TIMEOUT_S = 30

#: The characters that can continue a finding key. A match is segment-bounded
#: when neither the character before nor the character after is one of these —
#: so `ops/leaks-a-key` does not match inside `ops/leaks-a-key/070/us4` or
#: inside `x-ops/leaks-a-key`, but does match when followed by a backtick, a
#: space, or a full stop (FR-009, plan trap 6).
_KEY_CHAR = re.compile(r"[A-Za-z0-9_/-]")

#: FR-009's shape: three or more slash-separated segments, grouped by the first
#: two. Anything shorter is a plain `category/slug` key and forms no group.
_PREFIX_SEGMENTS = 2
_MIN_SEGMENTS = 3

#: A fragmented class needs at least two members; a group of one is not a class
#: (FR-009, plan trap 7 — the control US2-S6 holds this to).
_MIN_MEMBERS = 2


class TriageClass(StrEnum):
    """The classes FR-004 assigns every open and regressed finding to, exactly one."""

    FIXED = "fixed"
    SEEN_AFTER_FIX = "seen-after-fix"
    FRAGMENTED = "fragmented"
    CANDIDATE = "candidate"
    COLD = "cold"
    NEEDS_HUMAN = "needs-human"


#: The order the report prints, and the order a finding is offered the classes
#: in. `NEEDS_HUMAN` is last in both senses: it is the residue (FR-011), and it
#: is also where an undated declaration lands (FR-007).
CLASS_ORDER = (
    TriageClass.FIXED,
    TriageClass.SEEN_AFTER_FIX,
    TriageClass.FRAGMENTED,
    TriageClass.CANDIDATE,
    TriageClass.COLD,
    TriageClass.NEEDS_HUMAN,
)


@dataclass(frozen=True)
class SpecRecord:
    """One spec's state, its declared `fixes:`, and its prose — from one read.

    `state` and `fixes` come from a single parse of one frontmatter block, and
    `prose` is every `.md` in the spec directory — see `_prose` for why the
    block itself is in there too, and why that cannot put one finding in two
    classes.

    Shape is read leniently here and refused elsewhere: `ergane spec validate`
    is what rejects a `fixes:` that is not a list of strings, naming the spec.
    A sweep over a sixty-nine-spec corpus that refused to run at all because one
    spec has a typo would be a report the operator cannot get.
    """

    spec_dir: str
    state: str | None
    fixes: list[str]
    prose: str
    path: str

    @property
    def landed(self) -> bool:
        return self.state == LANDED_STATE


@dataclass(frozen=True)
class TriagedFinding:
    """One finding, its class, and the evidence the operator would re-derive.

    `specs` names the declaring specs for the declared classes (FR-012) and
    every naming spec for the candidate class (FR-008). `landing_date` is the
    date of the commit that first introduced the attestation, so a fixed row can
    be checked without re-running `git log` (FR-012). `reason` is the sentence
    that says why this row is in this class and not another.
    """

    key: str
    triage_class: TriageClass
    reason: str
    specs: list[str] = field(default_factory=list)
    landing_date: str | None = None
    prefix: str | None = None
    members: int = 0


@dataclass(frozen=True)
class FragmentedClass:
    """Two or more rows that are one defect split by key (FR-009).

    `prefix` is the shared first two segments, `keys` the members in sorted
    order, and `members` their count — the surviving class US3's `--apply` folds
    them into.
    """

    prefix: str
    source: str
    keys: list[str]

    @property
    def members(self) -> int:
        return len(self.keys)


@dataclass(frozen=True)
class Triage:
    """The whole classification, and the arithmetic FR-011 requires it to show.

    `total` is the number of open and regressed findings; `classified` is how
    many landed in a class. The two are equal by construction, and the report
    prints both so that the day they are not, the operator sees it rather than a
    silently shortened list.
    """

    specs_root: str
    cold_days: int
    total: int
    findings: list[TriagedFinding]
    fragmented_classes: list[FragmentedClass]

    @property
    def classified(self) -> int:
        return len(self.findings)

    def members(self, triage_class: TriageClass) -> list[TriagedFinding]:
        return [item for item in self.findings if item.triage_class is triage_class]

    def counts(self) -> dict[TriageClass, int]:
        return {name: len(self.members(name)) for name in CLASS_ORDER}


# --- reading the corpus -------------------------------------------------------


def read_spec_records(specs_root: str | Path) -> list[SpecRecord]:
    """Every spec under `specs_root`, each read once and parsed once.

    `state` and `fixes` come from the same `yaml.safe_load` of the same
    frontmatter block, so the two facts FR-005 rests on can never disagree about
    which spec they describe. The prose is gathered in the same pass because
    FR-008 needs it and a second walk of the corpus would be a second chance for
    the two to drift.

    An absent root is an empty corpus, matching `read_roadmap`. A directory with
    no `spec.md` is not a spec the roadmap tracks and is skipped rather than
    rejected.
    """
    root = Path(specs_root)
    if not root.is_dir():
        return []

    records: list[SpecRecord] = []
    for directory in sorted(
        path
        for path in root.iterdir()
        if path.is_dir() and not path.name.startswith(".")
    ):
        spec_path = directory / SPEC_NAME
        spec_text = _read_text(spec_path)
        if spec_text is None:
            continue
        block_text, _body = _split_frontmatter(spec_text)
        state, fixes = _declaration(block_text)
        records.append(
            SpecRecord(
                spec_dir=directory.name,
                state=state,
                fixes=fixes,
                prose=_prose(directory),
                path=str(spec_path),
            )
        )
    return records


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _declaration(block_text: str | None) -> tuple[str | None, list[str]]:
    """`state` and `fixes` out of one frontmatter block, in one parse."""
    if block_text is None:
        return None, []
    try:
        loaded = yaml.safe_load(block_text)
    except yaml.YAMLError:
        return None, []
    if not isinstance(loaded, dict):
        return None, []

    state = loaded.get("state")
    if not isinstance(state, str):
        state = None

    declared = loaded.get("fixes")
    if isinstance(declared, list) and all(isinstance(key, str) for key in declared):
        fixes = list(declared)
    else:
        # Absent reads `[]`, and so does a shape `ergane spec validate` refuses:
        # a malformed declaration is not a declaration, and treating it as one
        # here would close a row on a spec the grammar rejects.
        fixes = []
    return state, fixes


def _prose(directory: Path) -> str:
    """Every `.md` in the spec directory, whole.

    The plan and task documents name findings as often as the spec does, and
    FR-008's question is only whether a *landed spec* writes the key down at
    all. Frontmatter is included for the same reason: on the corpus this spec
    was written against, two landed specs name a finding solely inside the
    `# ATTESTED landed …` comment block their frontmatter carries, and dropping
    those would under-report the naming specs FR-008 requires be listed in full.

    Including the block cannot leak a declaration into the candidate class,
    because the declared classes are offered first: a landed spec's own `fixes:`
    entry is always in the declared index before the prose scan runs, so it can
    never reach here. The one case that does arrive — a `fixes:` of a shape
    `ergane spec validate` refuses — is correctly a candidate: a malformed
    declaration is not a proof, but it is a mention worth a human's eye, and the
    candidate class is the one `--apply` may never act on.
    """
    parts: list[str] = []
    for path in sorted(directory.glob("*.md")):
        text = _read_text(path)
        if text is not None:
            parts.append(text)
    return "\n".join(parts)


# --- dating a landing (FR-005, plan trap 3) -----------------------------------


def git_landing_dates(specs_root: str | Path) -> Callable[[str], datetime | None]:
    """A cached resolver for *when a spec first attested `state: landed`*.

    `git log --reverse` and the first commit, never `git log -1`: the question
    is when this landed, and `-1` answers when `state: landed` was last
    *touched*, which is a different date on any spec whose frontmatter was
    edited after landing.

    Cached per spec directory because the shape of this sweep is one subprocess
    per candidate spec against a few hundred findings — the naive shape runs
    `git log` once per finding.

    Returns `None` for anything it cannot date: a corpus outside a repository, a
    spec whose attestation was never committed, a git that fails or hangs. Every
    one of those is FR-007's needs-a-human, never a guess.
    """
    root = Path(specs_root)
    cache: dict[str, datetime | None] = {}

    def landing_date_for(spec_dir: str) -> datetime | None:
        if spec_dir not in cache:
            cache[spec_dir] = _first_attesting_commit_date(root / spec_dir)
        return cache[spec_dir]

    return landing_date_for


def _git_env() -> dict[str, str]:
    """The same hermetic environment the boundary detector's git reads use."""
    return {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": os.devnull,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
    }


def _first_attesting_commit_date(spec_dir: Path) -> datetime | None:
    if not (spec_dir / SPEC_NAME).is_file():
        return None
    try:
        completed = subprocess.run(
            [
                "git",
                "-C",
                str(spec_dir),
                "log",
                "--reverse",
                "--format=%cI",
                f"-S{_ATTESTATION}",
                "--",
                SPEC_NAME,
            ],
            capture_output=True,
            text=True,
            env=_git_env(),
            check=False,
            timeout=_GIT_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    for line in completed.stdout.splitlines():
        stamp = line.strip()
        if stamp:
            return _parse_timestamp(stamp)
    return None


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment


# --- matching keys (FR-009, plan trap 6) --------------------------------------


def mentions_key(text: str, key: str) -> bool:
    """Whether `text` names `key` exactly or on segment boundaries.

    Never a bare substring test. `ops/leaks-a-key` is a strict prefix of
    `ops/leaks-a-key/070/us4`, and a naive `key in text` reads the second as a
    mention of the first — a defect that is invisible while no key is a prefix
    of another and arrives whole the day one is.
    """
    if not key:
        return False
    start = 0
    while True:
        index = text.find(key, start)
        if index < 0:
            return False
        before = text[index - 1] if index > 0 else ""
        after = text[index + len(key)] if index + len(key) < len(text) else ""
        if not _KEY_CHAR.match(before or " ") and not _KEY_CHAR.match(after or " "):
            return True
        start = index + 1


def _fragmented_groups(findings: Sequence[Finding]) -> list[FragmentedClass]:
    """Group by (first two segments, `source`); a group of one is not a class.

    Segment *count*, not the last slash: `ops/one` and `ops/two` share a
    category and are two ordinary findings, while
    `hardening/agent-worktree-boundary/070/us4` and its sibling are one defect
    the detector split by node.
    """
    groups: dict[tuple[str, str], list[str]] = {}
    for finding in findings:
        segments = finding.key.split("/")
        if len(segments) < _MIN_SEGMENTS:
            continue
        prefix = "/".join(segments[:_PREFIX_SEGMENTS])
        groups.setdefault((prefix, finding.source), []).append(finding.key)

    return [
        FragmentedClass(prefix=prefix, source=source, keys=sorted(keys))
        for (prefix, source), keys in sorted(groups.items())
        if len(keys) >= _MIN_MEMBERS
    ]


# --- the classifier -----------------------------------------------------------


def classify(
    findings: Iterable[Finding],
    records: Sequence[SpecRecord],
    *,
    landing_date_for: Callable[[str], datetime | None],
    now: datetime,
    specs_root: str = "",
    cold_days: int = DEFAULT_COLD_DAYS,
) -> Triage:
    """Sort every open and regressed finding into exactly one class (FR-004).

    Pure over its inputs: the git reads live behind `landing_date_for` and the
    clock behind `now`, so the classification is decidable — and testable —
    without a repository or a wall clock (constitution IV).
    """
    pool = [
        finding
        for finding in findings
        if finding.status in (Status.OPEN, Status.REGRESSED)
    ]
    total = len(pool)
    triaged: list[TriagedFinding] = []

    # 1-3. The declared classes. A declaration is the only thing that closes a
    # row (FR-005), and it is offered first so that no amount of prose or key
    # shape can move a declared finding somewhere `--apply` reads differently.
    declared = _declared_index(records)
    remaining: list[Finding] = []
    for finding in pool:
        specs = declared.get(finding.key)
        if specs:
            triaged.append(_class_declared(finding, specs, landing_date_for))
        else:
            remaining.append(finding)

    # 4. Fragmentation, decidable from the ledger's own keys (FR-009).
    fragmented_classes = _fragmented_groups(remaining)
    class_of_key = {
        key: group for group in fragmented_classes for key in group.keys
    }
    for finding in list(remaining):
        group = class_of_key.get(finding.key)
        if group is None:
            continue
        triaged.append(
            TriagedFinding(
                key=finding.key,
                triage_class=TriageClass.FRAGMENTED,
                reason=(
                    f"one of {group.members} rows under '{group.prefix}' from "
                    f"source '{group.source}' — one defect split by key"
                ),
                prefix=group.prefix,
                members=group.members,
            )
        )
    remaining = [item for item in remaining if item.key not in class_of_key]

    # 5. Prose candidates (FR-008). Named, never closed: naming is not fixing.
    naming = _prose_index(records, [finding.key for finding in remaining])
    still_remaining: list[Finding] = []
    for finding in remaining:
        specs = naming.get(finding.key)
        if not specs:
            still_remaining.append(finding)
            continue
        triaged.append(
            TriagedFinding(
                key=finding.key,
                triage_class=TriageClass.CANDIDATE,
                reason=(
                    "named in the prose of landed "
                    f"{_plural('spec', len(specs))} {_quoted(specs)}, but no "
                    "'fixes:' declares it — prose is not a declaration"
                ),
                specs=specs,
            )
        )

    # 6/7. Cold, then the residue (FR-010, FR-011).
    cutoff = now - timedelta(days=cold_days)
    for finding in still_remaining:
        seen = _parse_timestamp(finding.last_seen)
        if finding.occurrences == 1 and seen is not None and seen < cutoff:
            triaged.append(
                TriagedFinding(
                    key=finding.key,
                    triage_class=TriageClass.COLD,
                    reason=(
                        f"seen once, on {_render_date(seen)}, more than "
                        f"{cold_days} days ago"
                    ),
                )
            )
            continue
        triaged.append(
            TriagedFinding(
                key=finding.key,
                triage_class=TriageClass.NEEDS_HUMAN,
                reason="no landed spec declares or names it, and it is not cold",
            )
        )

    triaged.sort(key=lambda item: (CLASS_ORDER.index(item.triage_class), item.key))
    return Triage(
        specs_root=specs_root,
        cold_days=cold_days,
        total=total,
        findings=triaged,
        fragmented_classes=fragmented_classes,
    )


def _declared_index(records: Sequence[SpecRecord]) -> dict[str, list[str]]:
    """Finding key -> the landed spec dirs that declare it under `fixes:`.

    Landed specs only. A `fixes:` in a draft spec is an intention, and FR-005
    rests on the attestation as much as on the declaration.
    """
    index: dict[str, list[str]] = {}
    for record in records:
        if not record.landed:
            continue
        for key in record.fixes:
            index.setdefault(key, []).append(record.spec_dir)
    return {key: sorted(specs) for key, specs in index.items()}


def _prose_index(
    records: Sequence[SpecRecord], keys: Sequence[str]
) -> dict[str, list[str]]:
    """Finding key -> every landed spec whose prose names it (FR-008)."""
    index: dict[str, list[str]] = {}
    landed = [record for record in records if record.landed]
    for key in keys:
        naming = [
            record.spec_dir for record in landed if mentions_key(record.prose, key)
        ]
        if naming:
            index[key] = sorted(naming)
    return index


def _class_declared(
    finding: Finding,
    specs: Sequence[str],
    landing_date_for: Callable[[str], datetime | None],
) -> TriagedFinding:
    """Split one declared finding into fixed / seen-after-fix / undated.

    A finding several specs declare is fixed when *any* of them proves it: the
    proof is a dated landing no earlier than the last sighting. When every
    declaring spec's landing is undated, or the finding's own `last_seen` cannot
    be read, there is no proof to have and the row goes to a human (FR-007).
    """
    dated = [
        (spec_dir, landed)
        for spec_dir in specs
        for landed in (landing_date_for(spec_dir),)
        if landed is not None
    ]
    seen = _parse_timestamp(finding.last_seen)

    if not dated or seen is None:
        return TriagedFinding(
            key=finding.key,
            triage_class=TriageClass.NEEDS_HUMAN,
            reason=(
                f"declared fixed by {_quoted(specs)}, but no commit dates the "
                "'state: landed' attestation — an undated claim is not a proof"
            ),
            specs=list(specs),
        )

    proving = [(spec_dir, landed) for spec_dir, landed in dated if seen <= landed]
    if proving:
        spec_dir, landed = min(proving, key=lambda pair: pair[1])
        return TriagedFinding(
            key=finding.key,
            triage_class=TriageClass.FIXED,
            reason=(
                f"declared fixed by '{spec_dir}', which landed "
                f"{_render_date(landed)}; last seen {_render_date(seen)}"
            ),
            specs=sorted(spec_dir for spec_dir, _ in proving),
            landing_date=landed.isoformat(),
        )

    spec_dir, landed = max(dated, key=lambda pair: pair[1])
    return TriagedFinding(
        key=finding.key,
        triage_class=TriageClass.SEEN_AFTER_FIX,
        reason=(
            f"declared fixed by '{spec_dir}', which landed "
            f"{_render_date(landed)} — but it was seen again on "
            f"{_render_date(seen)}"
        ),
        specs=sorted(spec_dir for spec_dir, _ in dated),
        landing_date=landed.isoformat(),
    )


# --- rendering ----------------------------------------------------------------


def to_document(triage: Triage) -> dict:
    """The `--json` document: the same classification, machine-readable."""
    return {
        "specs_root": triage.specs_root,
        "spec_state_source": SPEC_STATE_SOURCE,
        "cold_days": triage.cold_days,
        "total": triage.total,
        "classified": triage.classified,
        "counts": {name.value: count for name, count in triage.counts().items()},
        "classes": {
            name.value: [
                {
                    "key": item.key,
                    "reason": item.reason,
                    "specs": item.specs,
                    "landing_date": item.landing_date,
                    "prefix": item.prefix,
                    "members": item.members,
                }
                for item in triage.members(name)
            ]
            for name in CLASS_ORDER
        },
        "fragmented_classes": [
            {
                "prefix": group.prefix,
                "source": group.source,
                "members": group.members,
                "keys": group.keys,
            }
            for group in triage.fragmented_classes
        ],
    }


def render(triage: Triage) -> str:
    """The human report: per-class counts and members, and the sum check.

    The header names the tree spec state was read from, because the answer is a
    known defect class rather than a detail, and the footer prints the
    arithmetic FR-011 asks for rather than asserting it.
    """
    lines = [
        f"ergane findings triage — {triage.total} open and regressed "
        f"{_plural('finding', triage.total)}",
        f"spec state read from the {SPEC_STATE_SOURCE} at {triage.specs_root}",
        f"cold threshold: {triage.cold_days} days",
    ]

    for name in CLASS_ORDER:
        members = triage.members(name)
        lines.append("")
        lines.append(f"{name.value} ({len(members)})")
        if not members:
            lines.append("  (none)")
            continue
        for item in members:
            lines.append(f"  {item.key}")
            lines.append(f"    {item.reason}")

    if triage.fragmented_classes:
        lines.append("")
        lines.append(
            f"fragmented classes ({len(triage.fragmented_classes)}) — the "
            "surviving key of each fold"
        )
        for group in triage.fragmented_classes:
            lines.append(
                f"  {group.prefix} ({group.members} members, "
                f"source '{group.source}')"
            )

    lines.append("")
    lines.append(
        f"{triage.classified} classified = {triage.total} open and regressed"
    )
    return "\n".join(lines)


# --- helpers ------------------------------------------------------------------


def _render_date(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%d")


def _plural(noun: str, count: int) -> str:
    return noun if count == 1 else f"{noun}s"


def _quoted(values: Sequence[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)
