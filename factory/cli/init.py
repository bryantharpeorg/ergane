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

120's US1 stops the act that made all of the above beside the point on a
repository that was already configured. `ergane init --wire` treated an existing
manifest as a thing to regenerate, so a valid committed file came back through
`safe_dump` without its comments, without `standards`, and without the `ladder`
block this module has no vocabulary for — and `--check` then called the result
valid, because every key that vanished is optional. A manifest that the loader
accepts is now *kept* (`_existing_manifest`, `_write_scaffold`'s `None`), the
rest of init runs exactly as before, and a manifest the loader refuses stops the
run with its error quoted rather than being replaced by a fresh one.

120's US2 covers the rewrite that is left. It carries what the file declared
instead of re-deriving it: `_init_default` consults the computed defaults
*before* returning "absent" for an optional key, so the committed value wins and
absent means the repository declared nothing; `_load_existing_defaults` reads
those keys from the document as written, because for an optional key the
question is what the operator declared and not what the schema resolved; and
`_carried_forward` brings `ladder` and `verify` through without the interview
growing a question, refusing rather than dropping a key it cannot write back.
What no rewrite can carry is comments, so one that will lose them says so before
it writes (`_comment_warning`) — the whole reason US1 comes first.
"""

from __future__ import annotations

import argparse
import dataclasses
import re
import subprocess
from pathlib import Path
from typing import Any, Callable, Mapping

import yaml

from factory import registry
from factory.cli.errors import EXIT_OK, EXIT_USER, OperatorError
from factory.constitution import DEFAULT_FLOOR_VERSION as FLOOR_VERSION, resolve_default_floor
from factory.locking import LockUnavailable, lock_path_for
from factory.mergequeue import wiring
from factory.mergequeue.forge import WiringRefused, format_step
from factory.mergequeue.models import Finding, TargetRepoProfile
from factory.mergequeue.onboard import InitFacts
from factory.roadmap import schedule as roadmap_schedule
from factory.stack_packs import (
    StackDetection,
    StackPack,
    detect_stack_packs,
    fallback_pack,
)
from factory.verify.factory_yaml import (
    MANIFEST_NAME,
    _SUPPORTED_VERSION,
    _TOP_LEVEL_KEYS,
    _V2_TOP_LEVEL_KEYS,
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
    # 101/US2: the caches this repo's gates need carried across the gate
    # boundary, whose `HOME` is a tmpfs. The prompt names the shape rather than
    # the reason — an operator who needs this already met the reason as a gate
    # that re-downloaded the world.
    "caches": (
        "caches the gates need inside the boundary (YAML list of "
        "{path, env}, paths under your home, optional)"
    ),
    # 092/US2: the size above which this repository refuses to build a story.
    # Optional, and the floor the parser enforces is the judge's attention
    # budget, so the question names bytes rather than inviting a round number.
    "diff_refusal_bytes": (
        "diff refusal threshold in bytes — the size above which a story is "
        "refused unjudged (optional)"
    ),
}

#: Prompt for the optional template source that displaces the shipped default.
_TEMPLATE_SOURCE_PROMPT = "template source path (optional)"

#: Keys an empty answer omits rather than defaults.  Each is additive: a repo
#: that declares none of them is a complete manifest.
_OPTIONAL_KEYS = (
    "timeouts",
    "standards",
    "roadmap",
    "forge",
    "writes",
    "caches",
    "diff_refusal_bytes",
)

#: Every key a manifest this module writes may carry — the parser's own v2
#: vocabulary, never a second list beside it (120 FR-006).
#:
#: `_TOP_LEVEL_KEYS` is what the *interview* asks about, and the two tuples are
#: deliberately not the same one. `ladder` and `verify` are in this tuple and in
#: no prompt: they are carried from the file, not asked about, which is why
#: `tests/test_forge_manifest.py`'s `set(_PROMPTS) == set(_TOP_LEVEL_KEYS)` still
#: holds. Growing the question set was never what FR-006 asked for (trap 5).
#:
#: This is also the tuple `_carried_forward` refuses against: a key outside it is
#: one no rewrite here can carry, and the only two answers to that are refusing
#: and dropping it silently. Dropping it silently is what produced this epic.
#:
#: Read by name rather than subscripted by literal wherever a key is looked up:
#: `tests/test_ergane_cli.py`'s guard against a hardcoded list of CLI noun names
#: matches a bracket followed by any quoted noun name, and `roadmap` is both a
#: manifest key and a CLI noun.
_KNOWN_KEYS = _V2_TOP_LEVEL_KEYS

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

    Pack-driven detection: a shipped stack pack contributes its `test` command
    when its markers match, and the language-agnostic fallback contributes the
    undeclared-gate sentinel. Returns the mapping the manifest actually carries
    rather than a rendered YAML line (057/US2 FR-007, FR-009).
    """
    pack, _notice = select_stack_without_operator(repo_root)
    if "test" in pack.commands:
        return {"test": pack.commands["test"]}
    return {"test": _UNDECLARED_GATE_COMMAND}


def _load_existing_defaults(repo_root: Path) -> dict[str, Any]:
    """If a manifest already exists, return its values as interview defaults.

    Two sources, and which one answers which key is the whole of 120 FR-005.

    The keys the schema **resolves** — `version`, `runtime`, `gates`,
    `landing_branch` — come from the loader, because a manifest that declares no
    `landing_branch` still has one and the interview has to offer the value the
    repository actually runs with.

    Every optional key comes from the document **as written**, because for those
    the question is not "what does this repository run with" but "what did the
    operator declare", and a rewrite carries the answer to the second. The
    distinction is not academic — it is where the data went. `forge` resolves to
    `github` whether it was declared or not, so a carry-forward taken from the
    typed config cannot tell a manifest that spells the default out from one
    that says nothing, and this function used to settle that by dropping the
    operator's line (the cost 034 FR-005 accepted, and no longer has to).
    `diff_refusal_bytes` resolves to a number nobody typed. `caches` resolves
    every declared path against *this host's* home, so carrying the typed value
    would rewrite `~/.npm` into one machine's answer for it.

    An unreadable manifest is no defaults at all, unchanged: `_existing_manifest`
    is what refuses a broken file (FR-004), and it has already run by the time
    anything here matters.
    """
    manifest = repo_root / MANIFEST_NAME
    if not manifest.is_file():
        return {}
    try:
        config = load_factory_config(manifest)
        document = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    defaults: dict[str, Any] = {
        "version": config.version,
        "runtime": config.runtime,
        "gates": dict(config.gates),
        "landing_branch": config.landing_branch,
    }
    # Declared means declared, key by key and by name rather than by literal
    # (see `_KNOWN_KEYS`). A loop rather than a stanza each: the stanzas are how
    # `caches` came to have a branch in `_build_defaults` that nothing could
    # reach, and how `diff_refusal_bytes` never got one at all.
    for key in _OPTIONAL_KEYS:
        if key in document:
            defaults[key] = document[key]
    return defaults


@dataclasses.dataclass(frozen=True)
class _ExistingManifest:
    """The manifest a repository already has, read the way `--check` reads it.

    `declared` is the document as written — the keys the operator actually
    typed, including any this module has no vocabulary for. `config` is the
    loader's resolved answer, which is what the wiring is driven from: a
    manifest that declares no `landing_branch` still *has* one, and the resolved
    value is the one the forge must be pointed at.

    `text` is the bytes as committed, and it is here for the one thing neither
    of the other two can answer: whether this file carries comments a rewrite
    would destroy (120 FR-009). Both `declared` and `config` are what survives
    `yaml.safe_load`, and what a rewrite loses is precisely what does not.
    """

    path: Path
    text: str
    declared: dict[str, Any]
    config: FactoryConfig


def _existing_manifest(repo_root: Path) -> _ExistingManifest | None:
    """The committed manifest, `None` when there is none — refusing a broken one.

    120 FR-001, trap 1: "valid" means the schema's answer and nobody else's.
    This asks `resolve_manifest_path` and `load_factory_config`, the pair
    `gather_init_facts` already asks for `ergane init --check`, so the two verbs
    cannot call one file valid and replaced. A second notion of validity inside
    init is precisely how a manifest gets kept by one door and flattened by the
    other.

    A file the schema refuses raises rather than being ignored (FR-004, trap 3).
    The tempting reading of "leave a valid manifest alone" is "so replace an
    invalid one", and that is worse than the defect this story fixes: it
    destroys the file of an operator who is halfway through editing it. The
    loader's own error is quoted rather than paraphrased, for the same reason
    the loader is the one asked.

    Absent is not a refusal — it is `None`, and the caller writes a manifest
    exactly as it does today (FR-003).
    """
    path, _name = resolve_manifest_path(repo_root)
    if not path.is_file():
        return None

    try:
        config = load_factory_config(path)
    except FactoryConfigError as refusal:
        raise OperatorError(
            "\n".join(
                [
                    str(refusal),
                    "",
                    f"{path} is unchanged: init does not replace a manifest it "
                    "cannot read. Fix the file — `ergane init --check` reports "
                    "the same finding — or move it aside to have a new one "
                    "written.",
                ]
            ),
            code=EXIT_USER,
        ) from None

    text = path.read_text(encoding="utf-8")
    # A mapping, guaranteed: the loader has already refused every document whose
    # root is not one, and every byte sequence that does not decode.
    declared = dict(yaml.safe_load(text) or {})
    return _ExistingManifest(path=path, text=text, declared=declared, config=config)


def _carried_forward(existing: _ExistingManifest | None) -> dict[str, Any]:
    """The declarations a rewrite must carry that nobody is asked about.

    120 FR-006 and FR-007, which are one function because they are one question:
    what does this module do with a key it is not going to ask a question about?
    There are exactly two answers. Carry it, if it is a key the schema knows and
    this writer can emit. Refuse, naming it, if it is not. What there is not is a
    third answer, and the third answer is what shipped: `ladder` and `verify`
    were dropped on every path, by a writer that emitted `_TOP_LEVEL_KEYS` and
    had never heard of them, into a file the operator then committed.

    The refusal reads as unreachable and is not. `_reject_unknown_keys` refuses
    a key *the schema* does not know before `_existing_manifest` returns, so a
    typo never arrives here — the case that does is a key the schema has learned
    and this module has not, which is not hypothetical. It is the state this
    epic found the tree in: `factory/verify/factory_yaml.py` named `ladder`
    twenty-nine times and `factory/cli/init.py` named it zero. A refusal costs
    one run and one error message; the alternative cost a repository its
    configuration and erased the evidence on the way out.
    """
    if existing is None:
        return {}

    unknown = [key for key in existing.declared if key not in _KNOWN_KEYS]
    if unknown:
        raise OperatorError(
            "\n".join(
                [
                    f"{existing.path} declares "
                    + ", ".join(f"`{key}`" for key in unknown)
                    + ", which `ergane init` cannot write back.",
                    "",
                    "The rewrite was refused and the file is unchanged: a key "
                    "this verb does not recognise is a key it would have "
                    "dropped, and a manifest that comes back smaller than it "
                    "went in is how a repository loses its configuration "
                    "without anyone reading a diff.",
                    "",
                    "Either remove the key, or leave the manifest as it is — "
                    "`ergane init --check` judges it without writing to it.",
                ]
            ),
            code=EXIT_USER,
        )

    return {
        key: existing.declared[key]
        for key in _KNOWN_KEYS
        if key not in _TOP_LEVEL_KEYS and key in existing.declared
    }


#: What a manifest opens a comment with, and the two characters that may precede
#: one. YAML starts a comment at a `#` that begins a line or follows whitespace;
#: a `#` anywhere else belongs to the value it sits in — `test: "make x#y"` is a
#: gate command, not prose, and a warning that counted it would fire about a
#: loss that cannot happen.
_COMMENT = "#"


def _comment_lines(text: str) -> list[str]:
    """Every line of a manifest carrying a comment no emitter here can reproduce.

    120 FR-009's mechanism, and the reason it is a scan rather than a parse:
    comments are not tokens. `yaml.safe_load` discards them before anything in
    this module could see one, which is the same fact that makes `safe_dump`
    unable to write them and makes this warning necessary at all.

    Quoting is tracked so a `#` inside a scalar is not counted. Escapes inside a
    double-quoted scalar are not, which can only over-count — a spurious warning
    on a rewrite that loses nothing, rather than silence on one that does.
    """
    found: list[str] = []
    for line in text.splitlines():
        quote: str | None = None
        for index, char in enumerate(line):
            if quote is not None:
                if char == quote:
                    quote = None
                continue
            if char in "\"'":
                quote = char
                continue
            if char == _COMMENT and (index == 0 or line[index - 1] in " \t"):
                found.append(line)
                break
    return found


def _comment_warning(existing: _ExistingManifest) -> str | None:
    """What to tell the operator before a rewrite discards their prose, or None.

    FR-009. Said *before* the write, because after it the file is already gone
    and the sentence is a report. The count is stated rather than the lines
    quoted: the operator has the original in git and needs to know how much to
    go and get, not to read it back off a terminal.

    US1 means this is rare — a valid manifest is kept, comments and all — and
    rare is what keeps it readable. A caution printed on every run is one
    operators learn to scroll past, which is how the next silent loss goes
    unread.
    """
    comments = _comment_lines(existing.text)
    if not comments:
        return None
    lines = "line" if len(comments) == 1 else "lines"
    return (
        f"warning: {existing.path} carries {len(comments)} comment {lines}, and "
        "this rewrite cannot keep them — the manifest is emitted through "
        "`yaml.safe_dump`, which writes no comment. They are still in git; "
        "`git diff` before you commit, and copy back what you meant to keep."
    )


def _declared_wiring_values(existing: _ExistingManifest) -> dict[str, Any]:
    """The manifest values `_wire` acts on, taken from the file init kept.

    FR-002, trap 2: not rewriting the manifest is not declining the job, so the
    wiring still needs a gate list and a landing branch. They come from the
    loader's resolved config rather than from the raw document, because a
    manifest may leave `landing_branch` to the schema's default and the forge
    still has to be pointed at a real branch.
    """
    values = dict(existing.declared)
    values["gates"] = dict(existing.config.gates)
    values["landing_branch"] = existing.config.landing_branch
    return values


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
    # Every optional key the repository declared, offered back rather than
    # re-derived — the rule the four above already follow: a re-run reconciles
    # what the repository declared. Deriving would be worse for some of them
    # than for others (`caches` paths are holes in a verification boundary, and
    # init has no business opening one nobody typed — 101 FR-007), but it is
    # wrong for all of them, and a loop is what stops the next key being added
    # to `_OPTIONAL_KEYS` and to nothing else.
    for key in _OPTIONAL_KEYS:
        if key in existing:
            defaults[key] = existing[key]
    return defaults


def _init_default(key: str, repo_root: Path) -> Any:
    """Return the documented default for one manifest key, or `_NO_DEFAULT`.

    This is the shared defaults source for the non-interactive path.  The
    interactive path displays the same values through `_build_defaults`; a field
    whose only safe value is operator-supplied has no default here.

    The order of the two branches below is 120 FR-005, and the defect it fixes
    was five lines and a comment. `_build_defaults` opens by reading the
    existing manifest, so the operator's committed value is *in hand* here — and
    an early return for `_OPTIONAL_KEYS` above the consultation threw it away
    one line before it would have been used, for exactly the keys a repository
    configures itself with. `standards` is one of them, so a wired repository
    came back declaring no standards document at all and every node it
    dispatched afterwards ran with none.
    """
    defaults = _build_defaults(repo_root)
    if key in defaults:
        return defaults[key]
    if key in _OPTIONAL_KEYS:
        # "Absent" is a safe default for a manifest that does not exist and a
        # destructive one for a manifest that does. Reached only when the
        # repository declared nothing for this key, because a declared value is
        # in `defaults` above (FR-008: a fresh repository still gets nothing).
        # 057/US1: `standards` gets a documented default rather than becoming
        # mandatory, so an empty answer still means "omit" for the other optional
        # keys, but a fresh repository receives the default path rather than no
        # path at all.
        if key == "standards":
            return DEFAULT_STANDARDS_PATH
        return None
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

    That rule is unchanged by 120 US2 and deliberately so: the operator was
    *shown* the value their manifest declares — `_build_defaults` now offers
    every optional key back — so an empty answer here is a person reading their
    own declaration and asking for it to go. The loss this story fixes was the
    other thing entirely, a key removed from a file nobody was asked about.
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
        if key is None and prompt == _TEMPLATE_SOURCE_PROMPT:
            # 057/US4: non-interactive mode uses the shipped default; an operator
            # who wants a custom template names it interactively or edits the file.
            self._reports.append("applied default: template source = shipped default")
            return ""
        if key is None and prompt == "repo slug":
            # The default is the normalized directory name or existing registry slug.
            try:
                known = registry.load_registry().for_path(self._repo_root)
            except registry.RegistryError:
                known = None
            default_slug = known.slug if known is not None else registry.normalize_slug(self._repo_root.name)
            self._reports.append(f"applied default: repo slug = \"{default_slug}\"")
            return default_slug
        # 057/US2: there is deliberately no "detected stack" branch here. Only
        # `select_stack_with_operator` asks that question, and it is never
        # reached with this prompter — a non-interactive run calls
        # `select_stack_without_operator` directly. A branch here would be a
        # second detection path answering the same question, free to drift from
        # the first, which is the fault this story had to fix once already: the
        # interactive path re-implemented marker matching instead of sharing it.
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
    """Render the in-progress manifest as YAML.

    Over `_KNOWN_KEYS` rather than `_TOP_LEVEL_KEYS` (120 FR-006): the schema's
    whole vocabulary, so a key this module carries without asking about is a key
    it can also write. A writer whose key list was the *interview's* is what made
    `ladder` unwritable — and therefore, on every rewrite, gone.

    The order is the parser's own, so a carried key lands where the schema
    declares it rather than wherever the interview happened to leave it.
    """
    ordered: dict[str, Any] = {}
    for key in _KNOWN_KEYS:
        if key in values and values[key] is not None:
            ordered[key] = values[key]
    return yaml.safe_dump(ordered, sort_keys=False, default_flow_style=False)


def _interview(
    repo_root: Path,
    existing: _ExistingManifest | None,
    *,
    prompter: Any,
) -> dict[str, Any]:
    """Ask for every key the interview owns, and return the manifest to write.

    The rewrite path, in one place. Two kinds of value end up in the result and
    only one of them is asked about:

    - the interview's own keys (`_TOP_LEVEL_KEYS`), seeded from `_build_defaults`
      so the first question can already be validated against the full parser, and
      so an existing manifest's values are what the operator is offered;
    - the keys init carries but has no question for (`_carried_forward`), which
      is 120 FR-006's whole mechanism — `ladder` and `verify` reach the written
      file without the question set growing by one (trap 5).

    Seeded *before* the loop rather than merged after it, because `_ask_for_key`
    validates each answer by rendering the whole in-progress manifest: a carried
    `ladder` block has to be in that document, or the parser would be asked to
    accept a manifest this run is not going to write.
    """
    defaults = _build_defaults(repo_root)
    manifest_values: dict[str, Any] = {
        key: defaults[key] for key in _TOP_LEVEL_KEYS if key in defaults
    }
    manifest_values.update(_carried_forward(existing))

    for key in _TOP_LEVEL_KEYS:
        value = _ask_for_key(
            key,
            default_value=manifest_values.get(key),
            manifest_values=manifest_values,
            prompter=prompter,
        )
        if value is None:
            manifest_values.pop(key, None)
        else:
            manifest_values[key] = value

    # 057/US4: ask for an optional template source after the manifest interview.
    # A supplied source displaces the shipped default; an absent source uses the
    # shipped default. A bad source is refused here, at interview time, rather
    # than silently falling back.
    template_source = _ask_for_template_source(prompter)
    if template_source is not None:
        manifest_values["_template_source"] = template_source

    return manifest_values


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

        # FR-001, and the first act of the run that touches this repository's
        # own declarations: what is already there, judged by the loader rather
        # than by init. A manifest the schema refuses stops the run here, before
        # anything is written (FR-004).
        existing = _existing_manifest(repo_root)

        if existing is not None and non_interactive:
            # FR-001. Nobody was asked anything, so nobody asked for a change:
            # the documented default for a repository that already declares a
            # valid manifest is that manifest. The interview is skipped rather
            # than run-and-discarded, so the run reports what it did rather than
            # a list of defaults it applied to nothing.
            manifest_values: dict[str, Any] = _declared_wiring_values(existing)
            keeps_manifest = True
        else:
            # A rewrite, and the only path that performs one. What it carries is
            # `_interview`'s subject: every value the existing manifest declared,
            # asked about or not (120 FR-005, FR-006), and a refusal rather than
            # a silent drop for a key it cannot carry (FR-007) — raised here,
            # before anything has been written.
            manifest_values = _interview(repo_root, existing, prompter=prompter)

            # The same rule with an operator in the room: their answers are the
            # request, so a manifest is rewritten when the answers say something
            # the file does not already say, and kept — comments and all — when
            # they do not. An interview that changes nothing is not a licence to
            # re-emit the file through `safe_dump`.
            keeps_manifest = (
                existing is not None and manifest_values == existing.declared
            )

        # 057/US2: detect the repository stack, propose it, and allow override.
        # Detection runs inside the interview region so the operator can answer the
        # proposal before any file is written. The stack influences only the seeded
        # constitution, not the manifest itself.
        # 057/US4: a supplied template may carry its own stack packs. Discover them
        # in a `stacks/` sibling of the supplied floor file so supplied packs of the
        # same name override shipped packs and shipped packs still fill gaps.
        template_source = manifest_values.get("_template_source")
        extra_pack_dirs: list[Path] = []
        if template_source is not None:
            supplied_stacks = Path(template_source).parent / "stacks"
            if supplied_stacks.is_dir():
                extra_pack_dirs.append(supplied_stacks)

        stack_pack: StackPack | None = None
        if existing is None:
            if non_interactive:
                stack_pack, stack_notice = select_stack_without_operator(
                    repo_root, extra_directories=extra_pack_dirs
                )
                print(stack_notice)
            else:
                stack_pack = select_stack_with_operator(
                    repo_root, prompter, extra_directories=extra_pack_dirs
                )

        # The slug is declared by the operator and lives in the engine's registry,
        # never in the manifest: it is what the engine calls this repo, not what the
        # repo declares about itself.
        slug = _ask_for_slug(repo_root, prompter=prompter)
    finally:
        # Reset so a subsequent invocation in the same process is not permanently
        # pinned to the last invocation's flag.
        _require_explicit_consent = False

    # FR-002, trap 2: the manifest write is one part of the job, not the job.
    # Skipping it skips nothing else — the runtime root, the `.gitignore` line,
    # the registry row, the schedule and the wiring all still happen below.
    kept_manifest = existing if keeps_manifest else None
    text = None if kept_manifest is not None else _render_manifest(manifest_values)

    # FR-009, and the position on the page is the requirement: the operator is
    # told *before* the write, while the file they are being told about is still
    # on disk. Said afterwards this is a report of a loss rather than a warning
    # about one, and the difference is whether `git diff` is still worth running.
    comment_loss = (
        None if existing is None or kept_manifest is not None
        else _comment_warning(existing)
    )
    if comment_loss is not None:
        print(comment_loss)

    # 057/US1: resolve the floor and the standards path before any write, so a
    # `--check` run that reports an absence can do so without having created
    # directories. The constitution is written as part of the scaffold: a file
    # exists at the path is left untouched, and a missing file is seeded.
    # 057/US4: template resolution is part of the interview, so the resolved
    # floor and source are already in `manifest_values` as `_template_source`.
    template_source = manifest_values.pop("_template_source", None)
    floor = _resolve_floor(template_source)
    standards_path = _resolve_standards_path(manifest_values)
    manifest_values["standards"] = standards_path

    if kept_manifest is None:
        text = _render_manifest(manifest_values)

    _write_scaffold(repo_root, text)

    # 057/US1: seed a standards document when none exists. Parents are created
    # only when writing; the existence guard is on the file, not on its content
    # (FR-002, plan trap 4).
    standards_path, standards_found = _write_constitution(
        repo_root,
        manifest_values,
        floor_text=floor.text,
        source=floor.path,
        stack_pack=stack_pack,
    )
    if not standards_found:
        print(f"standards source: {floor.path}")

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
    # 120/FR-010, trap 7: the manifest that was kept is handed down rather than
    # re-read, so the schedule is reconciled against the operator's file and not
    # against whatever init has just put on disk. When the manifest *was*
    # written, `None` says so and the reconciliation reads the file back — there
    # the write is the declaration.
    schedule_line = _schedule(
        repo_root, slug, control_plane_reason=control_plane_reason, kept=kept_manifest
    )

    # Wiring runs last, after the repo-local half is complete and recorded, so a
    # refusal from GitHub's side never costs the operator the scaffold.
    wiring_lines = _wire(
        repo_root, manifest_values, requested=bool(getattr(args, "wire", False))
    )

    print(f"joined {repo_root.resolve()} as slug '{slug}'")
    if kept_manifest is not None:
        # Reported as its own line, above the list of what *was* written: an
        # operator who has just been told their manifest is untouched does not
        # then have to notice it missing from a list of writes.
        print(f"kept: {kept_manifest.path} is valid and was left unchanged")
    print("written:")
    if kept_manifest is None:
        print(f"  {repo_root / MANIFEST_NAME}")
    print(f"  {repo_root / '.gitignore'}")
    print(f"  {repo_root / RUNTIME_ROOT}")
    print(_constitution_write_line(repo_root, standards_path, standards_found))
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


def _schedule(
    repo_root: Path,
    slug: str,
    *,
    control_plane_reason: str | None,
    kept: _ExistingManifest | None,
) -> str:
    """Create or reconcile this repo's roadmap schedule, and report one line.

    Never raises (FR-017).  What steers the schedule is the operator's manifest
    and never the interview's values, so the dials on the schedule are the dials
    on the file they will commit.

    120 FR-010 and trap 7 are about *which* manifest that is.  `kept` is the
    manifest `init_command` read before anything was written, and it is passed
    down rather than re-read whenever the file was left alone: the reconciliation
    then compares the live schedule against the same object that decided the file
    was valid, which is what makes "the schedule disagrees with your manifest" a
    statement about the operator's manifest.  The alternative is the defect this
    story closes — comparing the world against init's own edit, and reporting the
    agreement that necessarily follows.

    `kept` is `None` exactly when init wrote a manifest, and then the file it
    wrote is the declaration: an operator who answered the interview asked for
    those values, and a repository that had no manifest has one now.  It is read
    back through `resolve_manifest_path`, the one resolver `_existing_manifest`
    and `ergane init --check` also ask, because a second opinion about where the
    manifest lives is a second answer about one file — a repository still
    committing the legacy `factory.yaml` had its schedule reported `failed: the
    manifest just written did not load` while the check three lines below named
    the drift correctly.

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
    if kept is not None:
        config, manifest_name = kept.config, kept.path.name
    else:
        manifest_path, manifest_name = resolve_manifest_path(repo_root)
        try:
            config = load_factory_config(manifest_path)
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
    step = roadmap_schedule.apply_schedule(desired)
    return roadmap_schedule.format_step(step) + _undeclared_dials_note(
        step, config, manifest_name
    )


def _undeclared_dials_note(
    step: roadmap_schedule.ScheduleStep, config: FactoryConfig, manifest_name: str
) -> str:
    """Say when the cadence just reported was nobody's declaration (120 US3-S3).

    `desired_for_repo` substitutes `RoadmapDials()` for a manifest that declares
    no `roadmap:` block, which is right — a repository must be joinable without
    steering its own scheduler — and unreadable: every other number on the line
    above came off the operator's file, and `every 300s` sits among them looking
    exactly like one more of them.  The same substitution is what lets the check
    then call the schedule a match for a manifest that says nothing about it.

    Naming the absence is the whole of the fix; the schedule still gets the
    defaults it always got.  A failed step is left alone, because nothing was
    compared and a note about the dials of a schedule that was never reached is
    noise in front of the reason it was not.
    """
    if step.action == roadmap_schedule.FAILED or config.roadmap is not None:
        return ""
    return (
        f"\n  {manifest_name} declares no roadmap dials, so the cadence and "
        f"concurrency above are Ergane's defaults rather than this repository's "
        f"declaration — add a `roadmap:` block to steer them"
    )


def _ask_for_template_source(prompter: Any) -> str | None:
    """Ask the operator for a template source that displaces the shipped default.

    Empty answer means "use the shipped default". A non-empty answer is returned
    as-is and validated later, because the prompt only collects intent; refusing
    a missing or empty file belongs to the resolver so the error names the path.
    """
    answer = prompter.ask(_TEMPLATE_SOURCE_PROMPT, default="")
    stripped = answer.strip()
    if not stripped:
        return None
    return stripped


def _resolve_floor(template_source: str | None) -> "FloorSource":
    """Resolve the floor to seed from: supplied, then shipped.

    A supplied source that does not exist, is unreadable, or is empty is refused
    at interview time naming the path (FR-018). The shipped default is never
    silently substituted for a bad supplied source.
    """
    from factory.constitution import resolve_default_floor, resolve_supplied_floor

    if template_source is not None:
        resolved = resolve_supplied_floor(template_source)
        if resolved is None:
            raise OperatorError(
                f"template source {template_source!r} is missing, unreadable, or empty",
                code=EXIT_USER,
            )
        return resolved
    return resolve_default_floor()


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


def _write_scaffold(repo_root: Path, manifest_text: str | None) -> None:
    """Write exactly the declared files and nothing else.

    `manifest_text` is `None` when the repository's own manifest stands (120
    FR-001): the rest of the scaffold is still written, because the manifest is
    one of init's outputs and not the whole of it (FR-002, trap 2). A caller
    that means "leave the file alone" passes `None` rather than re-rendering the
    text it read, since a render that happens to round-trip today still loses
    every comment the moment a key moves.
    """
    if manifest_text is not None:
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


#: Default relative path for the seeded standards document (FR-003).
DEFAULT_STANDARDS_PATH = ".specify/memory/constitution.md"


def _resolve_standards_path(manifest_values: dict[str, Any]) -> str:
    """Return the path the constitution will be written to.

    The manifest's `standards` key wins when present; otherwise the documented
    default is used. The returned value is relative to the repo root.
    """
    declared = manifest_values.get("standards")
    if isinstance(declared, str) and declared.strip():
        return declared.strip()
    return DEFAULT_STANDARDS_PATH


def _standards_document_exists(repo_root: Path, standards_path: str) -> bool:
    """Whether a standards document already exists at the resolved path.

    Existence is the guard, not content: an empty file is a deliberate choice and
    must not be overwritten (plan trap 4).
    """
    return (repo_root / standards_path).is_file()


def _stack_notice(
    detection: StackDetection, pack: StackPack, *, can_ask: bool
) -> str:
    """The line the operator reads about how this stack was arrived at.

    Three outcomes, and the difference between them is the point: a detected
    stack is a claim the operator can contradict, the fallback is an admission
    that nothing was recognised, and ambiguity is a question. Rendered
    identically all three would read as a decision, and only one of them is.
    """
    if detection.ambiguous:
        named = ", ".join(f"{p.label} ({p.name})" for p in detection.candidates)
        if can_ask:
            return (
                f"marker files matched more than one stack ({named}); name one, "
                f"or answer empty to write the {pack.label} layer instead"
            )
        return (
            f"marker files matched more than one stack ({named}); no stack was "
            f"chosen, and the {pack.label} layer was written instead — re-run "
            "`ergane init` interactively to name one"
        )
    if detection.unmatched:
        return (
            "no shipped stack matched this repository's marker files; the "
            f"{pack.label} layer was written and names what to complete"
        )
    return f"detected stack: {pack.label} ({pack.name})"


def select_stack_without_operator(
    repo_root: Path,
    *,
    extra_directories: list[Path] | None = None,
) -> tuple[StackPack, str]:
    """Choose a stack with nobody to ask, and say how it was chosen.

    Returns the pack and the notice to print. Ambiguity is *not* resolved here
    (plan trap 7): with two candidate stacks and no operator, picking either one
    is a coin flip whose result gets written into the document this repository's
    agents obey. The fallback layer is written instead and the notice names both
    candidates, so the question survives as a question.
    """
    detection = detect_stack_packs(repo_root, extra_directories=extra_directories)
    pack = detection.pack if not detection.ambiguous else None
    if pack is None:
        pack = detection.fallback()
    return pack, _stack_notice(detection, pack, can_ask=False)


def select_stack_with_operator(
    repo_root: Path,
    prompter: Any,
    *,
    extra_directories: list[Path] | None = None,
) -> StackPack:
    """Detect a stack, state it before it is used, and let the operator override.

    US2-S1 puts the statement before the use, so the operator is told what was
    detected while they can still contradict it (US2-S2). Ambiguity asks rather
    than picks; an empty answer there takes the fallback, and the notice says so
    before the question rather than after it.

    A repository that matched nothing is told so and not asked. There is no
    detection to disagree with, and a question with no proposal behind it would
    lengthen the interview for every brownfield repository to no purpose — the
    fallback layer it gets names what to complete, which is where that decision
    belongs (US2-S3, FR-009).
    """
    detection = detect_stack_packs(repo_root, extra_directories=extra_directories)
    proposed = detection.pack if not detection.ambiguous else None
    if proposed is None:
        proposed = detection.fallback()

    # Stated *before* the question, which is the whole of US2-S1: an operator
    # asked to confirm a value they have not been shown is being asked nothing.
    print(_stack_notice(detection, proposed, can_ask=not detection.unmatched))
    if detection.unmatched:
        return proposed

    answer = prompter.ask("detected stack", default=proposed.name).strip()
    if not answer or answer == proposed.name:
        return proposed

    chosen = detection.by_name(answer)
    if chosen is None:
        # Not an omission — a wrong answer, and the two are kept apart
        # deliberately (plan trap 11). An empty answer takes the proposal; a
        # name no pack answers to is refused with the names that exist, rather
        # than silently falling back to the proposal and writing a stack layer
        # the operator did not ask for.
        raise OperatorError(
            f"no shipped stack pack is named {answer!r}; available: "
            + ", ".join(sorted(p.name for p in detection.available))
        )
    print(f"using operator-chosen stack: {chosen.label} ({chosen.name})")
    return chosen


def compose_constitution(
    floor_text: str,
    source: str,
    *,
    project_name: str,
    stack_layer: str,
) -> str:
    """Compose a constitution from floor, stack layer, project section, and governance.

    Pure function of its inputs so it is testable without a repository. The
    `source` argument records where the floor came from; US4 will pass a
    different source through this same seam.
    """
    parts: list[str] = []
    parts.append(floor_text.rstrip())
    parts.append("")
    parts.append("---")
    parts.append("")
    parts.append(stack_layer.rstrip())
    parts.append("")
    parts.append("---")
    parts.append("")
    parts.append(f"# Project principles: {project_name}")
    parts.append("")
    parts.append("Add what this repository believes about how its agents should work.")
    parts.append("")
    parts.append("---")
    parts.append("")
    parts.append("# Governance")
    parts.append("")
    parts.append("This document belongs to the repository. Edit it directly. Ergane will not rewrite it once it exists, and will not re-impose a principle you have removed.")
    parts.append("")
    parts.append(f"Seeded from {source} (floor version {FLOOR_VERSION}).")
    return "\n".join(parts) + "\n"


def _write_constitution(
    repo_root: Path,
    manifest_values: dict[str, Any],
    *,
    floor_text: str,
    source: str,
    stack_pack: StackPack | None = None,
) -> tuple[str, bool]:
    """Seed a standards document if none exists, and report what happened.

    Returns the path written and whether an existing file was found. Parents are
    created only when writing, so a `--check` run that reports an absence leaves
    no directory behind (plan trap 5).
    """
    standards_path = _resolve_standards_path(manifest_values)
    target = repo_root / standards_path
    if _standards_document_exists(repo_root, standards_path):
        return standards_path, True

    project_name = manifest_values.get("landing_branch", "this repository")
    # One renderer for every pack (FR-010). This used to compare the pack's name
    # against the fallback's and render that one through a separate hardcoded
    # function — a branch per stack in the writer, which is what SC-004 forbids,
    # and which meant a new pack needing anything of the fallback's shape would
    # have earned itself a second branch.
    stack_layer = (stack_pack if stack_pack is not None else fallback_pack()).render_layer()
    text = compose_constitution(
        floor_text,
        source,
        project_name=str(project_name),
        stack_layer=stack_layer,
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return standards_path, False


def _constitution_write_line(
    repo_root: Path, standards_path: str, found: bool
) -> str:
    """One line reporting what happened to the constitution."""
    if found:
        return f"found: {repo_root / standards_path} exists and was left unchanged"
    return f"  {repo_root / standards_path} (seeded)"


_FLOOR_VERSION_RE = re.compile(r"\(floor version ([^)]+)\)")


def _read_floor_version(path: Path | None) -> str | None:
    """Return the floor version recorded in a standards document, if any.

    A missing file or a file that does not contain the marker yields None,
    which is reported as "unknown" rather than "behind" (FR-014).
    """
    if path is None or not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001 - an unreadable document is just unversioned
        return None
    match = _FLOOR_VERSION_RE.search(text)
    return match.group(1) if match else None


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
    standards_path = config.standards if config is not None else ""
    target = repo_root / standards_path if standards_path else None
    standards_exists = bool(target) and target.is_file() if target is not None else False

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
        standards_path=standards_path,
        standards_exists=standards_exists,
        standards_recorded_version=_read_floor_version(target),
        installed_floor_version=FLOOR_VERSION,
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
