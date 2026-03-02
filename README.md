# Wyze Pricing Tool

> Internal FP&A pricing analysis platform replacing SharePoint Lists + Power BI workflows.

A multi-page **Streamlit** web application that centralizes product pricing, CPAM (Cost/Profit Analysis Model) calculations, assumption management, and Snowflake data validation into a single interactive tool.

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Getting Started](#getting-started)
- [Configuration](#configuration)
- [Deployment](#deployment)
- [Project Structure](#project-structure)
- [Data Flow](#data-flow)
- [Database Schema](#database-schema)
- [Pages Reference](#pages-reference)
- [Channels & Mapping](#channels--mapping)
- [Common Issues & Troubleshooting](#common-issues--troubleshooting)

---

## Overview

The Wyze Pricing Tool is an internal application built for the FP&A team to:

- **Analyze product profitability** across 13 sales channels (DTC, Amazon, Retail, etc.)
- **Calculate CPAM** (Cost/Profit Analysis Model) with full waterfall breakdowns
- **Manage pricing assumptions** with a multi-source resolution chain (Database > CSV > Reference SKU > Default)
- **Validate data** by comparing working cache against live Snowflake snapshots
- **Save & load pricing templates** for scenario modeling and historical reference

---

## Features

### Pricing & Analysis
- **CPAM Calculator** - Full Price / Promotional / Blended CPAM with waterfall visualization
- **Channel Mix Editor** - Allocate revenue across 13 channels, with smart-fill from Snowflake historical data
- **Sensitivity Analysis** - MSRP and FOB sweep heatmaps via Plotly

### Data Management
- **Product Directory** - Full CRUD: browse, create (with assumption cloning), edit (ref SKU change triggers reclone warning), delete (type-to-confirm, cascades to all assumption tables)
- **5 Assumption Editors** - Retail Margin, Return Rate, Outbound Shipping, Product Costs, Finance Assumptions (all SKU pages show Product Name + Reference SKU for context)
- **Pricing Templates** - Save/load complete pricing scenarios (assumptions + channel mix + inputs)

### Data Integration
- **Snowflake Sync** - Pull SKU mapping, return rates, outbound shipping, and channel mix data
- **Data Validation** - Side-by-side comparison of cache vs. Snowflake; batch & individual conflict resolution
- **SF Raw Data Viewer** - Browse cached Snowflake data with CSV export

### Administration
- **DB Admin** - Connection testing, schema initialization, CSV sync, Snowflake sync triggers
- **SSO Authentication** - JumpCloud OIDC integration (disabled by default for local development)

---

## Architecture

```
                                   +------------------+
                                   |   Streamlit UI   |
                                   |   (15 pages)     |
                                   +--------+---------+
                                            |
                      +---------------------+---------------------+
                      |                     |                     |
              +-------v--------+   +--------v--------+   +-------v--------+
              | cpam_engine    |   | assumption_     |   | channel_mix_   |
              | (calculations) |   | resolver        |   | engine         |
              +-------+--------+   | (DB>CSV>Ref>0)  |   | (smart fill)   |
                      |            +--------+--------+   +-------+--------+
                      |                     |                     |
                      +---------------------+---------------------+
                                            |
                      +---------------------+---------------------+
                      |                                           |
              +-------v--------+                         +--------v--------+
              |  database.py   |                         | snowflake_sync  |
              |  (Azure SQL)   |                         | (Snowflake SSO) |
              +-------+--------+                         +--------+--------+
                      |                                           |
              +-------v--------+                         +--------v--------+
              |  Azure SQL DB  |                         |   Snowflake DW  |
              |  (23 tables)   |                         |  (source data)  |
              +----------------+                         +-----------------+
```

### Core Modules

| Module | Purpose |
|--------|---------|
| `core/database.py` | Azure SQL connection, DDL (23 tables), CRUD, batch validation, SKU update/reclone/delete |
| `core/data_loader.py` | CSV loading, channel definitions, subchannel mapping |
| `core/cpam_engine.py` | CPAM calculation engine (translated from DAX) |
| `core/assumption_resolver.py` | Multi-source assumption resolution chain |
| `core/channel_mix_engine.py` | Channel mix calculations, Snowflake smart-fill |
| `core/template_manager.py` | Pricing template save/load/delete |
| `core/snowflake_sync.py` | Snowflake data sync (4 sync functions) |
| `core/auth.py` | JumpCloud OIDC SSO authentication |

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Frontend | [Streamlit](https://streamlit.io/) (multi-page app) |
| Visualization | [Plotly](https://plotly.com/) |
| Database | Azure SQL Server (ODBC Driver 17/18) |
| Data Warehouse | Snowflake (SSO via externalbrowser) |
| Authentication | JumpCloud OIDC SSO |
| Language | Python 3.12 |
| Containerization | Docker |

---

## Getting Started

### Prerequisites

- **Python 3.12+**
- **ODBC Driver 17 or 18** for SQL Server ([Download](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server))
- Access to **Azure SQL** and **Snowflake** (credentials from FP&A team)

### Installation

1. **Clone or copy the project**
   ```bash
   cd "C:\Users\<you>\Documents\Pricing Tool"
   # copy pricing-tool-app/ to your local machine
   ```

2. **Create a virtual environment**
   ```bash
   cd pricing-tool-app
   python -m venv .venv
   .venv\Scripts\activate        # Windows
   # source .venv/bin/activate   # macOS/Linux
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables** (see [Configuration](#configuration))
   ```bash
   copy .env.example .env
   # Edit .env with your credentials
   ```

5. **Run the app**
   ```bash
   streamlit run app.py
   ```

6. **First-time setup** - Go to **Settings > DB Admin** page to:
   - Test database connection
   - Initialize schema (creates 23 tables)
   - Sync CSV reference data to cache tables
   - (Optional) Run Snowflake sync

### CLI Snowflake Sync

For headless sync without the UI (opens browser for SSO):

```bash
python run_sync.py
```

---

## Configuration

### Environment Variables (`.env`)

```env
# Azure SQL Database
AZURE_SQL_SERVER=pricing-tool-server-uswest.database.windows.net
AZURE_SQL_DATABASE=pricing-tool-db
AZURE_SQL_USERNAME=<your-username>
AZURE_SQL_PASSWORD=<your-password>

# Snowflake
SNOWFLAKE_ACCOUNT=ELDEWGA-HHA08189
SNOWFLAKE_USER=<your-email>
SNOWFLAKE_WAREHOUSE=<warehouse-name>
SNOWFLAKE_DATABASE=<database-name>
SNOWFLAKE_SCHEMA=<schema-name>

# Authentication (optional - disabled by default)
AUTH_ENABLED=false
JUMPCLOUD_CLIENT_ID=<client-id>
JUMPCLOUD_CLIENT_SECRET=<client-secret>
JUMPCLOUD_ORG_ID=<org-id>
APP_URL=http://localhost:8501
```

> **Important:** Never commit the `.env` file. Add it to `.gitignore`.

---

## Deployment

### Option 1: Docker

```bash
docker build -t wyze-pricing-tool .
docker run -p 8501:8501 --env-file .env wyze-pricing-tool
```

### Option 2: Azure App Service

Set `startup.sh` as the startup command in Azure App Service (Linux):

```bash
bash startup.sh
```

The script will:
1. Install ODBC Driver 17 if not present
2. Install Python dependencies from `requirements.txt`
3. Start Streamlit on `0.0.0.0:${PORT:-8501}`

---

## Project Structure

```
pricing-tool-app/
├── app.py                          # Entry point: 5 nav groups, session state init
├── run_sync.py                     # CLI tool for headless Snowflake sync
├── requirements.txt                # 9 Python dependencies
├── Dockerfile                      # Python 3.12 + ODBC 17 container
├── startup.sh                      # Azure App Service startup script
├── .env                            # Credentials (not committed)
│
├── core/                           # Business logic modules
│   ├── database.py                 # Azure SQL: DDL, CRUD, validation, SKU CRUD (~1220 lines)
│   ├── data_loader.py              # CSV loading, channel definitions (405 lines)
│   ├── cpam_engine.py              # CPAM calculation engine (420 lines)
│   ├── assumption_resolver.py      # DB > CSV > ref SKU > default (557 lines)
│   ├── channel_mix_engine.py       # Smart-fill from Snowflake (221 lines)
│   ├── template_manager.py         # Template CRUD (265 lines)
│   ├── snowflake_sync.py           # 4 Snowflake sync functions (425 lines)
│   └── auth.py                     # JumpCloud OIDC SSO (305 lines)
│
├── pages/                          # Streamlit page files
│   ├── product_directory.py        # SKU browser, create/edit/delete (~345 lines)
│   ├── pricing_tool_main.py        # Main pricing tool page
│   ├── pricing_tool_cpam.py        # CPAM waterfall breakdown
│   ├── pricing_tool_channel_mix.py # Channel mix editor
│   ├── pricing_tool_sensitivity.py # Sensitivity heatmaps
│   ├── pricing_tool_assumptions.py # Per-SKU assumption viewer
│   ├── pricing_templates.py        # Template management
│   ├── assumptions_finance.py      # Finance assumptions (Azure SQL only)
│   ├── assumptions_outbound_shipping.py
│   ├── assumptions_product_costs.py
│   ├── assumptions_retail_margin.py
│   ├── assumptions_return_rate.py
│   ├── data_validation.py          # Cache vs Snowflake comparison (731 lines)
│   ├── sf_raw_viewer.py            # Snowflake raw data browser
│   ├── db_admin.py                 # DB connection, schema, sync controls
│   └── _old_backup/                # Archived legacy page files
│
├── data/
│   └── reference data/             # 8 CSV source files
│       ├── Product Directory.csv
│       ├── Input_SKU_CostAssumptions.csv
│       ├── Input_SKU_Retail Margin.csv
│       ├── Input_SKU_Return Rate.csv
│       ├── Input_SKU_Outbound Shipping.csv
│       ├── Static_Cost Assumptions.csv
│       ├── Static_Channel Terms.csv
│       └── Static_Sales & Marketing Expenses.csv
│
└── .streamlit/
    └── config.toml                 # Streamlit configuration
```

**Codebase stats:** 25 active Python files, ~9,500 lines of code.

---

## Data Flow

```
 ┌──────────────────────────────────────────────────────────────────────┐
 │                        DATA SOURCES                                  │
 │                                                                      │
 │  8 CSV Files (reference data/)          Snowflake Data Warehouse     │
 │  ─────────────────────────────          ────────────────────────     │
 │  Product Directory                      SKU Mapping                  │
 │  Cost Assumptions                       Return Rates (by product     │
 │  Retail Margin                            line + sub_channel)        │
 │  Return Rate                            Outbound Shipping (3 ch.)   │
 │  Outbound Shipping                      Channel Mix (historical)    │
 │  Static Cost Assumptions                                             │
 │  Channel Terms                                                       │
 │  S&M Expenses                                                        │
 └────────────┬──────────────────────────────────────┬─────────────────┘
              │ sync_csv_to_cache()                   │ 4 sync functions
              ▼                                       ▼
 ┌────────────────────────────┐    ┌────────────────────────────────────┐
 │   CACHE TABLES (working)   │    │   SNAPSHOT TABLES (from Snowflake) │
 │   ────────────────────────  │    │   ────────────────────────────── │
 │   cache_product_directory   │    │   cache_return_rate              │
 │   cache_cost_assumptions    │    │   cache_outbound_shipping_sf     │
 │   cache_outbound_shipping   │    │   cache_sku_mapping              │
 │   cache_return_rate_sku     │    │   cache_channel_mix              │
 │   cache_po_discount         │    │                                  │
 │   cache_channel_terms       │    │   (SF sync NEVER auto-overwrites │
 │   cache_sm_expenses         │    │    working cache tables)         │
 │   cache_static_assumptions  │    │                                  │
 │   cache_channel_mix         │    │                                  │
 └──────────┬─────────────────┘    └──────────────┬────────────────────┘
            │                                      │
            │         ┌────────────────────┐       │
            └────────►│  DATA VALIDATION   │◄──────┘
                      │  ────────────────  │
                      │  Compare cache vs  │
                      │  SF, batch/single  │
                      │  resolution        │
                      └────────┬───────────┘
                               │ MERGE resolved values
                               ▼
                      ┌────────────────────┐
                      │  ASSUMPTION        │
                      │  RESOLVER          │
                      │  ────────────────  │
                      │  DB > CSV > Ref    │
                      │  SKU > Default(0)  │
                      └────────┬───────────┘
                               │
                               ▼
                      ┌────────────────────┐
                      │  CPAM ENGINE       │
                      │  ────────────────  │
                      │  Full / Promo /    │
                      │  Blended calcs     │
                      └────────────────────┘
```

### Key Design Decisions

- **SF sync does NOT auto-overwrite cache.** Snowflake data is written to separate snapshot tables (`cache_return_rate`, `cache_outbound_shipping_sf`). Users must review and resolve differences on the Data Validation page.
- **SKU naming mismatch.** CSV files use user-defined SKU names (e.g., "Battery Cam Solar"). Snowflake uses internal codes (e.g., "WYZECOP"). Matching strategy: direct SKU match first, then fallback via `reference_sku` from `cache_product_directory`.
- **Return rate unit conversion.** Snowflake stores percentages (2.02 = 2.02%), CSVs store decimals (0.0202). Division by 100 is required when comparing.
- **Product Directory CRUD cascading.** Editing a product's `reference_sku` warns the user and triggers a reclone of all 4 assumption tables. Deleting a SKU requires typing the SKU name to confirm and cascades deletion to all assumption tables.
- **Assumption page context.** All 4 SKU assumption pages (Return Rate, Outbound Shipping, Product Costs, Retail Margin) display Product Name and Reference SKU columns alongside the data for user context.

---

## Database Schema

**23 Azure SQL tables** organized into 5 categories:

### Admin Tables (Finance - editable only through UI)
| Table | Purpose |
|-------|---------|
| `admin_channel_records` | Channel revenue records |
| `admin_channel_terms` | Per-channel discount/term fields |
| `admin_sm_expenses` | Per-channel S&M expense rates |
| `admin_static_assumptions` | Global cost assumptions (EOS, UID, Cloud, Royalties) |

### Cache Tables (from CSV / user edits - the "working" data)
| Table | Purpose |
|-------|---------|
| `cache_product_directory` | SKU master list with reference SKU mapping |
| `cache_cost_assumptions` | Per-SKU: inbound freight, warehouse, FBA, product life |
| `cache_outbound_shipping` | Per-SKU per-channel: shipping cost (83 SKUs x 13 channels) |
| `cache_return_rate_sku` | Per-SKU per-channel: return rate (decimal) |
| `cache_po_discount` | Per-SKU per-channel: PO discount rate |
| `cache_channel_terms` | Per-channel: 10 discount/term fields |
| `cache_sm_expenses` | Per-channel: CC fee, customer service, marketing |
| `cache_static_assumptions` | Global static cost fields |
| `cache_channel_mix` | Revenue allocation by period/channel/product |
| `cache_sku_mapping` | Product group/category/line mapping |

### Snapshot Tables (from Snowflake - read-only comparison data)
| Table | Purpose |
|-------|---------|
| `cache_return_rate` | SF return rates (product_line + sub_channel, percentage form) |
| `cache_outbound_shipping_sf` | SF shipping costs (internal SKU codes, 3 channels only) |

### Pricing Template Tables
| Table | Purpose |
|-------|---------|
| `pricing_templates` | Template metadata (name, SKU, timestamp) |
| `pricing_template_assumptions` | Snapshot of assumptions at save time |
| `pricing_template_channel_mix` | Snapshot of channel mix at save time |

### System Tables
| Table | Purpose |
|-------|---------|
| `sync_metadata` | Last sync timestamps per data source |
| `user_overrides` | User override values (legacy, replaced by direct cache edits) |
| `override_audit_log` | Audit trail for override changes |
| `validation_log` | All data validation decisions (keep cache / accept SF) |

---

## Pages Reference

### Navigation Structure

| Group | Page | Description |
|-------|------|-------------|
| **Product Directory** | Product Directory | Full CRUD: browse, create (clone from ref SKU), edit (ref SKU change → reclone), delete (type-to-confirm, cascades) |
| **Pricing Tool** | Pricing Tool | Select SKU, set MSRP/FOB/tariff/promo inputs |
| | CPAM Calculator | Full/Promo/Blended CPAM waterfall breakdown |
| | Channel Mix | Allocate revenue across channels, smart-fill from SF |
| | Sensitivity Analysis | MSRP & FOB sweep heatmaps |
| | Assumptions Loaded | View resolved assumptions per SKU with source attribution |
| **Pricing Template** | Pricing Templates | Save, load, browse, delete pricing scenarios |
| **Assumptions** | Retail Margin | Per-SKU per-channel PO discount rates (with Product Name + Ref SKU context) |
| | Return Rate | Per-SKU per-channel return rates (with Product Name + Ref SKU context) |
| | Outbound Shipping | Per-SKU per-channel shipping costs (with Product Name + Ref SKU context) |
| | Product Costs | Per-SKU: inbound freight, warehouse, FBA, product life (with Product Name + Ref SKU context) |
| | Finance Assumptions | Channel records, terms, static costs, S&M (Azure SQL only) |
| **Settings** | DB Admin | Connection test, schema init, CSV sync, SF sync |
| | Data Validation | Cache vs Snowflake comparison & conflict resolution |
| | SF Raw Data | Browse cached Snowflake data, CSV export |

---

## Channels & Mapping

### 13 Standard Channels

| # | Channel | Notes |
|---|---------|-------|
| 1 | DTC US | Direct to consumer (Wyze.com US) |
| 2 | DTC CA | Direct to consumer (Wyze.com Canada) |
| 3 | TikTok Shop | Social commerce |
| 4 | Amazon 1P | Amazon Vendor Central |
| 5 | Home Depot US | Retail |
| 6 | Home Depot CA | Retail (Canada) |
| 7 | Best Buy | Retail |
| 8 | Costco | Retail (in-store) |
| 9 | Costco.com | Retail (online) |
| 10 | Amazon 3P | Amazon Seller Central |
| 11 | ACE | Retail |
| 12 | Walmart 1P | Retail |
| 13 | New Channel 2 | Placeholder for future expansion |

### Snowflake Subchannel Mapping

Snowflake uses various sub_channel names that must be normalized to the 13 standard channels:

| Snowflake Name(s) | Maps To |
|--------------------|---------|
| `Wyze.com`, `Wyze.com US`, `DTC`, `DTC US` | DTC US |
| `Wyze.com CA`, `DTC CA` | DTC CA |
| `TikTok`, `TikTok Shop` | TikTok Shop |
| `Amazon 1P`, `Amazon Vendor Central` | Amazon 1P |
| `Amazon 3P`, `Amazon Seller Central` | Amazon 3P |
| `Home Depot`, `Home Depot US` | Home Depot US |
| `Home Depot CA`, `Home Depot Canada` | Home Depot CA |
| `Best Buy` | Best Buy |
| `Costco` | Costco |
| `Costco.com` | Costco.com |
| `ACE` | ACE |
| `Walmart`, `Walmart 1P` | Walmart 1P |

---

## Common Issues & Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| `st.Page` icon not showing | Using `:shortcode:` format | Use Unicode emoji characters directly (e.g., `"📊"` not `":chart:"`) |
| Duplicate page pathname error | Old numbered files (e.g., `1_home.py`) in `pages/` | Move old files to `pages/_old_backup/` |
| `UnicodeEncodeError` on Windows | Python `cp1252` encoding | Use ASCII-safe output in test/print statements |
| Reference SKU shows "nan" | Missing `pd.notna()` check | Always guard with `pd.notna(ref_raw)` before `str()` |
| CPAM values formatted wrong | Using `abs(x) <= 1.5` heuristic | Use explicit `format_type` per field (`$` / `pct` / `mix`) |
| SF shipping overwrites cache | Writing to wrong table | SF sync must write to `cache_outbound_shipping_sf` ONLY |
| SKU not matching SF data | CSV uses product names, SF uses internal codes | Match via direct SKU first, then `reference_sku` fallback |
| Return rates don't match | SF=percentage, CSV=decimal | Divide SF values by 100 when comparing (2.02% → 0.0202) |
| ODBC driver not found | Missing SQL Server driver | Install ODBC Driver 17 or 18; `database.py` auto-detects |

---

## Session State

The app maintains these session state variables (initialized in `app.py`):

| Key | Type | Default | Purpose |
|-----|------|---------|---------|
| `selected_sku` | `str \| None` | `None` | Currently selected SKU |
| `user_inputs` | `dict` | All `0.0` | MSRP, FOB, tariff_rate, promotion_mix, promo_percentage |
| `channel_mix` | `dict` | All `0.0` | Revenue allocation per channel (13 keys) |
| `resolved_assumptions` | `object \| None` | `None` | Populated by assumption_resolver |
| `current_user` | `str` | `"local_user"` | Email from SSO, or stub for local dev |

---

## Dependencies

```
streamlit>=1.40
pandas>=2.2
plotly>=5.22
openpyxl>=3.1
pyodbc>=5.0
sqlalchemy>=2.0
snowflake-connector-python>=3.0
requests>=2.31
authlib>=1.3
```

---

*Built by Wyze FP&A Team | Internal Use Only*
