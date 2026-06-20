"""Authentication utilities — argon2 password hashing, session helpers, FastAPI dependency.

The web UI uses cookie-based sessions signed by Starlette's
:class:`~starlette.middleware.sessions.SessionMiddleware`. The session payload
is intentionally minimal — once the user is logged in we just store an
``"auth": True`` flag. There is only one user (the admin), so we don't need
user IDs, roles, or session storage on the server side.

Inbound webhook auth (bearer token for ``POST /api/keys/{id}/state``) lives
separately in M7 alongside that route.
"""

from __future__ import annotations

import contextlib
import secrets
from typing import TYPE_CHECKING

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import HTTPException, Request, WebSocket, status

if TYPE_CHECKING:
    from pathlib import Path

    from deckbridge.storage import Storage

# Single shared hasher; argon2 parameters are reasonable defaults from the
# argon2-cffi maintainers (RFC 9106 second-recommended profile).
_HASHER = PasswordHasher()

SESSION_KEY_AUTHENTICATED = "auth"
"""Key in the Starlette session dict that flags an authenticated user."""


# ---- password hashing ----------------------------------------------------


def hash_password(password: str) -> str:
    """Return an argon2 hash string suitable for storing in Preferences.password_hash."""
    if not password:
        raise ValueError("password must not be empty")
    return _HASHER.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Constant-time check of *password* against an argon2 *password_hash*."""
    try:
        _HASHER.verify(password_hash, password)
        return True
    except VerifyMismatchError:
        return False


# ---- setup wizard ---------------------------------------------------------


def is_setup_needed(storage: Storage) -> bool:
    """True when no admin password has been configured yet."""
    return storage.get_preferences().password_hash is None


# ---- session helpers ------------------------------------------------------


def login_session(request: Request) -> None:
    """Mark the current session as authenticated. Persists via the signed cookie."""
    request.session[SESSION_KEY_AUTHENTICATED] = True


def logout_session(request: Request) -> None:
    """Clear the authentication flag from the session."""
    request.session.pop(SESSION_KEY_AUTHENTICATED, None)


def is_authenticated(request: Request | WebSocket) -> bool:
    """True when the current request/WebSocket carries an authenticated session."""
    try:
        return bool(request.session.get(SESSION_KEY_AUTHENTICATED))
    except (AssertionError, AttributeError):
        # SessionMiddleware not installed — treat as unauthenticated.
        return False


# ---- FastAPI dependency ---------------------------------------------------


def require_auth(request: Request) -> None:
    """FastAPI dependency that 401s when the request is not authenticated.

    Usage::

        @router.get("/protected", dependencies=[Depends(require_auth)])
        def protected(...): ...
    """
    if not is_authenticated(request):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )


# ---- session secret bootstrap --------------------------------------------


def get_or_create_session_secret(data_dir: Path) -> str:
    """Return the persistent session-signing secret, creating one if absent.

    The secret lives under ``data_dir/secrets/session.key`` so it survives
    restarts (otherwise every restart would invalidate every session). On
    POSIX the file is mode 0600; on Windows the chmod is best-effort and the
    file inherits parent ACLs (the install script narrows those further).
    """
    secret_dir = data_dir / "secrets"
    secret_dir.mkdir(parents=True, exist_ok=True)
    secret_path = secret_dir / "session.key"
    if secret_path.is_file():
        existing = secret_path.read_text(encoding="utf-8").strip()
        if existing:
            return existing

    new_secret = secrets.token_urlsafe(48)
    secret_path.write_text(new_secret, encoding="utf-8")
    # Windows: chmod is largely a no-op; ACLs are managed elsewhere.
    with contextlib.suppress(PermissionError, NotImplementedError):
        secret_path.chmod(0o600)
    return new_secret
