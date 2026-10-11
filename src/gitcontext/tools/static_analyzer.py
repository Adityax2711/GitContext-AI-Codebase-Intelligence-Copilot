"""Static analysis integration supporting Ruff, AST diagnostics, and optional Mypy."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import List, Optional, Union

from gitcontext.bug_models import StaticAnalysisFinding
from gitcontext.ingestion import should_ignore_dir, should_ignore_file
from gitcontext.tools.repo_inspector import RepoInspector


class StaticAnalyzer:
    """Runs and normalizes static analysis checks from Ruff, Python AST, and Mypy."""

    def __init__(
        self,
        repo_inspector: RepoInspector,
        ruff_executable: Optional[str] = None,
        mypy_executable: Optional[str] = None,
    ) -> None:
        self.inspector = repo_inspector
        self.repo_path = repo_inspector.repo_path
        self.ruff_cmd = ruff_executable or self._find_ruff()
        self.mypy_cmd = mypy_executable or self._find_mypy()

    def _find_ruff(self) -> Optional[List[str]]:
        """Determine command list to run ruff."""
        # 1. Try python -m ruff
        try:
            res = subprocess.run(
                [sys.executable, "-m", "ruff", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if res.returncode == 0:
                return [sys.executable, "-m", "ruff"]
        except Exception:
            pass

        # 2. Try global ruff on PATH
        which_ruff = shutil.which("ruff")
        if which_ruff:
            return [which_ruff]

        return None

    def _find_mypy(self) -> Optional[List[str]]:
        """Determine command list to run mypy."""
        try:
            res = subprocess.run(
                [sys.executable, "-m", "mypy", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if res.returncode == 0:
                return [sys.executable, "-m", "mypy"]
        except Exception:
            pass

        which_mypy = shutil.which("mypy")
        if which_mypy:
            return [which_mypy]

        return None

    def run_ruff(
        self,
        target_path: Optional[Union[str, Path]] = None,
        timeout_seconds: int = 20,
    ) -> List[StaticAnalysisFinding]:
        """Run Ruff on repo or specified path and parse JSON findings."""
        if not self.ruff_cmd:
            return []

        resolved_target = (
            self.inspector.resolve_safe_path(target_path)
            if target_path
            else self.repo_path
        )

        cmd = self.ruff_cmd + [
            "check",
            "--output-format=json",
            str(resolved_target),
        ]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(self.repo_path),
                timeout=timeout_seconds,
            )
        except (subprocess.TimeoutExpired, Exception):
            return []

        # Ruff returns exit code 1 if lint errors are found, but still outputs JSON
        raw_stdout = proc.stdout.strip()
        if not raw_stdout:
            return []

        findings: List[StaticAnalysisFinding] = []
        try:
            items = json.loads(raw_stdout)
            if not isinstance(items, list):
                return []
        except json.JSONDecodeError:
            return []

        for item in items:
            raw_file = item.get("filename", "")
            try:
                rel_file = self.inspector.to_relative_path(raw_file)
            except Exception:
                rel_file = raw_file

            rule_code = item.get("code") or "UNKNOWN"
            if rule_code == "E902":
                continue
            msg = item.get("message", "Lint diagnostic")
            loc = item.get("location", {})
            end_loc = item.get("end_location", {})

            s_line = loc.get("row", 1)
            e_line = end_loc.get("row", s_line)

            # Assign severity based on rule code prefix
            severity: str = "medium"
            if rule_code.startswith("F821") or rule_code.startswith("E9"):
                severity = "critical"
            elif rule_code.startswith("B") or rule_code.startswith("F"):
                severity = "high"
            elif rule_code.startswith("W"):
                severity = "low"

            findings.append(
                StaticAnalysisFinding(
                    rule_id=rule_code,
                    message=msg,
                    file_path=rel_file,
                    start_line=max(1, s_line),
                    end_line=max(s_line, e_line),
                    tool_source="ruff",
                    severity=severity,  # type: ignore[arg-type]
                )
            )

        return findings

    def run_ast_diagnostics(
        self,
        target_path: Optional[Union[str, Path]] = None,
    ) -> List[StaticAnalysisFinding]:
        """Perform deterministic AST-level inspections for obvious defect patterns."""
        findings: List[StaticAnalysisFinding] = []

        if target_path:
            targets = [self.inspector.resolve_safe_path(target_path)]
        else:
            targets = [
                p
                for p in self.repo_path.rglob("*.py")
                if not any(should_ignore_dir(part) for part in p.parent.parts)
                and not should_ignore_file(p.name)
            ]

        for py_file in targets:
            rel_file = self.inspector.to_relative_path(py_file)
            try:
                source = py_file.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            # Check for syntax errors first
            try:
                tree = ast.parse(source, filename=str(py_file))
            except SyntaxError as syn:
                findings.append(
                    StaticAnalysisFinding(
                        rule_id="AST:SYNTAX_ERROR",
                        message=f"SyntaxError: {syn.msg}",
                        file_path=rel_file,
                        start_line=syn.lineno or 1,
                        end_line=syn.lineno or 1,
                        tool_source="ast_inspector",
                        severity="critical",
                    )
                )
                continue

            class DefectVisitor(ast.NodeVisitor):
                def visit_BinOp(self, node: ast.BinOp) -> None:
                    # Check division by zero: a / 0 or a // 0 or a % 0
                    if isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)):
                        if isinstance(node.right, ast.Constant) and node.right.value == 0:
                            s_line = getattr(node, "lineno", 1)
                            e_line = getattr(node, "end_lineno", s_line)
                            findings.append(
                                StaticAnalysisFinding(
                                    rule_id="AST:ZERO_DIVISION",
                                    message="Division, floor division, or modulo by literal zero detected.",
                                    file_path=rel_file,
                                    start_line=s_line,
                                    end_line=e_line,
                                    tool_source="ast_inspector",
                                    severity="critical",
                                )
                            )
                    self.generic_visit(node)

                def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
                    # Check bare except: except: pass
                    if node.type is None:
                        s_line = getattr(node, "lineno", 1)
                        e_line = getattr(node, "end_lineno", s_line)
                        findings.append(
                            StaticAnalysisFinding(
                                rule_id="AST:BARE_EXCEPT",
                                message="Bare 'except:' clause catches all exceptions including system exits.",
                                file_path=rel_file,
                                start_line=s_line,
                                end_line=e_line,
                                tool_source="ast_inspector",
                                severity="low",
                            )
                        )
                    # Check silent except: except Exception: pass
                    if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                        s_line = getattr(node, "lineno", 1)
                        e_line = getattr(node, "end_lineno", s_line)
                        findings.append(
                            StaticAnalysisFinding(
                                rule_id="AST:SILENT_EXCEPT",
                                message="Exception handler silently suppresses exceptions with 'pass'.",
                                file_path=rel_file,
                                start_line=s_line,
                                end_line=e_line,
                                tool_source="ast_inspector",
                                severity="medium",
                            )
                        )
                    self.generic_visit(node)

            visitor = DefectVisitor()
            visitor.visit(tree)

        return findings

    def run_mypy(
        self,
        target_path: Optional[Union[str, Path]] = None,
        timeout_seconds: int = 30,
    ) -> List[StaticAnalysisFinding]:
        """Optionally run mypy type checker if available."""
        if not self.mypy_cmd:
            return []

        resolved_target = (
            self.inspector.resolve_safe_path(target_path)
            if target_path
            else self.repo_path
        )

        cmd = self.mypy_cmd + [
            "--no-error-summary",
            "--show-column-numbers",
            "--hide-error-context",
            str(resolved_target),
        ]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(self.repo_path),
                timeout=timeout_seconds,
            )
        except (subprocess.TimeoutExpired, Exception):
            return []

        findings: List[StaticAnalysisFinding] = []
        for line in proc.stdout.splitlines():
            # Example format: file.py:10:5: error: Incompatible return value type [return-value]
            parts = line.split(":", 3)
            if len(parts) >= 4 and "error:" in parts[3]:
                raw_file = parts[0].strip()
                try:
                    rel_file = self.inspector.to_relative_path(raw_file)
                except Exception:
                    rel_file = raw_file

                try:
                    line_no = int(parts[1].strip())
                except ValueError:
                    line_no = 1

                msg_clean = parts[3].strip()
                findings.append(
                    StaticAnalysisFinding(
                        rule_id="MYPY:TYPE_ERROR",
                        message=msg_clean,
                        file_path=rel_file,
                        start_line=line_no,
                        end_line=line_no,
                        tool_source="mypy",
                        severity="high",
                    )
                )

        return findings

    def analyze(
        self,
        target_path: Optional[Union[str, Path]] = None,
        run_mypy: bool = False,
    ) -> List[StaticAnalysisFinding]:
        """Aggregate static analysis findings across all configured analyzers."""
        results: List[StaticAnalysisFinding] = []

        # 1. Ruff linting
        ruff_findings = self.run_ruff(target_path=target_path)
        results.extend(ruff_findings)

        # 2. AST diagnostics (e.g. division by literal zero, bare except)
        ast_findings = self.run_ast_diagnostics(target_path=target_path)
        results.extend(ast_findings)

        # 3. Optional mypy
        if run_mypy:
            mypy_findings = self.run_mypy(target_path=target_path)
            results.extend(mypy_findings)

        # De-duplicate by (file_path, start_line, rule_id)
        seen = set()
        unique_findings: List[StaticAnalysisFinding] = []
        for f in results:
            key = (f.file_path, f.start_line, f.rule_id)
            if key not in seen:
                seen.add(key)
                unique_findings.append(f)

        return unique_findings
