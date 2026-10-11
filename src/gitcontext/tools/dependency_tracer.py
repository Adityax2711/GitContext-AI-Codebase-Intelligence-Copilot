"""AST-based static function and dependency tracer."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from gitcontext.bug_models import CallTraceInfo
from gitcontext.ingestion import should_ignore_dir, should_ignore_file
from gitcontext.tools.repo_inspector import RepoInspector


class DependencyTracer:
    """Statically analyzes Python ASTs to map function calls, callers, and dependencies."""

    STATIC_ANALYSIS_DISCLAIMER = (
        "Static AST inspection only. Does not perform runtime dynamic dispatch or complete dataflow analysis."
    )

    def __init__(self, repo_inspector: RepoInspector) -> None:
        self.inspector = repo_inspector
        self.repo_path = repo_inspector.repo_path

    def _get_py_files(self) -> List[Path]:
        return [
            p
            for p in self.repo_path.rglob("*.py")
            if not any(should_ignore_dir(part) for part in p.parent.parts)
            and not should_ignore_file(p.name)
        ]

    def _extract_call_name(
        self,
        node: ast.Call,
        imports: Dict[str, str],
        wildcards: Set[str],
    ) -> Tuple[str, bool, Optional[str]]:
        """Extract function/method name from an ast.Call node.

        Returns (target_name, is_ambiguous, ambiguity_reason).
        """
        func_expr = node.func

        # Direct name call: e.g. calculate_tax(...)
        if isinstance(func_expr, ast.Name):
            func_id = func_expr.id
            if func_id in imports:
                # Imported symbol: e.g. 'hash_user_password' imported from 'auth'
                return imports[func_id], False, None
            if wildcards:
                return (
                    func_id,
                    True,
                    f"Name '{func_id}' may originate from wildcard import(s): {', '.join(sorted(wildcards))}",
                )
            return func_id, False, None

        # Attribute call: e.g. self.do_something(...) or auth.verify_password(...) or obj.method(...)
        if isinstance(func_expr, ast.Attribute):
            attr_name = func_expr.attr
            if isinstance(func_expr.value, ast.Name):
                val_id = func_expr.value.id
                if val_id == "self":
                    return f"self.{attr_name}", False, None
                if val_id in imports:
                    return f"{imports[val_id]}.{attr_name}", False, None
                return (
                    f"{val_id}.{attr_name}",
                    True,
                    f"Attribute call on variable '{val_id}' with dynamic/unresolved runtime type",
                )
            return (
                f"<expr>.{attr_name}",
                True,
                "Chained or compound expression before attribute call",
            )

        # Dynamic call: e.g. func_list[0](...) or getattr(...)()
        return (
            "<dynamic_call>",
            True,
            f"Dynamic callable expression of type '{type(func_expr).__name__}'",
        )

    def find_callers(
        self,
        target_symbol: str,
        target_file: Optional[str] = None,
    ) -> List[CallTraceInfo]:
        """Find all caller sites in the repository that invoke target_symbol."""
        clean_target = target_symbol.split(".")[-1]  # bare function name
        results: List[CallTraceInfo] = []

        for py_file in self._get_py_files():
            try:
                content = py_file.read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(content, filename=str(py_file))
                rel_file = self.inspector.to_relative_path(py_file)
                lines = content.splitlines()
            except Exception:
                continue

            # First pass: collect imports in this file
            imports: Dict[str, str] = {}
            wildcards: Set[str] = set()

            for top_node in ast.iter_child_nodes(tree):
                if isinstance(top_node, ast.Import):
                    for alias in top_node.names:
                        asname = alias.asname or alias.name
                        imports[asname] = alias.name
                elif isinstance(top_node, ast.ImportFrom):
                    mod = top_node.module or ""
                    for alias in top_node.names:
                        if alias.name == "*":
                            wildcards.add(mod)
                        else:
                            asname = alias.asname or alias.name
                            target_imp = f"{mod}.{alias.name}" if mod else alias.name
                            imports[asname] = target_imp

            # Second pass: visit functions and find calls
            class CallVisitor(ast.NodeVisitor):
                def __init__(self, owner: DependencyTracer) -> None:
                    self.owner = owner
                    self.scope_stack: List[str] = []

                def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                    self.scope_stack.append(node.name)
                    self.generic_visit(node)
                    self.scope_stack.pop()

                def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
                    self.scope_stack.append(node.name)
                    self.generic_visit(node)
                    self.scope_stack.pop()

                def visit_ClassDef(self, node: ast.ClassDef) -> None:
                    self.scope_stack.append(node.name)
                    self.generic_visit(node)
                    self.scope_stack.pop()

                def visit_Call(self, node: ast.Call) -> None:
                    called_target, is_ambig, ambig_reason = self.owner._extract_call_name(
                        node, imports, wildcards
                    )
                    # Match against target_symbol or bare clean_target
                    matched = False
                    if called_target == target_symbol or called_target == clean_target:
                        matched = True
                    elif called_target.endswith(f".{clean_target}") or called_target.endswith(f".{target_symbol}"):
                        matched = True

                    if matched:
                        current_scope = ".".join(self.scope_stack) if self.scope_stack else "<module>"
                        call_line = getattr(node, "lineno", 1)
                        snippet = lines[call_line - 1].strip() if 0 <= call_line - 1 < len(lines) else ""

                        results.append(
                            CallTraceInfo(
                                caller_file=rel_file,
                                caller_symbol=current_scope,
                                caller_line=call_line,
                                target_symbol=target_symbol,
                                target_file=target_file,
                                call_snippet=snippet,
                                is_ambiguous=is_ambig,
                                ambiguity_reason=ambig_reason,
                            )
                        )
                    self.generic_visit(node)

            visitor = CallVisitor(self)
            visitor.visit(tree)

        return results

    def trace_function_callees(
        self,
        function_name: str,
        file_path: Union[str, Path],
    ) -> Dict[str, Any]:
        """Statically inspect a function definition and extract all calls made from inside it."""
        safe_path = self.inspector.resolve_safe_path(file_path)
        rel_file = self.inspector.to_relative_path(safe_path)

        try:
            content = safe_path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(content, filename=str(safe_path))
            lines = content.splitlines()
        except Exception as e:
            return {
                "file_path": rel_file,
                "function_name": function_name,
                "callees": [],
                "error": str(e),
                "disclaimer": self.STATIC_ANALYSIS_DISCLAIMER,
            }

        imports: Dict[str, str] = {}
        wildcards: Set[str] = set()
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports[alias.asname or alias.name] = alias.name
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                for alias in node.names:
                    if alias.name == "*":
                        wildcards.add(mod)
                    else:
                        imports[alias.asname or alias.name] = f"{mod}.{alias.name}" if mod else alias.name

        callees: List[Dict[str, Any]] = []

        class FuncFinder(ast.NodeVisitor):
            def __init__(self, owner: DependencyTracer) -> None:
                self.owner = owner

            def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                if node.name == function_name or function_name.endswith(f".{node.name}"):
                    self._collect_calls(node)
                self.generic_visit(node)

            def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
                if node.name == function_name or function_name.endswith(f".{node.name}"):
                    self._collect_calls(node)
                self.generic_visit(node)

            def _collect_calls(self, node: Union[ast.FunctionDef, ast.AsyncFunctionDef]) -> None:
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Call) and sub is not node:
                        target_name, is_ambig, ambig_reason = self.owner._extract_call_name(
                            sub, imports, wildcards
                        )
                        line_no = getattr(sub, "lineno", node.lineno)
                        snippet = lines[line_no - 1].strip() if 0 <= line_no - 1 < len(lines) else ""
                        callees.append({
                            "target_symbol": target_name,
                            "line_number": line_no,
                            "call_snippet": snippet,
                            "is_ambiguous": is_ambig,
                            "ambiguity_reason": ambig_reason,
                        })

        finder = FuncFinder(self)
        finder.visit(tree)

        return {
            "file_path": rel_file,
            "function_name": function_name,
            "callees": callees,
            "disclaimer": self.STATIC_ANALYSIS_DISCLAIMER,
        }
