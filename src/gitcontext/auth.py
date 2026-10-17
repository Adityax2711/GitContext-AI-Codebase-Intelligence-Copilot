"""Authentication, session management, and GitHub OAuth integration service.

Supports:
- Email/password registration and sign-in with salted cryptographic PBKDF2 hashing
- Bearer session token issuance, validation, and expiration
- GitHub OAuth code exchange and state anti-CSRF verification
- Safe GitHub account linking with account-takeover protection
- Disconnect GitHub safeguards preventing user lockout
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from gitcontext.db import DatabaseManager, get_db

logger = logging.getLogger(__name__)

# Password hashing constants
PBKDF2_ITERATIONS = 100_000
SALT_BYTES = 16


def hash_password(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
    """Generate a salted PBKDF2-HMAC-SHA256 password hash."""
    if not salt:
        salt = secrets.token_hex(SALT_BYTES)
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ITERATIONS,
    )
    return derived.hex(), salt


def verify_password(password: str, stored_hash: str, salt: str) -> bool:
    """Verify password against stored salt and hash using constant-time comparison."""
    computed_hash, _ = hash_password(password, salt=salt)
    return secrets.compare_digest(computed_hash, stored_hash)


class AuthService:
    """Core authentication logic for users, sessions, and OAuth."""

    def __init__(self, db: Optional[DatabaseManager] = None) -> None:
        self.db = db or get_db()
        self.github_client_id = os.getenv("GITHUB_CLIENT_ID", "")
        self.github_client_secret = os.getenv("GITHUB_CLIENT_SECRET", "")
        self.github_redirect_uri = os.getenv("GITHUB_REDIRECT_URI", "")

    # -----------------------------------------------------------------------
    # Email Registration & Login
    # -----------------------------------------------------------------------
    def register_email_user(
        self,
        email: str,
        password: str,
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Register a new user with email and password."""
        clean_email = email.strip().lower()
        if not clean_email or "@" not in clean_email:
            raise ValueError("A valid email address is required.")
        if len(password) < 6:
            raise ValueError("Password must be at least 6 characters long.")

        pw_hash, salt = hash_password(password)
        now = datetime.now(timezone.utc).isoformat()

        with self.db.connection() as conn:
            existing = conn.execute("SELECT id FROM users WHERE email = ?;", (clean_email,)).fetchone()
            if existing:
                raise ValueError("An account with this email address already exists. Please sign in instead.")

            cursor = conn.execute(
                """
                INSERT INTO users (email, password_hash, salt, name, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (clean_email, pw_hash, salt, name.strip() if name else None, now, now),
            )
            user_id = cursor.lastrowid

        return self.get_user_by_id(user_id)  # type: ignore

    def authenticate_email(self, email: str, password: str) -> Optional[Dict[str, Any]]:
        """Authenticate user by email and password."""
        clean_email = email.strip().lower()
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE email = ?;",
                (clean_email,),
            ).fetchone()

            if not row or not row["password_hash"] or not row["salt"]:
                return None

            if not verify_password(password, row["password_hash"], row["salt"]):
                return None

            return self._format_user_row(row)

    # -----------------------------------------------------------------------
    # Sessions
    # -----------------------------------------------------------------------
    def create_session(self, user_id: int, ttl_days: int = 14) -> str:
        """Create a secure session token with expiration."""
        token = secrets.token_hex(32)
        now = datetime.now(timezone.utc)
        expires_at = (now + timedelta(days=ttl_days)).isoformat()

        with self.db.connection() as conn:
            conn.execute(
                """
                INSERT INTO sessions (token, user_id, expires_at, created_at)
                VALUES (?, ?, ?, ?);
                """,
                (token, user_id, expires_at, now.isoformat()),
            )
        return token

    def get_user_from_session(self, token: str) -> Optional[Dict[str, Any]]:
        """Validate session token and return user if active."""
        if not token:
            return None

        now = datetime.now(timezone.utc).isoformat()
        with self.db.connection() as conn:
            row = conn.execute(
                """
                SELECT u.* FROM users u
                JOIN sessions s ON u.id = s.user_id
                WHERE s.token = ? AND s.expires_at > ?;
                """,
                (token.strip(), now),
            ).fetchone()

            if not row:
                return None
            return self._format_user_row(row)

    def delete_session(self, token: str) -> bool:
        """Log out / invalidate session."""
        with self.db.connection() as conn:
            cursor = conn.execute("DELETE FROM sessions WHERE token = ?;", (token.strip(),))
            return cursor.rowcount > 0

    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Fetch user by primary key."""
        with self.db.connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?;", (user_id,)).fetchone()
            if not row:
                return None
            return self._format_user_row(row)

    # -----------------------------------------------------------------------
    # GitHub OAuth & Account Linking
    # -----------------------------------------------------------------------
    def create_oauth_state(
        self,
        user_id: Optional[int] = None,
        action: str = "login",
        redirect_uri: Optional[str] = None,
    ) -> str:
        """Generate and record a cryptographically secure anti-CSRF state token."""
        state = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        expires_at = (now + timedelta(minutes=15)).isoformat()

        with self.db.connection() as conn:
            conn.execute(
                """
                INSERT INTO oauth_states (state, user_id, action, redirect_uri, expires_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (state, user_id, action, redirect_uri, expires_at, now.isoformat()),
            )
        return state

    def verify_and_consume_oauth_state(self, state: str) -> Optional[Dict[str, Any]]:
        """Verify state token validity and delete it to prevent replay attacks."""
        if not state:
            return None

        now = datetime.now(timezone.utc).isoformat()
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM oauth_states WHERE state = ? AND expires_at > ?;",
                (state.strip(), now),
            ).fetchone()

            if not row:
                return None

            conn.execute("DELETE FROM oauth_states WHERE state = ?;", (state.strip(),))
            return dict(row)

    def build_github_oauth_url(self, state: str, redirect_uri: Optional[str] = None) -> str:
        """Build the GitHub OAuth authorization URL."""
        if not self.github_client_id:
            raise ValueError(
                "GITHUB_CLIENT_ID environment variable is not configured. Please set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET."
            )

        cb = redirect_uri or self.github_redirect_uri
        params = {
            "client_id": self.github_client_id,
            "scope": "read:user,user:email,repo",
            "state": state,
        }
        if cb:
            params["redirect_uri"] = cb

        return f"https://github.com/login/oauth/authorize?{urllib.parse.urlencode(params)}"

    def exchange_github_code(self, code: str, redirect_uri: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
        """Exchange GitHub OAuth authorization code for an access token."""
        if not self.github_client_id or not self.github_client_secret:
            return None, "GitHub OAuth credentials (GITHUB_CLIENT_ID / GITHUB_CLIENT_SECRET) are not configured on server."

        url = "https://github.com/login/oauth/access_token"
        data = {
            "client_id": self.github_client_id,
            "client_secret": self.github_client_secret,
            "code": code,
        }
        if redirect_uri:
            data["redirect_uri"] = redirect_uri

        req = urllib.request.Request(
            url,
            data=urllib.parse.urlencode(data).encode("utf-8"),
            headers={
                "Accept": "application/json",
                "User-Agent": "GitContext-AI-Copilot",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                token = res_data.get("access_token")
                if token:
                    return token, None
                err_msg = res_data.get("error_description") or res_data.get("error") or "Failed to obtain access token."
                return None, err_msg
        except Exception as e:
            return None, f"OAuth exchange network error: {e}"

    def fetch_github_profile_and_email(self, token: str) -> Tuple[Optional[Dict[str, Any]], Optional[str], Optional[str]]:
        """Fetch user profile and primary verified email using a GitHub token.

        Returns (profile_dict, primary_email, error_message).
        """
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "GitContext-AI-Copilot",
        }

        # Fetch profile
        user_req = urllib.request.Request("https://api.github.com/user", headers=headers)
        try:
            with urllib.request.urlopen(user_req, timeout=12) as resp:
                profile = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 401:
                return None, None, "Invalid or expired GitHub token."
            return None, None, f"GitHub API error: {e.code} {e.reason}"
        except Exception as e:
            return None, None, f"Network error connecting to GitHub: {e}"

        # Fetch verified primary email
        primary_email = profile.get("email")
        if not primary_email:
            try:
                email_req = urllib.request.Request("https://api.github.com/user/emails", headers=headers)
                with urllib.request.urlopen(email_req, timeout=10) as resp:
                    emails = json.loads(resp.read().decode("utf-8"))
                    for em in emails:
                        if em.get("primary") and em.get("verified"):
                            primary_email = em.get("email")
                            break
                    if not primary_email and emails:
                        primary_email = emails[0].get("email")
            except Exception:
                pass

        return profile, primary_email, None

    def login_or_create_github_user(
        self,
        github_profile: Dict[str, Any],
        token: str,
        email: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Authenticate or register a user through GitHub OAuth."""
        github_id = int(github_profile["id"])
        github_login = github_profile.get("login", "")
        avatar_url = github_profile.get("avatar_url", "")
        name = github_profile.get("name") or github_login
        now = datetime.now(timezone.utc).isoformat()

        with self.db.connection() as conn:
            # 1. Existing user with this github_id
            row = conn.execute("SELECT * FROM users WHERE github_id = ?;", (github_id,)).fetchone()
            if row:
                conn.execute(
                    """
                    UPDATE users
                    SET github_login = ?, github_avatar = ?, github_token = ?, updated_at = ?
                    WHERE id = ?;
                    """,
                    (github_login, avatar_url, token, now, row["id"]),
                )
                return self.get_user_by_id(row["id"])  # type: ignore

            # 2. If email provided, check if existing email account can be linked safely
            if email:
                row_email = conn.execute("SELECT * FROM users WHERE email = ?;", (email.lower(),)).fetchone()
                if row_email:
                    # Link account if not already linked to another github
                    if row_email["github_id"] is not None and row_email["github_id"] != github_id:
                        raise ValueError(
                            "This email is already associated with a different GitHub account. Please sign in with your email first."
                        )
                    conn.execute(
                        """
                        UPDATE users
                        SET github_id = ?, github_login = ?, github_avatar = ?, github_token = ?, updated_at = ?
                        WHERE id = ?;
                        """,
                        (github_id, github_login, avatar_url, token, now, row_email["id"]),
                    )
                    return self.get_user_by_id(row_email["id"])  # type: ignore

            # 3. Create fresh user
            cursor = conn.execute(
                """
                INSERT INTO users (email, name, github_id, github_login, github_avatar, github_token, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    email.lower() if email else None,
                    name,
                    github_id,
                    github_login,
                    avatar_url,
                    token,
                    now,
                    now,
                ),
            )
            return self.get_user_by_id(cursor.lastrowid)  # type: ignore

    def link_github_to_user(
        self,
        user_id: int,
        github_profile: Dict[str, Any],
        token: str,
    ) -> Dict[str, Any]:
        """Link a GitHub identity to an already signed-in user, preventing duplicate account takeover."""
        github_id = int(github_profile["id"])
        github_login = github_profile.get("login", "")
        avatar_url = github_profile.get("avatar_url", "")
        now = datetime.now(timezone.utc).isoformat()

        with self.db.connection() as conn:
            # Check if this GitHub ID is already claimed by someone else
            existing_holder = conn.execute(
                "SELECT id, email FROM users WHERE github_id = ? AND id != ?;",
                (github_id, user_id),
            ).fetchone()

            if existing_holder:
                raise ValueError(
                    f"This GitHub account (@{github_login}) is already linked to another user account. "
                    "Disconnect it from that account first or sign in using that account."
                )

            conn.execute(
                """
                UPDATE users
                SET github_id = ?, github_login = ?, github_avatar = ?, github_token = ?, updated_at = ?
                WHERE id = ?;
                """,
                (github_id, github_login, avatar_url, token, now, user_id),
            )

        return self.get_user_by_id(user_id)  # type: ignore

    def disconnect_github_account(self, user_id: int) -> Dict[str, Any]:
        """Disconnect GitHub from user account, safeguarding against lockout."""
        with self.db.connection() as conn:
            user = conn.execute("SELECT * FROM users WHERE id = ?;", (user_id,)).fetchone()
            if not user:
                raise ValueError("User not found.")

            # Safety check: does the user have email/password to sign back in?
            if not user["email"] or not user["password_hash"]:
                raise ValueError(
                    "Cannot disconnect GitHub because you do not have an email and password set. "
                    "Set an email and password first to prevent being locked out of your account."
                )

            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """
                UPDATE users
                SET github_id = NULL, github_login = NULL, github_avatar = NULL, github_token = NULL, updated_at = ?
                WHERE id = ?;
                """,
                (now, user_id),
            )

        return self.get_user_by_id(user_id)  # type: ignore

    # -----------------------------------------------------------------------
    # Formatting
    # -----------------------------------------------------------------------
    def _format_user_row(self, row: Any) -> Dict[str, Any]:
        """Format database row into a safe, client-facing dictionary (no password hashes or salts)."""
        has_github = bool(row["github_id"] and row["github_token"])
        return {
            "id": row["id"],
            "email": row["email"],
            "name": row["name"],
            "has_password": bool(row["password_hash"]),
            "github": {
                "connected": has_github,
                "id": row["github_id"],
                "login": row["github_login"],
                "avatar_url": row["github_avatar"],
            }
            if has_github
            else {
                "connected": False,
                "id": None,
                "login": None,
                "avatar_url": None,
            },
            "created_at": row["created_at"],
        }
