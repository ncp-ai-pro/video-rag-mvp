import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from .config import SESSION_MAX_AGE_SECONDS
from .db import connection


ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _new_workspace_code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(8))


def create_guest_workspace():
    with connection() as conn:
        for _ in range(10):
            code = _new_workspace_code()
            try:
                row = conn.execute(
                    "INSERT INTO users(workspace_code) VALUES (?) RETURNING id, workspace_code", (code,)
                ).fetchone()
                return dict(row)
            except Exception as exc:
                if "UNIQUE constraint failed" not in str(exc):
                    raise
    raise RuntimeError("workspace code generation failed")


def find_workspace(code: str):
    normalized = code.strip().upper().replace("-", "")
    with connection() as conn:
        row = conn.execute("SELECT id, workspace_code FROM users WHERE workspace_code=?", (normalized,)).fetchone()
    return dict(row) if row else None


def create_session(user_id: int):
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=SESSION_MAX_AGE_SECONDS)
    with connection() as conn:
        conn.execute(
            "INSERT INTO sessions(user_id, token_hash, expires_at) VALUES (?, ?, ?)",
            (user_id, _token_hash(token), expires_at.strftime("%Y-%m-%d %H:%M:%S")),
        )
    return token


def session_workspace(token: str):
    if not token:
        return None
    with connection() as conn:
        row = conn.execute(
            """
            SELECT users.id, users.workspace_code
            FROM sessions JOIN users ON users.id=sessions.user_id
            WHERE sessions.token_hash=? AND sessions.expires_at > CURRENT_TIMESTAMP
            """,
            (_token_hash(token),),
        ).fetchone()
        if row:
            conn.execute("UPDATE sessions SET last_seen_at=CURRENT_TIMESTAMP WHERE token_hash=?", (_token_hash(token),))
    return dict(row) if row else None
