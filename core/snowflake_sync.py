"""
Snowflake Data Sync Module

Connects to Snowflake via SSO/Okta or username/password.
Pulls live data and updates Azure SQL cache tables.

Snowflake Sources:
  1. DATA_MART.FINANCE.SKU_MAPPING              → cache_sku_mapping
  2. DATA_MART.FINANCE.ROLLING_RETURN_RATE_SELLIN → cache_return_rate
  3. FINANCE_TEAM_DB.REFERENCES.PRICING_TOOL_CHANNEL_MIX → cache_channel_mix
  4. DATA_MART.FINANCE.SHIPPING_COST_EST_SUPPLEMENT → cache_outbound_shipping
"""

import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ENV_PATH = Path(__file__).parent.parent / ".env"


def _load_env():
    """Load .env file."""
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip().strip('"').strip("'")


_load_env()


def get_snowflake_config() -> dict:
    """Get Snowflake connection config from environment variables."""
    config = {
        "account": os.environ.get("SNOWFLAKE_ACCOUNT", ""),
        "user": os.environ.get("SNOWFLAKE_USER", ""),
        "warehouse": os.environ.get("SNOWFLAKE_WAREHOUSE", ""),
        "database": os.environ.get("SNOWFLAKE_DATABASE", ""),
        "schema": os.environ.get("SNOWFLAKE_SCHEMA", ""),
        "role": os.environ.get("SNOWFLAKE_ROLE", ""),
    }

    auth = os.environ.get("SNOWFLAKE_AUTHENTICATOR", "externalbrowser")
    password = os.environ.get("SNOWFLAKE_PASSWORD", "")

    if password:
        config["password"] = password
    else:
        config["authenticator"] = auth

    return {k: v for k, v in config.items() if v}


def get_snowflake_connection():
    """Get a Snowflake connection. Opens browser for SSO if needed."""
    import snowflake.connector

    config = get_snowflake_config()
    if not config.get("account") or not config.get("user"):
        raise ConnectionError(
            "Snowflake config not found. Add to .env:\n"
            "SNOWFLAKE_ACCOUNT=your_account\n"
            "SNOWFLAKE_USER=your_email@wyze.com\n"
            "SNOWFLAKE_WAREHOUSE=your_warehouse\n"
            "SNOWFLAKE_AUTHENTICATOR=externalbrowser"
        )

    logger.info(f"Connecting to Snowflake account: {config['account']}...")
    conn = snowflake.connector.connect(**config)
    logger.info("Snowflake connected successfully.")
    return conn


def test_snowflake_connection() -> dict:
    """Test Snowflake connection and return status."""
    try:
        conn = get_snowflake_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT CURRENT_VERSION(), CURRENT_ACCOUNT(), CURRENT_USER(), CURRENT_DATABASE()")
        row = cursor.fetchone()
        conn.close()
        return {
            "status": "connected",
            "version": row[0],
            "account": row[1],
            "user": row[2],
            "database": row[3],
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# Snowflake → Azure SQL Sync Functions
# ---------------------------------------------------------------------------

# ========================
# 1. SKU Mapping
# ========================
SF_QUERY_SKU_MAPPING = """
SELECT
    ITEM AS sku,
    PRODUCT_GROUP AS product_group,
    PRODUCT_CATEGORY AS product_category,
    PRODUCT_LINE AS product_line
FROM DATA_MART.FINANCE.SKU_MAPPING
WHERE ITEM IS NOT NULL
"""


def sync_sku_mapping(sf_conn=None) -> int:
    """
    Sync SKU Mapping from Snowflake.
    Source: DATA_MART.FINANCE.SKU_MAPPING
    Target: cache_sku_mapping
    """
    close_conn = False
    if sf_conn is None:
        sf_conn = get_snowflake_connection()
        close_conn = True

    query = os.environ.get("SF_QUERY_SKU_MAPPING", SF_QUERY_SKU_MAPPING)
    df = pd.read_sql(query, sf_conn)
    df.columns = [c.lower() for c in df.columns]

    if close_conn:
        sf_conn.close()

    if df.empty:
        return 0

    # Deduplicate (keep first occurrence per SKU)
    df = df.drop_duplicates(subset=["sku"], keep="first")

    from core.database import get_sqlalchemy_engine
    engine = get_sqlalchemy_engine()
    df["synced_at"] = datetime.utcnow()
    df.to_sql("cache_sku_mapping", engine, if_exists="replace", index=False)

    _update_sync_metadata("cache_sku_mapping", len(df), "snowflake")
    return len(df)


# ========================
# 2. Return Rate
# ========================
SF_QUERY_RETURN_RATE = """
SELECT
    MONTH_START,
    PRODUCT_GROUP,
    PRODUCT_CATEGORY,
    PRODUCT_LINE,
    CHANNEL,
    SUB_CHANNEL,
    RETURN_QUANTITY,
    SELL_IN_UNITS,
    RETURN_UNITS_3M,
    SELL_IN_UNITS_3M_SHIFTED,
    RETURN_RATE_3M_PCT,
    RETURN_UNITS_6M,
    SELL_IN_UNITS_6M_SHIFTED,
    RETURN_RATE_6M_PCT,
    RETURN_UNITS_12M,
    SELL_IN_UNITS_12M_SHIFTED,
    RETURN_RATE_12M_PCT
FROM DATA_MART.FINANCE.ROLLING_RETURN_RATE_SELLIN
"""


def sync_return_rate(sf_conn=None) -> int:
    """
    Sync full Return Rate history from Snowflake.
    Source: DATA_MART.FINANCE.ROLLING_RETURN_RATE_SELLIN
    Target: cache_return_rate
    Syncs all rows (all months, all dimensions).
    """
    close_conn = False
    if sf_conn is None:
        sf_conn = get_snowflake_connection()
        close_conn = True

    query = os.environ.get("SF_QUERY_RETURN_RATE", SF_QUERY_RETURN_RATE)
    df = pd.read_sql(query, sf_conn)
    df.columns = [c.lower() for c in df.columns]

    if close_conn:
        sf_conn.close()

    if df.empty:
        return 0

    from core.database import get_sqlalchemy_engine
    engine = get_sqlalchemy_engine()
    df["synced_at"] = datetime.utcnow()
    df.to_sql("cache_return_rate", engine, if_exists="replace", index=False)

    _update_sync_metadata("cache_return_rate", len(df), "snowflake")
    return len(df)


# ========================
# 3. Channel Mix
# ========================
SF_QUERY_CHANNEL_MIX = """
SELECT
    PERIODNAME,
    SUB_CHANNEL,
    PRODUCT_GROUP,
    PRODUCT_CATEGORY,
    PRODUCT_LINE,
    QUANTITY
FROM FINANCE_TEAM_DB.REFERENCES.PRICING_TOOL_CHANNEL_MIX
WHERE QUANTITY IS NOT NULL AND QUANTITY > 0
ORDER BY PERIODNAME, SUB_CHANNEL, PRODUCT_LINE
"""


def sync_channel_mix(sf_conn=None) -> int:
    """
    Sync Channel Mix history from Snowflake.
    Source: FINANCE_TEAM_DB.REFERENCES.PRICING_TOOL_CHANNEL_MIX
    Target: cache_channel_mix (new table)
    """
    close_conn = False
    if sf_conn is None:
        sf_conn = get_snowflake_connection()
        close_conn = True

    query = os.environ.get("SF_QUERY_CHANNEL_MIX", SF_QUERY_CHANNEL_MIX)
    df = pd.read_sql(query, sf_conn)
    df.columns = [c.lower() for c in df.columns]

    if close_conn:
        sf_conn.close()

    if df.empty:
        return 0

    from core.database import get_sqlalchemy_engine
    engine = get_sqlalchemy_engine()
    df["synced_at"] = datetime.utcnow()
    df.to_sql("cache_channel_mix", engine, if_exists="replace", index=False)

    _update_sync_metadata("cache_channel_mix", len(df), "snowflake")
    return len(df)


# ========================
# 4. Outbound Shipping
# ========================
SF_QUERY_SHIPPING = """
SELECT
    CUSTOMER,
    SKU,
    BLENDED_COST
FROM DATA_MART.FINANCE.SHIPPING_COST_EST_SUPPLEMENT
WHERE BLENDED_COST IS NOT NULL
"""

# Map Snowflake CUSTOMER values to our standard channel names
# Actual values from SF: "2 E-Commerce - US", "3 E-Commerce - CA", "64 TikTok Shop"
CUSTOMER_CHANNEL_MAP = {
    "2 E-Commerce - US": "DTC US",
    "3 E-Commerce - CA": "DTC CA",
    "64 TikTok Shop": "TikTok Shop",
}


def sync_outbound_shipping(sf_conn=None) -> int:
    """
    Sync Outbound Shipping Cost from Snowflake.
    Source: DATA_MART.FINANCE.SHIPPING_COST_EST_SUPPLEMENT
    Target: cache_outbound_shipping
    Maps CUSTOMER field to standard channel names.
    """
    close_conn = False
    if sf_conn is None:
        sf_conn = get_snowflake_connection()
        close_conn = True

    query = os.environ.get("SF_QUERY_SHIPPING", SF_QUERY_SHIPPING)
    df = pd.read_sql(query, sf_conn)
    df.columns = [c.lower() for c in df.columns]

    if close_conn:
        sf_conn.close()

    if df.empty:
        return 0

    # Map CUSTOMER to channel name
    df["channel"] = df["customer"].str.strip().map(CUSTOMER_CHANNEL_MAP)

    # Log unmapped customers for debugging
    unmapped = df[df["channel"].isna()]["customer"].unique()
    if len(unmapped) > 0:
        logger.warning(f"Unmapped CUSTOMER values in shipping data: {list(unmapped)}")

    # Drop unmapped, rename
    df = df.dropna(subset=["channel"])
    df = df.rename(columns={"blended_cost": "outbound_shipping_cost"})
    df = df[["sku", "channel", "outbound_shipping_cost"]].copy()

    # Deduplicate: keep average if multiple rows per SKU/channel
    df = df.groupby(["sku", "channel"], as_index=False).agg({"outbound_shipping_cost": "mean"})

    # --- Save Snowflake data to _sf snapshot table ONLY ---
    # Do NOT auto-merge into cache_outbound_shipping.
    # Users review diffs on Data Validation page and decide per-SKU/channel.
    from core.database import get_sqlalchemy_engine
    engine = get_sqlalchemy_engine()
    sf_raw = df.copy()
    sf_raw["synced_at"] = datetime.utcnow()
    sf_raw.to_sql("cache_outbound_shipping_sf", engine, if_exists="replace", index=False)
    _update_sync_metadata("cache_outbound_shipping_sf", len(sf_raw), "snowflake")

    return len(sf_raw)


# ---------------------------------------------------------------------------
# Sync All
# ---------------------------------------------------------------------------

def sync_all(sf_conn=None) -> dict:
    """Run all sync operations. Returns dict of table -> row count."""
    close_conn = False
    if sf_conn is None:
        sf_conn = get_snowflake_connection()
        close_conn = True

    results = {}

    for name, func in [
        ("cache_sku_mapping", sync_sku_mapping),
        ("cache_return_rate", sync_return_rate),
        ("cache_channel_mix", sync_channel_mix),
        ("cache_outbound_shipping", sync_outbound_shipping),
    ]:
        try:
            results[name] = func(sf_conn)
        except Exception as e:
            results[name] = f"Error: {e}"
            logger.error(f"Sync {name} failed: {e}")

    if close_conn:
        sf_conn.close()

    return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _update_sync_metadata(table_name: str, count: int, source: str):
    """Update sync_metadata table."""
    try:
        from core.database import get_connection
        conn = get_connection()
        cursor = conn.cursor()
        now = datetime.utcnow()
        cursor.execute("""
            MERGE sync_metadata AS target
            USING (SELECT ? AS table_name) AS source
            ON target.table_name = source.table_name
            WHEN MATCHED THEN
                UPDATE SET last_synced_at = ?, record_count = ?, source = ?
            WHEN NOT MATCHED THEN
                INSERT (table_name, last_synced_at, record_count, source)
                VALUES (?, ?, ?, ?);
        """, (table_name, now, count, source, table_name, now, count, source))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"Failed to update sync_metadata: {e}")


def get_unmapped_customers(sf_conn=None) -> list:
    """Get list of CUSTOMER values in shipping table that aren't mapped to channels."""
    close_conn = False
    if sf_conn is None:
        sf_conn = get_snowflake_connection()
        close_conn = True

    df = pd.read_sql("SELECT DISTINCT CUSTOMER FROM DATA_MART.FINANCE.SHIPPING_COST_EST_SUPPLEMENT", sf_conn)
    df.columns = [c.lower() for c in df.columns]

    if close_conn:
        sf_conn.close()

    all_customers = df["customer"].str.strip().unique()
    unmapped = [c for c in all_customers if c not in CUSTOMER_CHANNEL_MAP]
    return unmapped


# ---------------------------------------------------------------------------
# Custom Query Support
# ---------------------------------------------------------------------------

def run_custom_query(query: str, sf_conn=None) -> pd.DataFrame:
    """Run a custom Snowflake query and return results as DataFrame."""
    close_conn = False
    if sf_conn is None:
        sf_conn = get_snowflake_connection()
        close_conn = True

    df = pd.read_sql(query, sf_conn)

    if close_conn:
        sf_conn.close()

    return df
