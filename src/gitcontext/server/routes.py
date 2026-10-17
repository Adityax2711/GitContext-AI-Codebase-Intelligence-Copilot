"""FastAPI route handlers for GitContext Copilot."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException, Query, Response
from fastapi.responses import RedirectResponse

from gitcontext.agent.orchestrator import AgentOrchestrator
from gitcontext.agent.tools import AgentToolRegistry
from gitcontext.auth import AuthService
from gitcontext.db import get_db
from gitcontext.indexing import get_default_index_dir, index_repository, load_index
from gitcontext.ingestion import should_ignore_dir, should_ignore_file
from gitcontext.github_service import GitHubService, parse_github_identifier
from gitcontext.investigator import BugInvestigator
from gitcontext.llm import get_llm_client
from gitcontext.server.models import (
    ChatMessage,
    ChatRequest,
    FileReadRequest,
    GitHubImportRequest,
    GitHubLinkTokenRequest,
    GitHubLoginRequest,
    InvestigateRequest,
    PatchActionRequest,
    RepositorySelectRequest,
    RunTestRequest,
    SearchRequest,
    URLValidateRequest,
    UserLoginRequest,
    UserRegisterRequest,
)
from gitcontext.tools.repo_inspector import RepoInspector
from gitcontext.url_validator import GitHubUrlValidationError, validate_and_parse_github_url

router = APIRouter(prefix="/api")


class ServerState:
    """Holds active repository and service instances."""

    def __init__(self) -> None:
        self.workspace_root = Path.cwd().resolve()
        # Default to synthetic_bug_repo fixture if it exists, otherwise current directory
        bug_repo = self.workspace_root / "fixtures" / "synthetic_bug_repo"
        if bug_repo.is_dir():
            self.active_repo_path = bug_repo
        else:
            self.active_repo_path = self.workspace_root

        self.index_dir = self.workspace_root / "data" / "index"
        self.github_service = GitHubService(repos_dir=self.workspace_root / "data" / "repos")
        try:
            self.llm_client = get_llm_client()
        except Exception:
            from gitcontext.llm import MockLLMClient
            self.llm_client = MockLLMClient()
        self.registry = AgentToolRegistry(self.active_repo_path, index_dir=self.index_dir)
        self.orchestrator = AgentOrchestrator(self.registry, llm_client=self.llm_client)
        self.db = get_db()
        self.auth_service = AuthService(db=self.db)
        self.conversation_history: List[Dict[str, str]] = []

    def select_repo(self, path_str: str, reindex: bool = False) -> Dict[str, Any]:
        """Switch active repository and reinitialize inspector and tools."""
        target = Path(path_str).resolve()
        if not target.exists():
            raise FileNotFoundError(f"Path does not exist: {path_str}")
        if not target.is_dir():
            raise NotADirectoryError(f"Path is not a directory: {path_str}")

        self.active_repo_path = target
        if reindex or not (self.index_dir / "chunks.jsonl").exists():
            try:
                index_repository(self.active_repo_path, self.index_dir)
            except Exception as e:
                pass

        self.registry = AgentToolRegistry(self.active_repo_path, index_dir=self.index_dir)
        self.orchestrator = AgentOrchestrator(self.registry, llm_client=self.llm_client)
        return {
            "repository_name": self.active_repo_path.name,
            "repository_path": str(self.active_repo_path),
            "status": "active",
        }


state = ServerState()


@router.get("/status")
def get_status() -> Dict[str, Any]:
    """Return system status, active repository, and LLM configuration."""
    chunks, meta = load_index(state.index_dir)
    return {
        "status": "healthy",
        "active_repository": {
            "name": state.active_repo_path.name,
            "path": str(state.active_repo_path),
            "is_dir": state.active_repo_path.is_dir(),
        },
        "index": {
            "total_chunks": len(chunks) if chunks else 0,
            "repository_indexed": meta.repository_name if meta else None,
            "last_indexed_at": meta.last_indexed_at if meta else None,
        },
        "llm": {
            "provider": getattr(state.llm_client, "provider_name", "unknown"),
            "model": getattr(state.llm_client, "model_name", "unknown"),
        },
    }


@router.get("/repositories")
def list_repositories() -> List[Dict[str, Any]]:
    """List available and suggested local repositories."""
    repos = []

    # 1. Active repo
    repos.append({
        "name": state.active_repo_path.name,
        "path": str(state.active_repo_path),
        "is_active": True,
        "category": "active",
    })

    # 2. Check fixtures
    fixtures_dir = state.workspace_root / "fixtures"
    if fixtures_dir.is_dir():
        for d in fixtures_dir.iterdir():
            if d.is_dir() and d != state.active_repo_path:
                repos.append({
                    "name": d.name,
                    "path": str(d.resolve()),
                    "is_active": False,
                    "category": "fixture",
                })

    # 3. Check imported GitHub repositories in data/repos
    repos_dir = state.workspace_root / "data" / "repos"
    if repos_dir.is_dir():
        for d in sorted(repos_dir.iterdir()):
            if d.is_dir() and d != state.active_repo_path:
                repos.append({
                    "name": d.name.replace("_", "/"),
                    "path": str(d.resolve()),
                    "is_active": False,
                    "category": "github",
                })

    # 4. Check repositories recorded in database
    try:
        with state.db.connection() as conn:
            db_repos = conn.execute("SELECT * FROM repositories ORDER BY id DESC;").fetchall()
            seen_paths = {r["path"] for r in repos}
            for row in db_repos:
                lp = row["local_path"]
                if lp not in seen_paths and Path(lp).is_dir():
                    repos.append({
                        "name": row["full_name"],
                        "path": lp,
                        "is_active": lp == str(state.active_repo_path),
                        "category": "github",
                    })
                    seen_paths.add(lp)
    except Exception:
        pass

    # 5. Current root workspace
    if state.workspace_root != state.active_repo_path:
        repos.append({
            "name": state.workspace_root.name,
            "path": str(state.workspace_root),
            "is_active": False,
            "category": "workspace",
        })

    return repos


@router.post("/repository/select")
def select_repository(req: RepositorySelectRequest) -> Dict[str, Any]:
    """Select active repository."""
    try:
        return state.select_repo(req.repository_path, reindex=req.reindex)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/repository/tree")
def get_file_tree() -> List[Dict[str, Any]]:
    """Generate recursive file tree for the active repository."""
    inspector = RepoInspector(state.active_repo_path)
    root = state.active_repo_path

    def build_tree(current_dir: Path) -> List[Dict[str, Any]]:
        nodes: List[Dict[str, Any]] = []
        try:
            entries = sorted(list(current_dir.iterdir()), key=lambda p: (not p.is_dir(), p.name.lower()))
        except Exception:
            return []

        for entry in entries:
            # Check ignored directories and files
            if entry.is_dir():
                if should_ignore_dir(entry.name) or entry.name.startswith("."):
                    continue
                children = build_tree(entry)
                nodes.append({
                    "name": entry.name,
                    "path": inspector.to_relative_path(entry),
                    "type": "directory",
                    "children": children,
                })
            elif entry.is_file():
                if should_ignore_file(entry.name) or entry.name.startswith("."):
                    continue
                nodes.append({
                    "name": entry.name,
                    "path": inspector.to_relative_path(entry),
                    "type": "file",
                    "extension": entry.suffix.lstrip(".").lower(),
                    "size": entry.stat().st_size,
                })

        return nodes

    return build_tree(root)


@router.get("/repository/file")
def read_file(
    file_path: str = Query(..., description="Repository-relative file path"),
    start_line: Optional[int] = Query(None, ge=1),
    end_line: Optional[int] = Query(None, ge=1),
) -> Dict[str, Any]:
    """Read file content and return lines with 1-indexed numbers for the code viewer."""
    try:
        res = state.registry.inspector.read_file(
            file_path,
            start_line=start_line,
            end_line=end_line,
        )
        return {
            "file_path": res.file_path,
            "start_line": res.start_line,
            "end_line": res.end_line,
            "total_lines": res.total_lines,
            "content": res.content,
            "lines": [{"line_number": num, "text": text} for num, text in res.lines_with_numbers],
        }
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/chat")
def chat(req: ChatRequest) -> Dict[str, Any]:
    """Conversational AI Copilot endpoint with multi-step tool execution and grounding."""
    try:
        history = [{"role": m.role, "content": m.content} for m in (req.history or [])]
        result = state.orchestrator.run(req.message, conversation_history=history)

        # Record into server state history
        state.conversation_history.append({"role": "user", "content": req.message})
        state.conversation_history.append({"role": "assistant", "content": result.final_answer})

        return result.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/investigate")
def investigate_bug(req: InvestigateRequest) -> Dict[str, Any]:
    """Run comprehensive bug-to-fix workflow."""
    try:
        investigator = BugInvestigator(
            repo_path=state.active_repo_path,
            index_dir=state.index_dir,
            llm_client=state.llm_client,
        )
        report = investigator.investigate(
            query=req.query,
            target_file=req.target_file,
            target_symbol=req.target_symbol,
            run_tests=req.run_tests,
            test_path=req.test_path,
        )

        # Also trigger agent patch generation if defect identified
        agent_result = state.orchestrator.run(req.query)

        data = report.to_dict()
        data["agent_run"] = agent_result.to_dict()
        data["proposed_patch"] = agent_result.proposed_patch
        data["test_results"] = agent_result.test_results
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/patch/apply")
def apply_patch(req: PatchActionRequest) -> Dict[str, Any]:
    """Apply an approved patch to the repository."""
    try:
        success = state.registry.patch_manager.apply_patch(req.patch_id)
        patch = state.registry.patch_manager.get_patch(req.patch_id)
        return {
            "success": success,
            "patch_id": req.patch_id,
            "status": "applied",
            "patch": patch.to_dict() if patch else None,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/patch/reject")
def reject_patch(req: PatchActionRequest) -> Dict[str, Any]:
    """Reject a proposed patch."""
    try:
        success = state.registry.patch_manager.reject_patch(req.patch_id)
        return {"success": success, "patch_id": req.patch_id, "status": "rejected"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/patch/verify")
def verify_patch(req: PatchActionRequest) -> Dict[str, Any]:
    """Run tests in isolation on the proposed patch."""
    try:
        res = state.registry.patch_manager.verify_patch_in_isolation(
            req.patch_id,
            test_path=req.test_path,
        )
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/patch/rollback")
def rollback_patch(req: PatchActionRequest) -> Dict[str, Any]:
    """Rollback an applied patch."""
    try:
        success = state.registry.patch_manager.rollback_patch(req.patch_id)
        return {"success": success, "patch_id": req.patch_id, "status": "reverted"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/patches")
def list_patches() -> List[Dict[str, Any]]:
    """List all staged or applied patches."""
    return [p.to_dict() for p in state.registry.patch_manager.list_patches()]


@router.post("/test/run")
def run_tests_endpoint(req: RunTestRequest) -> Dict[str, Any]:
    """Execute isolated tests directly."""
    try:
        summary = state.registry.test_runner.run_tests(test_path=req.test_path)
        return summary.model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search")
def search_codebase(
    query: str = Query(..., description="Search query"),
    top_k: int = Query(5, ge=1, le=20),
) -> Dict[str, Any]:
    """Hybrid RAG search across indexed codebase."""
    res = state.registry.execute("search_codebase", {"query": query, "top_k": top_k})
    return res.get("result", {})


@router.get("/symbols")
def get_symbols(
    query: Optional[str] = Query(None, description="Symbol name query"),
    file_path: Optional[str] = Query(None, description="Optional target file path"),
) -> Dict[str, Any]:
    """Discover functions and classes in repository."""
    res = state.registry.execute("find_symbols", {"name_query": query, "file_path": file_path})
    return res.get("result", {})


# ---------------------------------------------------------------------------
# Authentication & GitHub OAuth Endpoints
# ---------------------------------------------------------------------------
def _get_current_user(authorization: Optional[str] = Header(None)) -> Optional[Dict[str, Any]]:
    """Helper to extract active user from Authorization: Bearer <token> header."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization[7:].strip()
    return state.auth_service.get_user_from_session(token)


@router.post("/auth/register")
def register_user(req: UserRegisterRequest) -> Dict[str, Any]:
    """Register a new user account with email and password."""
    try:
        user = state.auth_service.register_email_user(
            email=req.email,
            password=req.password,
            name=req.name,
        )
        token = state.auth_service.create_session(user["id"])
        return {
            "status": "authenticated",
            "token": token,
            "user": user,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Registration failed: {e}")


@router.post("/auth/login")
def login_user(req: UserLoginRequest) -> Dict[str, Any]:
    """Authenticate with email and password."""
    user = state.auth_service.authenticate_email(req.email, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    token = state.auth_service.create_session(user["id"])

    # If user has GitHub connected, sync token with GitHubService
    with state.db.connection() as conn:
        row = conn.execute("SELECT github_token FROM users WHERE id = ?;", (user["id"],)).fetchone()
        if row and row["github_token"]:
            state.github_service.set_token(row["github_token"])

    return {
        "status": "authenticated",
        "token": token,
        "user": user,
    }


@router.post("/auth/logout")
def logout_user(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """Invalidate session token."""
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
        state.auth_service.delete_session(token)

    state.github_service.set_token(None)
    return {"status": "logged_out"}


@router.get("/auth/me")
def get_current_user_profile(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """Return profile of the currently authenticated user."""
    user = _get_current_user(authorization)
    if user:
        return {"authenticated": True, "user": user}

    # Fallback to GitHubService standalone token if present
    gh_user = state.github_service.get_authenticated_user()
    if gh_user:
        return {
            "authenticated": True,
            "user": {
                "id": None,
                "email": None,
                "name": gh_user.name,
                "has_password": False,
                "github": {
                    "connected": True,
                    "id": gh_user.id,
                    "login": gh_user.login,
                    "avatar_url": gh_user.avatar_url,
                },
            },
        }

    return {"authenticated": False, "user": None}


@router.get("/auth/github/start")
def start_github_oauth(
    redirect_uri: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """Initiate GitHub OAuth flow with anti-CSRF state token."""
    current_user = _get_current_user(authorization)
    user_id = current_user["id"] if current_user else None

    if not state.auth_service.github_client_id:
        return {
            "configured": False,
            "message": "GitHub OAuth App is not configured on the server. Please set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET, or sign in using a Personal Access Token.",
        }

    try:
        state_token = state.auth_service.create_oauth_state(
            user_id=user_id,
            action="link" if user_id else "login",
            redirect_uri=redirect_uri,
        )
        auth_url = state.auth_service.build_github_oauth_url(state_token, redirect_uri=redirect_uri)
        return {
            "configured": True,
            "authorization_url": auth_url,
            "state": state_token,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/auth/github/callback")
def github_oauth_callback(
    code: Optional[str] = Query(None),
    state_param: Optional[str] = Query(None, alias="state"),
    error: Optional[str] = Query(None),
    error_description: Optional[str] = Query(None),
) -> Any:
    """Handle OAuth callback from GitHub."""
    if error:
        raise HTTPException(status_code=400, detail=f"GitHub authorization denied: {error_description or error}")

    if not code or not state_param:
        raise HTTPException(status_code=400, detail="Missing authorization code or state parameter.")

    # 1. Verify anti-CSRF state
    state_record = state.auth_service.verify_and_consume_oauth_state(state_param)
    if not state_record:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state parameter. Please try signing in again.")

    # 2. Exchange code for access token
    cb_uri = state_record.get("redirect_uri")
    access_token, token_err = state.auth_service.exchange_github_code(code, redirect_uri=cb_uri)
    if not access_token or token_err:
        raise HTTPException(status_code=400, detail=token_err or "Failed to exchange GitHub authorization code.")

    # 3. Fetch profile and verified email
    profile, email, profile_err = state.auth_service.fetch_github_profile_and_email(access_token)
    if not profile or profile_err:
        raise HTTPException(status_code=400, detail=profile_err or "Failed to fetch GitHub profile.")

    # 4. Handle linking vs login
    user_id_to_link = state_record.get("user_id")
    try:
        if user_id_to_link:
            user = state.auth_service.link_github_to_user(user_id_to_link, profile, access_token)
        else:
            user = state.auth_service.login_or_create_github_user(profile, access_token, email=email)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 5. Issue session token and configure GitHub service
    session_token = state.auth_service.create_session(user["id"])
    state.github_service.set_token(access_token)

    # 6. Redirect back to frontend with session token
    redirect_target = f"/?auth_token={session_token}&login_success=true"
    return RedirectResponse(url=redirect_target, status_code=302)


@router.post("/auth/github/link-token")
def link_github_pat(
    req: GitHubLinkTokenRequest,
    authorization: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """Link a GitHub Personal Access Token to current authenticated account."""
    current_user = _get_current_user(authorization)
    token = req.token.strip()
    if not token:
        raise HTTPException(status_code=400, detail="GitHub token cannot be empty.")

    profile, _, err = state.auth_service.fetch_github_profile_and_email(token)
    if not profile or err:
        raise HTTPException(status_code=401, detail=err or "Invalid or expired GitHub token.")

    state.github_service.set_token(token)

    if current_user:
        try:
            updated_user = state.auth_service.link_github_to_user(current_user["id"], profile, token)
            return {
                "status": "linked",
                "user": updated_user,
            }
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    return {
        "status": "authenticated",
        "github": {
            "login": profile.get("login"),
            "avatar_url": profile.get("avatar_url"),
        },
    }


@router.post("/auth/github/disconnect")
def disconnect_github(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """Disconnect GitHub from current authenticated account with lockout safety check."""
    current_user = _get_current_user(authorization)
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required.")

    try:
        updated_user = state.auth_service.disconnect_github_account(current_user["id"])
        state.github_service.set_token(None)
        return {
            "status": "disconnected",
            "user": updated_user,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# GitHub Repository Validation, User Profile & Repos Endpoints
# ---------------------------------------------------------------------------
@router.post("/github/validate-url")
def validate_repository_url(req: URLValidateRequest) -> Dict[str, Any]:
    """Validate and parse a GitHub repository URL or identifier with rich error feedback."""
    try:
        parsed = validate_and_parse_github_url(req.url)
        return {
            "valid": True,
            "owner": parsed.owner,
            "repo": parsed.repo,
            "full_name": parsed.full_name,
            "canonical_url": parsed.canonical_url,
            "clone_url": parsed.clone_url,
        }
    except GitHubUrlValidationError as e:
        return {
            "valid": False,
            "error": e.message,
            "code": e.code,
        }


@router.get("/github/user")
def get_github_user() -> Dict[str, Any]:
    """Check active GitHub authentication status and profile."""
    user = state.github_service.get_authenticated_user()
    return {
        "authenticated": user is not None,
        "user": user.to_dict() if user else None,
    }


@router.post("/github/login")
def github_login(req: GitHubLoginRequest) -> Dict[str, Any]:
    """Authenticate with GitHub using a Personal Access Token or OAuth token."""
    token = req.token.strip()
    if not token:
        raise HTTPException(status_code=400, detail="GitHub token cannot be empty.")

    state.github_service.set_token(token)
    user = state.github_service.get_authenticated_user()
    if not user:
        state.github_service.set_token(None)
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired GitHub token. Ensure the token has 'repo' and 'read:user' scopes.",
        )

    return {
        "status": "authenticated",
        "user": user.to_dict(),
    }


@router.post("/github/logout")
def github_logout() -> Dict[str, Any]:
    """Clear GitHub authentication session."""
    state.github_service.set_token(None)
    return {"status": "logged_out"}


@router.get("/github/repos")
def list_github_user_repos(limit: int = Query(50, ge=1, le=100)) -> Dict[str, Any]:
    """List accessible repositories for the authenticated GitHub user."""
    user = state.github_service.get_authenticated_user()
    if not user:
        raise HTTPException(status_code=401, detail="Please connect your GitHub account first.")

    repos = state.github_service.list_user_repositories(limit=limit)
    return {
        "user": user.login,
        "repositories": [r.to_dict() for r in repos],
    }


@router.post("/github/import")
def import_github_repo(
    req: GitHubImportRequest,
    authorization: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """Clone or download a repository from GitHub, persist in database, and index into RAG."""
    # 1. URL validation
    try:
        parsed_repo = validate_and_parse_github_url(req.repository_url)
    except GitHubUrlValidationError as e:
        raise HTTPException(status_code=400, detail=e.message)

    # 2. Resolve token
    current_user = _get_current_user(authorization)
    token_to_use = req.token or state.github_service.token
    if not token_to_use and current_user:
        with state.db.connection() as conn:
            row = conn.execute("SELECT github_token FROM users WHERE id = ?;", (current_user["id"],)).fetchone()
            if row and row["github_token"]:
                token_to_use = row["github_token"]

    if req.token:
        state.github_service.set_token(req.token)

    # 3. Import repository files
    try:
        dest_path = state.github_service.import_repository(
            identifier=req.repository_url,
            branch=req.branch,
            token=token_to_use,
            force_reclone=req.force_reclone,
        )
    except GitHubUrlValidationError as e:
        raise HTTPException(status_code=400, detail=e.message)
    except Exception as e:
        error_msg = str(e)
        status_code = 400
        if "rate limit" in error_msg.lower():
            status_code = 429
        elif "authentication failed" in error_msg.lower() or "expired" in error_msg.lower():
            status_code = 401
        elif "not found" in error_msg.lower() or "does not exist" in error_msg.lower():
            status_code = 404
        raise HTTPException(status_code=status_code, detail=error_msg)

    # 4. Switch active repository and run RAG indexing
    select_info = state.select_repo(str(dest_path), reindex=req.reindex)

    # 5. Fetch fresh index metadata
    chunks, meta = load_index(state.index_dir)
    total_chunks = len(chunks) if chunks else 0
    total_files = meta.total_files if meta else 0

    # 6. Persist repository record in SQLite database
    from datetime import datetime, timezone
    import uuid

    now = datetime.now(timezone.utc).isoformat()
    repo_id: Optional[int] = None

    try:
        with state.db.connection() as conn:
            existing_repo = conn.execute(
                "SELECT id FROM repositories WHERE local_path = ?;",
                (str(dest_path),),
            ).fetchone()

            if existing_repo:
                repo_id = existing_repo["id"]
                conn.execute(
                    """
                    UPDATE repositories
                    SET total_chunks = ?, total_files = ?, last_indexed_at = ?, branch = ?
                    WHERE id = ?;
                    """,
                    (total_chunks, total_files, now, req.branch or "main", repo_id),
                )
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO repositories (user_id, owner, name, full_name, branch, local_path, total_chunks, total_files, last_indexed_at, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        current_user["id"] if current_user else None,
                        parsed_repo.owner,
                        parsed_repo.repo,
                        parsed_repo.full_name,
                        req.branch or "main",
                        str(dest_path),
                        total_chunks,
                        total_files,
                        now,
                        now,
                    ),
                )
                repo_id = cursor.lastrowid

            # Record indexing job
            job_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO indexing_jobs (id, repo_id, status, progress, total_files, total_chunks, created_at, finished_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (job_id, repo_id, "completed", 1.0, total_files, total_chunks, now, now),
            )
    except Exception as e:
        logger.warning(f"Could not persist repository record to database: {e}")

    return {
        "status": "imported",
        "repository_id": repo_id,
        "repository_name": select_info["repository_name"],
        "repository_path": select_info["repository_path"],
        "owner": parsed_repo.owner,
        "repo": parsed_repo.repo,
        "index": {
            "total_chunks": total_chunks,
            "total_files": total_files,
            "dense_indexed": getattr(meta, "dense_indexed", False) if meta else False,
            "dense_vectors_count": getattr(meta, "dense_vectors_count", 0) if meta else 0,
            "last_indexed_at": meta.last_indexed_at if meta else None,
        },
    }


