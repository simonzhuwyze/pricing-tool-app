"""
CPAM Calculator Page - Full CPAM Waterfall Breakdown
Replicates the Power BI 'CPAM Details' page with editable cells.
"""

import streamlit as st
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.data_loader import load_product_directory, load_sku_mapping, load_po_discount, load_outbound_shipping, CHANNELS
from core.cpam_engine import (
    UserInputs, ProductInfo, ChannelAssumptions, StaticAssumptions,
    calculate_channel_cpam, calculate_weighted_cpam,
)

st.title("CPAM Calculation Breakdown")

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

user_inputs = UserInputs(
    msrp=user_inputs_dict.get("msrp", float(product_row.get("Default MSRP", 0) or 0)),
    fob=user_inputs_dict.get("fob", float(product_row.get("Default FOB", 0) or 0)),
    tariff_rate=user_inputs_dict.get("tariff_rate", float(product_row.get("Default Tariff Rate", 0) or 0) * 100),
    promotion_mix=user_inputs_dict.get("promotion_mix", 0),
)

st.caption(f"**{selected_sku}** - {product_row.get('Product Name', '')}  |  MSRP: ${user_inputs.msrp:.2f}  |  FOB: ${user_inputs.fob:.2f}  |  Tariff: {user_inputs.tariff_rate:.1f}%  |  Promo Mix: {user_inputs.promotion_mix:.0f}%")

# Calculate for all channels
channel_mix_values = st.session_state.get("channel_mix", {})
channel_results = []

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
    result = calculate_channel_cpam(user_inputs, product, assumptions, static)
    channel_results.append(result)

weighted = calculate_weighted_cpam(channel_results)

# Build the CPAM waterfall table (matches Power BI Template_CPAM Detail structure)
# Rows are line items, columns are channels
waterfall_rows = [
    ("Unit Sales Mix %", "L1", "channel_mix"),
    ("Net Revenue", "L1", "net_revenue"),
    ("  1.1 Gross Product Price (MSRP)", "L2", "msrp"),
    ("  1.2 Shipping Revenue", "L2", "shipping_revenue"),
    ("  1.3 Retail Margin", "L2", "retail_margin"),
    ("  1.4 Promotion", "L2", "promotion"),
    ("  1.5 Retail Discounts & Allowances", "L2", "retail_discounts"),
    ("  1.6 Other Contra Revenue", "L2", "other_contra_revenue"),
    ("    Chargebacks", "L3", "chargebacks"),
    ("    Returns & Replacements", "L3", "returns_replacements"),
    ("Cost of Goods", "L1", "cost_of_goods"),
    ("  2.1 Landed Cost", "L2", "landed_cost"),
    ("    FOB", "L3", "fob"),
    ("    Inbound Freight & Insurance", "L3", "inbound_freight"),
    ("    Tariff", "L3", "tariff"),
    ("  2.2 Shipping & Logistics Cost", "L2", "shipping_cost"),
    ("    Outbound Shipping", "L3", "outbound_shipping"),
    ("    Warehouse Storage & Handling", "L3", "warehouse_storage"),
    ("  2.3 Other Costs", "L2", "other_cost"),
    ("    Cloud Cost (Lifetime)", "L3", "cloud_cost_lifetime"),
    ("    Excess, Obsolete & Shrinkage", "L3", "eos"),
    ("    UID", "L3", "uid"),
    ("    Royalties", "L3", "royalties"),
    ("Gross Margin", "L1", "gross_profit"),
    ("Sales & Marketing", "L1", "sales_marketing_expenses"),
    ("  3.1 Customer Service", "L2", "customer_service"),
    ("  3.2 Credit-card & Platform Fees", "L2", "cc_platform_fees"),
    ("  3.3 Marketing", "L2", "marketing"),
    ("CPAM $", "CPAM", "cpam_dollar"),
    ("CPAM %", "CPAM", "cpam_pct"),
]

# Filter to channels that have mix > 0, or show all if no mix set
active_channels = [r for r in channel_results if r.channel_mix > 0]
if not active_channels:
    active_channels = channel_results  # Show all if no mix set

# Build dataframe
table_data = {"Metric": [], "Level": []}
for r in active_channels:
    table_data[r.channel] = []
if weighted and any(r.channel_mix > 0 for r in channel_results):
    table_data["Weighted Avg"] = []

for label, level, field in waterfall_rows:
    table_data["Metric"].append(label)
    table_data["Level"].append(level)
    for r in active_channels:
        val = getattr(r, field, 0)
        table_data[r.channel].append(val)
    if "Weighted Avg" in table_data and weighted:
        table_data["Weighted Avg"].append(getattr(weighted, field, 0))

df = pd.DataFrame(table_data)

# Display
display_df = df.drop(columns=["Level"])

# Style function - uses Level from original df, returns styles matching display_df columns
def style_waterfall(row):
    level = df.at[row.name, "Level"]
    n = len(row)
    if level == "L1":
        return ["background-color: #F1F2F7; font-weight: bold"] * n
    elif level == "CPAM":
        return ["background-color: #E8F5E9; font-weight: bold; color: #0D8A7B"] * n
    return [""] * n

# Custom formatting
styled = display_df.style.apply(style_waterfall, axis=1)

# Format values
channel_cols = [c for c in display_df.columns if c != "Metric"]
for col in channel_cols:
    styled = styled.format(
        subset=[col],
        formatter=lambda x, row_label=None: (
            f"{x:.1%}" if isinstance(x, (int, float)) and abs(x) <= 1.5 and x != 0
            else f"${x:.2f}" if isinstance(x, (int, float))
            else str(x)
        ),
    )

st.dataframe(styled, use_container_width=True, hide_index=True, height=1100)

# Additional pricing metrics
st.divider()
st.subheader("Additional Pricing Metrics")

metrics_data = []
for r in active_channels:
    metrics_data.append({
        "Channel": r.channel,
        "PO Price": f"${r.po_price:.2f}",
        "Price Paid by End-User": f"${r.price_paid_by_enduser:.2f}",
        "Pre-promo Retailer Price": f"${r.pre_promo_retailer_price:.2f}",
        "Post-promo Retailer Price": f"${r.post_promo_retailer_price:.2f}",
        "Gross Margin %": f"{r.gross_margin_pct:.1%}",
    })

st.dataframe(pd.DataFrame(metrics_data), use_container_width=True, hide_index=True)
