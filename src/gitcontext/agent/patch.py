"""Patch generation, diffing, isolated verification, and controlled application."""

from __future__ import annotations

import difflib
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union

from gitcontext.tools.repo_inspector import RepoInspector
from gitcontext.tools.test_runner import TestRunner


@dataclass
class PatchProposal:
    """Represents a proposed code patch with unified diff and verification status."""

    patch_id: str
    file_path: str  # Repository-relative normalized path
    title: str
    explanation: str
    diff: str
    original_content: str
    modified_content: str
    status: Literal["pending", "verified", "applied", "rejected", "reverted"] = "pending"
    created_at: float = field(default_factory=time.time)
    test_verification: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "patch_id": self.patch_id,
            "file_path": self.file_path,
            "title": self.title,
            "explanation": self.explanation,
            "diff": self.diff,
            "original_content": self.original_content,
            "modified_content": self.modified_content,
            "status": self.status,
            "created_at": self.created_at,
            "test_verification": self.test_verification,
        }


class PatchManager:
    """Manages patch generation, unified diff formatting, isolated testing, and safe application."""

    def __init__(
        self,
        repo_inspector: RepoInspector,
        test_runner: Optional[TestRunner] = None,
    ) -> None:
        self.inspector = repo_inspector
        self.repo_path = repo_inspector.repo_path
        self.test_runner = test_runner or TestRunner(repo_inspector)
        self.patches: Dict[str, PatchProposal] = {}

    @staticmethod
    def generate_unified_diff(
        file_path: str,
        original_content: str,
        modified_content: str,
    ) -> str:
        """Produce a standard git-style unified diff."""
        orig_lines = original_content.splitlines(keepends=True)
        mod_lines = modified_content.splitlines(keepends=True)

        diff_lines = list(
            difflib.unified_diff(
                orig_lines,
                mod_lines,
                fromfile=f"a/{file_path}",
                tofile=f"b/{file_path}",
                lineterm="\n",
            )
        )
        return "".join(diff_lines)

    def propose_patch(
        self,
        file_path: str,
        modified_content: str,
        title: str = "Proposed Code Patch",
        explanation: str = "",
    ) -> PatchProposal:
        """Create and stage a proposed code patch without modifying the repository."""
        safe_path = self.inspector.resolve_safe_path(file_path)
        rel_path = self.inspector.to_relative_path(safe_path)

        if not safe_path.exists():
            original_content = ""
        else:
            original_content = safe_path.read_text(encoding="utf-8", errors="replace")

        # Normalize line endings to LF for clean diffs
        norm_orig = original_content.replace("\r\n", "\n")
        norm_mod = modified_content.replace("\r\n", "\n")

        diff = self.generate_unified_diff(rel_path, norm_orig, norm_mod)
        patch_id = f"patch-{uuid.uuid4().hex[:8]}"

        proposal = PatchProposal(
            patch_id=patch_id,
            file_path=rel_path,
            title=title,
            explanation=explanation,
            diff=diff,
            original_content=norm_orig,
            modified_content=norm_mod,
            status="pending",
        )
        self.patches[patch_id] = proposal
        return proposal

    def propose_line_replacement(
        self,
        file_path: str,
        start_line: int,
        end_line: int,
        replacement_code: str,
        title: str = "Proposed Replacement",
        explanation: str = "",
    ) -> PatchProposal:
        """Propose a patch targeting a specific 1-indexed line range."""
        safe_path = self.inspector.resolve_safe_path(file_path)
        original_content = safe_path.read_text(encoding="utf-8", errors="replace")
        lines = original_content.splitlines()

        s_idx = max(0, start_line - 1)
        e_idx = min(len(lines), end_line)

        repl_lines = replacement_code.strip().splitlines()
        new_lines = lines[:s_idx] + repl_lines + lines[e_idx:]
        modified_content = "\n".join(new_lines) + ("\n" if original_content.endswith("\n") else "")

        return self.propose_patch(
            file_path=file_path,
            modified_content=modified_content,
            title=title,
            explanation=explanation,
        )

    def verify_patch_in_isolation(
        self,
        patch_id: str,
        test_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Apply patch temporarily, execute isolated tests, and restore original code immediately."""
        proposal = self.patches.get(patch_id)
        if not proposal:
            raise KeyError(f"Patch ID '{patch_id}' not found.")

        safe_path = self.inspector.resolve_safe_path(proposal.file_path)
        original_disk = safe_path.read_text(encoding="utf-8", errors="replace") if safe_path.exists() else None

        # 1. Measure baseline before patch if needed
        pre_summary = self.test_runner.run_tests(test_path=test_path)

        # 2. Write patch to disk temporarily
        try:
            safe_path.parent.mkdir(parents=True, exist_ok=True)
            safe_path.write_text(proposal.modified_content, encoding="utf-8")

            # 3. Execute tests under isolated environment
            post_summary = self.test_runner.run_tests(test_path=test_path)
        finally:
            # 4. CRITICAL SAFETY: Always restore original content immediately
            if original_disk is not None:
                safe_path.write_text(original_disk, encoding="utf-8")
            elif safe_path.exists():
                safe_path.unlink()

        # Assess results
        fixed_errors = pre_summary.failed_tests > 0 and post_summary.failed_tests < pre_summary.failed_tests
        all_passed = post_summary.executed and post_summary.failed_tests == 0 and post_summary.error_tests == 0
        has_regressions = post_summary.failed_tests > pre_summary.failed_tests

        verification_result = {
            "patch_id": patch_id,
            "executed": post_summary.executed,
            "total_tests": post_summary.total_tests,
            "passed_tests": post_summary.passed_tests,
            "failed_tests": post_summary.failed_tests,
            "errors": post_summary.error_tests,
            "pre_failures": pre_summary.failed_tests,
            "fixed_known_bug": fixed_errors,
            "all_passed": all_passed,
            "regressions": has_regressions,
            "raw_output": post_summary.raw_output[:1000],
            "failures": [f.model_dump() for f in post_summary.failures],
            "status": "passed" if all_passed else ("partially_fixed" if fixed_errors else "failed"),
        }

        proposal.test_verification = verification_result
        if all_passed:
            proposal.status = "verified"

        return verification_result

    def apply_patch(self, patch_id: str) -> bool:
        """Apply approved patch to disk. Creates .bak backup file for rollback safety."""
        proposal = self.patches.get(patch_id)
        if not proposal:
            raise KeyError(f"Patch ID '{patch_id}' not found.")

        safe_path = self.inspector.resolve_safe_path(proposal.file_path)

        # Create backup if file exists
        if safe_path.exists():
            backup_path = safe_path.with_suffix(safe_path.suffix + ".gitcontext_bak")
            backup_path.write_text(safe_path.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")

        safe_path.parent.mkdir(parents=True, exist_ok=True)
        safe_path.write_text(proposal.modified_content, encoding="utf-8")
        proposal.status = "applied"
        return True

    def reject_patch(self, patch_id: str) -> bool:
        """Reject proposed patch."""
        proposal = self.patches.get(patch_id)
        if not proposal:
            raise KeyError(f"Patch ID '{patch_id}' not found.")

        proposal.status = "rejected"
        return True

    def rollback_patch(self, patch_id: str) -> bool:
        """Roll back an applied patch using the original content or backup."""
        proposal = self.patches.get(patch_id)
        if not proposal:
            raise KeyError(f"Patch ID '{patch_id}' not found.")

        safe_path = self.inspector.resolve_safe_path(proposal.file_path)
        backup_path = safe_path.with_suffix(safe_path.suffix + ".gitcontext_bak")

        if backup_path.exists():
            safe_path.write_text(backup_path.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
            backup_path.unlink()
        else:
            safe_path.write_text(proposal.original_content, encoding="utf-8")

        proposal.status = "reverted"
        return True

    def get_patch(self, patch_id: str) -> Optional[PatchProposal]:
        return self.patches.get(patch_id)

    def list_patches(self) -> List[PatchProposal]:
        return list(self.patches.values())
