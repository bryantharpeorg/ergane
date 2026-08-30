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

104's US6 adds an act that runs only where it applies. On a host whose engine
runs in the container tier, joining a repo is not finished when the registry row
is written: the engine mounts each repo at its own path, and one it does not
mount is one its supervisor refuses to start against (088 FR-009). So init
regenerates that mount list and re-ups the engine, immediately after the
registry row and from it. The generated project on disk is the only record of
that tier (104 R1), so a host without one is not probed and not told; and the
step never raises, for `_schedule`'s reason. `--check` judges the same fact
through `gather_init_facts`, as the `engine_container` finding.

064's US2 adds the question that comes before all of it. Init resolves upward,
so a directory that is not itself a repository root enrols the repository it
happens to sit inside — and the near-miss that produced the spec was a scratch
directory beneath a checkout holding twenty-five unrelated projects. The root is
now named and consented to before the interview asks anything
(`_confirm_resolved_root`), refused rather than assumed under
`--non-interactive`, and reported by `--check` as a finding rather than only in
the header line the reporter happened to read. The root invocation gains no
question at all: a prompt in the common case is a prompt operators learn to
answer without reading.
"""

from __future__ import annotations

import argparse
import dataclasses
import subprocess
from pathlib import Path
from typing import Any, Callable, Mapping

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

#: When True, the default `_TerminalPrompter` refuses on EOF instead of silently
#: accepting defaults. Set by `init_command` from the `--non-interactive` flag so
#: the distinguishing signal is the flag, not the state of stdin (US2, FR-005).
_require_explicit_consent: bool = False

#: Sentinel returned by `_init_default` when a manifest key has no safe default.
#: A non-interactive path that omits such a field must refuse before writing
#: anything (FR-004).
_NO_DEFAULT = object()


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


def _default_project_writer(project: Any) -> Any:
    """Write the engine container's regenerated project (104 R11's writer).

    Imported late, like every other outward reach in this file: a `--check` run
    on a host with no container tier must not pay for the module, and nothing
    here may import the supervision tier at module scope.
    """
    from factory.supervision.container_manifest import write_project

    return write_project(project)


#: Seam: how `ergane init` writes the regenerated engine container project.
#: Rebound in tests, which then read back what the mount list became.
_project_writer: Callable[[Any], Any] = _default_project_writer


def _default_compose_runner(argv: Any) -> Any:
    """Run one `docker compose` command — 104-US5's own runner, not a second one.

    Reaching for its private name is deliberate and is the argument
    `container_manifest.py` makes for importing `units._digest`: one compose
    runner has one behaviour, and the behaviour that matters here (stderr
    merged into the output, because compose says most of what matters there) is
    not one this file should re-decide.
    """
    from factory.supervision.container_engine import _run_compose

    return _run_compose(argv)


#: Seam: how `ergane init` reconciles the engine container.  Rebound in tests,
#: so no test starts a container or contacts a daemon (104 trap 11).
_compose_runner: Callable[[Any], Any] = _default_compose_runner


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
        except (EOFError, ValueError, RuntimeError):
            # US2/FR-005: a closed stdin is not consent unless the operator
            # explicitly asked for non-interactive mode.  A closed `StringIO`
            # raises `ValueError`; a real closed stdin raises `EOFError` or
            # `RuntimeError` depending on the interpreter path.
            if _require_explicit_consent:
                raise OperatorError(
                    f"stdin is closed; cannot answer question: {prompt}",
                    code=EXIT_USER,
                ) from None
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


def resolve_invocation_dir(path: str | Path | None) -> Path:
    """The directory the operator *pointed at*, resolved — never walked up from.

    Reads its argument exactly as `resolve_repo_root` does, so the two answers
    are comparable: bare `ergane init` and `ergane init .` both mean the working
    directory, and `ergane init <path>` means that path. The comparison between
    the two is 064/US2's whole subject — a resolved root that differs from this
    is a repository the operator did not name (FR-005).
    """
    return (Path(path) if path else Path.cwd()).resolve()


def _confirmation_question(repo_root: Path, invoked_from: Path) -> str:
    """The question, with the resolved root inside it rather than above it.

    Interpolated rather than referred to ("the root above"): the operator reads
    the path in the line they are answering, which is the difference between
    catching this and the near-miss that produced the spec.
    """
    return (
        f"{invoked_from} is not a repository root — enrol {repo_root} instead? (y/N)"
    )


#: What counts as consent. Anything else — including the empty answer an
#: operator presses enter for — declines, because 060 settled that an absent
#: answer is not an answer and a blank one is no more of one (FR-007).
_CONSENT = ("y", "yes")


def _confirm_resolved_root(
    repo_root: Path,
    invoked_from: Path,
    *,
    prompter: Any,
    non_interactive: bool,
) -> None:
    """Name the repository init resolved, and require consent before enrolling it.

    064/US2. `ergane init` run from a scratch directory beneath a repository
    walked up out of it and offered to enrol the parent; the path was printed,
    and the reporter happened to read it. The unnoticed outcome is twenty-five
    unrelated projects joined as one managed repository.

    Two cases reach here and both are the same comparison: a directory that is
    not itself a repository, and a subdirectory of one. The third — a linked
    worktree, which resolves elsewhere *legitimately* — never does:
    `resolve_repo_root` has already refused it by name (trap 6), so "resolved
    somewhere else because worktree" and "resolved somewhere else because we
    walked up" are distinguished before this is called rather than here.

    Called before the interview and before `_build_defaults`, so a decline costs
    the operator nothing and writes nothing (FR-005). The root invocation — the
    overwhelmingly normal one — returns without asking anything at all (FR-006,
    trap 5): a prompt there teaches operators to press a key without reading.
    """
    if invoked_from == repo_root:
        return

    if non_interactive:
        # FR-007, and 060's rule in the same words: silence is not consent. The
        # remedy names the invocation that *is* unambiguous, so an automated
        # caller has something to change rather than a flag to drop.
        raise OperatorError(
            f"init resolved the repository root to {repo_root}, which is not the "
            f"directory it was invoked from ({invoked_from}); --non-interactive "
            "has nobody to ask, and an absent answer is not consent — run "
            f"`ergane init {repo_root}` to name the repository you mean, or "
            "re-run without --non-interactive to confirm it",
            code=EXIT_USER,
        )

    print(f"init resolved the repository root to {repo_root}, walking up from {invoked_from}")
    answer = prompter.ask(
        _confirmation_question(repo_root, invoked_from), default="n"
    )
    if answer.strip().lower() not in _CONSENT:
        raise OperatorError(
            f"declined: {repo_root} was not enrolled and nothing was written — "
            f"run `ergane init {repo_root}` to enrol it, or run init from the "
            "repository you meant",
            code=EXIT_USER,
        )


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
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        dest="non_interactive",
        help=(
            "use documented defaults for every question; fields with no safe "
            "default cause a refusal"
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
    "writes": (
        "gates that write on purpose (YAML mapping of gate name to true, "
        "optional)"
    ),
    # 092/US2: the size above which this repository refuses to build a story.
    # Optional, and the floor the parser enforces is the judge's attention
    # budget, so the question names bytes rather than inviting a round number.
    "diff_refusal_bytes": (
        "diff refusal threshold in bytes — the size above which a story is "
        "refused unjudged (optional)"
    ),
}

#: Keys an empty answer omits rather than defaults.  Each is additive: a repo
#: that declares none of them is a complete manifest.
_OPTIONAL_KEYS = (
    "timeouts",
    "standards",
    "roadmap",
    "forge",
    "writes",
    "diff_refusal_bytes",
)

#: Spelled as a constant only because `tests/test_ergane_cli.py`'s guard against
#: a hardcoded list of CLI noun names matches a bracket followed by any quoted
#: noun name, and this manifest key shares its word with the `roadmap` noun.  A
#: subscript by literal would trip it; do not inline this back.
_ROADMAP_KEY = "roadmap"

#: Placeholder values that keep a partial manifest valid for full-parser checks.
#: `landing_branch` is the *last* resort rather than the answer: see
#: `_default_landing_branch`.
#:
#: `gates` used to be here as `{"test": "true"}` and is not a placeholder — it
#: is written into the manifest, committed, and executed by every node this repo
#: dispatches. `true` exits 0 having run nothing, so a repository initialised
#: without a tree that suggested a command got a gate that could not fail, and
#: `ergane init --check` reported it as a passing gate. 061 US3-S5: a value the
#: code calls a placeholder may not silently become a live gate. See
#: `_UNDECLARED_GATE_COMMAND` for the value that replaced it and why it is not
#: here.
_PLACEHOLDERS: dict[str, Any] = {
    "runtime": "bwrap",
    "landing_branch": "main",
}

#: The gate command a repository gets when neither its existing manifest nor its
#: tree names one (061 FR-010).
#:
#: The choice is between a gate that cannot fail and a gate that cannot pass,
#: and only one of them is safe to be wrong about. `true` says "verified"
#: about work nothing looked at; this says "not configured" and says it in the
#: gate's own output, where the operator is already reading when a node fails.
#: It is deliberately not a placeholder and deliberately not silent: a gate is
#: the thing that decides whether an agent's work lands, so a repository whose
#: operator has not said what green means declares that fact rather than a
#: value that resembles an answer.
#:
#: Kept short on purpose. This string is offered back to the operator as the
#: interview's default for `gates`, and `_yaml_repr` renders it through
#: `yaml.safe_dump`, which folds a scalar past 80 columns onto a second line —
#: 051's `test_the_interview_offers_no_multi_line_default` is what says so, and
#: `test: '<command>'` is the whole line that has to fit. Lengthen the message
#: and that test goes red rather than the operator finding out.
_UNDECLARED_GATE_COMMAND = (
    'echo "ergane: declare gates.test in ergane.yaml" >&2; exit 1'
)

#: What `git rev-parse --abbrev-ref HEAD` answers on a detached HEAD. Git
#: refuses to create a branch by this name, so it can only ever be the sentinel.
_DETACHED_HEAD = "HEAD"


def _current_branch(repo_root: Path) -> str | None:
    """The branch this repository is on, or None when it is not on one.

    Three HEAD states, measured against git 2.43 rather than assumed, because
    the two obvious readings disagree on two of them:

        state                     symbolic-ref --short HEAD   rev-parse --abbrev-ref HEAD
        on `master`, committed    master              rc 0    master              rc 0
        empty, no commit          master              rc 0    (fatal)             rc 128
        detached HEAD             (fatal)             rc 128  HEAD                rc 0

    `rev-parse` is used because its failure *is* "no resolvable HEAD", which is
    exactly the case FR-002 sends back to the literal. `symbolic-ref` would name
    the unborn branch of an empty repository — a branch that does not exist and
    that the operator has not committed to — and 051 US1-S3 says an empty
    repository gets the literal instead.

    A read, never a write: `_git_read` is the same helper `--check` uses, for
    the same reason.
    """
    completed = _git_read(repo_root, "rev-parse", "--abbrev-ref", "HEAD")
    if completed.returncode != 0:
        return None
    branch = completed.stdout.strip()
    if not branch or branch == _DETACHED_HEAD:
        return None
    return branch


def _default_landing_branch(repo_root: Path) -> str:
    """The landing branch to *offer*: this repository's own, or the literal.

    051 US1. `git init` on a stock machine creates `master`, and git 2.47 still
    defaults `init.defaultBranch` to that; the interview offered `main` anyway
    and the readiness check then failed on a fact the tool already had in hand
    when it asked. A machine that sets `init.defaultBranch = main` made the
    literal accidentally correct, which is why this survived so long.

    An offer, not a verdict (FR-005): `onboard._landing_branch_finding` is still
    the only thing that says whether the branch exists, and on an empty
    repository — which has no refs at all — it will fail whatever is offered.
    """
    return _current_branch(repo_root) or _PLACEHOLDERS["landing_branch"]


def _default_gates(repo_root: Path) -> dict[str, str]:
    """The gates to offer a repository that declares none yet.

    A reading of the tree where there is one to make, and `_UNDECLARED_GATE_COMMAND`
    where there is not. Returns the mapping the manifest actually carries rather
    than a rendered YAML line: the caller used to receive `'test: "uv run pytest
    -q"'` and take the value back apart with `split(":", 1)`, which meant the one
    place that decided this repository's gate could not state it as data.
    """
    if (repo_root / "pyproject.toml").is_file():
        return {"test": "uv run pytest -q"}
    return {"test": _UNDECLARED_GATE_COMMAND}


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
    if config.writes:
        # Offered back so a re-run reconciles the declaration rather than
        # dropping it: a repo whose lockfile gate is declared would otherwise
        # come out of `ergane init` with that gate refused again (084 FR-009).
        defaults["writes"] = dict(config.writes)
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
    defaults: dict[str, Any] = {
        "version": existing.get("version", _SUPPORTED_VERSION),
        "runtime": existing.get("runtime", _PLACEHOLDERS["runtime"]),
        # An existing manifest's gates win, exactly as `landing_branch`'s do: a
        # re-run reconciles what a repository declared, and a repository that
        # declared `true` keeps it — `ergane init --check` is what now says so
        # (061 FR-008), rather than init rewriting the operator's declaration.
        "gates": existing.get("gates", _default_gates(repo_root)),
        # The repository reading goes *underneath* the existing-manifest
        # preference, never in front of it (051 FR-004): re-running init in a
        # joined repository reconciles what is declared, and must not silently
        # re-point it at whatever branch happens to be checked out.
        "landing_branch": existing.get("landing_branch", _default_landing_branch(repo_root)),
    }
    if "timeouts" in existing:
        defaults["timeouts"] = existing["timeouts"]
    if "standards" in existing:
        defaults["standards"] = existing["standards"]
    if "roadmap" in existing:
        defaults[_ROADMAP_KEY] = existing[_ROADMAP_KEY]
    if "forge" in existing:
        defaults["forge"] = existing["forge"]
    if "writes" in existing:
        defaults["writes"] = existing["writes"]
    return defaults


def _init_default(key: str, repo_root: Path) -> Any:
    """Return the documented default for one manifest key, or `_NO_DEFAULT`.

    This is the shared defaults source for the non-interactive path.  The
    interactive path displays the same values through `_build_defaults`; a field
    whose only safe value is operator-supplied has no default here.
    """
    defaults = _build_defaults(repo_root)
    # Optional keys have a safe default of "absent".
    if key in _OPTIONAL_KEYS:
        return None
    if key in defaults:
        return defaults[key]
    return _NO_DEFAULT


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


class _NonInteractivePrompter:
    """A prompter that returns the documented default for each question.

    Used by `init --non-interactive` so the same interview functions drive the
    non-interactive path (trap 1).  A field with no safe default causes the
    command to refuse before any manifest is written (FR-004).
    """

    def __init__(self, repo_root: Path, reports: list[str]) -> None:
        self._repo_root = repo_root
        self._reports = reports

    def ask(self, prompt: str, *, default: str | None = None, error: str | None = None) -> str:
        if error is not None:
            raise AssertionError(
                f"non-interactive answer was refused by the parser: {error}"
            )
        # Resolve the question from its prompt text.  `_PROMPTS` is keyed by
        # manifest key; find the key whose human prompt matches.
        key: str | None = None
        for k, text in _PROMPTS.items():
            if text == prompt:
                key = k
                break
        # The slug question is not in `_PROMPTS`.
        if key is None and prompt == "repo slug":
            # The default is the normalized directory name or existing registry slug.
            try:
                known = registry.load_registry().for_path(self._repo_root)
            except registry.RegistryError:
                known = None
            default_slug = known.slug if known is not None else registry.normalize_slug(self._repo_root.name)
            self._reports.append(f"applied default: repo slug = \"{default_slug}\"")
            return default_slug
        if key is None:
            raise AssertionError(f"non-interactive prompter does not know prompt: {prompt!r}")
        value = _init_default(key, self._repo_root)
        if value is _NO_DEFAULT:
            raise OperatorError(
                f"non-interactive init cannot answer question: {prompt} "
                "(no safe documented default)",
                code=EXIT_USER,
            )
        if value is None:
            return ""
        rendered = _yaml_repr(value)
        self._reports.append(f"applied default: {key} = {rendered}")
        return rendered


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
    (0 when every finding passes, non-zero when any fails). It carries the
    invocation directory into the report so the root it resolved is a finding
    rather than a header line (064/FR-008).
    """
    global _require_explicit_consent

    repo_root = resolve_repo_root(args.path)
    invoked_from = resolve_invocation_dir(args.path)

    if getattr(args, "check", False):
        return run_check(repo_root, invocation_dir=invoked_from)

    non_interactive = getattr(args, "non_interactive", False)
    _require_explicit_consent = not non_interactive

    reports: list[str] = []
    if non_interactive:
        prompter: Any = _NonInteractivePrompter(repo_root, reports)
    else:
        prompter = _prompter()

    try:
        # 064/US2, first: the repository is named and consented to before the
        # interview asks anything about it, so a decline costs no answers and
        # writes no file.
        _confirm_resolved_root(
            repo_root,
            invoked_from,
            prompter=prompter,
            non_interactive=non_interactive,
        )

        defaults = _build_defaults(repo_root)

        # Seed the in-progress manifest with placeholders/defaults so the first
        # question can already be validated against the full parser.
        manifest_values: dict[str, Any] = {
            key: defaults[key]
            for key in _TOP_LEVEL_KEYS
            if key in defaults
        }

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
    finally:
        # Reset so a subsequent invocation in the same process is not permanently
        # pinned to the last invocation's flag.
        _require_explicit_consent = False

    text = _render_manifest(manifest_values)
    _write_scaffold(repo_root, text)

    for line in reports:
        print(line)

    registration = _register(slug, repo_root)

    # 104/US6: immediately after the registry row, because the two are halves of
    # one fact — the engine knowing this repo exists — and the mount list is
    # regenerated *from* that row.  On a host with no engine container project
    # this is None and nothing happens at all.
    engine_line = _reconcile_engine(repo_root)

    # 050/FR-001: the readability of the control plane is decided *here*, above
    # the one act of init that publishes to shared infrastructure, and handed
    # down.  Every fact needed to refuse was already in hand when the schedule
    # that produced this spec was created — it was simply computed afterwards.
    #
    # 050/FR-006: the readability check runs once per init run and its result is
    # shared between the schedule precondition and the readiness report.  When the
    # control plane is unreadable, the same error string is handed to both, so the
    # probe suite is skipped and no network calls are made for a refusal we
    # already know.
    control_plane_reason = _control_plane_reason()
    schedule_line = _schedule(repo_root, slug, control_plane_reason=control_plane_reason)

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
    if engine_line is not None:
        print(engine_line)
    # US2-S1: the control-plane verdict is reported before the act that depends
    # on it, so the transcript reads as a decision rather than a confession.
    print(_control_plane_verdict_line(control_plane_reason))
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
    # FR-006: reuse the single readability result when it already refuses; when
    # the control plane is readable, the readiness report still runs the probe
    # suite so the operator sees per-subsystem detail.
    run_check(
        repo_root,
        control_plane=((), control_plane_reason) if control_plane_reason is not None else None,
        invocation_dir=invoked_from,
    )

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


def _control_plane_verdict_line(reason: str | None) -> str:
    """One line reporting the control-plane verdict.

    Uses the same error string `_control_plane_facts` already uses for the
    readiness report, so an operator meets one phrasing for the same fact,
    whether it appears above the schedule step or in the final report (FR-003).
    """
    if reason is not None:
        return f"control plane: not readable — {reason}"
    return "control plane: readable"


def _control_plane_reason() -> str | None:
    """Why this host's control-plane config cannot be read, or `None` when it can.

    A file read, not a probe.  The question 050/FR-001 asks is the cheap one —
    does the operator have a control plane at all, the thing `ergane install`
    writes — and it is deliberately not the probe suite: `_control_plane_facts`
    reaches the network, and a precondition that cost a round trip per init
    would be one the next person moved back below the act it guards.

    Every exception is caught and rendered, in the same idiom and the same
    vocabulary `_control_plane_facts` already uses for the readiness report, so
    an operator meets one phrasing rather than two (FR-003).  An escape here
    would cost the repository its scaffold, which is the outcome FR-017 spent a
    whole failure branch avoiding.
    """
    from factory.controlplane.config import load_controlplane_config

    try:
        load_controlplane_config()
    except Exception as error:  # noqa: BLE001 - a precondition must never abort init
        return f"{type(error).__name__}: {error}"
    return None


def _schedule_target() -> str:
    """Which Temporal a schedule from this repository would have reached.

    Named in the refusal on purpose.  FR-001 catches a fresh machine, where
    nothing is listening — it does *not* catch a machine already running a
    control plane on the namespace the fallback happens to pick, which is how
    the schedule this spec was filed for came to exist: an `env -i` init found a
    live namespace nobody had declared, passed every readability check, and
    published into it.  Saying which namespace, and which source chose it, is
    what turns that from a bare success into a visible mismatch.

    Resolution itself refuses on a config it cannot use, so the answer is
    guarded: this is reached only when the control plane is already unreadable,
    and a refusal message is the last place that may raise.
    """
    try:
        from factory.controlplane.resolve import resolve_temporal_target

        target = resolve_temporal_target()
    except Exception as error:  # noqa: BLE001 - see above; never raises
        return f"a Temporal that could not be resolved ({type(error).__name__}: {error})"
    return (
        f"Temporal at {target.address} in namespace '{target.namespace}' "
        f"({target.namespace_source})"
    )


def _schedule(repo_root: Path, slug: str, *, control_plane_reason: str | None) -> str:
    """Create or reconcile this repo's roadmap schedule, and report one line.

    Never raises (FR-017).  The manifest is re-read from disk rather than taken
    from the interview's values, so what steers the schedule is exactly what the
    operator will commit.

    This is the only act of `ergane init` whose blast radius reaches past the
    repository being joined, and the only one another person can observe — so it
    is the only one with a precondition (050/FR-001).  `control_plane_reason` is
    that precondition's answer, computed once by the caller rather than here so
    the readiness report can share the single evaluation (FR-006).  A refusal is
    a *failed step*, never an exception: the second instance of a branch this
    function already had, because a control plane that is not there must not cost
    the operator the scaffold, the registry row or the wiring (FR-002).
    """
    if control_plane_reason is not None:
        return roadmap_schedule.format_step(
            roadmap_schedule.ScheduleStep(
                roadmap_schedule.FAILED,
                roadmap_schedule.schedule_id_for(slug),
                f"refused: the control plane could not be read, so no schedule "
                f"was created — {control_plane_reason} — and `ergane install` is "
                f"what creates it; a schedule for this repository would "
                f"otherwise have gone to {_schedule_target()}",
            )
        )
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


def _engine_compose_document(compose_path: Path) -> dict[str, Any]:
    """The installed compose, parsed. Raises on a file that is not a mapping —
    a project nobody can read is a fact both callers below must report, and
    neither may guess at it."""
    document = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{compose_path} does not parse as a compose project")
    return document


def _engine_repo_sources(compose_path: Path) -> set[Path]:
    """Every repository the installed project mounts, read back from its own
    `x-ergane-repos` list — the block `render_compose` emits as `[]` rather than
    a bare key precisely so this read has something to parse."""
    from factory.supervision.container_project import REPO_MOUNT_KEY

    declared = _engine_compose_document(compose_path).get(REPO_MOUNT_KEY) or ()
    return {Path(str(mount["source"])).resolve() for mount in declared}


def _installed_confinement(compose_path: Path) -> str:
    """Which confinement variant the installed project asks Docker for.

    Read back rather than defaulted.  An operator who declined the AppArmor
    profile at install has a config-F project, and regenerating it as config G
    would ask Docker for a profile this host never loaded — so the engine `ergane
    init` was reconciling would refuse to start, and the operator would have lost
    it to the one command that was supposed to be safe.  Config F is a state
    somebody chose, not a mistake to be corrected behind their back.
    """
    from factory.supervision import container_project as project_module

    service = (
        _engine_compose_document(compose_path).get("services") or {}
    ).get(project_module.SERVICE_NAME) or {}
    declared = set(service.get(project_module.SECURITY_OPT_KEY) or ())
    relaxed = set(project_module.UNCONFINED_SECURITY_OPT) - set(
        project_module.CONFINED_SECURITY_OPT
    )
    if declared & relaxed:
        return project_module.CONFINEMENT_UNCONFINED
    return project_module.CONFINEMENT_PROFILE


def _reconcile_engine(repo_root: Path) -> str | None:
    """Regenerate the engine container's mount list and reconcile the engine.

    Returns the one line the report prints, or `None` on a host that does not
    run the container tier — the generated project on disk *is* that record
    (104 R1), so a systemd-tier host is not probed, not asked and not told about
    a tier it does not have.

    Never raises, for `_schedule`'s reason (FR-017): the scaffold and the
    registry row are already the operator's, and an engine that could not be
    reconciled is a failed *step*, not a failed init.  `ergane install` is the
    verb that converges, and every failure line names it.

    Regenerate first, then `up`.  `docker compose up -d` reconciles rather than
    duplicating, so it is the whole of "the engine picks the repo up" — and it
    reads the file that was just rewritten, which is why the order is not free.
    """
    from factory.supervision import container_engine, container_manifest
    from factory.supervision.container_project import resolve_project

    installed = container_manifest.installed_project()
    if installed is None:
        return None

    compose_path = installed.compose_path
    try:
        from factory.controlplane.config import load_controlplane_config

        project = resolve_project(
            load_controlplane_config(),
            confinement=_installed_confinement(compose_path),
        )
        report = _project_writer(project)
        container_engine.bring_up(compose_path, run=_compose_runner)
    except Exception as error:  # noqa: BLE001 - a late step must never abort init
        return (
            f"engine container: not reconciled — {type(error).__name__}: {error}; "
            f"{repo_root.resolve()} is registered but the engine at "
            f"{installed.directory} may not mount it, and its supervisor refuses "
            "to start against a repo it cannot see — re-run `ergane install`"
        )

    if report.kept:
        # The writer refuses to overwrite a file it did not write (104 US3), so
        # the mount list on disk is still the operator's.  Saying the repo was
        # mounted would be false, and false in the direction that fails hours
        # later at the first dispatch rather than here.
        return (
            f"engine container: reconciled, but {compose_path.name} in "
            f"{installed.directory} was left as you edited it, so it may not "
            f"mount {repo_root.resolve()} — move it aside and re-run "
            "`ergane install` to have it generated again"
        )

    return (
        f"engine container: regenerated {compose_path} with "
        f"{repo_root.resolve()} mounted at its own path, and reconciled the engine"
    )


def _engine_facts(repo_root: Path) -> dict[str, Any]:
    """This host's engine container facts, as `InitFacts` keyword arguments.

    An empty mapping is "this host does not run the container tier", and the
    judgment renders no finding for it.  Every failure is a fact rather than an
    exception, for `_control_plane_facts`' reason: a gathering step that raises
    takes the whole report with it, and one unreadable file must not be able to
    hide every other finding.
    """
    from factory.supervision.container_manifest import installed_project

    try:
        installed = installed_project()
    except Exception as error:  # noqa: BLE001 - a fact-gatherer must never abort
        return {"engine_project_dir": "?", "engine_error": f"{type(error).__name__}: {error}"}
    if installed is None:
        return {}

    facts: dict[str, Any] = {"engine_project_dir": str(installed.directory)}
    try:
        mounted = repo_root.resolve() in _engine_repo_sources(installed.compose_path)
    except Exception as error:  # noqa: BLE001 - see above
        return {**facts, "engine_error": f"{type(error).__name__}: {error}"}
    return {**facts, "engine_repo_mounted": mounted}


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

    specs_root = repo_root / "specs"
    specs_root.mkdir(exist_ok=True)


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


def gather_init_facts(
    repo_root: Path,
    *,
    control_plane: tuple[tuple[Finding, ...], str | None] | None = None,
    invocation_dir: Path | None = None,
) -> InitFacts:
    """Read the facts init created, so `evaluate_repo` can judge them (FR-010).

    Gathering only: the judgment lives in `factory/mergequeue/onboard.py` beside
    the 003 checks, because a second place deciding what "ready" means is a
    second place that can drift.

    `control_plane`, when provided, is the precomputed result of
    `_control_plane_facts()` so a full init evaluates the control plane once
    and shares it between the schedule precondition and the readiness report
    (FR-006).  `ergane init --check` omits it and gathers fresh.

    `invocation_dir` is 064/FR-008's fact: the directory the *operator* pointed
    at, which only the CLI knows.  A caller that names a repository directly —
    every programmatic one — leaves it unset, and the finding then reports the
    root without claiming anyone walked up to it.
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

    if control_plane is None:
        control_plane_findings, control_plane_error = _control_plane_facts()
    else:
        control_plane_findings, control_plane_error = control_plane

    return InitFacts(
        repo_root=str(repo_root),
        invocation_dir="" if invocation_dir is None else str(invocation_dir),
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
        control_plane=control_plane_findings,
        control_plane_error=control_plane_error,
        **_schedule_facts(repo_root, slug, config),
        **_engine_facts(repo_root),
    )


def check_repo(
    repo_root: str | Path,
    *,
    control_plane: tuple[tuple[Finding, ...], str | None] | None = None,
    invocation_dir: Path | None = None,
) -> TargetRepoProfile:
    """Judge one repository's readiness through the shared judgment (FR-010).

    `onboard_target_repo` is the seam both doors already share, so the 003 facts
    are gathered by the code that already knows how and init's ride beside them.
    The `@activity.defn` wrapper is deliberately not what is called: it cannot
    run outside a worker (plan trap 2).
    """
    from factory.activities.merge_activities import onboard_target_repo

    root = Path(repo_root).resolve()
    facts = gather_init_facts(
        root, control_plane=control_plane, invocation_dir=invocation_dir
    )
    forge = _forge_factory(repo_path=str(root))
    return onboard_target_repo(forge, str(root), init_facts=facts)


def render_check(
    profile: TargetRepoProfile,
    repo_root: Path,
    manifest_name: str,
    *,
    remedy: Mapping[str, str] | None = None,
) -> str:
    """One line per finding: `PASS`, `WARN` or `FAIL`.

    Passing findings print too: "checked" and "passed" are different claims, and
    a failures-only report cannot make the first.

    061-US3 added the third mark, and the summary line has to carry it or the
    mark is wasted: a run whose only non-passing finding is a warning exits 0,
    and "all N checks passed" over the top of a `[WARN]` line would be the
    report contradicting itself — which is the exact reading ("gates work") this
    story exists to stop.

    US5 added an optional remedy table: every non-passing line names the command
    that clears it. A check not present in the table falls back to naming
    `ergane init --check` so a red line never leaves the operator guessing.
    When the table is absent the output is byte-identical to the pre-US5 shape,
    keeping `ergane init --check`'s existing tests green untouched (trap 13).
    """
    lines = [f"ergane readiness for {repo_root} ({manifest_name})"]
    failed = 0
    warned = 0
    for finding in profile.findings:
        if finding.blocking:
            failed += 1
        elif not finding.passed:
            warned += 1
        line = f"  [{finding.mark}] {finding.check}: {finding.detail}"
        if remedy is not None and not finding.passed:
            fix = remedy.get(finding.check)
            if fix is None:
                fix = "run `ergane init --check`"
            line = f"{line} — fix: {fix}"
        lines.append(line)

    total = len(profile.findings)
    warnings = f", {warned} warned" if warned else ""
    if failed:
        lines.append(f"{failed} of {total} checks failed{warnings}")
    elif warned:
        lines.append(
            f"{total - warned} of {total} checks passed, {warned} warned; "
            "nothing here refuses this repository"
        )
    else:
        lines.append(f"all {total} checks passed")
    return "\n".join(lines)


def run_check(
    repo_root: Path,
    *,
    control_plane: tuple[tuple[Finding, ...], str | None] | None = None,
    invocation_dir: Path | None = None,
) -> int:
    """Render the report; non-zero on any failing finding, 0 when all pass.

    `control_plane`, when provided, is the precomputed result of
    `_control_plane_facts()` so a full init shares one evaluation between the
    schedule precondition and the readiness report (FR-006).  `ergane init
    --check` omits it and probes fresh.

    `invocation_dir` carries 064/FR-008's fact down to the judgment: the report
    names the root it resolved in a *finding*, not only in the header line the
    reporter of that near-miss happened to read.
    """
    profile = check_repo(
        repo_root, control_plane=control_plane, invocation_dir=invocation_dir
    )
    _manifest_path, manifest_name = resolve_manifest_path(repo_root)
    print(render_check(profile, repo_root, manifest_name))
    return EXIT_OK if profile.passed else EXIT_USER
