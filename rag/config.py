"""Configuration for local development and Streamlit Community Cloud.

Settings use environment variables, then Streamlit secrets, then the local .env.
Credentials are resolved when needed and never included in public API errors.
"""
import os
from pathlib import Path
import sys

from dotenv import dotenv_values
from google import genai
from google.genai import types

ROOT = Path(__file__).resolve().parents[1]


class UserFacingError(ValueError):
    """A deliberately written, safe validation message for the app user."""


class ConfigError(UserFacingError):
    """An actionable configuration problem without credential values."""


def _streamlit_settings():
    # Normal scripts and tests do not need to import or initialize Streamlit.
    streamlit = sys.modules.get("streamlit")
    if streamlit is None:
        return {}
    try:
        secrets = streamlit.secrets
        return {name: secrets.get(name) for name in (
            "GEMINI_API_KEY", "GOOGLE_API_KEY", "GEMINI_MODEL",
            "GEMINI_EMBEDDING_MODEL", "GEMINI_TIMEOUT_SECONDS",
            "CORTEX_AUTH_MODE", "CORTEX_AUTH_DB", "CORTEX_ALLOW_REGISTRATION", "CORTEX_ALLOWED_EMAILS",
        )}
    except Exception:
        # Missing secrets.toml is normal for local .env-based development.
        return {}


def _sources():
    yield os.environ
    yield _streamlit_settings()
    yield dotenv_values(ROOT / ".env", interpolate=False)


def _setting(name, default):
    for source in _sources():
        value = source.get(name)
        if isinstance(value, (str, int, float)) and str(value).strip():
            return str(value).strip()
    return default


def _valid_key(value):
    if not isinstance(value, str):
        return False
    normalized = value.strip().lower()
    return bool(normalized) and not (
        normalized in {"none", "null", "changeme", "change_me", "replace_me",
                       "api_key", "gemini_api_key", "google_api_key"}
        or normalized.startswith(("your_", "your-", "your ", "paste_", "paste-",
                                   "paste ", "replace_", "replace-", "replace ",
                                   "<", "${"))
    )


def _api_key():
    for source in _sources():
        for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
            value = source.get(name)
            if _valid_key(value):
                return value.strip()
    return None


def has_api_key():
    """Report whether a non-placeholder key is configured, without exposing it."""
    return _api_key() is not None


GENERATION_MODEL = _setting("GEMINI_MODEL", "gemini-3.6-flash")
EMBEDDING_MODEL = _setting("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
EMBEDDING_DIMENSION = 768


def get_client():
    key = _api_key()
    if key is None:
        raise ConfigError(
            "Add GEMINI_API_KEY to your local .env file or Streamlit Cloud app "
            "secrets, then restart the app."
        )
    try:
        timeout_seconds = int(_setting("GEMINI_TIMEOUT_SECONDS", "60"))
    except (TypeError, ValueError):
        raise ConfigError("GEMINI_TIMEOUT_SECONDS must be a whole number from 10 to 300.") from None
    if not 10 <= timeout_seconds <= 300:
        raise ConfigError("GEMINI_TIMEOUT_SECONDS must be a whole number from 10 to 300.")
    return genai.Client(
        api_key=key,
        http_options=types.HttpOptions(
            timeout=timeout_seconds * 1000,
            retry_options=types.HttpRetryOptions(
                attempts=3, initial_delay=1, max_delay=8,
                http_status_codes=[408, 429, 500, 502, 503, 504],
            ),
        ),
    )


def public_error(error):
    """Never display raw SDK exception text, request URLs, or payloads."""
    if isinstance(error, UserFacingError):
        return str(error)
    try:
        code = int(getattr(error, "code", 0) or 0)
    except (TypeError, ValueError):
        code = 0
    if code in (401, 403):
        return "Gemini access denied. Check your API key and project permissions."
    if code == 429:
        return "Gemini quota reached. Check your API quota or billing, or wait before trying again."
    if code == 404:
        return "Configured Gemini model unavailable. Check the model names in .env or Streamlit secrets."
    if code == 400:
        return "Gemini could not process this request. Check your model settings and try a smaller document or question."
    if code in (408, 500, 502, 503, 504) or isinstance(error, TimeoutError):
        return "Gemini is temporarily unavailable or timed out. Please try again shortly."
    return "Operation failed. Check your connection and Gemini configuration, then retry."
