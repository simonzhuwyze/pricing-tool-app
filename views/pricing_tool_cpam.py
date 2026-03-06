"""
CPAM Calculator Page - Full CPAM Waterfall Breakdown
Uses resolved assumptions from assumption_resolver (no hardcoded values).
Toggle between Full Price / Promo / Blended views.
"""

import streamlit as st
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.data_loader import CHANNELS
from core.cpam_engine import (
    UserInputs, calculate_channel_cpam, calculate_weighted_cpam,
)
from core.ui_helpers import styled_header, styled_divider, styled_metric_cards, styled_segmented
import streamlit_antd_components as sac

styled_header("CPAM Calculation Breakdown", "Full waterfall view of revenue, costs, and CPAM by channel.")

# Check prerequisites
selected_sku = st.session_state.get("selected_sku")
resolved = st.session_state.get("resolved_assumptions")

if not selected_sku or resolved is None:
    st.warning("Please select a product on the Pricing Tool page first.")
    st.page_link("views/pricing_tool_main.py", label="Go to Pricing Tool ->")
    st.stop()

user_inputs_dict = st.session_state.get("user_inputs", {})
promo_abs = user_inputs_dict.get("promo_absolute_values", {})
user_inputs = UserInputs(
    msrp=user_inputs_dict.get("msrp", 0),
    fob=user_inputs_dict.get("fob", 0),
    tariff_rate=user_inputs_dict.get("tariff_rate", 0),
    promotion_mix=user_inputs_dict.get("promotion_mix", 0),
    promo_percentage=user_inputs_dict.get("promo_percentage", 0),
    promo_absolute_values=promo_abs if isinstance(promo_abs, dict) else {},
)

st.caption(
    f"**{selected_sku}** - {resolved.product_info.product_name}  |  "
    f"MSRP: ${user_inputs.msrp:.2f}  |  FOB: ${user_inputs.fob:.2f}  |  "
    f"Tariff: {user_inputs.tariff_rate:.1f}%  |  Promo Mix: {user_inputs.promotion_mix:.0f}%"
)

# ---------------------------------------------------------------------------
# View mode toggle
# ---------------------------------------------------------------------------
view_mode = styled_segmented(
    ["Blended", "Full Price", "Promo"],
    icons=["shuffle", "cash-stack", "percent"],
    key="cpam_detail_view_mode",
)

# Calculate for all channels using RESOLVED assumptions
channel_mix_values = st.session_state.get("channel_mix", {})
channel_results = []

for ch in CHANNELS:
    ca = resolved.channel_assumptions[ch]
    ca.channel_mix = channel_mix_values.get(ch, 0.0) / 100.0
    result = calculate_channel_cpam(user_inputs, resolved.product_info, ca, resolved.static_assumptions)
    channel_results.append(result)

weighted = calculate_weighted_cpam(channel_results)

# ---------------------------------------------------------------------------
# Build CPAM waterfall table based on view mode
# Each row: (label, level, field, format_type)
# format_type: "pct" = percentage, "$" = dollar, "mix" = mix percentage
# ---------------------------------------------------------------------------

# Common rows shared across all views
common_top_rows = [
    ("Unit Sales Mix %",                       "L1",   "channel_mix",            "mix"),
]

# Revenue section varies by view
revenue_rows_promo = [
    ("Net Revenue",                             "L1",   "net_revenue",            "$"),
    ("  1.1 Gross Product Price (MSRP)",        "L2",   "msrp",                   "$"),
    ("  1.2 Shipping Revenue",                  "L2",   "shipping_revenue",       "$"),
    ("  1.3 Retail Margin",                     "L2",   "retail_margin",          "$"),
    ("  1.4 Promotion",                         "L2",   "promotion",              "$"),
    ("  1.5 Retail Discounts & Allowances",     "L2",   "retail_discounts",       "$"),
    ("  1.6 Other Contra Revenue",              "L2",   "other_contra_revenue",   "$"),
    ("    Chargebacks",                         "L3",   "chargebacks",            "$"),
    ("    Returns & Replacements",              "L3",   "returns_replacements",   "$"),
]

revenue_rows_fullprice = [
    ("Net Revenue (Full Price)",                "L1",   "net_revenue_fullprice",  "$"),
    ("  1.1 Gross Product Price (MSRP)",        "L2",   "msrp",                   "$"),
    ("  1.2 Shipping Revenue",                  "L2",   "shipping_revenue",       "$"),
    ("  1.3 Retail Margin",                     "L2",   "retail_margin",          "$"),
    ("  1.4 Promotion",                         "L2",   "_zero",                  "$"),
    ("  1.5 Retail Discounts & Allowances",     "L2",   "retail_discounts",       "$"),
    ("  1.6 Other Contra Revenue (Full Price)", "L2",   "_ocr_fullprice",         "$"),
    ("    Chargebacks",                         "L3",   "chargebacks",            "$"),
    ("    Returns (Full Price)",                "L3",   "_returns_fullprice",     "$"),
]

revenue_rows_blended = [
    ("Net Revenue (Blended)",                   "L1",   "net_revenue_blended",    "$"),
    ("  1.1 Gross Product Price (MSRP)",        "L2",   "msrp",                   "$"),
    ("  1.2 Shipping Revenue",                  "L2",   "shipping_revenue",       "$"),
    ("  1.3 Retail Margin",                     "L2",   "retail_margin",          "$"),
    ("  1.4 Promotion (Blended)",               "L2",   "_promo_blended",         "$"),
    ("  1.5 Retail Discounts & Allowances",     "L2",   "retail_discounts",       "$"),
    ("  1.6 Other Contra Revenue (Blended)",    "L2",   "_ocr_blended",           "$"),
    ("    Chargebacks",                         "L3",   "chargebacks",            "$"),
    ("    Returns (Blended)",                   "L3",   "_returns_blended",       "$"),
]

# COGS section (same for all views — costs don't change with promo)
cogs_rows = [
    ("Cost of Goods",                           "L1",   "cost_of_goods",          "$"),
    ("  2.1 Landed Cost",                       "L2",   "landed_cost",            "$"),
    ("    FOB",                                 "L3",   "fob",                    "$"),
    ("    Inbound Freight & Insurance",         "L3",   "inbound_freight",        "$"),
    ("    Tariff",                              "L3",   "tariff",                 "$"),
    ("  2.2 Shipping & Logistics Cost",         "L2",   "shipping_cost",          "$"),
    ("    Outbound Shipping",                   "L3",   "outbound_shipping",      "$"),
    ("    Warehouse Storage & Handling",         "L3",   "warehouse_storage",      "$"),
    ("  2.3 Other Costs",                       "L2",   "other_cost",             "$"),
    ("    Cloud Cost (Lifetime)",               "L3",   "cloud_cost_lifetime",    "$"),
    ("    Excess, Obsolete & Shrinkage",        "L3",   "eos",                    "$"),
    ("    UID",                                 "L3",   "uid",                    "$"),
    ("    Royalties",                           "L3",   "royalties",              "$"),
]

# Margin & S&M vary by view
sm_rows_promo = [
    ("Gross Margin",                            "L1",   "gross_profit",           "$"),
    ("Gross Margin %",                          "L1",   "gross_margin_pct",       "pct"),
    ("Sales & Marketing",                       "L1",   "sales_marketing_expenses", "$"),
    ("  3.1 Customer Service",                  "L2",   "customer_service",       "$"),
    ("  3.2 Credit-card & Platform Fees",       "L2",   "cc_platform_fees",       "$"),
    ("  3.3 Marketing",                         "L2",   "marketing",              "$"),
    ("CPAM $ (Promo)",                          "CPAM", "cpam_dollar",            "$"),
    ("CPAM % (Promo)",                          "CPAM", "cpam_pct",              "pct"),
]

sm_rows_fullprice = [
    ("Gross Margin (Full Price)",               "L1",   "_gm_fullprice",          "$"),
    ("Gross Margin % (Full Price)",             "L1",   "_gm_pct_fullprice",      "pct"),
    ("Sales & Marketing (Full Price)",          "L1",   "_sm_fullprice",          "$"),
    ("  3.1 Customer Service (Full Price)",     "L2",   "_cs_fullprice",          "$"),
    ("  3.2 Credit-card & Platform Fees",       "L2",   "_cc_fullprice",          "$"),
    ("  3.3 Marketing",                         "L2",   "marketing",              "$"),
    ("CPAM $ (Full Price)",                     "CPAM", "cpam_dollar_full",       "$"),
    ("CPAM % (Full Price)",                     "CPAM", "cpam_pct_full",         "pct"),
]

sm_rows_blended = [
    ("Gross Margin (Blended)",                  "L1",   "_gm_blended",            "$"),
    ("Gross Margin % (Blended)",                "L1",   "_gm_pct_blended",        "pct"),
    ("Sales & Marketing (Blended)",             "L1",   "_sm_blended",            "$"),
    ("  3.1 Customer Service (Blended)",        "L2",   "_cs_blended",            "$"),
    ("  3.2 Credit-card & Platform Fees (Blended)", "L2", "_cc_blended",          "$"),
    ("  3.3 Marketing",                         "L2",   "marketing",              "$"),
    ("CPAM $ (Blended)",                        "CPAM", "cpam_dollar_blended",    "$"),
    ("CPAM % (Blended)",                        "CPAM", "cpam_pct_blended",      "pct"),
]

# Assemble waterfall rows based on view mode
if view_mode == "Full Price":
    waterfall_rows = common_top_rows + revenue_rows_fullprice + cogs_rows + sm_rows_fullprice
    label_suffix = "(Full Price)"
elif view_mode == "Promo":
    waterfall_rows = common_top_rows + revenue_rows_promo + cogs_rows + sm_rows_promo
    label_suffix = "(Promo)"
else:  # Blended
    waterfall_rows = common_top_rows + revenue_rows_blended + cogs_rows + sm_rows_blended
    label_suffix = "(Blended)"

# ---------------------------------------------------------------------------
# Compute derived fields not directly on CPAMBreakdown
# ---------------------------------------------------------------------------
def get_field_value(r, field):
    """Get a value from the result, including computed virtual fields."""
    if field == "_zero":
        return 0.0

    # Full-price derived fields
    if field == "_returns_fullprice":
        # Returns at full price = -pre_promo_retailer_price * return_rate
        # This is already embedded in net_revenue_fullprice calculation
        ca = resolved.channel_assumptions.get(r.channel)
        if ca:
            return -r.pre_promo_retailer_price * ca.return_rate
        return 0.0
    if field == "_ocr_fullprice":
        # Other Contra Revenue Full Price = chargebacks + returns at full price
        ca = resolved.channel_assumptions.get(r.channel)
        if ca:
            returns_fp = -r.pre_promo_retailer_price * ca.return_rate
            return r.chargebacks + returns_fp
        return r.chargebacks
    if field == "_gm_fullprice":
        return r.net_revenue_fullprice - r.cost_of_goods
    if field == "_gm_pct_fullprice":
        return (r.net_revenue_fullprice - r.cost_of_goods) / r.net_revenue_fullprice if r.net_revenue_fullprice != 0 else 0
    if field == "_cs_fullprice":
        ca = resolved.channel_assumptions.get(r.channel)
        if ca:
            return ca.customer_service_rate * r.pre_promo_retailer_price
        return 0.0
    if field == "_cc_fullprice":
        # Full price: cc_fee on MSRP (no promo discount on end user price)
        ca = resolved.channel_assumptions.get(r.channel)
        if ca:
            val = ca.cc_fee_rate * r.msrp
            if r.channel == "Amazon 3P":
                val += 0.99
            return val
        return 0.0
    if field == "_sm_fullprice":
        cs = get_field_value(r, "_cs_fullprice")
        cc = get_field_value(r, "_cc_fullprice")
        return cs + cc + r.marketing

    # Blended derived fields
    promotion_mix = user_inputs.promotion_mix / 100.0
    if field == "_promo_blended":
        return r.promotion * promotion_mix
    if field == "_returns_blended":
        ca = resolved.channel_assumptions.get(r.channel)
        if ca:
            returns_fp = -r.pre_promo_retailer_price * ca.return_rate
            returns_promo = r.returns_replacements
            return returns_fp * (1 - promotion_mix) + returns_promo * promotion_mix
        return r.returns_replacements * promotion_mix
    if field == "_ocr_blended":
        returns_b = get_field_value(r, "_returns_blended")
        return r.chargebacks + returns_b
    if field == "_gm_blended":
        return r.net_revenue_blended - r.cost_of_goods
    if field == "_gm_pct_blended":
        return (r.net_revenue_blended - r.cost_of_goods) / r.net_revenue_blended if r.net_revenue_blended != 0 else 0
    if field == "_cs_blended":
        ca = resolved.channel_assumptions.get(r.channel)
        if ca:
            cs_fp = ca.customer_service_rate * r.pre_promo_retailer_price
            cs_promo = r.customer_service
            return cs_fp * (1 - promotion_mix) + cs_promo * promotion_mix
        return r.customer_service
    if field == "_cc_blended":
        ca = resolved.channel_assumptions.get(r.channel)
        if ca:
            cc_fp = ca.cc_fee_rate * r.msrp
            if r.channel == "Amazon 3P":
                cc_fp += 0.99
            cc_promo = r.cc_platform_fees
            return cc_fp * (1 - promotion_mix) + cc_promo * promotion_mix
        return r.cc_platform_fees
    if field == "_sm_blended":
        cs = get_field_value(r, "_cs_blended")
        cc = get_field_value(r, "_cc_blended")
        return cs + cc + r.marketing

    # Default: read directly from result
    return getattr(r, field, 0)


# For weighted average, handle virtual fields
def get_weighted_field_value(field):
    """Get weighted average value for virtual fields."""
    if not weighted:
        return 0.0

    # For directly available fields, just read from weighted
    if not field.startswith("_"):
        return getattr(weighted, field, 0)

    # For virtual fields, compute weighted average across active channels
    active = [r for r in channel_results if r.channel_mix > 0]
    if not active:
        return 0.0
    total_mix = sum(r.channel_mix for r in active)
    if total_mix == 0:
        return 0.0

    weighted_sum = sum(get_field_value(r, field) * r.channel_mix for r in active)
    return weighted_sum / total_mix


# Filter to active channels or show all
active_channels = [r for r in channel_results if r.channel_mix > 0]
if not active_channels:
    active_channels = channel_results

has_weighted = weighted and any(r.channel_mix > 0 for r in channel_results)

# ---------------------------------------------------------------------------
# Build pre-formatted table (strings, not raw floats)
# ---------------------------------------------------------------------------
def fmt_val(val, fmt_type):
    """Format a value based on its type."""
    if fmt_type == "pct":
        return f"{val:.1%}"
    elif fmt_type == "mix":
        return f"{val * 100:.0f}%" if val > 0 else "-"
    else:  # "$"
        return f"${val:.2f}"


table_data = {"Metric": []}
for r in active_channels:
    table_data[r.channel] = []
if has_weighted:
    table_data["Weighted Avg"] = []

levels = []
for label, level, field, fmt_type in waterfall_rows:
    table_data["Metric"].append(label)
    levels.append(level)
    for r in active_channels:
        val = get_field_value(r, field)
        table_data[r.channel].append(fmt_val(val, fmt_type))
    if has_weighted:
        val = get_weighted_field_value(field)
        table_data["Weighted Avg"].append(fmt_val(val, fmt_type))

df = pd.DataFrame(table_data)
df["_level"] = levels


# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------
def style_waterfall(row):
    level = df.at[row.name, "_level"]
    n = len(row)
    if level == "L1":
        return ["background-color: #F0F2F6; font-weight: bold; border-bottom: 1px solid #ddd"] * n
    elif level == "CPAM":
        return ["background-color: #D5F5F0; font-weight: bold; color: #0D8A7B; border-bottom: 1px solid #0D8A7B"] * n
    elif level == "L2":
        return ["padding-left: 20px"] * n
    else:  # L3
        return ["padding-left: 40px; color: #666"] * n


display_df = df.drop(columns=["_level"])
styled = display_df.style.apply(style_waterfall, axis=1)

st.dataframe(styled, use_container_width=True, hide_index=True, height=1200)

# ---------------------------------------------------------------------------
# Key metrics cards
# ---------------------------------------------------------------------------
styled_divider(label="Key Metrics", icon="speedometer2")

if has_weighted:
    if view_mode == "Full Price":
        cpam_d = weighted.cpam_dollar_full
        cpam_p = weighted.cpam_pct_full
        nr = weighted.net_revenue_fullprice
    elif view_mode == "Promo":
        cpam_d = weighted.cpam_dollar
        cpam_p = weighted.cpam_pct
        nr = weighted.net_revenue
    else:
        cpam_d = weighted.cpam_dollar_blended
        cpam_p = weighted.cpam_pct_blended
        nr = weighted.net_revenue_blended

    gm = (nr - weighted.cost_of_goods) / nr if nr != 0 else 0

    col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
    with col_m1:
        st.metric(f"CPAM $ {label_suffix}", f"${cpam_d:.2f}")
    with col_m2:
        st.metric(f"CPAM % {label_suffix}", f"{cpam_p:.1%}")
    with col_m3:
        st.metric(f"Net Revenue {label_suffix}", f"${nr:.2f}")
    with col_m4:
        st.metric("Gross Margin", f"{gm:.1%}")
    with col_m5:
        st.metric("PO Price (Avg)", f"${weighted.po_price:.2f}")

    styled_metric_cards()

# ---------------------------------------------------------------------------
# Per-Channel Summary
# ---------------------------------------------------------------------------
styled_divider(label="Per-Channel Summary", icon="table")

# Map view mode to fields for summary table
if view_mode == "Full Price":
    cpam_dollar_field = "cpam_dollar_full"
    cpam_pct_field = "cpam_pct_full"
    rev_field = "net_revenue_fullprice"
elif view_mode == "Promo":
    cpam_dollar_field = "cpam_dollar"
    cpam_pct_field = "cpam_pct"
    rev_field = "net_revenue"
else:
    cpam_dollar_field = "cpam_dollar_blended"
    cpam_pct_field = "cpam_pct_blended"
    rev_field = "net_revenue_blended"

metrics_data = []
for r in active_channels:
    nr = getattr(r, rev_field, 0)
    gm = (nr - r.cost_of_goods) / nr if nr != 0 else 0
    metrics_data.append({
        "Channel": r.channel,
        "Mix %": f"{r.channel_mix * 100:.0f}%" if r.channel_mix > 0 else "-",
        "PO Price": f"${r.po_price:.2f}",
        f"Net Revenue {label_suffix}": f"${nr:.2f}",
        "COGS": f"${r.cost_of_goods:.2f}",
        "Gross Margin": f"{gm:.1%}",
        f"CPAM $ {label_suffix}": f"${getattr(r, cpam_dollar_field, 0):.2f}",
        f"CPAM % {label_suffix}": f"{getattr(r, cpam_pct_field, 0):.1%}",
    })

if has_weighted:
    nr_w = getattr(weighted, rev_field, 0)
    gm_w = (nr_w - weighted.cost_of_goods) / nr_w if nr_w != 0 else 0
    metrics_data.append({
        "Channel": "Weighted Avg",
        "Mix %": f"{weighted.channel_mix * 100:.0f}%",
        "PO Price": f"${weighted.po_price:.2f}",
        f"Net Revenue {label_suffix}": f"${nr_w:.2f}",
        "COGS": f"${weighted.cost_of_goods:.2f}",
        "Gross Margin": f"{gm_w:.1%}",
        f"CPAM $ {label_suffix}": f"${getattr(weighted, cpam_dollar_field, 0):.2f}",
        f"CPAM % {label_suffix}": f"{getattr(weighted, cpam_pct_field, 0):.1%}",
    })

st.dataframe(pd.DataFrame(metrics_data), use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# Cross-view comparison (always show all three CPAM types for quick reference)
# ---------------------------------------------------------------------------
styled_divider(label="Cross-View Comparison", icon="columns-gap")
st.caption("Quick reference: all three CPAM views side-by-side")

if has_weighted:
    comp_cols = st.columns(3)
    with comp_cols[0]:
        st.metric("Full Price CPAM $", f"${weighted.cpam_dollar_full:.2f}")
        st.caption(f"CPAM %: {weighted.cpam_pct_full:.1%}")
    with comp_cols[1]:
        st.metric("Promo CPAM $", f"${weighted.cpam_dollar:.2f}")
        st.caption(f"CPAM %: {weighted.cpam_pct:.1%}")
    with comp_cols[2]:
        st.metric("Blended CPAM $", f"${weighted.cpam_dollar_blended:.2f}")
        st.caption(f"CPAM %: {weighted.cpam_pct_blended:.1%}")
else:
    comp_data = []
    for r in active_channels:
        comp_data.append({
            "Channel": r.channel,
            "Full Price CPAM $": f"${r.cpam_dollar_full:.2f}",
            "Promo CPAM $": f"${r.cpam_dollar:.2f}",
            "Blended CPAM $": f"${r.cpam_dollar_blended:.2f}",
        })
    st.dataframe(pd.DataFrame(comp_data), use_container_width=True, hide_index=True)
