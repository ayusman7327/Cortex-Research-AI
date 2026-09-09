"""Native-provider configuration and authorization without network or cookies."""

from types import SimpleNamespace

import pytest

from auth import oidc
from rag.config import UserFacingError


@pytest.fixture(autouse=True)
def identity_settings(monkeypatch, tmp_path):
    monkeypatch.delenv("CORTEX_ALLOWED_EMAILS", raising=False)
    monkeypatch.setattr(oidc, "ROOT", tmp_path)
    monkeypatch.setattr(oidc.time, "time", lambda: 1000)
    fake_st = SimpleNamespace(
        secrets={"auth": {
            "redirect_uri": "http://localhost:8501/oauth2callback",
            "cookie_secret": "a-random-test-only-cookie-value-1234567890",
            "client_id": "test-provider-client-id",
            "client_secret": "test-provider-client-secret",
            "server_metadata_url": "https://accounts.google.com/.well-known/openid-configuration",
        }},
        user={"is_logged_in": True, "iss": "https://accounts.google.com", "sub": "provider-user-123",
              "name": "Researcher", "email": "researcher@example.org", "email_verified": True, "exp": 2000},
    )
    monkeypatch.setattr(oidc, "st", fake_st)
    return fake_st


def test_valid_config_and_identity(identity_settings):
    assert oidc.oidc_configured() is True
    user = oidc.oidc_user()
    assert user["id"].startswith("oidc:")
    assert user["username"] == "researcher@example.org"
    assert user["display_name"] == "Researcher"
    assert set(user) == {"id", "username", "display_name"}


def test_identity_is_stable_across_email_or_name_changes(identity_settings):
    original = oidc.oidc_user()["id"]
    identity_settings.user.update(email="new@example.org", name="Renamed")
    assert oidc.oidc_user()["id"] == original
    identity_settings.user["sub"] = "another-provider-user"
    assert oidc.oidc_user()["id"] != original


def test_different_issuer_has_separate_workspace(identity_settings):
    original = oidc.oidc_user()["id"]
    identity_settings.user["iss"] = "https://another-provider.example.org"
    assert oidc.oidc_user()["id"] != original


@pytest.mark.parametrize("name", oidc._REQUIRED_SETTINGS)
@pytest.mark.parametrize("value", [None, "", "   ", "xxx", "your_client_secret", "replace-me", "<client-id>"])
def test_missing_and_placeholder_provider_settings(identity_settings, name, value):
    identity_settings.secrets["auth"][name] = value
    assert oidc.oidc_configured() is False
    with pytest.raises(UserFacingError, match="not fully configured"):
        oidc.oidc_user()


@pytest.mark.parametrize("uri", ["/oauth2callback", "https://example.org", "https://example.org/oauth2callback?x=1",
                                "https://example.org/oauth2callback#x", "https://secret@example.org/oauth2callback"])
def test_bad_redirect_configuration_is_rejected(identity_settings, uri):
    identity_settings.secrets["auth"]["redirect_uri"] = uri
    assert oidc.oidc_configured() is False


@pytest.mark.parametrize("uri", [
    "http://localhost:8501/oauth2callback", "http://127.0.0.1:8501/oauth2callback",
    "http://[::1]:8501/oauth2callback", "https://research.example.org/oauth2callback",
])
def test_https_and_explicit_localhost_redirects_are_supported(identity_settings, uri):
    identity_settings.secrets["auth"]["redirect_uri"] = uri
    assert oidc.oidc_configured() is True


@pytest.mark.parametrize("uri", [
    "http://research.example.org/oauth2callback", "http://localhost.example.org/oauth2callback",
    "http://127.0.0.2/oauth2callback", "http://127.1/oauth2callback",
    "http://[::ffff:127.0.0.1]/oauth2callback", "http://0.0.0.0/oauth2callback",
    "https://example.org:70000/oauth2callback", "https://example.org:invalid/oauth2callback",
    "https://example.org:0/oauth2callback", "https://exam ple.org/oauth2callback",
    "https://example.org/oauth2\ncallback",
])
def test_insecure_or_malformed_redirects_are_rejected(identity_settings, uri):
    identity_settings.secrets["auth"]["redirect_uri"] = uri
    assert oidc.oidc_configured() is False


@pytest.mark.parametrize("uri", [
    "http://accounts.google.com/.well-known/openid-configuration",
    "http://localhost:8000/.well-known/openid-configuration",
    "/.well-known/openid-configuration", "https:///.well-known/openid-configuration",
    "https://user:password@example.org/.well-known/openid-configuration",
])
def test_metadata_discovery_requires_https(identity_settings, uri):
    identity_settings.secrets["auth"]["server_metadata_url"] = uri
    assert oidc.oidc_configured() is False


@pytest.mark.parametrize("length, expected", [(1, False), (31, False), (32, True), (64, True)])
def test_cookie_secret_requires_at_least_32_characters(identity_settings, length, expected):
    identity_settings.secrets["auth"]["cookie_secret"] = "a" * length
    assert oidc.oidc_configured() is expected


def test_missing_secrets_are_safe(monkeypatch):
    class MissingSecrets:
        user = {"is_logged_in": False}

        @property
        def secrets(self):
            raise FileNotFoundError("private/path/to/secrets.toml")

    monkeypatch.setattr(oidc, "st", MissingSecrets())
    assert oidc.oidc_configured() is False
    assert oidc.oidc_user() is None


def test_signed_out_identity_is_not_authorized(identity_settings):
    identity_settings.user["is_logged_in"] = False
    assert oidc.oidc_user() is None


def test_attribute_style_user_supported(identity_settings):
    identity_settings.user = SimpleNamespace(**identity_settings.user)
    assert oidc.oidc_user()["display_name"] == "Researcher"


@pytest.mark.parametrize("claim", ["sub", "iss"])
@pytest.mark.parametrize("value", [None, "", "  ", 123])
def test_incomplete_identity_denied(identity_settings, claim, value):
    identity_settings.user[claim] = value
    with pytest.raises(UserFacingError, match="valid identity"):
        oidc.oidc_user()


@pytest.mark.parametrize("expiry", [999, 1000, True, "invalid-private-value", float("nan"), float("inf"), []])
def test_expired_or_invalid_expiry_denied(identity_settings, expiry):
    identity_settings.user["exp"] = expiry
    with pytest.raises(UserFacingError, match="expired") as error:
        oidc.oidc_user()
    assert "private-value" not in str(error.value)


def test_optional_expiry_and_email_claims(identity_settings):
    for claim in ("exp", "email", "email_verified", "name"):
        identity_settings.user.pop(claim)
    user = oidc.oidc_user()
    assert user["username"] == "provider-user-123"
    assert user["display_name"] == "provider-user-123"


def test_allowlist_is_case_insensitive_and_requires_verified_email(monkeypatch, identity_settings):
    monkeypatch.setenv("CORTEX_ALLOWED_EMAILS", " ADMIN@example.org, Researcher@Example.org ")
    assert oidc.oidc_user() is not None
    identity_settings.user["email"] = "stranger@example.org"
    with pytest.raises(UserFacingError, match="does not have access"):
        oidc.oidc_user()


@pytest.mark.parametrize("verified", [False, None, "true", "false", 1])
def test_restricted_login_requires_boolean_verified_claim(monkeypatch, identity_settings, verified):
    monkeypatch.setenv("CORTEX_ALLOWED_EMAILS", "researcher@example.org")
    identity_settings.user["email_verified"] = verified
    with pytest.raises(UserFacingError, match="does not have access"):
        oidc.oidc_user()


def test_allowlist_precedence(monkeypatch, identity_settings, tmp_path):
    (tmp_path / ".env").write_text("CORTEX_ALLOWED_EMAILS=local@example.org\n", encoding="utf-8")
    identity_settings.secrets["CORTEX_ALLOWED_EMAILS"] = "cloud@example.org"
    monkeypatch.setenv("CORTEX_ALLOWED_EMAILS", "researcher@example.org")
    assert oidc.oidc_user() is not None
    monkeypatch.delenv("CORTEX_ALLOWED_EMAILS")
    with pytest.raises(UserFacingError, match="does not have access"):
        oidc.oidc_user()
    identity_settings.user["email"] = "cloud@example.org"
    assert oidc.oidc_user() is not None
    del identity_settings.secrets["CORTEX_ALLOWED_EMAILS"]
    identity_settings.user["email"] = "local@example.org"
    assert oidc.oidc_user() is not None


def test_blank_environment_does_not_disable_cloud_allowlist(monkeypatch, identity_settings):
    monkeypatch.setenv("CORTEX_ALLOWED_EMAILS", " ")
    identity_settings.secrets["CORTEX_ALLOWED_EMAILS"] = "other@example.org"
    with pytest.raises(UserFacingError, match="does not have access"):
        oidc.oidc_user()


@pytest.mark.parametrize("value", [",", "private-invalid-email", ["researcher@example.org"], True])
def test_malformed_access_setting_fails_closed(identity_settings, value):
    identity_settings.secrets["CORTEX_ALLOWED_EMAILS"] = value
    with pytest.raises(UserFacingError, match="access rules") as error:
        oidc.oidc_user()
    assert "private-invalid-email" not in str(error.value)
