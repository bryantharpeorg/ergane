"""Structural checks for factory/cli/repo.py (US3-S3, FR-004).

The module must not reference a global name that is not imported or defined
inside the module.  This catches the class of defect that shipped US3: a name
used at module or function scope that is not bound by an import.
"""

from __future__ import annotations

import ast
import builtins
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
REPO_CLI_PATH = REPO_ROOT / "factory" / "cli" / "repo.py"


def _local_bindings(target: ast.AST) -> set[str]:
    """Names assigned by an assignment target (handles tuples and starred)."""
    bindings: set[str] = set()
    if isinstance(target, ast.Name):
        bindings.add(target.id)
    elif isinstance(target, (ast.Tuple, ast.List)):
        for elt in target.elts:
            bindings.update(_local_bindings(elt))
    elif isinstance(target, ast.Starred):
        bindings.update(_local_bindings(target.value))
    return bindings


class _ScopeChecker(ast.NodeVisitor):
    """Track local bindings and report any loaded name not bound locally.

    Module-level globals are supplied from the outside; this visitor only
    checks that a name has *some* binding in the current or enclosing scope.
    """

    def __init__(self, module_globals: set[str]) -> None:
        self.module_globals = module_globals
        self.unbound: set[str] = set()
        # Stack of local scope bindings.  Module scope is not on this stack;
        # module globals are consulted explicitly.
        self._scopes: list[set[str]] = []

    def _bind(self, names: set[str]) -> None:
        self._scopes[-1].update(names)

    def _is_bound(self, name: str) -> bool:
        return name in self.module_globals or any(
            name in scope for scope in reversed(self._scopes)
        )

    def _visit_body(self, body: list[ast.stmt], pre_bind: set[str] | None = None) -> None:
        self._scopes.append(set(pre_bind or set()))
        for stmt in body:
            self.visit(stmt)
        self._scopes.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        # Defaults, decorators and annotations are evaluated in the enclosing scope.
        for default in node.args.defaults + node.args.kw_defaults:
            if default is not None:
                self.visit(default)
        for decorator in node.decorator_list:
            self.visit(decorator)
        for arg in node.args.posonlyargs + node.args.args + node.args.kwonlyargs:
            if arg.annotation:
                self.visit(arg.annotation)
        if node.args.vararg and node.args.vararg.annotation:
            self.visit(node.args.vararg.annotation)
        if node.args.kwarg and node.args.kwarg.annotation:
            self.visit(node.args.kwarg.annotation)
        if node.returns:
            self.visit(node.returns)

        # Function body sees the function's own bindings.
        local: set[str] = set()
        for arg in node.args.posonlyargs + node.args.args + node.args.kwonlyargs:
            local.add(arg.arg)
        if node.args.vararg:
            local.add(node.args.vararg.arg)
        if node.args.kwarg:
            local.add(node.args.kwarg.arg)
        self._visit_body(node.body, pre_bind=local)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        # Treat exactly like a synchronous function for binding purposes.
        self.visit_FunctionDef(node)  # type: ignore[arg-type]

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for base in node.bases:
            self.visit(base)
        for decorator in node.decorator_list:
            self.visit(decorator)
        for keyword in node.keywords:
            self.visit(keyword.value)
        self._visit_body(node.body)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        for default in node.args.defaults + node.args.kw_defaults:
            if default is not None:
                self.visit(default)
        local: set[str] = set()
        for arg in node.args.posonlyargs + node.args.args + node.args.kwonlyargs:
            local.add(arg.arg)
        if node.args.vararg:
            local.add(node.args.vararg.arg)
        if node.args.kwarg:
            local.add(node.args.kwarg.arg)
        self._visit_body([ast.Return(value=node.body)], pre_bind=local)

    def visit_comprehension(self, node: ast.comprehension) -> None:
        # Iterables are evaluated in the enclosing scope before the loop variable binds.
        self.visit(node.iter)
        local = _local_bindings(node.target)
        self._visit_body(list(node.ifs) + [node.target], pre_bind=local)

    def visit_ListComp(self, node: ast.ListComp) -> None:
        self._scopes.append(set())
        for gen in node.generators:
            self.visit_comprehension(gen)
        self.visit(node.elt)
        self._scopes.pop()

    def visit_SetComp(self, node: ast.SetComp) -> None:
        self._scopes.append(set())
        for gen in node.generators:
            self.visit_comprehension(gen)
        self.visit(node.elt)
        self._scopes.pop()

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        self._scopes.append(set())
        for gen in node.generators:
            self.visit_comprehension(gen)
        self.visit(node.elt)
        self._scopes.pop()

    def visit_DictComp(self, node: ast.DictComp) -> None:
        self._scopes.append(set())
        for gen in node.generators:
            self.visit_comprehension(gen)
        self.visit(node.key)
        self.visit(node.value)
        self._scopes.pop()

    def visit_Assign(self, node: ast.Assign) -> None:
        self.visit(node.value)
        # Guarded like `visit_AnnAssign` below, and for the same reason: module
        # scope is not on the stack, so a plain assignment at module level has
        # nothing to bind into.  Those names are already supplied from the
        # outside by `_module_global_bindings`.  Unguarded, the first
        # module-level constant added to `factory/cli/repo.py` turned this guard
        # into an `IndexError` — a checker that can neither pass nor fail is not
        # a checker (034 US5).
        if not self._scopes:
            return
        for target in node.targets:
            self._bind(_local_bindings(target))

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value:
            self.visit(node.value)
        if node.annotation:
            self.visit(node.annotation)
        if self._scopes:
            self._bind(_local_bindings(node.target))

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self.visit(node.value)
        self.visit(node.target)
        if self._scopes:
            self._bind(_local_bindings(node.target))

    def visit_For(self, node: ast.For) -> None:
        self.visit(node.iter)
        if self._scopes:
            self._bind(_local_bindings(node.target))
        for stmt in node.body + node.orelse:
            self.visit(stmt)

    def visit_With(self, node: ast.With) -> None:
        for item in node.items:
            self.visit(item.context_expr)
            if item.optional_vars and self._scopes:
                self._bind(_local_bindings(item.optional_vars))
        for stmt in node.body:
            self.visit(stmt)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.type:
            self.visit(node.type)
        if node.name and self._scopes:
            self._bind({node.name})
        for stmt in node.body:
            self.visit(stmt)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load) and not self._is_bound(node.id):
            self.unbound.add(node.id)


def _module_global_bindings(tree: ast.AST) -> set[str]:
    """All names bound at module scope by import or definition."""
    bindings: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                bindings.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                bindings.add(alias.asname or alias.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bindings.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                bindings.update(_local_bindings(target))
        elif isinstance(node, ast.AnnAssign):
            bindings.update(_local_bindings(node.target))
    return bindings


def test_repo_cli_module_references_only_imported_or_defined_names() -> None:
    """Every global name referenced by factory/cli/repo.py is bound in the file.

    This is the general form of the check that would have caught the missing
    `import os` in US3.  It walks the module's AST, tracking scope, and fails on
    any name loaded without a binding in the current or enclosing scope.
    """
    source = REPO_CLI_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(REPO_CLI_PATH))

    module_globals = _module_global_bindings(tree)
    checker = _ScopeChecker(module_globals)
    checker.visit(tree)

    allowed = set(dir(builtins)) | {"__name__", "__doc__", "__file__", "__annotations__"}
    unbound = checker.unbound - allowed

    assert not unbound, f"factory/cli/repo.py references unbound global names: {sorted(unbound)}"


def test_the_checker_survives_a_module_level_plain_assignment() -> None:
    """The checker must report on a module with a constant in it, not crash.

    `visit_AnnAssign` was guarded against an empty scope stack from the start and
    `visit_Assign` was not, so the checker above raised `IndexError` the moment
    `factory/cli/repo.py` gained its first plain module-level constant — passing
    for every module that happened not to have one.  This is the case that was
    never exercised: a constant, and a genuine unbound name after it, which must
    still be found.
    """
    tree = ast.parse("SOME_CONSTANT = 'x'\n\ndef f():\n    return missing_name\n")
    checker = _ScopeChecker(_module_global_bindings(tree))
    checker.visit(tree)

    assert checker.unbound == {"missing_name"}
