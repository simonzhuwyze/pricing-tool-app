"""
Pricing Tool - Main Page
Product selection -> Load/Create session -> Key inputs -> Promo settings -> CPAM Summary
"""

import streamlit as st
import sys
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.data_loader import CHANNELS
from core.cpam_engine import (
    UserInputs, calculate_channel_cpam, calculate_weighted_cpam,
)
from core.assumption_resolver import resolve_all_assumptions, clear_cache
from core.ui_helpers import styled_header, styled_divider, styled_metric_cards, styled_segmented



# ---------------------------------------------------------------------------
# Load product list (from Azure SQL)
# ---------------------------------------------------------------------------
@st.cache_data(ttl=300)
def _load_products():
    from core.database import get_sqlalchemy_engine
    engine = get_sqlalchemy_engine()
    df = pd.read_sql_table("cache_product_directory", engine)
    # Normalize column names for compatibility
    col_map = {}
    for c in df.columns:
        cl = c.lower()
        if cl == "sku": col_map[c] = "SKU"
        elif cl == "product_name": col_map[c] = "Product Name"
        elif cl == "reference_sku": col_map[c] = "Reference SKU"
        elif cl == "default_msrp": col_map[c] = "Default MSRP"
        elif cl == "default_fob": col_map[c] = "Default FOB"
        elif cl == "default_tariff_rate": col_map[c] = "Default Tariff Rate"
    return df.rename(columns=col_map)


products_df = _load_products()

# ---------------------------------------------------------------------------
# Title
# ---------------------------------------------------------------------------
styled_header("Pricing Tool", "Select a product, configure inputs, and calculate CPAM across all channels.")

# ---------------------------------------------------------------------------
# 1. Product Selection
# ---------------------------------------------------------------------------
st.subheader("1. Select Product")

if products_df.empty:
    st.error("No products found. Check data/reference data/Product Directory.csv")
    st.stop()

# Build display options: "SKU - Product Name"
products_df["display"] = products_df["SKU"] + " - " + products_df["Product Name"].fillna("")
options = [""] + products_df["display"].tolist()

# Determine default index
default_idx = 0
if st.session_state.selected_sku:
    match = products_df[products_df["SKU"] == st.session_state.selected_sku]
    if not match.empty:
        display_val = match.iloc[0]["display"]
        if display_val in options:
            default_idx = options.index(display_val)

selected_display = st.selectbox(
    "Product",
    options,
    index=default_idx,
    placeholder="Choose a product...",
)

if not selected_display:
    st.info("Please select a product to begin.")
    st.stop()

# Extract SKU from selection
selected_sku = selected_display.split(" - ")[0].strip()
prod_row = products_df[products_df["SKU"] == selected_sku].iloc[0]

# Update session state
st.session_state.selected_sku = selected_sku

# Show product info
col_info1, col_info2, col_info3 = st.columns(3)
with col_info1:
    st.metric("Product", prod_row.get("Product Name", "N/A"))
with col_info2:
    ref = prod_row.get("Reference SKU", "")
    st.metric("Reference SKU", ref if pd.notna(ref) and ref else chr(8212))
with col_info3:
    preload = prod_row.get("Preload", "")
    st.metric("Type", "Existing" if str(preload) == "1" else "New Product")

# ---------------------------------------------------------------------------
# 2. Resolve Assumptions
# ---------------------------------------------------------------------------
# Auto-resolve when SKU changes
if (st.session_state.resolved_assumptions is None or
        st.session_state.resolved_assumptions.sku != selected_sku):
    with st.spinner(f"Loading assumptions for {selected_sku}..."):
        clear_cache()
        resolved = resolve_all_assumptions(selected_sku)
        st.session_state.resolved_assumptions = resolved

        # Set default inputs from product directory
        ui = st.session_state.user_inputs
        if ui.get("msrp", 0) == 0:
            ui["msrp"] = float(prod_row.get("Default MSRP", 0) or 0)
        if ui.get("fob", 0) == 0:
            ui["fob"] = float(prod_row.get("Default FOB", 0) or 0)
        if ui.get("tariff_rate", 0) == 0:
            ui["tariff_rate"] = float(prod_row.get("Default Tariff Rate", 0) or 0) * 100

resolved = st.session_state.resolved_assumptions

# Show resolved product info
pi = resolved.product_info
if pi.product_group or pi.product_line:
    st.caption(f"Product Group: **{pi.product_group}** | Product Line: **{pi.product_line}**"
               + (f" | (via Reference SKU: {pi.reference_sku})" if not pi.product_group else ""))

# ---------------------------------------------------------------------------
# 3. Key Inputs
# ---------------------------------------------------------------------------
styled_divider(label="Pricing Inputs", icon="currency-dollar")

col1, col2, col3 = st.columns(3)

with col1:
    msrp = st.number_input(
        "MSRP ($)",
        min_value=0.0,
        value=float(st.session_state.user_inputs.get("msrp", 0)),
        step=1.0,
        format="%.2f",
        key="input_msrp",
    )
    st.session_state.user_inputs["msrp"] = msrp

with col2:
    fob = st.number_input(
        "FOB ($)",
        min_value=0.0,
        value=float(st.session_state.user_inputs.get("fob", 0)),
        step=1.0,
        format="%.2f",
        key="input_fob",
    )
    st.session_state.user_inputs["fob"] = fob

with col3:
    tariff = st.number_input(
        "Tariff Rate (%)",
        min_value=0.0,
        max_value=100.0,
        value=float(st.session_state.user_inputs.get("tariff_rate", 0)),
        step=0.5,
        format="%.1f",
        key="input_tariff",
    )
    st.session_state.user_inputs["tariff_rate"] = tariff

# Validate
if msrp == 0:
    st.warning("MSRP is $0.00. Enter a value to calculate CPAM.")
    st.stop()

# ---------------------------------------------------------------------------
# 4. Promotion Settings
# ---------------------------------------------------------------------------
styled_divider(label="Promotion Settings", icon="tag-fill")
st.caption(
    "**Promo Mix** = % of units sold under promotion.  "
    "**Blended CPAM** = Full Price CPAM x (1 - Promo Mix) + Promo CPAM x Promo Mix"
)

col_p1, col_p2, col_p3 = st.columns(3)

with col_p1:
    promo_mix = st.number_input(
        "Promo Mix (% units under promo)",
        min_value=0.0,
        max_value=100.0,
        value=float(st.session_state.user_inputs.get("promotion_mix", 0)),
        step=5.0,
        format="%.0f",
        key="input_promo_mix",
    )
    st.session_state.user_inputs["promotion_mix"] = promo_mix

with col_p2:
    promo_pct = st.number_input(
        "Quick Promo % (discount off MSRP)",
        min_value=0.0,
        max_value=100.0,
        value=float(st.session_state.user_inputs.get("promo_percentage", 0)),
        step=5.0,
        format="%.0f",
        key="input_promo_pct",
        help="Quick promo discount % applied to all channels. Set 0 to use per-channel promo $ below.",
    )
    st.session_state.user_inputs["promo_percentage"] = promo_pct

with col_p3:
    if promo_pct > 0:
        promo_dollar_preview = msrp * (promo_pct / 100)
        st.metric("Promo $ Preview", f"-${promo_dollar_preview:.2f}")
    else:
        st.metric("Promo Mode", "Per-channel $" if promo_mix > 0 else "No promo")

# Per-channel promo $ (only if promo_pct == 0 and promo_mix > 0)
promo_abs = st.session_state.user_inputs.get("promo_absolute_values", {})
if promo_pct == 0 and promo_mix > 0:
    with st.expander("Per-Channel Promo $ (optional)", expanded=False):
        st.caption("Set absolute promo $ deduction per channel. Leave 0 for no promo on that channel.")
        promo_cols = st.columns(4)
        new_promo_abs = {}
        for i, ch in enumerate(CHANNELS):
            with promo_cols[i % 4]:
                new_promo_abs[ch] = st.number_input(
                    ch,
                    min_value=0.0,
                    value=float(promo_abs.get(ch, 0.0)),
                    step=1.0,
                    format="%.2f",
                    key=f"promo_abs_{ch}",
                )
        st.session_state.user_inputs["promo_absolute_values"] = new_promo_abs
        promo_abs = new_promo_abs

# ---------------------------------------------------------------------------
# 5. CPAM Summary Calculation
# ---------------------------------------------------------------------------
styled_divider(label="CPAM Summary", icon="bar-chart-fill")

# Build UserInputs
user_inputs = UserInputs(
    msrp=msrp,
    fob=fob,
    tariff_rate=tariff,
    promotion_mix=promo_mix,
    promo_percentage=promo_pct,
    promo_absolute_values=promo_abs if isinstance(promo_abs, dict) else {},
)

# Calculate per-channel
channel_results = []
for ch in CHANNELS:
    ca = resolved.channel_assumptions[ch]
    ca.channel_mix = st.session_state.channel_mix.get(ch, 0.0) / 100.0

    result = calculate_channel_cpam(
        inputs=user_inputs,
        product=resolved.product_info,
        channel_assumptions=ca,
        static=resolved.static_assumptions,
    )
    channel_results.append(result)

# Weighted average
weighted = calculate_weighted_cpam(channel_results)

# View mode toggle
view_mode = styled_segmented(
    ["Blended", "Full Price", "Promo"],
    icons=["shuffle", "cash-stack", "percent"],
    key="cpam_view_mode",
)

# Map view mode to fields
if view_mode == "Full Price":
    cpam_dollar_field = "cpam_dollar_full"
    cpam_pct_field = "cpam_pct_full"
    rev_field = "net_revenue_fullprice"
    label_suffix = "(Full Price)"
elif view_mode == "Promo":
    cpam_dollar_field = "cpam_dollar"
    cpam_pct_field = "cpam_pct"
    rev_field = "net_revenue"
    label_suffix = "(Promo)"
else:
    cpam_dollar_field = "cpam_dollar_blended"
    cpam_pct_field = "cpam_pct_blended"
    rev_field = "net_revenue_blended"
    label_suffix = "(Blended)"

# Build summary table
rows = []
for r in channel_results:
    mix_pct = r.channel_mix * 100
    if mix_pct > 0 or r.net_revenue != 0:
        rows.append({
            "Channel": r.channel,
            "Mix %": f"{mix_pct:.0f}%" if mix_pct > 0 else "-",
            "PO Price": f"${r.po_price:.2f}",
            "Net Revenue": f"${getattr(r, rev_field, 0):.2f}",
            "COGS": f"${r.cost_of_goods:.2f}",
            "Gross Margin": f"{r.gross_margin_pct:.1%}",
            "S&M": f"${r.sales_marketing_expenses:.2f}",
            f"CPAM $ {label_suffix}": f"${getattr(r, cpam_dollar_field, 0):.2f}",
            f"CPAM % {label_suffix}": f"{getattr(r, cpam_pct_field, 0):.1%}",
        })

if weighted:
    rows.append({
        "Channel": "Weighted Avg",
        "Mix %": f"{weighted.channel_mix * 100:.0f}%",
        "PO Price": f"${weighted.po_price:.2f}",
        "Net Revenue": f"${getattr(weighted, rev_field, 0):.2f}",
        "COGS": f"${weighted.cost_of_goods:.2f}",
        "Gross Margin": f"{weighted.gross_margin_pct:.1%}",
        "S&M": f"${weighted.sales_marketing_expenses:.2f}",
        f"CPAM $ {label_suffix}": f"${getattr(weighted, cpam_dollar_field, 0):.2f}",
        f"CPAM % {label_suffix}": f"{getattr(weighted, cpam_pct_field, 0):.1%}",
    })

if rows:
    summary_df = pd.DataFrame(rows)
    st.dataframe(
        summary_df,
        use_container_width=True,
        hide_index=True,
        height=min(len(rows) * 35 + 40, 600),
    )

    # Key metrics
    if weighted:
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        with col_m1:
            st.metric(f"CPAM $ {label_suffix}",
                      f"${getattr(weighted, cpam_dollar_field, 0):.2f}")
        with col_m2:
            st.metric(f"CPAM % {label_suffix}",
                      f"{getattr(weighted, cpam_pct_field, 0):.1%}")
        with col_m3:
            st.metric("Full Price CPAM $", f"${weighted.cpam_dollar_full:.2f}")
        with col_m4:
            st.metric("Gross Margin", f"{weighted.gross_margin_pct:.1%}")
    styled_metric_cards()
else:
    st.info("Set channel mix percentages (Channel Mix page) to see the weighted CPAM summary.")
    # Still show per-channel results for all channels
    all_rows = []
    for r in channel_results:
        all_rows.append({
            "Channel": r.channel,
            "PO Price": f"${r.po_price:.2f}",
            "Net Revenue": f"${r.net_revenue:.2f}",
            f"CPAM $ {label_suffix}": f"${getattr(r, cpam_dollar_field, 0):.2f}",
            f"CPAM % {label_suffix}": f"{getattr(r, cpam_pct_field, 0):.1%}",
        })
    if all_rows:
        st.dataframe(pd.DataFrame(all_rows), use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# 6. Quick Links
# ---------------------------------------------------------------------------
styled_divider(label="Quick Links", icon="link-45deg")
link_cols = st.columns(3)
with link_cols[0]:
    st.page_link("pages/pricing_tool_cpam.py", label="CPAM Breakdown", icon="🧮")
with link_cols[1]:
    st.page_link("pages/pricing_tool_channel_mix.py", label="Channel Mix", icon="📊")
with link_cols[2]:
    st.page_link("pages/pricing_tool_assumptions.py", label="Assumptions", icon="📋")
