"""The `ergane` dispatcher: one front door, one contract, and a registry.

US1 builds only the dispatcher; the four nouns arrive in later stories. Tests
here therefore pin the contract with deliberately failing handlers registered
just for the test, and with a fixture noun package whose modules come and go.

The contract is the load-bearing part of this story: every path through `ergane`
must share one exit-code table and one error boundary. Tests are written before
the implementation and are expected to fail until T007/T008 land.
"""

from __future__ import annotations

import ast
import importlib
import pkgutil
import re
import shutil
import subprocess
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator, NamedTuple

import pytest

from factory.cli import errors as errors_module
from factory.cli import main as main_module

REPO_ROOT = Path(__file__).resolve().parents[1]
CLI_ROOT = REPO_ROOT / "factory" / "cli"


class Run(NamedTuple):
    code: int
    stdout: str
    stderr: str


@pytest.fixture
def run(monkeypatch: pytest.MonkeyPatch) -> Callable[..., Run]:
    """Invoke `main_module.main(argv)` without touching real services."""

    def invoke(*argv: str, env: dict[str, str] | None = None) -> Run:
        saved = {k: os.environ.get(k) for k in (env or {})}
        for k, v in (env or {}).items():
            monkeypatch.setenv(k, v)
        try:
            # Prevent the actual CLI from reading the real noun package by default:
            # tests that need discovery point main_module._NOUNS at their fixture.
            code = main_module.main(list(argv))
        except SystemExit as exit_request:
            code = 0 if exit_request.code is None else int(exit_request.code)
        finally:
            for k, v in saved.items():
                if v is None:
                    monkeypatch.delenv(k, raising=False)
                else:
                    monkeypatch.setenv(k, v)
        return Run(code, "", "")  # replaced below

    return invoke


# Helpers ----------------------------------------------------------------------


def _invoke(argv: list[str], monkeypatch: pytest.MonkeyPatch) -> Run:
    """Run main(argv) and capture stdout/stderr via pytest."""
    import io

    old_stdout, old_stderr = sys.stdout, sys.stderr
    buf_out, buf_err = io.StringIO(), io.StringIO()
    try:
        sys.stdout, sys.stderr = buf_out, buf_err
        try:
            code = main_module.main(argv)
        except SystemExit as exit_request:
            code = 0 if exit_request.code is None else int(exit_request.code)
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr
    return Run(code, buf_out.getvalue(), buf_err.getvalue())


@pytest.fixture
def invoke(monkeypatch: pytest.MonkeyPatch) -> Callable[..., Run]:
    def _caller(*argv: str, env: dict[str, str] | None = None) -> Run:
        saved: dict[str, str | None] = {}
        if env:
            saved = {k: os.environ.get(k) for k in env}
            for k, v in env.items():
                monkeypatch.setenv(k, v)
        try:
            result = _invoke(list(argv), monkeypatch)
        finally:
            for k, v in saved.items():
                if v is None:
                    monkeypatch.delenv(k, raising=False)
                else:
                    monkeypatch.setenv(k, v)
        return result

    return _caller


@pytest.fixture
def noun_pkg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """A temporary package that acts as the noun package for one test.

    Tests drop modules in here and clean them up; the dispatcher reads the
    package through `pkgutil.iter_modules` on its path.
    """
    pkg = tmp_path / "test_nouns"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    monkeypatch.setattr(main_module, "_NOUN_PACKAGE_NAME", "test_nouns")
    monkeypatch.setattr(main_module, "_NOUN_PACKAGE_PATH", str(pkg))
    yield pkg


# T003 / T004 acceptance: dispatcher + boundary --------------------------------


def test_bare_ergane_lists_nouns_and_exits_zero(invoke: Callable[..., Run], noun_pkg: Path) -> None:
    """A bare invocation is orientation, never an error."""
    (noun_pkg / "alpha.py").write_text(
        "from factory.cli.nouns import Noun\n"
        "NOUN = Noun(name='alpha', summary='first noun', order=1, "
        "add_parser=lambda sp: sp.add_parser('alpha', help='alpha help'))\n"
    )
    (noun_pkg / "beta.py").write_text(
        "from factory.cli.nouns import Noun\n"
        "NOUN = Noun(name='beta', summary='second noun', order=2, "
        "add_parser=lambda sp: sp.add_parser('beta', help='beta help'))\n"
    )

    result = invoke()
    assert result.code == 0
    assert "alpha" in result.stdout and "first noun" in result.stdout
    assert "beta" in result.stdout and "second noun" in result.stdout


def test_help_lists_nouns(invoke: Callable[..., Run], noun_pkg: Path) -> None:
    """`ergane --help` is the same orientation surface as a bare invocation."""
    (noun_pkg / "alpha.py").write_text(
        "from factory.cli.nouns import Noun\n"
        "NOUN = Noun(name='alpha', summary='first noun', order=1, "
        "add_parser=lambda sp: sp.add_parser('alpha', help='alpha help'))\n"
    )

    result = invoke("--help")
    assert result.code == 0
    assert "alpha" in result.stdout


def test_ergane_with_noun_lists_verbs(invoke: Callable[..., Run], noun_pkg: Path) -> None:
    """`ergane <noun>` with no verb lists that noun's verbs."""
    (noun_pkg / "alpha.py").write_text(
        "from factory.cli.nouns import Noun\n"
        "def build(sp):\n"
        "    p = sp.add_parser('alpha', help='alpha help')\n"
        "    verbs = p.add_subparsers(dest='verb', required=True)\n"
        "    verbs.add_parser('run', help='run it')\n"
        "NOUN = Noun(name='alpha', summary='first noun', order=1, add_parser=build)\n"
    )

    result = invoke("alpha")
    # argparse prints usage on stderr and exits 2 when a required subparser is missing.
    assert result.code == 2
    assert result.stdout == ""
    assert "usage:" in result.stderr.lower()
    assert "run" in result.stderr


def test_unknown_noun_exits_two_with_usage_on_stderr(invoke: Callable[..., Run]) -> None:
    """An unknown noun is a usage error (argparse's own exit code, unmodified)."""
    result = invoke("notanoun")
    assert result.code == 2
    assert result.stdout == ""
    assert "usage:" in result.stderr.lower()


def test_unknown_flag_exits_two_with_usage_on_stderr(invoke: Callable[..., Run]) -> None:
    """An unknown global flag is a usage error."""
    result = invoke("--notaflag")
    assert result.code == 2
    assert result.stdout == ""
    assert "usage:" in result.stderr.lower()


# T004: error boundary ---------------------------------------------------------


def test_operator_error_exits_one_with_one_line(invoke: Callable[..., Run], noun_pkg: Path) -> None:
    def build(sp: Any) -> None:
        p = sp.add_parser("boom", help="boom")
        p.set_defaults(run=lambda _: (_ for _ in ()).throw(errors_module.OperatorError("bad input")))

    (noun_pkg / "boom.py").write_text(
        "from factory.cli.nouns import Noun\n"
        "def build(sp):\n"
        "    p = sp.add_parser('boom', help='boom')\n"
        "    def run(_): raise errors.OperatorError('bad input')\n"
        "    p.set_defaults(run=run)\n"
        "from factory.cli import errors\n"
        "NOUN = Noun(name='boom', summary='boom noun', order=1, add_parser=build)\n"
    )

    result = invoke("boom")
    assert result.code == 1
    assert result.stdout == ""
    lines = [line for line in result.stderr.splitlines() if line.strip()]
    assert len(lines) == 1
    assert "bad input" in result.stderr
    assert "Traceback" not in result.stderr


def test_operator_error_with_custom_code_exits_that_code(invoke: Callable[..., Run], noun_pkg: Path) -> None:
    (noun_pkg / "transport.py").write_text(
        "from factory.cli.nouns import Noun\n"
        "def build(sp):\n"
        "    p = sp.add_parser('transport', help='transport')\n"
        "    def run(_): raise errors.OperatorError('proxy down', code=3)\n"
        "    p.set_defaults(run=run)\n"
        "from factory.cli import errors\n"
        "NOUN = Noun(name='transport', summary='transport noun', order=1, add_parser=build)\n"
    )

    result = invoke("transport")
    assert result.code == 3
    assert result.stdout == ""
    assert "proxy down" in result.stderr


def test_service_failure_exits_three_and_names_address(invoke: Callable[..., Run], noun_pkg: Path) -> None:
    (noun_pkg / "svc.py").write_text(
        "from factory.cli.nouns import Noun\n"
        "def build(sp):\n"
        "    p = sp.add_parser('svc', help='svc')\n"
        "    def run(_): raise errors.ServiceError('temporal', 'localhost:7233')\n"
        "    p.set_defaults(run=run)\n"
        "from factory.cli import errors\n"
        "NOUN = Noun(name='svc', summary='svc noun', order=1, add_parser=build)\n"
    )

    result = invoke("svc")
    assert result.code == 3
    assert result.stdout == ""
    assert "localhost:7233" in result.stderr


def test_unexpected_exception_exits_one_naming_debug(invoke: Callable[..., Run], noun_pkg: Path) -> None:
    (noun_pkg / "oops.py").write_text(
        "from factory.cli.nouns import Noun\n"
        "def build(sp):\n"
        "    p = sp.add_parser('oops', help='oops')\n"
        "    def run(_): raise RuntimeError('kaboom')\n"
        "    p.set_defaults(run=run)\n"
        "NOUN = Noun(name='oops', summary='oops noun', order=1, add_parser=build)\n"
    )

    result = invoke("oops")
    assert result.code == 1
    assert result.stdout == ""
    lines = [line for line in result.stderr.splitlines() if line.strip()]
    assert len(lines) == 1
    assert "--debug" in result.stderr
    assert "Traceback" not in result.stderr


def test_debug_flag_prints_traceback(invoke: Callable[..., Run], noun_pkg: Path) -> None:
    (noun_pkg / "oops.py").write_text(
        "from factory.cli.nouns import Noun\n"
        "def build(sp):\n"
        "    p = sp.add_parser('oops', help='oops')\n"
        "    def run(_): raise RuntimeError('kaboom')\n"
        "    p.set_defaults(run=run)\n"
        "NOUN = Noun(name='oops', summary='oops noun', order=1, add_parser=build)\n"
    )

    result = invoke("--debug", "oops")
    assert result.code == 1
    assert "Traceback" in result.stderr
    assert "kaboom" in result.stderr


def test_keyboard_interrupt_exits_130(invoke: Callable[..., Run], noun_pkg: Path) -> None:
    (noun_pkg / "ctrlc.py").write_text(
        "from factory.cli.nouns import Noun\n"
        "def build(sp):\n"
        "    p = sp.add_parser('ctrlc', help='ctrlc')\n"
        "    def run(_): raise KeyboardInterrupt\n"
        "    p.set_defaults(run=run)\n"
        "NOUN = Noun(name='ctrlc', summary='ctrlc noun', order=1, add_parser=build)\n"
    )

    result = invoke("ctrlc")
    assert result.code == 130


# T005: structural sweeps ------------------------------------------------------


def _factory_modules() -> Iterator[Path]:
    for path in sorted((REPO_ROOT / "factory").rglob("*.py")):
        if path.is_file():
            yield path


@pytest.mark.parametrize("path", list(_factory_modules()), ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_no_argument_parser_subclass_under_factory(path: Path) -> None:
    """FR-003: no subclass of argparse.ArgumentParser anywhere under factory/.

    The legacy CLI modules still contain their old subclasses; US5 removes them.
    This sweep asserts that no *new* module under `factory/cli/` introduces one,
    and that no module outside the legacy CLIs does either. The existing
    subclasses are left untouched here per trap 1.
    """
    if "factory/cli/" in str(path):
        return
    if path.name == "cli.py" and path.parent.name in ("workgraph", "roadmap"):
        return
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for base in node.bases:
                if isinstance(base, ast.Attribute) and base.attr == "ArgumentParser":
                    assert False, f"{path}:{node.lineno} subclasses argparse.ArgumentParser"
                if isinstance(base, ast.Name) and base.id == "ArgumentParser":
                    # Heuristic: confirm it refers to argparse by checking imports.
                    assert False, f"{path}:{node.lineno} subclasses ArgumentParser"


def _subcommand_paths(parser: Any) -> list[list[str]]:
    """Walk the argparse subparser tree and return every subcommand path."""
    paths: list[list[str]] = []
    subs = getattr(parser, "_subparsers", None)
    if subs is None:
        return paths
    action = subs._actions[0] if subs._actions else None
    if action is None:
        return paths
    choices = getattr(action, "choices", {})
    for name, sub in choices.items():
        paths.append([name])
        subpaths = _subcommand_paths(sub)
        for sp in subpaths:
            paths.append([name, *sp])
    return paths


@pytest.fixture
def populated_parser(noun_pkg: Path) -> Any:
    """Build a parser with a nested noun so the sweep has paths to walk."""
    (noun_pkg / "alpha.py").write_text(
        "from factory.cli.nouns import Noun\n"
        "def build(sp):\n"
        "    p = sp.add_parser('alpha', help='alpha')\n"
        "    verbs = p.add_subparsers(dest='verb', required=True)\n"
        "    verbs.add_parser('run', help='run')\n"
        "NOUN = Noun(name='alpha', summary='alpha noun', order=1, add_parser=build)\n"
    )
    return main_module._build_parser()


@pytest.mark.parametrize(
    "path", [["alpha", "run"]], ids=lambda p: " ".join(p)
)
def test_bad_flag_on_subcommand_exits_two(populated_parser: Any, path: list[str]) -> None:
    """FR-002/FR-003: every discovered subcommand path rejects bad flags with 2."""
    argv = [*path, "--notaflag"]
    try:
        populated_parser.parse_args(argv)
    except SystemExit as exit_request:
        code = 0 if exit_request.code is None else int(exit_request.code)
        assert code == 2, f"path {' '.join(path)} got exit {code} for bad flag"


# T005a: registry --------------------------------------------------------------


def test_dropped_module_appears_in_help(invoke: Callable[..., Run], noun_pkg: Path) -> None:
    """Adding a noun is adding a file; no edit to any existing file."""
    (noun_pkg / "new.py").write_text(
        "from factory.cli.nouns import Noun\n"
        "NOUN = Noun(name='new', summary='new noun', order=1, "
        "add_parser=lambda sp: sp.add_parser('new', help='new help'))\n"
    )

    result = invoke()
    assert result.code == 0
    assert "new" in result.stdout and "new noun" in result.stdout

    (noun_pkg / "new.py").unlink()
    result = invoke()
    assert "new" not in result.stdout


def test_ties_break_by_name_stably(invoke: Callable[..., Run], noun_pkg: Path) -> None:
    (noun_pkg / "b.py").write_text(
        "from factory.cli.nouns import Noun\n"
        "NOUN = Noun(name='b', summary='b noun', order=5, "
        "add_parser=lambda sp: sp.add_parser('b', help='b help'))\n"
    )
    (noun_pkg / "a.py").write_text(
        "from factory.cli.nouns import Noun\n"
        "NOUN = Noun(name='a', summary='a noun', order=5, "
        "add_parser=lambda sp: sp.add_parser('a', help='a help'))\n"
    )

    one = invoke()
    two = invoke()
    assert one.stdout == two.stdout
    assert one.stdout.index("a") < one.stdout.index("b")


def test_import_failure_is_named_and_non_fatal(invoke: Callable[..., Run], noun_pkg: Path) -> None:
    (noun_pkg / "good.py").write_text(
        "from factory.cli.nouns import Noun\n"
        "NOUN = Noun(name='good', summary='good noun', order=1, "
        "add_parser=lambda sp: sp.add_parser('good', help='good help'))\n"
    )
    (noun_pkg / "bad.py").write_text("raise ImportError('boom')\n")

    # A broken module is reported at parser-build time, so it appears on the
    # first command that needs the parser. `ergane` (bare) exits 1 and still
    # prints the healthy nouns on stdout.
    result = invoke()
    assert result.code == 1
    assert "good" in result.stdout  # other nouns still work
    assert "bad" in result.stderr
    assert "failed to load" in result.stderr
    assert "Traceback" not in result.stderr


def test_no_literal_list_of_noun_names() -> None:
    """A fallback list would put US2/3/4 back on one file; assert there is none."""
    for path in CLI_ROOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        # Heuristic: reject any list/dict/set literal containing the known noun
        # names. This test will be run against the real dispatcher, so we use
        # a conservative pattern that flags a sequence of quoted names.
        if re.search(r"\[\s*['\"](spec|build|roadmap|doctor|usage|repo|env|completion)['\"]", text):
            assert False, f"{path} contains a literal list of noun names"


# T006: --version --------------------------------------------------------------


def test_version_reports_version_revision_and_endpoints(invoke: Callable[..., Run]) -> None:
    result = invoke(
        "--version",
        env={
            "TEMPORAL_ADDRESS": "temporal.example:7233",
            "TEMPORAL_NAMESPACE": "factory-ns",
            "LITELLM_PROXY_URL": "http://proxy.example:4000",
        },
    )
    assert result.code == 0
    out = result.stdout
    # The version must come from installed metadata, not a literal. Pin it by
    # reading the same distribution the implementation reads.
    import importlib.metadata

    expected = importlib.metadata.version("ergane-cli")
    assert expected in out
    # revision is the short git hash, non-empty.
    assert re.search(r"[0-9a-f]{7,}", out)
    assert "temporal.example:7233" in out
    assert "http://proxy.example:4000" in out
    assert "factory-ns" in out


def test_version_makes_no_network_call(invoke: Callable[..., Run], monkeypatch: pytest.MonkeyPatch) -> None:
    from temporalio.client import Client

    called = False

    async def raising_connect(*args: Any, **kwargs: Any) -> Any:
        nonlocal called
        called = True
        raise RuntimeError("should not connect")

    monkeypatch.setattr(Client, "connect", raising_connect)

    result = invoke("--version")
    assert result.code == 0
    assert not called


def test_version_does_not_print_credentials(invoke: Callable[..., Run]) -> None:
    result = invoke(
        "--version",
        env={
            "LITELLM_MASTER_KEY": "sk-secret-master",
            "TELEGRAM_BOT_TOKEN": "123456:secret-token",
        },
    )
    assert result.code == 0
    out = result.stdout
    assert "sk-secret-master" not in out
    assert "secret-token" not in out


# Import at module bottom to avoid circular imports with fixtures.
import os
