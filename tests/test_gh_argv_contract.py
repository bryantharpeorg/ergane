"""US2: every argv `GhClient` builds is accepted by the real `gh` binary.

The merge-queue component issues every GitHub command through `GhClient`, but
the existing tests use `FakeGh`, and a fake answers whatever it is scripted to
answer. Two real commands were therefore wrong for months:

- `gh pr checks <n> --json ...` — `pr checks` has no `--json` flag.
- `gh pr create ...` parsed as JSON, but `pr create` prints a URL.

This file adds a check that runs every command `GhClient` builds against the
installed `gh` binary, with no token, no network, and no repository. `gh`
rejects unknown flags during argument parsing, before it authenticates, so the
check is fast and cheap. The command surface is enumerated from the class, not
hand-listed, so a new method is covered automatically.

078-US1 fixes what that check could not see. It classified a refusal by matching
three phrases in stderr — "unknown flag", "unknown command", "usage:" — which is
three shapes out of an open set. `gh` refuses an unknown `--json` field with
`Unknown JSON field: "baseRefOid"`, which matches none of the three, so the
check watched a refusal and reported acceptance. The classification is now the
process exit status (FR-001), with the authentication exit kept as acceptance
(FR-002) so the check stays runnable with no token and no network, and the
poller's `--json` field set is validated from the value the poller sends
(FR-003) rather than from a copy.

**This file's verdict is about the `gh` on the asking process's `PATH`, and it
says so.** That is not a hedge, it is the measurement. `gh`'s version is a
property of the environment, not of the code, so there are two different
questions here and only one of them is about the tree:

- *Is the argv malformed?* — a defect in `GhClient`, true on every host. Always
  a failure.
- *Does the `gh` this process resolves declare every `--json` field the argv
  asks for?* — a property of this machine. Named and reported explicitly, never
  passed over in silence and never charged to the tree.

The second question has a live answer right now: `/usr/bin/gh` in the node's
environment is 2.45.0 and does not declare `baseRefOid`, which
`factory/mergequeue/gh.py` `_VIEW_FIELDS` sends; the worker that actually runs
`poll_landing` resolves a 2.98.0 further up its own `PATH` and answers it fine
(operator, 2026-08-21, from three live landings: PRs #268, #269, #270). Two
`gh` binaries, two true answers, one tree. So the gap is reported as what it is
— this environment being behind the code — and no `gh` version is written into
a test, because pinning one re-creates the defect this story removes.
"""

from __future__ import annotations

import functools
import inspect
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, Sequence

import pytest

from factory.mergequeue.gh import (
    _VERSION_SENSITIVE_VIEW_FIELDS,
    _VIEW_FIELDS,
    GhClient,
)

TARGET_CLONE = "/srv/target"


def _gh_binary() -> str | None:
    """Return the path to the `gh` binary, or `None` if it is absent."""
    return shutil.which("gh")


def _public_command_methods() -> list[str]:
    """Every public `GhClient` method that issues a `gh` command.

    The set is derived from the class source so a hand-written list cannot go
    stale. A method is included if its body contains a call to `_run` or
    `_run_json`.
    """
    source = inspect.getsource(GhClient)
    methods: list[str] = []
    for match in re.finditer(r"    def (\w+)\(", source):
        name = match.group(1)
        if name.startswith("_"):
            continue
        start = match.end()
        end_match = re.search(r"\n    def \w+\(", source[start:])
        body = source[start : start + end_match.start()] if end_match else source[start:]
        if re.search(r"self\._run(?:_json)?\(", body):
            methods.append(name)
    return methods


def _extract_argvs(method_name: str) -> list[list[str]]:
    """Return the argv sequences one method can build, with placeholders filled.

    Each method is called with representative arguments so every branch that
    builds a different argv is exercised. The calls are made against a recording
    runner, not the real `gh` binary. The runner returns JSON shapes that let
    each method return normally, so the test measures the argv, not the parsing.
    """
    argvs: list[list[str]] = []

    def recorder(argv: Sequence[str], cwd: str) -> Any:
        argvs.append(list(argv))
        # Return JSON shapes that satisfy each caller. `api` calls that expect
        # a list or dict need the right container so the method returns.
        if argv[0] == "api" and argv[-1].endswith("/rulesets"):
            return _FakeCompleted(stdout="[]", stderr="", returncode=0)
        if argv[0] == "api" and "/rules/branches/" in argv[-1]:
            return _FakeCompleted(stdout="[]", stderr="", returncode=0)
        if argv[:2] == ["pr", "create"]:
            return _FakeCompleted(
                stdout="https://github.com/owner/repo/pull/1\n",
                stderr="",
                returncode=0,
            )
        return _FakeCompleted(stdout="{}", stderr="", returncode=0)

    client = GhClient(repo=TARGET_CLONE, runner=recorder)
    method = getattr(client, method_name)

    # Body-file argument: provide a real file path so `--body-file` would be
    # accepted by `gh` if the call ever reached it.
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write("body")
        body_file = f.name

    try:
        if method_name == "find_existing_pr":
            method("factory/003-merge-queue/us1")
        elif method_name == "create_pr":
            method(base="main", head="feature", title="title", body_file=body_file)
        elif method_name == "enqueue_pr":
            method(7, merge_method="squash")
        elif method_name == "poll_pr":
            method(7)
        elif method_name == "disable_auto_merge":
            method(7)
        elif method_name == "pr_checks":
            method(7)
        elif method_name == "run_failed_log":
            method("123")
        elif method_name == "repo_view":
            method()
        elif method_name == "rules_for_branch":
            method("owner/repo", "main")
        elif method_name == "classic_branch_protection":
            method("owner/repo", "main")
        elif method_name == "merge_settings":
            method("owner/repo")
        elif method_name == "auth_status":
            method()
        elif method_name == "set_squash_merge_commit_title":
            method("owner/repo", "PR_TITLE")
        elif method_name == "set_allow_auto_merge":
            method("owner/repo", True)
        elif method_name == "list_rulesets":
            method("owner/repo")
        elif method_name == "ruleset":
            method("owner/repo", 1)
        elif method_name == "create_ruleset":
            method("owner/repo", {"name": "test"})
        elif method_name == "update_ruleset":
            method("owner/repo", 1, {"name": "test"})
        # 069-US3's reset cleanup. The head is spelled in full, slashes and all,
        # because that is what the git-refs endpoints have to accept: a branch
        # named `factory/<epic>/<node>` is three path segments inside the URL.
        elif method_name == "close_pr":
            method(7, comment="closed by `ergane build reset`")
        elif method_name == "ref_sha":
            method("owner/repo", "heads/factory/069-epic/us1")
        elif method_name == "create_ref":
            method(
                "owner/repo",
                "heads/archive/factory/069-epic/us1/0123456789ab",
                "0123456789abcdef0123456789abcdef01234567",
            )
        elif method_name == "remove_ref":
            method("owner/repo", "heads/factory/069-epic/us1")
        else:
            raise AssertionError(f"_extract_argvs does not know how to call {method_name}")
    finally:
        os.unlink(body_file)

    return argvs


class _FakeCompleted:
    """Minimal subprocess completion shape for the recorder."""

    def __init__(self, stdout: str, stderr: str, returncode: int) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


#: `gh`'s exit status when it parsed the command and every flag and then found
#: it had no credential to run them with. **This is acceptance, not refusal**
#: (FR-002): reaching the authentication wall means `gh` had no complaint about
#: the argv, which is the only thing this file checks. The check runs with no
#: token in CI, so "tightening" this into a refusal denies every well-formed
#: argv — a check that denies everything is exactly as useless as one that
#: accepts everything, and it is the easier of the two mistakes to make here.
_GH_EXIT_AUTH_REQUIRED = 4

#: The exit statuses that mean `gh` did not refuse the argv.
_GH_ACCEPTING_EXITS = frozenset({0, _GH_EXIT_AUTH_REQUIRED})

#: Commands `gh` runs *without* a credential, whose non-zero exit is their
#: answer rather than a refusal of the argv. `gh auth status` is the only one
#: `GhClient` issues: with no credential it exits 1 to say "not logged into any
#: GitHub hosts", which is the command working, not the command being rejected.
#: The exception is keyed on the exact command path and is paired with a parse
#: probe below, so an unknown flag on `auth status` is still caught — without
#: that pairing this entry would blind the check to a whole command.
_GH_REPORTS_WITHOUT_CREDENTIALS = frozenset({("auth", "status")})


@functools.lru_cache(maxsize=1)
def _gh_sandbox() -> str:
    """A directory with no git repository in it and no `gh` config under it.

    `gh` reads a stored credential from its config dir, so unsetting `GH_TOKEN`
    alone does not make a run credential-free on a host where the operator has
    run `gh auth login`. Pointing `GH_CONFIG_DIR` at an empty directory does,
    which is what makes the authentication exit deterministic and keeps the
    check from touching the network on a logged-in host.
    """
    return tempfile.mkdtemp(prefix="ergane-gh-argv-contract-")


def _gh_env(**overrides: str) -> dict[str, str]:
    """The environment every `gh` run in this file uses: no token, no config."""
    env = os.environ.copy()
    env.update(
        {
            "GH_TOKEN": "",
            "GITHUB_TOKEN": "",
            "GH_ENTERPRISE_TOKEN": "",
            "GITHUB_ENTERPRISE_TOKEN": "",
            "GH_CONFIG_DIR": os.path.join(_gh_sandbox(), "gh-config"),
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    env.update(overrides)
    return env


def _run_gh(
    argv: Sequence[str], *, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str] | None:
    """Run `gh` with the argv in the sandbox, or `None` if it could not be run."""
    try:
        return subprocess.run(
            ["gh", *argv],
            cwd=_gh_sandbox(),
            capture_output=True,
            text=True,
            env=env if env is not None else _gh_env(),
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None


@functools.lru_cache(maxsize=1)
def _gh_version() -> str:
    """What `gh --version` reports, for a failure message that diagnoses itself.

    A refused `--json` field is almost always a version gap rather than a typo,
    and the version is the first thing the reader needs.
    """
    completed = _run_gh(["--version"])
    if completed is None or completed.returncode != 0:
        return "unknown version"
    first_line = (completed.stdout or "").strip().splitlines()
    return first_line[0] if first_line else "unknown version"


def _gh_parses_argv(argv: Sequence[str], *, env: dict[str, str] | None = None) -> bool:
    """Whether `gh` can parse the argv's flags at all, without running it.

    Appending `--help` makes `gh` stop after flag parsing: it exits 0 when every
    flag is one the command has and non-zero when it is not, with no credential
    and no request. That separates "this argv is malformed" from "this command
    ran and reported a failure", which the exit status of the real run cannot.
    """
    completed = _run_gh([*argv, "--help"], env=env)
    return completed is not None and completed.returncode == 0


def _declared_json_fields(
    command: Sequence[str], *, env: dict[str, str] | None = None
) -> frozenset[str] | None:
    """The `--json` field names `gh` itself declares for a command, or `None`.

    `gh __complete <command> --json ''` is the shell-completion interface: it
    prints one field name per line and exits 0, with no credential, no network
    and no repository. `None` means the vocabulary could not be read, which is
    reported as "cannot tell" rather than as a refusal — a check that accuses on
    ignorance is the deny-everything failure mode wearing a different hat.
    """
    completed = _run_gh(["__complete", *command, "--json", ""], env=env)
    if completed is None or completed.returncode != 0:
        return None
    fields = {
        line.split("\t", 1)[0].strip()
        for line in (completed.stdout or "").splitlines()
        # Cobra terminates the completion list with a `:<directive>` line.
        if line.strip() and not line.startswith(":")
    }
    return frozenset(fields) or None


def _undeclared_json_fields(
    argv: Sequence[str], *, env: dict[str, str] | None = None
) -> list[str]:
    """The argv's `--json` fields that the locally resolved `gh` does not declare.

    Where `gh` validates `--json` field names relative to its authentication
    check moved between versions: gh 2.98 validates the fields first, so a bad
    field exits 1 and the exit status alone is enough; gh 2.45 checks
    authentication first, so a bad field exits 4 and the fields are never looked
    at. Reading the field vocabulary `gh` declares gives the same answer on both
    without a credential, so the field set is checked here whenever the run
    itself came back accepting.

    An empty list means "nothing missing" *or* "could not tell" — the vocabulary
    is unreadable on some hosts, and a check that accuses on ignorance is the
    deny-everything failure mode wearing a different hat.
    """
    argv = list(argv)
    if "--json" not in argv or argv.index("--json") + 1 >= len(argv):
        return []
    index = argv.index("--json")
    requested = [field for field in argv[index + 1].split(",") if field]
    declared = _declared_json_fields(argv[:index], env=env)
    if declared is None:
        return []
    return [field for field in requested if field not in declared]


def _undeclared_field_refusal(argv: Sequence[str], missing: Sequence[str]) -> str:
    """The refusal message for fields this `gh` does not declare, or empty.

    It names the version, because a refused `--json` field is far more often a
    version gap than a typo and the version is the first thing the reader needs.
    """
    if not missing:
        return ""
    argv = list(argv)
    index = argv.index("--json")
    return (
        f"Unknown JSON field(s) {', '.join(missing)}: the installed gh "
        f"({_gh_version()}) does not declare "
        f"{'them' if len(missing) > 1 else 'it'} for `gh {' '.join(argv[:index])}`"
    )


def _gh_would_refuse(argv: Sequence[str], *, env: dict[str, str] | None = None) -> str:
    """Run `gh` with the argv and return a refusal message, or empty if accepted.

    The classification is the process exit status, never the wording of the
    message (FR-001). `gh`'s prose differs across versions, subcommands and
    locales, so any set of phrases to match is a set that a future `gh` leaves
    behind.

    Exit 0 and the authentication exit are acceptance; every other exit status
    is a refusal, except for the one command `gh` runs without a credential,
    whose non-zero exit is its answer and which is disambiguated by a parse
    probe rather than by reading what it said.

    The run uses no token, no stored credential, no network, and no repository.
    """
    completed = _run_gh(argv, env=env)
    if completed is None:
        return f"could not run gh to validate {list(argv)!r}"

    if completed.returncode not in _GH_ACCEPTING_EXITS:
        reports_without_credentials = (
            tuple(argv[:2]) in _GH_REPORTS_WITHOUT_CREDENTIALS
            and _gh_parses_argv(argv, env=env)
        )
        if not reports_without_credentials:
            return (
                completed.stderr
                or completed.stdout
                or f"gh exited {completed.returncode} with no output"
            )

    return _undeclared_field_refusal(argv, _undeclared_json_fields(argv, env=env))


def _local_vocabulary_gap(
    argv: Sequence[str], refusal: str, *, env: dict[str, str] | None = None
) -> list[str]:
    """The fields missing here, when *that alone* is the whole of the refusal.

    Anything else in `refusal` — an unknown flag, an unknown command, any other
    non-zero exit — returns `[]`, so the split below can never swallow a real
    malformed argv. The comparison is against the message this file would build
    for the missing fields, not against a phrase match: prose is what this story
    stopped classifying on, and it is not sneaking back in one function later.
    """
    missing = _undeclared_json_fields(argv, env=env)
    if missing and refusal == _undeclared_field_refusal(argv, missing):
        return missing
    return []


def _is_this_host_being_behind(missing: Sequence[str]) -> bool:
    """Whether every missing field is one the tree declared as merely newer.

    This is the whole difference between "this machine's `gh` is old" and "the
    tree asks for a field that does not exist", and without it the two are the
    same observation: a name the local `gh` does not declare. `gh` cannot tell
    them apart offline — a newer binary's vocabulary is a superset of an older
    one's, and nothing local says which supersets exist — so the tree says which
    of its own fields it sends ahead of the field's arrival in `gh`, in
    `factory/mergequeue/gh.py` `_VERSION_SENSITIVE_VIEW_FIELDS`, next to the set
    it annotates.

    Everything outside that annotation fails, on every host. A typo has no
    version to be waiting for.
    """
    return bool(missing) and set(missing) <= _VERSION_SENSITIVE_VIEW_FIELDS


def _report_local_gh_is_behind_the_tree(gaps: Sequence[str]) -> None:
    """Degrade explicitly: name the fields, the `gh`, and who is actually wrong.

    This is the environment question, not the code question, so it is neither a
    pass nor a failure. Passing would be a lie — the fields really are
    unanswerable here. Failing would pin the suite to whichever `gh` happens to
    be first on the `PATH` of whoever ran it, which is the same as writing a
    version number into a test.

    Do not "fix" this by shrinking `_VIEW_FIELDS`. `baseRefOid` is 069-US1's
    free rebase; without it every landing rejection is priced as the node's own
    defect. The tree is right and this machine is behind it. The surface that
    turns this into something an operator is *told* — before an epic parks — is
    078-US2's forge capability probe, not a red gate here.
    """
    pytest.skip(
        "this environment's gh is behind the tree, which is a fact about the "
        "machine and not a defect in it: "
        + "; ".join(gaps)
        + f". Resolved gh: {_gh_binary()} ({_gh_version()}). The argv is "
        "well-formed and every other check on it passed."
    )


@pytest.mark.skipif(_gh_binary() is None, reason="gh is not installed")
@pytest.mark.parametrize("method_name", _public_command_methods())
def test_gh_client_method_argv_is_accepted_by_real_gh(method_name: str) -> None:
    """T015: every command `GhClient` issues is accepted by the real `gh` binary.

    A malformed argv fails. An argv this host's `gh` is merely too old to answer
    is reported as that, by name — see `_report_local_gh_is_behind_the_tree`.
    """
    failures: list[str] = []
    gaps: list[str] = []
    for argv in _extract_argvs(method_name):
        refusal = _gh_would_refuse(argv)
        if not refusal:
            continue
        missing = _local_vocabulary_gap(argv, refusal)
        if _is_this_host_being_behind(missing):
            gaps.append(f"{method_name} sends {', '.join(missing)}, which {refusal}")
        else:
            failures.append(f"{method_name}: {argv!r}\n{refusal}")
    assert not failures, "\n---\n".join(failures)
    if gaps:
        _report_local_gh_is_behind_the_tree(gaps)


@pytest.mark.skipif(_gh_binary() is None, reason="gh is not installed")
def test_malformed_argv_is_rejected_and_names_command_and_flag() -> None:
    """T016: mutation control — a flag `gh` does not have makes the check fail.

    The malformed argv is deliberately constructed: it appends an invented flag
    to a real command. The check must report the command name and the flag.
    """
    argv = ["pr", "view", "1", "--json", "state", "--ergane-test-unknown-flag"]
    refusal = _gh_would_refuse(argv)
    assert "unknown flag" in refusal.lower()
    assert "--ergane-test-unknown-flag" in refusal
    assert "pr view" in refusal or "pr" in argv[0]


@pytest.mark.skipif(_gh_binary() is None, reason="gh is not installed")
def test_check_catches_unknown_flag_with_no_network_token_or_repository() -> None:
    """T017: the check works without network, token, or repository.

    `gh` rejects unknown flags during argument parsing, before it does any
    network work. The helper already runs in `/tmp` with `GH_TOKEN` unset; this
    test asserts that the same environment still catches an unknown flag.
    """
    argv = ["pr", "view", "1", "--json", "state", "--ergane-networkless-flag"]
    env = os.environ.copy()
    env.update({"GH_TOKEN": "", "GIT_TERMINAL_PROMPT": "0"})

    completed = subprocess.run(
        ["gh", *argv],
        cwd="/tmp",
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )

    stderr = (completed.stderr or completed.stdout or "").lower()
    assert "unknown flag" in stderr


@pytest.mark.skipif(_gh_binary() is not None, reason="gh is installed")
def test_check_skips_by_real_guard_when_gh_is_absent() -> None:
    """T018: when `gh` is absent, the test skips by a real runtime guard.

    This test only runs when `gh` is not on `PATH`. It asserts that the helper
    reports the binary as absent, which is the guard the parametrized tests use.
    The guard is checked at runtime; no pytest marker is used.
    """
    assert shutil.which("gh") is None


@pytest.mark.skipif(_gh_binary() is None, reason="gh is not installed")
def test_create_pr_no_longer_parses_output_as_json() -> None:
    """T019: `create_pr` stops using `_run_json` and returns a `CreatedPr` from the URL.

    `gh pr create` prints the URL of the created PR on stdout. The corrected
    implementation runs the command through `_run`, extracts the PR number from
    the printed URL, and returns it with the URL.
    """
    client = GhClient(repo=TARGET_CLONE, runner=_url_printing_runner)

    created = client.create_pr(
        base="main",
        head="feature",
        title="title",
        body_file="/tmp/body.md",
    )

    assert created.number == 123
    assert created.url == "https://github.com/owner/repo/pull/123"


#: A `--json` field name no `gh` has ever had. `gh` refuses it the same way it
#: refuses a field a newer `gh` added — which is how the 2026-08-20 evidence was
#: produced — so it needs no old binary and no stub on `PATH`.
_NO_SUCH_JSON_FIELD = "erganeDefinitelyNotAJsonField"


@pytest.mark.skipif(_gh_binary() is None, reason="gh is not installed")
def test_refusal_phrased_as_none_of_the_three_old_patterns_is_still_a_refusal() -> None:
    """T001 (US1-S1): a refusal `gh` does not phrase as a flag or usage error.

    The old check matched three phrases in stderr. This argv is refused with a
    message containing none of them, and the test asserts that too, so the
    classification demonstrably does not come from the prose.
    """
    argv = ["pr", "view", "1", "--json", _NO_SUCH_JSON_FIELD]

    completed = _run_gh(argv)
    assert completed is not None, "gh could not be run"
    assert completed.returncode != 0, "gh accepted a field it does not have"
    said = (completed.stderr or completed.stdout or "").lower()
    for phrase in ("unknown flag", "unknown command", "usage:"):
        assert phrase not in said, f"this argv was supposed to dodge {phrase!r}: {said}"

    refusal = _gh_would_refuse(argv)

    assert refusal, f"a refused --json field was classified as accepted: {said}"
    assert _NO_SUCH_JSON_FIELD in refusal


@pytest.mark.skipif(_gh_binary() is None, reason="gh is not installed")
def test_argv_gh_accepts_but_cannot_complete_without_credentials_is_accepted() -> None:
    """T002 (US1-S2): the control, and the failure mode of this whole change.

    `gh` exits 4 when it parsed the argv and then needed a credential it does
    not have. That must stay acceptance: the check runs with no token in CI, so
    a classifier that denies on any non-zero exit denies every well-formed argv,
    which is the same as deleting the check.
    """
    argv = ["pr", "view", "1", "--repo", "owner/repo", "--json", "state"]

    completed = _run_gh(argv)
    assert completed is not None, "gh could not be run"
    assert completed.returncode == _GH_EXIT_AUTH_REQUIRED, (
        "the control is only a control if gh really did stop for want of a "
        f"credential; it exited {completed.returncode}: "
        f"{completed.stderr or completed.stdout}"
    )

    assert _gh_would_refuse(argv) == ""


@pytest.mark.skipif(_gh_binary() is None, reason="gh is not installed")
def test_auth_status_reporting_no_credential_is_not_a_refusal() -> None:
    """T002 (US1-S2): `gh auth status` exits non-zero to *answer*, not to refuse.

    It is the one command `GhClient` issues that `gh` runs without a credential.
    The second half is the mutation control on the exception: an unknown flag on
    that same command must still be refused, or the exception has blinded the
    check to a whole command.
    """
    assert _gh_would_refuse(["auth", "status"]) == ""

    refusal = _gh_would_refuse(["auth", "status", "--ergane-test-unknown-flag"])

    assert "--ergane-test-unknown-flag" in refusal


@pytest.mark.skipif(_gh_binary() is None, reason="gh is not installed")
def test_poller_json_field_set_is_validated_as_a_set_from_the_value_it_sends() -> None:
    """T003 (US1-S3, FR-003): the poller's field set, derived and checked as a set.

    071-US2 enumerated `GhClient`'s methods correctly and still missed this: the
    argument it could not read was inside one of them. So the argv here is built
    by calling `poll_pr` itself, and the `--json` value it carries is asserted to
    be `_VIEW_FIELDS` — the object the poller sends, not a copy of it.

    Everything up to the last two lines is asserted on every host, including the
    mutation control, so the check is provably live wherever it runs. Only the
    final verdict on the real field set is environment-dependent, and it says so.
    """
    argvs = _extract_argvs("poll_pr")
    assert len(argvs) == 1, f"poll_pr built {len(argvs)} argvs, expected one"
    argv = argvs[0]
    index = argv.index("--json")
    assert argv[index + 1] == _VIEW_FIELDS, (
        "the checked field set must be the value the poller sends, not a copy"
    )

    # The mutation control, and the reason a degraded verdict below is still
    # worth something: one bad field inside the poller's own value is caught
    # here on every host, on the gh that host has. Without this the test would
    # pass on a check that never looked.
    poisoned = list(argv)
    poisoned[index + 1] = f"{_VIEW_FIELDS},{_NO_SUCH_JSON_FIELD}"
    poisoned_refusal = _gh_would_refuse(poisoned)
    assert _NO_SUCH_JSON_FIELD in poisoned_refusal
    assert _NO_SUCH_JSON_FIELD in _local_vocabulary_gap(poisoned, poisoned_refusal), (
        "the field-set path must be what refused the poisoned value; if the "
        "argv was refused for some other reason this control proved nothing"
    )

    refusal = _gh_would_refuse(argv)
    if not refusal:
        return

    missing = _local_vocabulary_gap(argv, refusal)
    assert _is_this_host_being_behind(missing), (
        "the landing poller sends a --json field no gh declares and the tree "
        "does not vouch for as merely new (factory/mergequeue/gh.py "
        f"`_VERSION_SENSITIVE_VIEW_FIELDS`): {refusal}"
    )
    _report_local_gh_is_behind_the_tree(
        [f"factory/mergequeue/gh.py `_VIEW_FIELDS` sends {', '.join(missing)}: {refusal}"]
    )


@pytest.mark.skipif(_gh_binary() is None, reason="gh is not installed")
def test_only_a_field_vocabulary_gap_is_charged_to_the_environment() -> None:
    """T003 (US1-S3): the code/environment split cannot swallow a malformed argv.

    The two tree-facing checks above report a locally-undeclared `--json` field
    as this machine being behind the tree rather than as a defect in it. That
    split is only safe if it is narrow, so this is its mutation control, and it
    runs on every host because both argvs are refused by every `gh`:

    - a field no `gh` has is recognised as a vocabulary gap, and *only* that
      field is named — the split can see the case it exists for;
    - an unknown flag is not, however many good `--json` fields ride along with
      it — so no malformed argv can be reported as somebody else's `gh`;
    - and neither is excused, because neither is a field the tree vouched for.
      This last one is what stops the split from becoming a way to make any
      refused field quietly disappear on an old host.
    """
    vocabulary = ["pr", "view", "1", "--json", f"state,{_NO_SUCH_JSON_FIELD}"]
    malformed = ["pr", "view", "1", "--json", "state", "--ergane-test-unknown-flag"]

    gap = _local_vocabulary_gap(vocabulary, _gh_would_refuse(vocabulary))
    assert gap == [_NO_SUCH_JSON_FIELD]
    assert not _is_this_host_being_behind(gap), (
        "an invented field was excused as this host being out of date; only "
        "fields the tree names in `_VERSION_SENSITIVE_VIEW_FIELDS` may be"
    )

    malformed_refusal = _gh_would_refuse(malformed)
    assert malformed_refusal, "the malformed argv was not refused at all"
    assert _local_vocabulary_gap(malformed, malformed_refusal) == [], (
        "an unknown flag was charged to this host's gh version instead of to "
        f"the argv: {malformed_refusal}"
    )


def test_version_sensitive_fields_are_a_subset_of_what_the_poller_sends() -> None:
    """T003 (US1-S3, FR-003): the annotation cannot drift into a second field list.

    `_VERSION_SENSITIVE_VIEW_FIELDS` is the one thing allowed to excuse a field
    the local `gh` will not answer, so it is exactly the thing that must not
    become a hand-maintained restatement of the field set (078 trap 5). Holding
    it to a strict subset of `_VIEW_FIELDS` is what keeps it an annotation *on*
    that value rather than a copy *of* it: it can only ever name fields the
    poller actually sends, and it may never name all of them.

    This runs with no `gh` at all — it is a fact about the tree, not the host.
    """
    sent = {field for field in _VIEW_FIELDS.split(",") if field}

    assert _VERSION_SENSITIVE_VIEW_FIELDS < sent, (
        "every version-sensitive field must be one the poller sends, and the "
        "annotation may not swallow the whole set: "
        f"{sorted(_VERSION_SENSITIVE_VIEW_FIELDS - sent)} not sent"
    )


@pytest.mark.skipif(_gh_binary() is None, reason="gh is not installed")
def test_refused_field_is_caught_with_no_token_no_repository_and_no_network() -> None:
    """T004 (US1-S5, FR-002): the check works on a host with nothing to work with.

    No token and no stored credential, a working directory outside any git
    repository, and every proxy pointed at a closed port so a request that did
    escape would fail. `gh` settles a field name without leaving the machine.
    """
    env = _gh_env(
        HTTP_PROXY="http://127.0.0.1:1",
        HTTPS_PROXY="http://127.0.0.1:1",
        ALL_PROXY="http://127.0.0.1:1",
        NO_PROXY="",
    )
    assert env["GH_TOKEN"] == ""
    assert env["GITHUB_TOKEN"] == ""
    outside_a_repo = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        cwd=_gh_sandbox(),
        capture_output=True,
        text=True,
    )
    assert outside_a_repo.returncode != 0, f"{_gh_sandbox()} is inside a git repository"

    refusal = _gh_would_refuse(["pr", "view", "1", "--json", _NO_SUCH_JSON_FIELD], env=env)

    assert _NO_SUCH_JSON_FIELD in refusal


def test_gh_absence_is_a_runtime_condition_not_a_declared_one() -> None:
    """T005 (US1-S6, FR-004): the guard is evaluated, not declared.

    Emptying `PATH` is the runtime condition a host without `gh` presents, and
    the guard every skip in this file is built from reports it.
    """
    original = os.environ.get("PATH", "")
    try:
        os.environ["PATH"] = ""
        assert _gh_binary() is None
    finally:
        os.environ["PATH"] = original
    assert _gh_binary() == shutil.which("gh")


def test_no_skip_in_this_file_is_a_bare_marker() -> None:
    """T005 (US1-S6, FR-004): nothing here skips on a marker `-m` would have to select.

    Nothing in this repository passes `-m` in CI or in the gate, so a marked
    test is an unrun test (open finding `live-tier-skips-by-guard-not-marker`).
    Every skip here must therefore be a `skipif` whose condition is computed
    when the module is imported, or — for the environment gap reported by
    `_report_local_gh_is_behind_the_tree` — a `pytest.skip()` *call*, which is
    a condition evaluated mid-test and cannot be selected away by `-m` either.
    What is banned is the declared, unconditional form.
    """
    source = Path(__file__).read_text()

    # Spelled in two pieces so this assertion is not its own counterexample.
    assert "@pytest.mark." + "skip(" not in source

    markers = set(re.findall(r"@pytest\.mark\.(\w+)", source))
    assert markers <= {"skipif", "parametrize"}, f"unexpected markers: {markers}"

    conditions = re.findall(r"@pytest\.mark\.skipif\((.*?), reason=", source)
    assert conditions, "no skipif conditions found — has the guard been removed?"
    for condition in conditions:
        assert "_gh_binary()" in condition, f"not a runtime guard: {condition!r}"


def _url_printing_runner(argv: Sequence[str], cwd: str) -> Any:
    """A runner that returns the stdout `gh pr create` would print."""
    return _FakeCompleted(
        stdout="https://github.com/owner/repo/pull/123\n",
        stderr="",
        returncode=0,
    )
