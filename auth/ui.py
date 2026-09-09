"""Authentication gate and account controls for the Streamlit workspace."""
from pathlib import Path
import streamlit as st
from rag.config import ROOT, _setting, UserFacingError
from auth.service import AuthStore
from auth.oidc import oidc_configured, oidc_user

def _store():
    configured = _setting("CORTEX_AUTH_DB", str(ROOT / "data" / "auth.sqlite3"))
    path = Path(configured).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return AuthStore(path)

def _mode():
    mode = _setting("CORTEX_AUTH_MODE", "local").lower()
    if mode not in ("local", "oidc"):
        raise UserFacingError("CORTEX_AUTH_MODE must be local or oidc. Check the app settings.")
    return mode

def _clear_session(token=None, identity=None):
    # Tokens and all document/chat/widget state belong to one identity only.
    st.session_state.clear()
    if token:
        st.session_state["_auth_token"] = token
    if identity:
        st.session_state["_auth_identity"] = identity

def _recovery_notice():
    code = st.session_state.get("_auth_recovery")
    if not code:
        return
    st.success("Your account is ready. Save this recovery code before signing in.")
    st.caption("Keep it somewhere private. It can reset your password and is shown only here.")
    st.code(code, language=None)
    if st.button("I saved my recovery code", type="primary"):
        st.session_state.pop("_auth_recovery", None)
        st.rerun()

def _local_login(store):
    _recovery_notice()
    login_tab, create_tab, recover_tab = st.tabs(["Sign in", "Create account", "Recover account"])
    with login_tab:
        with st.form("signin", clear_on_submit=True):
            username = st.text_input("Username", key="login_username", max_chars=32)
            password = st.text_input("Password", type="password", key="login_password", max_chars=128)
            submitted = st.form_submit_button("Sign in", type="primary",
                                              disabled=bool(st.session_state.get("_auth_recovery")))
        if submitted:
            try:
                token = store.login(username, password)
                _clear_session(token=token)
                st.rerun()
            except UserFacingError as error:
                st.error(str(error))
            except Exception:
                st.error("Sign-in is temporarily unavailable. Please try again.")
    with create_tab:
        allow = _setting("CORTEX_ALLOW_REGISTRATION", "true").lower()
        if allow not in ("true", "false"):
            st.error("CORTEX_ALLOW_REGISTRATION must be true or false.")
        elif allow == "false":
            st.info("New registrations are closed. Contact the app owner for access.")
        else:
            with st.form("register", clear_on_submit=True):
                name = st.text_input("Display name", max_chars=80)
                username = st.text_input("Choose a username", max_chars=32)
                password = st.text_input("Choose a password", type="password", max_chars=128)
                confirm = st.text_input("Confirm password", type="password", max_chars=128)
                st.caption("Username: 3–32 letters, numbers, dots, underscores or hyphens. Password: 12–128 characters.")
                submitted = st.form_submit_button("Create account", type="primary",
                                                  disabled=bool(st.session_state.get("_auth_recovery")))
            if submitted:
                try:
                    if password != confirm:
                        raise UserFacingError("The passwords do not match.")
                    created = store.register(username, name, password)
                    st.session_state["_auth_recovery"] = created["recovery_code"]
                    st.rerun()
                except UserFacingError as error:
                    st.error(str(error))
                except Exception:
                    st.error("Account creation is temporarily unavailable. Please try again.")
    with recover_tab:
        st.caption("Use the recovery code saved when you created your account. No email is sent.")
        with st.form("recover", clear_on_submit=True):
            username = st.text_input("Account username", max_chars=32)
            code = st.text_input("Recovery code", type="password", max_chars=256)
            password = st.text_input("New password", type="password", max_chars=128)
            confirm = st.text_input("Confirm new password", type="password", max_chars=128)
            submitted = st.form_submit_button("Reset password",
                                              disabled=bool(st.session_state.get("_auth_recovery")))
        if submitted:
            try:
                if password != confirm:
                    raise UserFacingError("The passwords do not match.")
                new_code = store.recover(username, code, password)
                _clear_session()
                st.session_state["_auth_recovery"] = new_code
                st.rerun()
            except UserFacingError as error:
                st.error(str(error))
            except Exception:
                st.error("Account recovery is temporarily unavailable. Please try again.")

def require_user():
    """Stop the app before document rendering or API access unless authenticated."""
    try:
        mode = _mode()
        store = _store() if mode == "local" else None
        token = st.session_state.get("_auth_token")
        user = store.get_session(token) if store and token else None
        if mode == "oidc":
            try:
                user = oidc_user()
            except UserFacingError as error:
                _clear_session()
                st.error(str(error))
                if st.button("Sign out"):
                    st.logout()
                st.stop()
    except UserFacingError as error:
        st.error(str(error))
        st.stop()
    except Exception:
        st.error("Account service unavailable. Check the app configuration and database access.")
        st.stop()

    if not user:
        if st.session_state.get("_auth_identity") or st.session_state.get("_auth_token"):
            _clear_session()
        st.caption("YOUR PRIVATE RESEARCH WORKSPACE")
        st.title("Cortex Research AI")
        st.markdown("Sign in to explore your documents, follow the evidence, and save your findings as downloads.")
        if mode == "local":
            _local_login(store)
        else:
            if not oidc_configured():
                st.info("Sign-in provider setup is required. The app owner can follow AUTHENTICATION.md.")
            elif st.button("Continue with your identity provider", type="primary"):
                try:
                    # Logout an expired cookie first; the next visit starts a new login.
                    if st.user.is_logged_in:
                        _clear_session()
                        st.logout()
                    else:
                        st.login()
                except Exception:
                    st.error("Could not start sign-in. Check the identity provider settings.")
        st.caption("Your documents remain separate from other users. Signing out clears this workspace.")
        st.stop()

    identity = f"{mode}:{user['id']}"
    if st.session_state.get("_auth_identity") != identity:
        _clear_session(token if mode == "local" else None, identity)
    with st.sidebar:
        st.caption("SIGNED IN")
        st.write(user["display_name"])
        if st.button("Sign out", use_container_width=True):
            if mode == "local":
                try:
                    store.logout(token)
                except UserFacingError:
                    _clear_session()
                    st.error("Signed out here. Account storage could not confirm session revocation.")
                    st.stop()
                _clear_session()
                st.rerun()
            else:
                _clear_session()
                st.logout()
        if mode == "local":
            with st.expander("Account settings"):
                st.caption("Changing your password signs out all active sessions.")
                with st.form("change_password", clear_on_submit=True):
                    old = st.text_input("Current password", type="password", max_chars=128)
                    new = st.text_input("New account password", type="password", max_chars=128)
                    confirm = st.text_input("Confirm account password", type="password", max_chars=128)
                    change = st.form_submit_button("Change password")
                if change:
                    try:
                        if new != confirm:
                            raise UserFacingError("The passwords do not match.")
                        store.change_password(token, old, new)
                        _clear_session()
                        st.rerun()
                    except UserFacingError as error:
                        st.error(str(error))
                    except Exception:
                        st.error("Password change is temporarily unavailable.")
        st.divider()
    return user
