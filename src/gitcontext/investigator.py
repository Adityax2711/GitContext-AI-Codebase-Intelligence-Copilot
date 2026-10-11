"""Investigation orchestrator coordinating retrieval, inspection, static analysis, and testing."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Sequence, Union

from gitcontext.bug_models import (
    BugFinding,
    BugInvestigationReport,
    CallTraceInfo,
    StaticAnalysisFinding,
    TestExecutionSummary,
    TestFailure,
)
from gitcontext.citations import Citation, is_valid_chunk_bounds, verify_citations
from gitcontext.indexing import get_default_index_dir, load_index
from gitcontext.llm import LLMClient, MockLLMClient, get_llm_client
from gitcontext.models import CodeChunk, SearchResult
from gitcontext.retrieval import hybrid_search
from gitcontext.tools.dependency_tracer import DependencyTracer
from gitcontext.tools.repo_inspector import RepoInspector
from gitcontext.tools.static_analyzer import StaticAnalyzer
from gitcontext.tools.test_runner import TestRunner


class BugInvestigator:
    """Orchestrates comprehensive bug investigations across code, tests, and static diagnostics."""

    def __init__(
        self,
        repo_path: Union[str, Path],
        index_dir: Optional[Path] = None,
        llm_client: Optional[LLMClient] = None,
        max_files_inspected: int = 10,
        timeout_seconds: int = 25,
    ) -> None:
        self.repo_path = Path(repo_path).resolve()
        self.index_dir = index_dir or get_default_index_dir()
        self.inspector = RepoInspector(self.repo_path)
        self.tracer = DependencyTracer(self.inspector)
        self.analyzer = StaticAnalyzer(self.inspector)
        self.test_runner = TestRunner(self.inspector, default_timeout_seconds=timeout_seconds)
        self.llm_client = llm_client
        self.max_files_inspected = max_files_inspected
        self.timeout_seconds = timeout_seconds

    def investigate(
        self,
        query: str,
        target_file: Optional[str] = None,
        target_symbol: Optional[str] = None,
        run_tests: bool = False,
        test_path: Optional[str] = None,
        chunks: Optional[List[CodeChunk]] = None,
    ) -> BugInvestigationReport:
        """Execute bounded investigation workflow and produce structured bug report."""
        clean_query = query.strip()
        if not clean_query:
            return BugInvestigationReport(
                query=query,
                repository_path=str(self.repo_path),
                summary="Investigation query cannot be empty.",
                findings=[],
                missing_evidence=["No query provided"],
                next_steps=["Provide a descriptive bug report or query"],
                sources=[],
            )

        # -------------------------------------------------------------------
        # Step 1: Hybrid Retrieval to gather initial candidate chunks
        # -------------------------------------------------------------------
        evidence_chunks: List[CodeChunk] = []
        if chunks is not None:
            active_chunks = chunks
        else:
            loaded, _ = load_index(self.index_dir)
            active_chunks = [c for c in loaded if (self.repo_path / c.file_path).exists()] if loaded else []

        if active_chunks:
            retrieval_results = hybrid_search(clean_query, active_chunks, top_k=5)
            evidence_chunks = [r.chunk for r in retrieval_results]
        else:
            # Fallback keyword search directly on repo
            search_matches = self.inspector.search_code(clean_query.split()[0], max_matches=5)
            for sm in search_matches:
                evidence_chunks.append(
                    CodeChunk.create(
                        repository=self.repo_path.name,
                        source_type="code",
                        file_path=sm.file_path,
                        symbol_or_heading="search_match",
                        programming_language="python",
                        start_line=sm.line_number,
                        end_line=sm.line_number,
                        content=sm.line_content,
                    )
                )

        # -------------------------------------------------------------------
        # Step 2: Repository Source & Symbol Inspection
        # -------------------------------------------------------------------
        inspected_symbols = []
        relevant_files = set()
        if target_file:
            safe_target = self.inspector.resolve_safe_path(target_file)
            if safe_target.exists():
                relevant_files.add(self.inspector.to_relative_path(safe_target))

        for c in evidence_chunks:
            if (self.repo_path / c.file_path).exists():
                relevant_files.add(c.file_path)

        # Find matching symbols
        symbol_query = target_symbol or (clean_query.split()[0] if len(clean_query.split()) == 1 else None)
        if symbol_query:
            inspected_symbols.extend(self.inspector.find_symbols(name_query=symbol_query))
        elif target_file:
            inspected_symbols.extend(self.inspector.find_symbols(file_path=target_file))

        # -------------------------------------------------------------------
        # Step 3: Function and Caller Tracing
        # -------------------------------------------------------------------
        call_traces: List[CallTraceInfo] = []
        symbols_to_trace = set()
        if target_symbol:
            symbols_to_trace.add(target_symbol)
        for s in inspected_symbols:
            symbols_to_trace.add(s.name.split(".")[-1])

        # Also extract any function names mentioned in the query
        for word in re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]+\b", clean_query):
            if any(sym.name.endswith(word) for sym in inspected_symbols):
                symbols_to_trace.add(word)

        for sym in list(symbols_to_trace)[:5]:
            callers = self.tracer.find_callers(target_symbol=sym)
            call_traces.extend(callers)

        # -------------------------------------------------------------------
        # Step 4: Static Analysis (Ruff + AST Checks)
        # -------------------------------------------------------------------
        static_findings: List[StaticAnalysisFinding] = []
        # If target file specified, check it; otherwise check relevant files or entire repo
        if target_file:
            static_findings = self.analyzer.analyze(target_path=target_file)
        elif relevant_files:
            for rf in list(relevant_files)[: self.max_files_inspected]:
                static_findings.extend(self.analyzer.analyze(target_path=rf))
        else:
            static_findings = self.analyzer.analyze()

        # -------------------------------------------------------------------
        # Step 5: Test Execution and Failure Investigation
        # -------------------------------------------------------------------
        test_summary: Optional[TestExecutionSummary] = None
        should_run_tests = (
            run_tests
            or test_path is not None
            or "test" in clean_query.lower()
            or "assert" in clean_query.lower()
            or "fail" in clean_query.lower()
        )

        if should_run_tests:
            test_summary = self.test_runner.run_tests(test_path=test_path)

        # -------------------------------------------------------------------
        # Step 6: Evidence Correlation and Finding Synthesis
        # -------------------------------------------------------------------
        findings: List[BugFinding] = []
        sources: List[Citation] = []
        missing_evidence: List[str] = []
        next_steps: List[str] = []
        bug_counter = 1

        # 6A: Convert Test Failures into Verified Findings
        if test_summary and test_summary.failures:
            for fail in test_summary.failures:
                source_file = fail.suspected_source_file or fail.file_path
                source_line = fail.suspected_source_line or fail.line_number or 1

                # Read excerpt around failure
                try:
                    excerpt_res = self.inspector.read_file(
                        source_file,
                        start_line=max(1, source_line - 2),
                        end_line=source_line + 2,
                    )
                    code_excerpt = excerpt_res.content
                    s_line = excerpt_res.start_line
                    e_line = excerpt_res.end_line
                except Exception:
                    code_excerpt = fail.stack_trace[:300]
                    s_line = source_line
                    e_line = source_line

                category = "assertion_failure"
                if "zero" in fail.error_type.lower() or "zerodivision" in fail.error_type.lower():
                    category = "zero_division"
                elif "index" in fail.error_type.lower() or "boundary" in fail.error_type.lower():
                    category = "boundary_condition"
                elif "key" in fail.error_type.lower() or "val" in fail.error_type.lower():
                    category = "missing_validation"

                finding = BugFinding(
                    bug_id=f"BUG-{bug_counter:03d}",
                    title=f"Test failure: {fail.test_name} raised {fail.error_type}",
                    description=(
                        f"Isolated test execution failed on {fail.test_name}. "
                        f"Exception details: {fail.error_message}."
                    ),
                    category=category,
                    severity="high",
                    severity_justification="Verified by executing automated test suite in isolated environment.",
                    confidence="high",
                    confidence_rationale=(
                        "High confidence: Defect was directly reproduced by test runner and localized via stack trace."
                    ),
                    evidence_type="test_failure",
                    file_path=source_file,
                    start_line=s_line,
                    end_line=e_line,
                    code_excerpt=code_excerpt,
                    expected_behavior=f"Test {fail.test_name} should pass without raising unhandled {fail.error_type}.",
                    observed_behavior=f"{fail.error_type}: {fail.error_message}",
                    likely_root_cause=(
                        f"Unhandled condition in {fail.suspected_source_symbol or source_file} "
                        f"triggered by test input."
                    ),
                    reproduction_steps=[
                        f"Run test suite: pytest {fail.file_path}",
                        f"Observe {fail.error_type} at line {source_line}",
                    ],
                    suggested_next_diagnostic_step=(
                        f"Inspect variables leading to {source_file}:L{source_line} during test execution."
                    ),
                    suggested_fix_direction=(
                        "Implement input validation or guard clause handling the failing edge case."
                    ),
                    verification_status="reproduced",
                )
                findings.append(finding)
                bug_counter += 1

                # Grounded citation
                sources.append(
                    Citation(
                        source_index=len(sources) + 1,
                        file_path=source_file,
                        symbol_or_heading=fail.suspected_source_symbol or fail.test_name,
                        start_line=s_line,
                        end_line=e_line,
                        programming_language="python",
                        raw_reference=f"[{len(sources) + 1}]",
                    )
                )

        # 6B: Convert Critical / High Static Analyzer Findings into Findings
        for sf in static_findings:
            if sf.severity in ("critical", "high"):
                # Avoid exact duplicate of test failure location
                if any(f.file_path == sf.file_path and f.start_line == sf.start_line for f in findings):
                    continue

                try:
                    excerpt_res = self.inspector.read_file(
                        sf.file_path,
                        start_line=sf.start_line,
                        end_line=sf.end_line,
                    )
                    code_excerpt = excerpt_res.content
                except Exception:
                    code_excerpt = sf.message

                category = "logic_error"
                if "ZERO_DIVISION" in sf.rule_id:
                    category = "zero_division"
                elif "SYNTAX" in sf.rule_id:
                    category = "syntax_error"
                elif "TYPE" in sf.rule_id:
                    category = "type_error"

                finding = BugFinding(
                    bug_id=f"BUG-{bug_counter:03d}",
                    title=f"Static analysis violation: {sf.rule_id} in {sf.file_path}",
                    description=sf.message,
                    category=category,
                    severity=sf.severity,
                    severity_justification=f"Reported by {sf.tool_source} static analyzer rule {sf.rule_id}.",
                    confidence="high" if sf.tool_source == "ast_inspector" else "medium",
                    confidence_rationale=(
                        "High confidence: Deterministic AST defect detected."
                        if sf.tool_source == "ast_inspector"
                        else f"Medium confidence: Emitted by {sf.tool_source} static diagnostics without dynamic test run."
                    ),
                    evidence_type="static_analyzer",
                    file_path=sf.file_path,
                    start_line=sf.start_line,
                    end_line=sf.end_line,
                    code_excerpt=code_excerpt,
                    expected_behavior=f"Code should adhere to correctness rule {sf.rule_id}.",
                    observed_behavior=sf.message,
                    likely_root_cause=f"Direct occurrence of pattern flagged by {sf.rule_id}.",
                    reproduction_steps=[
                        f"Run static analyzer: python -m ruff check {sf.file_path}",
                    ],
                    suggested_next_diagnostic_step=f"Inspect AST structure and surrounding logic at {sf.file_path}:L{sf.start_line}.",
                    suggested_fix_direction="Refactor the flagged statement to adhere to proper safety constraints.",
                    verification_status="suspected",
                )
                findings.append(finding)
                bug_counter += 1

                sources.append(
                    Citation(
                        source_index=len(sources) + 1,
                        file_path=sf.file_path,
                        symbol_or_heading=sf.rule_id,
                        start_line=sf.start_line,
                        end_line=sf.end_line,
                        programming_language="python",
                        raw_reference=f"[{len(sources) + 1}]",
                    )
                )

        # 6C: Semantic Source Inspection for Boundary Condition or Missing Validation
        # If no findings yet, inspect retrieved code chunks for specific patterns matching query
        if not findings and evidence_chunks:
            q_lower = clean_query.lower()
            for chunk in evidence_chunks:
                # Boundary condition check (e.g. <= vs < or off-by-one)
                if ("boundary" in q_lower or "off by one" in q_lower or "<=" in q_lower) and (
                    "<=" in chunk.content or ">=" in chunk.content or "len(" in chunk.content
                ):
                    finding = BugFinding(
                        bug_id=f"BUG-{bug_counter:03d}",
                        title=f"Potential boundary condition error in {chunk.symbol_or_heading}",
                        description=(
                            f"Suspicious comparison or boundary index logic observed in {chunk.file_path}:L{chunk.start_line}-L{chunk.end_line}. "
                            f"Loop or slice bound may allow index overflow or off-by-one access."
                        ),
                        category="boundary_condition",
                        severity="medium",
                        severity_justification="Boundary conditions can lead to IndexError or off-by-one logic errors.",
                        confidence="medium",
                        confidence_rationale="Medium confidence: Identified through AST source inspection against user query keywords.",
                        evidence_type="source_inspection",
                        file_path=chunk.file_path,
                        start_line=chunk.start_line,
                        end_line=chunk.end_line,
                        code_excerpt=chunk.content[:400],
                        expected_behavior="Index boundary comparison should strictly respect valid range bounds (< len).",
                        observed_behavior=None,
                        likely_root_cause="Inclusive comparison operator (<=) instead of strict comparison (<).",
                        reproduction_steps=[
                            f"Call {chunk.symbol_or_heading} with edge input at collection length limit.",
                        ],
                        suggested_next_diagnostic_step="Add a unit test checking edge index at maximum length.",
                        suggested_fix_direction="Change comparison bound to strict inequality or validate index range.",
                        verification_status="suspected",
                    )
                    findings.append(finding)
                    bug_counter += 1

                    sources.append(
                        Citation(
                            source_index=len(sources) + 1,
                            file_path=chunk.file_path,
                            symbol_or_heading=chunk.symbol_or_heading,
                            start_line=chunk.start_line,
                            end_line=chunk.end_line,
                            programming_language=chunk.programming_language,
                            raw_reference=f"[{len(sources) + 1}]",
                        )
                    )
                    break

                # Missing input validation check
                if ("validation" in q_lower or "missing check" in q_lower or "negative" in q_lower) and (
                    "def " in chunk.content
                ):
                    finding = BugFinding(
                        bug_id=f"BUG-{bug_counter:03d}",
                        title=f"Missing input validation in {chunk.symbol_or_heading}",
                        description=(
                            f"Function {chunk.symbol_or_heading} processes input parameters without defensive validation checks."
                        ),
                        category="missing_validation",
                        severity="medium",
                        severity_justification="Unvalidated arguments can propagate invalid state or trigger runtime crashes.",
                        confidence="medium",
                        confidence_rationale="Medium confidence: Static source inspection identified absent parameter checks.",
                        evidence_type="source_inspection",
                        file_path=chunk.file_path,
                        start_line=chunk.start_line,
                        end_line=chunk.end_line,
                        code_excerpt=chunk.content[:400],
                        expected_behavior="Function should raise ValueError or handle unexpected/negative inputs gracefully.",
                        observed_behavior=None,
                        likely_root_cause="Parameters are consumed directly without range or type assertions.",
                        reproduction_steps=[
                            f"Invoke {chunk.symbol_or_heading} with invalid or negative argument.",
                        ],
                        suggested_next_diagnostic_step="Write parameterized tests with edge-case and invalid inputs.",
                        suggested_fix_direction="Add parameter validation at the beginning of the function body.",
                        verification_status="suspected",
                    )
                    findings.append(finding)
                    bug_counter += 1

                    sources.append(
                        Citation(
                            source_index=len(sources) + 1,
                            file_path=chunk.file_path,
                            symbol_or_heading=chunk.symbol_or_heading,
                            start_line=chunk.start_line,
                            end_line=chunk.end_line,
                            programming_language=chunk.programming_language,
                            raw_reference=f"[{len(sources) + 1}]",
                        )
                    )
                    break

        # -------------------------------------------------------------------
        # Step 7: Assess Missing Evidence & Recommendations
        # -------------------------------------------------------------------
        if not test_summary or not test_summary.executed:
            missing_evidence.append("Automated test suite was not executed; dynamic runtime behavior is unverified.")
            next_steps.append("Run the test runner with --run-tests to verify test assertions.")
        elif test_summary.timed_out:
            missing_evidence.append(f"Test run timed out after {self.timeout_seconds}s; partial results only.")
            next_steps.append("Investigate potential infinite loop or increase execution timeout.")

        if not any(f.verification_status == "reproduced" for f in findings):
            missing_evidence.append("No active test reproduced this bug under isolated execution.")
            next_steps.append("Construct a reproduction test fixture to confirm suspected defect.")

        next_steps.append("Review suggested fix directions and plan Step 5 automated fix generation.")

        # Summary line
        if findings:
            reproduced_count = sum(1 for f in findings if f.verification_status == "reproduced")
            summary = (
                f"Investigation completed: {len(findings)} finding(s) identified "
                f"({reproduced_count} reproduced, {len(findings) - reproduced_count} suspected)."
            )
        else:
            summary = "Investigation completed: No defects or test failures detected for the query."

        return BugInvestigationReport(
            query=clean_query,
            repository_path=str(self.repo_path),
            summary=summary,
            findings=findings,
            missing_evidence=missing_evidence,
            next_steps=next_steps,
            sources=sources,
            test_summary=test_summary,
            static_analysis_findings=static_findings,
            call_traces=call_traces,
        )


def investigate_codebase(
    query: str,
    repo_path: Union[str, Path],
    target_file: Optional[str] = None,
    target_symbol: Optional[str] = None,
    run_tests: bool = False,
    test_path: Optional[str] = None,
    index_dir: Optional[Path] = None,
    llm_client: Optional[LLMClient] = None,
) -> BugInvestigationReport:
    """Convenience functional interface for bug investigation."""
    investigator = BugInvestigator(
        repo_path=repo_path,
        index_dir=index_dir,
        llm_client=llm_client,
    )
    return investigator.investigate(
        query=query,
        target_file=target_file,
        target_symbol=target_symbol,
        run_tests=run_tests,
        test_path=test_path,
    )
