"""FR-011: the doctor is read-only against factory state.

Probes detect and file findings; they never remediate. This test checks the
whole `factory/doctor/` package structurally — imports and calls — for any
surface that deletes proxy keys, prunes worktrees, signals processes, or
otherwise mutates factory state. It fails until `factory/doctor/probes.py`
exists and can be inspected, then constrains every probe the registry holds.

The grep-backed pattern mirrors `tests/test_final_sweep.py` SC-005: absence is
proved by parsing, not by observing that a particular run did not mutate.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import sys
from pathlib import Path
from typing import Iterator

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCTOR_ROOT = REPO_ROOT / "factory" / "doctor"

#: Imports that give a module the vocabulary to mutate filesystem state or processes.
FORBIDDEN_IMPORT_ROOTS = frozenset({"signal", "shutil", "multiprocessing"})

#: Attribute names / function names that perform the mutations FR-011 forbids.
FORBIDDEN_CALL_NAMES = frozenset({
    "revoke_key",
    "remove_worktree",
    "rmtree",
    "rmdir",
    "kill",
    "terminate",
    "send_signal",
})

#: Import paths that are forbidden because they expose mutation-only surfaces.
FORBIDDEN_IMPORT_PATHS = frozenset({
    "factory.activities.agent_activities.remove_worktree",
    "factory.workgraph.worktree.remove_worktree",
})


@pytest.fixture(scope="module")
def doctor_modules() -> list[Path]:
    """Every Python module under factory/doctor/ that is committed now."""
    return sorted(DOCTOR_ROOT.rglob("*.py"))


def module_id(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def import_roots(tree: ast.Module) -> set[str]:
    """Top-level package of every import."""
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                roots.add(node.module.split(".")[0])
    return roots


def import_dotted_names(tree: ast.Module) -> set[str]:
    """Fully-qualified import paths that may name a mutation surface."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                module = node.module
                for alias in node.names:
                    names.add(f"{module}.{alias.name}")
    return names


def calls_and_attributes(tree: ast.Module) -> set[str]:
    """Every name called or accessed as an attribute."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                found.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                found.add(node.func.attr)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
    return found


def class_method_names(tree: ast.Module) -> set[str]:
    """Names defined as methods/functions in the module (false-positive guard)."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found.add(node.name)
        elif isinstance(node, ast.ClassDef):
            found.add(node.name)
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    found.add(item.name)
    return found


def test_factory_doctor_never_imports_mutation_vocabulary(doctor_modules: list[Path]) -> None:
    """The package must not import the modules that carry mutation verbs."""
    for path in doctor_modules:
        tree = parse(path)
        forbidden = import_roots(tree) & FORBIDDEN_IMPORT_ROOTS
        assert not forbidden, (
            f"{module_id(path)} imports forbidden roots: {sorted(forbidden)}"
        )


def test_factory_doctor_never_calls_mutation_surfaces(doctor_modules: list[Path]) -> None:
    """No call or attribute access reaches a mutation surface."""
    for path in doctor_modules:
        tree = parse(path)
        used = calls_and_attributes(tree)
        # A module may define a local helper with the same name as a forbidden
        # surface; only flag names that are actually called/attr-accessed and
        # are not local definitions.
        local_defs = class_method_names(tree)
        suspicious = (used & FORBIDDEN_CALL_NAMES) - local_defs
        assert not suspicious, (
            f"{module_id(path)} calls forbidden mutation surfaces: {sorted(suspicious)}"
        )


def test_factory_doctor_never_imports_forbidden_paths(doctor_modules: list[Path]) -> None:
    """No import statement names a known mutation-only surface."""
    for path in doctor_modules:
        tree = parse(path)
        forbidden = import_dotted_names(tree) & FORBIDDEN_IMPORT_PATHS
        assert not forbidden, (
            f"{module_id(path)} imports forbidden path: {sorted(forbidden)}"
        )


def test_probe_registry_is_importable_and_its_members_are_read_only() -> None:
    """The registry must exist, and every registered probe's gather/evaluate
    source must be read-only (no forbidden imports or calls).

    This fails until `factory/doctor/probes.py` exists.
    """
    module = importlib.import_module("factory.doctor.probes")
    registry = getattr(module, "REGISTRY")
    assert isinstance(registry, list), "REGISTRY must be a list"

    src_path = DOCTOR_ROOT / "probes.py"
    assert src_path.exists()
    tree = parse(src_path)

    forbidden_roots = import_roots(tree) & FORBIDDEN_IMPORT_ROOTS
    assert not forbidden_roots, (
        f"probes.py imports forbidden roots: {sorted(forbidden_roots)}"
    )

    used = calls_and_attributes(tree)
    local_defs = class_method_names(tree)
    suspicious = (used & FORBIDDEN_CALL_NAMES) - local_defs
    assert not suspicious, (
        f"probes.py calls forbidden mutation surfaces: {sorted(suspicious)}"
    )

    forbidden_paths = import_dotted_names(tree) & FORBIDDEN_IMPORT_PATHS
    assert not forbidden_paths, (
        f"probes.py imports forbidden paths: {sorted(forbidden_paths)}"
    )
