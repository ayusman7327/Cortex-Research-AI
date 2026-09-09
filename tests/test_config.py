"""Credential resolution and public errors, tested without real credentials."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from rag import config


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ROOT", tmp_path)
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GEMINI_TIMEOUT_SECONDS",
                 "GEMINI_MODEL", "GEMINI_EMBEDDING_MODEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(config, "_streamlit_settings", lambda: {})


def test_environment_wins_over_cloud_and_dotenv(monkeypatch, tmp_path):
    monkeypatch.setenv("GOOGLE_API_KEY", "env-test-key")
    monkeypatch.setattr(config, "_streamlit_settings", lambda: {"GEMINI_API_KEY": "cloud-test-key"})
    (tmp_path / ".env").write_text("GEMINI_API_KEY=local-test-key\n", encoding="utf-8")
    assert config._api_key() == "env-test-key"


def test_cloud_wins_over_dotenv(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "_streamlit_settings", lambda: {"GEMINI_API_KEY": "cloud-test-key"})
    (tmp_path / ".env").write_text("GEMINI_API_KEY=local-test-key\n", encoding="utf-8")
    assert config._api_key() == "cloud-test-key"


def test_dotenv_fallback_does_not_mutate_environment(tmp_path):
    (tmp_path / ".env").write_text("GEMINI_API_KEY=local-test-key\n", encoding="utf-8")
    assert config.has_api_key()
    assert config._api_key() == "local-test-key"
    assert "GEMINI_API_KEY" not in config.os.environ


@pytest.mark.parametrize("placeholder", ["", "   ", "your_api_key_here", "YOUR_GEMINI_API_KEY",
                                           "paste-your-key", "<API_KEY>", "replace_me", "null"])
def test_placeholder_keys_are_rejected(monkeypatch, placeholder):
    monkeypatch.setenv("GEMINI_API_KEY", placeholder)
    assert not config.has_api_key()
    with pytest.raises(config.ConfigError, match="Streamlit Cloud"):
        config.get_client()


def test_placeholder_does_not_hide_real_cloud_setting(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "your_api_key_here")
    monkeypatch.setattr(config, "_streamlit_settings", lambda: {"GEMINI_API_KEY": "cloud-test-key"})
    assert config.has_api_key()


def test_client_timeout_and_bounded_retries(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_TIMEOUT_SECONDS", "90")
    factory = Mock()
    monkeypatch.setattr(config.genai, "Client", factory)
    assert config.get_client() is factory.return_value
    options = factory.call_args.kwargs["http_options"]
    assert options.timeout == 90000
    assert options.retry_options.attempts == 3
    assert 503 in options.retry_options.http_status_codes
    assert 403 not in options.retry_options.http_status_codes


@pytest.mark.parametrize("timeout", ["hello-secret", "1", "301", "1.5"])
def test_invalid_timeout_is_actionable_and_redacted(monkeypatch, timeout):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_TIMEOUT_SECONDS", timeout)
    with pytest.raises(config.ConfigError) as caught:
        config.get_client()
    assert "whole number" in config.public_error(caught.value)
    assert "hello-secret" not in config.public_error(caught.value)


@pytest.mark.parametrize("error", [RuntimeError("SECRET_KEY"), ValueError("SECRET_KEY")])
def test_untrusted_exception_messages_are_not_displayed(error):
    assert "SECRET_KEY" not in config.public_error(error)


@pytest.mark.parametrize("code, expected", [(401, "access denied"), ("403", "access denied"),
                                             (429, "quota"), (404, "model unavailable"),
                                             (503, "temporarily unavailable")])
def test_api_errors_are_actionable_and_redacted(code, expected):
    error = RuntimeError("SECRET_KEY")
    error.code = code
    message = config.public_error(error)
    assert expected in message
    assert "SECRET_KEY" not in message


def test_deliberate_validation_message_is_preserved():
    assert config.public_error(config.UserFacingError("Upload a document first.")) == "Upload a document first."


def test_streamlit_secrets_can_be_read_without_file(monkeypatch):
    # Undo the fixture override to test the lazy Streamlit lookup itself.
    import importlib.util
    spec = importlib.util.spec_from_file_location("isolated_config", config.__file__)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(config.sys.modules, "streamlit", SimpleNamespace(secrets={"GEMINI_API_KEY": "cloud-test-key"}))
    spec.loader.exec_module(module)
    assert module._streamlit_settings()["GEMINI_API_KEY"] == "cloud-test-key"


def test_missing_streamlit_secrets_are_optional(monkeypatch):
    import importlib.util
    class MissingSecrets:
        @property
        def secrets(self):
            raise FileNotFoundError("No secrets.toml")
    spec = importlib.util.spec_from_file_location("isolated_config", config.__file__)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(config.sys.modules, "streamlit", MissingSecrets())
    spec.loader.exec_module(module)
    assert module._streamlit_settings() == {}
