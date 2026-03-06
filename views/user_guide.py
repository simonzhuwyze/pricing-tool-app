"""
User Guide - Step-by-step instructions for using the Wyze Pricing Tool.
"""

import streamlit as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.ui_helpers import styled_header, styled_divider

styled_header("User Guide", "Step-by-step instructions for pricing existing products and onboarding new SKUs")

# ---------------------------------------------------------------------------
# Table of Contents
# ---------------------------------------------------------------------------
st.markdown("""
**Jump to:** [Quick Start](#quick-start) · [Price an Existing Product](#price-an-existing-product) · [Add a New SKU](#add-a-new-sku) · [Channel Mix](#set-up-channel-mix) · [Export & Save](#export-save) · [Manage Assumptions](#manage-assumptions) · [Admin Tasks](#admin-tasks) · [Roles & Permissions](#roles-permissions) · [FAQ](#faq)
""")

# ===== QUICK START =====
styled_divider(label="Quick Start", icon="rocket-takeoff-fill")
st.header("Quick Start", anchor="quick-start")

st.markdown("""
The Pricing Tool calculates **CPAM (Contribution Profit After Marketing)** for any Wyze product across 13 sales channels. Here's the core workflow:

1. **Select a product** on the Pricing Tool page (or Quick Select from Product Directory)
2. **Set your inputs** (MSRP, FOB, Tariff %, Promo settings)
3. **Set Channel Mix** to get a weighted average across channels
4. **Review CPAM** with Blended / Full Price / Promo views
5. **Export** a PDF report or **Save** as a template for later recall

All assumptions (return rates, shipping costs, channel terms, etc.) are auto-loaded from Azure SQL. You just provide the pricing inputs.
""")

st.subheader("Navigation Overview")
st.markdown("""
| Section | Pages | What It Does |
|---------|-------|-------------|
| **Product Directory** | Product Directory | Browse all SKUs, create/edit/delete products |
| **Pricing Tool** | Pricing Tool, Channel Mix, CPAM Calculator, Sensitivity, Assumptions, Export & Save | Core pricing workflow |
| **Reference** | Pricing Templates, Formula Reference, User Guide | Browse/load saved scenarios, view CPAM formulas |
| **Assumptions** | Retail Margin, Return Rate, Outbound Shipping, Product Costs, Finance | View and edit assumption data (editor+ role) |
| **Settings** | Data Validation, SF Raw Data, DB Admin, User Management | Data management and admin (role-gated) |
""")

st.info("Some sections (Assumptions, Settings) are only visible if your account has the required permissions. See [Roles & Permissions](#roles-permissions) below.")

# ===== PRICE AN EXISTING PRODUCT =====
styled_divider(label="Pricing Workflow", icon="currency-dollar")
st.header("Price an Existing Product", anchor="price-an-existing-product")

st.subheader("Step 1: Select Product")
st.markdown("""
1. Go to **Pricing Tool** (default landing page)
2. Use the **Product** dropdown to search and select your SKU
3. The tool displays the product name, Reference SKU, and product classification (Group / Line)
4. All per-SKU assumptions are **automatically loaded** from the database

> **Tip**: You can also select a product from the **Product Directory** page using the Quick Select feature, which links you directly to the Pricing Tool.

> **Not seeing a newly created SKU?** Click the **Refresh** button in the top-right corner of the Pricing Tool page to reload the product list from the database.
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

- **Promo Mix %** --- What percentage of units are sold under promotion (0--100%)
- **Quick Promo %** --- Discount off MSRP applied to all promo units

**Two promo modes:**
- If **Quick Promo % > 0**: A flat percentage discount is applied across all channels
- If **Quick Promo % = 0** and **Promo Mix > 0**: An expander appears where you can set per-channel absolute promo dollar amounts

**Blended CPAM** = Full Price CPAM x (1 - Promo Mix) + Promo CPAM x Promo Mix
""")

st.subheader("Step 4: Review CPAM Results")
st.markdown("""
The CPAM Summary table shows per-channel results. Use the view toggle:

- **Blended** --- Weighted combination of full price and promo (default, most useful)
- **Full Price** --- As if no promotion is running
- **Promo** --- As if all units are under promotion

**Key metrics:**
- **CPAM $** --- Dollar contribution profit after marketing per unit
- **CPAM %** --- CPAM as percentage of net revenue. Higher is better.
- **Gross Margin %** --- Profit before Sales & Marketing expenses
- **Weighted Avg** row --- Only appears when Channel Mix is set
""")

st.subheader("Step 5: Deep Dive (Optional)")
st.markdown("""
Use the sub-pages for more detail:

| Page | What It Shows |
|------|--------------|
| **Channel Mix** | Set channel distribution (manual or Smart Fill from Snowflake) |
| **CPAM Calculator** | Full waterfall breakdown per channel: Revenue, COGS, S&M, CPAM. Cross-view comparison of all 3 modes. |
| **Sensitivity Analysis** | Interactive charts showing how CPAM changes as MSRP or FOB varies (configurable step size and range) |
| **Assumptions Loaded** | All resolved assumptions for the current SKU, grouped by category, with source attribution |
| **Export & Save** | Generate PDF report or save the session as a reusable template |
""")

# ===== ADD A NEW SKU =====
styled_divider(label="New SKU", icon="plus-circle-fill")
st.header("Add a New SKU", anchor="add-a-new-sku")

st.markdown("""
When launching a new product that doesn't exist in the system yet:
""")

st.subheader("Step 1: Create the SKU")
st.markdown("""
1. Go to **Product Directory**
2. Expand the **Create New SKU** section at the bottom
3. Fill in the form:
   - **SKU** --- Unique identifier (e.g., `WYZECPANV4`)
   - **Product Name** --- Display name (e.g., `Cam Pan v4`)
   - **Reference SKU** --- An existing product to clone assumptions from (**required**)
   - **Default MSRP / FOB / Tariff Rate** --- Pre-fills Pricing Tool inputs
4. Click **Create SKU & Clone Assumptions**

> **What "Reference SKU" does**: The system copies all per-SKU assumptions (return rates, outbound shipping, retail margins, product costs) from the reference product to the new SKU. This gives you a starting point that you can then customize.
""")

st.subheader("Step 2: Review & Customize Assumptions")
st.markdown("""
After creation, the new SKU inherits all assumptions from the Reference SKU. To customize:

1. Go to **Assumptions** section in the sidebar (requires editor+ role)
2. Each page shows per-SKU data with Product Name and Reference SKU columns for context:
   - **Retail Margin** --- PO Discount rates per channel
   - **Return Rate** --- Return rates per channel
   - **Outbound Shipping** --- Shipping costs per channel
   - **Product Costs** --- Inbound freight, warehouse, FBA fee, product life
3. Find your new SKU and edit the values as needed
""")

st.subheader("Step 3: Price the New Product")
st.markdown("""
1. Go to **Pricing Tool** and select your new SKU (it appears immediately after creation)
2. Set MSRP, FOB, Tariff Rate
3. The tool uses the cloned (or customized) assumptions to calculate CPAM
4. Iterate on pricing until you find a target CPAM %
5. Save your scenario as a template via **Export & Save**
""")

# ===== CHANNEL MIX =====
styled_divider(label="Channel Mix", icon="bar-chart-fill")
st.header("Set Up Channel Mix", anchor="set-up-channel-mix")

st.markdown("""
Channel Mix determines the **weighted average CPAM** across all sales channels. Without it, you only see per-channel results with no weighted average row.
""")

st.subheader("Manual Entry")
st.markdown("""
1. Go to **Channel Mix** page (under Pricing Tool)
2. Enter a percentage for each channel (should add up to ~100%)
3. Return to Pricing Tool to see the weighted average row in the summary

Example: If 40% of sales go through Amazon 1P and 30% through DTC US, set those channels accordingly.
""")

st.subheader("Smart Fill from Snowflake")
st.markdown("""
Instead of entering manually, you can pull historical channel mix data:

1. On the **Channel Mix** page, select a **Product Line**:
   - **Quick Pick**: Uses the current SKU's product line (or its Reference SKU's product line)
   - **Manual Cascade**: Browse Product Group > Category > Line
2. Configure the **time period** (3--24 months of historical data)
3. Click **Smart Fill** to auto-populate channel percentages from historical revenue data
4. Review the **Channel Distribution** chart and **Yearly History** table
5. Adjust individual channel percentages as needed

> **Note**: Smart Fill requires Snowflake data to be synced. If no data appears, run a Snowflake Sync locally (see [Admin Tasks](#admin-tasks)).
""")

# ===== EXPORT & SAVE =====
styled_divider(label="Export & Save", icon="file-earmark-arrow-down-fill")
st.header("Export & Save", anchor="export-save")

st.subheader("Generate PDF Report")
st.markdown("""
Create a professional PDF pricing report from the **Export & Save** page:

1. Ensure you have a product selected with MSRP set on the Pricing Tool page
2. Go to **Export & Save** (under Pricing Tool)
3. Choose a **view mode** (Blended, Full Price, or Promo) for the report
4. Select which **sections** to include:
   - **CPAM Summary** --- Per-channel results table with key metrics
   - **CPAM Waterfall** --- Detailed breakdown (Revenue > COGS > S&M > CPAM) per channel
   - **Channel Mix** --- Distribution chart and percentages
   - **Sensitivity Analysis** --- MSRP and FOB sweep tables
   - **Assumptions Detail** --- Static assumptions and full resolution log
5. Click **Generate PDF Report** to download

The PDF includes product info (SKU, name, product group/line, reference SKU) and a timestamp.
""")

st.subheader("Save as Template")
st.markdown("""
Templates save a complete pricing scenario for later recall:

1. On the **Export & Save** page, scroll to the **Save Template** section
2. Enter a **Template Name** and optional **Notes**
3. Click **Save Template**

The template stores: SKU, MSRP, FOB, Tariff, Promo settings, Channel Mix percentages, and a snapshot of all resolved assumptions.

> **Tip**: Save a "Launch Pricing" and "Post-Launch Pricing" template for the same SKU to compare scenarios.
""")

st.subheader("Load a Saved Template")
st.markdown("""
1. Go to **Pricing Templates** (under Reference)
2. Browse templates by SKU or user, or enter a Template ID
3. Click **Load Template** --- it restores all inputs, channel mix, and navigates you to the Pricing Tool

You can also view template details (inputs, channel mix snapshot, assumptions) and delete templates you no longer need.
""")

# ===== MANAGE ASSUMPTIONS =====
styled_divider(label="Assumptions", icon="sliders")
st.header("Manage Assumptions", anchor="manage-assumptions")

st.subheader("Per-SKU Assumptions (4 tables)")
st.markdown("""
These vary by SKU and sometimes by channel. Each page shows Product Name and Reference SKU columns for context.

| Page | What You Edit | Granularity |
|------|--------------|-------------|
| **Retail Margin** | PO Discount Rate | Per-SKU x Per-Channel |
| **Return Rate** | Return rate | Per-SKU x Per-Channel |
| **Outbound Shipping** | Shipping cost per unit ($) | Per-SKU x Per-Channel |
| **Product Costs** | Inbound freight, warehouse, FBA, product life | Per-SKU |

All changes are saved directly to Azure SQL.

> **Access**: Requires **editor** or **admin** role. Viewers see the Assumptions Loaded page (read-only) but cannot access individual assumption editors.
""")

st.subheader("Finance Assumptions (Global)")
st.markdown("""
The **Finance Assumptions** page manages global settings that apply across all SKUs:

| Tab | What You Edit |
|-----|--------------|
| **Channel Terms** | Chargeback rate, total discount rate, and other terms per channel |
| **S&M Expenses** | Customer service rate, credit card fee rate, marketing rate per channel |
| **Static Assumptions** | EOS rate, monthly cloud cost, UID, royalties |

These are stored in Azure SQL admin tables.
""")

st.subheader("Assumption Resolution Priority")
st.markdown("""
When the Pricing Tool loads assumptions for a SKU, it checks sources in this order:
""")
st.code("""
Database (cache tables)  >  Reference SKU Fallback  >  Default (0)
""", language=None)
st.markdown("""
1. **Database**: Values stored in Azure SQL cache tables (from CSV import or manual edits)
2. **Reference SKU Fallback**: If the SKU has a Reference SKU and no direct value is found, the Reference SKU's values are used
3. **Default (0)**: If nothing is found, assumes 0

You can see exactly which source was used for each assumption on the **Assumptions Loaded** page (source column shows `cache`, `ref_sku`, or `default`).
""")

# ===== ADMIN TASKS =====
styled_divider(label="Admin Tasks", icon="gear-fill")
st.header("Admin Tasks", anchor="admin-tasks")

st.subheader("First-Time Setup")
st.markdown("""
1. **DB Admin** page > Paste your Azure SQL connection string > **Save & Connect**
2. Click **Initialize Schema** to create all database tables
3. Click **Sync CSV to Azure SQL** to load reference data into the database
4. (Optional) Run **Snowflake Sync** locally to pull live data
""")

st.subheader("Regular Data Refresh (Snowflake Sync)")
st.markdown("""
To update the app with the latest Snowflake data:

1. Open the app **locally** (Snowflake uses SSO authentication which requires a browser)
2. Go to **DB Admin** > Click **Sync Snowflake to Azure SQL**
3. This pulls: SKU mapping, return rates, outbound shipping costs, channel mix history
4. Data goes into Azure SQL --- the deployed version can then read it

> **Note**: Snowflake Sync is hidden on Azure (headless server cannot open a browser for SSO). Use the local app or `run_sync.py` CLI tool instead.
""")

st.subheader("Data Validation")
st.markdown("""
After Snowflake sync, review differences between your working data and fresh Snowflake data:

1. Go to **Data Validation** page (requires validate_data permission)
2. Two conflict types: **Return Rate** and **Outbound Shipping**
3. **Individual resolution**: For each conflict row, choose:
   - **Keep Cache** --- Keep your current working value
   - **Accept SF** --- Update to the Snowflake value
   - **Manual** --- Enter a custom value with a note
4. **Batch resolution**: Filter by channel or product line, select multiple rows, and apply a single action to all selected conflicts
5. All resolution decisions are logged for audit purposes
""")

st.subheader("Edit / Delete a Product")
st.markdown("""
On the **Product Directory** page (requires create_sku permission):

**Edit:**
1. Select a SKU from the **Edit Product** dropdown
2. Modify fields: Product Name, Reference SKU, Default MSRP, FOB, Tariff Rate
3. If you change the **Reference SKU**, a warning appears --- all 4 assumption tables will be overwritten with the new reference's values. You must check the confirmation box.
4. Click **Save Changes**

**Delete:**
1. Select a SKU and expand the **Delete this SKU** section
2. Type the exact SKU name to confirm
3. This permanently removes the SKU from the Product Directory **and** all associated assumption data (PO Discount, Return Rate, Outbound Shipping, Product Costs)
""")

st.subheader("SF Raw Data Viewer")
st.markdown("""
The **SF Raw Data** page lets you browse the cached Snowflake data stored in Azure SQL:
- SKU Mapping (product group, category, line)
- Return Rates (by product line and sub-channel)
- Outbound Shipping (by SKU and channel)
- Channel Mix History (historical revenue by period, channel, and product)

This is read-only --- useful for verifying what data was synced from Snowflake.
""")

st.subheader("User Management")
st.markdown("""
The **User Management** page (admin only) shows the role and permission structure:

| Role | Permissions |
|------|------------|
| **admin** | All permissions (view, edit, create, validate, sync, db_admin) |
| **editor** | View pricing, edit assumptions, create SKUs |
| **viewer** | View pricing only |

When authentication is enabled (AUTH_ENABLED=true), users are assigned roles via the `user_roles` database table. The navigation sidebar automatically shows or hides pages based on the user's permissions.
""")

# ===== ROLES & PERMISSIONS =====
styled_divider(label="Roles & Permissions", icon="shield-lock-fill")
st.header("Roles & Permissions", anchor="roles-permissions")

st.markdown("""
The app supports **JumpCloud SSO** authentication (configurable via AUTH_ENABLED environment variable).

**When AUTH_ENABLED = false** (development mode): All features are available, user is `local_user`.

**When AUTH_ENABLED = true** (production): Users must sign in via JumpCloud SSO, and page access is controlled by roles.
""")

st.markdown("""
| Permission | Who Has It | What It Controls |
|------------|-----------|-----------------|
| `view_pricing` | All roles | Access to Pricing Tool, Product Directory, Reference pages |
| `edit_assumptions` | Editor, Admin | Access to Assumption editor pages (Retail Margin, Return Rate, etc.) |
| `create_sku` | Editor, Admin | Create, edit, and delete products in Product Directory |
| `validate_data` | Admin | Access to Data Validation page |
| `sync_snowflake` | Admin | Access to SF Raw Data viewer |
| `db_admin` | Admin | Access to DB Admin and User Management pages |
""")

# ===== FAQ =====
styled_divider(label="FAQ", icon="question-circle-fill")
st.header("FAQ", anchor="faq")

faq = {
    "Why are all my CPAM values showing as 0?": (
        "Check that **MSRP** is not $0 on the Pricing Tool page. "
        "Also verify the product has assumptions loaded --- go to the **Assumptions Loaded** page to check."
    ),
    "Why don't I see a Weighted Average row?": (
        "You need to set **Channel Mix** first. Go to the Channel Mix page and enter percentages "
        "for at least one channel (or use Smart Fill from Snowflake data)."
    ),
    "I just created a new SKU but can't find it in the Pricing Tool?": (
        "The Pricing Tool caches the product list for performance. "
        "Click the **Refresh** button in the top-right corner of the Pricing Tool page "
        "to reload the product list from the database."
    ),
    "How do I update assumptions for a specific SKU?": (
        "Go to the relevant **Assumptions** page (Retail Margin, Return Rate, etc.) in the sidebar, "
        "find your SKU, and edit the values directly. Changes save to Azure SQL immediately. "
        "Requires editor or admin role."
    ),
    "What happens when I change a product's Reference SKU?": (
        "All 4 assumption tables (Retail Margin, Return Rate, Outbound Shipping, Product Costs) "
        "are **deleted** for that SKU and **re-cloned** from the new Reference SKU. "
        "Any customizations you made to the old assumptions will be lost."
    ),
    "Why can't I run Snowflake Sync on the deployed app?": (
        "Snowflake uses SSO authentication which requires a browser popup. "
        "This only works locally. Run Snowflake Sync from your local app or use the `run_sync.py` CLI tool. "
        "The synced data is stored in Azure SQL where the deployed version can read it."
    ),
    "How do I compare two pricing scenarios?": (
        "Use **Templates**. Save your first scenario from the Export & Save page, "
        "adjust the inputs for the second scenario and save it as another template. "
        "Load either template from the Pricing Templates page to switch between them."
    ),
    "What are the 13 channels?": (
        "DTC US, DTC CA, TikTok Shop, Amazon 1P, Home Depot US, Home Depot CA, "
        "Best Buy, Costco, Costco.com, Amazon 3P, ACE, Walmart 1P, New Channel 2"
    ),
    "How do I generate a PDF report?": (
        "Go to **Export & Save** under Pricing Tool. Select which sections to include "
        "(Summary, Waterfall, Channel Mix, Sensitivity, Assumptions), choose a view mode, "
        "and click **Generate PDF Report**."
    ),
    "Why do some sidebar sections not show for me?": (
        "The sidebar is filtered by your role. **Viewers** only see Product Directory, Pricing Tool, and Reference. "
        "**Editors** also see Assumptions. **Admins** see everything including Settings. "
        "Contact an admin if you need elevated access."
    ),
    "Where does the Formula Reference come from?": (
        "The **Formula Reference** page documents the complete CPAM calculation methodology, "
        "including Net Revenue, Cost of Goods, Sales & Marketing, and all constants used by the engine. "
        "It reflects the logic in `cpam_engine.py`."
    ),
}

for q, a in faq.items():
    with st.expander(q):
        st.markdown(a)
