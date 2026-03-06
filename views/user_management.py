"""
User Management Page - Manage user roles and permissions.
Admin-only page for RBAC configuration.
"""

import streamlit as st
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.auth import require_permission, ROLES, AUTH_ENABLED
from core.ui_helpers import styled_header

styled_header("User Management", "Manage user roles and permissions.", color="indigo")

require_permission("db_admin", "User Management")

# --- Load database functions ---
try:
    from core.database import list_all_users, set_user_role, delete_user_role
    db_available = True
except Exception as e:
    db_available = False
    st.error(f"Database not available: {e}")
    st.stop()

# =====================================================
# Section 1: Role Reference
# =====================================================
with st.expander("Role & Permission Reference", expanded=False):
    role_data = []
    for role_name, perms in ROLES.items():
        row = {"Role": role_name}
        for perm, val in perms.items():
            row[perm] = "Yes" if val else "-"
        role_data.append(row)
    st.dataframe(pd.DataFrame(role_data), use_container_width=True, hide_index=True)

    st.markdown("""
    **Permission descriptions:**
    - `view_pricing` - View Product Directory, Pricing Tool, Reference pages
    - `edit_assumptions` - Edit Assumptions pages (Retail Margin, Return Rate, etc.)
    - `create_sku` - Create, Edit, Delete SKUs in Product Directory
    - `validate_data` - Access Data Validation page
    - `sync_snowflake` - Access SF Raw Data page
    - `db_admin` - Access DB Admin and User Management pages
    """)

# =====================================================
# Section 2: Current Users
# =====================================================
st.subheader("Current Users")

df_users = list_all_users()

if df_users.empty:
    st.info("No users in the database yet. Add users below or they will be auto-created on first SSO login.")
else:
    # Editable table
    display_df = df_users.copy()
    display_df["last_login"] = display_df["last_login"].apply(
        lambda x: x.strftime("%Y-%m-%d %H:%M") if pd.notna(x) else "Never"
    )

    edited_users = st.data_editor(
        display_df[["email", "role", "name", "last_login"]],
        use_container_width=True,
        num_rows="fixed",
        disabled=["email", "last_login"],
        column_config={
            "email": st.column_config.TextColumn("Email"),
            "role": st.column_config.SelectboxColumn(
                "Role",
                options=["admin", "editor", "viewer"],
                required=True,
            ),
            "name": st.column_config.TextColumn("Display Name"),
            "last_login": st.column_config.TextColumn("Last Login"),
        },
        key="edit_users",
    )

    if st.button("Save Role Changes", type="primary"):
        updated = 0
        for idx, row in edited_users.iterrows():
            orig = df_users.iloc[idx]
            if row["role"] != orig["role"] or row.get("name") != orig.get("name"):
                set_user_role(
                    row["email"],
                    row["role"],
                    name=row.get("name"),
                    updated_by=st.session_state.get("current_user", "admin"),
                )
                updated += 1
        if updated:
            st.success(f"Updated {updated} user(s).")
            st.rerun()
        else:
            st.info("No changes detected.")

# =====================================================
# Section 3: Add New User
# =====================================================
st.subheader("Add New User")
st.caption("Pre-register a user with a specific role before they first log in.")

col_email, col_role, col_name = st.columns([3, 1, 2])
with col_email:
    new_email = st.text_input("Email", placeholder="user@wyze.com", key="new_user_email")
with col_role:
    new_role = st.selectbox("Role", ["editor", "viewer", "admin"], key="new_user_role")
with col_name:
    new_name = st.text_input("Display Name (optional)", key="new_user_name")

if st.button("Add User"):
    if not new_email or "@" not in new_email:
        st.error("Please enter a valid email address.")
    else:
        existing = df_users[df_users["email"] == new_email.lower()]
        if not existing.empty:
            st.warning(f"{new_email} already exists with role: {existing.iloc[0]['role']}")
        else:
            set_user_role(
                new_email,
                new_role,
                name=new_name or None,
                updated_by=st.session_state.get("current_user", "admin"),
            )
            st.success(f"Added {new_email} as {new_role}.")
            st.rerun()

# =====================================================
# Section 4: Remove User
# =====================================================
st.subheader("Remove User")
if not df_users.empty:
    col_del, col_btn = st.columns([3, 1])
    with col_del:
        del_email = st.selectbox(
            "Select user to remove",
            df_users["email"].tolist(),
            key="del_user_email",
        )
    with col_btn:
        st.write("")  # spacer
        st.write("")
        if st.button("Remove", type="secondary"):
            delete_user_role(del_email)
            st.success(f"Removed {del_email}.")
            st.rerun()
else:
    st.info("No users to remove.")

# =====================================================
# Section 5: Auth Status
# =====================================================
st.divider()
st.caption(f"Auth enabled: **{AUTH_ENABLED}** | Current user: **{st.session_state.get('current_user', 'local_user')}**")
if not AUTH_ENABLED:
    st.info("AUTH_ENABLED=false. Set AUTH_ENABLED=true in .env and configure JumpCloud credentials to enable SSO.")
