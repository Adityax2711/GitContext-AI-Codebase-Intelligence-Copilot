"""Repository discovery, file filtering, and ingestion module."""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import List, Optional, Set

# Default directories to always skip
DEFAULT_IGNORED_DIRS: Set[str] = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "env",
    "ENV",
    "node_modules",
    "build",
    "dist",
    ".idea",
    ".vscode",
    "data",
    ".egg-info",
    "site-packages",
}

# Default file patterns to always skip (sensitive or binary)
DEFAULT_IGNORED_PATTERNS: Set[str] = {
    ".env",
    ".env.*",
    "*.pyc",
    "*.pyo",
    "*.pyd",
    "*.so",
    "*.dylib",
    "*.dll",
    "*.exe",
    "*.bin",
    "*.pem",
    "*.key",
    "*.cert",
    "*.id_rsa",
    "credentials.json",
    "secrets.json",
    "*.swp",
    "*.swo",
    "*.DS_Store",
}

# Supported file extensions for Phase 1
SUPPORTED_EXTENSIONS: Set[str] = {".py", ".md", ".markdown"}


class GitIgnoreFilter:
    """Parses and matches .gitignore rules against repository file paths."""

    def __init__(self, root_dir: Path, ignore_patterns: Optional[List[str]] = None) -> None:
        self.root_dir = root_dir.resolve()
        self.patterns: List[str] = list(ignore_patterns or [])
        self._load_gitignore()

    def _load_gitignore(self) -> None:
        gitignore_path = self.root_dir / ".gitignore"
        if not gitignore_path.is_file():
            return

        try:
            with open(gitignore_path, "r", encoding="utf-8", errors="ignore") as f:
                for raw_line in f:
                    line = raw_line.strip()
                    if not line or line.startswith("#"):
                        continue
                    # Normalize pattern
                    if line.endswith("/"):
                        line = line[:-1]
                    self.patterns.append(line)
        except OSError:
            pass

    def is_ignored(self, relative_path: str, is_dir: bool = False) -> bool:
        """Check if relative path matches any ignore pattern."""
        # Normalize to posix-style relative path
        norm_path = relative_path.replace("\\", "/").strip("/")
        parts = norm_path.split("/")

        # Check directory segments
        for part in parts:
            if part in DEFAULT_IGNORED_DIRS:
                return True
            if part.endswith(".egg-info"):
                return True

        # Check default pattern rules
        file_name = parts[-1]
        for pat in DEFAULT_IGNORED_PATTERNS:
            if fnmatch.fnmatch(file_name, pat) or fnmatch.fnmatch(norm_path, pat):
                return True

        # Check custom gitignore patterns
        for pat in self.patterns:
            # Match exact folder name or filename
            if fnmatch.fnmatch(file_name, pat) or fnmatch.fnmatch(norm_path, pat):
                return True
            # Match wildcard inside paths
            if fnmatch.fnmatch(norm_path, f"*/{pat}") or fnmatch.fnmatch(norm_path, f"{pat}/*"):
                return True
            # Match any directory match in path
            if any(fnmatch.fnmatch(part, pat) for part in parts):
                return True

        return False


def discover_repository_files(repo_path: Path) -> List[Path]:
    """Discover all supported code and documentation files in the repository.

    Respects .gitignore rules and excludes binary, virtual environment, and sensitive files.
    """
    resolved_path = repo_path.resolve()
    if not resolved_path.exists():
        raise FileNotFoundError(f"Repository directory does not exist: {repo_path}")
    if not resolved_path.is_dir():
        raise NotADirectoryError(f"Specified path is not a directory: {repo_path}")

    git_filter = GitIgnoreFilter(resolved_path)
    discovered: List[Path] = []

    for item in resolved_path.rglob("*"):
        if not item.is_file():
            continue

        try:
            rel_path = item.relative_to(resolved_path)
        except ValueError:
            continue

        rel_str = str(rel_path)
        if git_filter.is_ignored(rel_str, is_dir=False):
            continue

        if item.suffix.lower() in SUPPORTED_EXTENSIONS:
            discovered.append(item)

    return sorted(discovered)


def read_source_file(file_path: Path) -> Optional[str]:
    """Safely read text content of a source file.

    Returns None if file is binary, corrupted, or unreadable.
    """
    try:
        # Check for binary null bytes
        with open(file_path, "rb") as bf:
            sample = bf.read(1024)
            if b"\x00" in sample:
                return None

        # Read as UTF-8 with fallback replacement for weird characters
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except (OSError, UnicodeError):
        return None
