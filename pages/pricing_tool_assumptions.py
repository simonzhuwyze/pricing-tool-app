"""
Assumptions Loaded - Shows all assumptions used in current pricing session
with source attribution (cache, ref_sku, default).
Filterable by Category (which assumption table the data comes from).
"""

import streamlit as st
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.assumption_resolver import resolution_log_to_df
from core.ui_helpers import styled_header

styled_header("Assumptions Loaded", "All assumptions used in current pricing session with source attribution.")

selected_sku = st.session_state.get("selected_sku")
resolved = st.session_state.get("resolved_assumptions")

if not selected_sku or resolved is None:
    st.warning("Please select a product on the Pricing Tool page first.")
    st.page_link("pages/pricing_tool_main.py", label="Go to Pricing Tool ->")
    st.stop()

st.caption(
    f"Product: **{selected_sku}** - {resolved.product_info.product_name}  |  "
    f"Reference SKU: **{resolved.reference_sku or chr(8212)}**"
)

# Product info
st.subheader("Product Classification")
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Product Group", resolved.product_info.product_group or chr(8212))
with col2:
    st.metric("Product Line", resolved.product_info.product_line or chr(8212))
with col3:
    st.metric("Reference SKU", resolved.reference_sku or chr(8212))

# Static Assumptions
st.subheader("Static Cost Assumptions")
sa = resolved.static_assumptions
static_data = [
    {"Item": "UID (Camera)", "Value": f"${sa.uid_cam:.2f}", "Unit": "per unit"},
    {"Item": "Royalties (Camera)", "Value": f"${sa.royalties_cam:.2f}", "Unit": "per unit"},
    {"Item": "Royalties (Bulb)", "Value": f"{sa.royalties_bulb_rate:.1%}", "Unit": "% of Net Rev"},
    {"Item": "Cloud Cost (Camera)", "Value": f"${sa.monthly_cloud_cost_cam:.2f}", "Unit": "per month"},
    {"Item": "Cloud Cost (Non-Cam)", "Value": f"${sa.monthly_cloud_cost_noncam:.2f}", "Unit": "per month"},
    {"Item": "EOS Rate", "Value": f"{sa.eos_rate:.1%}", "Unit": "% of Landed Cost"},
]
st.dataframe(pd.DataFrame(static_data), use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# Resolution log with CATEGORY mapping
# ---------------------------------------------------------------------------
st.subheader("All Resolved Assumptions")

# Map field_name -> Category (which assumption table it comes from)
FIELD_TO_CATEGORY = {
    "po_discount_rate": "Retail Margin",
    "return_rate": "Return Rate",
    "outbound_shipping": "Outbound Shipping",
    "inbound_freight": "Product Costs",
    "warehouse_storage": "Product Costs",
    "amazon_fba": "Product Costs",
    "expected_product_life": "Product Costs",
    "chargeback_rate": "Channel Terms",
    "total_discount_rate": "Channel Terms",
    "cc_fee_rate": "S&M Expenses",
    "customer_service_rate": "S&M Expenses",
    "marketing_rate": "S&M Expenses",
}

# Friendly display names for fields
FIELD_DISPLAY = {
    "po_discount_rate": "PO Discount Rate",
    "return_rate": "Return Rate",
    "outbound_shipping": "Outbound Shipping",
    "inbound_freight": "Inbound Freight",
    "warehouse_storage": "Warehouse Storage",
    "amazon_fba": "Amazon FBA Fee",
    "expected_product_life": "Expected Product Life",
    "chargeback_rate": "Chargeback Rate",
    "total_discount_rate": "Total Discount Rate",
    "cc_fee_rate": "CC & Platform Fee",
    "customer_service_rate": "Customer Service Rate",
    "marketing_rate": "Marketing Rate",
}

log_df = resolution_log_to_df(resolved.resolution_log)

if not log_df.empty:
    # Add Category and friendly names
    log_df["Category"] = log_df["Field"].map(FIELD_TO_CATEGORY).fillna("Other")
    log_df["Field"] = log_df["Field"].map(FIELD_DISPLAY).fillna(log_df["Field"])

    # Add source indicator
    def source_indicator(source):
        if source == "ref_sku":
            return "ref_sku"
        elif source == "default":
            return "default"
        else:
            return source

    log_df["Source"] = log_df["Source"].apply(source_indicator)

    # Format value based on category
    def format_value(row):
        val = row["Value"]
        cat = row["Category"]
        field = row["Field"]
        # Rate fields: display as percentage
        if cat in ("Retail Margin", "Return Rate", "Channel Terms", "S&M Expenses"):
            return f"{val:.2%}" if val != 0 else "0.00%"
        # Dollar fields
        elif cat in ("Outbound Shipping", "Product Costs"):
            if "Life" in field:
                return f"{val:.0f} mo" if val != 0 else "0"
            return f"${val:.2f}" if val != 0 else "$0.00"
        return f"{val:.4f}"

    log_df["Display Value"] = log_df.apply(format_value, axis=1)

    # Summary stats
    total = len(log_df)
    from_data = len(log_df[log_df["Source"] == "cache"])
    from_ref = len(log_df[log_df["Source"] == "ref_sku"])
    from_default = len(log_df[log_df["Source"] == "default"])

    col_s1, col_s2, col_s3, col_s4 = st.columns(4)
    with col_s1:
        st.metric("Total Fields", total)
    with col_s2:
        st.metric("From Data", from_data)
    with col_s3:
        st.metric("From Ref SKU", from_ref)
    with col_s4:
        st.metric("Default (0)", from_default)

    st.caption("Source: **cache** = from CSV/DB data  |  **ref_sku** = from Reference SKU fallback  |  **default** = no data (0)")

    # Filter controls - Category first (most useful), then Channel, then Source
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        category_filter = st.multiselect(
            "Filter by Category",
            options=sorted(log_df["Category"].unique()),
            default=[],
        )
    with col_f2:
        channel_filter = st.multiselect(
            "Filter by Channel",
            options=sorted(log_df["Channel"].unique()),
            default=[],
        )
    with col_f3:
        source_filter = st.multiselect(
            "Filter by Source",
            options=sorted(log_df["Source"].unique()),
            default=[],
        )

    filtered = log_df.copy()
    if category_filter:
        filtered = filtered[filtered["Category"].isin(category_filter)]
    if channel_filter:
        filtered = filtered[filtered["Channel"].isin(channel_filter)]
    if source_filter:
        filtered = filtered[filtered["Source"].isin(source_filter)]

    # Display table with Category, Channel, Field, Display Value, Source
    display_cols = ["Category", "Channel", "Field", "Display Value", "Source"]
    st.dataframe(
        filtered[display_cols].rename(columns={"Display Value": "Value"}),
        use_container_width=True,
        hide_index=True,
        height=600,
    )

    # Per-category summary tables (collapsible)
    st.divider()
    st.subheader("Summary by Category")

    for cat in sorted(log_df["Category"].unique()):
        cat_df = log_df[log_df["Category"] == cat]
        n_from_data = len(cat_df[cat_df["Source"] == "cache"])
        n_default = len(cat_df[cat_df["Source"] == "default"])
        n_ref = len(cat_df[cat_df["Source"] == "ref_sku"])

        coverage = f"{n_from_data}/{len(cat_df)}"
        with st.expander(f"{cat} ({coverage} from data)"):
            # Pivot: rows=Channel, cols=Field, values=Display Value
            pivot = cat_df.pivot_table(
                index="Channel", columns="Field", values="Display Value",
                aggfunc="first"
            )
            st.dataframe(pivot, use_container_width=True)
else:
    st.info("No resolution log available.")

# Links to assumption pages
st.divider()
st.subheader("Edit Assumptions")
col1, col2, col3 = st.columns(3)
with col1:
    st.page_link("pages/assumptions_retail_margin.py", label="Edit Retail Margin ->")
    st.page_link("pages/assumptions_return_rate.py", label="Edit Return Rate ->")
with col2:
    st.page_link("pages/assumptions_outbound_shipping.py", label="Edit Outbound Shipping ->")
    st.page_link("pages/assumptions_product_costs.py", label="Edit Product Costs ->")
with col3:
    st.page_link("pages/assumptions_finance.py", label="Edit Finance Assumptions ->")
