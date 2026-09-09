"""Validate identities supplied by Streamlit's native OpenID Connect login.

Streamlit and Authlib perform the protocol/token signature validation. These
helpers only read the resulting identity, enforce local authorization, and
return a stable workspace owner ID. They never initiate login or logout.
"""

import hashlib
import json
import math
import os
from pathlib import Path
import re
import time
from urllib.parse import urlparse

from dotenv import dotenv_values
import streamlit as st

from rag.config import UserFacingError

ROOT = Path(__file__).resolve().parents[1]
_REQUIRED_SETTINGS = (
    "redirect_uri", "cookie_secret", "client_id", "client_secret",
    "server_metadata_url",
)


def _secrets():
    try:
        return st.secrets
    except Exception:
        # secrets.toml is optional when the application uses local accounts.
        return {}


def _configured_value(value):
    if not isinstance(value, str):
        return False
    normalized = value.strip().lower()
    return bool(normalized) and not (
        normalized in {"xxx", "none", "null", "changeme", "change_me",
                       "replace_me", "secret", "client_id", "client_secret"}
        or normalized.startswith(("your_", "your-", "your ", "paste_", "paste-",
                                   "paste ", "replace_", "replace-", "replace "))
        or any(marker in normalized for marker in ("<", ">", "${", "{", "}"))
    )


def oidc_configured():
    """Return whether the unnamed OIDC provider has usable configuration.

    This is a configuration-shape check, not an outbound provider validation.
    No setting values or upstream exceptions are exposed to the caller.
    """
    try:
        settings = _secrets().get("auth", {})
        if not all(_configured_value(settings.get(key)) for key in _REQUIRED_SETTINGS):
            return False
        if len(settings["cookie_secret"].strip()) < 32:
            return False
        for key in ("redirect_uri", "server_metadata_url"):
            uri = settings[key].strip()
            if any(character.isspace() for character in uri):
                return False
            parsed = urlparse(uri)
            if parsed.scheme not in ("http", "https") or not parsed.hostname:
                return False
            if parsed.username or parsed.password:
                return False
            # Accessing port also rejects invalid/out-of-range URL ports.
            if parsed.port is not None and not 1 <= parsed.port <= 65535:
                return False
        if urlparse(settings["server_metadata_url"].strip()).scheme != "https":
            return False
        redirect = urlparse(settings["redirect_uri"].strip())
        if redirect.scheme != "https" and redirect.hostname not in {"localhost", "127.0.0.1", "::1"}:
            return False
        return redirect.path.endswith("/oauth2callback") and not (redirect.query or redirect.fragment)
    except Exception:
        return False


def _claim(user, name, default=None):
    try:
        return user.get(name, default)
    except (AttributeError, TypeError):
        return getattr(user, name, default)


def _string_claim(user, name):
    value = _claim(user, name)
    return value.strip() if isinstance(value, str) else ""


def _allowed_emails():
    """Resolve a comma-separated allowlist; malformed restrictions deny access."""
    try:
        sources = (os.environ, _secrets(), dotenv_values(ROOT / ".env", interpolate=False))
        for source in sources:
            raw = source.get("CORTEX_ALLOWED_EMAILS")
            if raw is None or raw == "":
                continue
            if not isinstance(raw, str):
                raise ValueError("invalid setting type")
            if not raw.strip():
                continue
            emails = {item.strip().casefold() for item in raw.split(",") if item.strip()}
            if not emails or any(not re.fullmatch(r"[^\s@,]+@[^\s@,]+\.[^\s@,]+", email) for email in emails):
                raise ValueError("invalid email setting")
            return emails
    except Exception:
        raise UserFacingError(
            "Sign-in access rules are not configured correctly. Ask the app owner to check CORTEX_ALLOWED_EMAILS."
        ) from None
    return set()


def oidc_user():
    """Return an authorized identity, or None when the visitor is signed out.

    An authenticated but incomplete, expired, or disallowed identity raises a safe
    UserFacingError. Callers must show the error and stop before reading workspace
    data; they can offer st.logout() so the visitor can use another account.
    """
    user = st.user
    if _claim(user, "is_logged_in", False) is not True:
        return None
    if not oidc_configured():
        raise UserFacingError("Sign-in is not fully configured. Ask the app owner to check the OIDC settings.")

    issuer = _string_claim(user, "iss")
    subject = _string_claim(user, "sub")
    if not issuer or not subject:
        raise UserFacingError("Your sign-in provider did not return a valid identity. Sign out and try again.")

    expiry = _claim(user, "exp")
    if expiry is not None:
        try:
            if isinstance(expiry, bool):
                raise ValueError("invalid expiry")
            expires_at = float(expiry)
            if not math.isfinite(expires_at) or expires_at <= time.time():
                raise ValueError("expired identity")
        except (TypeError, ValueError, OverflowError):
            raise UserFacingError("Your sign-in session has expired. Sign out and sign in again.") from None

    allowed_emails = _allowed_emails()
    email = _string_claim(user, "email")
    if allowed_emails and (
        _claim(user, "email_verified") is not True or email.casefold() not in allowed_emails
    ):
        raise UserFacingError("This account does not have access to this app. Sign out and use an approved account.")

    # JSON encoding avoids ambiguous boundaries between issuer and subject.
    identity = json.dumps([issuer, subject], ensure_ascii=False, separators=(",", ":"))
    owner_id = "oidc:" + hashlib.sha256(identity.encode("utf-8")).hexdigest()
    username = email or _string_claim(user, "preferred_username") or subject
    return {
        "id": owner_id,
        "username": username,
        "display_name": _string_claim(user, "name") or username,
    }
