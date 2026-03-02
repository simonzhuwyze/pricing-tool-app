# Wyze Pricing Tool

## Overview
Streamlit web app (Python 3.12) for FP&A product pricing. Replaces SharePoint Lists + Power BI.

## Language
- Conversation with user: Chinese
- Code & UI: English

## Architecture
- Entry: `app.py` (5 nav groups, 15 pages)
- Core modules: `core/` (9 files: database, data_loader, cpam_engine, assumption_resolver, channel_mix_engine, template_manager, snowflake_sync, auth)
- Pages: `pages/` (15 files)
- Data: `data/reference data/` (8 CSVs)
- DB: Azure SQL (23 tables, DDL in database.py INIT_SQL)
- Snowflake: read-only source for validation comparisons

## Critical Rules
1. **NEVER modify `core/cpam_engine.py`** - calculation logic is verified correct
2. **NEVER auto-merge SF data into cache tables** - users resolve diffs on Data Validation page
3. **SF writes to `_sf` suffix tables only** (e.g. `cache_outbound_shipping_sf`)
4. **SKU naming**: CSV = user-defined names, SF = internal codes. Match: direct SKU first, then reference_sku fallback
5. **Return rate units**: SF = percentage (2.02), CSV = decimal (0.0202). Divide SF by 100
6. **Assumption resolution order**: DB > CSV > Reference SKU fallback > default(0)
7. **All changes must sync to MEMORY.md** at `~/.claude/projects/.../memory/MEMORY.md`
8. **Streamlit icons**: Use Unicode emoji chars, NOT `:shortcode:` format
9. **Reference SKU NaN**: Always check `pd.notna()` before converting to string

## 13 Standard Channels
DTC US, DTC CA, TikTok Shop, Amazon 1P, Home Depot US, Home Depot CA, Best Buy, Costco, Costco.com, Amazon 3P, ACE, Walmart 1P, New Channel 2

## Key Files
| Module | File | Purpose |
|--------|------|---------|
| DB | `core/database.py` | Azure SQL DDL, CRUD, validation, SKU cascade |
| Loader | `core/data_loader.py` | CSV loading, CHANNELS, SUBCHANNEL_MAP |
| Calc | `core/cpam_engine.py` | CPAM calculator (DO NOT MODIFY) |
| Resolve | `core/assumption_resolver.py` | DB>CSV>RefSKU>default chain |
| Sync | `core/snowflake_sync.py` | SF sync to _sf tables only |
| Validate | `pages/data_validation.py` | Cache vs SF comparison & resolution |
| Directory | `pages/product_directory.py` | SKU CRUD with cascade |

## Testing
- Run app: `streamlit run app.py`
- Syntax check: `python -c "import ast; ast.parse(open('file.py').read())"`
- No test framework configured yet
