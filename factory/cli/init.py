"""Implementation of `ergane init` (US1).

The scaffold writes the repo's declarations and commits nothing. It refuses
two cases before any question is asked: a directory that is not a git
repository, and a linked git worktree (the factory's own workspaces are never
registered as repos).

The interview is driven by the parser's own `_TOP_LEVEL_KEYS` so a schema that
grows does not leave the interview behind. Each answer is validated with
`parse_factory_config` itself — the installed engine's parser is the parser
that counts (026 finding).

Validation works by keeping a complete in-progress manifest: every required
key has either an operator answer or a valid placeholder default. After each
answer the whole manifest is parsed; if the parser refuses, the operator is
re-asked. This avoids maintaining a second copy of the parser rules while still
catching mistakes at entry time (FR-004).

US2 adds the last act: the completed init records the repo in the engine's
registry (`factory/registry.py`) under the declared slug. That record lives
under the engine's state home, never inside any repo, and it is the only place
the slug exists — the manifest declares what the repo *is*, the registry
records what the engine *calls* it.

US4 adds `--check`, and a full init now ends by running it (FR-010). The check
**gathers and renders; it never writes**: every step is a read — `git
check-ignore`, `git show-ref`, a registry load, a manifest parse, 033's probes —
and the judgment over them is the one the 003 dispatch path already uses
(`onboard.evaluate_repo`), extended rather than forked, so a repo that fails at
the operator's terminal fails the same way at dispatch. Two module-level seams
in the `_client_factory` idiom keep it offline in tests: `_forge_factory`
and `_controlplane_probe`; no test here reaches either default.

US6 adds the third act and the third seam. A full init now creates or reconciles
the repo's roadmap schedule (`factory/roadmap/schedule.py`) before it wires
GitHub, because a repo that is scaffolded, registered and wired but has no
scheduler dispatches nothing when a spec is flipped to `ready` — silently. That
step never raises: an unreachable control plane is a failed *step* (FR-017),
since the scaffold and registry entry are already the operator's. US7 adds the
matching finding: the schedule is read here and judged in `onboard.py`.

049's US4 finished the seam `_forge_factory` started: `--wire` now asks the
forge it resolved to apply a landing policy, instead of resolving one and then
reaching past it for GitHub's own client. One forge-shaped thing stays on this
side of the seam, and is named here rather than left to be discovered: the gates
workflow scaffolded into the operator's own tree is GitHub Actions' file in
GitHub Actions' directory. It stays because it is a local write that needs no
network and must survive a refusal from the forge — moving it behind the seam
would mean a refused operator lost the file the manual steps tell them to
commit. A second forge makes it a question; today it is a stated limit.
"""

from __future__ import annotations

import argparse
import dataclasses
import subprocess
from pathlib import Path
from typing import Any, Callable

import yaml

from factory import registry
from factory.cli.errors import EXIT_OK, EXIT_USER, OperatorError
from factory.locking import LockUnavailable, lock_path_for
from factory.mergequeue import wiring
from factory.mergequeue.forge import WiringRefused, format_step
from factory.mergequeue.models import Finding, TargetRepoProfile
from factory.mergequeue.onboard import InitFacts
from factory.roadmap import schedule as roadmap_schedule
from factory.verify.factory_yaml import (
    DEFAULT_FORGE_NAME,
    MANIFEST_NAME,
    _SUPPORTED_VERSION,
    _TOP_LEVEL_KEYS,
    FactoryConfigError,
    load_factory_config,
    parse_factory_config,
    resolve_manifest_path,
)
from factory.verify.models import FactoryConfig
from factory.workgraph.worktree import DEFAULT_RUNTIME_ROOT, LEGACY_FACTORY_ROOT

#: Runtime root created inside the target repo.
RUNTIME_ROOT = Path(".ergane")

#: Module-level seam so tests can inject a scripted prompter.
_prompter_factory: Callable[[], Any] | None = None

def _default_forge(*, repo_path: str) -> Any:
    """Resolve the forge this repository's manifest declares (049 FR-014).

    Imported late so init stays offline. A repository with no manifest yet — the
    state `--check` exists to judge — resolves the default, so declaring the key
    is what changes the answer and nothing else does.
    """
    from factory.mergequeue.forge import resolve_forge_for_repo

    return resolve_forge_for_repo(repo_path=repo_path)


#: Seam: how *both* `--check` (US4) and `--wire` (US3) reach the forge. One name,
#: one signature — rebound in tests. Exactly one factory for this boundary here:
#: on 2026-08-16 two concurrent stories each added one to this file in different
#: regions, nothing conflicted, the merge kept both and nine tests died (trap 14).
_forge_factory: Callable[..., Any] = _default_forge


def _default_controlplane_probe() -> tuple[list[Finding], int]:
    """Run 033's probes unmodified: this check owns the summary, 033 the probing."""
    from factory.controlplane.verify import verify_controlplane

    return verify_controlplane()


#: Seam: how `--check` reaches the control plane.  Rebound in tests.
_controlplane_probe: Callable[[], tuple[list[Finding], int]] = _default_controlplane_probe


def _prompter() -> Any:
    """Return the current prompter, defaulting to the terminal prompter."""
    factory = _prompter_factory
    if factory is not None:
        return factory()
    return _TerminalPrompter()


class _TerminalPrompter:
    """Ask the operator one question at a time, showing defaults and errors."""

    def ask(self, prompt: str, *, default: str | None = None, error: str | None = None) -> str:
        import sys

        if error:
            print(f"  {error}", file=sys.stderr)
        display = prompt
        if default is not None:
            display = f"{prompt} [{default}]"
        try:
            answer = input(f"{display}: ")
        except EOFError:
            answer = ""
        if default is not None and answer.strip() == "":
            return default
        return answer


def _git_checked(repo: Path, *args: str) -> str:
    """Run a git command and raise OperatorError if it fails."""
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        err = completed.stderr.strip()
        raise OperatorError(
            f"git {' '.join(args)} failed in {repo.resolve()}: {err}",
            code=EXIT_USER,
        )
    return completed.stdout


def resolve_repo_root(path: str | Path | None) -> Path:
    """Return the absolute repo root for the path argument, or refuse.

    Bare `ergane init` (no path) resolves the repo containing the working
    directory. `ergane init .` does the same. Refuses immediately if the
    target is not inside a git repository, naming `git init` as the
    prerequisite. Refuses if the resolved checkout is itself a linked git
    worktree, naming the primary checkout (the parent of `--git-common-dir`).
    """
    target = Path(path) if path else Path.cwd()

    completed = subprocess.run(
        ["git", "-C", str(target), "rev-parse", "--git-dir"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise OperatorError(
            f"{target.resolve()} is not a git repository; run `git init` first",
            code=EXIT_USER,
        )

    # Resolve to the top-level of the repository containing `target`.
    toplevel = Path(_git_checked(target, "rev-parse", "--show-toplevel").strip())

    # In a linked worktree, --git-dir points inside the main repo's .git
    # directory while --git-common-dir points to the main repo's .git.
    git_dir = Path(_git_checked(toplevel, "rev-parse", "--absolute-git-dir").strip())
    common_dir_raw = _git_checked(toplevel, "rev-parse", "--git-common-dir").strip()
    common_dir = Path(common_dir_raw)
    if not common_dir.is_absolute():
        common_dir = toplevel / common_dir

    if git_dir.resolve() != common_dir.resolve():
        primary = common_dir.parent.resolve()
        raise OperatorError(
            f"{toplevel.resolve()} is a linked git worktree of {primary}; "
            "run init in the primary checkout",
            code=EXIT_USER,
        )

    return toplevel.resolve()


def add_init_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "init",
        help="join a git repository to Ergane",
        description=(
            "Interview the operator and write the Ergane declarations "
            "(ergane.yaml, .gitignore entry, .ergane/) into the repo. "
            "Commits nothing."
        ),
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="path inside the repository to initialise (default: current directory)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="judge this repository's readiness and exit; writes nothing",
    )
    parser.add_argument(
        "--wire",
        action="store_true",
        help=(
            "also wire the repo's GitHub side to match the declarations: enable "
            "the merge queue on the declared landing branch, require one check "
            "per declared gate, and scaffold the workflow that produces them"
        ),
    )
    parser.set_defaults(run=init_command)
    return parser


#: Human-readable prompts for each top-level manifest key. The order is the
#: order `_TOP_LEVEL_KEYS` declares, and the interview follows it.
_PROMPTS: dict[str, str] = {
    "version": "schema version",
    "runtime": "runtime backend",
    "gates": "gates (YAML mapping of gate name to command)",
    "timeouts": "timeouts in seconds (YAML mapping of gate name to seconds, optional)",
    "standards": "standards document path (optional)",
    "landing_branch": "landing branch",
    "roadmap": (
        "roadmap dials (YAML mapping of cadence_s, max_concurrent_epics, "
        "max_concurrent_nodes, optional)"
    ),
    "forge": "forge this repository is on (optional)",
}

#: Keys an empty answer omits rather than defaults.  Each is additive: a repo
#: that declares none of them is a complete manifest.
_OPTIONAL_KEYS = ("timeouts", "standards", "roadmap", "forge")

#: Spelled as a constant only because `tests/test_ergane_cli.py`'s guard against
#: a hardcoded list of CLI noun names matches a bracket followed by any quoted
#: noun name, and this manifest key shares its word with the `roadmap` noun.  A
#: subscript by literal would trip it; do not inline this back.
_ROADMAP_KEY = "roadmap"

#: Placeholder values that keep a partial manifest valid for full-parser checks.
_PLACEHOLDERS: dict[str, Any] = {
    "runtime": "bwrap",
    "gates": {"test": "true"},
    "landing_branch": "main",
}


def _default_gate_command(repo_root: Path) -> str | None:
    """Propose a gate command if the tree suggests one, otherwise None."""
    if (repo_root / "pyproject.toml").is_file():
        return 'test: "uv run pytest -q"'
    return None


def _load_existing_defaults(repo_root: Path) -> dict[str, Any]:
    """If a manifest already exists, return its values as interview defaults."""
    manifest = repo_root / MANIFEST_NAME
    if not manifest.is_file():
        return {}
    try:
        config = load_factory_config(manifest)
    except Exception:
        return {}
    defaults: dict[str, Any] = {
        "version": config.version,
        "runtime": config.runtime,
        "gates": dict(config.gates),
        "landing_branch": config.landing_branch,
    }
    if config.timeouts:
        defaults["timeouts"] = dict(config.timeouts)
    if config.standards is not None:
        defaults["standards"] = config.standards
    if config.roadmap is not None:
        defaults[_ROADMAP_KEY] = dataclasses.asdict(config.roadmap)
    if config.forge != DEFAULT_FORGE_NAME:
        # Only a forge that is *not* the default is offered back. `forge` is
        # resolved rather than nullable, so a manifest declaring `github` is
        # indistinguishable here from one declaring nothing — and offering the
        # default back to every repo would make an otherwise unchanged re-run
        # write a key nobody asked for, which is 034 FR-005's complaint exactly.
        # The cost is narrow and in the safe direction: a manifest that spells
        # out the default loses that spelling on a re-run; one that names any
        # other forge keeps it.
        defaults["forge"] = config.forge
    return defaults


#: `safe_dump` closes a document whose root is a *scalar* with an explicit
#: end-of-document marker — `1\n...\n`, `main\n...\n`. Collections do not get
#: one. Left in, it reached the terminal as part of the offered default and the
#: first questions of `ergane init` read `schema version [1\n...]:` and
#: `landing branch [main\n...]:`.
_YAML_DOCUMENT_END = "\n..."


def _yaml_repr(value: Any) -> str:
    """Render a value back to YAML for use as a default string.

    The result is round-tripped: pressing Enter feeds this text back through
    `yaml.safe_load`, so dropping the marker has to leave a document that still
    loads to the same value. It does — `...` closes a document that is already
    complete, and `safe_load("1")` and `safe_load("1\\n...")` are both `1`.
    """
    if value is None:
        return ""
    text = yaml.safe_dump(value, default_flow_style=False).strip()
    if text.endswith(_YAML_DOCUMENT_END):
        text = text[: -len(_YAML_DOCUMENT_END)].rstrip()
    return text


def _build_defaults(repo_root: Path) -> dict[str, Any]:
    """Return a fully populated, valid manifest used to seed the interview."""
    existing = _load_existing_defaults(repo_root)
    gate_default = _default_gate_command(repo_root)
    defaults: dict[str, Any] = {
        "version": existing.get("version", _SUPPORTED_VERSION),
        "runtime": existing.get("runtime", _PLACEHOLDERS["runtime"]),
        "gates": existing.get("gates", ({"test": gate_default.split(":", 1)[1].strip().strip('"')} if gate_default else _PLACEHOLDERS["gates"])),
        "landing_branch": existing.get("landing_branch", _PLACEHOLDERS["landing_branch"]),
    }
    if "timeouts" in existing:
        defaults["timeouts"] = existing["timeouts"]
    if "standards" in existing:
        defaults["standards"] = existing["standards"]
    if "roadmap" in existing:
        defaults[_ROADMAP_KEY] = existing[_ROADMAP_KEY]
    if "forge" in existing:
        defaults["forge"] = existing["forge"]
    return defaults


def _ask_for_key(
    key: str,
    *,
    default_value: Any,
    manifest_values: dict[str, Any],
    prompter: Any,
) -> Any:
    """Ask the operator for one key, re-asking until `parse_factory_config` accepts it.

    Empty answers for optional keys (`timeouts`, `standards`) mean "omit".
    Required keys fall back to the default when an empty answer is given.
    """
    prompt = _PROMPTS[key]
    optional = key in _OPTIONAL_KEYS
    default_text = _yaml_repr(default_value) if default_value is not None else ""
    error: str | None = None

    while True:
        answer = prompter.ask(prompt, default=default_text, error=error)
        if optional and answer.strip() == "":
            return None

        candidate = dict(manifest_values)
        try:
            parsed = yaml.safe_load(answer)
        except yaml.YAMLError as exc:
            error = f"not valid YAML: {exc}"
            continue

        if parsed is None and not optional:
            # Empty answer for a required key means "accept default".
            parsed = default_value

        candidate[key] = parsed
        text = _render_manifest(candidate)
        try:
            parse_factory_config(text, source=MANIFEST_NAME)
        except Exception as exc:
            error = str(exc)
            continue
        return parsed


def _render_manifest(values: dict[str, Any]) -> str:
    """Render the in-progress manifest as YAML."""
    ordered: dict[str, Any] = {}
    for key in _TOP_LEVEL_KEYS:
        if key in values and values[key] is not None:
            ordered[key] = values[key]
    return yaml.safe_dump(ordered, sort_keys=False, default_flow_style=False)


def init_command(args: argparse.Namespace) -> int:
    """Run the interview and write the scaffold — or, with `--check`, only judge.

    `--check` short-circuits before any question is asked and before any file is
    touched: it is the judging half of init, and its exit code is the contract
    (0 when every finding passes, non-zero when any fails).
    """
    repo_root = resolve_repo_root(args.path)

    if getattr(args, "check", False):
        return run_check(repo_root)

    defaults = _build_defaults(repo_root)

    # Seed the in-progress manifest with placeholders/defaults so the first
    # question can already be validated against the full parser.
    manifest_values: dict[str, Any] = {
        key: defaults[key]
        for key in _TOP_LEVEL_KEYS
        if key in defaults
    }

    prompter = _prompter()

    for key in _TOP_LEVEL_KEYS:
        default_value = manifest_values.get(key)
        value = _ask_for_key(
            key,
            default_value=default_value,
            manifest_values=manifest_values,
            prompter=prompter,
        )
        if value is None:
            manifest_values.pop(key, None)
        else:
            manifest_values[key] = value

    # The slug is declared by the operator and lives in the engine's registry,
    # never in the manifest: it is what the engine calls this repo, not what the
    # repo declares about itself.
    slug = _ask_for_slug(repo_root, prompter=prompter)

    text = _render_manifest(manifest_values)
    _write_scaffold(repo_root, text)

    registration = _register(slug, repo_root)

    # The scheduler, before wiring: a GitHub refusal must not cost the repo the
    # thing that makes a `ready` spec dispatch, and an unreachable control plane
    # must not cost it the wiring (FR-017).  Neither step can abort the other.
    schedule_line = _schedule(repo_root, slug)

    # Wiring runs last, after the repo-local half is complete and recorded, so a
    # refusal from GitHub's side never costs the operator the scaffold.
    wiring_lines = _wire(
        repo_root, manifest_values, requested=bool(getattr(args, "wire", False))
    )

    print(f"joined {repo_root.resolve()} as slug '{slug}'")
    print("written:")
    print(f"  {repo_root / MANIFEST_NAME}")
    print(f"  {repo_root / '.gitignore'}")
    print(f"  {repo_root / RUNTIME_ROOT}")
    print(_registration_line(registration))
    print(schedule_line)
    for line in wiring_lines:
        print(line)
    print("next, run:")
    print(f"  git -C {repo_root.resolve()} add {_paths_to_commit(repo_root)}")
    print(f"  git -C {repo_root.resolve()} commit -m \"join ergane\"")

    # FR-010: a full init ends by executing the check, so readiness is judged at
    # the operator's terminal rather than discovered by the factory's first
    # dispatch.  Its verdict is *reported*, not returned: the scaffold and the
    # registry entry succeeded, and a merge queue nobody has wired yet (US3) or
    # an unreachable control plane (FR-017) must not read as init having failed.
    # `ergane init --check` is the door whose exit code is the verdict.
    print()
    run_check(repo_root)

    return EXIT_OK


def _paths_to_commit(repo_root: Path) -> str:
    """The paths the operator is told to stage — the workflow only if it exists."""
    paths = ["ergane.yaml", ".gitignore", str(RUNTIME_ROOT)]
    if (repo_root / wiring.WORKFLOW_PATH).is_file():
        paths.append(str(wiring.WORKFLOW_PATH))
    return " ".join(paths)


def _wire(
    repo_root: Path, manifest_values: dict[str, Any], *, requested: bool
) -> list[str]:
    """The forge half of init: opt-in, idempotent, and reported line by line.

    A flag rather than a further interview question, so a repo whose forge side
    is already governed is never asked; plain `ergane init` names the flag
    instead.

    The CI half is written before the forge is asked anything, because it needs
    no network: an operator refused at the forge boundary still leaves with the
    file the manual steps tell them to commit.
    """
    if not requested:
        return [
            "github wiring: not attempted — re-run with `ergane init --wire` to",
            "  queue the landing branch and require one check per declared gate",
        ]

    gates = dict(manifest_values.get("gates") or {})
    landing_branch = str(manifest_values.get("landing_branch") or "")

    lines = ["wiring:"]
    lines.extend(format_step(wiring.scaffold_gates_workflow(repo_root, gates)))

    try:
        # 049 US4: wiring is a forge operation, so this asks whichever forge the
        # repository is on rather than reaching past the seam for one forge's
        # client. The scaffolded workflow above stays on this side of it: it is a
        # write into the operator's own tree, needs no network, and is written
        # first on purpose — an operator refused at the forge still leaves with
        # the file the manual steps tell them to commit.
        steps = _forge_factory(repo_path=str(repo_root)).apply_landing_policy(
            landing_branch, list(gates)
        )
    except WiringRefused as refusal:
        raise OperatorError(
            "\n".join(
                [
                    str(refusal),
                    "",
                    "the repo-local half of init is complete and unchanged in "
                    f"{repo_root.resolve()}:",
                    *lines[1:],
                ]
            ),
            code=EXIT_USER,
        ) from None

    for step in steps:
        lines.extend(format_step(step))
    return lines


def _schedule(repo_root: Path, slug: str) -> str:
    """Create or reconcile this repo's roadmap schedule, and report one line.

    Never raises (FR-017).  The manifest is re-read from disk rather than taken
    from the interview's values, so what steers the schedule is exactly what the
    operator will commit.
    """
    try:
        config = load_factory_config(repo_root / MANIFEST_NAME)
    except FactoryConfigError as problem:
        return roadmap_schedule.format_step(
            roadmap_schedule.ScheduleStep(
                roadmap_schedule.FAILED,
                roadmap_schedule.schedule_id_for(slug),
                f"the manifest just written did not load: {problem}",
            )
        )
    desired = roadmap_schedule.desired_for_repo(
        slug=slug, repo_root=repo_root, config=config
    )
    return roadmap_schedule.format_step(roadmap_schedule.apply_schedule(desired))


def _ask_for_slug(repo_root: Path, *, prompter: Any) -> str:
    """Ask for the repo's slug, re-asking until it is a usable namespace token.

    The default is the slug this repo is already registered under, if any, so a
    re-run edits rather than clobbers (FR-005); otherwise it is the *normalized*
    directory name, proposed rather than applied — a directory called `My App`
    yields the proposal `my-app`, and the operator confirms it like every other
    declaration (D-009).
    """
    try:
        known = registry.load_registry().for_path(repo_root)
    except registry.RegistryError as problem:
        raise OperatorError(str(problem), code=EXIT_USER) from None
    default = known.slug if known is not None else registry.normalize_slug(repo_root.name)
    error: str | None = None

    while True:
        answer = prompter.ask("repo slug", default=default, error=error).strip()
        candidate = answer or default
        if registry.is_valid_slug(candidate):
            return candidate
        error = str(registry.InvalidSlug(candidate))


def _register(slug: str, repo_root: Path) -> registry.Registration:
    """Record the repo in the engine's registry, refusing a slug collision.

    Registration runs *after* the scaffold is written, so the repo-local work an
    operator can still use is never lost to a refusal from the engine's side —
    the refusal says so rather than leaving them to guess.
    """
    try:
        return registry.register(slug, repo_root)
    except registry.SlugCollision as collision:
        raise OperatorError(
            f"{collision}; the scaffold in {repo_root} was written and is unchanged",
            code=EXIT_USER,
        ) from None
    except registry.RegistryError as error:
        raise OperatorError(str(error), code=EXIT_USER) from None
    except LockUnavailable as error:
        raise OperatorError(
            f"another `ergane` command holds the registry lock "
            f"{lock_path_for(error.target)} (waited {error.timeout_s:g}s); "
            "the scaffold was written — re-run init to finish registering",
            code=EXIT_USER,
        ) from None


def _registration_line(registration: registry.Registration) -> str:
    """One line saying what the registry did, including when it did nothing."""
    entry = registration.entry
    if registration.previous_slug is not None:
        return (
            f"registered: {entry.path} moved from slug "
            f"'{registration.previous_slug}' to '{entry.slug}'"
        )
    if registration.changed:
        return f"registered: '{entry.slug}' -> {entry.path}"
    return f"registered: '{entry.slug}' -> {entry.path} (already recorded)"


def _write_scaffold(repo_root: Path, manifest_text: str) -> None:
    """Write exactly the declared files and nothing else."""
    manifest_path = repo_root / MANIFEST_NAME
    manifest_path.write_text(manifest_text, encoding="utf-8")

    gitignore = repo_root / ".gitignore"
    line = f"{RUNTIME_ROOT}/\n"
    if gitignore.is_file():
        current = gitignore.read_text(encoding="utf-8")
        if f"{RUNTIME_ROOT}/" not in current.splitlines():
            gitignore.write_text(current.rstrip("\n") + "\n" + line, encoding="utf-8")
    else:
        gitignore.write_text(line, encoding="utf-8")

    runtime_root = repo_root / RUNTIME_ROOT
    runtime_root.mkdir(exist_ok=True)


# --- US4: readiness is judged, not assumed ------------------------------------


def _git_read(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """One *read-only* git query; a non-zero status is an answer, not an error.

    Nothing reached from here may create a ref, a file or an index entry:
    `--check` reports on a repository, it does not repair one.
    """
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def resolve_repo_runtime_root(repo_root: Path) -> tuple[str, bool]:
    """Which runtime root *this repository* has, and whether it is the legacy one.

    Deliberately not `worktree.resolve_factory_root()`: that resolver **creates**
    `.ergane/` when neither name exists — the one thing a check must never do —
    and it resolves against the *process's* cwd and the worker's `ERGANE_ROOT`
    override, so from anywhere but the repo it answers about the wrong tree.
    The policy and the constants here are still its: `.ergane/` wins, a lone
    `.factory/` is honoured (trap 12), neither means the name init would write.
    """
    if (repo_root / DEFAULT_RUNTIME_ROOT).is_dir():
        return str(DEFAULT_RUNTIME_ROOT), False
    if (repo_root / LEGACY_FACTORY_ROOT).is_dir():
        return str(LEGACY_FACTORY_ROOT), True
    return str(DEFAULT_RUNTIME_ROOT), False


def _git_ignores(repo_root: Path, path: str) -> bool:
    """Whether git's ignore *rules* exclude `path` — asked, not text-searched.

    `--no-index` asks about the rules rather than what is already tracked, which
    is what a remedy naming a `.gitignore` line can act on.
    """
    completed = _git_read(repo_root, "check-ignore", "--quiet", "--no-index", "--", path)
    return completed.returncode == 0


def _git_has_branch(repo_root: Path, branch: str) -> bool:
    """Whether `refs/heads/<branch>` exists.  Reads a ref; never creates one."""
    completed = _git_read(
        repo_root, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"
    )
    return completed.returncode == 0


def _registry_facts(repo_root: Path) -> tuple[Path, str | None, str | None]:
    """The registry path, the slug pointing here, and why it could not be read.

    An unparseable registry is a fact, not a crash: one failing finding is what
    lets every other finding still render.
    """
    registry_path = registry.resolve_registry_path()
    try:
        entry = registry.load_registry().for_path(repo_root)
    except registry.RegistryError as problem:
        return registry_path, None, str(getattr(problem, "problem", problem))
    return registry_path, (entry.slug if entry is not None else None), None


def _control_plane_facts() -> tuple[tuple[Finding, ...], str | None]:
    """033's probe findings, or the reason there are none.

    Every exception is caught, including the ones 033's registry does not catch
    for itself — an unreadable control-plane config raises before the first probe
    runs.  An escape here would abort the render: exactly what "no failure
    masking another" forbids.
    """
    try:
        findings, _exit_code = _controlplane_probe()
    except Exception as error:  # noqa: BLE001 - a probe must never abort the report
        return (), f"{type(error).__name__}: {error}"
    return tuple(findings), None


def _schedule_facts(
    repo_root: Path, slug: str | None, config: FactoryConfig | None
) -> dict[str, Any]:
    """This repo's schedule facts, as `InitFacts` keyword arguments.

    Two things make the answer unknowable rather than negative.  Without a
    registry entry there is no slug, and the slug is the whole identifier;
    without a loadable manifest there is nothing to compare a live schedule
    against.  Each already has its own failing finding, so this one names the
    cause and points at it rather than repeating the remedy.
    """
    if slug is None:
        return {
            "schedule_error": (
                "no entry in the engine registry names this repository, and the "
                "slug is what identifies its schedule (see the registry_entry "
                "finding)"
            )
        }

    schedule_id = roadmap_schedule.schedule_id_for(slug)
    if config is None:
        return {
            "schedule_id": schedule_id,
            "schedule_error": (
                "this repository's manifest did not load, so the schedule has "
                "nothing to be judged against (see the factory_yaml finding)"
            ),
        }

    desired = roadmap_schedule.desired_for_repo(
        slug=slug, repo_root=repo_root, config=config
    )
    try:
        live = roadmap_schedule.read_schedule(schedule_id)
    except roadmap_schedule.ScheduleUnavailable as unavailable:
        return {"schedule_id": schedule_id, "schedule_error": str(unavailable)}

    if live is None:
        return {"schedule_id": schedule_id}
    return {
        "schedule_id": schedule_id,
        "schedule_present": True,
        "schedule_paused": live.paused,
        "schedule_drift": roadmap_schedule.disagreements(desired, live),
    }


def gather_init_facts(repo_root: Path) -> InitFacts:
    """Read the facts init created, so `evaluate_repo` can judge them (FR-010).

    Gathering only: the judgment lives in `factory/mergequeue/onboard.py` beside
    the 003 checks, because a second place deciding what "ready" means is a
    second place that can drift.
    """
    root_name, is_legacy = resolve_repo_runtime_root(repo_root)
    registry_path, slug, registry_error = _registry_facts(repo_root)

    manifest_path, _manifest_name = resolve_manifest_path(repo_root)
    config: FactoryConfig | None
    try:
        config = load_factory_config(manifest_path)
    except FactoryConfigError:
        # The manifest's own finding carries the loader's error; here the
        # consequence is that the landing branch cannot be judged, and an
        # unjudgeable check is reported rather than skipped.
        config = None
    landing_branch = config.landing_branch if config is not None else None

    control_plane, control_plane_error = _control_plane_facts()

    return InitFacts(
        repo_root=str(repo_root),
        runtime_root=root_name,
        runtime_root_is_legacy=is_legacy,
        runtime_root_ignored=_git_ignores(repo_root, f"{root_name}/"),
        gitignore=str(repo_root / ".gitignore"),
        registry_path=str(registry_path),
        registry_slug=slug,
        registry_error=registry_error,
        landing_branch=landing_branch,
        landing_branch_exists=(
            landing_branch is not None and _git_has_branch(repo_root, landing_branch)
        ),
        control_plane=control_plane,
        control_plane_error=control_plane_error,
        **_schedule_facts(repo_root, slug, config),
    )


def check_repo(repo_root: str | Path) -> TargetRepoProfile:
    """Judge one repository's readiness through the shared judgment (FR-010).

    `onboard_target_repo` is the seam both doors already share, so the 003 facts
    are gathered by the code that already knows how and init's ride beside them.
    The `@activity.defn` wrapper is deliberately not what is called: it cannot
    run outside a worker (plan trap 2).
    """
    from factory.activities.merge_activities import onboard_target_repo

    root = Path(repo_root).resolve()
    facts = gather_init_facts(root)
    forge = _forge_factory(repo_path=str(root))
    return onboard_target_repo(forge, str(root), init_facts=facts)


def render_check(profile: TargetRepoProfile, repo_root: Path, manifest_name: str) -> str:
    """One line per finding, pass and fail alike.

    Passing findings print too: "checked" and "passed" are different claims, and
    a failures-only report cannot make the first.
    """
    lines = [f"ergane readiness for {repo_root} ({manifest_name})"]
    failed = 0
    for finding in profile.findings:
        mark = "PASS" if finding.passed else "FAIL"
        if not finding.passed:
            failed += 1
        lines.append(f"  [{mark}] {finding.check}: {finding.detail}")

    total = len(profile.findings)
    if failed:
        lines.append(f"{failed} of {total} checks failed")
    else:
        lines.append(f"all {total} checks passed")
    return "\n".join(lines)


def run_check(repo_root: Path) -> int:
    """Render the report; non-zero on any failing finding, 0 when all pass."""
    profile = check_repo(repo_root)
    _manifest_path, manifest_name = resolve_manifest_path(repo_root)
    print(render_check(profile, repo_root, manifest_name))
    return EXIT_OK if profile.passed else EXIT_USER
