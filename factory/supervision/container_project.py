"""The engine container's compose project, rendered from data (104-US2).

*The engine container* is the Docker container `ergane install` brings up — never
bwrap's sandbox, never "a container of specs".

One renderer, two projects. `reference_project()` is symbolic and must agree with
the committed `container/compose.reference.yaml` **structurally** — parsed
documents equal, ordered comment lines equal — never byte-for-byte (R4).
`resolve_project(...)` is operational and calls the path resolvers rather than
copying that file's `${HOME}` literals (trap 5).

Three rules the rest keeps: **comments are data**, or the operational file
inherits "this is a reference artifact" and lies about itself; **resolved values
go in `.env`**, never `environment:`, and credentials into neither; **every
declared path is covered by one of the project's own mounts** (`_check_paths`) —
the check that would have caught the supervisor's unmounted `/var/lib/ergane`.
"""

from __future__ import annotations

import dataclasses
import importlib.metadata
import importlib.resources
import json
import os
import re
from pathlib import Path
from typing import Mapping

from factory.cli.errors import OperatorError
from factory.config import resolve_default_registry_path
from factory.controlplane.config import ControlPlaneConfig, resolve_config_path
from factory.registry import Registry, load_registry, resolve_state_home
from factory.supervision.units import (
    GeneratedFile,
    InstallLayout,
    resolve_layout,
    supervision_home,
)

SERVICE_NAME = "ergane"

#: The project's directory name, under the supervision home.
PROJECT_DIRNAME = "container"

COMPOSE_NAME = "compose.yaml"
ENV_NAME = ".env"

#: Copied beside the compose file so `security_opt`'s relative paths resolve.
SECCOMP_ARTIFACT = "seccomp-ergane.json"
APPARMOR_ARTIFACT = "ergane-engine.profile"

#: The AppArmor profile's own name, as `apparmor_parser` loads it.
APPARMOR_PROFILE_NAME = "ergane-engine"

#: The shipped confinement — config G, a literal no parameter reaches (trap 9),
#: so US4's `unconfined` variant cannot arrive here as a changed default.
CONFINED_SECURITY_OPT: tuple[str, ...] = (
    "no-new-privileges:true",
    f"seccomp:./{SECCOMP_ARTIFACT}",
    f"apparmor={APPARMOR_PROFILE_NAME}",
)

#: Config F (104-US4): what the operator gets when the profile was declined or
#: `apparmor_parser` refused it. AppArmor is the only thing that changes —
#: seccomp and no-new-privileges are identical, because F is a relaxation of one
#: layer and not of the contract.
UNCONFINED_SECURITY_OPT: tuple[str, ...] = (
    "no-new-privileges:true",
    f"seccomp:./{SECCOMP_ARTIFACT}",
    "apparmor=unconfined",
)

#: The two confinement variants, named by what they ask Docker for. Only
#: `resolve_project` takes one; `reference_project()` takes no parameters at all
#: (trap 9), so the committed reference cannot go red on a changed default.
CONFINEMENT_PROFILE = "profile"
CONFINEMENT_UNCONFINED = "unconfined"

_SECURITY_OPT_BY_CONFINEMENT: dict[str, tuple[str, ...]] = {
    CONFINEMENT_PROFILE: CONFINED_SECURITY_OPT,
    CONFINEMENT_UNCONFINED: UNCONFINED_SECURITY_OPT,
}

#: Annotation key for the comment block above `security_opt:` — where config F
#: explains itself in the generated file.
SECURITY_OPT_KEY = "security_opt"

#: Why an F project is an F project, as data (R4) so it reaches both the
#: generated file's comments and the installer's own output from one source. A
#: renderer literal would put it in *every* render, including G's.
#:
#: Both measured facts in it are trap 8's, and both are the reason the decline
#: path may not be described as "the safe option": the stub F depends on is
#: hand-installed on the reference floor and owned by no package, and removing
#: the profile on Ubuntu >= 23.10 makes the situation worse rather than neutral.
UNCONFINED_EXPLANATION: tuple[str, ...] = (
    "Confinement: config F -- `apparmor=unconfined`, which is NOT the shipped",
    "configuration. The shipped configuration is config G:",
    f"`apparmor={APPARMOR_PROFILE_NAME}`, the named profile in",
    f"{APPARMOR_ARTIFACT} beside this file. It was not loaded into the kernel, so",
    "this project asks Docker for no AppArmor profile at all. seccomp and",
    "no-new-privileges are identical in both variants; AppArmor is the whole of",
    "the difference.",
    "",
    "This is a completely generated, honestly annotated engine, and these are its",
    "remaining prerequisites. Config F is not the privilege-free option; it is",
    "the other one:",
    "",
    "  1. A /etc/apparmor.d/bwrap stub must already be loaded on this host. It is",
    "     not stock Ubuntu 24.04 and no package owns it -- it is hand-installed",
    "     on the reference floor. Without it bwrap fails at `write failed",
    "     /proc/self/uid_map: Operation not permitted` with no obvious cause",
    "     (measured: docs/container-onramp-research-findings.md section 8, item",
    "     3).",
    "  2. To reach config G instead, load the profile from this directory and",
    f"     re-run install:  sudo apparmor_parser -r ./{APPARMOR_ARTIFACT}",
    "     then `ergane install`.",
    "",
    'Do not read this as "AppArmor is off". On Ubuntu 23.10 and later, removing',
    "the profile activates the kernel's capability-stripping unprivileged_userns",
    "transition: the namespace is created and the uid_map write is then refused.",
    "Turning AppArmor off to debug this makes it worse, always (findings section",
    "8, item 4).",
)

#: The top-level key carrying the per-repo same-path mount list.
REPO_MOUNT_KEY = "x-ergane-repos"

#: Annotation key for the generated `.env`'s own comment block.
ENV_FILE_KEY = ENV_NAME

#: Where Temporal listens *inside* the engine, spelled `host:port`: the tree-wide
#: convention, and the supervisor's children read the same variable (R12).
ENGINE_TEMPORAL_PORT = 7233
ENGINE_TEMPORAL_ADDRESS = f"127.0.0.1:{ENGINE_TEMPORAL_PORT}"

#: The engine's own Temporal database, under the state root (R6) — never
#: `temporal_db_path`'s `dev.db`: two servers on one SQLite file is findings §3.
TEMPORAL_DB_NAME = "engine.db"

#: `local` is the default until spec 105 publishes the image: a `registry`
#: project would today pull a tag GHCR has not got.
IMAGE_SOURCE_REGISTRY = "registry"
IMAGE_SOURCE_LOCAL = "local"

#: Private on purpose: spec 105's `engine_identity.py` owns the public version
#: vocabulary and will delegate these, so 104 must not create a second.
_IMAGE_REPOSITORY = "ghcr.io/bryantharpeorg/ergane"
_LOCAL_IMAGE_REPOSITORY = "ergane-local"

#: The import package the distribution rename left alone (FR-002);
#: `_engine_image_version()` asks which distribution ships it.
_IMPORT_PACKAGE = "factory"

#: Seam: how the version is derived. Rebound in tests, the convention
#: `factory/cli/install.py` uses for `_scan_endpoints`.
_distribution_version = importlib.metadata.version


# --- The env passthrough list — one shared source (T021) ---

#: The bare names the compose `environment:` passes through, in the reference's
#: order — compose resolves an `=`-less entry from the `.env` beside it (R5).
REFERENCE_ENVIRONMENT_NAMES: tuple[str, ...] = (
    "PATH",
    "LANG",
    "TERM",
    "HOME",
    "ERGANE_STATE_HOME",
    "FACTORY_STATE_HOME",
    "ERGANE_CONFIG_PATH",
    "FACTORY_CONFIG_PATH",
    "ERGANE_LLM_MASTER_KEY",
    "ERGANE_LLM_API_KEY",
    "ERGANE_MEMORY_URL",
    "ERGANE_MEMORY_API_KEY",
    "TEMPORAL_ADDRESS",
    "TEMPORAL_NAMESPACE",
    "ERGANE_TEMPORAL_API_KEY",
    "ERGANE_OTLP_ENDPOINT",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "ERGANE_VERSION",
)

#: What the operational project adds, additively: a `.env` value reaches the
#: engine only if declared here — trap 3's registry pin and R6's database pin.
_OPERATIONAL_ENVIRONMENT_NAMES: tuple[str, ...] = (
    "ERGANE_PERSONAS_PATH",
    "ERGANE_TEMPORAL_DB_FILENAME",
)


def derived_environment_names() -> set[str]:
    """The env-var names the five subsystem blocks name by default, derived
    rather than restated. The drift suite used to own this; the generator and the
    reference need one answer, not two (T021)."""
    # Imported inside the function: US5 wires `factory.cli.install` to this
    # module, so a module-level import closes that loop into a cycle — and drags
    # the discovery/notify/usage tree into every process wanting a compose file.
    from factory.cli.install import (  # noqa: PLC0415 - see comment above
        BLANK_DOCUMENT,
        _OPTIONAL_INTERVIEW_FIELDS,
        _controlplane_default,
    )

    env_names: set[str] = set()
    document = dict(BLANK_DOCUMENT)

    def _collect(obj: object) -> None:
        if isinstance(obj, dict):
            for value in obj.values():
                _collect(value)
        elif isinstance(obj, str) and re.fullmatch(r"[A-Z_][A-Z0-9_]*", obj):
            env_names.add(obj)

    _collect(document)

    for field in _OPTIONAL_INTERVIEW_FIELDS:
        default = _controlplane_default(document, field)
        if isinstance(default, str) and re.fullmatch(r"[A-Z_][A-Z0-9_]*", default):
            env_names.add(default)

    # Path overrides the factory honours, then the low-level passthrough.
    env_names.update(
        {"ERGANE_STATE_HOME", "FACTORY_STATE_HOME", "ERGANE_CONFIG_PATH", "FACTORY_CONFIG_PATH"}
    )
    env_names.update({"PATH", "LANG", "TERM", "HOME"})
    return env_names


# --- The project data ---

#: Role in the mount guard: `value` is no path; `path` is opened, so a mount must
#: contain it; `anchor` is resolved *through*, so a mount must sit beneath it.
ENV_VALUE = "value"
ENV_PATH = "path"
ENV_ANCHOR = "anchor"


@dataclasses.dataclass(frozen=True)
class Mount:
    """One bind, `<path>:<path>`. Same-path is the invariant: git stores absolute
    paths in `.git/worktrees/<name>/gitdir`, so a host worktree survives a commit
    made in the engine only if both sides spell it alike."""

    source: str
    target: str


@dataclasses.dataclass(frozen=True)
class BuildStanza:
    """Where `docker compose build` finds the image's source."""

    context: str
    dockerfile: str = "Dockerfile"


@dataclasses.dataclass(frozen=True)
class EnvAssignment:
    """One `NAME=value` line of the generated `.env`, and its role in the guard."""

    name: str
    value: str
    kind: str = ENV_VALUE


@dataclasses.dataclass(frozen=True)
class ContainerProject:
    """The engine container's compose project, as data — no clock, no environment
    read, no filesystem probe, which makes US2-S2's determinism structural.
    `header` is the comment block above `services:`; `annotations` are comments
    keyed by what they precede: a mount source, `x-ergane-repos`, `.env`."""

    image: str
    build: BuildStanza | None
    #: The confinement variant, as the `security_opt` lines it renders to.
    security_opt: tuple[str, ...]
    user: str
    #: What the guard is against: state root, supervision home, config dir, every
    #: repo — the *argument* of `InstallLayout.roots`, not its tuple.
    roots: tuple[Path, ...]
    mounts: tuple[Mount, ...]
    repo_mounts: tuple[Mount, ...]
    environment: tuple[str, ...]
    env_assignments: tuple[EnvAssignment, ...]
    ports: tuple[str, ...]
    directory: Path
    header: tuple[str, ...] = ()
    annotations: Mapping[str, tuple[str, ...]] = dataclasses.field(default_factory=dict)

    def __post_init__(self) -> None:
        _check_paths(self)


def project_dir(layout: InstallLayout | None = None) -> Path:
    """Where the generated project lives — and the record that this installation
    runs the container tier (R1). Later stories ask here, never `config.toml`."""
    if layout is not None:
        return layout.generated_dir / PROJECT_DIRNAME
    return supervision_home() / PROJECT_DIRNAME


# --- The mount guard (trap 4) ---


def _covered(path: Path, roots: tuple[Path, ...]) -> bool:
    """Whether a mount makes `path` reachable inside the engine."""
    return any(path == root or path.is_relative_to(root) for root in roots)


def _anchors(path: Path, roots: tuple[Path, ...]) -> bool:
    """Whether a mount is created *beneath* `path` — what makes an anchor exist
    inside the engine though nothing mounts it."""
    return any(root == path or root.is_relative_to(path) for root in roots)


def _check_paths(project: ContainerProject) -> None:
    """Refuse, at construction, a project only one host would run correctly — what
    it catches fails not at bring-up but at the first dispatch, hours later."""
    roots = tuple(project.roots)

    for mount in (*project.mounts, *project.repo_mounts):
        if mount.source != mount.target:
            raise OperatorError(
                f"the engine container's bind for {mount.source} is not same-path "
                f"(container path {mount.target}); git records absolute paths in "
                "its worktree files, and a rewritten one breaks on the other side"
            )
        if not _covered(Path(mount.source), roots):
            raise OperatorError(
                f"the engine container's project declares a mount at {mount.source}, "
                f"which none of its own roots covers "
                f"({', '.join(str(root) for root in roots)})"
            )

    for assignment in project.env_assignments:
        if assignment.kind == ENV_PATH and not _covered(Path(assignment.value), roots):
            raise OperatorError(
                f"the engine container's {assignment.name} points at "
                f"{assignment.value}, which no mount covers — inside the engine "
                "that is a throwaway layer, discarded on the next recreate"
            )
        if assignment.kind == ENV_ANCHOR and not _anchors(Path(assignment.value), roots):
            raise OperatorError(
                f"the engine container's {assignment.name} points at "
                f"{assignment.value}, and no mount is created beneath it, so that "
                "directory does not exist inside the engine"
            )


# --- Package data: the confinement artifacts (R10) ---


def _packaged_artifact(name: str):
    """The artifact as package data, present or not — a seam, so a test can prove
    the wheel layout wins without building one."""
    return importlib.resources.files("factory") / PROJECT_DIRNAME / name


def confinement_artifact_text(name: str) -> str:
    """A committed confinement artifact's text: package data first — the ordering
    `factory/config.py:98-101` fixes — then the checkout. Every reader comes
    through here, US4's consent prompt included."""
    packaged = _packaged_artifact(name)
    if packaged.is_file():
        return packaged.read_text(encoding="utf-8")
    # Checkout: two levels up from `factory/supervision/` is the repo root — the
    # walk `factory/config.py:72` makes. In a wheel that is `site-packages`.
    checkout = Path(__file__).resolve().parents[2] / PROJECT_DIRNAME / name
    if not checkout.is_file():
        raise OperatorError(
            f"cannot read the confinement artifact {name}: it is neither packaged "
            f"at factory/{PROJECT_DIRNAME}/{name} nor present at {checkout}; the "
            "engine container's confinement contract is not optional"
        )
    return checkout.read_text(encoding="utf-8")


# --- The image reference (R7) ---


def _engine_image_version() -> str:
    """The CLI's version, also the image's tag — the derivation
    `factory/cli/main.py:131` makes, in a file this story never edits. The
    distribution is *asked for*, never spelled: `test_distribution_rename.py:266`
    holds `main.py` as the only module allowed to name it (FR-002), and asking
    which distribution ships this import package states the real relationship
    rather than restating a name."""
    shipped_by = importlib.metadata.packages_distributions().get(_IMPORT_PACKAGE, [])
    for distribution in shipped_by:
        try:
            return _distribution_version(distribution)
        except importlib.metadata.PackageNotFoundError:
            continue
    raise OperatorError(
        "cannot derive the engine container's image tag: no readable version for "
        f"the distribution shipping {_IMPORT_PACKAGE!r} "
        f"({', '.join(shipped_by) or 'none is installed'}), so there is no "
        "version to read. The tag is never guessed — a wrong one runs an engine "
        "this CLI does not match, and the startup handshake refuses it"
    )


def _engine_image_reference(source: str, version: str) -> str:
    if source == IMAGE_SOURCE_REGISTRY:
        return f"{_IMAGE_REPOSITORY}:{version}"
    if source == IMAGE_SOURCE_LOCAL:
        return f"{_LOCAL_IMAGE_REPOSITORY}:{version}"
    raise OperatorError(
        f"unknown image source {source!r} for the engine container; expected "
        f"{IMAGE_SOURCE_REGISTRY!r} or {IMAGE_SOURCE_LOCAL!r}"
    )


def _build_stanza(source: str, install_root: Path) -> BuildStanza | None:
    """The build stanza, or the refusal a wheel install gets instead:
    `Dockerfile:44` is `COPY . /opt/ergane`, so the context *is* the repository
    and a wheel has none. Refusing here costs a prompt, nothing privileged."""
    if source != IMAGE_SOURCE_LOCAL:
        return None
    dockerfile = install_root / "Dockerfile"
    if not dockerfile.is_file():
        raise OperatorError(
            f"this installation has no build context: {dockerfile} is not a file, "
            "which is what an install from a wheel looks like. The engine container "
            "needs a source checkout until the published image lands (spec 105); "
            "run `ergane install` from a checkout, or wait for the published image"
        )
    return BuildStanza(context=str(install_root), dockerfile="Dockerfile")


# --- The two projects ---

#: The committed file's own header, as data so the operational project can carry
#: its own (R4).
_REFERENCE_HEADER: tuple[str, ...] = (
    "Reference compose for the Ergane engine container.",
    "",
    "This is a reference artifact: `ergane install` (spec 104) generates the",
    "operational project from the same interview answers used for the native tier.",
    "It declares the narrow confinement contract (seccomp + AppArmor) and the",
    "same-path mount invariants the engine relies on.",
)

#: The reference's symbolic paths — literals here and nowhere else (trap 5).
_REFERENCE_STATE_ROOT = "${HOME}/.local/state/ergane"
_REFERENCE_SUPERVISION = "${HOME}/.local/state/ergane/supervision"
_REFERENCE_REPO = "${ERGANE_REPO_EXAMPLE:-/path/to/repo}"


def reference_project() -> ContainerProject:
    """The reference project: what `container/compose.reference.yaml` says. Takes
    no parameters, and that is the point (trap 9) — the confinement is a literal,
    so config F is unreachable from here rather than merely untaken."""
    return ContainerProject(
        image=f"{_IMAGE_REPOSITORY}:${{ERGANE_VERSION}}",
        build=None,
        security_opt=CONFINED_SECURITY_OPT,
        user="1000:1000",
        roots=(
            Path(_REFERENCE_STATE_ROOT),
            Path(_REFERENCE_SUPERVISION),
            Path(_REFERENCE_REPO),
        ),
        mounts=(
            Mount(_REFERENCE_STATE_ROOT, _REFERENCE_STATE_ROOT),
            Mount(_REFERENCE_SUPERVISION, _REFERENCE_SUPERVISION),
            Mount(_REFERENCE_REPO, _REFERENCE_REPO),
        ),
        repo_mounts=(Mount(_REFERENCE_REPO, _REFERENCE_REPO),),
        environment=REFERENCE_ENVIRONMENT_NAMES,
        env_assignments=(),
        ports=(),
        directory=Path(PROJECT_DIRNAME),
        header=_REFERENCE_HEADER,
        annotations={
            _REFERENCE_STATE_ROOT: (
                "State root: must be the same absolute path on host and in the container",
                "so the native CLI and the container read the same SQLite files.",
            ),
            _REFERENCE_SUPERVISION: (
                "Supervision home: the managed Temporal dev-server keeps its database",
                "one directory above the supervision subdirectory. Mount it, or workflow",
                "history is discarded on recreate.",
            ),
            _REFERENCE_REPO: (
                "Per-repo source mounts are generated by `ergane install` (spec 104).",
                "Each entry must be same-path: the host path and the container path are",
                "identical so git worktree records resolve on both sides.",
            ),
            REPO_MOUNT_KEY: (
                "Per-repo same-path mount list.  The generator (spec 104) emits one entry per",
                "registered repo.  Keeping it outside the service volumes makes the shape",
                "explicit and keeps the reference file readable.",
            ),
        },
    )


def _operational_header(version: str) -> tuple[str, ...]:
    return (
        f"Ergane engine container, generated by `ergane install` {version}.",
        "Do not hand-edit: rendered from the confirmed control-plane config and the",
        "repo registry, with a digest recorded, so an edit here is overwritten on",
        "the next run or left behind at teardown. Change the answers instead.",
        "",
        "Every bind below is same-path, so git worktree records resolve on both",
        "sides.",
    )


def _env_header(version: str) -> tuple[str, ...]:
    return (
        f"Generated by `ergane install` {version}. Do not hand-edit.",
        "",
        "Read by Docker Compose out of the project directory. Resolved host paths",
        "only: credentials stay in the operator's shell and reach the engine",
        "through the compose `environment:` list, never a generated file.",
    )


def _published_ports(config: ControlPlaneConfig) -> tuple[str, ...]:
    """What the project publishes, bound to loopback. The reference declares none,
    so the host CLI could reach nothing. The port is the confirmed
    `temporal.address`'s, which is why US5 probes it first (trap 6)."""
    address = config.temporal.address
    if not address:
        return ()
    _, separator, port = address.rpartition(":")
    if not separator or not port.isdigit():
        return ()
    return (f"127.0.0.1:{port}:{ENGINE_TEMPORAL_PORT}",)


def resolve_project(
    config: ControlPlaneConfig,
    *,
    registry: Registry | None = None,
    config_path: Path | None = None,
    personas_path: Path | None = None,
    home: Path | None = None,
    install_root: Path | None = None,
    image_source: str = IMAGE_SOURCE_LOCAL,
    confinement: str = CONFINEMENT_PROFILE,
) -> ContainerProject:
    """Resolve the operational project for this host from confirmed answers.
    Everything resolves here, once, so the project is data and the renderer pure;
    every path comes from a resolver, never a literal (trap 5).

    `confinement` is US4's decision, and it reaches *only* this function: the
    consent step decides it, and a declined or failed profile load is the whole
    of what makes an F project. The reference is unaffected by construction
    (trap 9) — it takes no parameters at all.
    """
    security_opt = _SECURITY_OPT_BY_CONFINEMENT.get(confinement)
    if security_opt is None:
        raise OperatorError(
            f"unknown confinement variant {confinement!r} for the engine "
            f"container; expected {CONFINEMENT_PROFILE!r} (config G, the shipped "
            f"one) or {CONFINEMENT_UNCONFINED!r} (config F)"
        )

    version = _engine_image_version()
    install_root = (
        resolve_layout().install_root if install_root is None else Path(install_root)
    )
    build = _build_stanza(image_source, install_root)
    image = _engine_image_reference(image_source, version)

    home = Path.home() if home is None else Path(home)
    state_home = resolve_state_home()
    state_root = state_home / "ergane"
    supervision = supervision_home()
    config_path = resolve_config_path() if config_path is None else Path(config_path)
    config_dir = config_path.parent
    personas_path = (
        resolve_default_registry_path() if personas_path is None else Path(personas_path)
    )
    registry = load_registry() if registry is None else registry
    repo_paths = tuple(entry.path for entry in registry.entries)

    repo_mounts = tuple(Mount(str(path), str(path)) for path in repo_paths)
    mounts = (
        Mount(str(state_root), str(state_root)),
        Mount(str(supervision), str(supervision)),
        Mount(str(config_dir), str(config_dir)),
        *repo_mounts,
    )

    # The host uid, which puts bwrap on its working code path: as PID 1 it fails
    # its uid map, as uid 0 it needs CAP_SYS_ADMIN. Measured, not hygiene.
    user = f"{os.getuid()}:{os.getgid()}"

    env_assignments = (
        EnvAssignment("ERGANE_VERSION", version),
        # Anchors: nothing opens them, but paths resolving through them land in a
        # mount. The image pins HOME=/home/ergane, so `~/.config` needs this.
        EnvAssignment("HOME", str(home), ENV_ANCHOR),
        EnvAssignment("ERGANE_STATE_HOME", str(state_home), ENV_ANCHOR),
        # Trap 3: by explicit path, or `resolve_default_registry_path` falls to
        # the packaged example and the engine runs healthy on `example/` aliases.
        EnvAssignment("ERGANE_CONFIG_PATH", str(config_path), ENV_PATH),
        EnvAssignment("ERGANE_PERSONAS_PATH", str(personas_path), ENV_PATH),
        EnvAssignment(
            "ERGANE_TEMPORAL_DB_FILENAME",
            str(state_root / "temporal" / TEMPORAL_DB_NAME),
            ENV_PATH,
        ),
        EnvAssignment("TEMPORAL_ADDRESS", ENGINE_TEMPORAL_ADDRESS),
        *(
            (EnvAssignment("TEMPORAL_NAMESPACE", config.temporal.namespace),)
            if config.temporal.namespace
            else ()
        ),
    )

    annotations: dict[str, tuple[str, ...]] = {
        str(state_root): (
            "State root: same absolute path here and in the engine, and the mount",
            "that carries the engine's own Temporal database across a recreate.",
        ),
        str(supervision): (
            "Supervision home: a sibling of that database, not its parent.",
        ),
        str(config_dir): (
            "Config directory: without it the engine's `~/.config` does not exist",
            "and the persona registry resolves to the packaged example.",
        ),
        REPO_MOUNT_KEY: (
            "Per-repo same-path mount list. Re-run `ergane init <repo>` to add one.",
        ),
        ENV_FILE_KEY: _env_header(version),
    }
    if confinement == CONFINEMENT_UNCONFINED:
        # Only F annotates itself. G is the shipped configuration and a file that
        # explains why it is normal teaches nobody anything.
        annotations[SECURITY_OPT_KEY] = UNCONFINED_EXPLANATION
    for mount in repo_mounts:
        annotations[mount.source] = (
            "Registered repository, same-path so worktrees resolve on both sides.",
        )

    return ContainerProject(
        image=image,
        build=build,
        security_opt=security_opt,
        user=user,
        roots=(state_root, supervision, config_dir, *repo_paths),
        mounts=mounts,
        repo_mounts=repo_mounts,
        environment=REFERENCE_ENVIRONMENT_NAMES + _OPERATIONAL_ENVIRONMENT_NAMES,
        env_assignments=env_assignments,
        ports=_published_ports(config),
        directory=project_dir(),
        header=_operational_header(version),
        annotations=annotations,
    )


# --- Rendering ---

#: A string safe as a YAML plain scalar; anything else is double-quoted, which
#: YAML reads back identically.
_PLAIN_SAFE = re.compile(r"[A-Za-z0-9_$/][A-Za-z0-9_${}./:@=+,-]*")


def _scalar(value: str) -> str:
    return value if _PLAIN_SAFE.fullmatch(value) else json.dumps(value)


def _comments(lines: tuple[str, ...], indent: str) -> list[str]:
    """Comment lines; `#` markers are supplied here so the data stays text."""
    return [f"{indent}#" if not line else f"{indent}# {line}" for line in lines]


def render_compose(project: ContainerProject) -> str:
    """Render `compose.yaml` from the project and nothing else — the one renderer,
    which makes the committed reference and the generated file one fact."""
    lines: list[str] = []
    if project.header:
        lines.extend(_comments(project.header, ""))
        lines.append("")

    lines.append("services:")
    lines.append(f"  {SERVICE_NAME}:")
    lines.append(f"    image: {_scalar(project.image)}")
    if project.build is not None:
        lines.append("    build:")
        lines.append(f"      context: {_scalar(project.build.context)}")
        lines.append(f"      dockerfile: {_scalar(project.build.dockerfile)}")
    lines.append("    init: true")
    lines.append(f'    user: "{project.user}"')
    lines.append("    cap_drop: [ALL]")
    # An annotation slot, empty for the shipped confinement: config F's
    # explanation is data on the project (R4), so it lands here on an F render
    # and nowhere at all on a G one — including the reference's (trap 9).
    lines.extend(_comments(project.annotations.get(SECURITY_OPT_KEY, ()), "    "))
    lines.append("    security_opt:")
    lines.extend(f"      - {option}" for option in project.security_opt)
    if project.ports:
        lines.append("    ports:")
        # Always quoted: an unquoted `127.0.0.1:7233:7233` is the classic
        # compose foot-gun.
        lines.extend(f"      - {json.dumps(port)}" for port in project.ports)
    lines.append("    volumes:")
    for mount in project.mounts:
        lines.extend(_comments(project.annotations.get(mount.source, ()), "      "))
        lines.append(f"      - {_scalar(f'{mount.source}:{mount.target}')}")
    lines.append("    environment:")
    lines.extend(f"      - {name}" for name in project.environment)

    lines.append("")
    lines.extend(_comments(project.annotations.get(REPO_MOUNT_KEY, ()), ""))
    if not project.repo_mounts:
        # Empty rather than absent, `[]` rather than a bare key: a bare key parses
        # to null, and US6 regenerates this list by reading it back.
        lines.append(f"{REPO_MOUNT_KEY}: []")
    else:
        lines.append(f"{REPO_MOUNT_KEY}:")
        for mount in project.repo_mounts:
            lines.append(f"  - source: {json.dumps(mount.source)}")
            lines.append(f"    target: {json.dumps(mount.target)}")

    return "\n".join(lines) + "\n"


def render_env(project: ContainerProject) -> str:
    """Render the `.env` beside the compose file, from the project alone."""
    lines = _comments(project.annotations.get(ENV_FILE_KEY, ()), "")
    if lines:
        lines.append("")
    lines.extend(f"{a.name}={a.value}" for a in project.env_assignments)
    return "\n".join(lines) + "\n"


def project_files(project: ContainerProject) -> tuple[GeneratedFile, ...]:
    """Every file the project is made of: rendered here, written by US3's manifest
    writer (R11). The confinement artifacts are copies, so `security_opt`'s
    relative path resolves beside the compose file."""
    return (
        GeneratedFile(COMPOSE_NAME, render_compose(project), project.directory),
        # 0600: no secret is written here, but a file named `.env` attracts them.
        GeneratedFile(ENV_NAME, render_env(project), project.directory, 0o600),
        GeneratedFile(
            SECCOMP_ARTIFACT, confinement_artifact_text(SECCOMP_ARTIFACT), project.directory
        ),
        GeneratedFile(
            APPARMOR_ARTIFACT, confinement_artifact_text(APPARMOR_ARTIFACT), project.directory
        ),
    )
