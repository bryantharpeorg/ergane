"""Guard: no workflow-scoped function may read the process environment (US2).

US1 removed the one known read from `factory/roadmap/workflow.py`.  US2's job
is to keep that read from coming back, and to keep it from appearing in any
future workflow module, by guarding the class rather than the instance.

The guard discovers workflow modules by scanning `factory/` for the
`@workflow.defn` decorator, parses each with `ast` (no import side effects),
and flags reads of `os.environ`, `environ.get`, or `os.getenv` inside
functions reachable at workflow scope: methods of the workflow class plus
module-level functions those methods call.

Activity functions and module-import-time reads are intentionally out of
scope: `_store_path` in `factory/activities/notify_activities.py` reads the
environment legitimately in activity context today.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Iterable

import pytest


#: Patterns the guard treats as a process-environment read.
_ENV_READ_FORMS = (
    "os.environ",
    "environ.get",
    "os.getenv",
)


def _is_env_read(node: ast.AST) -> bool:
    """Return True if `node` reads the process environment.

    Matches the forms named by US2:
      - `os.environ` (including `os.environ.get(...)`, `os.environ["X"]`)
      - `environ.get(...)` (from `from os import environ`)
      - `os.getenv(...)`
    """
    # os.environ or os.environ.get / os.environ["X"]
    if isinstance(node, ast.Attribute):
        if (
            isinstance(node.value, ast.Name)
            and node.value.id == "os"
            and node.attr == "environ"
        ):
            return True
    # environ.get(...) (aliased import)
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Attribute):
            if (
                isinstance(func.value, ast.Name)
                and func.value.id == "environ"
                and func.attr == "get"
            ):
                return True
            # os.getenv(...) also appears as an Attribute call.
            if (
                isinstance(func.value, ast.Name)
                and func.value.id == "os"
                and func.attr == "getenv"
            ):
                return True
    return False


def _is_workflow_defn(node: ast.AST) -> bool:
    """True for a class decorated with `@workflow.defn`."""
    if not isinstance(node, ast.ClassDef):
        return False
    for decorator in node.decorator_list:
        if isinstance(decorator, ast.Attribute):
            if (
                isinstance(decorator.value, ast.Name)
                and decorator.value.id == "workflow"
                and decorator.attr == "defn"
            ):
                return True
    return False


def _is_activity_defn(node: ast.AST) -> bool:
    """True for a function decorated with `@activity.defn`."""
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    for decorator in node.decorator_list:
        if isinstance(decorator, ast.Attribute):
            if (
                isinstance(decorator.value, ast.Name)
                and decorator.value.id == "activity"
                and decorator.attr == "defn"
            ):
                return True
    return False


def _top_level_functions(tree: ast.AST) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    """All module-level function definitions, keyed by name."""
    result: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            result[node.name] = node
    return result


def _calls_in(node: ast.AST) -> set[str]:
    """Names of bare function calls inside `node` (e.g. `foo()` -> {'foo'})."""
    called: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            func = child.func
            if isinstance(func, ast.Name):
                called.add(func.id)
    return called


def _env_read_locations(node: ast.AST) -> list[tuple[int, str]]:
    """Return (lineno, text) for every env read inside `node`."""
    locations: list[tuple[int, str]] = []
    for child in ast.walk(node):
        if _is_env_read(child):
            text = ast.unparse(child) if hasattr(ast, "unparse") else type(child).__name__
            locations.append((getattr(child, "lineno", 0), text))
    return locations


def _collect_violations(source: str, module_path: str) -> list[str]:
    """Return human-readable violations in one module's source.

    A violation names the offending module and function (FR-007).
    """
    tree = ast.parse(source)

    # Find every workflow class in this module.
    workflow_classes = [node for node in tree.body if _is_workflow_defn(node)]

    violations: list[str] = []
    module_functions = _top_level_functions(tree)

    for cls in workflow_classes:
        # All methods of the workflow class are in workflow scope.
        methods = [
            node for node in cls.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]

        # Follow calls from those methods to module-level functions.
        reachable_module_functions: set[str] = set()
        for method in methods:
            for name in _calls_in(method):
                if name in module_functions:
                    reachable_module_functions.add(name)

        # Transitive closure through module-level functions.
        frontier = set(reachable_module_functions)
        while frontier:
            name = frontier.pop()
            func = module_functions[name]
            for callee in _calls_in(func):
                if callee in module_functions and callee not in reachable_module_functions:
                    reachable_module_functions.add(callee)
                    frontier.add(callee)

        # Check every reachable function for env reads.
        checked_functions: list[ast.FunctionDef | ast.AsyncFunctionDef] = [
            *methods,
            *(module_functions[name] for name in reachable_module_functions),
        ]

        for func in checked_functions:
            for lineno, text in _env_read_locations(func):
                violations.append(
                    f"{module_path}:{lineno}: {func.name}() reads process environment: {text}"
                )

    return violations


def _discover_workflow_modules(root: Path) -> list[Path]:
    """Find every `.py` file under `root` that defines a Temporal workflow class."""
    modules: list[Path] = []
    for path in root.rglob("*.py"):
        try:
            source = path.read_text(encoding="utf-8")
        except OSError:
            continue
        tree = ast.parse(source)
        if any(_is_workflow_defn(node) for node in tree.body):
            modules.append(path)
    return modules


def assert_no_workflow_env_reads(root: Path) -> None:
    """Scan `root` for workflow modules and assert none read the env at workflow scope.

    Fails with the offending module and function named (FR-007).
    """
    modules = _discover_workflow_modules(root)
    assert modules, f"no workflow modules found under {root}; the scanner must not be blind"

    all_violations: list[str] = []
    for path in modules:
        source = path.read_text(encoding="utf-8")
        all_violations.extend(_collect_violations(source, str(path)))

    if all_violations:
        raise AssertionError(
            "workflow-scoped environment read(s) found:\n" + "\n".join(all_violations)
        )


def _guard_passes(source: str) -> list[str]:
    """Run the per-module guard against a source string; return violations."""
    return _collect_violations(source, "<test>")


# ============================================================================
# T010 — the guard discovers workflow modules and forbids workflow-scope reads
# ============================================================================


def test_guard_discovers_workflow_modules_and_forbids_env_reads() -> None:
    """FR-006/007: scan `factory/` by construction, fail naming module+function."""
    factory_root = Path(__file__).resolve().parent.parent / "factory"
    assert_no_workflow_env_reads(factory_root)


# ============================================================================
# T011 — the guard does not over-reach (FR-008)
# ============================================================================


def test_guard_allows_activity_functions_and_import_time_reads() -> None:
    """FR-008: activity functions and module-level import-time reads are accepted.

    `notify_activities._store_path` reads the environment legitimately in activity
    context; the guard must not flag it just because it lives in the repo.
    """
    source = '''\
from __future__ import annotations

import os
from temporalio import activity, workflow


# Module import time read: accepted.
_IMPORT_PATH = os.environ.get("SOME_VAR", "default")


@activity.defn
async def _store_path() -> str:
    """Activity helper: accepted."""
    return os.environ.get("STORE_PATH", "/tmp")


@workflow.defn
class DemoWorkflow:
    @workflow.run
    async def run(self) -> None:
        # Clean workflow method.
        pass
'''
    violations = _guard_passes(source)
    assert violations == [], (
        "guard flagged legitimate activity/import-time reads:\n"
        + "\n".join(violations)
    )


# ============================================================================
# T012 — two-way evidence (green / red / green)
# ============================================================================

EVIDENCE = '''
The guard was run three times to produce the evidence US2 requires.

1. Green on the fixed tree:

$ uv run pytest tests/test_workflow_env_guard.py -v
============================= test session starts ==============================
platform linux -- Python 3.11.15, pytest-9.1.1, pluggy-1.6.0 -- /home/admin/code/ergane/.factory/worktrees/039-roadmap-workflow-determinism/us2/.venv/bin/python
cachedir: .pytest_cache
rootdir: /home/admin/code/ergane/.factory/worktrees/039-roadmap-workflow-determinism/us2
configfile: pyproject.toml
plugins: asyncio-1.4.0, anyio-4.14.2, asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 2 items

tests/test_workflow_env_guard.py::test_guard_discovers_workflow_modules_and_forbids_env_reads PASSED [ 50%]
tests/test_workflow_env_guard.py::test_guard_allows_activity_functions_and_import_time_reads PASSED [100%]

============================== 2 passed in 0.08s ===============================


2. Red with an `os.environ` read reintroduced into `RoadmapWorkflow.run`:

$ uv run pytest tests/test_workflow_env_guard.py::test_guard_discovers_workflow_modules_and_forbids_env_reads -v
============================= test session starts ==============================
platform linux -- Python 3.11.15, pytest-9.1.1, pluggy-1.6.0 -- /home/admin/code/ergane/.factory/worktrees/039-roadmap-workflow-determinism/us2/.venv/bin/python
cachedir: .pytest_cache
rootdir: /home/admin/code/ergane/.factory/worktrees/039-roadmap-workflow-determinism/us2
configfile: pyproject.toml
plugins: asyncio-1.4.0, anyio-4.14.2, asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 1 item

tests/test_workflow_env_guard.py::test_guard_discovers_workflow_modules_and_forbids_env_reads FAILED [100%]

=================================== FAILURES ===================================
_________ test_guard_discovers_workflow_modules_and_forbids_env_reads __________

    def test_guard_discovers_workflow_modules_and_forbids_env_reads() -> None:
        """FR-006/007: scan `factory/` by construction, fail naming module+function."""
        factory_root = Path(__file__).resolve().parent.parent / "factory"
>       assert_no_workflow_env_reads(factory_root)

tests/test_workflow_env_guard.py:230:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

root = PosixPath('/home/admin/code/ergane/.factory/worktrees/039-roadmap-workflow-determinism/us2/factory')

    def assert_no_workflow_env_reads(root: Path) -> None:
        """Scan `root` for workflow modules and assert none read the env at workflow scope.

        Fails with the offending module and function named (FR-007).
        """
        modules = _discover_workflow_modules(root)
        assert modules, f"no workflow modules found under {root}; the scanner must not be blind"

        all_violations: list[str] = []
        for path in modules:
            source = path.read_text(encoding="utf-8")
            all_violations.extend(_collect_violations(source, str(path)))

        if all_violations:
>           raise AssertionError(
                "workflow-scoped environment read(s) found:\n" + "\n".join(all_violations)
            )
E           AssertionError: workflow-scoped environment read(s) found:
E           /home/admin/code/ergane/.factory/worktrees/039-roadmap-workflow-determinism/us2/factory/roadmap/workflow.py:658: run() reads process environment: os.environ

tests/test_workflow_env_guard.py:212: AssertionError

=========================== short test summary info ============================
FAILED tests/test_workflow_env_guard.py::test_guard_discovers_workflow_modules_and_forbids_env_reads
============================== 1 failed in 0.10s ===============================


3. Green again after reverting the reintroduction:

$ uv run pytest tests/test_workflow_env_guard.py -v
============================= test session starts ==============================
platform linux -- Python 3.11.15, pytest-9.1.1, pluggy-1.6.0 -- /home/admin/code/ergane/.factory/worktrees/039-roadmap-workflow-determinism/us2/.venv/bin/python
cachedir: .pytest_cache
rootdir: /home/admin/code/ergane/.factory/worktrees/039-roadmap-workflow-determinism/us2
configfile: pyproject.toml
plugins: asyncio-1.4.0, anyio-4.14.2, asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 2 items

tests/test_workflow_env_guard.py::test_guard_discovers_workflow_modules_and_forbids_env_reads PASSED [ 50%]
tests/test_workflow_env_guard.py::test_guard_allows_activity_functions_and_import_time_reads PASSED [100%]

============================== 2 passed in 0.08s ===============================
'''

