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
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from typing import Any, Callable

import yaml

from factory import registry
from factory.cli.errors import EXIT_OK, EXIT_USER, OperatorError
from factory.locking import LockUnavailable, lock_path_for
from factory.verify.factory_yaml import (
    MANIFEST_NAME,
    _SUPPORTED_VERSION,
    _TOP_LEVEL_KEYS,
    load_factory_config,
    parse_factory_config,
)

#: Runtime root created inside the target repo.
RUNTIME_ROOT = Path(".ergane")

#: Module-level seam so tests can inject a scripted prompter.
_prompter_factory: Callable[[], Any] | None = None


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
}

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
    return defaults


def _yaml_repr(value: Any) -> str:
    """Render a value back to YAML for use as a default string."""
    if value is None:
        return ""
    return yaml.safe_dump(value, default_flow_style=False).strip()


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
    optional = key in ("timeouts", "standards")
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
    """Run the interview and write the scaffold."""
    repo_root = resolve_repo_root(args.path)

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

    print(f"joined {repo_root.resolve()} as slug '{slug}'")
    print("written:")
    print(f"  {repo_root / MANIFEST_NAME}")
    print(f"  {repo_root / '.gitignore'}")
    print(f"  {repo_root / RUNTIME_ROOT}")
    print(_registration_line(registration))
    print("next, run:")
    print(f"  git -C {repo_root.resolve()} add ergane.yaml .gitignore .ergane")
    print(f"  git -C {repo_root.resolve()} commit -m \"join ergane\"")

    return EXIT_OK


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
    except registry.RegistryError as error:
        raise OperatorError(str(error), code=EXIT_USER) from None
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
