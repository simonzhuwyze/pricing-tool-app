"""
Wyze Pricing Tool - Main Application Entry Point
5-module navigation structure with session state management.
Optional JumpCloud SSO authentication (AUTH_ENABLED=true).
"""

import os
import streamlit as st
import sys
from pathlib import Path

# Ensure core/ is on Python path
sys.path.insert(0, str(Path(__file__).parent))

# --- Page config (must be first Streamlit command) ---
st.set_page_config(
    page_title="Wyze Pricing Tool",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Authentication Gate (JumpCloud SSO) ---
# When AUTH_ENABLED=false (default): no impact, returns local_user stub.
# When AUTH_ENABLED=true: redirects to JumpCloud login, enforces roles.
from core.auth import require_auth, show_user_info, AUTH_ENABLED, has_permission

if AUTH_ENABLED:
    user_info = require_auth()
    st.session_state.current_user = user_info.get("email", "local_user")

# --- Session state initialization ---
if "selected_sku" not in st.session_state:
    st.session_state.selected_sku = None
if "user_inputs" not in st.session_state:
    st.session_state.user_inputs = {
        "msrp": 0.0,
        "fob": 0.0,
        "tariff_rate": 0.0,
        "promotion_mix": 0.0,
        "promo_percentage": 0.0,
    }
if "channel_mix" not in st.session_state:
    from core.data_loader import CHANNELS
    st.session_state.channel_mix = {ch: 0.0 for ch in CHANNELS}
if "resolved_assumptions" not in st.session_state:
    st.session_state.resolved_assumptions = None
if "current_user" not in st.session_state:
    st.session_state.current_user = "local_user"

# --- Page definitions ---
# Product Directory
product_directory = st.Page(
    "views/product_directory.py",
    title="Product Directory",
    icon="📦",
)

# Pricing Tool
pt_main = st.Page(
    "views/pricing_tool_main.py",
    title="Pricing Tool",
    icon="💰",
    default=True,
)
pt_cpam = st.Page(
    "views/pricing_tool_cpam.py",
    title="CPAM Calculator",
    icon="🧮",
)
pt_channel_mix = st.Page(
    "views/pricing_tool_channel_mix.py",
    title="Channel Mix",
    icon="📊",
)
pt_sensitivity = st.Page(
    "views/pricing_tool_sensitivity.py",
    title="Sensitivity Analysis",
    icon="📈",
)
pt_assumptions = st.Page(
    "views/pricing_tool_assumptions.py",
    title="Assumptions Loaded",
    icon="📋",
)
pt_export = st.Page(
    "views/pricing_tool_export.py",
    title="Export & Save",
    icon="📄",
)

# Reference
templates = st.Page(
    "views/pricing_templates.py",
    title="Pricing Templates",
    icon="📁",
)
formula_ref = st.Page(
    "views/formula_reference.py",
    title="Formula Reference",
    icon="📐",
)
user_guide = st.Page(
    "views/user_guide.py",
    title="User Guide",
    icon="📖",
)

# Assumptions
a_retail_margin = st.Page(
    "views/assumptions_retail_margin.py",
    title="Retail Margin",
    icon="🧾",
)
a_return_rate = st.Page(
    "views/assumptions_return_rate.py",
    title="Return Rate",
    icon="↩",
)
a_outbound = st.Page(
    "views/assumptions_outbound_shipping.py",
    title="Outbound Shipping",
    icon="🚚",
)
a_product_costs = st.Page(
    "views/assumptions_product_costs.py",
    title="Product Costs",
    icon="🏭",
)
a_finance = st.Page(
    "views/assumptions_finance.py",
    title="Finance Assumptions",
    icon="🏦",
)

# Settings
db_admin = st.Page(
    "views/db_admin.py",
    title="DB Admin",
    icon="⚙",
)
data_validation = st.Page(
    "views/data_validation.py",
    title="Data Validation",
    icon="✅",
)
sf_raw_viewer = st.Page(
    "views/sf_raw_viewer.py",
    title="SF Raw Data",
    icon="❄",
)
user_mgmt = st.Page(
    "views/user_management.py",
    title="User Management",
    icon="👥",
)

# --- Navigation (role-based filtering) ---
try:
    nav_pages = {
        "Product Directory": [product_directory, templates],
        "Pricing Tool": [pt_main, pt_channel_mix, pt_cpam, pt_sensitivity, pt_assumptions, pt_export],
        "Reference": [formula_ref, user_guide],
    }

    if has_permission("edit_assumptions"):
        nav_pages["Assumptions"] = [a_retail_margin, a_return_rate, a_outbound, a_product_costs, a_finance]

    settings_pages = []
    if has_permission("validate_data"):
        settings_pages.append(data_validation)
    if has_permission("sync_snowflake"):
        settings_pages.append(sf_raw_viewer)
    if has_permission("db_admin"):
        settings_pages.extend([db_admin, user_mgmt])
    if settings_pages:
        nav_pages["Settings"] = settings_pages

    pg = st.navigation(nav_pages)
except Exception as e:
    # Fallback: ensure navigation still works even if role check fails
    import logging
    logging.getLogger(__name__).error(f"Navigation setup error: {e}")
    pg = st.navigation({
        "Pricing Tool": [pt_main, pt_channel_mix, pt_cpam, pt_sensitivity, pt_assumptions, pt_export],
        "Product Directory": [product_directory, templates],
        "Reference": [formula_ref, user_guide],
    })

# Show user info in sidebar (only when auth is enabled)
show_user_info()

pg.run()
