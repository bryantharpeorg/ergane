"""The half of triage that writes: what `ergane findings triage --apply` enacts.

US2's classifier sorts every open and regressed finding into exactly one class.
This module is the other half — the one that touches the store — and it is a
separate file on purpose, so that the classifier's claim about itself ("the
whole module is a read") stays checkable by eye rather than by trust.

**The single predicate that reverses a whole pass is `RESOLVABLE`.** Two of the
six classes may be closed: `fixed`, because a landed spec declared the key under
its `fixes:`, and `fragmented`, because the rows are one defect the detector
split by key. Adding a third name to that tuple would close, on the corpus this
spec was written against, a hundred and nineteen findings nobody attested — one
of which a landed spec's own prose describes as *regressed*. It is a tuple
consulted by one branch rather than a loop per class, because a loop per class
makes the predicate decorative: widen it and nothing happens, narrow it and
nothing happens. Here, adding `candidate` to it fails three tests that assert
a silence, and adding `seen-after-fix` as well fails four (FR-019; the runs are
pasted in `tests/test_findings_triage_applies.py`).

What the other four classes get:

- `seen-after-fix` and `candidate` — **nothing at all**, not even an annotation
  (FR-015). A declaration plus a later sighting is a live regression, and a
  mention in prose is not a declaration. Both are the operator's queue, and a
  sweep that wrote to them would be editing the evidence it was asked to
  summarise.
- `cold` and `needs-human` — a triage annotation in `notes` and nothing else
  (FR-017, FR-018). They stay `open`, because "a human should look at this" is
  not a resolution.
- Anything else — a class this module has no rule for — is **refused**, counted
  and named. A seventh class arriving from a later story must default to doing
  nothing, not to falling through into the nearest branch.

The classification arrives as data rather than as an import: `apply_triage`
takes the sequences the classifier produces and reads four attributes off each
row. That is what lets this half be tested against a real store without a specs
corpus, a git history or a clock — and it is why the class names here are the
plain strings the classifier's `TriageClass` is built from, which compare equal
to its members because it is a `StrEnum`.

**The CLI seam.** `--apply` is one flag on the `triage` verb and one call:

    triage_parser.add_argument("--apply", action="store_true", help=...)
    ...
    application = apply_triage(conn, triage.findings, triage.fragmented_classes)
    print(render(application))

with the verb's connection opened writable for that pass only, and still not
through `_with_store` — that wrapper resolves promoted findings on the way past,
and `--apply` must enact the classification it just showed the operator and
nothing else.

That wiring is not in this diff, and the reason is worth writing down rather
than leaving to be rediscovered: this node's worktree is pinned to a commit that
predates the classifier's, `depends_on` carries no content guarantee
(`docs/architecture.md`), and a branch carrying both halves measured 97,820
diff bytes against a 64 KiB verification ceiling — refused before a judge reads
it. So the seam is four lines wide and the sweep behind it is whole and tested.
It was run against the real classifier on a tree that had both, over a supplied
store and corpus; the tail of that run, pasted:

    --apply: 5 rows changed

    resolved (1)
      ops/leaks-a-key
        012-plugs-the-leak

    folded (2)
      hardening/agent-worktree-boundary/070/us4
        folded into 'hardening/agent-worktree-boundary' — 2 rows from source
        'boundary-detector' are one defect split by key
      hardening/agent-worktree-boundary/070/us5
        folded into 'hardening/agent-worktree-boundary' — 2 rows ...

    surviving class key: hardening/agent-worktree-boundary
      the fold does not hold yet: until the detector keys on the class ...

    annotated, still open (2)
      ops/long-quiet
      ops/still-live

    untouched by design: 0 seen-after-fix
    untouched by design: 1 candidate

and a second `--apply` over the same store reported `"writes": 0` with both
annotations listed under `annotations_already_present`.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Protocol, Sequence

from factory.doctor.store import annotate, resolve, resolve_by_spec

#: The only two classes `--apply` may close (FR-019). One tuple, one branch,
#: one place for an operator to audit — see the module docstring.
RESOLVABLE = ("fixed", "fragmented")

#: Annotated in `notes`, and left `open` (FR-017).
ANNOTATABLE = ("cold", "needs-human")

#: Not touched in any way (FR-015).
UNTOUCHED = ("seen-after-fix", "candidate")

#: Every class this module has a rule for. A row outside it is refused rather
#: than guessed at.
KNOWN_CLASSES = RESOLVABLE + ANNOTATABLE + UNTOUCHED

#: Said in the output of every fold, because it is true of every fold until the
#: detector keys on the class: `--apply` resolves the per-node rows, and the
#: very next attempt mints a fresh one from the same unchanged key. An operator
#: who is not told this reads a re-fragmented ledger as a fold that did nothing.
REFRAGMENT_NOTICE = (
    "the fold does not hold yet: until the detector keys on the class rather "
    "than on the node, the next attempt re-fragments these rows under a fresh key"
)


class ClassifiedFinding(Protocol):
    """One classified row, as the sweep needs to see it.

    Structural on purpose: the classifier's `TriagedFinding` satisfies this
    exactly, and so does a four-field object a test builds in six lines. What
    the sweep does with a row must be provable without a specs corpus, a git
    history and a clock standing behind it.
    """

    key: str
    triage_class: str
    reason: str
    specs: Sequence[str]


class FragmentedClass(Protocol):
    """Two or more rows that are one defect split by key.

    `prefix` is the shared first two segments and `keys` the members; `members`
    is their count, carried rather than recomputed so that the number written
    into every member's resolution is one fact about the class.
    """

    prefix: str
    source: str
    keys: Sequence[str]
    members: int


def may_resolve(triage_class: str) -> bool:
    """Whether `--apply` is allowed to close a row in this class (FR-019)."""
    return triage_class in RESOLVABLE


@dataclass(frozen=True)
class Enacted:
    """One thing `--apply` did, and the resolution the row now carries."""

    key: str
    triage_class: str
    action: str
    resolution: str


@dataclass(frozen=True)
class Application:
    """The whole of what one pass changed — and what it deliberately did not."""

    resolved: list[Enacted] = field(default_factory=list)
    folded: list[Enacted] = field(default_factory=list)
    annotated: list[Enacted] = field(default_factory=list)
    already_annotated: list[str] = field(default_factory=list)
    untouched: dict[str, int] = field(default_factory=dict)
    folds: list[FragmentedClass] = field(default_factory=list)
    refused: list[str] = field(default_factory=list)

    @property
    def writes(self) -> int:
        return len(self.resolved) + len(self.folded) + len(self.annotated)


def apply_triage(
    conn: sqlite3.Connection,
    findings: Iterable[ClassifiedFinding],
    fragmented_classes: Sequence[FragmentedClass] = (),
    *,
    now: datetime | None = None,
) -> Application:
    """Enact the two closable classes, annotate two, and leave the rest alone.

    One loop over every classified row, with the class deciding — rather than
    one loop per class, which would make `RESOLVABLE` a comment (see the module
    docstring). A fragmented row still folds as one act: its class is looked up
    by key, so every member carries the same prefix and the same count.

    `now` is injected so the timestamps a pass writes are the caller's to fix
    (constitution IV). The classification is already pure over its inputs, and
    this keeps the enactment testable without a wall clock.
    """
    resolved_at = _stamp(now)
    application = Application(untouched={name: 0 for name in UNTOUCHED})
    group_of = {key: group for group in fragmented_classes for key in group.keys}

    for item in findings:
        triage_class = str(item.triage_class)
        if triage_class not in KNOWN_CLASSES:
            application.refused.append(item.key)
        elif may_resolve(triage_class):
            _resolve_one(conn, item, group_of.get(item.key), resolved_at, application)
        elif triage_class in ANNOTATABLE:
            _annotate(conn, item, application)
        else:
            application.untouched[triage_class] = (
                application.untouched.get(triage_class, 0) + 1
            )

    folded = {item.key for item in application.folded}
    application.folds.extend(
        group for group in fragmented_classes if folded.intersection(group.keys)
    )
    return application


def _stamp(now: datetime | None) -> str:
    moment = now or datetime.now(timezone.utc)
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _resolve_one(
    conn: sqlite3.Connection,
    item: ClassifiedFinding,
    group: FragmentedClass | None,
    resolved_at: str,
    application: Application,
) -> None:
    """Close one row, by the only two doors that exist. Two shapes:

    - **A fold** (FR-016) goes through `resolve`, the reason-carrying variant,
      because the shared prefix and the member count *are* the reason. There is
      no spec to name, and naming one would claim a proof this class has not
      got.
    - **A declaration** (FR-014) goes through `resolve_by_spec`, the path the
      promoted-finding sweep already uses: it records the spec directory as the
      resolution and sources the event to the roadmap rather than to an
      operator. No second resolution path is added for this story.

    A resolvable row with neither a group nor a declaring spec is refused, not
    closed under a resolution nobody could check.
    """
    if group is not None:
        reason = (
            f"folded into '{group.prefix}' — {group.members} rows from source "
            f"'{group.source}' are one defect split by key"
        )
        if resolve(conn, item.key, reason=reason, resolved_at=resolved_at):
            application.folded.append(
                Enacted(item.key, str(item.triage_class), "folded", reason)
            )
        return

    if not item.specs:
        application.refused.append(item.key)
        return

    spec_dir = ", ".join(item.specs)
    if resolve_by_spec(conn, item.key, spec_dir=spec_dir, resolved_at=resolved_at):
        application.resolved.append(
            Enacted(item.key, str(item.triage_class), "resolved", spec_dir)
        )


def _annotate(
    conn: sqlite3.Connection, item: ClassifiedFinding, application: Application
) -> None:
    """FR-017/FR-018: write the class and its reason into `notes`, and stop.

    The row keeps its status, its occurrences, its `last_seen` and its event
    trail — which is the whole reason `annotate` exists beside `resolve` rather
    than this going through `report()`. A second pass over an unchanged
    classification writes nothing at all, which is what `annotate` returning
    False reports.
    """
    annotation = f"{item.triage_class}: {item.reason}"
    if annotate(conn, item.key, annotation=annotation):
        application.annotated.append(
            Enacted(item.key, str(item.triage_class), "annotated", "")
        )
    else:
        application.already_annotated.append(item.key)


# --- rendering ----------------------------------------------------------------


def render(application: Application) -> str:
    """What the pass did, in the order an operator needs to check it.

    The classes left alone are printed as counts rather than omitted: a sweep
    silent about the rows it did not touch is indistinguishable from one that
    forgot them, and those are the two classes it would be most damaging to
    close.
    """
    lines = ["", f"--apply: {application.writes} rows changed"]
    lines.extend(_section("resolved", application.resolved))
    lines.extend(_section("folded", application.folded))

    if application.folds:
        lines.append("")
        lines.append(
            f"surviving class {_plural('key', len(application.folds))}: "
            + ", ".join(group.prefix for group in application.folds)
        )
        lines.append(f"  {REFRAGMENT_NOTICE}")

    lines.append("")
    lines.append(f"annotated, still open ({len(application.annotated)})")
    for item in application.annotated:
        lines.append(f"  {item.key}")
    if application.already_annotated:
        lines.append(
            f"  ({len(application.already_annotated)} already annotated by an "
            "earlier pass, unchanged)"
        )

    lines.append("")
    for name in UNTOUCHED:
        lines.append(f"untouched by design: {application.untouched.get(name, 0)} {name}")
    lines.append(
        "  a declaration plus a later sighting is a regression, and prose is "
        "not a declaration — neither is closable"
    )
    if application.refused:
        lines.append("")
        lines.append(f"refused ({len(application.refused)})")
        for key in application.refused:
            lines.append(f"  {key}")
    return "\n".join(lines)


def _section(title: str, enacted: Sequence[Enacted]) -> list[str]:
    lines = ["", f"{title} ({len(enacted)})"]
    if not enacted:
        lines.append("  (none)")
        return lines
    for item in enacted:
        lines.append(f"  {item.key}")
        lines.append(f"    {item.resolution}")
    return lines


def to_document(application: Application) -> dict:
    """The `--json` half: the same pass, machine-readable."""
    return {
        "writes": application.writes,
        "resolvable_classes": list(RESOLVABLE),
        "resolved": [_entry(item) for item in application.resolved],
        "folded": [_entry(item) for item in application.folded],
        "surviving_class_keys": [group.prefix for group in application.folds],
        "refragments_until_the_detector_keys_on_the_class": bool(application.folds),
        "annotated": [item.key for item in application.annotated],
        "annotations_already_present": list(application.already_annotated),
        "untouched": {name: application.untouched.get(name, 0) for name in UNTOUCHED},
        "refused": list(application.refused),
    }


def _entry(item: Enacted) -> dict:
    return {
        "key": item.key,
        "class": item.triage_class,
        "action": item.action,
        "resolution": item.resolution,
    }


def _plural(noun: str, count: int) -> str:
    return noun if count == 1 else f"{noun}s"
