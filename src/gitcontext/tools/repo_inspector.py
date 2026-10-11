"""Repository inspection tool with strict path traversal prevention."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Sequence, Union

from gitcontext.ingestion import should_ignore_dir, should_ignore_file


class PathTraversalError(SecurityError if "SecurityError" in dir(__builtins__) else PermissionError):
    """Raised when an attempt is made to access a file outside the repository root."""


@dataclass(frozen=True)
class FileInspectionResult:
    """Represents safely read content from a repository file."""

    file_path: str
    start_line: int
    end_line: int
    total_lines: int
    content: str
    lines_with_numbers: List[tuple[int, str]]


@dataclass(frozen=True)
class CodeSearchMatch:
    """Represents a search match in a repository file."""

    file_path: str
    line_number: int
    line_content: str
    surrounding_context: str


@dataclass(frozen=True)
class SymbolDefinition:
    """Represents an AST-discovered function or class definition."""

    name: str
    symbol_type: str  # "function", "async_function", "class", "method"
    file_path: str
    start_line: int
    end_line: int
    docstring: Optional[str]
    parameters: List[str]
    code_excerpt: str


class RepoInspector:
    """Safely inspects files, searches patterns, and discovers symbols inside a repository."""

    def __init__(self, repo_path: Union[str, Path]) -> None:
        self.repo_path = Path(repo_path).resolve()
        if not self.repo_path.exists():
            raise FileNotFoundError(f"Repository path does not exist: {self.repo_path}")
        if not self.repo_path.is_dir():
            raise NotADirectoryError(f"Repository path is not a directory: {self.repo_path}")

    def resolve_safe_path(self, relative_or_abs_path: Union[str, Path]) -> Path:
        """Resolve a file path and strictly enforce containment within repository root.

        Prevents path traversal attacks (e.g. '../', absolute paths pointing outside repo).
        """
        input_path = Path(relative_or_abs_path)
        if input_path.is_absolute():
            resolved = input_path.resolve()
        else:
            resolved = (self.repo_path / input_path).resolve()

        # Enforce that resolved path starts with repo_path
        try:
            resolved.relative_to(self.repo_path)
        except ValueError as err:
            raise PathTraversalError(
                f"Path traversal detected: '{relative_or_abs_path}' resolves outside repository root '{self.repo_path}'"
            ) from err

        return resolved

    def to_relative_path(self, path: Union[str, Path]) -> str:
        """Convert a path into a clean, normalized repository-relative forward-slash path."""
        resolved = self.resolve_safe_path(path)
        rel = resolved.relative_to(self.repo_path)
        return rel.as_posix()

    def read_file(
        self,
        file_path: Union[str, Path],
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
    ) -> FileInspectionResult:
        """Read lines from a file within the repository with optional 1-indexed slicing."""
        safe_path = self.resolve_safe_path(file_path)
        if not safe_path.exists():
            raise FileNotFoundError(f"File not found in repository: {file_path}")
        if not safe_path.is_file():
            raise IsADirectoryError(f"Path is a directory, not a file: {file_path}")

        try:
            raw_text = safe_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            raise IOError(f"Could not read file '{file_path}': {e}") from e

        all_lines = raw_text.splitlines()
        total_lines = len(all_lines)

        s_line = 1 if start_line is None else max(1, start_line)
        e_line = total_lines if end_line is None else min(total_lines, max(s_line, end_line))

        if total_lines == 0:
            return FileInspectionResult(
                file_path=self.to_relative_path(safe_path),
                start_line=1,
                end_line=1,
                total_lines=0,
                content="",
                lines_with_numbers=[],
            )

        selected = all_lines[s_line - 1 : e_line]
        numbered = [(s_line + idx, line) for idx, line in enumerate(selected)]
        content = "\n".join(selected)

        return FileInspectionResult(
            file_path=self.to_relative_path(safe_path),
            start_line=s_line,
            end_line=e_line,
            total_lines=total_lines,
            content=content,
            lines_with_numbers=numbered,
        )

    def search_code(
        self,
        pattern: str,
        is_regex: bool = False,
        case_sensitive: bool = False,
        max_matches: int = 50,
        file_extensions: Optional[Sequence[str]] = None,
    ) -> List[CodeSearchMatch]:
        """Search repository files for matching strings or regular expressions."""
        if not pattern:
            return []

        flags = 0 if case_sensitive else re.IGNORECASE
        compiled_re = re.compile(pattern if is_regex else re.escape(pattern), flags)

        matches: List[CodeSearchMatch] = []
        extensions = set(file_extensions) if file_extensions else None

        for item in self.repo_path.rglob("*"):
            if not item.is_file():
                continue

            # Respect ignore patterns
            if any(should_ignore_dir(part) for part in item.parent.parts):
                continue
            if should_ignore_file(item.name):
                continue
            if extensions and item.suffix.lower() not in extensions:
                continue

            try:
                rel_path = self.to_relative_path(item)
                text = item.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            lines = text.splitlines()
            for line_idx, line in enumerate(lines, start=1):
                if compiled_re.search(line):
                    # Extract surrounding 2 lines before and after
                    c_start = max(0, line_idx - 3)
                    c_end = min(len(lines), line_idx + 2)
                    context_lines = [
                        f"{i+1:4d} | {lines[i]}" for i in range(c_start, c_end)
                    ]
                    context = "\n".join(context_lines)

                    matches.append(
                        CodeSearchMatch(
                            file_path=rel_path,
                            line_number=line_idx,
                            line_content=line,
                            surrounding_context=context,
                        )
                    )
                    if len(matches) >= max_matches:
                        return matches

        return matches

    def find_symbols(
        self,
        name_query: Optional[str] = None,
        file_path: Optional[Union[str, Path]] = None,
    ) -> List[SymbolDefinition]:
        """Discover Python function and class definitions using the AST."""
        symbols: List[SymbolDefinition] = []

        if file_path:
            target_files = [self.resolve_safe_path(file_path)]
        else:
            target_files = [
                p
                for p in self.repo_path.rglob("*.py")
                if not any(should_ignore_dir(part) for part in p.parent.parts)
                and not should_ignore_file(p.name)
            ]

        for py_file in target_files:
            try:
                content = py_file.read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(content, filename=str(py_file))
                rel_file = self.to_relative_path(py_file)
                lines = content.splitlines()
            except Exception:
                continue

            class SymbolVisitor(ast.NodeVisitor):
                def __init__(self, owner: RepoInspector) -> None:
                    self.current_class: Optional[str] = None
                    self.owner = owner

                def visit_ClassDef(self, node: ast.ClassDef) -> None:
                    if not name_query or name_query.lower() in node.name.lower():
                        doc = ast.get_docstring(node)
                        start_l = getattr(node, "lineno", 1)
                        end_l = getattr(node, "end_lineno", start_l)
                        excerpt = "\n".join(lines[start_l - 1 : min(len(lines), start_l + 8)])
                        symbols.append(
                            SymbolDefinition(
                                name=node.name,
                                symbol_type="class",
                                file_path=rel_file,
                                start_line=start_l,
                                end_line=end_l,
                                docstring=doc,
                                parameters=[],
                                code_excerpt=excerpt,
                            )
                        )

                    prev_class = self.current_class
                    self.current_class = node.name
                    self.generic_visit(node)
                    self.current_class = prev_class

                def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                    self._handle_func(node, is_async=False)

                def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
                    self._handle_func(node, is_async=True)

                def _handle_func(
                    self,
                    node: Union[ast.FunctionDef, ast.AsyncFunctionDef],
                    is_async: bool,
                ) -> None:
                    full_name = f"{self.current_class}.{node.name}" if self.current_class else node.name
                    sym_type = "method" if self.current_class else ("async_function" if is_async else "function")

                    if not name_query or (name_query.lower() in node.name.lower() or name_query.lower() in full_name.lower()):
                        doc = ast.get_docstring(node)
                        start_l = getattr(node, "lineno", 1)
                        end_l = getattr(node, "end_lineno", start_l)
                        params = [a.arg for a in node.args.args]
                        excerpt = "\n".join(lines[start_l - 1 : min(len(lines), end_l)])
                        symbols.append(
                            SymbolDefinition(
                                name=full_name,
                                symbol_type=sym_type,
                                file_path=rel_file,
                                start_line=start_l,
                                end_line=end_l,
                                docstring=doc,
                                parameters=params,
                                code_excerpt=excerpt,
                            )
                        )
                    self.generic_visit(node)

            visitor = SymbolVisitor(self)
            visitor.visit(tree)

        return symbols

    def get_surrounding_code(
        self,
        file_path: Union[str, Path],
        target_line: int,
        context_lines: int = 5,
    ) -> str:
        """Return formatted snippet surrounding target line with line numbers."""
        res = self.read_file(
            file_path,
            start_line=max(1, target_line - context_lines),
            end_line=target_line + context_lines,
        )
        output_lines = []
        for line_no, line in res.lines_with_numbers:
            marker = " ->" if line_no == target_line else "   "
            output_lines.append(f"{marker} {line_no:4d} | {line}")
        return "\n".join(output_lines)
