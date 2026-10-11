"""Isolated test runner and test failure investigation tool."""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Dict, List, Optional, Union

from gitcontext.bug_models import TestExecutionSummary, TestFailure
from gitcontext.tools.repo_inspector import RepoInspector

# Regex patterns for parsing pytest outputs
SUMMARY_RE = re.compile(
    r"=(?:=|\s)+((?:\d+\s+[a-z]+(?:,\s*)?)+)\s+in\s+[\d\.]+s(?:=|\s)+",
    re.IGNORECASE,
)
FAILED_COUNT_RE = re.compile(r"(\d+)\s+failed", re.IGNORECASE)
PASSED_COUNT_RE = re.compile(r"(\d+)\s+passed", re.IGNORECASE)
ERROR_COUNT_RE = re.compile(r"(\d+)\s+error", re.IGNORECASE)

# Traceback file matcher: e.g. File "...", line 12, in my_func or path.py:12: in test_foo
TB_FILE_LINE_RE = re.compile(
    r'(?:File\s+["\']([^"\']+)["\'],\s+line\s+(\d+)(?:,\s+in\s+([a-zA-Z0-9_]+))?)|(?:([a-zA-Z0-9_\-\./\\]+\.py):(\d+):(?:\s+in\s+([a-zA-Z0-9_]+))?)'
)


class TestRunner:
    """Executes tests in an isolated, timeout-guarded environment and parses failures."""

    __test__ = False

    SENSITIVE_ENV_KEYS = {
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "ANTHROPIC_API_KEY",
        "AWS_SECRET_ACCESS_KEY",
        "GITHUB_TOKEN",
        "SECRET_KEY",
        "PASSWORD",
    }

    def __init__(
        self,
        repo_inspector: RepoInspector,
        default_timeout_seconds: int = 25,
    ) -> None:
        self.inspector = repo_inspector
        self.repo_path = repo_inspector.repo_path
        self.default_timeout = default_timeout_seconds

    def detect_framework(self) -> Optional[str]:
        """Detect whether pytest or standard test fixtures exist in the repo."""
        if (self.repo_path / "pytest.ini").exists() or (self.repo_path / "conftest.py").exists():
            return "pytest"

        pyproject = self.repo_path / "pyproject.toml"
        if pyproject.exists():
            try:
                content = pyproject.read_text(encoding="utf-8", errors="replace")
                if "tool.pytest" in content or "pytest" in content:
                    return "pytest"
            except Exception:
                pass

        # Check for test directory or test files
        tests_dir = self.repo_path / "tests"
        if tests_dir.is_dir() and any(tests_dir.glob("test_*.py")):
            return "pytest"

        if any(self.repo_path.glob("**/test_*.py")):
            return "pytest"

        return None

    def _sanitize_env(self) -> Dict[str, str]:
        """Create sanitized environment variables without API keys, secrets, or tokens."""
        env: Dict[str, str] = {}
        for k, v in os.environ.items():
            k_upper = k.upper()
            if any(sub in k_upper for sub in ("KEY", "SECRET", "TOKEN", "PASSW", "CREDENTIAL", "AUTH")):
                continue
            env[k] = v

        # Configure python path and prevent pyc caching
        existing_pp = env.get("PYTHONPATH", "")
        repo_str = str(self.repo_path)
        src_str = str(self.repo_path / "src")
        env["PYTHONPATH"] = f"{src_str}{os.pathsep}{repo_str}{os.pathsep}{existing_pp}" if existing_pp else f"{src_str}{os.pathsep}{repo_str}"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        return env

    def run_tests(
        self,
        test_path: Optional[Union[str, Path]] = None,
        timeout_seconds: Optional[int] = None,
    ) -> TestExecutionSummary:
        """Run pytest in an isolated subprocess with strict timeouts and sanitized env."""
        timeout = timeout_seconds if timeout_seconds is not None else self.default_timeout
        # Ensure non-positive timeout triggers immediately
        if timeout <= 0:
            timeout = 0.0001
        framework = self.detect_framework() or "pytest"

        cmd = [sys.executable, "-m", "pytest", "-v", "--tb=short", "--no-header"]
        if test_path:
            safe_target = self.inspector.resolve_safe_path(test_path)
            cmd.append(str(safe_target))

        sanitized_env = self._sanitize_env()

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(self.repo_path),
                env=sanitized_env,
                timeout=timeout,
            )
            raw_output = (proc.stdout + "\n" + proc.stderr).strip()
            timed_out = False
        except subprocess.TimeoutExpired as te:
            stdout_text = te.stdout.decode("utf-8", errors="replace") if te.stdout else ""
            stderr_text = te.stderr.decode("utf-8", errors="replace") if te.stderr else ""
            raw_output = f"Test execution timed out after {timeout} seconds.\n{stdout_text}\n{stderr_text}".strip()
            return TestExecutionSummary(
                framework=framework,
                executed=True,
                total_tests=0,
                passed_tests=0,
                failed_tests=1,
                error_tests=0,
                timed_out=True,
                failures=[
                    TestFailure(
                        test_name="<timeout>",
                        file_path=str(test_path or "tests"),
                        error_type="TimeoutExpired",
                        error_message=f"Test execution exceeded maximum timeout of {timeout}s",
                        stack_trace=raw_output,
                    )
                ],
                raw_output=raw_output,
            )
        except Exception as e:
            return TestExecutionSummary(
                framework=framework,
                executed=False,
                raw_output=f"Failed to start test execution: {e}",
            )

        # Parse test results
        passed_count = 0
        failed_count = 0
        error_count = 0

        m_failed = FAILED_COUNT_RE.search(raw_output)
        if m_failed:
            failed_count = int(m_failed.group(1))

        m_passed = PASSED_COUNT_RE.search(raw_output)
        if m_passed:
            passed_count = int(m_passed.group(1))

        m_error = ERROR_COUNT_RE.search(raw_output)
        if m_error:
            error_count = int(m_error.group(1))

        total_tests = passed_count + failed_count + error_count

        failures = self._parse_failures(raw_output)

        return TestExecutionSummary(
            framework=framework,
            executed=True,
            total_tests=total_tests,
            passed_tests=passed_count,
            failed_tests=failed_count,
            error_tests=error_count,
            timed_out=timed_out,
            failures=failures,
            raw_output=raw_output,
        )

    def _parse_failures(self, raw_output: str) -> List[TestFailure]:
        """Parse failed test blocks and correlate stack traces to source files."""
        failures: List[TestFailure] = []

        # Sections in pytest output usually start with "FAILURES"
        if "FAILURES" not in raw_output and "ERRORS" not in raw_output:
            return failures

        # Split failure sections by lines with _________________ test_name _________________
        fail_blocks = re.split(r"_{5,}\s+([^\n]+?)\s+_{5,}", raw_output)

        if len(fail_blocks) > 1:
            for i in range(1, len(fail_blocks), 2):
                test_title = fail_blocks[i].strip()
                block_content = fail_blocks[i + 1] if i + 1 < len(fail_blocks) else ""
                fail = self._parse_single_failure_block(test_title, block_content)
                failures.append(fail)
        else:
            # Fallback parsing for short failures
            lines = raw_output.splitlines()
            for line in lines:
                if "FAILED" in line and "::" in line:
                    parts = line.split("::")
                    failures.append(
                        TestFailure(
                            test_name=parts[-1].strip(),
                            file_path=parts[0].replace("FAILED", "").strip(),
                            error_type="AssertionError",
                            error_message="Test failed assertion",
                            stack_trace=line,
                        )
                    )

        return failures

    def _parse_single_failure_block(self, test_name: str, block: str) -> TestFailure:
        """Extract error type, message, and suspected repository source location."""
        lines = block.strip().splitlines()

        # Identify exception or assertion line: usually starts with "E   "
        error_type = "AssertionError"
        error_message = ""
        suspected_source_file = None
        suspected_source_line = None
        suspected_source_symbol = None
        test_file_path = "tests"

        for line in reversed(lines):
            if line.startswith("E   "):
                clean_e = line[4:].strip()
                if ":" in clean_e:
                    parts = clean_e.split(":", 1)
                    error_type = parts[0].strip()
                    error_message = parts[1].strip()
                else:
                    error_message = clean_e
                break

        if not error_message and lines:
            error_message = lines[-1].strip()

        # Traceback lines to find source file inside the repository
        for line in lines:
            # Match traceback pointers
            for m in TB_FILE_LINE_RE.finditer(line):
                # Could be format 1 or format 2
                f_path = m.group(1) or m.group(4)
                f_line = m.group(2) or m.group(5)
                f_sym = m.group(3) or m.group(6)

                if not f_path or not f_line:
                    continue

                try:
                    f_line_int = int(f_line)
                except ValueError:
                    continue

                # Check if it resolves within repo
                try:
                    rel_p = self.inspector.to_relative_path(f_path)
                except Exception:
                    # Maybe it's already relative
                    rel_p = f_path.replace("\\", "/")

                # If it's a test file, record as test_file_path
                if "test" in rel_p.lower():
                    test_file_path = rel_p
                else:
                    # Non-test source file in repo: this is likely the implementation location!
                    suspected_source_file = rel_p
                    suspected_source_line = f_line_int
                    suspected_source_symbol = f_sym

        return TestFailure(
            test_name=test_name,
            file_path=test_file_path,
            error_type=error_type,
            error_message=error_message,
            stack_trace=block.strip(),
            suspected_source_file=suspected_source_file,
            suspected_source_line=suspected_source_line,
            suspected_source_symbol=suspected_source_symbol,
        )
