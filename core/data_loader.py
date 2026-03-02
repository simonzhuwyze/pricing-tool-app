"""
Data Loader Module
Loads pricing data from reference CSV files in data/reference data/.
Provides fallback data source when Azure SQL is unavailable.
"""

import pandas as pd
from pathlib import Path

# Base path to reference data files
DATA_ROOT = Path(__file__).parent.parent / "data" / "reference data"

# Standard channel ordering (from Power BI model)
CHANNELS = [
    "DTC US", "DTC CA", "TikTok Shop",
    "Amazon 1P", "Home Depot US", "Home Depot CA",
    "Best Buy", "Costco", "Costco.com",
    "Amazon 3P", "ACE", "Walmart 1P", "New Channel 2",
]

# Retail channels (those with Channel Terms / PO Discount)
RETAIL_CHANNELS = [
    "Amazon 1P", "Home Depot US", "Home Depot CA",
    "Best Buy", "Amazon 3P", "ACE", "Walmart 1P", "New Channel 2",
]

# Canonical Sub-Channel Name Mapping (Snowflake SUB_CHANNEL -> standard channel names)
# Used by channel_mix_engine, data_validation, and other modules.
SUBCHANNEL_MAP = {
    # DTC
    "Wyze.com": "DTC US",
    "Wyze.com US": "DTC US",
    "DTC": "DTC US",
    "DTC US": "DTC US",
    "Wyze.com CA": "DTC CA",
    "DTC CA": "DTC CA",
    # Marketplaces
    "TikTok": "TikTok Shop",
    "TikTok Shop": "TikTok Shop",
    "Amazon 1P": "Amazon 1P",
    "Amazon Vendor Central": "Amazon 1P",
    "Amazon 3P": "Amazon 3P",
    "Amazon Seller Central": "Amazon 3P",
    # Retail
    "Home Depot": "Home Depot US",
    "Home Depot US": "Home Depot US",
    "Home Depot CA": "Home Depot CA",
    "Home Depot Canada": "Home Depot CA",
    "Best Buy": "Best Buy",
    "Costco": "Costco",
    "Costco.com": "Costco.com",
    "ACE": "ACE",
    "Walmart 1P": "Walmart 1P",
    "Walmart": "Walmart 1P",
}


def _strip_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Strip whitespace from column names."""
    df.columns = df.columns.str.strip()
    return df


# ---------------------------------------------------------------------------
# 1. Product Directory
# ---------------------------------------------------------------------------
def load_product_directory() -> pd.DataFrame:
    """
    Load Product Directory with SKU, Product Name, Reference SKU,
    Default MSRP, FOB, Tariff Rate, Preload flag.
    Source: data/reference data/Product Directory.csv
    """
    path = DATA_ROOT / "Product Directory.csv"
    df = _strip_cols(pd.read_csv(path))
    # Normalize column name (may have trailing space)
    rename = {"Default MSRP ": "Default MSRP"}
    df = df.rename(columns=rename)

    # Ensure numeric types
    for col in ["Default MSRP", "Default FOB", "Default Tariff Rate"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    cols = [
        "SKU", "Product Name", "Reference SKU",
        "Default MSRP", "Default FOB", "Default Tariff Rate", "Preload",
    ]
    return df[[c for c in cols if c in df.columns]].copy()


# ---------------------------------------------------------------------------
# 2. SKU Mapping (from Snowflake cache or local CSV)
# ---------------------------------------------------------------------------
def load_sku_mapping() -> pd.DataFrame:
    """
    Load SKU Mapping.
    Primary: Snowflake-synced cache in Azure SQL (via database.py)
    Fallback: Try local CSV files in data/reference data/ or Data Source/
    Returns: SKU, Product_Group, Product_Category, Product_Line
    """
    # Snowflake SF_SKU Mapping is the single source of truth
    app_root = DATA_ROOT.parent.parent          # pricing-tool-app/
    project_root = app_root.parent              # Pricing Tool/
    for search_dir in [DATA_ROOT, project_root / "Data Source", app_root / "Data Source"]:
        for fname in ["SF_SKU Mapping.csv"]:
            path = search_dir / fname
            if path.exists():
                df = _strip_cols(pd.read_csv(path))
                col_map = {}
                for c in df.columns:
                    cl = c.lower().replace(" ", "_")
                    if cl in ("item", "sku"):
                        col_map[c] = "SKU"
                    elif "product_group" in cl:
                        col_map[c] = "Product_Group"
                    elif "product_category" in cl or "product_family" in cl:
                        col_map[c] = "Product_Category"
                    elif "product_line" in cl:
                        col_map[c] = "Product_Line"
                df = df.rename(columns=col_map)
                keep = [c for c in ["SKU", "Product_Group", "Product_Category", "Product_Line"]
                        if c in df.columns]
                return df[keep].drop_duplicates(subset=["SKU"]).copy()

    return pd.DataFrame(columns=["SKU", "Product_Group", "Product_Category", "Product_Line"])


# ---------------------------------------------------------------------------
# 3. PO Discount / Retail Margin (per-SKU per-channel)
# ---------------------------------------------------------------------------
def load_retail_margin() -> pd.DataFrame:
    """
    Load PO Discount Rates (called 'Retail Margin' in the pricing tool).
    Source: data/reference data/Input_SKU_Retail Margin.csv
    Returns long format: SKU, Channel, PO_Discount_Rate
    """
    path = DATA_ROOT / "Input_SKU_Retail Margin.csv"
    df = _strip_cols(pd.read_csv(path))

    # Drop metadata columns
    meta_cols = [c for c in df.columns if c in [
        "Modified", "Modified By", "Created", "Created By"
    ]]
    df = df.drop(columns=meta_cols, errors="ignore")

    # Unpivot: SKU as id, channel columns as values
    value_cols = [c for c in df.columns if c != "SKU"]
    long = df.melt(
        id_vars=["SKU"],
        value_vars=value_cols,
        var_name="Channel",
        value_name="PO_Discount_Rate",
    )
    long["PO_Discount_Rate"] = pd.to_numeric(long["PO_Discount_Rate"], errors="coerce")
    # Keep NaN as NaN (not 0) so we can distinguish "no data" from "0%"
    return long


# Alias for backward compatibility
load_po_discount = load_retail_margin


# ---------------------------------------------------------------------------
# 4. Return Rate (per-SKU per-channel)
# ---------------------------------------------------------------------------
def load_return_rate_by_sku() -> pd.DataFrame:
    """
    Load Return Rates per SKU per channel.
    Source: data/reference data/Input_SKU_Return Rate.csv
    Returns long format: SKU, Channel, Return_Rate
    """
    path = DATA_ROOT / "Input_SKU_Return Rate.csv"
    df = _strip_cols(pd.read_csv(path))

    # Drop metadata columns
    meta_cols = [c for c in df.columns if c in [
        "Modified", "Modified By", "Created", "Created By"
    ]]
    df = df.drop(columns=meta_cols, errors="ignore")

    # Unpivot
    value_cols = [c for c in df.columns if c != "SKU"]
    long = df.melt(
        id_vars=["SKU"],
        value_vars=value_cols,
        var_name="Channel",
        value_name="Return_Rate",
    )
    long["Return_Rate"] = pd.to_numeric(long["Return_Rate"], errors="coerce")
    return long


# ---------------------------------------------------------------------------
# 5. Outbound Shipping (per-SKU per-channel)
# ---------------------------------------------------------------------------
def load_outbound_shipping() -> pd.DataFrame:
    """
    Load Outbound Shipping costs per SKU per channel.
    Source: Snowflake cache (cache_outbound_shipping) or local CSV.
    Returns long format: SKU, Channel, Outbound_Shipping_Cost

    Note: The reference data directory does NOT have a standalone outbound
    shipping CSV. This data comes from Snowflake sync
    (DATA_MART.FINANCE.SHIPPING_COST_EST_SUPPLEMENT) which only covers
    DTC US, DTC CA, TikTok Shop.
    Falls back to old path if available.
    """
    # Try old location
    old_path = DATA_ROOT.parent.parent / "Outbound Shipping" / "Input_SKU_Outbound Shipping.csv"
    if old_path.exists():
        df = _strip_cols(pd.read_csv(old_path))
        meta_cols = [c for c in df.columns if c in [
            "Modified", "Modified By", "Created", "Created By"
        ]]
        df = df.drop(columns=meta_cols, errors="ignore")
        value_cols = [c for c in df.columns if c != "SKU"]
        long = df.melt(
            id_vars=["SKU"],
            value_vars=value_cols,
            var_name="Channel",
            value_name="Outbound_Shipping_Cost",
        )
        long["Outbound_Shipping_Cost"] = pd.to_numeric(
            long["Outbound_Shipping_Cost"], errors="coerce"
        )
        return long

    return pd.DataFrame(columns=["SKU", "Channel", "Outbound_Shipping_Cost"])


# ---------------------------------------------------------------------------
# 6. Cost Assumptions (per-SKU)
# ---------------------------------------------------------------------------
def load_cost_assumptions() -> pd.DataFrame:
    """
    Load per-SKU cost assumptions.
    Source: data/reference data/Input_SKU_CostAssumptions.csv
    Returns: SKU, Inbound_Freight, Warehouse_Storage, Amazon_FBA, Expected_Product_Life
    """
    path = DATA_ROOT / "Input_SKU_CostAssumptions.csv"
    df = _strip_cols(pd.read_csv(path))

    # Standardize column names
    rename = {
        "Inbound Freight & Insurance": "Inbound_Freight",
        "Warehouse Storage": "Warehouse_Storage",
        "Amazon FBA": "Amazon_FBA",
        "Expected Product Life": "Expected_Product_Life",
    }
    df = df.rename(columns=rename)

    # Drop metadata
    meta_cols = [c for c in df.columns if c in [
        "Modified", "Modified By", "Created", "Created By"
    ]]
    df = df.drop(columns=meta_cols, errors="ignore")

    # Ensure numeric
    for col in ["Inbound_Freight", "Warehouse_Storage", "Amazon_FBA", "Expected_Product_Life"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    keep = [c for c in ["SKU", "Inbound_Freight", "Warehouse_Storage",
                         "Amazon_FBA", "Expected_Product_Life"]
            if c in df.columns]
    return df[keep].copy()


# ---------------------------------------------------------------------------
# 7. Static Cost Assumptions (global)
# ---------------------------------------------------------------------------
def load_static_cost_assumptions() -> pd.DataFrame:
    """
    Load global static cost assumptions.
    Source: data/reference data/Static_Cost Assumptions.csv
    Returns: Item, Unit, Value, Cost Type

    Items: EOS, UID, Monthly Cloud Cost (Cam), Monthly Cloud Cost (NonCam),
           Royalties (Cam), Royalties (Bulb)
    """
    path = DATA_ROOT / "Static_Cost Assumptions.csv"
    df = _strip_cols(pd.read_csv(path))
    df["Value"] = pd.to_numeric(df["Value"], errors="coerce").fillna(0)
    return df.dropna(subset=["Item"])


def parse_static_assumptions(df: pd.DataFrame = None) -> dict:
    """
    Parse Static Cost Assumptions CSV into a dict for cpam_engine.StaticAssumptions.
    Returns dict with keys matching StaticAssumptions fields.
    """
    if df is None:
        df = load_static_cost_assumptions()

    result = {
        "uid_cam": 0.0,
        "royalties_cam": 0.0,
        "royalties_bulb_rate": 0.0,
        "monthly_cloud_cost_cam": 0.0,
        "monthly_cloud_cost_noncam": 0.0,
        "eos_rate": 0.0,
    }

    for _, row in df.iterrows():
        item = str(row.get("Item", "")).strip().lower()
        val = float(row.get("Value", 0) or 0)

        if "excess" in item or "obsolete" in item or "shrinkage" in item:
            result["eos_rate"] = val
        elif item == "uid" or "uid" in item:
            result["uid_cam"] = val
        elif "cloud" in item and "cam" in item and "non" not in item:
            result["monthly_cloud_cost_cam"] = val
        elif "cloud" in item and ("noncam" in item or "non" in item):
            result["monthly_cloud_cost_noncam"] = val
        elif "royalties" in item and "cam" in item and "bulb" not in item:
            result["royalties_cam"] = val
        elif "royalties" in item and "bulb" in item:
            result["royalties_bulb_rate"] = val

    return result


# ---------------------------------------------------------------------------
# 8. Channel Terms (per-channel)
# ---------------------------------------------------------------------------
def load_channel_terms() -> pd.DataFrame:
    """
    Load channel terms / discount structure.
    Source: data/reference data/Static_Channel Terms.csv
    Returns: Channel, Chargeback, Early Pay Discount, Co-Op, Freight Allowance,
             Labor, Damage Allowance, End Cap, Discount Special, Trade Discount,
             Total Discount
    """
    path = DATA_ROOT / "Static_Channel Terms.csv"
    df = _strip_cols(pd.read_csv(path))

    # Ensure numeric for all discount columns
    num_cols = [c for c in df.columns if c != "Channel"]
    for col in num_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    return df.dropna(subset=["Channel"])


# ---------------------------------------------------------------------------
# 9. Sales & Marketing Expenses (per-channel)
# ---------------------------------------------------------------------------
def load_sm_expenses() -> pd.DataFrame:
    """
    Load Sales & Marketing expense rates per channel.
    Source: data/reference data/Static_Sales & Marketing Expenses.csv
    Returns: Channel, CC_Platform_Fee, Customer_Service, Marketing
    """
    path = DATA_ROOT / "Static_Sales & Marketing Expenses.csv"
    df = _strip_cols(pd.read_csv(path))

    # Standardize column names
    rename = {
        "Channel Name": "Channel",
        "Credit Card & Platform Fee": "CC_Platform_Fee",
        "Customer Service": "Customer_Service",
        "Marketing": "Marketing",
    }
    df = df.rename(columns=rename)

    for col in ["CC_Platform_Fee", "Customer_Service", "Marketing"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    return df.dropna(subset=["Channel"])


# ---------------------------------------------------------------------------
# 10. Channel Mix History (from Snowflake cache / old CSV)
# ---------------------------------------------------------------------------
def load_channel_mix_history() -> pd.DataFrame:
    """Load historical revenue channel mix for reference charts."""
    # Try old location first
    old_path = DATA_ROOT.parent.parent / "Data Source" / "rev channel mix.csv"
    if old_path.exists():
        df = _strip_cols(pd.read_csv(old_path))
        return df

    return pd.DataFrame()


# ---------------------------------------------------------------------------
# Convenience: load all data
# ---------------------------------------------------------------------------
def get_all_data() -> dict:
    """Load all data and return as a dict of DataFrames."""
    return {
        "product_directory": load_product_directory(),
        "sku_mapping": load_sku_mapping(),
        "retail_margin": load_retail_margin(),
        "return_rate": load_return_rate_by_sku(),
        "outbound_shipping": load_outbound_shipping(),
        "cost_assumptions": load_cost_assumptions(),
        "static_cost_assumptions": load_static_cost_assumptions(),
        "channel_terms": load_channel_terms(),
        "sm_expenses": load_sm_expenses(),
        "channel_mix_history": load_channel_mix_history(),
    }
