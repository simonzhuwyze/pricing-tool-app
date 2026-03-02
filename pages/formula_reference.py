"""
Formula Reference - Complete CPAM calculation methodology documentation.
All formulas translated from the Power BI DAX semantic model.
"""

import streamlit as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.ui_helpers import styled_header
from core.cpam_engine import PROMO_CHANNEL_FACTORS, SHIPPING_REVENUE

styled_header("Formula Reference", "Complete CPAM calculation methodology and metric definitions")

# ---------------------------------------------------------------------------
# Table of Contents
# ---------------------------------------------------------------------------
st.markdown("""
**Jump to:** [Net Revenue](#net-revenue) · [Cost of Goods](#cost-of-goods) · [Sales & Marketing](#sales-marketing) · [Profit Metrics](#profit-metrics) · [Blended & Weighted](#blended-weighted) · [Assumptions](#assumptions-reference) · [Constants](#constants)
""")

# ===== NET REVENUE =====
st.divider()
st.header("Net Revenue", anchor="net-revenue")
st.caption("Revenue components from MSRP down to Net Revenue (per unit, per channel)")

st.markdown(r"""
| # | Metric | Formula | Notes |
|---|--------|---------|-------|
| 1 | **MSRP** | User input | Manufacturer's Suggested Retail Price |
| 2 | **Retail Margin** | $-\text{PO Discount Rate} \times \text{MSRP}$ | Per-SKU per-channel rate from assumptions |
| 3 | **PO Price** | $\text{MSRP} + \text{Retail Margin}$ | Price retailer pays Wyze |
| 4 | **Retail Discounts & Allowances** | $-\text{Total Discount Rate} \times \text{PO Price}$ | Channel-level rate from Channel Terms |
| 5 | **Pre-Promo Retailer Price** | $\text{PO Price} + \text{Retail Discounts}$ | Retailer price before promotions |
| 6 | **Promotion** | See below | Depends on promo mode |
| 7 | **Price Paid by End-User** | $\text{MSRP} + \text{Promotion}$ | What consumer actually pays |
| 8 | **Post-Promo Retailer Price** | $\text{PO Price} + \text{Promotion} + \text{Retail Discounts}$ | Effective retailer price after all adjustments |
| 9 | **Chargebacks** | $-\text{PO Price} \times \text{Chargeback Rate}$ | Channel-level rate from Channel Terms |
| 10 | **Returns & Replacements** | $-\text{Post-Promo Retailer Price} \times \text{Return Rate}$ | Per-SKU per-channel return rate |
| 11 | **Other Contra Revenue** | $\text{Chargebacks} + \text{Returns \& Replacements}$ | Combined deductions |
| 12 | **Shipping Revenue** | Channel-specific constant | See Constants section |
| 13 | **Net Revenue** | $\text{Post-Promo Retailer Price} + \text{Other Contra Revenue} + \text{Shipping Revenue}$ | Final net revenue per unit |
""")

st.subheader("Promotion Calculation")
st.markdown(r"""
Two modes depending on user input:

**Mode 1: Percentage-based** (when Promo % > 0)
$$\text{Promotion} = -\text{MSRP} \times \text{Promo \%} \times \text{Channel Factor}$$

**Mode 2: Absolute value** (when Promo % = 0)
$$\text{Promotion} = -\text{Promo Absolute Value from Library}$$

**Channel Promo Factors:**
""")

factor_data = {ch: f for ch, f in PROMO_CHANNEL_FACTORS.items()}
cols = st.columns(len(factor_data) + 1)
cols[0].metric("All Other Channels", "1.0x")
for i, (ch, f) in enumerate(factor_data.items()):
    cols[i + 1].metric(ch, f"{f}x")

# ===== COST OF GOODS =====
st.divider()
st.header("Cost of Goods", anchor="cost-of-goods")
st.caption("All cost components from FOB to total Cost of Goods (per unit, per channel)")

st.markdown(r"""
| # | Metric | Formula | Notes |
|---|--------|---------|-------|
| 1 | **FOB** | User input | Factory price |
| 2 | **Tariff** | $\text{Tariff Rate \%} \times \text{FOB} \div 100$ | User input rate |
| 3 | **Inbound Freight & Insurance** | Per-SKU assumption | From Cost Assumptions table |
| 4 | **Landed Cost** | $\text{FOB} + \text{Inbound Freight} + \text{Tariff}$ | Total cost to warehouse |
| 5 | **Outbound Shipping** | Per-SKU per-channel | From Outbound Shipping table |
| 6 | **Warehouse Storage & Handling** | Per-SKU assumption | Amazon 3P uses FBA Fee instead |
| 7 | **Shipping Cost** | $\text{Outbound Shipping} + \text{Warehouse Storage}$ | Total logistics cost |
| 8 | **Cloud Cost (Lifetime)** | $\text{Expected Product Life} \times \text{Monthly Cloud Cost}$ | Camera vs Non-Camera rate |
| 9 | **EOS (Excess, Obsolete & Shrinkage)** | $\text{Landed Cost} \times \text{EOS Rate}$ | Global rate from Static Assumptions |
| 10 | **UID** | $0.20 for Cameras, $0 otherwise | Fixed per unit |
| 11 | **Royalties** | See below | Product-type dependent |
| 12 | **Other Cost** | $\text{Cloud Cost} + \text{EOS} + \text{UID} + \text{Royalties}$ | Combined other costs |
| 13 | **Cost of Goods** | $\text{Landed Cost} + \text{Shipping Cost} + \text{Other Cost}$ | Total COGS per unit |
""")

st.subheader("Royalties Calculation")
st.markdown(r"""
Priority order (first match wins):

| Priority | Condition | Formula |
|----------|-----------|---------|
| 1 | **Product Group = Cameras** | Fixed \$0.20 per unit |
| 2 | **Product Line = Bulbs** | $\text{Royalty Rate (5\%)} \times \text{Net Revenue}$ |
| 3 | **All Others** | \$0.00 |
""")

st.subheader("Warehouse Logic")
st.markdown(r"""
| Channel | Field Used |
|---------|-----------|
| **Amazon 3P** | Amazon FBA Fee (from Cost Assumptions) |
| **All Other Channels** | Warehouse Storage & Handling (from Cost Assumptions) |
""")

# ===== SALES & MARKETING =====
st.divider()
st.header("Sales & Marketing", anchor="sales-marketing")
st.caption("Sales & Marketing expense components (per unit, per channel)")

st.markdown(r"""
| # | Metric | Formula | Notes |
|---|--------|---------|-------|
| 1 | **Customer Service** | $\text{Customer Service Rate} \times \text{Post-Promo Retailer Price}$ | Channel-level rate |
| 2 | **CC & Platform Fees** | $\text{CC Fee Rate} \times \text{Price Paid by End-User}$ | +\$0.99 for Amazon 3P |
| 3 | **Marketing** | $\text{Marketing Rate} \times \text{MSRP}$ | Channel-level rate |
| 4 | **S&M Expenses Total** | $\text{Customer Service} + \text{CC Fees} + \text{Marketing}$ | Total S&M per unit |
""")

st.info("💡 **Amazon 3P special rule**: CC & Platform Fees adds a fixed $0.99/unit on top of the rate-based calculation.")

# ===== PROFIT METRICS =====
st.divider()
st.header("Profit Metrics", anchor="profit-metrics")
st.caption("Final profitability calculations")

st.markdown(r"""
| # | Metric | Formula | Interpretation |
|---|--------|---------|---------------|
| 1 | **Gross Profit** | $\text{Net Revenue} - \text{Cost of Goods}$ | Profit before S&M |
| 2 | **Gross Margin %** | $\text{Gross Profit} \div \text{Net Revenue}$ | Profitability ratio |
| 3 | **CPAM \$** | $\text{Gross Profit} - \text{S\&M Expenses}$ | Contribution Profit After Marketing |
| 4 | **CPAM %** | $\text{CPAM \$} \div \text{Net Revenue}$ | Key profitability KPI |
""")

st.success("🎯 **CPAM** (Contribution Profit After Marketing) is the primary profitability metric used for pricing decisions.")

# ===== BLENDED & WEIGHTED =====
st.divider()
st.header("Blended & Weighted", anchor="blended-weighted")
st.caption("Full price, blended, and weighted average calculations")

st.subheader("Full Price vs Promotional")
st.markdown(r"""
"Full Price" scenarios calculate as if there is **no promotion**:

| Metric | Formula |
|--------|---------|
| **Net Revenue (Full Price)** | $\text{PO Price} + \text{Retail Discounts} - \text{Pre-Promo Retailer Price} \times \text{Return Rate} + \text{Chargebacks} + \text{Shipping Revenue}$ |
| **S&M Expenses (Full Price)** | Same rates but Customer Service uses Pre-Promo Retailer Price instead of Post-Promo |
| **CPAM \$ (Full Price)** | $\text{Net Revenue (Full Price)} - \text{Cost of Goods} - \text{S\&M (Full Price)}$ |
| **CPAM % (Full Price)** | $\text{CPAM \$ (Full Price)} \div \text{Net Revenue (Full Price)}$ |
""")

st.subheader("Blended Calculation")
st.markdown(r"""
Blends full-price and promotional scenarios using the **Promotion Mix** percentage:

$$\text{Net Revenue (Blended)} = \text{Net Revenue (Full)} \times (1 - \text{Promo Mix}) + \text{Net Revenue (Promo)} \times \text{Promo Mix}$$

$$\text{CPAM \$ (Blended)} = \text{CPAM \$ (Full)} \times (1 - \text{Promo Mix}) + \text{CPAM \$ (Promo)} \times \text{Promo Mix}$$

$$\text{CPAM \% (Blended)} = \text{CPAM \$ (Blended)} \div \text{Net Revenue (Blended)}$$
""")

st.subheader("Weighted Average (across channels)")
st.markdown(r"""
When Channel Mix is applied, all **dollar metrics** are weighted:

$$\text{Weighted Metric} = \frac{\sum_{c} \text{Metric}_c \times \text{Mix}_c}{\sum_{c} \text{Mix}_c}$$

**Percentage metrics** (Gross Margin %, CPAM %) are **recomputed** from the weighted dollar values, not averaged directly:

$$\text{Weighted CPAM \%} = \frac{\text{Weighted CPAM \$}}{\text{Weighted Net Revenue}}$$
""")

# ===== ASSUMPTIONS REFERENCE =====
st.divider()
st.header("Assumptions Reference", anchor="assumptions-reference")
st.caption("Where each assumption comes from and its resolution priority")

st.markdown(r"""
### Resolution Priority
All per-SKU assumptions follow this fallback chain:

$$\text{Database Override} \rightarrow \text{Cache Table} \rightarrow \text{CSV File} \rightarrow \text{Reference SKU Fallback} \rightarrow \text{Default (0)}$$

### Assumption Sources

| Assumption | Granularity | Source Table / CSV |
|-----------|-------------|-------------------|
| PO Discount Rate | Per-SKU × Per-Channel | `Input_SKU_Retail Margin.csv` / `cache_po_discount` |
| Return Rate | Per-SKU × Per-Channel | `Input_SKU_Return Rate.csv` / `cache_return_rate_sku` |
| Outbound Shipping | Per-SKU × Per-Channel | `Input_SKU_Outbound Shipping.csv` / `cache_outbound_shipping` |
| Inbound Freight | Per-SKU | `Input_SKU_CostAssumptions.csv` / `cache_cost_assumptions` |
| Warehouse Storage | Per-SKU | `Input_SKU_CostAssumptions.csv` / `cache_cost_assumptions` |
| Amazon FBA Fee | Per-SKU | `Input_SKU_CostAssumptions.csv` / `cache_cost_assumptions` |
| Expected Product Life | Per-SKU | `Input_SKU_CostAssumptions.csv` / `cache_cost_assumptions` |
| Chargeback Rate | Per-Channel | `Static_Channel Terms.csv` / `admin_channel_terms` |
| Total Discount Rate | Per-Channel | `Static_Channel Terms.csv` / `admin_channel_terms` |
| Customer Service Rate | Per-Channel | `Static_S&M Expenses.csv` / `admin_sm_expenses` |
| CC Fee Rate | Per-Channel | `Static_S&M Expenses.csv` / `admin_sm_expenses` |
| Marketing Rate | Per-Channel | `Static_S&M Expenses.csv` / `admin_sm_expenses` |
| EOS Rate | Global | `Static_Cost Assumptions.csv` / `admin_static_assumptions` |
| Monthly Cloud Cost | Global (Camera / Non-Camera) | `Static_Cost Assumptions.csv` / `admin_static_assumptions` |
| UID | Global (Camera only) | Fixed $0.10 |
| Royalty Rate (Bulbs) | Global | Fixed 5% of Net Revenue |
| Royalty (Cameras) | Global | Fixed $0.20/unit |
""")

# ===== CONSTANTS =====
st.divider()
st.header("Constants", anchor="constants")
st.caption("Hard-coded values from the original Power BI DAX model")

st.subheader("Shipping Revenue (per unit)")
ship_cols = st.columns(len(SHIPPING_REVENUE) + 1)
for i, (ch, val) in enumerate(SHIPPING_REVENUE.items()):
    ship_cols[i].metric(ch, f"${val:.2f}")
ship_cols[len(SHIPPING_REVENUE)].metric("All Other Channels", "$0.00")

st.subheader("Fixed Values")
st.markdown("""
| Constant | Value | Applies To |
|----------|-------|-----------|
| UID | $0.20 / unit | Cameras (product_group) only |
| Royalties | $0.20 / unit | Cameras (product_group) only |
| Royalties | 5% of Net Revenue | Bulbs (product_line) only |
| Amazon 3P CC surcharge | $0.99 / unit | Amazon 3P only |

> **Royalties priority**: Camera check (product_group) is evaluated first. If a product is both Camera and Bulb, Camera rule wins.
""")

st.subheader("Promotion Channel Factors")
st.markdown("Used in percentage-based promo calculation to adjust promo depth by channel:")
factor_md = "| Channel | Factor |\n|---------|--------|\n"
for ch, f in PROMO_CHANNEL_FACTORS.items():
    factor_md += f"| {ch} | {f} |\n"
factor_md += "| All Other Channels | 1.0 |\n"
st.markdown(factor_md)

# ===== DATA FLOW =====
st.divider()
st.header("Data Flow Overview")

st.markdown("""
```
User Inputs (MSRP, FOB, Tariff %, Promo settings)
    │
    ├── Per-Channel Assumptions (resolved via DB > CSV > Ref SKU > 0)
    │       │
    │       ├── PO Discount Rate ──→ Retail Margin
    │       ├── Channel Terms ──→ Retail Discounts, Chargebacks
    │       ├── Return Rate ──→ Returns & Replacements
    │       ├── Outbound Shipping ──→ Shipping Cost
    │       ├── Cost Assumptions ──→ Inbound, Warehouse, Cloud, Product Life
    │       └── S&M Rates ──→ Customer Service, CC Fees, Marketing
    │
    ├── ────────────────────────────────────────────
    │   CALCULATE per channel:
    │       Net Revenue  =  Post-Promo Price + Contra Revenue + Shipping Rev
    │       Cost of Goods  =  Landed Cost + Shipping Cost + Other Cost
    │       S&M Expenses  =  Cust Service + CC Fees + Marketing
    │       Gross Profit  =  Net Revenue - COGS
    │       CPAM $  =  Gross Profit - S&M
    │       CPAM %  =  CPAM $ / Net Revenue
    │
    └── Channel Mix weights ──→ Weighted Average CPAM across all channels
```
""")
