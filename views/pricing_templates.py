"""
Pricing Templates - Browse, view details, and manage saved pricing templates.
Load templates from the Pricing Tool main page. Save templates from Export & Save.
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

from core.ui_helpers import styled_header, styled_divider

styled_header(
    "Pricing Templates",
    "Browse, view details, and manage saved pricing templates. "
    "Load templates from the **Pricing Tool** page. Save from **Export & Save**.",
)

# Check DB
try:
    from core.database import get_sqlalchemy_engine
    engine = get_sqlalchemy_engine()
    pd.read_sql("SELECT 1", engine)
except Exception as e:
    st.error(f"Database not connected: {e}")
    st.info("Templates require Azure SQL. Go to **DB Admin** to configure.")
    st.stop()

from core.template_manager import (
    list_templates, delete_template, get_template_by_id,
)

# ---------------------------------------------------------------------------
# Filter & Load Templates
# ---------------------------------------------------------------------------
st.subheader("All Templates")

col_f1, col_f2 = st.columns(2)
with col_f1:
    filter_sku = st.text_input("Filter by SKU", key="browse_sku_filter")
with col_f2:
    filter_user = st.text_input("Filter by User", key="browse_user_filter")

try:
    templates_df = list_templates(
        sku=filter_sku or None,
        user=filter_user or None,
    )
except Exception as e:
    st.error(f"Failed to load templates: {e}")
    templates_df = pd.DataFrame()

if templates_df.empty:
    st.info("No templates found. Save your first template from the **Export & Save** page.")
    st.stop()

# Format for display table
display_rows = []
for _, row in templates_df.iterrows():
    display_rows.append({
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
    pd.DataFrame(display_rows),
    use_container_width=True,
    hide_index=True,
)
st.caption(f"{len(templates_df)} template(s)")

# ---------------------------------------------------------------------------
# Select Template (dropdown)
# ---------------------------------------------------------------------------
styled_divider(label="Template Detail", icon="info-circle-fill")

# Build selectbox options from loaded templates
_tmpl_labels = [""] + [
    f"ID {row['id']}  -  {row.get('template_name', '')}  ({row['sku']})"
    for _, row in templates_df.iterrows()
]
_tmpl_ids = [None] + templates_df["id"].tolist()

selected_idx = st.selectbox(
    "Select a template to view details",
    range(len(_tmpl_labels)),
    format_func=lambda i: _tmpl_labels[i] if _tmpl_labels[i] else "Choose a template...",
    key="tmpl_detail_select",
)

if selected_idx and selected_idx > 0:
    _sel_id = int(_tmpl_ids[selected_idx])
    data = get_template_by_id(_sel_id)

    if data is None:
        st.warning(f"Template {_sel_id} not found.")
    else:
        master = data["master"]
        st.write(f"**{master.get('template_name', '')}** ({master['sku']})")
        st.caption(
            f"Created by: {master.get('created_by', '')}  |  "
            f"Updated: {str(master.get('updated_at', ''))[:19]}"
        )
        if master.get("notes"):
            st.info(f"Notes: {master['notes']}")

        # Inputs preview
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            st.write("**Pricing Inputs:**")
            st.write(f"- MSRP: ${master.get('msrp', 0):.2f}")
            st.write(f"- FOB: ${master.get('fob', 0):.2f}")
            st.write(f"- Tariff Rate: {master.get('tariff_rate', 0):.1f}%")
            st.write(f"- Promo Mix: {master.get('promotion_mix', 0):.0f}%")
            st.write(f"- Promo %: {master.get('promo_percentage', 0):.0f}%")
        with col_d2:
            st.write("**Channel Mix:**")
            if data["channel_mix"]:
                for ch, pct in data["channel_mix"].items():
                    if pct > 0:
                        st.write(f"- {ch}: {pct:.0f}%")
                if not any(pct > 0 for pct in data["channel_mix"].values()):
                    st.caption("No channel mix set")
            else:
                st.caption("No channel mix set")

        # Assumption snapshot
        if not data["assumptions"].empty:
            with st.expander("Assumption Snapshot", expanded=False):
                st.dataframe(data["assumptions"], use_container_width=True, hide_index=True)

        # --- Delete ---
        styled_divider(label="Delete Template", icon="trash3-fill")
        st.warning(
            f"This will deactivate template **{master.get('template_name', '')}** "
            f"(ID: {_sel_id}, SKU: {master['sku']}). It will no longer appear in lists."
        )
        _confirm_name = st.text_input(
            f'Type "{master.get("template_name", "")}" to confirm deletion',
            key="tmpl_delete_confirm",
        )
        if st.button("Delete Template", key="btn_delete_tmpl"):
            if _confirm_name.strip() == master.get("template_name", "").strip():
                try:
                    delete_template(_sel_id)
                    st.success(f"Template '{master.get('template_name', '')}' deactivated.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Delete failed: {e}")
            else:
                st.error("Template name does not match. Deletion cancelled.")
