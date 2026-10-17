"""Tests for the GitContext AI agent, tool registry, patch manager, and orchestrator."""

from pathlib import Path
import pytest

from gitcontext.agent.orchestrator import AgentOrchestrator
from gitcontext.agent.patch import PatchManager
from gitcontext.agent.tools import AgentToolRegistry
from gitcontext.llm import MockLLMClient
from gitcontext.tools.repo_inspector import PathTraversalError, RepoInspector


@pytest.fixture
def synthetic_bug_repo_path() -> Path:
    return Path(__file__).parent.parent / "fixtures" / "synthetic_bug_repo"


@pytest.fixture
def synthetic_repo_path() -> Path:
    return Path(__file__).parent.parent / "fixtures" / "synthetic_repo"


def test_tool_registry_initialization(synthetic_bug_repo_path: Path):
    registry = AgentToolRegistry(synthetic_bug_repo_path)
    tools = registry.list_tools()
    assert len(tools) >= 8

    tool_names = {t.name for t in tools}
    assert "search_codebase" in tool_names
    assert "read_file" in tool_names
    assert "find_symbols" in tool_names
    assert "find_callers" in tool_names
    assert "inspect_dependencies" in tool_names
    assert "run_static_analysis" in tool_names
    assert "run_tests" in tool_names
    assert "propose_patch" in tool_names
    assert "run_isolated_tests" in tool_names


def test_read_file_tool(synthetic_bug_repo_path: Path):
    registry = AgentToolRegistry(synthetic_bug_repo_path)
    res = registry.execute("read_file", {"file_path": "math_ops.py", "start_line": 6, "end_line": 12})
    assert res["status"] == "success"
    data = res["result"]
    assert "divide_numbers" in data["content"]
    assert data["start_line"] == 6
    assert data["end_line"] == 12


def test_path_traversal_prevention(synthetic_bug_repo_path: Path):
    registry = AgentToolRegistry(synthetic_bug_repo_path)
    res = registry.execute("read_file", {"file_path": "../../../etc/passwd"})
    assert res["status"] == "error"
    assert "Path traversal" in res["error"] or "outside repository" in res["error"]


def test_find_symbols_tool(synthetic_bug_repo_path: Path):
    registry = AgentToolRegistry(synthetic_bug_repo_path)
    res = registry.execute("find_symbols", {"name_query": "divide"})
    assert res["status"] == "success"
    symbols = res["result"]["symbols"]
    assert any(s["name"] == "divide_numbers" for s in symbols)


def test_static_analysis_tool(synthetic_bug_repo_path: Path):
    registry = AgentToolRegistry(synthetic_bug_repo_path)
    res = registry.execute("run_static_analysis", {"target_path": "math_ops.py"})
    assert res["status"] == "success"
    findings = res["result"]["findings"]
    assert any("ZERO_DIVISION" in f["rule_id"] for f in findings)


def test_run_tests_tool(synthetic_bug_repo_path: Path):
    registry = AgentToolRegistry(synthetic_bug_repo_path)
    res = registry.execute("run_tests", {})
    assert res["status"] == "success"
    data = res["result"]
    assert data["executed"] is True
    assert data["failed_tests"] >= 1
    failures = data["failures"]
    assert any("ZeroDivisionError" in f["error_type"] for f in failures)


def test_patch_manager_workflow(synthetic_bug_repo_path: Path):
    inspector = RepoInspector(synthetic_bug_repo_path)
    pm = PatchManager(inspector)

    orig_content = (synthetic_bug_repo_path / "math_ops.py").read_text(encoding="utf-8")
    mod_content = orig_content.replace(
        "    return numerator / denominator",
        "    if denominator == 0.0 or denominator == 0:\n        return 0.0\n    return numerator / denominator",
    )

    patch = pm.propose_patch(
        file_path="math_ops.py",
        modified_content=mod_content,
        title="Zero division fix",
        explanation="Return 0.0 on zero denominator",
    )
    assert patch.patch_id.startswith("patch-")
    assert "--- a/math_ops.py" in patch.diff
    assert "+++ b/math_ops.py" in patch.diff
    assert "+    if denominator == 0.0" in patch.diff

    # Verify in isolation without changing disk permanently
    ver_res = pm.verify_patch_in_isolation(patch.patch_id)
    assert ver_res["executed"] is True
    assert ver_res["fixed_known_bug"] is True
    assert ver_res["all_passed"] is True

    # Disk file must still have original content!
    current_disk = (synthetic_bug_repo_path / "math_ops.py").read_text(encoding="utf-8")
    assert current_disk == orig_content


def test_agent_orchestrator_investigate_flow(synthetic_bug_repo_path: Path):
    registry = AgentToolRegistry(synthetic_bug_repo_path)
    mock_llm = MockLLMClient()
    agent = AgentOrchestrator(tool_registry=registry, llm_client=mock_llm)

    result = agent.run("Investigate zero division error in divide_numbers")
    assert result.completed is True
    assert len(result.steps) >= 3
    assert len(result.findings) >= 1
    assert result.proposed_patch is not None
    assert result.test_results is not None
    assert result.test_results.get("all_passed") is True
    assert len(result.citations) >= 1
    assert any("math_ops.py" in c.file_path for c in result.citations)
