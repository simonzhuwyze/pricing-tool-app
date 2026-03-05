"""
Authentication & Authorization Module (JumpCloud OIDC SSO)

When AUTH_ENABLED=true:
  - Redirects to JumpCloud OIDC login
  - Validates tokens and extracts user info
  - Enforces role-based access control

When AUTH_ENABLED=false (default):
  - Returns a local_user stub with admin permissions
  - Zero impact on existing development experience

JumpCloud OIDC Configuration:
  - Create a "Custom OIDC App" in JumpCloud Admin Console
  - Set Redirect URI to your app URL + /callback
  - Grant type: Authorization Code
  - Scopes: openid, profile, email

Required .env variables (when AUTH_ENABLED=true):
  AUTH_ENABLED=true
  JUMPCLOUD_ISSUER=https://oauth.id.jumpcloud.com/
  JUMPCLOUD_CLIENT_ID=your_client_id
  JUMPCLOUD_CLIENT_SECRET=your_client_secret
  JUMPCLOUD_REDIRECT_URI=http://localhost:8501
"""

import os
import logging
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Load .env if not already loaded
_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if "=" in _line and not _line.startswith("#"):
            _k, _v = _line.split("=", 1)
            _v = _v.strip().strip('"').strip("'")
            if _k.strip() not in os.environ or not os.environ[_k.strip()]:
                os.environ[_k.strip()] = _v

AUTH_ENABLED = os.environ.get("AUTH_ENABLED", "false").lower() == "true"

OIDC_ISSUER = os.environ.get("JUMPCLOUD_ISSUER", "https://oauth.id.jumpcloud.com/")
OIDC_CLIENT_ID = os.environ.get("JUMPCLOUD_CLIENT_ID", "")
OIDC_CLIENT_SECRET = os.environ.get("JUMPCLOUD_CLIENT_SECRET", "")
OIDC_REDIRECT_URI = os.environ.get("JUMPCLOUD_REDIRECT_URI", "http://localhost:8501")

# Well-known OIDC endpoints (JumpCloud standard)
OIDC_AUTH_ENDPOINT = f"{OIDC_ISSUER}oauth/authorize"
OIDC_TOKEN_ENDPOINT = f"{OIDC_ISSUER}oauth/token"
OIDC_USERINFO_ENDPOINT = f"{OIDC_ISSUER}userinfo"
OIDC_JWKS_URI = f"{OIDC_ISSUER}.well-known/jwks.json"

# Scopes
OIDC_SCOPES = "openid profile email"

# ---------------------------------------------------------------------------
# Role definitions & permissions
# ---------------------------------------------------------------------------

ROLES = {
    "admin": {
        "view_pricing": True,
        "edit_assumptions": True,
        "create_sku": True,
        "validate_data": True,
        "sync_snowflake": True,
        "db_admin": True,
    },
    "editor": {
        "view_pricing": True,
        "edit_assumptions": True,
        "create_sku": True,
        "validate_data": True,
        "sync_snowflake": False,
        "db_admin": False,
    },
    "viewer": {
        "view_pricing": True,
        "edit_assumptions": False,
        "create_sku": False,
        "validate_data": False,
        "sync_snowflake": False,
        "db_admin": False,
    },
}

DEFAULT_ROLE = "editor"  # Default role for authenticated users not in user_roles table


# ---------------------------------------------------------------------------
# Core Auth Functions
# ---------------------------------------------------------------------------

def require_auth() -> dict:
    """
    Main auth gate. Call this at the top of app.py.

    If AUTH_ENABLED=true:
      - Checks st.session_state for valid auth token
      - If not authenticated, redirects to JumpCloud login
      - Returns user info dict {email, name, role}

    If AUTH_ENABLED=false:
      - Returns local user stub with admin role
    """
    if not AUTH_ENABLED:
        return {
            "email": "local_user",
            "name": "Local Developer",
            "role": "admin",
            "authenticated": False,
        }

    import streamlit as st

    # Check if already authenticated
    if "auth_user" in st.session_state and st.session_state.auth_user:
        return st.session_state.auth_user

    # Check for callback code in URL params
    params = st.query_params
    code = params.get("code")

    if code:
        # Exchange code for token
        user_info = _exchange_code(code)
        if user_info:
            st.session_state.auth_user = user_info
            st.query_params.clear()
            st.rerun()
        else:
            st.error("Authentication failed. Please try again.")
            _show_login_button()
            st.stop()
    else:
        # Not authenticated, show login
        _show_login_button()
        st.stop()

    return st.session_state.get("auth_user", {})


def _show_login_button():
    """Show the SSO login button."""
    import streamlit as st
    import urllib.parse

    st.markdown("### Please sign in to continue")
    st.markdown("This application requires JumpCloud SSO authentication.")

    auth_url = (
        f"{OIDC_AUTH_ENDPOINT}?"
        f"client_id={OIDC_CLIENT_ID}&"
        f"response_type=code&"
        f"scope={urllib.parse.quote(OIDC_SCOPES)}&"
        f"redirect_uri={urllib.parse.quote(OIDC_REDIRECT_URI)}&"
        f"state=pricing_tool"
    )

    st.link_button("Sign in with JumpCloud SSO", auth_url, type="primary")


def _exchange_code(code: str) -> Optional[dict]:
    """Exchange authorization code for tokens and extract user info."""
    try:
        import requests

        # Token exchange
        token_response = requests.post(
            OIDC_TOKEN_ENDPOINT,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": OIDC_REDIRECT_URI,
                "client_id": OIDC_CLIENT_ID,
                "client_secret": OIDC_CLIENT_SECRET,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10,
        )

        if token_response.status_code != 200:
            logger.error(f"Token exchange failed: {token_response.status_code} {token_response.text}")
            return None

        tokens = token_response.json()
        access_token = tokens.get("access_token")

        if not access_token:
            logger.error("No access_token in response")
            return None

        # Get user info
        userinfo_response = requests.get(
            OIDC_USERINFO_ENDPOINT,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )

        if userinfo_response.status_code != 200:
            logger.error(f"Userinfo failed: {userinfo_response.status_code}")
            return None

        userinfo = userinfo_response.json()
        email = userinfo.get("email", "unknown@wyze.com")
        name = userinfo.get("name", email.split("@")[0])

        # Determine role from DB (falls back to DEFAULT_ROLE)
        try:
            from core.database import get_user_role, update_last_login
            role = get_user_role(email)
            update_last_login(email, name)
        except Exception:
            role = DEFAULT_ROLE

        return {
            "email": email,
            "name": name,
            "role": role,
            "authenticated": True,
        }

    except Exception as e:
        logger.error(f"Auth exchange error: {e}")
        return None


def get_current_user() -> str:
    """Return the current user's email."""
    if not AUTH_ENABLED:
        return "local_user"

    try:
        import streamlit as st
        user = st.session_state.get("auth_user", {})
        return user.get("email", "local_user")
    except Exception:
        return "local_user"


def get_current_role() -> str:
    """Return the current user's role."""
    if not AUTH_ENABLED:
        return "admin"

    try:
        import streamlit as st
        user = st.session_state.get("auth_user", {})
        return user.get("role", "viewer")
    except Exception:
        return "viewer"


def has_permission(action: str) -> bool:
    """
    Check if current user has permission for an action.

    Actions: view_pricing, edit_assumptions, create_sku,
             validate_data, sync_snowflake, db_admin
    """
    role = get_current_role()
    permissions = ROLES.get(role, ROLES["viewer"])
    return permissions.get(action, False)


def require_permission(action: str, page_label: str = ""):
    """
    Page-level permission gate. Shows warning and stops if user lacks permission.
    No-op when AUTH_ENABLED=false (local dev).
    """
    if not AUTH_ENABLED:
        return
    if not has_permission(action):
        import streamlit as st
        st.warning(f"You don't have permission to access {page_label}. Current role: {get_current_role()}")
        st.info("Please contact an admin for access.")
        st.stop()


def logout():
    """Clear auth session state."""
    try:
        import streamlit as st
        if "auth_user" in st.session_state:
            del st.session_state.auth_user
    except Exception:
        pass


def show_user_info():
    """Display current user info in sidebar (call from app.py)."""
    if not AUTH_ENABLED:
        return

    try:
        import streamlit as st
        user = st.session_state.get("auth_user", {})
        if user:
            with st.sidebar:
                st.markdown("---")
                st.caption(f"Signed in as: **{user.get('name', 'Unknown')}**")
                st.caption(f"Role: `{user.get('role', 'viewer')}`")
                if st.button("Sign Out", key="btn_signout"):
                    logout()
                    st.rerun()
    except Exception:
        pass
