"""Pydantic data models for Step 4 Bug Investigation Agent."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

from gitcontext.citations import Citation


class StaticAnalysisFinding(BaseModel):
    """Normalized finding from a static analysis tool (Ruff, Mypy, or AST checker)."""

    rule_id: str = Field(..., description="Unique rule identifier (e.g. 'RUFF:E711', 'AST:ZERO_DIVISION')")
    message: str = Field(..., description="Diagnostic error or warning message")
    file_path: str = Field(..., description="Repository-relative file path")
    start_line: int = Field(..., ge=1, description="1-indexed starting line number")
    end_line: int = Field(..., ge=1, description="1-indexed ending line number")
    tool_source: Literal["ruff", "mypy", "ast_inspector"] = Field(
        ..., description="Tool that emitted the diagnostic"
    )
    severity: Literal["critical", "high", "medium", "low"] = Field(
        default="medium", description="Severity classification of the rule"
    )

    model_config = ConfigDict(frozen=True)


class TestFailure(BaseModel):
    """Observed failure or error from running a test suite."""

    __test__ = False

    test_name: str = Field(..., description="Fully qualified test name or node ID")
    file_path: str = Field(..., description="Test file path")
    line_number: Optional[int] = Field(default=None, description="Line number of failure in test file")
    error_type: str = Field(..., description="Type of exception/assertion raised")
    error_message: str = Field(..., description="Assertion or exception message")
    stack_trace: str = Field(..., description="Captured traceback text")
    suspected_source_file: Optional[str] = Field(
        default=None, description="Repository-relative source file identified in stack trace"
    )
    suspected_source_line: Optional[int] = Field(
        default=None, description="Line number in suspected source file"
    )
    suspected_source_symbol: Optional[str] = Field(
        default=None, description="Function or method name executing at failure point"
    )


class TestExecutionSummary(BaseModel):
    """Summary of a test run executed in an isolated environment."""

    __test__ = False

    framework: str = Field(default="pytest", description="Test framework detected and executed")
    executed: bool = Field(default=False, description="Whether tests were actually executed")
    total_tests: int = Field(default=0, ge=0)
    passed_tests: int = Field(default=0, ge=0)
    failed_tests: int = Field(default=0, ge=0)
    error_tests: int = Field(default=0, ge=0)
    timed_out: bool = Field(default=False, description="Whether execution hit timeout limit")
    failures: List[TestFailure] = Field(default_factory=list)
    raw_output: str = Field(default="", description="Sanitized stdout/stderr summary")


class CallTraceInfo(BaseModel):
    """Statically traced caller or callee relationship across code symbols."""

    caller_file: str = Field(..., description="File containing caller")
    caller_symbol: str = Field(..., description="Function or class name of caller")
    caller_line: int = Field(..., description="Line number of the call")
    target_symbol: str = Field(..., description="Target function or method invoked")
    target_file: Optional[str] = Field(default=None, description="File defining target symbol if resolved")
    call_snippet: str = Field(default="", description="Code snippet showing invocation")
    is_ambiguous: bool = Field(
        default=False,
        description="Whether static resolution could not definitively verify dynamic binding",
    )
    ambiguity_reason: Optional[str] = Field(
        default=None, description="Explanation why resolution is incomplete or ambiguous"
    )


class BugFinding(BaseModel):
    """Detailed evidence-backed finding for an investigated bug."""

    bug_id: str = Field(..., description="Unique bug identifier (e.g. 'BUG-001')")
    title: str = Field(..., max_length=150, description="Short descriptive title of the bug")
    description: str = Field(..., description="In-depth explanation of the issue")
    category: str = Field(
        ...,
        description="Bug category (e.g. zero_division, boundary_condition, missing_validation, logic_error)",
    )
    severity: Literal["critical", "high", "medium", "low"] = Field(
        ..., description="Severity level of the defect"
    )
    severity_justification: str = Field(
        ..., description="Concrete justification explaining why this severity was assigned"
    )
    confidence: Literal["high", "medium", "low"] = Field(
        ..., description="Confidence level of the finding"
    )
    confidence_rationale: str = Field(
        ...,
        description="Explicit reasoning for confidence level (e.g. verified test failure vs static lint vs heuristic)",
    )
    evidence_type: Literal["static_analyzer", "test_failure", "source_inspection", "ai_hypothesis"] = Field(
        ..., description="Primary evidence category backing this finding"
    )
    file_path: str = Field(..., description="Repository-relative file path containing the bug")
    start_line: int = Field(..., ge=1, description="1-indexed starting line number")
    end_line: int = Field(..., ge=1, description="1-indexed ending line number")
    code_excerpt: str = Field(..., description="Relevant code excerpt or evidence reference")
    expected_behavior: str = Field(..., description="What the code was supposed to do")
    observed_behavior: Optional[str] = Field(
        default=None, description="Observed error message or failing behavior if verified"
    )
    likely_root_cause: str = Field(..., description="Identified root cause of the bug")
    reproduction_steps: Optional[List[str]] = Field(
        default=None, description="Ordered steps or test command to reproduce"
    )
    suggested_next_diagnostic_step: str = Field(
        ..., description="Recommended diagnostic check or instrumentation step"
    )
    suggested_fix_direction: str = Field(
        ..., description="Guidance for repairing the defect without modifying files automatically"
    )
    verification_status: Literal["suspected", "reproduced", "not_reproduced"] = Field(
        ..., description="Verification status of the bug"
    )


class BugInvestigationReport(BaseModel):
    """Structured report produced by the Bug Investigation Agent."""

    query: str = Field(..., description="Original investigation query, symptom, or error report")
    repository_path: str = Field(..., description="Path to the investigated repository")
    summary: str = Field(..., description="Executive summary of investigation findings")
    findings: List[BugFinding] = Field(
        default_factory=list, description="List of identified bugs backed by evidence"
    )
    missing_evidence: List[str] = Field(
        default_factory=list, description="List of missing evidence, unverified assumptions, or gaps"
    )
    next_steps: List[str] = Field(
        default_factory=list, description="Recommended next diagnostic or testing steps"
    )
    sources: List[Citation] = Field(
        default_factory=list, description="Verified source citations grounded in repository files"
    )
    test_summary: Optional[TestExecutionSummary] = Field(
        default=None, description="Outcome of isolated test run if executed"
    )
    static_analysis_findings: List[StaticAnalysisFinding] = Field(
        default_factory=list, description="Diagnostics collected from static analyzers"
    )
    call_traces: List[CallTraceInfo] = Field(
        default_factory=list, description="Statically traced call relationships"
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert report to standard serializable dictionary."""
        return self.model_dump()

    def format_cli_output(self) -> str:
        """Format a comprehensive, human-readable terminal report."""
        lines = [
            "=" * 78,
            "GITCONTEXT BUG INVESTIGATION REPORT",
            "=" * 78,
            f"Query      : {self.query}",
            f"Repository : {self.repository_path}",
            f"Summary    : {self.summary}",
            "-" * 78,
        ]

        # Test results section
        if self.test_summary and self.test_summary.executed:
            lines.append("[TEST EXECUTION - ISOLATED RUN]:")
            lines.append(
                f"  Total: {self.test_summary.total_tests} | "
                f"Passed: {self.test_summary.passed_tests} | "
                f"Failed: {self.test_summary.failed_tests} | "
                f"Errors: {self.test_summary.error_tests}"
            )
            if self.test_summary.timed_out:
                lines.append("  [WARNING] Execution hit timeout limit!")
            for idx, fail in enumerate(self.test_summary.failures, 1):
                lines.append(f"  [{idx}] {fail.test_name} ({fail.error_type}): {fail.error_message}")
                if fail.suspected_source_file:
                    lines.append(
                        f"      Traceback points to: {fail.suspected_source_file}:L{fail.suspected_source_line} ({fail.suspected_source_symbol})"
                    )
            lines.append("-" * 78)

        # Static Analysis section
        if self.static_analysis_findings:
            lines.append(f"[STATIC ANALYSIS FINDINGS] ({len(self.static_analysis_findings)} detected):")
            for sf in self.static_analysis_findings[:10]:
                lines.append(
                    f"  [{sf.tool_source.upper()}:{sf.rule_id}] {sf.file_path}:L{sf.start_line}-L{sf.end_line} - {sf.message}"
                )
            if len(self.static_analysis_findings) > 10:
                lines.append(f"  ... and {len(self.static_analysis_findings) - 10} more findings")
            lines.append("-" * 78)

        # Findings section
        lines.append(f"[IDENTIFIED BUG FINDINGS] ({len(self.findings)}):")
        if not self.findings:
            lines.append("  No confirmed bugs identified from available evidence.")
        else:
            for idx, f in enumerate(self.findings, 1):
                lines.extend([
                    f"\n[{idx}] {f.bug_id}: {f.title}",
                    f"    Category      : {f.category}",
                    f"    Severity      : {f.severity.upper()} ({f.severity_justification})",
                    f"    Confidence    : {f.confidence.upper()} ({f.confidence_rationale})",
                    f"    Evidence Type : {f.evidence_type}",
                    f"    Location      : {f.file_path}:L{f.start_line}-L{f.end_line}",
                    f"    Status        : {f.verification_status.upper()}",
                    f"    Root Cause    : {f.likely_root_cause}",
                    f"    Expected      : {f.expected_behavior}",
                ])
                if f.observed_behavior:
                    lines.append(f"    Observed      : {f.observed_behavior}")
                lines.extend([
                    f"    Fix Direction : {f.suggested_fix_direction}",
                    f"    Next Step     : {f.suggested_next_diagnostic_step}",
                ])
                if f.reproduction_steps:
                    lines.append("    Reproduction  :")
                    for step in f.reproduction_steps:
                        lines.append(f"      - {step}")
                if f.code_excerpt:
                    lines.append("    Code Excerpt  :")
                    for eline in f.code_excerpt.strip().splitlines()[:6]:
                        lines.append(f"      {eline}")

        lines.append("-" * 78)

        # Traces
        if self.call_traces:
            lines.append(f"[STATIC CALL RELATIONSHIPS] ({len(self.call_traces)}):")
            for t in self.call_traces[:5]:
                ambig = f" [AMBIGUOUS: {t.ambiguity_reason}]" if t.is_ambiguous else ""
                lines.append(
                    f"  {t.caller_file}:L{t.caller_line} ({t.caller_symbol}) -> calls '{t.target_symbol}'{ambig}"
                )
            lines.append("-" * 78)

        # Missing Evidence
        if self.missing_evidence:
            lines.append("[MISSING EVIDENCE & UNVERIFIED GAPS]:")
            for m in self.missing_evidence:
                lines.append(f"  * {m}")
            lines.append("-" * 78)

        # Next Steps
        if self.next_steps:
            lines.append("[RECOMMENDED NEXT STEPS]:")
            for s in self.next_steps:
                lines.append(f"  * {s}")
            lines.append("-" * 78)

        # Sources
        if self.sources:
            lines.append("[GROUNDED SOURCE CITATIONS]:")
            for s in self.sources:
                sym = f" ({s.symbol_or_heading})" if s.symbol_or_heading else ""
                lines.append(f"  [{s.source_index}] {s.file_path}:L{s.start_line}-L{s.end_line}{sym}")
            lines.append("-" * 78)

        lines.append("=" * 78)
        return "\n".join(lines)
