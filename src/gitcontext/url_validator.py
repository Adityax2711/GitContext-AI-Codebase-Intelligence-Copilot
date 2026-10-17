"""Shared GitHub repository URL parser, normalizer, and validator.

Handles:
- https://github.com/owner/repository
- https://github.com/owner/repository/
- https://github.com/owner/repository.git
- URLs with leading or trailing whitespace
- Short identifiers: owner/repository
- Case normalization and URL encoding

Rejects with descriptive, user-friendly explanations:
- User profile URLs (https://github.com/owner)
- Issue URLs (https://github.com/owner/repo/issues/123)
- Pull request URLs (https://github.com/owner/repo/pull/4)
- Tree / blob / commit / branch URLs (https://github.com/owner/repo/blob/...)
- Non-GitHub URLs (https://gitlab.com/...)
- Malformed inputs
"""

from __future__ import annotations

import re
import urllib.parse
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional, Tuple


@dataclass
class ParsedGitHubRepo:
    """Canonical representation of a parsed GitHub repository."""

    owner: str
    repo: str
    full_name: str
    canonical_url: str
    clone_url: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class GitHubUrlValidationError(ValueError):
    """Raised when a repository URL or identifier fails validation."""

    def __init__(self, message: str, code: str = "invalid_url") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


# Valid GitHub username: 1-39 chars, alphanumeric or single hyphens, cannot begin/end with hyphen
# Valid GitHub repo name: 1-100 chars, alphanumeric, '.', '_', '-'
VALID_OWNER_REGEX = re.compile(r"^[a-zA-Z0-9](?:[a-zA-Z0-9._-]{0,38})$")
VALID_REPO_REGEX = re.compile(r"^[a-zA-Z0-9._-]{1,100}$")


def validate_and_parse_github_url(raw_input: str) -> ParsedGitHubRepo:
    """Parse, normalize, and strictly validate a GitHub repository URL or identifier.

    Args:
        raw_input: Raw string input from user or API.

    Returns:
        ParsedGitHubRepo with canonical owner, repo, and URLs.

    Raises:
        GitHubUrlValidationError: If the input is invalid, with actionable error message.
    """
    if not raw_input or not raw_input.strip():
        raise GitHubUrlValidationError(
            "Repository URL cannot be empty. Please enter a GitHub repository URL or owner/repository identifier.",
            code="empty_url",
        )

    # Trim leading and trailing whitespace
    cleaned = raw_input.strip()

    # URL decode any percent-encoded characters (e.g., %20, %2F)
    try:
        decoded = urllib.parse.unquote(cleaned)
    except Exception:
        decoded = cleaned

    # Check if this is an owner/repo short identifier
    if "/" in decoded and not decoded.startswith("http://") and not decoded.startswith("https://") and not decoded.startswith("github.com/"):
        parts = decoded.split("/")
        if len(parts) == 2:
            owner, repo = parts[0].strip(), parts[1].strip()
            # Remove .git suffix if present
            if repo.endswith(".git"):
                repo = repo[:-4]

            _validate_names(owner, repo, cleaned)
            return _build_repo(owner, repo)

    # Check if input has no slashes and is not a URL
    if "/" not in decoded and not decoded.startswith("http://") and not decoded.startswith("https://"):
        raise GitHubUrlValidationError(
            f"Invalid repository identifier '{cleaned}'. Expected format: https://github.com/owner/repository or owner/repository.",
            code="invalid_format",
        )

    # Parse as URL
    url_to_parse = decoded
    if not url_to_parse.startswith("http://") and not url_to_parse.startswith("https://"):
        if url_to_parse.startswith("github.com/"):
            url_to_parse = f"https://{url_to_parse}"
        elif url_to_parse.startswith("www.github.com/"):
            url_to_parse = f"https://{url_to_parse}"
        else:
            url_to_parse = f"https://{url_to_parse}"

    try:
        parsed = urllib.parse.urlparse(url_to_parse)
    except Exception as e:
        raise GitHubUrlValidationError(
            f"Malformed URL: '{cleaned}'. Please check the URL and try again.",
            code="malformed_url",
        ) from e

    # Validate hostname
    hostname = (parsed.hostname or "").lower()
    if hostname not in ("github.com", "www.github.com"):
        raise GitHubUrlValidationError(
            f"Unsupported host '{hostname or parsed.netloc}'. GitContext currently supports GitHub repositories (e.g., https://github.com/owner/repository).",
            code="unsupported_host",
        )

    # Split path segments (ignoring empty segments caused by consecutive/trailing slashes)
    path_segments = [seg for seg in parsed.path.split("/") if seg]

    if len(path_segments) == 0:
        raise GitHubUrlValidationError(
            "Please provide a specific GitHub repository URL (e.g., https://github.com/owner/repository), not just the homepage.",
            code="empty_path",
        )

    if len(path_segments) == 1:
        # Profile URL detected: https://github.com/owner
        owner = path_segments[0]
        raise GitHubUrlValidationError(
            f"'{cleaned}' is a GitHub user profile, not a repository. Please enter a repository URL like https://github.com/{owner}/your-repo.",
            code="profile_url",
        )

    owner = path_segments[0].strip()
    repo = path_segments[1].strip()

    # Check for .git suffix
    if repo.endswith(".git"):
        repo = repo[:-4]

    # Inspect third+ segments to provide helpful explanations for sub-paths
    if len(path_segments) > 2:
        sub_type = path_segments[2].lower()
        canonical_suggest = f"https://github.com/{owner}/{repo}"

        if sub_type in ("issues", "issue"):
            raise GitHubUrlValidationError(
                f"The provided link is an issue page, not a repository root. To import this repository, use: {canonical_suggest}",
                code="issue_url",
            )
        if sub_type in ("pull", "pulls"):
            raise GitHubUrlValidationError(
                f"The provided link is a pull request page, not a repository root. To import this repository, use: {canonical_suggest}",
                code="pull_request_url",
            )
        if sub_type in ("blob", "tree", "raw", "edit"):
            raise GitHubUrlValidationError(
                f"The provided link points to a specific branch or file. Please provide the repository root URL: {canonical_suggest}",
                code="file_or_branch_url",
            )
        if sub_type in ("commit", "commits"):
            raise GitHubUrlValidationError(
                f"The provided link is a commit page. Please use the repository root URL: {canonical_suggest}",
                code="commit_url",
            )
        if sub_type in ("releases", "tags"):
            raise GitHubUrlValidationError(
                f"The provided link is a releases page. Please use the repository root URL: {canonical_suggest}",
                code="releases_url",
            )

        # Generic extra path
        raise GitHubUrlValidationError(
            f"The provided link contains extra path segments. Please use the repository root URL: {canonical_suggest}",
            code="extra_path_segments",
        )

    _validate_names(owner, repo, cleaned)
    return _build_repo(owner, repo)


def _validate_names(owner: str, repo: str, original_input: str) -> None:
    """Validate owner and repository name syntax."""
    if not VALID_OWNER_REGEX.match(owner):
        raise GitHubUrlValidationError(
            f"Invalid GitHub owner name '{owner}'. GitHub usernames only contain letters, numbers, hyphens, and periods.",
            code="invalid_owner_name",
        )
    if not VALID_REPO_REGEX.match(repo):
        raise GitHubUrlValidationError(
            f"Invalid repository name '{repo}'. Repository names only contain alphanumeric characters, hyphens, underscores, and periods.",
            code="invalid_repo_name",
        )


def _build_repo(owner: str, repo: str) -> ParsedGitHubRepo:
    """Construct canonical ParsedGitHubRepo object."""
    full_name = f"{owner}/{repo}"
    return ParsedGitHubRepo(
        owner=owner,
        repo=repo,
        full_name=full_name,
        canonical_url=f"https://github.com/{owner}/{repo}",
        clone_url=f"https://github.com/{owner}/{repo}.git",
    )
