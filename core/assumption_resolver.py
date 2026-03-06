"""
Assumption Resolver
Resolves the correct assumption value for a given SKU/channel/field,
applying the priority chain and Reference SKU fallback.

Data source: Azure SQL only (populated by CSV Sync or Snowflake Sync).
No runtime CSV fallback — all data must be in the database.

Priority chain:
  1. cache_* tables (Azure SQL)
  2. Reference SKU fallback (same tables, different SKU)
  3. default(0)
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple
import pandas as pd
import logging

from core.cpam_engine import (
    ChannelAssumptions,
    ProductInfo,
    StaticAssumptions,
)
from core.data_loader import CHANNELS

logger = logging.getLogger(__name__)


@dataclass
class ResolutionEntry:
    """One resolved field value with provenance."""
    channel: str
    field_name: str
    value: float
    source: str  # 'cache', 'ref_sku', 'default'


@dataclass
class ResolvedAssumptions:
    """All resolved assumptions for one SKU."""
    sku: str
    reference_sku: Optional[str]
    product_info: ProductInfo
    static_assumptions: StaticAssumptions
    channel_assumptions: Dict[str, ChannelAssumptions]
    resolution_log: List[ResolutionEntry] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Cache management (Streamlit-safe)
# ---------------------------------------------------------------------------
def clear_cache():
    """
    Clear page-level data caches after CSV sync or data change.
    Only clears specific known cached functions — NOT st.cache_data.clear()
    which is a nuclear option that destroys all page caches and causes instability.
    """
    try:
        import importlib
        import streamlit as st

        # Clear pricing_tool_main._load_products
        try:
            mod = importlib.import_module("pages.pricing_tool_main")
            if hasattr(mod, "_load_products") and hasattr(mod._load_products, "clear"):
                mod._load_products.clear()
        except Exception:
            pass

        # Clear pricing_tool_channel_mix._load_hierarchy
        try:
            mod = importlib.import_module("pages.pricing_tool_channel_mix")
            if hasattr(mod, "_load_hierarchy") and hasattr(mod._load_hierarchy, "clear"):
                mod._load_hierarchy.clear()
        except Exception:
            pass

    except Exception:
        pass


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------
def _try_load_from_db(table_name: str, engine) -> Optional[pd.DataFrame]:
    """Load a table from Azure SQL. Returns None if unavailable."""
    if engine is None:
        return None
    try:
        df = pd.read_sql_table(table_name, engine)
        if df is not None and not df.empty:
            return df
    except Exception:
        pass
    return None


def _get_db_engine():
    """Get the cached SQLAlchemy engine. Returns None if unavailable."""
    try:
        from core.database import get_sqlalchemy_engine
        return get_sqlalchemy_engine()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Product Info resolution (DB only)
# ---------------------------------------------------------------------------
def resolve_product_info(sku: str) -> ProductInfo:
    """
    Resolve ProductInfo from Azure SQL tables.
    Product directory: cache_product_directory
    SKU mapping: cache_sku_mapping
    """
    engine = _get_db_engine()

    # Load product directory from DB
    pd_df = _try_load_from_db("cache_product_directory", engine)

    product_name = ""
    reference_sku = ""
    if pd_df is not None and not pd_df.empty:
        # Normalize column names
        col_map = {}
        for c in pd_df.columns:
            cl = c.lower()
            if cl == "sku":
                col_map[c] = "SKU"
            elif cl == "product_name":
                col_map[c] = "Product Name"
            elif cl == "reference_sku":
                col_map[c] = "Reference SKU"
        pd_df = pd_df.rename(columns=col_map)

        if "SKU" in pd_df.columns:
            prod_row = pd_df[pd_df["SKU"] == sku]
            if not prod_row.empty:
                product_name = str(prod_row.iloc[0].get("Product Name", ""))
                ref_raw = prod_row.iloc[0].get("Reference SKU", "")
                reference_sku = str(ref_raw) if pd.notna(ref_raw) and ref_raw else ""

    # Load SKU mapping from DB
    sku_map_df = _try_load_from_db("cache_sku_mapping", engine)

    if sku_map_df is None or sku_map_df.empty:
        return ProductInfo(
            sku=sku, product_name=product_name,
            product_group="", product_category="", product_line="",
            reference_sku=reference_sku,
        )

    # Normalize column names
    col_renames = {}
    for c in sku_map_df.columns:
        cl = c.lower()
        if cl in ("item", "sku"):
            col_renames[c] = "SKU"
        elif "product_group" in cl:
            col_renames[c] = "Product_Group"
        elif "product_category" in cl or "product_family" in cl:
            col_renames[c] = "Product_Category"
        elif "product_line" in cl:
            col_renames[c] = "Product_Line"
    sku_map_df = sku_map_df.rename(columns=col_renames)

    def _lookup_mapping(lookup_sku: str) -> Tuple[str, str, str]:
        if "SKU" not in sku_map_df.columns:
            return ("", "", "")
        match = sku_map_df[sku_map_df["SKU"].str.upper() == lookup_sku.upper()]
        if not match.empty:
            row = match.iloc[0]
            return (
                str(row.get("Product_Group", "")),
                str(row.get("Product_Category", "")),
                str(row.get("Product_Line", "")),
            )
        return ("", "", "")

    pg, pc, pl = _lookup_mapping(sku)

    # Fallback to reference SKU
    if not pg and reference_sku and reference_sku != sku:
        pg, pc, pl = _lookup_mapping(reference_sku)

    return ProductInfo(
        sku=sku,
        product_name=product_name,
        product_group=pg,
        product_category=pc,
        product_line=pl,
        reference_sku=reference_sku,
    )


# ---------------------------------------------------------------------------
# Static Assumptions resolution (DB only)
# ---------------------------------------------------------------------------
def resolve_static_assumptions() -> StaticAssumptions:
    """
    Load static assumptions from Azure SQL.
    Priority: admin_static_assumptions > cache_static_assumptions
    """
    engine = _get_db_engine()

    # Try admin table first
    admin_df = _try_load_from_db("admin_static_assumptions", engine)
    if admin_df is not None and not admin_df.empty:
        parsed = _parse_admin_static(admin_df)
        return StaticAssumptions(**parsed)

    # Try cache table
    cache_df = _try_load_from_db("cache_static_assumptions", engine)
    if cache_df is not None and not cache_df.empty:
        parsed = _parse_admin_static(cache_df)
        return StaticAssumptions(**parsed)

    # No data — return zeros
    logger.warning("No static assumptions found in DB. Returning defaults.")
    return StaticAssumptions()


def _parse_admin_static(df: pd.DataFrame) -> dict:
    """Parse admin_static_assumptions table rows into StaticAssumptions dict."""
    result = {
        "uid_cam": 0.0,
        "royalties_cam": 0.0,
        "royalties_bulb_rate": 0.0,
        "monthly_cloud_cost_cam": 0.0,
        "monthly_cloud_cost_noncam": 0.0,
        "eos_rate": 0.0,
    }
    for _, row in df.iterrows():
        item = str(row.get("item", "")).strip().lower()
        val = float(row.get("value", 0) or 0)

        if "excess" in item or "obsolete" in item or "shrinkage" in item or "eos" in item:
            result["eos_rate"] = val
        elif "uid" in item:
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
# Channel-level assumptions resolution (per-SKU)
# ---------------------------------------------------------------------------
def _resolve_sku_field(
    sku: str,
    channel: str,
    field_name: str,
    ref_sku: str,
    datasets: dict,
) -> Tuple[float, str]:
    """
    Resolve a single SKU-level field (po_discount_rate, return_rate,
    inbound_freight, warehouse_storage, amazon_fba, expected_product_life,
    outbound_shipping).

    Returns (value, source_label).
    """
    def _lookup(lookup_sku: str, src_label_prefix: str) -> Tuple[Optional[float], str]:
        if field_name == "po_discount_rate":
            df = datasets.get("retail_margin")
            if df is not None:
                match = df[
                    (df["SKU"].str.upper() == lookup_sku.upper()) &
                    (df["Channel"] == channel)
                ]
                if not match.empty:
                    val = match.iloc[0]["PO_Discount_Rate"]
                    if pd.notna(val):
                        return float(val), src_label_prefix

        elif field_name == "return_rate":
            df = datasets.get("return_rate")
            if df is not None:
                match = df[
                    (df["SKU"].str.upper() == lookup_sku.upper()) &
                    (df["Channel"] == channel)
                ]
                if not match.empty:
                    val = match.iloc[0]["Return_Rate"]
                    if pd.notna(val):
                        return float(val), src_label_prefix

        elif field_name == "outbound_shipping":
            df = datasets.get("outbound_shipping")
            if df is not None and not df.empty:
                match = df[
                    (df["SKU"].str.upper() == lookup_sku.upper()) &
                    (df["Channel"] == channel)
                ]
                if not match.empty:
                    val = match.iloc[0]["Outbound_Shipping_Cost"]
                    if pd.notna(val):
                        return float(val), src_label_prefix

        elif field_name in ("inbound_freight", "warehouse_storage", "amazon_fba",
                            "expected_product_life"):
            df = datasets.get("cost_assumptions")
            if df is not None:
                match = df[df["SKU"].str.upper() == lookup_sku.upper()]
                if not match.empty:
                    col_map = {
                        "inbound_freight": "Inbound_Freight",
                        "warehouse_storage": "Warehouse_Storage",
                        "amazon_fba": "Amazon_FBA",
                        "expected_product_life": "Expected_Product_Life",
                    }
                    col = col_map.get(field_name)
                    if col and col in match.columns:
                        val = match.iloc[0][col]
                        if pd.notna(val):
                            return float(val), src_label_prefix

        return None, ""

    # Step 1: try actual SKU
    val, src = _lookup(sku, "cache")
    if val is not None:
        return val, src

    # Step 2: try reference SKU
    if ref_sku and ref_sku.upper() != sku.upper():
        val, src = _lookup(ref_sku, "ref_sku")
        if val is not None:
            return val, src

    return 0.0, "default"


def _resolve_channel_field(
    channel: str,
    field_name: str,
    datasets: dict,
) -> Tuple[float, str]:
    """
    Resolve a channel-level field (not SKU-specific):
    chargeback_rate, total_discount_rate, cc_fee_rate, customer_service_rate, marketing_rate
    """
    if field_name in ("chargeback_rate", "total_discount_rate"):
        df = datasets.get("channel_terms")
        if df is not None and not df.empty:
            match = df[df["Channel"] == channel]
            if not match.empty:
                row = match.iloc[0]
                if field_name == "chargeback_rate":
                    val = row.get("Chargeback", 0)
                else:
                    val = row.get("Total Discount", 0)
                return float(val or 0), "cache"

    elif field_name in ("cc_fee_rate", "customer_service_rate", "marketing_rate"):
        df = datasets.get("sm_expenses")
        if df is not None and not df.empty:
            match = df[df["Channel"] == channel]
            if not match.empty:
                row = match.iloc[0]
                col_map = {
                    "cc_fee_rate": "CC_Platform_Fee",
                    "customer_service_rate": "Customer_Service",
                    "marketing_rate": "Marketing",
                }
                col = col_map.get(field_name)
                if col:
                    return float(row.get(col, 0) or 0), "cache"

    return 0.0, "default"


# ---------------------------------------------------------------------------
# Main resolver
# ---------------------------------------------------------------------------
def resolve_all_assumptions(sku: str) -> ResolvedAssumptions:
    """
    Master function that resolves ALL assumptions for a given SKU.
    All data from Azure SQL — no CSV fallback.
    """
    # 1. Product info
    product_info = resolve_product_info(sku)
    ref_sku = product_info.reference_sku

    # 2. Static assumptions
    static = resolve_static_assumptions()

    # 3. Load datasets (DB only)
    engine = _get_db_engine()
    datasets = _load_all_datasets(engine)

    # 4. Build ChannelAssumptions for each channel
    channel_assumptions: Dict[str, ChannelAssumptions] = {}
    resolution_log: List[ResolutionEntry] = []

    sku_fields = [
        "po_discount_rate", "return_rate", "outbound_shipping",
        "inbound_freight", "warehouse_storage", "amazon_fba",
        "expected_product_life",
    ]
    channel_fields = [
        "chargeback_rate", "total_discount_rate",
        "cc_fee_rate", "customer_service_rate", "marketing_rate",
    ]

    for ch in CHANNELS:
        ca = ChannelAssumptions(channel=ch)

        # Resolve SKU-level fields
        for f in sku_fields:
            val, src = _resolve_sku_field(sku, ch, f, ref_sku, datasets)
            setattr(ca, f, val)
            resolution_log.append(ResolutionEntry(
                channel=ch, field_name=f, value=val, source=src
            ))

        # Resolve channel-level fields
        for f in channel_fields:
            val, src = _resolve_channel_field(ch, f, datasets)
            setattr(ca, f, val)
            resolution_log.append(ResolutionEntry(
                channel=ch, field_name=f, value=val, source=src
            ))

        channel_assumptions[ch] = ca

    return ResolvedAssumptions(
        sku=sku,
        reference_sku=ref_sku,
        product_info=product_info,
        static_assumptions=static,
        channel_assumptions=channel_assumptions,
        resolution_log=resolution_log,
    )


def _load_all_datasets(engine) -> dict:
    """Load all datasets from Azure SQL. No CSV fallback."""
    datasets = {}

    # Retail Margin / PO Discount
    db_df = _try_load_from_db("cache_po_discount", engine)
    if db_df is not None and not db_df.empty:
        col_map = {}
        for c in db_df.columns:
            cl = c.lower()
            if cl in ("sku", "item"):
                col_map[c] = "SKU"
            elif cl in ("channel",):
                col_map[c] = "Channel"
            elif "po_discount" in cl or "retail_margin" in cl:
                col_map[c] = "PO_Discount_Rate"
        datasets["retail_margin"] = db_df.rename(columns=col_map)

    # Return Rate (per-SKU)
    db_df = _try_load_from_db("cache_return_rate_sku", engine)
    if db_df is not None and not db_df.empty:
        col_map = {}
        for c in db_df.columns:
            cl = c.lower()
            if cl in ("sku",):
                col_map[c] = "SKU"
            elif cl in ("channel",):
                col_map[c] = "Channel"
            elif "return_rate" in cl:
                col_map[c] = "Return_Rate"
        datasets["return_rate"] = db_df.rename(columns=col_map)

    # Outbound Shipping
    db_df = _try_load_from_db("cache_outbound_shipping", engine)
    if db_df is not None and not db_df.empty:
        col_map = {}
        for c in db_df.columns:
            cl = c.lower()
            if cl in ("sku", "item"):
                col_map[c] = "SKU"
            elif cl in ("channel",):
                col_map[c] = "Channel"
            elif "shipping" in cl or "outbound" in cl:
                col_map[c] = "Outbound_Shipping_Cost"
        datasets["outbound_shipping"] = db_df.rename(columns=col_map)

    # Cost Assumptions (per-SKU)
    db_df = _try_load_from_db("cache_cost_assumptions", engine)
    if db_df is not None and not db_df.empty:
        col_map = {}
        for c in db_df.columns:
            cl = c.lower()
            if cl in ("sku",):
                col_map[c] = "SKU"
            elif "inbound" in cl or "freight" in cl:
                col_map[c] = "Inbound_Freight"
            elif "warehouse" in cl or "storage" in cl:
                col_map[c] = "Warehouse_Storage"
            elif "fba" in cl or "amazon" in cl:
                col_map[c] = "Amazon_FBA"
            elif "life" in cl or "product_life" in cl:
                col_map[c] = "Expected_Product_Life"
        datasets["cost_assumptions"] = db_df.rename(columns=col_map)

    # Channel Terms
    db_df = _try_load_from_db("cache_channel_terms", engine)
    if db_df is not None and not db_df.empty:
        col_map = {}
        for c in db_df.columns:
            cl = c.lower()
            if cl in ("channel",):
                col_map[c] = "Channel"
            elif cl == "chargeback":
                col_map[c] = "Chargeback"
            elif "total" in cl and "discount" in cl:
                col_map[c] = "Total Discount"
        datasets["channel_terms"] = db_df.rename(columns=col_map)

    # S&M Expenses
    db_df = _try_load_from_db("cache_sm_expenses", engine)
    if db_df is not None and not db_df.empty:
        col_map = {}
        for c in db_df.columns:
            cl = c.lower()
            if cl in ("channel",):
                col_map[c] = "Channel"
            elif "cc" in cl or "platform" in cl:
                col_map[c] = "CC_Platform_Fee"
            elif "customer" in cl or "service" in cl:
                col_map[c] = "Customer_Service"
            elif "marketing" in cl:
                col_map[c] = "Marketing"
        datasets["sm_expenses"] = db_df.rename(columns=col_map)

    return datasets


# ---------------------------------------------------------------------------
# Resolution log to DataFrame (for Assumptions Loaded page)
# ---------------------------------------------------------------------------
def resolution_log_to_df(log: List[ResolutionEntry]) -> pd.DataFrame:
    """Convert resolution log to a display DataFrame."""
    if not log:
        return pd.DataFrame(columns=["Channel", "Field", "Value", "Source"])
    return pd.DataFrame([
        {
            "Channel": e.channel,
            "Field": e.field_name,
            "Value": e.value,
            "Source": e.source,
        }
        for e in log
    ])
