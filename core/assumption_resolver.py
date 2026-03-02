"""
Assumption Resolver
Resolves the correct assumption value for a given SKU/channel/field,
applying the priority chain and Reference SKU fallback.

Priority chain:
  1. user_overrides table (Azure SQL)
  2. cache_* tables (Azure SQL, loaded from CSV or Snowflake)
  3. CSV file fallback (local files in data/reference data/)

Reference SKU Fallback:
  If SKU has no data for a given assumption, look up the product's
  Reference SKU from product directory and use its values instead.
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
from core.data_loader import (
    CHANNELS,
    load_product_directory,
    load_sku_mapping,
    load_retail_margin,
    load_return_rate_by_sku,
    load_outbound_shipping,
    load_cost_assumptions,
    load_channel_terms,
    load_sm_expenses,
    load_static_cost_assumptions,
    parse_static_assumptions,
)

logger = logging.getLogger(__name__)


@dataclass
class ResolutionEntry:
    """One resolved field value with provenance."""
    channel: str
    field_name: str
    value: float
    source: str  # 'cache', 'csv', 'ref_sku', 'default'


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
# Internal caches (loaded once per session)
# ---------------------------------------------------------------------------
_cache: dict = {}


def _get_cached(key: str, loader):
    """Cache CSV data in module-level dict (resets on restart)."""
    if key not in _cache:
        _cache[key] = loader()
    return _cache[key]


def clear_cache():
    """Clear the data cache (call after CSV sync or data change)."""
    _cache.clear()


# ---------------------------------------------------------------------------
# DB helpers (try Azure SQL first, fall back to CSV)
# ---------------------------------------------------------------------------
def _try_load_from_db(table_name: str, engine) -> Optional[pd.DataFrame]:
    """Try to load a table from Azure SQL. Returns None if unavailable."""
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
    """Try to get the cached SQLAlchemy engine. Returns None if unavailable."""
    try:
        from core.database import get_sqlalchemy_engine
        return get_sqlalchemy_engine()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Product Info resolution
# ---------------------------------------------------------------------------
def resolve_product_info(sku: str) -> ProductInfo:
    """
    Resolve ProductInfo including SKU mapping enrichment.
    If SKU not in sku_mapping, use reference_sku's mapping.
    """
    pd_df = _get_cached("product_directory", load_product_directory)
    prod_row = pd_df[pd_df["SKU"] == sku]

    product_name = ""
    reference_sku = ""
    if not prod_row.empty:
        product_name = str(prod_row.iloc[0].get("Product Name", ""))
        ref_raw = prod_row.iloc[0].get("Reference SKU", "")
        reference_sku = str(ref_raw) if pd.notna(ref_raw) and ref_raw else ""

    # Try sku mapping from DB first; fallback to CSV if DB lacks product_category
    engine = _get_db_engine()
    sku_map_df = _try_load_from_db("cache_sku_mapping", engine)
    if sku_map_df is not None:
        # Check if DB has product_category column
        cols_lower = [c.lower() for c in sku_map_df.columns]
        if "product_category" not in cols_lower:
            sku_map_df = None  # DB is stale, fallback to CSV
    if sku_map_df is None:
        sku_map_df = _get_cached("sku_mapping", load_sku_mapping)

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
# Static Assumptions resolution
# ---------------------------------------------------------------------------
def resolve_static_assumptions() -> StaticAssumptions:
    """
    Load static assumptions.
    Priority: admin_static_assumptions (DB) > cache > CSV
    """
    engine = _get_db_engine()

    # Try admin table first
    admin_df = _try_load_from_db("admin_static_assumptions", engine)
    if admin_df is not None and not admin_df.empty:
        parsed = _parse_admin_static(admin_df)
        return StaticAssumptions(**parsed)

    # Try CSV
    csv_df = _get_cached("static_cost_assumptions", load_static_cost_assumptions)
    parsed = parse_static_assumptions(csv_df)
    return StaticAssumptions(**parsed)


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

    Steps:
    1. Resolve product info (product directory + SKU mapping)
    2. Resolve static assumptions
    3. Load all datasets (DB preferred, CSV fallback)
    4. For each channel, resolve each field via priority chain
    5. Return ResolvedAssumptions with full channel_assumptions dict
    """
    # 1. Product info
    product_info = resolve_product_info(sku)
    ref_sku = product_info.reference_sku

    # 2. Static assumptions
    static = resolve_static_assumptions()

    # 3. Load datasets (prefer DB, fall back to CSV)
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
    """Load all datasets needed for assumption resolution."""
    datasets = {}

    # Retail Margin / PO Discount
    db_df = _try_load_from_db("cache_po_discount", engine)
    if db_df is not None and not db_df.empty:
        # Normalize columns
        col_map = {}
        for c in db_df.columns:
            cl = c.lower()
            if cl in ("sku", "item"):
                col_map[c] = "SKU"
            elif cl in ("channel",):
                col_map[c] = "Channel"
            elif "po_discount" in cl or "retail_margin" in cl:
                col_map[c] = "PO_Discount_Rate"
        db_df = db_df.rename(columns=col_map)
        datasets["retail_margin"] = db_df
    else:
        datasets["retail_margin"] = _get_cached("retail_margin", load_retail_margin)

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
        db_df = db_df.rename(columns=col_map)
        datasets["return_rate"] = db_df
    else:
        datasets["return_rate"] = _get_cached("return_rate", load_return_rate_by_sku)

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
        db_df = db_df.rename(columns=col_map)
        datasets["outbound_shipping"] = db_df
    else:
        datasets["outbound_shipping"] = _get_cached("outbound_shipping", load_outbound_shipping)

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
        db_df = db_df.rename(columns=col_map)
        datasets["cost_assumptions"] = db_df
    else:
        datasets["cost_assumptions"] = _get_cached("cost_assumptions", load_cost_assumptions)

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
        db_df = db_df.rename(columns=col_map)
        datasets["channel_terms"] = db_df
    else:
        datasets["channel_terms"] = _get_cached("channel_terms", load_channel_terms)

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
        db_df = db_df.rename(columns=col_map)
        datasets["sm_expenses"] = db_df
    else:
        datasets["sm_expenses"] = _get_cached("sm_expenses", load_sm_expenses)

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
