"""Exercise the actual authentication gate and account forms without network."""
from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest
from auth import ui
from auth.service import AuthStore

APP = str(Path(__file__).resolve().parents[1] / "app.py")
PASSWORD = "a long test password!"

@pytest.fixture
def store(monkeypatch, tmp_path):
    store = AuthStore(tmp_path / "accounts.sqlite3")
    monkeypatch.setattr(ui, "_store", lambda: store)
    monkeypatch.setattr(ui, "_mode", lambda: "local")
    monkeypatch.setenv("CORTEX_ALLOW_REGISTRATION", "true")
    return store

def button(at, label):
    return next(b for b in at.button if b.label == label)

def fill(at, label, value):
    next(w for w in at.text_input if w.label == label).set_value(value)

def test_anonymous_users_cannot_reach_workspace(store):
    at = AppTest.from_file(APP).run()
    assert not at.exception
    assert at.title[0].value == "Cortex Research AI"
    assert not any(b.label == "Process documents" for b in at.button)
    assert len(at.chat_input) == 0
    assert len(at.get("file_uploader")) == 0

def test_signup_signin_logout_forms_clear_private_state(store):
    at = AppTest.from_file(APP).run()
    fill(at, "Display name", "Ada Researcher")
    fill(at, "Choose a username", "ada")
    fill(at, "Choose a password", PASSWORD)
    fill(at, "Confirm password", PASSWORD)
    button(at, "Create account").click().run()
    assert not at.exception
    code = at.session_state["_auth_recovery"]
    assert len(code) >= 32
    button(at, "I saved my recovery code").click().run()
    fill(at, "Username", "ada")
    fill(at, "Password", PASSWORD)
    button(at, "Sign in").click().run()
    assert not at.exception
    assert any(b.label == "Process documents" for b in at.button)
    token = at.session_state["_auth_token"]
    at.session_state["private_test_value"] = "PRIVATE_CONTENT"
    button(at, "Sign out").click().run()
    assert not at.exception
    assert store.get_session(token) is None
    assert "private_test_value" not in at.session_state
    assert not any(b.label == "Process documents" for b in at.button)

def test_wrong_password_stays_on_login(store):
    store.register("alice", "Alice", PASSWORD)
    at = AppTest.from_file(APP).run()
    fill(at, "Username", "alice")
    fill(at, "Password", "wrong password")
    button(at, "Sign in").click().run()
    assert at.error
    assert not at.exception
    assert not any(b.label == "Process documents" for b in at.button)

def test_password_change_and_recovery_forms(store):
    created = store.register("alice", "Alice", PASSWORD)
    at = AppTest.from_file(APP)
    at.session_state["_auth_token"] = store.login("alice", PASSWORD)
    at.run()
    fill(at, "Current password", PASSWORD)
    fill(at, "New account password", "changed secure password")
    fill(at, "Confirm account password", "changed secure password")
    button(at, "Change password").click().run()
    assert not at.exception
    assert not any(b.label == "Process documents" for b in at.button)
    fill(at, "Account username", "alice")
    fill(at, "Recovery code", created["recovery_code"])
    fill(at, "New password", "recovered secure password")
    fill(at, "Confirm new password", "recovered secure password")
    button(at, "Reset password").click().run()
    assert not at.exception
    assert at.session_state["_auth_recovery"] != created["recovery_code"]
    assert store.get_session(store.login("alice", "recovered secure password"))["username"] == "alice"

def test_revoked_session_clears_workspace(store):
    store.register("alice", "Alice", PASSWORD)
    token = store.login("alice", PASSWORD)
    at = AppTest.from_file(APP)
    at.session_state["_auth_token"] = token
    at.run()
    at.session_state["private_test_value"] = "PRIVATE_CONTENT"
    store.logout(token)
    at.run()
    assert not at.exception
    assert "private_test_value" not in at.session_state
    assert len(at.chat_input) == 0

def test_switching_accounts_clears_previous_content(store):
    store.register("alice", "Alice", PASSWORD)
    store.register("bobby", "Bob", PASSWORD)
    at = AppTest.from_file(APP)
    at.session_state["_auth_token"] = store.login("alice", PASSWORD)
    at.run()
    at.session_state["private_test_value"] = "ALICE_DOCUMENT"
    at.session_state["_auth_token"] = store.login("bobby", PASSWORD)
    at.run()
    assert not at.exception
    assert "private_test_value" not in at.session_state
    assert at.session_state["chat_history"] == []

def test_closed_registration(store, monkeypatch):
    monkeypatch.setenv("CORTEX_ALLOW_REGISTRATION", "false")
    at = AppTest.from_file(APP).run()
    assert not at.exception
    assert not any(b.label == "Create account" for b in at.button)

def test_oidc_missing_configuration_fails_closed(monkeypatch):
    monkeypatch.setattr(ui, "_mode", lambda: "oidc")
    monkeypatch.setattr(ui, "oidc_user", lambda: None)
    monkeypatch.setattr(ui, "oidc_configured", lambda: False)
    at = AppTest.from_file(APP).run()
    assert not at.exception
    assert not any(b.label in ("Process documents", "Create account") for b in at.button)
    assert any("provider setup" in i.value for i in at.info)
