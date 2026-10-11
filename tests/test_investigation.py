"""Unit and integration tests for Step 4 Bug Investigation Agent."""

import json
from pathlib import Path
import pytest

from gitcontext.bug_models import (
    BugFinding,
    BugInvestigationReport,
    CallTraceInfo,
    StaticAnalysisFinding,
    TestExecutionSummary,
    TestFailure,
)
from gitcontext.citations import Citation
from gitcontext.cli import main
from gitcontext.investigator import BugInvestigator, investigate_codebase
from gitcontext.tools.dependency_tracer import DependencyTracer
from gitcontext.tools.repo_inspector import PathTraversalError, RepoInspector
from gitcontext.tools.static_analyzer import StaticAnalyzer
from gitcontext.tools.test_runner import TestRunner


@pytest.fixture
def synthetic_bug_repo_path() -> Path:
    """Path to the synthetic bug repository fixture."""
    path = Path(__file__).parent.parent / "fixtures" / "synthetic_bug_repo"
    assert path.is_dir()
    return path


# ---------------------------------------------------------------------------
# Test 1: File Inspection, Line-Number Accuracy, & Path Traversal Prevention
# ---------------------------------------------------------------------------
def test_repo_inspector_file_reading_and_line_accuracy(synthetic_bug_repo_path: Path):
    inspector = RepoInspector(synthetic_bug_repo_path)

    # 1. Read specific slice of math_ops.py
    res = inspector.read_file("math_ops.py", start_line=6, end_line=12)
    assert res.file_path == "math_ops.py"
    assert res.start_line == 6
    assert res.end_line == 12
    assert "def divide_numbers" in res.content
    assert len(res.lines_with_numbers) == 7
    assert res.lines_with_numbers[0][0] == 6

    # 2. Path traversal defense
    with pytest.raises((PathTraversalError, PermissionError, ValueError)):
        inspector.read_file("../../../pyproject.toml")

    with pytest.raises((PathTraversalError, PermissionError, ValueError)):
        inspector.resolve_safe_path("C:/Windows/System32/drivers/etc/hosts")

    # 3. Nonexistent file error
    with pytest.raises(FileNotFoundError):
        inspector.read_file("does_not_exist.py")


# ---------------------------------------------------------------------------
# Test 2: Symbol Discovery and Caller Tracing
# ---------------------------------------------------------------------------
def test_symbol_discovery_and_caller_tracing(synthetic_bug_repo_path: Path):
    inspector = RepoInspector(synthetic_bug_repo_path)
    tracer = DependencyTracer(inspector)

    # 1. Discover symbols in math_ops.py
    symbols = inspector.find_symbols(file_path="math_ops.py")
    sym_names = [s.name for s in symbols]
    assert "divide_numbers" in sym_names
    assert "compute_inverse_weight" in sym_names

    # 2. Find callers of divide_numbers across modules
    # consumer.py calls divide_numbers
    callers = tracer.find_callers("divide_numbers")
    assert len(callers) >= 1
    c = callers[0]
    assert c.caller_file == "consumer.py"
    assert "compute_ratio" in c.caller_symbol
    assert "divide_numbers" in c.call_snippet

    # 3. Trace function callees
    callees_info = tracer.trace_function_callees("compute_ratio", "consumer.py")
    callee_targets = [item["target_symbol"] for item in callees_info["callees"]]
    assert any("divide_numbers" in t for t in callee_targets)
    assert "Static AST inspection only" in callees_info["disclaimer"]


# ---------------------------------------------------------------------------
# Test 3: Static Analyzer Output Parsing (Ruff + AST Diagnostics)
# ---------------------------------------------------------------------------
def test_static_analyzer_diagnostics(synthetic_bug_repo_path: Path):
    inspector = RepoInspector(synthetic_bug_repo_path)
    analyzer = StaticAnalyzer(inspector)

    # 1. AST Diagnostics should catch division by literal zero in compute_inverse_weight
    ast_findings = analyzer.run_ast_diagnostics("math_ops.py")
    zero_div = [f for f in ast_findings if f.rule_id == "AST:ZERO_DIVISION"]
    assert len(zero_div) >= 1
    assert zero_div[0].file_path == "math_ops.py"
    assert zero_div[0].severity == "critical"
    assert zero_div[0].tool_source == "ast_inspector"

    # 2. Aggregated analysis
    all_findings = analyzer.analyze()
    assert any(f.rule_id == "AST:ZERO_DIVISION" for f in all_findings)


# ---------------------------------------------------------------------------
# Test 4: Test Failure Collection and Traceback Correlation
# ---------------------------------------------------------------------------
def test_test_runner_isolated_execution(synthetic_bug_repo_path: Path):
    inspector = RepoInspector(synthetic_bug_repo_path)
    runner = TestRunner(inspector, default_timeout_seconds=20)

    # Detect framework
    assert runner.detect_framework() == "pytest"

    # Run tests on synthetic repo tests
    summary = runner.run_tests(test_path="tests/test_math.py")
    assert summary.executed is True
    assert summary.total_tests == 2
    assert summary.passed_tests == 1
    assert summary.failed_tests == 1

    # Check failure details
    assert len(summary.failures) == 1
    fail = summary.failures[0]
    assert "test_divide_zero_division_failing" in fail.test_name
    assert "ZeroDivisionError" in fail.error_type
    # Must correctly map back to math_ops.py source!
    assert fail.suspected_source_file == "math_ops.py"
    assert fail.suspected_source_symbol == "divide_numbers"


# ---------------------------------------------------------------------------
# Test 5: Bug Report Schema Validation & Pydantic Models
# ---------------------------------------------------------------------------
def test_bug_report_schema_validation():
    finding = BugFinding(
        bug_id="BUG-001",
        title="Zero division error in divide_numbers",
        description="divide_numbers does not handle denominator == 0",
        category="zero_division",
        severity="critical",
        severity_justification="Unhandled zero division triggers process crash.",
        confidence="high",
        confidence_rationale="Reproduced directly by automated test execution.",
        evidence_type="test_failure",
        file_path="math_ops.py",
        start_line=6,
        end_line=12,
        code_excerpt="return numerator / denominator",
        expected_behavior="Should raise ValueError or return 0 on zero denominator.",
        observed_behavior="ZeroDivisionError: division by zero",
        likely_root_cause="Missing check for denominator == 0",
        reproduction_steps=["pytest tests/test_math.py"],
        suggested_next_diagnostic_step="Add unit test with denominator = 0",
        suggested_fix_direction="Add `if denominator == 0: raise ValueError(...)`",
        verification_status="reproduced",
    )

    report = BugInvestigationReport(
        query="Investigate division by zero crash",
        repository_path="fixtures/synthetic_bug_repo",
        summary="Found 1 critical zero division bug.",
        findings=[finding],
        missing_evidence=["Performance profiling unverified"],
        next_steps=["Apply guard clause"],
        sources=[
            Citation(
                source_index=1,
                file_path="math_ops.py",
                symbol_or_heading="divide_numbers",
                start_line=6,
                end_line=12,
                programming_language="python",
                raw_reference="[1]",
            )
        ],
    )

    # Verify JSON serialization and round-trip
    data_dict = report.to_dict()
    assert data_dict["findings"][0]["bug_id"] == "BUG-001"
    assert data_dict["findings"][0]["verification_status"] == "reproduced"

    json_str = json.dumps(data_dict)
    loaded = json.loads(json_str)
    assert loaded["query"] == "Investigate division by zero crash"

    # Terminal output formatting
    terminal_text = report.format_cli_output()
    assert "BUG INVESTIGATION REPORT" in terminal_text
    assert "BUG-001" in terminal_text
    assert "CRITICAL" in terminal_text


# ---------------------------------------------------------------------------
# Test 6: Full Investigation Orchestration Workflow
# ---------------------------------------------------------------------------
def test_investigator_orchestration_workflow(synthetic_bug_repo_path: Path):
    investigator = BugInvestigator(
        repo_path=synthetic_bug_repo_path,
        timeout_seconds=20,
    )

    # Investigate zero division in divide_numbers with test execution
    report = investigator.investigate(
        query="Investigate ZeroDivisionError in divide_numbers",
        target_file="math_ops.py",
        run_tests=True,
    )

    assert len(report.findings) >= 1
    # Check that at least one finding identifies zero division
    zero_div_findings = [f for f in report.findings if f.category == "zero_division"]
    assert len(zero_div_findings) >= 1

    first_find = zero_div_findings[0]
    assert first_find.file_path == "math_ops.py"
    assert first_find.severity in ("critical", "high")
    assert first_find.confidence == "high"
    assert len(first_find.reproduction_steps) > 0

    # Ensure source citations point to real files and valid lines
    assert len(report.sources) >= 1
    for s in report.sources:
        assert (synthetic_bug_repo_path / s.file_path).exists()
        assert s.start_line >= 1
        assert s.end_line >= s.start_line

    # Verify caller traces are present
    assert len(report.call_traces) >= 1
    assert any("consumer.py" in t.caller_file for t in report.call_traces)


# ---------------------------------------------------------------------------
# Test 7: False-Positive Handling (Clean Function)
# ---------------------------------------------------------------------------
def test_clean_function_false_positive_handling(synthetic_bug_repo_path: Path):
    investigator = BugInvestigator(repo_path=synthetic_bug_repo_path)

    # Investigate clean function without any bug queries
    report = investigator.investigate(
        query="Inspect format_user_name utility function",
        target_file="clean_service.py",
        target_symbol="format_user_name",
        run_tests=False,
    )

    # Clean function format_user_name should NOT have bug findings!
    clean_findings = [f for f in report.findings if f.file_path == "clean_service.py"]
    assert len(clean_findings) == 0


# ---------------------------------------------------------------------------
# Test 8: Investigation Timeouts and Limit Guards
# ---------------------------------------------------------------------------
def test_investigator_timeout_handling(synthetic_bug_repo_path: Path):
    # Set extremely low timeout (0.001s) to test graceful timeout handling
    investigator = BugInvestigator(
        repo_path=synthetic_bug_repo_path,
        timeout_seconds=0,
    )

    report = investigator.investigate(
        query="Run test suite and check timeout",
        run_tests=True,
    )

    assert report.test_summary is not None
    # Either executed cleanly or marked timed_out
    if report.test_summary.timed_out:
        assert any("timed out" in m.lower() or "timeout" in m.lower() for m in report.missing_evidence)


# ---------------------------------------------------------------------------
# Test 9: CLI 'investigate' Command
# ---------------------------------------------------------------------------
def test_cli_investigate_command(synthetic_bug_repo_path: Path, capsys: pytest.CaptureFixture):
    # Terminal format
    ret = main([
        "investigate",
        "--repo",
        str(synthetic_bug_repo_path),
        "--query",
        "Investigate ZeroDivisionError",
        "--run-tests",
    ])
    assert ret == 0
    captured = capsys.readouterr()
    assert "BUG INVESTIGATION REPORT" in captured.out
    assert "math_ops.py" in captured.out

    # JSON format
    ret_json = main([
        "investigate",
        "--repo",
        str(synthetic_bug_repo_path),
        "--query",
        "Investigate ZeroDivisionError",
        "--run-tests",
        "--json",
    ])
    assert ret_json == 0
    captured_json = capsys.readouterr()
    parsed = json.loads(captured_json.out)
    assert parsed["query"] == "Investigate ZeroDivisionError"
    assert len(parsed["findings"]) >= 1
