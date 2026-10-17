"""Tool registry and execution layer for the GitContext AI agent."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Union

from gitcontext.agent.patch import PatchManager, PatchProposal
from gitcontext.indexing import get_default_index_dir, load_index
from gitcontext.models import CodeChunk
from gitcontext.retrieval import hybrid_search
from gitcontext.tools.dependency_tracer import DependencyTracer
from gitcontext.tools.repo_inspector import RepoInspector
from gitcontext.tools.static_analyzer import StaticAnalyzer
from gitcontext.tools.test_runner import TestRunner


@dataclass
class ToolDefinition:
    """Definition of an executable tool for the AI agent."""

    name: str
    description: str
    parameters_schema: Dict[str, Any]
    handler: Callable[[Dict[str, Any]], Dict[str, Any]]

    def to_schema(self) -> Dict[str, Any]:
        """Return standardized OpenAI/Gemini/Anthropic compatible function schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema,
            },
        }


class AgentToolRegistry:
    """Provides safe, controlled execution of repository analysis and code modification tools."""

    def __init__(
        self,
        repo_path: Union[str, Path],
        index_dir: Optional[Path] = None,
        vector_store: Optional[Any] = None,
    ) -> None:
        self.repo_path = Path(repo_path).resolve()
        self.index_dir = index_dir or get_default_index_dir()
        self.vector_store = vector_store

        self.inspector = RepoInspector(self.repo_path)
        self.tracer = DependencyTracer(self.inspector)
        self.analyzer = StaticAnalyzer(self.inspector)
        self.test_runner = TestRunner(self.inspector)
        self.patch_manager = PatchManager(self.inspector, self.test_runner)

        self._tools: Dict[str, ToolDefinition] = {}
        self._register_default_tools()

    def register(self, tool: ToolDefinition) -> None:
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    def list_tools(self) -> List[ToolDefinition]:
        return list(self._tools.values())

    def get_tools_schema(self) -> List[Dict[str, Any]]:
        return [t.to_schema() for t in self._tools.values()]

    def execute(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a registered tool with security handling."""
        tool = self._tools.get(tool_name)
        if not tool:
            return {
                "status": "error",
                "tool": tool_name,
                "error": f"Tool '{tool_name}' not found. Available tools: {list(self._tools.keys())}",
            }
        try:
            result = tool.handler(arguments)
            return {"status": "success", "tool": tool_name, "result": result}
        except Exception as e:
            return {"status": "error", "tool": tool_name, "error": str(e)}

    # -------------------------------------------------------------------------
    # Tool Implementations
    # -------------------------------------------------------------------------

    def _tool_search_codebase(self, args: Dict[str, Any]) -> Dict[str, Any]:
        query = args.get("query", "").strip()
        top_k = int(args.get("top_k", 5))
        if not query:
            return {"matches": [], "message": "Search query was empty."}

        # Load active index chunks
        chunks, _ = load_index(self.index_dir)
        if not chunks:
            # Fallback to direct repo text search
            matches = self.inspector.search_code(query.split()[0], max_matches=top_k)
            return {
                "matches": [
                    {
                        "file_path": m.file_path,
                        "line_number": m.line_number,
                        "content": m.line_content,
                        "context": m.surrounding_context,
                    }
                    for m in matches
                ],
                "source": "text_search_fallback",
            }

        search_res = hybrid_search(query, chunks, top_k=top_k, vector_store=self.vector_store)
        return {
            "matches": [
                {
                    "chunk_id": r.chunk.chunk_id,
                    "file_path": r.chunk.file_path,
                    "symbol": r.chunk.symbol_or_heading,
                    "start_line": r.chunk.start_line,
                    "end_line": r.chunk.end_line,
                    "score": round(r.score, 4),
                    "code_preview": r.chunk.content[:400],
                }
                for r in search_res
            ],
            "total_matches": len(search_res),
            "source": "hybrid_rag",
        }

    def _tool_read_file(self, args: Dict[str, Any]) -> Dict[str, Any]:
        file_path = args.get("file_path", "")
        start_line = args.get("start_line")
        end_line = args.get("end_line")

        res = self.inspector.read_file(
            file_path,
            start_line=int(start_line) if start_line is not None else None,
            end_line=int(end_line) if end_line is not None else None,
        )
        return {
            "file_path": res.file_path,
            "start_line": res.start_line,
            "end_line": res.end_line,
            "total_lines": res.total_lines,
            "content": res.content,
            "numbered_lines": [f"{num:4d} | {line}" for num, line in res.lines_with_numbers],
        }

    def _tool_find_symbols(self, args: Dict[str, Any]) -> Dict[str, Any]:
        name_query = args.get("name_query")
        file_path = args.get("file_path")

        symbols = self.inspector.find_symbols(name_query=name_query, file_path=file_path)
        return {
            "symbols": [
                {
                    "name": s.name,
                    "type": s.symbol_type,
                    "file_path": s.file_path,
                    "start_line": s.start_line,
                    "end_line": s.end_line,
                    "parameters": s.parameters,
                    "docstring": s.docstring,
                    "excerpt": s.code_excerpt[:300],
                }
                for s in symbols[:25]
            ],
            "total_found": len(symbols),
        }

    def _tool_find_callers(self, args: Dict[str, Any]) -> Dict[str, Any]:
        target_symbol = args.get("target_symbol", "")
        target_file = args.get("target_file")
        if not target_symbol:
            return {"callers": [], "message": "target_symbol is required"}

        callers = self.tracer.find_callers(target_symbol=target_symbol, target_file=target_file)
        return {
            "target_symbol": target_symbol,
            "callers": [
                {
                    "caller_file": c.caller_file,
                    "caller_symbol": c.caller_symbol,
                    "caller_line": c.caller_line,
                    "snippet": c.call_snippet,
                    "is_ambiguous": c.is_ambiguous,
                    "ambiguity_reason": c.ambiguity_reason,
                }
                for c in callers
            ],
            "total_callers": len(callers),
        }

    def _tool_inspect_dependencies(self, args: Dict[str, Any]) -> Dict[str, Any]:
        function_name = args.get("function_name", "")
        file_path = args.get("file_path", "")
        if not function_name or not file_path:
            return {"error": "Both function_name and file_path are required"}

        return self.tracer.inspect_function_dependencies(
            function_name=function_name,
            file_path=file_path,
        )

    def _tool_run_static_analysis(self, args: Dict[str, Any]) -> Dict[str, Any]:
        target_path = args.get("target_path")
        findings = self.analyzer.analyze(target_path=target_path)
        return {
            "target": target_path or "entire repository",
            "findings_count": len(findings),
            "findings": [
                {
                    "rule_id": f.rule_id,
                    "message": f.message,
                    "file_path": f.file_path,
                    "start_line": f.start_line,
                    "end_line": f.end_line,
                    "tool": f.tool_source,
                    "severity": f.severity,
                }
                for f in findings[:30]
            ],
        }

    def _tool_run_tests(self, args: Dict[str, Any]) -> Dict[str, Any]:
        test_path = args.get("test_path")
        summary = self.test_runner.run_tests(test_path=test_path)
        return {
            "executed": summary.executed,
            "framework": summary.framework,
            "total_tests": summary.total_tests,
            "passed_tests": summary.passed_tests,
            "failed_tests": summary.failed_tests,
            "errors": summary.error_tests,
            "timed_out": summary.timed_out,
            "failures": [
                {
                    "test_name": fail.test_name,
                    "file_path": fail.file_path,
                    "line_number": fail.line_number,
                    "error_type": fail.error_type,
                    "error_message": fail.error_message,
                    "suspected_source_file": fail.suspected_source_file,
                    "suspected_source_line": fail.suspected_source_line,
                    "suspected_source_symbol": fail.suspected_source_symbol,
                    "stack_trace_snippet": fail.stack_trace[:500],
                }
                for fail in summary.failures
            ],
        }

    def _tool_propose_patch(self, args: Dict[str, Any]) -> Dict[str, Any]:
        file_path = args.get("file_path", "")
        modified_content = args.get("modified_content", "")
        title = args.get("title", "Proposed Patch")
        explanation = args.get("explanation", "")

        if not file_path or not modified_content:
            return {"error": "file_path and modified_content are required"}

        proposal = self.patch_manager.propose_patch(
            file_path=file_path,
            modified_content=modified_content,
            title=title,
            explanation=explanation,
        )
        return proposal.to_dict()

    def _tool_run_isolated_tests(self, args: Dict[str, Any]) -> Dict[str, Any]:
        patch_id = args.get("patch_id")
        test_path = args.get("test_path")

        if patch_id:
            return self.patch_manager.verify_patch_in_isolation(
                patch_id=patch_id,
                test_path=test_path,
            )
        # Otherwise run base tests
        summary = self.test_runner.run_tests(test_path=test_path)
        return {
            "executed": summary.executed,
            "total_tests": summary.total_tests,
            "passed_tests": summary.passed_tests,
            "failed_tests": summary.failed_tests,
            "errors": summary.error_tests,
            "status": "passed" if summary.failed_tests == 0 and summary.executed else "failed",
            "failures": [f.model_dump() for f in summary.failures],
        }

    def _register_default_tools(self) -> None:
        """Register the 9 standard repository intelligence and repair tools."""
        self.register(
            ToolDefinition(
                name="search_codebase",
                description="Search the repository for functions, symbols, or topics using hybrid RAG (BM25 + Dense).",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query or question"},
                        "top_k": {"type": "integer", "description": "Number of results to retrieve (default: 5)"},
                    },
                    "required": ["query"],
                },
                handler=self._tool_search_codebase,
            )
        )

        self.register(
            ToolDefinition(
                name="read_file",
                description="Read lines from a file in the repository with optional 1-indexed start and end line bounds.",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Repository-relative path of file to read"},
                        "start_line": {"type": "integer", "description": "Starting line number (1-based)"},
                        "end_line": {"type": "integer", "description": "Ending line number (1-based)"},
                    },
                    "required": ["file_path"],
                },
                handler=self._tool_read_file,
            )
        )

        self.register(
            ToolDefinition(
                name="find_symbols",
                description="Find Python functions, classes, and methods in the codebase using AST parser.",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "name_query": {"type": "string", "description": "Symbol name or substring to search for"},
                        "file_path": {"type": "string", "description": "Optional file path to limit symbol search"},
                    },
                },
                handler=self._tool_find_symbols,
            )
        )

        self.register(
            ToolDefinition(
                name="find_callers",
                description="Statically search for all caller sites and references in the repository that invoke a target function.",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "target_symbol": {"type": "string", "description": "Function or method name to locate callers for"},
                        "target_file": {"type": "string", "description": "Optional file where symbol is defined"},
                    },
                    "required": ["target_symbol"],
                },
                handler=self._tool_find_callers,
            )
        )

        self.register(
            ToolDefinition(
                name="inspect_dependencies",
                description="Inspect static dependency relationships and callees invoked inside a target function.",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "function_name": {"type": "string", "description": "Name of function to inspect"},
                        "file_path": {"type": "string", "description": "File path containing the function"},
                    },
                    "required": ["function_name", "file_path"],
                },
                handler=self._tool_inspect_dependencies,
            )
        )

        self.register(
            ToolDefinition(
                name="run_static_analysis",
                description="Run static diagnostics (Ruff linting, AST syntax and zero-division checks, Mypy) on the codebase.",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "target_path": {"type": "string", "description": "Optional file or directory path to analyze"},
                    },
                },
                handler=self._tool_run_static_analysis,
            )
        )

        self.register(
            ToolDefinition(
                name="run_tests",
                description="Run the repository test suite in an isolated environment and capture failure tracebacks.",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "test_path": {"type": "string", "description": "Optional test file or directory path to execute"},
                    },
                },
                handler=self._tool_run_tests,
            )
        )

        self.register(
            ToolDefinition(
                name="propose_patch",
                description="Propose a minimal code patch with unified diff without modifying the actual disk repository.",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Target file path to patch"},
                        "modified_content": {"type": "string", "description": "Full new file content including the fix"},
                        "title": {"type": "string", "description": "Short title describing the change"},
                        "explanation": {"type": "string", "description": "Explanation of why this fix is needed"},
                    },
                    "required": ["file_path", "modified_content"],
                },
                handler=self._tool_propose_patch,
            )
        )

        self.register(
            ToolDefinition(
                name="run_isolated_tests",
                description="Run approved tests in an isolated sandbox with the proposed patch applied, verifying if bugs are fixed.",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "patch_id": {"type": "string", "description": "ID of proposed patch to test in isolation"},
                        "test_path": {"type": "string", "description": "Optional specific test path to run"},
                    },
                },
                handler=self._tool_run_isolated_tests,
            )
        )
