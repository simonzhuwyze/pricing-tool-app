"""
Sensitivity Analysis Page - MSRP and FOB sweep.
Replicates the Power BI MSRP/FOB Sensitivity pages.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.data_loader import load_product_directory, load_sku_mapping, load_po_discount, load_outbound_shipping, CHANNELS
from core.cpam_engine import (
    UserInputs, ProductInfo, ChannelAssumptions, StaticAssumptions,
    calculate_channel_cpam, calculate_weighted_cpam,
)

st.title("Sensitivity Analysis")

selected_sku = st.session_state.get("selected_sku")
user_inputs_dict = st.session_state.get("user_inputs", {})

if not selected_sku:
    st.warning("Please select a product on the Home page first.")
    st.stop()

# Load data
products = load_product_directory()
sku_mapping = load_sku_mapping()
po_discount_df = load_po_discount()
outbound_df = load_outbound_shipping()

product_row = products[products["SKU"] == selected_sku].iloc[0]
ref_sku = product_row.get("Reference SKU", "")
sku_info = sku_mapping[sku_mapping["SKU"] == selected_sku]
if sku_info.empty and pd.notna(ref_sku) and ref_sku:
    sku_info = sku_mapping[sku_mapping["SKU"] == ref_sku]

product_group = sku_info["Product_Group"].iloc[0] if not sku_info.empty and "Product_Group" in sku_info.columns else ""
product_line = sku_info["Product_Line"].iloc[0] if not sku_info.empty and "Product_Line" in sku_info.columns else ""

product = ProductInfo(
    sku=selected_sku,
    product_name=str(product_row.get("Product Name", "")),
    product_group=str(product_group) if pd.notna(product_group) else "",
    product_line=str(product_line) if pd.notna(product_line) else "",
)
static = StaticAssumptions(
    uid_cam=0.10, royalties_cam=0.20, royalties_bulb_rate=0.05,
    monthly_cloud_cost_cam=0.08, monthly_cloud_cost_noncam=0.0, eos_rate=0.01,
)

base_msrp = user_inputs_dict.get("msrp", float(product_row.get("Default MSRP", 0) or 0))
base_fob = user_inputs_dict.get("fob", float(product_row.get("Default FOB", 0) or 0))
base_tariff = user_inputs_dict.get("tariff_rate", float(product_row.get("Default Tariff Rate", 0) or 0) * 100)
base_promo_mix = user_inputs_dict.get("promotion_mix", 0)

st.caption(f"**{selected_sku}** - {product_row.get('Product Name', '')}  |  Base MSRP: ${base_msrp:.2f}  |  Base FOB: ${base_fob:.2f}")


def run_cpam_for_inputs(msrp_val, fob_val):
    """Calculate weighted CPAM for given MSRP/FOB."""
    ui = UserInputs(msrp=msrp_val, fob=fob_val, tariff_rate=base_tariff, promotion_mix=base_promo_mix)
    channel_mix_values = st.session_state.get("channel_mix", {})
    results = []
    for ch in CHANNELS:
        po_row = po_discount_df[(po_discount_df["SKU"] == selected_sku) & (po_discount_df["Channel"] == ch)]
        po_rate = float(po_row["PO_Discount_Rate"].iloc[0]) if not po_row.empty else 0.0
        ob_row = outbound_df[(outbound_df["SKU"] == selected_sku) & (outbound_df["Channel"] == ch)]
        ob_cost = float(ob_row["Outbound_Shipping_Cost"].iloc[0]) if not ob_row.empty else 0.0
        mix_val = channel_mix_values.get(ch, 0.0) / 100.0

        assumptions = ChannelAssumptions(
            channel=ch, po_discount_rate=po_rate, outbound_shipping=ob_cost,
            channel_mix=mix_val, customer_service_rate=0.03, cc_fee_rate=0.03, marketing_rate=0.03,
        )
        results.append(calculate_channel_cpam(ui, product, assumptions, static))

    weighted = calculate_weighted_cpam(results)
    if weighted:
        return weighted.cpam_dollar_blended
    # If no mix set, return average across all channels
    if results:
        return sum(r.cpam_dollar_blended for r in results) / len(results)
    return 0


# --- Tab selection ---
tab_msrp, tab_fob = st.tabs(["MSRP Sensitivity", "FOB Sensitivity"])

with tab_msrp:
    st.subheader("MSRP Sensitivity")
    st.caption("See how different MSRP values impact Blended CPAM. Set Promotion Mix = 0 on Home page for Full Price CPAM.")

    col1, col2 = st.columns(2)
    with col1:
        msrp_step = st.number_input("Step ($)", value=1.0, min_value=1.0, max_value=10.0, step=1.0, key="msrp_step")
    with col2:
        msrp_range = st.number_input("Range (+/-)", value=5, min_value=1, max_value=20, step=1, key="msrp_range")

    # Generate sweep values
    sweep_values = [base_msrp + i * msrp_step for i in range(-msrp_range, msrp_range + 1)]
    sweep_values = [v for v in sweep_values if v > 0]

    results_data = []
    for msrp_val in sweep_values:
        cpam = run_cpam_for_inputs(msrp_val, base_fob)
        results_data.append({
            "MSRP": msrp_val,
            "Blended CPAM $": cpam,
            "Is Baseline": abs(msrp_val - base_msrp) < 0.01,
        })

    results_df = pd.DataFrame(results_data)

    # Chart
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=results_df["MSRP"],
        y=results_df["Blended CPAM $"],
        marker_color=[
            "#FFD700" if is_base else ("#15CAB6" if cpam >= 0 else "#E85E76")
            for is_base, cpam in zip(results_df["Is Baseline"], results_df["Blended CPAM $"])
        ],
        text=[f"${v:.2f}" for v in results_df["Blended CPAM $"]],
        textposition="outside",
    ))
    fig.update_layout(
        xaxis_title="MSRP ($)", yaxis_title="Blended CPAM ($)",
        height=400, plot_bgcolor="#F8FAFC",
        margin=dict(t=20),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Table
    display = results_df[["MSRP", "Blended CPAM $"]].copy()
    display["MSRP"] = display["MSRP"].map(lambda x: f"${x:.2f}")
    display["Blended CPAM $"] = display["Blended CPAM $"].map(lambda x: f"${x:.2f}")
    st.dataframe(display, use_container_width=True, hide_index=True)


with tab_fob:
    st.subheader("FOB Sensitivity")
    st.caption("See how different FOB values impact Blended CPAM.")

    col1, col2 = st.columns(2)
    with col1:
        fob_step = st.number_input("Step ($)", value=0.50, min_value=0.05, max_value=10.0, step=0.05, format="%.2f", key="fob_step")
    with col2:
        fob_range = st.number_input("Range (+/-)", value=5, min_value=1, max_value=20, step=1, key="fob_range")

    sweep_fob = [base_fob + i * fob_step for i in range(-fob_range, fob_range + 1)]
    sweep_fob = [v for v in sweep_fob if v > 0]

    fob_results = []
    for fob_val in sweep_fob:
        cpam = run_cpam_for_inputs(base_msrp, fob_val)
        fob_results.append({
            "FOB": fob_val,
            "Blended CPAM $": cpam,
            "Is Baseline": abs(fob_val - base_fob) < 0.01,
        })

    fob_df = pd.DataFrame(fob_results)

    fig2 = go.Figure()
    fig2.add_trace(go.Bar(
        x=fob_df["FOB"],
        y=fob_df["Blended CPAM $"],
        marker_color=[
            "#FFD700" if is_base else ("#15CAB6" if cpam >= 0 else "#E85E76")
            for is_base, cpam in zip(fob_df["Is Baseline"], fob_df["Blended CPAM $"])
        ],
        text=[f"${v:.2f}" for v in fob_df["Blended CPAM $"]],
        textposition="outside",
    ))
    fig2.update_layout(
        xaxis_title="FOB ($)", yaxis_title="Blended CPAM ($)",
        height=400, plot_bgcolor="#F8FAFC",
        margin=dict(t=20),
    )
    st.plotly_chart(fig2, use_container_width=True)

    display2 = fob_df[["FOB", "Blended CPAM $"]].copy()
    display2["FOB"] = display2["FOB"].map(lambda x: f"${x:.2f}")
    display2["Blended CPAM $"] = display2["Blended CPAM $"].map(lambda x: f"${x:.2f}")
    st.dataframe(display2, use_container_width=True, hide_index=True)
