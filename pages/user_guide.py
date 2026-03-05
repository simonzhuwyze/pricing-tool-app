"""
User Guide - Step-by-step instructions for using the Wyze Pricing Tool.
"""

import streamlit as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.ui_helpers import styled_header

styled_header("User Guide", "Step-by-step instructions for pricing existing products and onboarding new SKUs")

# ---------------------------------------------------------------------------
# Table of Contents
# ---------------------------------------------------------------------------
st.markdown("""
**Jump to:** [Quick Start](#quick-start) · [Price an Existing Product](#price-an-existing-product) · [Add a New SKU](#add-a-new-sku) · [Channel Mix](#set-up-channel-mix) · [Templates](#save-load-templates) · [Manage Assumptions](#manage-assumptions) · [Admin Tasks](#admin-tasks) · [FAQ](#faq)
""")

# ===== QUICK START =====
st.divider()
st.header("Quick Start", anchor="quick-start")

st.markdown("""
The Pricing Tool calculates **CPAM (Contribution Profit After Marketing)** for any Wyze product across 13 sales channels. Here's the 3-step workflow:

1. **Select a product** on the Pricing Tool page
2. **Set your inputs** (MSRP, FOB, Tariff %, Promo settings)
3. **Review CPAM** across all channels, with Blended / Full Price / Promo views

The tool auto-loads all assumptions (return rates, shipping costs, channel terms, etc.) from the database or CSV files. You just need to provide the pricing inputs.
""")

st.subheader("Navigation Overview")
st.markdown("""
| Section | Pages | What It Does |
|---------|-------|-------------|
| **Product Directory** | Product Directory | Browse all SKUs, create/edit/delete products |
| **Pricing Tool** | Pricing Tool, CPAM Calculator, Channel Mix, Sensitivity, Assumptions | Core pricing workflow |
| **Reference** | Pricing Templates, Formula Reference, User Guide | Save/load pricing scenarios, view formulas |
| **Assumptions** | Retail Margin, Return Rate, Outbound Shipping, Product Costs, Finance | View and edit assumption data tables |
| **Settings** | DB Admin, Data Validation, SF Raw Data | Database connection, Snowflake sync, data management |
""")

# ===== PRICE AN EXISTING PRODUCT =====
st.divider()
st.header("Price an Existing Product", anchor="price-an-existing-product")

st.subheader("Step 1: Select Product")
st.markdown("""
1. Go to **Pricing Tool** (default landing page)
2. Use the **Product** dropdown to search and select your SKU
3. The tool displays the product name, Reference SKU, and whether it's an existing or new product
4. All per-SKU assumptions are **automatically loaded** from the database

> **Tip**: You can also select a product from the **Product Directory** page using the "Quick Select" feature at the bottom.
""")

st.subheader("Step 2: Set Pricing Inputs")
st.markdown("""
Three key inputs drive the calculation:

| Input | Description | Default |
|-------|-------------|---------|
| **MSRP** | Manufacturer's Suggested Retail Price | Auto-filled from Product Directory |
| **FOB** | Factory price (cost from manufacturer) | Auto-filled from Product Directory |
| **Tariff Rate %** | Import tariff as percentage of FOB | Auto-filled from Product Directory |

These defaults come from the Product Directory. Override them as needed for your pricing scenario.
""")

st.subheader("Step 3: Configure Promotions (Optional)")
st.markdown("""
Two promo settings control the blended CPAM calculation:

- **Promo Mix %** — What percentage of units are sold under promotion (0-100%)
- **Quick Promo %** — Discount off MSRP applied to promo units

**Two promo modes:**
- If **Quick Promo % > 0**: A flat percentage discount is applied (with channel-specific factors)
- If **Quick Promo % = 0**: You can set per-channel absolute promo dollar amounts in the expander below

**Blended CPAM** combines full-price and promo results based on the Promo Mix %.
""")

st.subheader("Step 4: Review CPAM Results")
st.markdown("""
The CPAM Summary table shows per-channel results. Use the view toggle:

- **Blended** — Weighted combination of full price and promo (default, most useful)
- **Full Price** — As if no promotion is running
- **Promo** — As if all units are under promotion

**Key metrics to focus on:**
- **CPAM %** — Primary profitability metric. Higher is better.
- **Gross Margin %** — Profit before Sales & Marketing expenses.
- **Weighted Avg** row — Only appears when Channel Mix is set (see below).
""")

st.subheader("Step 5: Deep Dive (Optional)")
st.markdown("""
For more detail, use the sub-pages:

- **CPAM Calculator** — Full waterfall breakdown for each channel (Revenue → COGS → S&M → CPAM)
- **Sensitivity Analysis** — See how CPAM changes as MSRP or FOB varies
- **Assumptions Loaded** — View all resolved assumptions for the current SKU
""")

# ===== ADD A NEW SKU =====
st.divider()
st.header("Add a New SKU", anchor="add-a-new-sku")

st.markdown("""
When launching a new product that doesn't exist in the system yet:
""")

st.subheader("Step 1: Create the SKU")
st.markdown("""
1. Go to **Product Directory**
2. Scroll down to the **Create New SKU** section
3. Fill in:
   - **SKU** — Unique identifier (e.g., `WYZECPANV4`)
   - **Product Name** — Display name (e.g., `Cam Pan v4`)
   - **Reference SKU** — An existing similar product to clone assumptions from (important!)
   - **Default MSRP / FOB / Tariff Rate** — Optional, pre-fills Pricing Tool inputs
4. Click **Create**

> **What "Reference SKU" does**: The system copies all per-SKU assumptions (return rates, outbound shipping, retail margins, product costs) from the reference product to the new SKU. This gives you a starting point — you can then customize the new SKU's assumptions individually.
""")

st.subheader("Step 2: Review & Customize Assumptions")
st.markdown("""
After creation, the new SKU inherits all assumptions from the Reference SKU. To customize:

1. Go to **Assumptions** section in the sidebar
2. Each page shows per-SKU data:
   - **Retail Margin** — PO Discount rates per channel
   - **Return Rate** — Return rates per channel
   - **Outbound Shipping** — Shipping costs per channel
   - **Product Costs** — Inbound freight, warehouse, FBA fee, product life
3. Find your new SKU and edit the values as needed
""")

st.subheader("Step 3: Price the New Product")
st.markdown("""
1. Go to **Pricing Tool** and select your new SKU
2. Set MSRP, FOB, Tariff
3. The tool uses the cloned (or customized) assumptions to calculate CPAM
4. Iterate on pricing until you find a target CPAM %
""")

# ===== CHANNEL MIX =====
st.divider()
st.header("Set Up Channel Mix", anchor="set-up-channel-mix")

st.markdown("""
Channel Mix determines the **weighted average CPAM** across all sales channels. Without it, you only see per-channel results.
""")

st.subheader("Manual Entry")
st.markdown("""
1. Go to **Channel Mix** page
2. Enter a percentage for each channel (must add up to ~100%)
3. Return to Pricing Tool to see the weighted average row in the summary

Example: If 40% of sales go through Amazon 1P and 30% through DTC US, set those channels accordingly.
""")

st.subheader("Smart Fill from Snowflake")
st.markdown("""
Instead of entering manually, you can pull historical channel mix data:

1. On the **Channel Mix** page, select a **Product Line** using the dropdown
   - **Quick Pick**: Uses the current SKU's product line or reference SKU's product line
   - **Manual Cascade**: Browse Product Group → Category → Line
2. Select a **time period** (e.g., last 12 months)
3. Click **Smart Fill** to auto-populate channel mix from historical revenue data
4. Adjust as needed after filling

> **Note**: Smart Fill requires Snowflake data to be synced. If no data appears, run a Snowflake Sync from the DB Admin page (local only).
""")

# ===== TEMPLATES =====
st.divider()
st.header("Save & Load Templates", anchor="save-load-templates")

st.markdown("""
Templates save a complete pricing scenario (inputs + assumptions + channel mix) for later recall.

**Save a Template:**
1. Set up your product, inputs, and channel mix on the Pricing Tool
2. Go to **Pricing Templates**
3. Enter a template name and click **Save**
4. The template stores: SKU, MSRP, FOB, Tariff, Promo settings, Channel Mix, and all resolved assumptions

**Load a Template:**
1. Go to **Pricing Templates**
2. Select a saved template from the list
3. Click **Load** — it restores all inputs and navigates you back to the Pricing Tool

> **Use case**: Save a "Launch Pricing" and "Post-Launch Pricing" template for the same SKU to compare scenarios.
""")

# ===== MANAGE ASSUMPTIONS =====
st.divider()
st.header("Manage Assumptions", anchor="manage-assumptions")

st.subheader("Per-SKU Assumptions (4 tables)")
st.markdown("""
These vary by SKU and sometimes by channel:

| Page | What You Edit | Granularity |
|------|--------------|-------------|
| **Retail Margin** | PO Discount Rate | Per-SKU × Per-Channel |
| **Return Rate** | Return rate | Per-SKU × Per-Channel |
| **Outbound Shipping** | Shipping cost per unit | Per-SKU × Per-Channel |
| **Product Costs** | Inbound freight, warehouse, FBA, product life | Per-SKU |

Changes are saved to the Azure SQL database (when connected) or applied in-session.
""")

st.subheader("Finance Assumptions (Global)")
st.markdown("""
The **Finance Assumptions** page manages global settings that apply across all SKUs:

- **Channel Terms** — Chargeback rate, total discount rate per channel
- **S&M Expenses** — Customer service rate, CC fee rate, marketing rate per channel
- **Static Assumptions** — EOS rate, cloud costs, UID, royalties

These are stored in Azure SQL admin tables and can only be edited when the database is connected.
""")

st.subheader("Assumption Resolution Priority")
st.code("""
Database Override  >  Cache Table  >  CSV File  >  Reference SKU Fallback  >  Default (0)
""", language=None)
st.markdown("""
The system checks each source in order. If a value is found, it's used. If not, it falls through to the next source.

- **Database Override**: Manual overrides set via DB Admin
- **Cache Table**: Data synced from CSV or edited by users
- **CSV File**: Original reference data files in `data/reference data/`
- **Reference SKU Fallback**: If the SKU has a Reference SKU, looks up that SKU's values
- **Default (0)**: If nothing found, assumes 0
""")

# ===== ADMIN TASKS =====
st.divider()
st.header("Admin Tasks", anchor="admin-tasks")

st.subheader("First-Time Setup")
st.markdown("""
1. **DB Admin** page → Paste your Azure SQL connection string → **Save & Connect**
2. Click **Initialize Schema** to create all database tables
3. Click **Sync CSV to Azure SQL** to load reference data into the database
4. (Optional) Configure Snowflake and run **Snowflake Sync** to pull live data
""")

st.subheader("Regular Data Refresh")
st.markdown("""
To update the app with the latest Snowflake data:

1. Open the app **locally** (Snowflake SSO requires a browser)
2. Go to **DB Admin** → Click **Sync Snowflake to Azure SQL**
3. This pulls: SKU mapping, return rates, outbound shipping costs, channel mix history
4. Data goes into Azure SQL cache tables — the online version can then read it
""")

st.subheader("Data Validation")
st.markdown("""
After Snowflake sync, review differences between your working data and fresh Snowflake data:

1. Go to **Data Validation** page
2. Two tabs: **Return Rate** and **Outbound Shipping**
3. For each conflict, choose:
   - **Keep Cache** — Keep your current working value
   - **Accept SF** — Update to the Snowflake value
   - **Manual** — Enter a custom value with a note
4. Use **Batch Mode** to resolve multiple rows at once (filter by channel or product line)
""")

st.subheader("Edit a Product")
st.markdown("""
On the **Product Directory** page:

- **Edit**: Click Edit next to a product to change its name, Reference SKU, MSRP, FOB, or tariff
  - Changing the **Reference SKU** triggers a warning — all assumptions will be re-cloned from the new reference
- **Delete**: Click Delete and type the SKU name to confirm. This removes the SKU and all its assumptions from all tables.
""")

# ===== FAQ =====
st.divider()
st.header("FAQ", anchor="faq")

faq = {
    "Why are all my CPAM values showing as 0?": (
        "Check that **MSRP** is not 0 on the Pricing Tool page. "
        "Also verify the product has assumptions loaded — go to Assumptions Loaded page to check."
    ),
    "Why don't I see a Weighted Average row?": (
        "You need to set **Channel Mix** first. Go to the Channel Mix page and enter percentages "
        "for at least one channel (or use Smart Fill)."
    ),
    "How do I update assumptions for a specific SKU?": (
        "Go to the relevant Assumptions page (Retail Margin, Return Rate, etc.), "
        "find your SKU, and edit the values directly. Changes save to the database."
    ),
    "What happens when I change a product's Reference SKU?": (
        "All 4 assumption tables (Retail Margin, Return Rate, Outbound Shipping, Product Costs) "
        "are deleted for that SKU and re-cloned from the new Reference SKU. "
        "Any customizations you made to the old assumptions will be lost."
    ),
    "Why can't I run Snowflake Sync online?": (
        "Snowflake uses SSO authentication which requires a browser popup. "
        "This only works locally. Run Snowflake Sync from your local app, "
        "and the data is stored in Azure SQL where the online version can read it."
    ),
    "How do I compare two pricing scenarios?": (
        "Use **Pricing Templates**. Save your first scenario as a template, "
        "adjust the inputs for the second scenario and save it as another template. "
        "You can switch between them to compare."
    ),
    "What are the 13 channels?": (
        "DTC US, DTC CA, TikTok Shop, Amazon 1P, Home Depot US, Home Depot CA, "
        "Best Buy, Costco, Costco.com, Amazon 3P, ACE, Walmart 1P, New Channel 2"
    ),
    "How do I add a brand new channel?": (
        "Channels are currently hard-coded in the system. Contact the app developer "
        "to add a new channel to the CHANNELS list in data_loader.py."
    ),
}

for q, a in faq.items():
    with st.expander(q):
        st.markdown(a)
