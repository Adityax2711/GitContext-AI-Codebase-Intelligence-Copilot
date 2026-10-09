"""Authentication module for SynthStore."""

import hashlib
import secrets
from typing import Optional


def hash_user_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
    """Generate a cryptographic SHA-256 password hash with salt."""
    if salt is None:
        salt = secrets.token_hex(16)
    hashed = hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()
    return hashed, salt


def verify_user_credentials(provided_password: str, stored_hash: str, salt: str) -> bool:
    """Validate user credentials against stored salt and hash."""
    computed_hash, _ = hash_user_password(provided_password, salt=salt)
    return secrets.compare_digest(computed_hash, stored_hash)


class UserSessionManager:
    """Manages active user session tokens and lifecycle."""

    def __init__(self, token_expiry_seconds: int = 3600):
        self.expiry = token_expiry_seconds
        self.active_sessions: dict[str, str] = {}

    def create_session(self, user_id: str) -> str:
        """Issue a new secure session token for a user ID."""
        session_token = secrets.token_urlsafe(32)
        self.active_sessions[session_token] = user_id
        return session_token

    def validate_session(self, token: str) -> Optional[str]:
        """Return the associated user ID if token is valid."""
        return self.active_sessions.get(token)
