"""Local, single-host accounts backed by SQLite.

Use an OIDC identity provider for public hosting. This service deliberately does
not implement email verification, email recovery, or browser cookie management.
Passwords use Argon2id; only digests of random recovery/session secrets are saved.
"""
from contextlib import contextmanager
from functools import lru_cache
import hashlib
import hmac
from pathlib import Path
import re
import secrets
import sqlite3
import time
import unicodedata
import uuid

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError

from rag.config import ROOT, UserFacingError


SESSION_LIFETIME_SECONDS = 12 * 60 * 60
SESSION_IDLE_SECONDS = 60 * 60
ATTEMPT_WINDOW_SECONDS = 15 * 60
MAX_FAILURES = 5
_USERNAME = re.compile(r"[a-z0-9_.-]{3,32}", re.ASCII)
_HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4,
                         hash_len=32, salt_len=16, type=Type.ID)
_INVALID_LOGIN = "The username or password is incorrect."
_INVALID_RECOVERY = "The username or recovery code is incorrect."
_UNAVAILABLE = "Account storage is unavailable. Please contact the app administrator."


def _digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _username(value):
    return value.strip().lower() if isinstance(value, str) else ""


def _password(value):
    if not isinstance(value, str) or not 12 <= len(value) <= 128:
        raise UserFacingError("Use a password containing between 12 and 128 characters.")
    if not value.strip():
        raise UserFacingError("Your password cannot contain only spaces.")
    return value


def _display_name(value):
    value = value.strip() if isinstance(value, str) else ""
    if not 1 <= len(value) <= 80 or any(unicodedata.category(c).startswith("C") for c in value):
        raise UserFacingError("Enter a display name of 1 to 80 characters without control characters.")
    return value


@lru_cache(maxsize=1)
def _dummy_hash():
    # Unknown accounts still perform a real password verification.
    return _HASHER.hash(secrets.token_urlsafe(32))


def _verify(encoded, password):
    try:
        return _HASHER.verify(encoded, password)
    except (VerificationError, InvalidHashError, TypeError, ValueError):
        return False


def _user(row):
    return {"id": row["id"], "username": row["username"], "display_name": row["display_name"]}


class AuthStore:
    """Store local accounts; every operation closes its database connection.

    ``clock`` is a callable returning Unix seconds, injectable for expiry tests.
    Use the same absolute database path across Streamlit sessions and restarts.
    """

    def __init__(self, path=None, *, clock=None):
        self.path = Path(path) if path is not None else ROOT / "data" / "auth.sqlite3"
        self.clock = clock if clock is not None else time.time
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with self._transaction() as connection:
                connection.execute("""CREATE TABLE IF NOT EXISTS accounts (
                    id TEXT PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    recovery_hash TEXT NOT NULL,
                    created_at REAL NOT NULL
                )""")
                connection.execute("""CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    last_seen REAL NOT NULL
                )""")
                connection.execute("CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id)")
                connection.execute("""CREATE TABLE IF NOT EXISTS attempts (
                    bucket TEXT NOT NULL,
                    purpose TEXT NOT NULL,
                    started_at REAL NOT NULL,
                    failures INTEGER NOT NULL,
                    PRIMARY KEY (bucket, purpose)
                )""")
            self.path.chmod(0o600)
        except OSError:
            raise UserFacingError(_UNAVAILABLE) from None

    @contextmanager
    def _transaction(self):
        connection = None
        try:
            connection = sqlite3.connect(self.path, timeout=15, isolation_level=None)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except sqlite3.Error:
            if connection is not None:
                connection.rollback()
            raise UserFacingError(_UNAVAILABLE) from None
        except BaseException:
            if connection is not None:
                connection.rollback()
            raise
        finally:
            if connection is not None:
                connection.close()

    def register(self, username, display_name, password):
        username = _username(username)
        if not _USERNAME.fullmatch(username):
            raise UserFacingError("Use 3 to 32 letters, numbers, dots, underscores, or hyphens for your username.")
        display_name = _display_name(display_name)
        password = _password(password)
        encoded = _HASHER.hash(password)
        recovery_code = secrets.token_urlsafe(32)
        user = {"id": uuid.uuid4().hex, "username": username, "display_name": display_name}
        with self._transaction() as connection:
            # This check and insertion share a write transaction, including races.
            if connection.execute("SELECT 1 FROM accounts WHERE username = ?", (username,)).fetchone():
                raise UserFacingError("An account already uses that username. Choose another or sign in.")
            connection.execute(
                "INSERT INTO accounts VALUES (?, ?, ?, ?, ?, ?)",
                (user["id"], username, display_name, encoded, _digest(recovery_code), self.clock()),
            )
        return {"user": user, "recovery_code": recovery_code}

    def _check_attempts(self, connection, bucket, purpose, now):
        attempt = connection.execute(
            "SELECT started_at, failures FROM attempts WHERE bucket = ? AND purpose = ?",
            (bucket, purpose),
        ).fetchone()
        if attempt and now - attempt["started_at"] < ATTEMPT_WINDOW_SECONDS:
            if attempt["failures"] >= MAX_FAILURES:
                raise UserFacingError("Too many attempts. Please try again in 15 minutes.")
        else:
            connection.execute("DELETE FROM attempts WHERE bucket = ? AND purpose = ?", (bucket, purpose))

    def _record_failure(self, connection, bucket, purpose, now):
        connection.execute("""INSERT INTO attempts(bucket, purpose, started_at, failures)
            VALUES (?, ?, ?, 1) ON CONFLICT(bucket, purpose)
            DO UPDATE SET failures = failures + 1""", (bucket, purpose, now))

    def login(self, username, password):
        username = _username(username)
        bucket = _digest(username)
        now = self.clock()
        token = None
        with self._transaction() as connection:
            self._check_attempts(connection, bucket, "login", now)
            row = connection.execute("SELECT * FROM accounts WHERE username = ?", (username,)).fetchone()
            candidate = password if isinstance(password, str) and len(password) <= 128 else ""
            valid = _verify(row["password_hash"] if row else _dummy_hash(), candidate)
            if row is None or not valid:
                self._record_failure(connection, bucket, "login", now)
            else:
                if _HASHER.check_needs_rehash(row["password_hash"]):
                    connection.execute("UPDATE accounts SET password_hash = ? WHERE id = ?",
                                       (_HASHER.hash(candidate), row["id"]))
                connection.execute("DELETE FROM attempts WHERE bucket = ? AND purpose = 'login'", (bucket,))
                connection.execute("DELETE FROM sessions WHERE expires_at <= ? OR last_seen <= ?",
                                   (now, now - SESSION_IDLE_SECONDS))
                token = secrets.token_urlsafe(48)
                connection.execute("INSERT INTO sessions VALUES (?, ?, ?, ?, ?)",
                                   (_digest(token), row["id"], now, now + SESSION_LIFETIME_SECONDS, now))
        # Commit failures before raising; a UI rerun must not reset throttling.
        if token is None:
            raise UserFacingError(_INVALID_LOGIN)
        return token

    def _session(self, connection, token, now, *, touch=True):
        if not isinstance(token, str) or not 16 <= len(token) <= 256:
            return None
        token_hash = _digest(token)
        row = connection.execute("""SELECT accounts.*, sessions.expires_at, sessions.last_seen
            FROM sessions JOIN accounts ON accounts.id = sessions.user_id
            WHERE sessions.token_hash = ?""", (token_hash,)).fetchone()
        if row is None:
            return None
        if row["expires_at"] <= now or row["last_seen"] + SESSION_IDLE_SECONDS <= now:
            connection.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
            return None
        if touch:
            connection.execute("UPDATE sessions SET last_seen = ? WHERE token_hash = ?", (now, token_hash))
        return row

    def get_session(self, token):
        with self._transaction() as connection:
            row = self._session(connection, token, self.clock())
            return _user(row) if row else None

    def logout(self, token):
        if isinstance(token, str) and len(token) <= 256:
            with self._transaction() as connection:
                connection.execute("DELETE FROM sessions WHERE token_hash = ?", (_digest(token),))

    def change_password(self, token, old, new):
        new = _password(new)
        error = None
        now = self.clock()
        with self._transaction() as connection:
            row = self._session(connection, token, now)
            if row is None:
                error = "Your session has expired. Please sign in again."
            else:
                bucket = _digest(row["username"])
                self._check_attempts(connection, bucket, "change_password", now)
                candidate = old if isinstance(old, str) and len(old) <= 128 else ""
                if not _verify(row["password_hash"], candidate):
                    self._record_failure(connection, bucket, "change_password", now)
                    error = "The current password is incorrect."
                else:
                    connection.execute("UPDATE accounts SET password_hash = ? WHERE id = ?",
                                       (_HASHER.hash(new), row["id"]))
                    connection.execute("DELETE FROM sessions WHERE user_id = ?", (row["id"],))
                    connection.execute("DELETE FROM attempts WHERE bucket = ?", (bucket,))
        if error:
            raise UserFacingError(error)

    def recover(self, username, recovery_code, new_password):
        username = _username(username)
        new_password = _password(new_password)
        bucket = _digest(username)
        now = self.clock()
        new_code = None
        with self._transaction() as connection:
            self._check_attempts(connection, bucket, "recovery", now)
            row = connection.execute("SELECT * FROM accounts WHERE username = ?", (username,)).fetchone()
            candidate = recovery_code.strip() if isinstance(recovery_code, str) and len(recovery_code) <= 256 else ""
            expected = row["recovery_hash"] if row else _digest("unknown-account")
            valid = isinstance(expected, str) and hmac.compare_digest(expected.encode("utf-8"), _digest(candidate).encode("ascii"))
            if row is None or not valid:
                self._record_failure(connection, bucket, "recovery", now)
            else:
                new_code = secrets.token_urlsafe(32)
                connection.execute("UPDATE accounts SET password_hash = ?, recovery_hash = ? WHERE id = ?",
                                   (_HASHER.hash(new_password), _digest(new_code), row["id"]))
                connection.execute("DELETE FROM sessions WHERE user_id = ?", (row["id"],))
                connection.execute("DELETE FROM attempts WHERE bucket = ?", (bucket,))
        if new_code is None:
            raise UserFacingError(_INVALID_RECOVERY)
        return new_code
