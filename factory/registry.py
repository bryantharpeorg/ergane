"""The engine's registry of managed repositories (034 US2, FR-006 … FR-008).

A committed `ergane.yaml` is what makes a repository managed.  That fact lives
in the repo and travels with it — but committed facts cannot be *enumerated*
without an index of where the repos are, and every fleet-level surface (the
scheduler, `repo list`, per-repo ledger and findings dimensions) needs to
enumerate.  This module is that index, and nothing more:

- It lives under the engine's state home, outside every repository, so joining
  a repo never changes what the repo *is*.
- It is a **cache**.  `rebuild()` re-derives it from the committed manifests it
  is pointed at, prunes entries whose repos are gone, and leaves live entries
  alone.  Losing the file is an inconvenience, not amnesia — which is the whole
  defence against a derived index quietly becoming a second authority.
- The one thing it holds that no repo holds is the **slug**: the token woven
  into workflow IDs, ledger rows, findings and the memory-bank identity.  Slugs
  are unique across the registry (FR-007) because two repos sharing one would
  alias each other's workflows.  A rebuild seeded from a bare path therefore
  proposes the directory name, which is what the interview defaults to; a repo
  that declared something else is re-declared by re-running `ergane init`.

**Locking (FR-008).**  Every mutation runs inside `factory.locking`'s exclusive
lock — the same lock `ergane install` takes over the control-plane config, for
the same reason and by the same mechanism, rather than a second convention one
epic later.  Two properties of that helper matter here and are easy to lose if
this is ever rewritten:

1. The lock is a *sibling* `repos.json.lock`, not the registry file itself.  So
   the write below can replace `repos.json` atomically while the lock is held —
   locking the target directly would leave the holder guarding an inode nobody
   reads any more the instant the rename lands.
2. `flock` is released by the kernel when the holder dies, so a killed `ergane
   init` never leaves a stale lock for an operator to clear by hand.

Writes go through a temporary file and `os.replace`, so a reader either sees the
whole previous registry or the whole next one.  The rendering is canonical
(sorted keys, two-space indent), which is what lets SC-005 compare bytes.
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Any, Iterable, Mapping

from factory.controlplane.config import (
    ControlPlaneConfigError,
    load_controlplane_config,
)
from factory.env import (
    ERGANE_STATE_HOME_ENV,
    FACTORY_STATE_HOME_ENV,
    resolve_env_path,
)
from factory.locking import exclusive_lock
from factory.verify.factory_yaml import (
    MANIFEST_NAME,
    FactoryConfigError,
    load_factory_config,
    resolve_manifest_path,
)

#: Where the registry sits under the state home.
DEFAULT_REGISTRY_REL = Path("ergane") / "repos.json"

#: The registry document's schema version.
REGISTRY_VERSION = 1

#: Manifest statuses `repo list` renders (FR-011).  Drift is reported, never
#: hidden by dropping the entry.
MANIFEST_VALID = "valid"
MANIFEST_INVALID = "invalid"
MANIFEST_MISSING = "missing"

#: How long a mutation waits for another writer before refusing.
DEFAULT_LOCK_TIMEOUT_S = 30.0

#: The memory bank identity is derived from the slug, never declared separately:
#: two names for one repo is how a bank and a ledger start disagreeing.
MEMORY_BANK_PREFIX = "ergane-"

#: What a slug may be.  It ends up in workflow IDs and search attributes, so it
#: is deliberately narrow: lowercase, starting alphanumeric, no spaces.
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


class RegistryError(Exception):
    """Something an operator can fix, raised by the registry rather than the CLI.

    The registry is a library: the CLI boundary turns these into `OperatorError`
    so that `ergane init` and `ergane repo …` render one refusal grammar.
    """


class SlugCollision(RegistryError):
    """Two repos claimed one slug; the holder is named so the loser can move."""

    def __init__(self, slug: str, holder: Path, *, claimant: Path | None = None) -> None:
        self.slug = slug
        self.holder = Path(holder)
        self.claimant = Path(claimant) if claimant is not None else None
        message = (
            f"slug '{slug}' is already registered to {self.holder}; "
            "slugs are unique because they name the repo in every workflow ID, "
            "so declare a different slug for this repository"
        )
        super().__init__(message)


class RegistryCorrupt(RegistryError):
    """The cache cannot be read, and rebuilding it is the safe answer."""

    def __init__(self, path: Path, problem: str) -> None:
        self.path = Path(path)
        self.problem = problem
        super().__init__(
            f"{self.path} is not a readable registry ({problem}); it is a cache — "
            "re-derive it with `ergane repo rebuild <repo path> …`"
        )


class NotAManagedRepo(RegistryError):
    """A path offered to `rebuild` carries no committed manifest."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        super().__init__(
            f"{self.path} declares no {MANIFEST_NAME}; the committed manifest is "
            "what makes a repository managed — run `ergane init` there first"
        )


class InvalidSlug(RegistryError):
    """A slug that cannot be woven into a workflow ID, and what to use instead."""

    def __init__(self, slug: str) -> None:
        self.slug = slug
        self.proposal = normalize_slug(slug)
        super().__init__(
            f"slug {slug!r} is not usable as a namespace token; "
            f"use {self.proposal!r} (lowercase, no spaces, starting alphanumeric)"
        )


# ---------------------------------------------------------------------------
# Where the registry lives
# ---------------------------------------------------------------------------


def resolve_state_home() -> Path:
    """Return the engine's state home: env override, then XDG, then `~`.

    Follows the 040 rename convention through `resolve_env_path` — the modern
    `ERGANE_STATE_HOME` wins, the legacy `FACTORY_STATE_HOME` is honored with one
    deprecation per process — rather than reading `os.environ` directly, so this
    resolver and 033's config resolver cannot drift apart (034 plan, trap 4).
    """
    return resolve_env_path(
        ERGANE_STATE_HOME_ENV,
        FACTORY_STATE_HOME_ENV,
        _xdg_state_home(),
    )


def _xdg_state_home() -> Path:
    xdg = os.environ.get("XDG_STATE_HOME")
    if xdg:
        return Path(xdg)
    return Path.home() / ".local" / "state"


def resolve_registry_path() -> Path:
    """Return the registry file's path under the state home."""
    return resolve_state_home() / DEFAULT_REGISTRY_REL


# ---------------------------------------------------------------------------
# Slugs
# ---------------------------------------------------------------------------


def is_valid_slug(slug: str) -> bool:
    """True when `slug` is usable as a namespace token."""
    return bool(_SLUG_RE.match(slug))


def normalize_slug(text: str) -> str:
    """Propose a valid slug for `text` — a directory name, usually.

    Proposed, never applied silently: D-009 governs the interview, so the
    operator confirms this the same way they confirm every other declaration.
    """
    folded = unicodedata.normalize("NFKD", text)
    ascii_only = folded.encode("ascii", "ignore").decode("ascii").lower()
    cleaned = re.sub(r"[^a-z0-9._-]+", "-", ascii_only)
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-._")
    return cleaned or "repo"


def derive_memory_bank(slug: str) -> str:
    """The repo's memory-bank identity, derived from its slug (FR-006, AS4)."""
    return f"{MEMORY_BANK_PREFIX}{slug}"


def declared_memory_backend() -> str | None:
    """The control plane's memory backend, or None when none is declared.

    Read through 033's typed control-plane config rather than a second TOML
    reader.  A host with no control plane installed — or one whose config the
    parser refuses — simply declares no backend here; registering a repo must
    not depend on the engine being fully provisioned (FR-017's spirit).
    """
    try:
        config = load_controlplane_config()
    except ControlPlaneConfigError:
        return None
    backend = config.memory.backend
    return None if backend == "none" else backend


def derive_scopes(slug: str) -> dict[str, str]:
    """Scopes recorded on a registry entry, all derived from the slug."""
    backend = declared_memory_backend()
    if backend is None:
        return {}
    return {"memory_backend": backend, "memory_bank": derive_memory_bank(slug)}


# ---------------------------------------------------------------------------
# The entries
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class RegistryEntry:
    """One managed repo: its slug, where it is, and what was derived from both."""

    slug: str
    path: Path
    manifest: Path
    scopes: Mapping[str, str] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass(frozen=True)
class Registry:
    """A snapshot of the cache, read at one moment."""

    path: Path
    entries: tuple[RegistryEntry, ...]

    def get(self, slug: str) -> RegistryEntry | None:
        for entry in self.entries:
            if entry.slug == slug:
                return entry
        return None

    def for_path(self, repo_path: str | Path) -> RegistryEntry | None:
        target = Path(repo_path).resolve()
        for entry in self.entries:
            if entry.path == target:
                return entry
        return None


@dataclasses.dataclass(frozen=True)
class Registration:
    """What `register` did, so the caller can report it honestly."""

    entry: RegistryEntry
    changed: bool
    previous_slug: str | None = None


@dataclasses.dataclass(frozen=True)
class RebuildResult:
    """What `rebuild` did: what it took in, what it dropped, what remains."""

    adopted: tuple[RegistryEntry, ...]
    pruned: tuple[tuple[str, Path], ...]
    kept: tuple[RegistryEntry, ...]
    recovered: bool = False


# ---------------------------------------------------------------------------
# Reading and writing the document
# ---------------------------------------------------------------------------


def _blank_document() -> dict[str, Any]:
    return {"version": REGISTRY_VERSION, "repos": {}}


def _read_document(path: Path) -> dict[str, Any]:
    """Return the registry document at `path`, or a blank one when absent."""
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return _blank_document()
    except OSError as error:
        raise RegistryCorrupt(path, error.strerror or str(error)) from None
    except UnicodeDecodeError as error:
        raise RegistryCorrupt(path, f"is not valid UTF-8 ({error.reason})") from None

    if not raw.strip():
        return _blank_document()

    try:
        document = json.loads(raw)
    except json.JSONDecodeError as error:
        raise RegistryCorrupt(path, f"is not parseable JSON: {error}") from None

    if not isinstance(document, dict) or not isinstance(document.get("repos"), dict):
        raise RegistryCorrupt(path, "does not hold a `repos` mapping")
    return document


def _entries_of(document: Mapping[str, Any], path: Path) -> tuple[RegistryEntry, ...]:
    entries: list[RegistryEntry] = []
    for slug in sorted(document["repos"]):
        record = document["repos"][slug]
        if not isinstance(record, Mapping) or "path" not in record:
            raise RegistryCorrupt(path, f"entry {slug!r} declares no `path`")
        repo_path = Path(str(record["path"]))
        manifest = Path(str(record.get("manifest") or (repo_path / MANIFEST_NAME)))
        scopes = record.get("scopes") or {}
        if not isinstance(scopes, Mapping):
            raise RegistryCorrupt(path, f"entry {slug!r} has non-mapping `scopes`")
        entries.append(
            RegistryEntry(
                slug=slug,
                path=repo_path,
                manifest=manifest,
                scopes={str(key): str(value) for key, value in scopes.items()},
            )
        )
    return tuple(entries)


def render_registry(document: Mapping[str, Any]) -> str:
    """Render the document canonically, so two equal registries are equal bytes."""
    return json.dumps(document, indent=2, sort_keys=True) + "\n"


def _write_document(path: Path, document: Mapping[str, Any]) -> None:
    """Replace the registry atomically; a reader never sees a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(render_registry(document), encoding="utf-8")
    temporary.chmod(0o600)
    os.replace(temporary, path)


def _record_for(repo: Path, scopes: Mapping[str, str]) -> dict[str, Any]:
    manifest, _ = resolve_manifest_path(repo)
    record: dict[str, Any] = {"path": str(repo), "manifest": str(manifest)}
    if scopes:
        record["scopes"] = dict(scopes)
    return record


# ---------------------------------------------------------------------------
# The operations
# ---------------------------------------------------------------------------


def load_registry(path: str | Path | None = None) -> Registry:
    """Read the registry.  An absent file is an empty registry, not an error."""
    registry_path = Path(path) if path is not None else resolve_registry_path()
    document = _read_document(registry_path)
    return Registry(path=registry_path, entries=_entries_of(document, registry_path))


def manifest_status(entry: RegistryEntry) -> str:
    """Judge the entry's manifest *now*, against the repo rather than the cache.

    The committed manifest is the authority, so the status is resolved live: a
    repo that has since renamed `factory.yaml` to `ergane.yaml` reads valid, and
    one whose manifest was deleted reads `missing` rather than vanishing from the
    listing (AS5).
    """
    manifest, _ = resolve_manifest_path(entry.path)
    if not manifest.is_file():
        return MANIFEST_MISSING
    try:
        load_factory_config(manifest)
    except FactoryConfigError:
        return MANIFEST_INVALID
    return MANIFEST_VALID


def register(
    slug: str,
    repo_path: str | Path,
    *,
    path: str | Path | None = None,
    timeout_s: float = DEFAULT_LOCK_TIMEOUT_S,
    scopes: Mapping[str, str] | None = None,
) -> Registration:
    """Record `repo_path` under `slug`, refusing a collision (FR-007, FR-008).

    Idempotent for the repo that already holds the slug: re-running `ergane init`
    with unchanged answers leaves the file byte-identical (SC-003).  A repo
    re-declared under a *new* slug moves — one repo has one slug, or the two
    entries alias each other in every ID the slug appears in.
    """
    registry_path = Path(path) if path is not None else resolve_registry_path()
    repo = Path(repo_path).resolve()

    if not is_valid_slug(slug):
        raise InvalidSlug(slug)

    entry_scopes = dict(scopes) if scopes is not None else derive_scopes(slug)
    record = _record_for(repo, entry_scopes)

    with exclusive_lock(registry_path, timeout_s=timeout_s):
        document = _read_document(registry_path)
        repos = document["repos"]

        holder = repos.get(slug)
        if holder is not None and Path(str(holder["path"])) != repo:
            raise SlugCollision(slug, Path(str(holder["path"])), claimant=repo)

        previous_slug: str | None = None
        for other_slug, other in list(repos.items()):
            if other_slug != slug and Path(str(other["path"])) == repo:
                previous_slug = other_slug
                del repos[other_slug]

        changed = repos.get(slug) != record or previous_slug is not None
        repos[slug] = record
        if changed or not registry_path.exists():
            _write_document(registry_path, document)

        entries = _entries_of(document, registry_path)
        return Registration(
            entry=next(entry for entry in entries if entry.slug == slug),
            changed=changed,
            previous_slug=previous_slug,
        )


def forget(
    slug: str,
    *,
    path: str | Path | None = None,
    timeout_s: float = DEFAULT_LOCK_TIMEOUT_S,
) -> RegistryEntry | None:
    """Remove one entry, returning it, or `None` when no entry held that slug.

    Only the entry: the manifest, the gitignore line and `.ergane/` belong to
    the repository, and removing them is the operator's own git work (FR-011).
    Held under the same exclusive lock every other mutation takes, so a forget
    racing an init cannot interleave with it.
    """
    registry_path = Path(path) if path is not None else resolve_registry_path()
    with exclusive_lock(registry_path, timeout_s=timeout_s):
        document = _read_document(registry_path)
        repos = document["repos"]
        if slug not in repos:
            return None
        entries = _entries_of(document, registry_path)
        removed = None
        for entry in entries:
            if entry.slug == slug:
                removed = entry
        del repos[slug]
        _write_document(registry_path, document)
        return removed


def rebuild(
    seed_paths: Iterable[str | Path] = (),
    *,
    path: str | Path | None = None,
    timeout_s: float = DEFAULT_LOCK_TIMEOUT_S,
) -> RebuildResult:
    """Re-derive the cache: adopt the seeds, prune the dead, touch nothing live.

    Rebuilding must always be the safe answer (FR-006), which has two
    consequences worth stating.  A seed that carries no committed manifest is
    refused *before* the lock is taken, so a refusal changes nothing.  And a
    registry that cannot be parsed at all is rebuilt from the seeds rather than
    refused — refusing there would leave the operator with a corrupt cache and
    no verb that could repair it.
    """
    registry_path = Path(path) if path is not None else resolve_registry_path()

    seeds: list[Path] = []
    for seed in seed_paths:
        resolved = Path(seed).resolve()
        manifest, _ = resolve_manifest_path(resolved)
        if not manifest.is_file():
            raise NotAManagedRepo(resolved)
        seeds.append(resolved)

    with exclusive_lock(registry_path, timeout_s=timeout_s):
        recovered = False
        try:
            document = _read_document(registry_path)
            _entries_of(document, registry_path)
        except RegistryCorrupt:
            if not seeds:
                raise
            document = _blank_document()
            recovered = True

        repos = document["repos"]
        known_paths = {Path(str(record["path"])): slug for slug, record in repos.items()}

        adopted: list[str] = []
        for seed in seeds:
            if seed in known_paths:
                # Already known: it is a live entry, and live entries are never
                # touched — including their declared slug, which the repo itself
                # does not carry.
                continue
            slug = normalize_slug(seed.name)
            holder = repos.get(slug)
            if holder is not None:
                raise SlugCollision(slug, Path(str(holder["path"])), claimant=seed)
            repos[slug] = _record_for(seed, derive_scopes(slug))
            known_paths[seed] = slug
            adopted.append(slug)

        pruned: list[tuple[str, Path]] = []
        for slug in sorted(repos):
            repo = Path(str(repos[slug]["path"]))
            if not repo.is_dir():
                pruned.append((slug, repo))
        for slug, _repo in pruned:
            del repos[slug]

        if adopted or pruned or recovered or not registry_path.exists():
            _write_document(registry_path, document)
        entries = _entries_of(document, registry_path)

    return RebuildResult(
        adopted=tuple(entry for entry in entries if entry.slug in set(adopted)),
        pruned=tuple(pruned),
        kept=entries,
        recovered=recovered,
    )


__all__ = [
    "DEFAULT_LOCK_TIMEOUT_S",
    "ERGANE_STATE_HOME_ENV",
    "FACTORY_STATE_HOME_ENV",
    "MANIFEST_INVALID",
    "MANIFEST_MISSING",
    "MANIFEST_VALID",
    "InvalidSlug",
    "NotAManagedRepo",
    "RebuildResult",
    "Registration",
    "Registry",
    "RegistryCorrupt",
    "RegistryEntry",
    "RegistryError",
    "SlugCollision",
    "declared_memory_backend",
    "derive_memory_bank",
    "derive_scopes",
    "forget",
    "is_valid_slug",
    "load_registry",
    "manifest_status",
    "normalize_slug",
    "rebuild",
    "register",
    "render_registry",
    "resolve_registry_path",
    "resolve_state_home",
]
