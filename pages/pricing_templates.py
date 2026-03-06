"""
Pricing Templates - Save, load, browse, and manage pricing sessions.
Requires Azure SQL connection for persistence.
"""

import os
import streamlit as st
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Auto-load .env
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            key, val = line.split("=", 1)
            os.environ[key.strip()] = val.strip().strip('"').strip("'")

from core.data_loader import CHANNELS

from core.ui_helpers import styled_header
styled_header("Pricing Templates", "Save and load complete pricing sessions. Templates include inputs, channel mix, and assumption snapshots.")

# Check DB
db_connected = False
try:
    from core.database import get_sqlalchemy_engine
    engine = get_sqlalchemy_engine()
    pd.read_sql("SELECT 1", engine)
    db_connected = True
except Exception as e:
    st.error(f"Database not connected: {e}")
    st.info("Templates require Azure SQL. Go to **DB Admin** to configure.")
    st.stop()

from core.template_manager import (
    list_templates, load_template_to_session,
    delete_template, get_template_by_id,
)

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
from core.ui_helpers import styled_tabs
import streamlit_antd_components as sac

active_tab = styled_tabs(
    ["Browse Templates", "Load Template"],
    icons=["folder2-open", "download"],
    key="tmpl_tabs",
)

# ---------------------------------------------------------------------------
# Tab 1: Browse Templates
# ---------------------------------------------------------------------------
if active_tab == "Browse Templates":
    st.subheader("All Templates")

    col_f1, col_f2 = st.columns(2)
    with col_f1:
        filter_sku = st.text_input("Filter by SKU", key="browse_sku_filter")
    with col_f2:
        filter_user = st.text_input("Filter by User", key="browse_user_filter")

    templates_df = list_templates(
        sku=filter_sku or None,
        user=filter_user or None,
    )

    if templates_df.empty:
        st.info("No templates found. Save your first template from the **Export & Save** page.")
    else:
        # Format for display
        display_cols = []
        for _, row in templates_df.iterrows():
            display_cols.append({
                "ID": row["id"],
                "SKU": row["sku"],
                "Template Name": row.get("template_name", ""),
                "MSRP": f"${row.get('msrp', 0):.2f}",
                "FOB": f"${row.get('fob', 0):.2f}",
                "Created By": row.get("created_by", ""),
                "Updated": str(row.get("updated_at", ""))[:19],
                "Notes": str(row.get("notes", "") or "")[:80],
            })

        st.dataframe(
            pd.DataFrame(display_cols),
            use_container_width=True,
            hide_index=True,
        )
        st.caption(f"{len(templates_df)} template(s)")

        # Detail view
        st.divider()
        st.subheader("Template Detail")
        detail_id = st.number_input("Enter Template ID to view details", min_value=1, step=1, key="detail_id")

        if st.button("View Detail", key="btn_detail"):
            data = get_template_by_id(int(detail_id))
            if data is None:
                st.warning(f"Template {detail_id} not found.")
            else:
                master = data["master"]
                st.write(f"**{master.get('template_name', '')}** ({master['sku']})")
                st.write(f"Created by: {master.get('created_by', '')} | Updated: {master.get('updated_at', '')}")
                if master.get("notes"):
                    st.write(f"Notes: {master['notes']}")

                col_d1, col_d2 = st.columns(2)
                with col_d1:
                    st.write("**Inputs:**")
                    st.write(f"- MSRP: ${master.get('msrp', 0):.2f}")
                    st.write(f"- FOB: ${master.get('fob', 0):.2f}")
                    st.write(f"- Tariff: {master.get('tariff_rate', 0):.1f}%")
                    st.write(f"- Promo Mix: {master.get('promotion_mix', 0):.0f}%")
                with col_d2:
                    st.write("**Channel Mix:**")
                    for ch, pct in data["channel_mix"].items():
                        st.write(f"- {ch}: {pct:.0f}%")

                if not data["assumptions"].empty:
                    with st.expander("Assumption Snapshot"):
                        st.dataframe(data["assumptions"], use_container_width=True, hide_index=True)

        # Delete
        st.divider()
        del_id = st.number_input("Template ID to delete", min_value=1, step=1, key="del_id")
        if st.button("Delete Template", key="btn_delete"):
            try:
                delete_template(int(del_id))
                st.success(f"Template {del_id} deactivated.")
                st.rerun()
            except Exception as e:
                st.error(f"Delete failed: {e}")


# ---------------------------------------------------------------------------
# Tab 2: Load Template into Session
# ---------------------------------------------------------------------------
elif active_tab == "Load Template":
    st.subheader("Load a Template")
    st.caption("Loading a template will replace your current pricing inputs and channel mix.")

    # Show templates for current SKU first, then all
    current_sku = st.session_state.get("selected_sku")

    if current_sku:
        st.write(f"**Templates for current SKU ({current_sku}):**")
        sku_templates = list_templates(sku=current_sku)
        if sku_templates.empty:
            st.info(f"No templates for {current_sku}.")
        else:
            for _, row in sku_templates.iterrows():
                col_t1, col_t2, col_t3 = st.columns([3, 1, 1])
                with col_t1:
                    st.write(f"**{row.get('template_name', '')}** (ID: {row['id']})")
                    st.caption(
                        f"MSRP: ${row.get('msrp', 0):.2f} | FOB: ${row.get('fob', 0):.2f} | "
                        f"Updated: {str(row.get('updated_at', ''))[:19]}"
                    )
                with col_t2:
                    if row.get("notes"):
                        st.caption(str(row["notes"])[:60])
                with col_t3:
                    if st.button("Load", key=f"load_{row['id']}"):
                        session_data = load_template_to_session(int(row["id"]))
                        if session_data:
                            st.session_state.selected_sku = session_data["sku"]
                            st.session_state.user_inputs = session_data["user_inputs"]
                            # Merge channel mix (fill missing with 0)
                            new_mix = {ch: 0.0 for ch in CHANNELS}
                            for ch, pct in session_data["channel_mix"].items():
                                if ch in new_mix:
                                    new_mix[ch] = pct
                            st.session_state.channel_mix = new_mix
                            # Force re-resolve assumptions
                            st.session_state.resolved_assumptions = None
                            st.success(f"Loaded template: {session_data.get('template_name', '')}")
                            st.rerun()
                        else:
                            st.error("Failed to load template.")

    st.divider()
    st.write("**Load by Template ID:**")
    load_id = st.number_input("Template ID", min_value=1, step=1, key="load_by_id")
    if st.button("Load Template", key="btn_load_by_id"):
        session_data = load_template_to_session(int(load_id))
        if session_data:
            st.session_state.selected_sku = session_data["sku"]
            st.session_state.user_inputs = session_data["user_inputs"]
            new_mix = {ch: 0.0 for ch in CHANNELS}
            for ch, pct in session_data["channel_mix"].items():
                if ch in new_mix:
                    new_mix[ch] = pct
            st.session_state.channel_mix = new_mix
            st.session_state.resolved_assumptions = None
            st.success(f"Loaded template: {session_data.get('template_name', '')}")
            st.rerun()
        else:
            st.error(f"Template {load_id} not found.")
