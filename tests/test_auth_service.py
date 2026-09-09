"""Local account security and real SQLite persistence (no external services)."""
import sqlite3

from argon2 import PasswordHasher
import pytest

from auth.service import (
    ATTEMPT_WINDOW_SECONDS,
    AuthStore,
    SESSION_IDLE_SECONDS,
    SESSION_LIFETIME_SECONDS,
)
from rag.config import UserFacingError


PASSWORD = "Correct horse battery staple 2026!"
NEW_PASSWORD = "New independent passphrase 2026!"


@pytest.fixture
def account(tmp_path):
    now = [1_700_000_000.0]
    store = AuthStore(tmp_path / "accounts.sqlite3", clock=lambda: now[0])
    registration = store.register("Researcher", "Researcher One", PASSWORD)
    return store, now, registration


def read_rows(store, table):
    with sqlite3.connect(store.path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(f"SELECT * FROM {table}").fetchall()
    connection.close()
    return rows


def test_real_password_hash_login_and_public_user(account):
    store, _, registration = account
    token = store.login("  RESEARCHER  ", PASSWORD)
    assert store.get_session(token) == registration["user"]
    assert set(registration["user"]) == {"id", "username", "display_name"}
    encoded = read_rows(store, "accounts")[0]["password_hash"]
    assert encoded.startswith("$argon2id$v=19$m=65536,t=3,p=4$")
    assert PasswordHasher().verify(encoded, PASSWORD)


def test_wrong_and_unknown_credentials_have_same_error(account):
    store, _, _ = account
    errors = []
    for username in ("researcher", "unknown_account", "x' OR 1=1 --"):
        with pytest.raises(UserFacingError) as caught:
            store.login(username, "incorrect password")
        errors.append(str(caught.value))
    assert len(set(errors)) == 1
    assert store.get_session(store.login("researcher", PASSWORD))


def test_case_insensitive_duplicate_does_not_replace_account(account):
    store, _, registration = account
    with pytest.raises(UserFacingError, match="already uses"):
        store.register("RESEARCHER", "Different Person", NEW_PASSWORD)
    assert store.get_session(store.login("researcher", PASSWORD)) == registration["user"]


@pytest.mark.parametrize("username", ["ab", "a" * 33, "first name", "café", "' OR 1=1 --", "ＡＢＣ", None])
def test_registration_rejects_invalid_usernames(tmp_path, username):
    store = AuthStore(tmp_path / "accounts.sqlite3")
    with pytest.raises(UserFacingError, match="username"):
        store.register(username, "Name", PASSWORD)


@pytest.mark.parametrize("password", ["short", "x" * 129, " " * 12, None])
def test_registration_enforces_password_policy(tmp_path, password):
    store = AuthStore(tmp_path / "accounts.sqlite3")
    with pytest.raises(UserFacingError, match="password"):
        store.register("researcher", "Name", password)


@pytest.mark.parametrize("name", ["", " " * 5, "x" * 81, "New\nName", "Name\x00", "Name\u202e"])
def test_registration_rejects_invalid_display_names(tmp_path, name):
    with pytest.raises(UserFacingError, match="display name"):
        AuthStore(tmp_path / "accounts.sqlite3").register("researcher", name, PASSWORD)


def test_sql_like_display_name_is_stored_as_plain_data(account):
    store, _, _ = account
    name = "Robert'); DROP TABLE accounts; --"
    result = store.register("sql_test", name, PASSWORD)
    assert store.get_session(store.login("sql_test", PASSWORD)) == result["user"]
    assert store.get_session(store.login("researcher", PASSWORD))


def test_logout_revokes_only_selected_session(account):
    store, _, _ = account
    first = store.login("researcher", PASSWORD)
    second = store.login("researcher", PASSWORD)
    store.logout(first)
    assert store.get_session(first) is None
    assert store.get_session(second)
    store.logout(first)
    store.logout(None)
    assert store.get_session(None) is None
    assert store.get_session("invented-session-token") is None


def test_idle_expiry_and_last_seen_refresh(account):
    store, now, _ = account
    token = store.login("researcher", PASSWORD)
    now[0] += SESSION_IDLE_SECONDS - 1
    assert store.get_session(token)
    now[0] += SESSION_IDLE_SECONDS
    assert store.get_session(token) is None
    assert not read_rows(store, "sessions")


def test_absolute_expiry_despite_activity(account):
    store, now, _ = account
    start = now[0]
    token = store.login("researcher", PASSWORD)
    for offset in range(1800, SESSION_LIFETIME_SECONDS, 1800):
        now[0] = start + offset
        assert store.get_session(token)
    now[0] = start + SESSION_LIFETIME_SECONDS
    assert store.get_session(token) is None


def test_password_change_checks_current_password_and_revokes_all_sessions(account):
    store, _, _ = account
    first = store.login("researcher", PASSWORD)
    second = store.login("researcher", PASSWORD)
    with pytest.raises(UserFacingError, match="current password"):
        store.change_password(first, "incorrect password", NEW_PASSWORD)
    assert store.get_session(first)
    store.change_password(first, PASSWORD, NEW_PASSWORD)
    assert store.get_session(first) is None
    assert store.get_session(second) is None
    with pytest.raises(UserFacingError, match="incorrect"):
        store.login("researcher", PASSWORD)
    assert store.get_session(store.login("researcher", NEW_PASSWORD))


def test_expired_session_cannot_change_password(account):
    store, now, _ = account
    token = store.login("researcher", PASSWORD)
    now[0] += SESSION_IDLE_SECONDS
    with pytest.raises(UserFacingError, match="expired"):
        store.change_password(token, PASSWORD, NEW_PASSWORD)
    assert store.get_session(token) is None


def test_recovery_rotates_code_revokes_sessions_and_changes_password(account):
    store, _, registration = account
    first = store.login("researcher", PASSWORD)
    second = store.login("researcher", PASSWORD)
    old_code = registration["recovery_code"]
    new_code = store.recover("RESEARCHER", old_code, NEW_PASSWORD)
    assert new_code != old_code
    assert store.get_session(first) is None
    assert store.get_session(second) is None
    with pytest.raises(UserFacingError, match="incorrect"):
        store.login("researcher", PASSWORD)
    assert store.get_session(store.login("researcher", NEW_PASSWORD))
    with pytest.raises(UserFacingError, match="recovery code"):
        store.recover("researcher", old_code, PASSWORD)
    newest_code = store.recover("researcher", new_code, PASSWORD)
    assert newest_code != new_code
    assert store.get_session(store.login("researcher", PASSWORD))


def test_recovery_wrong_and_unknown_have_same_error(account):
    store, _, _ = account
    messages = []
    for username in ("researcher", "unknown_account"):
        with pytest.raises(UserFacingError) as caught:
            store.recover(username, "incorrect-code", NEW_PASSWORD)
        messages.append(str(caught.value))
    assert messages[0] == messages[1]


@pytest.mark.parametrize("operation", ["login", "recovery"])
@pytest.mark.parametrize("username", ["researcher", "unknown_account"])
def test_throttle_survives_store_recreation_and_blocked_attempts_do_not_extend_it(account, operation, username):
    store, now, _ = account

    def fail():
        recreated = AuthStore(store.path, clock=lambda: now[0])
        if operation == "login":
            recreated.login(username.upper(), "incorrect-password")
        else:
            recreated.recover(username.upper(), "incorrect-code", NEW_PASSWORD)

    for _ in range(5):
        with pytest.raises(UserFacingError, match="incorrect"):
            fail()
    for _ in range(2):
        now[0] += ATTEMPT_WINDOW_SECONDS / 3
        with pytest.raises(UserFacingError, match="Too many attempts"):
            fail()
    now[0] += ATTEMPT_WINDOW_SECONDS / 3
    with pytest.raises(UserFacingError, match="incorrect"):
        fail()


def test_successful_login_clears_failed_attempts(account):
    store, _, _ = account
    for _ in range(4):
        with pytest.raises(UserFacingError):
            store.login("researcher", "incorrect-password")
    assert store.login("researcher", PASSWORD)
    for _ in range(4):
        with pytest.raises(UserFacingError, match="incorrect"):
            store.login("researcher", "incorrect-password")
    assert store.login("researcher", PASSWORD)


def test_malformed_stored_password_hash_fails_safely(account):
    store, _, _ = account
    with sqlite3.connect(store.path) as connection:
        connection.execute("UPDATE accounts SET password_hash = ?", ("not-a-password-hash",))
    connection.close()
    with pytest.raises(UserFacingError, match="username or password"):
        store.login("researcher", PASSWORD)


@pytest.mark.parametrize("malformed", ["not-a-recovery-hash", "\u202e", b"bad-binary-hash"])
def test_malformed_stored_recovery_hash_fails_safely(account, malformed):
    store, _, registration = account
    with sqlite3.connect(store.path) as connection:
        connection.execute("UPDATE accounts SET recovery_hash = ?", (malformed,))
    connection.close()
    with pytest.raises(UserFacingError, match="username or recovery code"):
        store.recover("researcher", registration["recovery_code"], NEW_PASSWORD)


def test_password_change_attempts_are_throttled(account):
    store, _, _ = account
    token = store.login("researcher", PASSWORD)
    for _ in range(5):
        with pytest.raises(UserFacingError, match="current password"):
            store.change_password(token, "incorrect-password", NEW_PASSWORD)
    with pytest.raises(UserFacingError, match="Too many attempts"):
        AuthStore(store.path, clock=store.clock).change_password(token, PASSWORD, NEW_PASSWORD)


def test_invalid_password_does_not_consume_recovery_code(account):
    store, _, registration = account
    with pytest.raises(UserFacingError, match="password"):
        store.recover("researcher", registration["recovery_code"], "short")
    assert store.recover("researcher", registration["recovery_code"], NEW_PASSWORD)


def test_database_contains_no_plaintext_password_recovery_or_session_secrets(account):
    store, _, registration = account
    token = store.login("researcher", PASSWORD)
    binary = store.path.read_bytes()
    for secret in (PASSWORD, registration["recovery_code"], token):
        assert secret.encode("utf-8") not in binary
    assert read_rows(store, "sessions")[0]["token_hash"] != token
    assert read_rows(store, "accounts")[0]["recovery_hash"] != registration["recovery_code"]


def test_storage_errors_do_not_expose_sql_or_paths(tmp_path):
    path = tmp_path / "private-database-location.sqlite3"
    path.write_bytes(b"not a sqlite database")
    with pytest.raises(UserFacingError) as caught:
        AuthStore(path)
    assert "storage is unavailable" in str(caught.value)
    assert str(path) not in str(caught.value)
    assert "CREATE TABLE" not in str(caught.value)
