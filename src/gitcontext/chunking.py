"""Code and documentation chunking engine using AST and Markdown parsing."""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import List, Optional

from gitcontext.models import CodeChunk


def chunk_python_source(
    repo_name: str,
    file_path: str,
    source_code: str,
) -> List[CodeChunk]:
    """Extract code chunks (classes, methods, functions, module preamble) using Python AST.

    Preserves 1-based line numbers and gracefully handles syntax errors.
    """
    if not source_code.strip():
        return []

    lines = source_code.splitlines(keepends=True)
    total_lines = len(lines)

    try:
        tree = ast.parse(source_code)
    except SyntaxError as e:
        # Graceful fallback: return a single file-level chunk without crashing
        return [
            CodeChunk.create(
                repository=repo_name,
                source_type="code",
                file_path=file_path,
                symbol_or_heading=f"<syntax_error_line_{e.lineno or 1}>",
                programming_language="python",
                start_line=1,
                end_line=total_lines,
                content=source_code,
            )
        ]

    chunks: List[CodeChunk] = []
    covered_ranges: List[tuple[int, int]] = []

    def get_source_segment(start_line: int, end_line: int) -> str:
        s = max(1, start_line) - 1
        e = min(total_lines, end_line)
        return "".join(lines[s:e])

    # 1. Walk top-level nodes in the module
    for node in tree.body:
        start_line = getattr(node, "lineno", 1)
        end_line = getattr(node, "end_lineno", start_line)

        if isinstance(node, ast.ClassDef):
            # Class-level chunk
            class_content = get_source_segment(start_line, end_line)
            chunks.append(
                CodeChunk.create(
                    repository=repo_name,
                    source_type="code",
                    file_path=file_path,
                    symbol_or_heading=f"class {node.name}",
                    programming_language="python",
                    start_line=start_line,
                    end_line=end_line,
                    content=class_content,
                )
            )
            covered_ranges.append((start_line, end_line))

            # Method-level chunks inside class
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    m_start = getattr(item, "lineno", start_line)
                    m_end = getattr(item, "end_lineno", m_start)
                    m_content = get_source_segment(m_start, m_end)
                    chunks.append(
                        CodeChunk.create(
                            repository=repo_name,
                            source_type="code",
                            file_path=file_path,
                            symbol_or_heading=f"{node.name}.{item.name}",
                            programming_language="python",
                            start_line=m_start,
                            end_line=m_end,
                            content=m_content,
                        )
                    )

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Top-level function chunk
            func_content = get_source_segment(start_line, end_line)
            chunks.append(
                CodeChunk.create(
                    repository=repo_name,
                    source_type="code",
                    file_path=file_path,
                    symbol_or_heading=f"def {node.name}",
                    programming_language="python",
                    start_line=start_line,
                    end_line=end_line,
                    content=func_content,
                )
            )
            covered_ranges.append((start_line, end_line))

    # 2. If the file has top-level module code/docstring or no functions/classes, add module chunk
    if not chunks:
        chunks.append(
            CodeChunk.create(
                repository=repo_name,
                source_type="code",
                file_path=file_path,
                symbol_or_heading="<module>",
                programming_language="python",
                start_line=1,
                end_line=total_lines,
                content=source_code,
            )
        )
    else:
        # Check if there is a module docstring or top-level code before the first definition
        first_def_start = min(s for s, _ in covered_ranges)
        if first_def_start > 1:
            preamble = get_source_segment(1, first_def_start - 1).strip()
            if preamble:
                chunks.insert(
                    0,
                    CodeChunk.create(
                        repository=repo_name,
                        source_type="code",
                        file_path=file_path,
                        symbol_or_heading="<module_preamble>",
                        programming_language="python",
                        start_line=1,
                        end_line=first_def_start - 1,
                        content=get_source_segment(1, first_def_start - 1),
                    ),
                )

    return chunks


HEADING_REGEX = re.compile(r"^(#{1,6})\s+(.+)$")


def chunk_markdown_source(
    repo_name: str,
    file_path: str,
    markdown_content: str,
) -> List[CodeChunk]:
    """Split Markdown documents by headings while tracking hierarchical heading paths.

    Preserves 1-based start and end line numbers.
    """
    if not markdown_content.strip():
        return []

    lines = markdown_content.splitlines(keepends=True)
    total_lines = len(lines)

    # Find heading positions
    # entries: list of (line_idx_0_based, heading_level, heading_text)
    headings: List[tuple[int, int, str]] = []
    for idx, line in enumerate(lines):
        match = HEADING_REGEX.match(line.strip())
        if match:
            level = len(match.group(1))
            title = match.group(2).strip()
            headings.append((idx, level, title))

    chunks: List[CodeChunk] = []

    # If no headings exist, index whole file as one section
    if not headings:
        return [
            CodeChunk.create(
                repository=repo_name,
                source_type="documentation",
                file_path=file_path,
                symbol_or_heading="Document",
                programming_language="markdown",
                start_line=1,
                end_line=total_lines,
                content=markdown_content,
            )
        ]

    # Content before first heading (e.g. preamble)
    if headings[0][0] > 0:
        preamble_text = "".join(lines[0 : headings[0][0]])
        if preamble_text.strip():
            chunks.append(
                CodeChunk.create(
                    repository=repo_name,
                    source_type="documentation",
                    file_path=file_path,
                    symbol_or_heading="Overview",
                    programming_language="markdown",
                    start_line=1,
                    end_line=headings[0][0],
                    content=preamble_text,
                )
            )

    # Track heading hierarchy (e.g., [H1, H2, H3])
    # hierarchy stack: list of (level, title)
    hierarchy: List[tuple[int, str]] = []

    for i, (line_idx, level, title) in enumerate(headings):
        start_line = line_idx + 1
        end_line = headings[i + 1][0] if (i + 1 < len(headings)) else total_lines

        # Maintain hierarchy stack
        while hierarchy and hierarchy[-1][0] >= level:
            hierarchy.pop()
        hierarchy.append((level, title))

        heading_path = " > ".join(t for _, t in hierarchy)
        section_content = "".join(lines[start_line - 1 : end_line])

        if section_content.strip():
            chunks.append(
                CodeChunk.create(
                    repository=repo_name,
                    source_type="documentation",
                    file_path=file_path,
                    symbol_or_heading=heading_path,
                    programming_language="markdown",
                    start_line=start_line,
                    end_line=end_line,
                    content=section_content,
                )
            )

    return chunks


def chunk_file(
    repo_name: str,
    relative_path: str,
    content: str,
) -> List[CodeChunk]:
    """Dispatcher to chunk code or doc files based on file extension."""
    suffix = Path(relative_path).suffix.lower()
    if suffix == ".py":
        return chunk_python_source(repo_name, relative_path, content)
    elif suffix in {".md", ".markdown"}:
        return chunk_markdown_source(repo_name, relative_path, content)
    return []
