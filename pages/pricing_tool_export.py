"""
Export & Save - Generate PDF pricing analysis report and save pricing templates.
Select sections to include, then download as PDF. Save current session as a reusable template.
"""

import streamlit as st
import pandas as pd
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.data_loader import CHANNELS
from core.cpam_engine import (
    UserInputs, calculate_channel_cpam, calculate_weighted_cpam,
)
from core.assumption_resolver import resolution_log_to_df
from core.ui_helpers import styled_header, styled_divider, styled_segmented
from core.pdf_export import ExportConfig, generate_pricing_report
from core.template_manager import save_template


# =========================================================================
# Helper functions (defined before UI code)
# =========================================================================

def _build_waterfall(config, channel_results, weighted, user_inputs, view_mode, resolved):
    """Build waterfall table data matching cpam page structure."""
    promotion_mix = user_inputs.promotion_mix / 100.0

    def get_field_value(r, field_name):
        if field_name == "_zero":
            return 0.0
        if field_name == "_returns_fullprice":
            ca = resolved.channel_assumptions.get(r.channel)
            return -r.pre_promo_retailer_price * ca.return_rate if ca else 0.0
        if field_name == "_ocr_fullprice":
            ca = resolved.channel_assumptions.get(r.channel)
            rfp = -r.pre_promo_retailer_price * ca.return_rate if ca else 0.0
            return r.chargebacks + rfp
        if field_name == "_gm_fullprice":
            return r.net_revenue_fullprice - r.cost_of_goods
        if field_name == "_gm_pct_fullprice":
            return (r.net_revenue_fullprice - r.cost_of_goods) / r.net_revenue_fullprice if r.net_revenue_fullprice != 0 else 0
        if field_name == "_cs_fullprice":
            ca = resolved.channel_assumptions.get(r.channel)
            return ca.customer_service_rate * r.pre_promo_retailer_price if ca else 0.0
        if field_name == "_cc_fullprice":
            ca = resolved.channel_assumptions.get(r.channel)
            if ca:
                val = ca.cc_fee_rate * r.msrp
                if r.channel == "Amazon 3P":
                    val += 0.99
                return val
            return 0.0
        if field_name == "_sm_fullprice":
            return get_field_value(r, "_cs_fullprice") + get_field_value(r, "_cc_fullprice") + r.marketing
        if field_name == "_promo_blended":
            return r.promotion * promotion_mix
        if field_name == "_returns_blended":
            ca = resolved.channel_assumptions.get(r.channel)
            if ca:
                rfp = -r.pre_promo_retailer_price * ca.return_rate
                return rfp * (1 - promotion_mix) + r.returns_replacements * promotion_mix
            return r.returns_replacements * promotion_mix
        if field_name == "_ocr_blended":
            return r.chargebacks + get_field_value(r, "_returns_blended")
        if field_name == "_gm_blended":
            return r.net_revenue_blended - r.cost_of_goods
        if field_name == "_gm_pct_blended":
            return (r.net_revenue_blended - r.cost_of_goods) / r.net_revenue_blended if r.net_revenue_blended != 0 else 0
        if field_name == "_cs_blended":
            ca = resolved.channel_assumptions.get(r.channel)
            if ca:
                cs_fp = ca.customer_service_rate * r.pre_promo_retailer_price
                return cs_fp * (1 - promotion_mix) + r.customer_service * promotion_mix
            return r.customer_service
        if field_name == "_cc_blended":
            ca = resolved.channel_assumptions.get(r.channel)
            if ca:
                cc_fp = ca.cc_fee_rate * r.msrp
                if r.channel == "Amazon 3P":
                    cc_fp += 0.99
                return cc_fp * (1 - promotion_mix) + r.cc_platform_fees * promotion_mix
            return r.cc_platform_fees
        if field_name == "_sm_blended":
            return get_field_value(r, "_cs_blended") + get_field_value(r, "_cc_blended") + r.marketing
        return getattr(r, field_name, 0)

    def get_weighted_value(field_name):
        if not weighted:
            return 0.0
        if not field_name.startswith("_"):
            return getattr(weighted, field_name, 0)
        active = [r for r in channel_results if r.channel_mix > 0]
        if not active:
            return 0.0
        total_mix = sum(r.channel_mix for r in active)
        if total_mix == 0:
            return 0.0
        return sum(get_field_value(r, field_name) * r.channel_mix for r in active) / total_mix

    # Row definitions
    common_top = [("Unit Sales Mix %", "L1", "channel_mix", "mix")]
    rev_promo = [
        ("Net Revenue", "L1", "net_revenue", "$"),
        ("  1.1 MSRP", "L2", "msrp", "$"),
        ("  1.2 Shipping Revenue", "L2", "shipping_revenue", "$"),
        ("  1.3 Retail Margin", "L2", "retail_margin", "$"),
        ("  1.4 Promotion", "L2", "promotion", "$"),
        ("  1.5 Retail Discounts", "L2", "retail_discounts", "$"),
        ("  1.6 Other Contra Revenue", "L2", "other_contra_revenue", "$"),
        ("    Chargebacks", "L3", "chargebacks", "$"),
        ("    Returns & Replacements", "L3", "returns_replacements", "$"),
    ]
    rev_full = [
        ("Net Revenue (Full Price)", "L1", "net_revenue_fullprice", "$"),
        ("  1.1 MSRP", "L2", "msrp", "$"),
        ("  1.2 Shipping Revenue", "L2", "shipping_revenue", "$"),
        ("  1.3 Retail Margin", "L2", "retail_margin", "$"),
        ("  1.4 Promotion", "L2", "_zero", "$"),
        ("  1.5 Retail Discounts", "L2", "retail_discounts", "$"),
        ("  1.6 Other Contra Revenue", "L2", "_ocr_fullprice", "$"),
        ("    Chargebacks", "L3", "chargebacks", "$"),
        ("    Returns (Full Price)", "L3", "_returns_fullprice", "$"),
    ]
    rev_blended = [
        ("Net Revenue (Blended)", "L1", "net_revenue_blended", "$"),
        ("  1.1 MSRP", "L2", "msrp", "$"),
        ("  1.2 Shipping Revenue", "L2", "shipping_revenue", "$"),
        ("  1.3 Retail Margin", "L2", "retail_margin", "$"),
        ("  1.4 Promotion (Blended)", "L2", "_promo_blended", "$"),
        ("  1.5 Retail Discounts", "L2", "retail_discounts", "$"),
        ("  1.6 Other Contra Revenue", "L2", "_ocr_blended", "$"),
        ("    Chargebacks", "L3", "chargebacks", "$"),
        ("    Returns (Blended)", "L3", "_returns_blended", "$"),
    ]
    cogs = [
        ("Cost of Goods", "L1", "cost_of_goods", "$"),
        ("  2.1 Landed Cost", "L2", "landed_cost", "$"),
        ("    FOB", "L3", "fob", "$"),
        ("    Inbound Freight", "L3", "inbound_freight", "$"),
        ("    Tariff", "L3", "tariff", "$"),
        ("  2.2 Shipping Cost", "L2", "shipping_cost", "$"),
        ("    Outbound Shipping", "L3", "outbound_shipping", "$"),
        ("    Warehouse Storage", "L3", "warehouse_storage", "$"),
        ("  2.3 Other Costs", "L2", "other_cost", "$"),
        ("    Cloud Cost", "L3", "cloud_cost_lifetime", "$"),
        ("    EOS", "L3", "eos", "$"),
        ("    UID", "L3", "uid", "$"),
        ("    Royalties", "L3", "royalties", "$"),
    ]
    sm_promo = [
        ("Gross Margin", "L1", "gross_profit", "$"),
        ("Gross Margin %", "L1", "gross_margin_pct", "pct"),
        ("Sales & Marketing", "L1", "sales_marketing_expenses", "$"),
        ("  Customer Service", "L2", "customer_service", "$"),
        ("  CC & Platform Fees", "L2", "cc_platform_fees", "$"),
        ("  Marketing", "L2", "marketing", "$"),
        ("CPAM $ (Promo)", "CPAM", "cpam_dollar", "$"),
        ("CPAM % (Promo)", "CPAM", "cpam_pct", "pct"),
    ]
    sm_full = [
        ("Gross Margin (Full Price)", "L1", "_gm_fullprice", "$"),
        ("Gross Margin % (Full Price)", "L1", "_gm_pct_fullprice", "pct"),
        ("Sales & Marketing (Full Price)", "L1", "_sm_fullprice", "$"),
        ("  Customer Service", "L2", "_cs_fullprice", "$"),
        ("  CC & Platform Fees", "L2", "_cc_fullprice", "$"),
        ("  Marketing", "L2", "marketing", "$"),
        ("CPAM $ (Full Price)", "CPAM", "cpam_dollar_full", "$"),
        ("CPAM % (Full Price)", "CPAM", "cpam_pct_full", "pct"),
    ]
    sm_blended = [
        ("Gross Margin (Blended)", "L1", "_gm_blended", "$"),
        ("Gross Margin % (Blended)", "L1", "_gm_pct_blended", "pct"),
        ("Sales & Marketing (Blended)", "L1", "_sm_blended", "$"),
        ("  Customer Service", "L2", "_cs_blended", "$"),
        ("  CC & Platform Fees", "L2", "_cc_blended", "$"),
        ("  Marketing", "L2", "marketing", "$"),
        ("CPAM $ (Blended)", "CPAM", "cpam_dollar_blended", "$"),
        ("CPAM % (Blended)", "CPAM", "cpam_pct_blended", "pct"),
    ]

    if view_mode == "Full Price":
        wf_rows = common_top + rev_full + cogs + sm_full
    elif view_mode == "Promo":
        wf_rows = common_top + rev_promo + cogs + sm_promo
    else:
        wf_rows = common_top + rev_blended + cogs + sm_blended

    active = [r for r in channel_results if r.channel_mix > 0]
    if not active:
        active = channel_results
    has_weighted = weighted and any(r.channel_mix > 0 for r in channel_results)

    cols = ["Metric"] + [r.channel for r in active]
    if has_weighted:
        cols.append("Weighted Avg")
    config.waterfall_columns = cols

    def fmt(val, fmt_type):
        if fmt_type == "pct":
            return f"{val:.1%}"
        elif fmt_type == "mix":
            return f"{val * 100:.0f}%" if val > 0 else "-"
        else:
            return f"${val:.2f}"

    levels = []
    for label, level, field_name, fmt_type in wf_rows:
        row_dict = {"Metric": label}
        for r in active:
            row_dict[r.channel] = fmt(get_field_value(r, field_name), fmt_type)
        if has_weighted:
            row_dict["Weighted Avg"] = fmt(get_weighted_value(field_name), fmt_type)
        config.waterfall_rows.append(row_dict)
        levels.append(level)
    config.waterfall_levels = levels


def _build_sensitivity(config, user_inputs, channel_mix_values, resolved):
    """Build sensitivity sweep data."""
    base_msrp = user_inputs.msrp
    base_fob = user_inputs.fob

    def compute_cpam(msrp_val, fob_val):
        ui = UserInputs(
            msrp=msrp_val, fob=fob_val,
            tariff_rate=user_inputs.tariff_rate,
            promotion_mix=user_inputs.promotion_mix,
            promo_percentage=user_inputs.promo_percentage,
        )
        results = []
        for ch in CHANNELS:
            ca = resolved.channel_assumptions[ch]
            ca.channel_mix = channel_mix_values.get(ch, 0.0) / 100.0
            r = calculate_channel_cpam(ui, resolved.product_info, ca, resolved.static_assumptions)
            results.append(r)
        w = calculate_weighted_cpam(results)
        return w.cpam_dollar_blended if w else 0.0

    if base_msrp > 0:
        for i in range(-5, 6):
            m = base_msrp + i * 5
            if m > 0:
                cpam = compute_cpam(m, base_fob)
                config.sensitivity_msrp_rows.append({"msrp": f"${m:.2f}", "cpam": f"${cpam:.2f}"})

    if base_fob > 0:
        for i in range(-5, 6):
            f = base_fob + i * 2
            if f > 0:
                cpam = compute_cpam(base_msrp, f)
                config.sensitivity_fob_rows.append({"fob": f"${f:.2f}", "cpam": f"${cpam:.2f}"})


def _build_assumptions(config, resolved):
    """Build assumptions data from resolved state."""
    sa = resolved.static_assumptions
    config.assumptions_static_rows = [
        {"item": "UID (Camera)", "value": f"${sa.uid_cam:.2f}", "unit": "per unit"},
        {"item": "Royalties (Camera)", "value": f"${sa.royalties_cam:.2f}", "unit": "per unit"},
        {"item": "Royalties (Bulb)", "value": f"{sa.royalties_bulb_rate:.1%}", "unit": "% of Net Rev"},
        {"item": "Cloud Cost (Camera)", "value": f"${sa.monthly_cloud_cost_cam:.2f}", "unit": "per month"},
        {"item": "Cloud Cost (Non-Cam)", "value": f"${sa.monthly_cloud_cost_noncam:.2f}", "unit": "per month"},
        {"item": "EOS Rate", "value": f"{sa.eos_rate:.1%}", "unit": "% of Landed Cost"},
    ]
    log_df = resolution_log_to_df(resolved.resolution_log)
    if not log_df.empty:
        config.assumptions_log_columns = ["Channel", "Field", "Value", "Source"]
        for _, row in log_df.iterrows():
            config.assumptions_log_rows.append({
                "Channel": str(row.get("Channel", "")),
                "Field": str(row.get("Field", "")),
                "Value": str(row.get("Value", "")),
                "Source": str(row.get("Source", "")),
            })


def build_export_config(
    selected_sku, resolved, view_mode,
    inc_summary, inc_waterfall, inc_channel_mix, inc_sensitivity, inc_assumptions,
):
    """Recalculate all data from session state and build ExportConfig."""
    uid = st.session_state.get("user_inputs", {})
    promo_abs = uid.get("promo_absolute_values", {})

    user_inputs = UserInputs(
        msrp=uid.get("msrp", 0),
        fob=uid.get("fob", 0),
        tariff_rate=uid.get("tariff_rate", 0),
        promotion_mix=uid.get("promotion_mix", 0),
        promo_percentage=uid.get("promo_percentage", 0),
        promo_absolute_values=promo_abs if isinstance(promo_abs, dict) else {},
    )

    channel_mix_values = st.session_state.get("channel_mix", {})

    channel_results = []
    for ch in CHANNELS:
        ca = resolved.channel_assumptions[ch]
        ca.channel_mix = channel_mix_values.get(ch, 0.0) / 100.0
        result = calculate_channel_cpam(user_inputs, resolved.product_info, ca, resolved.static_assumptions)
        channel_results.append(result)
    weighted = calculate_weighted_cpam(channel_results)

    if view_mode == "Full Price":
        cpam_dollar_field, cpam_pct_field, rev_field = "cpam_dollar_full", "cpam_pct_full", "net_revenue_fullprice"
    elif view_mode == "Promo":
        cpam_dollar_field, cpam_pct_field, rev_field = "cpam_dollar", "cpam_pct", "net_revenue"
    else:
        cpam_dollar_field, cpam_pct_field, rev_field = "cpam_dollar_blended", "cpam_pct_blended", "net_revenue_blended"

    label_suffix = f"({view_mode})"
    pi = resolved.product_info

    config = ExportConfig(
        sku=selected_sku,
        product_name=pi.product_name,
        reference_sku=pi.reference_sku or "",
        product_group=pi.product_group or "",
        product_line=pi.product_line or "",
        msrp=user_inputs.msrp,
        fob=user_inputs.fob,
        tariff_rate=user_inputs.tariff_rate,
        promotion_mix=user_inputs.promotion_mix,
        promo_percentage=user_inputs.promo_percentage,
        view_mode=view_mode,
        include_summary=inc_summary,
        include_waterfall=inc_waterfall,
        include_channel_mix=inc_channel_mix,
        include_sensitivity=inc_sensitivity,
        include_assumptions=inc_assumptions,
        generated_by=st.session_state.get("current_user", "local_user"),
        generated_at=datetime.now(),
    )

    # Summary table
    if inc_summary:
        summary_cols = ["Channel", "Mix %", "PO Price", "Net Revenue", "COGS",
                        "Gross Margin", "S&M", f"CPAM $ {label_suffix}", f"CPAM % {label_suffix}"]
        config.summary_columns = summary_cols
        for r in channel_results:
            mix_pct = r.channel_mix * 100
            config.summary_rows.append({
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
            config.summary_rows.append({
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

    if inc_waterfall:
        _build_waterfall(config, channel_results, weighted, user_inputs, view_mode, resolved)

    if inc_channel_mix:
        for ch in CHANNELS:
            pct = channel_mix_values.get(ch, 0.0)
            config.channel_mix_rows.append({"channel": ch, "mix_pct": pct})

    if inc_sensitivity:
        _build_sensitivity(config, user_inputs, channel_mix_values, resolved)

    if inc_assumptions:
        _build_assumptions(config, resolved)

    return config


# =========================================================================
# Streamlit UI
# =========================================================================
styled_header("Export & Save", "Generate a PDF report or save your current session as a reusable template.")

# --- Prerequisites ---
selected_sku = st.session_state.get("selected_sku")
resolved = st.session_state.get("resolved_assumptions")

if not selected_sku or resolved is None:
    st.warning("Please select a product on the Pricing Tool page first.")
    st.page_link("pages/pricing_tool_main.py", label="Go to Pricing Tool ->")
    st.stop()

user_inputs_dict = st.session_state.get("user_inputs", {})
msrp = user_inputs_dict.get("msrp", 0)
fob = user_inputs_dict.get("fob", 0)

if msrp == 0:
    st.warning("MSRP is $0.00. Set pricing inputs on the Pricing Tool page first.")
    st.stop()

st.caption(
    f"**{selected_sku}** - {resolved.product_info.product_name}  |  "
    f"MSRP: ${msrp:.2f}  |  FOB: ${fob:.2f}"
)

# --- 1. Section Selection ---
st.subheader("1. Select Sections")
col1, col2 = st.columns(2)
with col1:
    inc_summary = st.checkbox("CPAM Summary", value=True)
    inc_waterfall = st.checkbox("CPAM Waterfall Breakdown", value=True)
    inc_channel_mix = st.checkbox("Channel Mix", value=True)
with col2:
    inc_sensitivity = st.checkbox("Sensitivity Analysis", value=False)
    inc_assumptions = st.checkbox("Assumptions Detail", value=False)

# --- 2. View Mode ---
st.subheader("2. View Mode")
view_mode = styled_segmented(
    ["Blended", "Full Price", "Promo"],
    icons=["shuffle", "cash-stack", "percent"],
    key="export_view_mode",
)

# --- 3. Generate ---
st.subheader("3. Generate & Download")

if st.button("Generate PDF Report", type="primary", use_container_width=True):
    with st.spinner("Generating PDF report..."):
        config = build_export_config(
            selected_sku, resolved, view_mode,
            inc_summary, inc_waterfall, inc_channel_mix, inc_sensitivity, inc_assumptions,
        )
        pdf_bytes = generate_pricing_report(config)
        st.session_state["export_pdf_bytes"] = pdf_bytes
        st.session_state["export_filename"] = (
            f"Pricing_{selected_sku}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        )
    st.success("PDF report generated!")

if "export_pdf_bytes" in st.session_state:
    st.download_button(
        label="Download PDF",
        data=st.session_state["export_pdf_bytes"],
        file_name=st.session_state.get("export_filename", "report.pdf"),
        mime="application/pdf",
        type="primary",
        use_container_width=True,
    )

# =========================================================================
# 4. Save to Template
# =========================================================================
styled_divider(label="Save to Template", icon="bookmark-fill")
st.caption(
    "Save the current pricing session (SKU, inputs, channel mix, assumptions) "
    "as a reusable template. Load it later from **Pricing Templates**."
)

ui = st.session_state.get("user_inputs", {})
mix = st.session_state.get("channel_mix", {})
active_mix = {ch: pct for ch, pct in mix.items() if pct > 0}

# Preview what will be saved
col_s1, col_s2, col_s3, col_s4 = st.columns(4)
with col_s1:
    st.metric("MSRP", f"${ui.get('msrp', 0):.2f}")
with col_s2:
    st.metric("FOB", f"${ui.get('fob', 0):.2f}")
with col_s3:
    st.metric("Tariff", f"{ui.get('tariff_rate', 0):.1f}%")
with col_s4:
    st.metric("Active Channels", len(active_mix))

if active_mix:
    st.caption("Channel Mix: " + ", ".join(f"{ch} ({pct:.0f}%)" for ch, pct in active_mix.items()))

template_name = st.text_input(
    "Template Name",
    value=f"{selected_sku} - Pricing",
    help="Give this template a descriptive name",
    key="export_template_name",
)
notes = st.text_area(
    "Notes (optional)",
    height=80,
    placeholder="e.g. Q1 2026 pricing review",
    key="export_template_notes",
)
user = st.session_state.get("current_user", "local_user")

if st.button("Save Template", type="primary", key="export_save_template"):
    if template_name:
        try:
            tid = save_template(
                sku=selected_sku,
                template_name=template_name,
                user=user,
                user_inputs=ui,
                channel_mix=mix,
                resolved_assumptions=resolved,
                notes=notes,
            )
            st.success(f"Template saved! (ID: {tid})")
        except Exception as e:
            st.error(f"Save failed: {e}")
    else:
        st.warning("Please enter a template name.")
