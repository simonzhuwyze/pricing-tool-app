"""
Azure SQL Database Connection & Operations Module

Two types of tables:
1. Admin/Cache tables - Store working data (initially loaded from CSV, maintained via UI)
2. SF snapshot tables - Mirror Snowflake data for validation comparison

Architecture:
  CSV files ──initial import──> Azure SQL (cache tables, one-time sync)
  Snowflake ──sync──> Azure SQL (SF snapshot tables, for comparison)
  App ──read/write──> Azure SQL (single source of truth, no CSV runtime fallback)
"""

import os
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Connection Configuration
# ---------------------------------------------------------------------------

CONFIG_PATH = Path(__file__).parent.parent / ".streamlit" / "secrets.toml"
ENV_CONN_STR = "AZURE_SQL_CONN_STR"

# Auto-load .env at module import time
_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if "=" in _line and not _line.startswith("#"):
            _k, _v = _line.split("=", 1)
            _v = _v.strip().strip('"').strip("'")
            if _k.strip() not in os.environ or not os.environ[_k.strip()]:
                os.environ[_k.strip()] = _v


def _load_connection_string() -> Optional[str]:
    """
    Load connection string from (in order):
      1. Environment variable AZURE_SQL_CONN_STR
      2. Streamlit secrets.toml  [azure_sql] connection_string
      3. .env file in project root
    """
    # 1) Environment variable
    conn = os.environ.get(ENV_CONN_STR)
    if conn:
        return conn

    # 2) Streamlit secrets.toml
    try:
        import streamlit as st
        conn = st.secrets.get("azure_sql", {}).get("connection_string")
        if conn:
            return conn
    except Exception:
        pass

    # 3) .env file
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith(f"{ENV_CONN_STR}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")

    return None


def _detect_odbc_driver() -> str:
    """Detect the best available ODBC driver for SQL Server."""
    import pyodbc
    drivers = pyodbc.drivers()
    # Prefer newer driver versions
    for candidate in ["ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server", "SQL Server"]:
        if candidate in drivers:
            return candidate
    return "ODBC Driver 17 for SQL Server"  # fallback


def get_connection():
    """Get a pyodbc connection to Azure SQL Database."""
    import pyodbc

    conn_str = _load_connection_string()
    if not conn_str:
        driver = _detect_odbc_driver()
        raise ConnectionError(
            "Azure SQL connection string not found. "
            "Set AZURE_SQL_CONN_STR environment variable or add to .streamlit/secrets.toml:\n"
            "[azure_sql]\n"
            f'connection_string = "Driver={{{driver}}};Server=tcp:YOUR_SERVER.database.windows.net,1433;Database=YOUR_DB;Uid=YOUR_USER;Pwd=YOUR_PASSWORD;Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"'
        )

    # Auto-fix driver if needed: replace Driver 18 with available driver
    if "{ODBC Driver 18 for SQL Server}" in conn_str:
        import pyodbc
        if "ODBC Driver 18 for SQL Server" not in pyodbc.drivers():
            detected = _detect_odbc_driver()
            conn_str = conn_str.replace("ODBC Driver 18 for SQL Server", detected)
            logger.info(f"Auto-switched ODBC driver to: {detected}")

    return pyodbc.connect(conn_str)


def get_sqlalchemy_engine():
    """Get a cached SQLAlchemy engine for pandas read/write operations."""
    # Try Streamlit cache first (preferred for concurrency safety)
    try:
        import streamlit as st
        return _get_cached_engine()
    except Exception:
        pass
    # Fallback for non-Streamlit contexts (CLI scripts, tests)
    return _create_engine_instance()


def _create_engine_instance():
    """Create a new SQLAlchemy engine instance."""
    from sqlalchemy import create_engine
    from urllib.parse import quote_plus

    conn_str = _load_connection_string()
    if not conn_str:
        raise ConnectionError("Azure SQL connection string not found.")

    return create_engine(
        f"mssql+pyodbc:///?odbc_connect={quote_plus(conn_str)}",
        pool_pre_ping=True,
        pool_recycle=300,
    )


try:
    import streamlit as st

    @st.cache_resource
    def _get_cached_engine():
        """Streamlit-cached engine (process-level singleton)."""
        return _create_engine_instance()
except ImportError:
    def _get_cached_engine():
        return _create_engine_instance()


def test_connection() -> dict:
    """Test the database connection and return status info."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT @@VERSION")
        version = cursor.fetchone()[0]
        cursor.execute("SELECT DB_NAME()")
        db_name = cursor.fetchone()[0]
        conn.close()
        return {"status": "connected", "database": db_name, "version": version.split("\n")[0]}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# Schema Initialization
# ---------------------------------------------------------------------------

INIT_SQL = """
-- =====================================================
-- Override Tables (user-editable, replaces SharePoint Lists)
-- =====================================================

-- User override records: any field the user changed
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'user_overrides')
CREATE TABLE user_overrides (
    id              INT IDENTITY(1,1) PRIMARY KEY,
    sku             NVARCHAR(50)   NOT NULL,
    channel         NVARCHAR(50)   NOT NULL,
    field_name      NVARCHAR(100)  NOT NULL,
    field_value     FLOAT          NOT NULL,
    updated_by      NVARCHAR(100)  DEFAULT 'local_user',
    updated_at      DATETIME2      DEFAULT GETUTCDATE(),
    notes           NVARCHAR(500)  NULL,
    CONSTRAINT uq_override UNIQUE (sku, channel, field_name)
);

-- Override audit log (keeps history of all changes)
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'override_audit_log')
CREATE TABLE override_audit_log (
    id              INT IDENTITY(1,1) PRIMARY KEY,
    sku             NVARCHAR(50)   NOT NULL,
    channel         NVARCHAR(50)   NOT NULL,
    field_name      NVARCHAR(100)  NOT NULL,
    old_value       FLOAT          NULL,
    new_value       FLOAT          NOT NULL,
    changed_by      NVARCHAR(100)  DEFAULT 'local_user',
    changed_at      DATETIME2      DEFAULT GETUTCDATE(),
    notes           NVARCHAR(500)  NULL
);

-- =====================================================
-- Admin Tables (finance-editable assumption tables)
-- =====================================================

-- Admin channel records (master channel list)
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'admin_channel_records')
CREATE TABLE admin_channel_records (
    id              INT IDENTITY(1,1) PRIMARY KEY,
    channel         NVARCHAR(50)   NOT NULL,
    channel_type    NVARCHAR(50)   NULL,
    display_order   INT            DEFAULT 0,
    updated_by      NVARCHAR(100)  DEFAULT 'admin',
    updated_at      DATETIME2      DEFAULT GETUTCDATE()
);

-- Admin channel terms (retail discount rates)
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'admin_channel_terms')
CREATE TABLE admin_channel_terms (
    id                  INT IDENTITY(1,1) PRIMARY KEY,
    channel             NVARCHAR(50)   NOT NULL,
    chargeback          FLOAT          DEFAULT 0,
    early_pay_discount  FLOAT          DEFAULT 0,
    co_op               FLOAT          DEFAULT 0,
    freight_allowance   FLOAT          DEFAULT 0,
    labor               FLOAT          DEFAULT 0,
    damage_allowance    FLOAT          DEFAULT 0,
    end_cap             FLOAT          DEFAULT 0,
    discount_special    FLOAT          DEFAULT 0,
    trade_discount      FLOAT          DEFAULT 0,
    total_discount      FLOAT          DEFAULT 0,
    updated_by          NVARCHAR(100)  DEFAULT 'admin',
    updated_at          DATETIME2      DEFAULT GETUTCDATE()
);

-- Admin static cost assumptions
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'admin_static_assumptions')
CREATE TABLE admin_static_assumptions (
    id              INT IDENTITY(1,1) PRIMARY KEY,
    item            NVARCHAR(100)  NOT NULL,
    unit            NVARCHAR(50)   NULL,
    value           FLOAT          DEFAULT 0,
    cost_type       NVARCHAR(50)   NULL,
    updated_by      NVARCHAR(100)  DEFAULT 'admin',
    updated_at      DATETIME2      DEFAULT GETUTCDATE()
);

-- Admin S&M expenses
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'admin_sm_expenses')
CREATE TABLE admin_sm_expenses (
    id                      INT IDENTITY(1,1) PRIMARY KEY,
    channel_name            NVARCHAR(50)   NOT NULL,
    credit_card_platform_fee FLOAT         DEFAULT 0,
    customer_service        FLOAT          DEFAULT 0,
    marketing               FLOAT          DEFAULT 0,
    updated_by              NVARCHAR(100)  DEFAULT 'admin',
    updated_at              DATETIME2      DEFAULT GETUTCDATE()
);

-- =====================================================
-- Cache Tables (mirrors Snowflake / CSV data)
-- =====================================================

-- Product Directory (from CSV / Snowflake)
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'cache_product_directory')
CREATE TABLE cache_product_directory (
    sku                 NVARCHAR(50)   PRIMARY KEY,
    product_name        NVARCHAR(200)  NULL,
    reference_sku       NVARCHAR(50)   NULL,
    default_msrp        FLOAT          NULL,
    default_fob         FLOAT          NULL,
    default_tariff_rate FLOAT          NULL,
    synced_at           DATETIME2      DEFAULT GETUTCDATE()
);

-- SKU Mapping (from Snowflake)
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'cache_sku_mapping')
CREATE TABLE cache_sku_mapping (
    sku                NVARCHAR(50)   PRIMARY KEY,
    product_group      NVARCHAR(100)  NULL,
    product_category   NVARCHAR(100)  NULL,
    product_line       NVARCHAR(100)  NULL,
    synced_at          DATETIME2      DEFAULT GETUTCDATE()
);

-- PO Discount Rates (from CSV: Input_SKU_Retail Margin)
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'cache_po_discount')
CREATE TABLE cache_po_discount (
    sku                 NVARCHAR(50)   NOT NULL,
    channel             NVARCHAR(50)   NOT NULL,
    po_discount_rate    FLOAT          NOT NULL DEFAULT 0,
    synced_at           DATETIME2      DEFAULT GETUTCDATE(),
    CONSTRAINT pk_po_discount PRIMARY KEY (sku, channel)
);

-- Outbound Shipping (from CSV or Snowflake)
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'cache_outbound_shipping')
CREATE TABLE cache_outbound_shipping (
    sku                     NVARCHAR(50)   NOT NULL,
    channel                 NVARCHAR(50)   NOT NULL,
    outbound_shipping_cost  FLOAT          NOT NULL DEFAULT 0,
    synced_at               DATETIME2      DEFAULT GETUTCDATE(),
    CONSTRAINT pk_outbound_shipping PRIMARY KEY (sku, channel)
);

-- Outbound Shipping (Snowflake raw snapshot for validation comparison)
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'cache_outbound_shipping_sf')
CREATE TABLE cache_outbound_shipping_sf (
    sku                     NVARCHAR(50)   NOT NULL,
    channel                 NVARCHAR(50)   NOT NULL,
    outbound_shipping_cost  FLOAT          NOT NULL DEFAULT 0,
    synced_at               DATETIME2      DEFAULT GETUTCDATE(),
    CONSTRAINT pk_outbound_shipping_sf PRIMARY KEY (sku, channel)
);

-- Return Rate per SKU per Channel (from CSV: Input_SKU_Return Rate)
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'cache_return_rate')
CREATE TABLE cache_return_rate (
    product_line    NVARCHAR(100)  NOT NULL,
    channel         NVARCHAR(50)   NOT NULL,
    return_rate     FLOAT          NOT NULL DEFAULT 0,
    synced_at       DATETIME2      DEFAULT GETUTCDATE(),
    CONSTRAINT pk_return_rate PRIMARY KEY (product_line, channel)
);

-- Return Rate per SKU (from CSV: Input_SKU_Return Rate)
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'cache_return_rate_sku')
CREATE TABLE cache_return_rate_sku (
    sku             NVARCHAR(50)   NOT NULL,
    channel         NVARCHAR(50)   NOT NULL,
    return_rate     FLOAT          DEFAULT 0,
    synced_at       DATETIME2      DEFAULT GETUTCDATE(),
    CONSTRAINT pk_return_rate_sku PRIMARY KEY (sku, channel)
);

-- Cost Assumptions per SKU (from CSV: Input_SKU_CostAssumptions)
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'cache_cost_assumptions')
CREATE TABLE cache_cost_assumptions (
    sku                    NVARCHAR(50)  PRIMARY KEY,
    inbound_freight        FLOAT         DEFAULT 0,
    warehouse_storage      FLOAT         DEFAULT 0,
    amazon_fba             FLOAT         DEFAULT 0,
    expected_product_life  FLOAT         DEFAULT 0,
    synced_at              DATETIME2     DEFAULT GETUTCDATE()
);

-- S&M Expenses per Channel (from CSV: Static_Sales & Marketing Expenses)
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'cache_sm_expenses')
CREATE TABLE cache_sm_expenses (
    channel          NVARCHAR(50)  PRIMARY KEY,
    cc_platform_fee  FLOAT         DEFAULT 0,
    customer_service FLOAT         DEFAULT 0,
    marketing        FLOAT         DEFAULT 0,
    synced_at        DATETIME2     DEFAULT GETUTCDATE()
);

-- Channel Terms (from CSV: Static_Channel Terms)
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'cache_channel_terms')
CREATE TABLE cache_channel_terms (
    channel             NVARCHAR(50)  PRIMARY KEY,
    chargeback          FLOAT         DEFAULT 0,
    early_pay_discount  FLOAT         DEFAULT 0,
    co_op               FLOAT         DEFAULT 0,
    freight_allowance   FLOAT         DEFAULT 0,
    labor               FLOAT         DEFAULT 0,
    damage_allowance    FLOAT         DEFAULT 0,
    end_cap             FLOAT         DEFAULT 0,
    discount_special    FLOAT         DEFAULT 0,
    trade_discount      FLOAT         DEFAULT 0,
    total_discount      FLOAT         DEFAULT 0,
    synced_at           DATETIME2     DEFAULT GETUTCDATE()
);

-- Static Assumptions
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'cache_static_assumptions')
CREATE TABLE cache_static_assumptions (
    key_name        NVARCHAR(100)  PRIMARY KEY,
    key_value       FLOAT          NOT NULL,
    synced_at       DATETIME2      DEFAULT GETUTCDATE()
);

-- =====================================================
-- Pricing Template Tables
-- =====================================================

-- Pricing Template master table
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'pricing_templates')
CREATE TABLE pricing_templates (
    id              INT IDENTITY(1,1) PRIMARY KEY,
    template_key    NVARCHAR(200) NOT NULL UNIQUE,
    sku             NVARCHAR(50)  NOT NULL,
    template_name   NVARCHAR(200) NULL,
    created_by      NVARCHAR(100) NOT NULL,
    created_at      DATETIME2     DEFAULT GETUTCDATE(),
    updated_at      DATETIME2     DEFAULT GETUTCDATE(),
    msrp            FLOAT         NOT NULL,
    fob             FLOAT         NOT NULL,
    tariff_rate     FLOAT         DEFAULT 0,
    promotion_mix   FLOAT         DEFAULT 0,
    promo_percentage FLOAT        DEFAULT 0,
    notes           NVARCHAR(1000) NULL,
    is_active       BIT           DEFAULT 1
);

-- Pricing Template channel mix
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'pricing_template_channel_mix')
CREATE TABLE pricing_template_channel_mix (
    id              INT IDENTITY(1,1) PRIMARY KEY,
    template_id     INT           NOT NULL,
    channel         NVARCHAR(50)  NOT NULL,
    mix_pct         FLOAT         DEFAULT 0,
    CONSTRAINT fk_ptcm_template FOREIGN KEY (template_id)
        REFERENCES pricing_templates(id) ON DELETE CASCADE,
    CONSTRAINT uq_ptcm UNIQUE (template_id, channel)
);

-- Pricing Template assumptions snapshot
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'pricing_template_assumptions')
CREATE TABLE pricing_template_assumptions (
    id              INT IDENTITY(1,1) PRIMARY KEY,
    template_id     INT           NOT NULL,
    channel         NVARCHAR(50)  NOT NULL,
    field_name      NVARCHAR(100) NOT NULL,
    field_value     FLOAT         DEFAULT 0,
    CONSTRAINT fk_pta_template FOREIGN KEY (template_id)
        REFERENCES pricing_templates(id) ON DELETE CASCADE,
    CONSTRAINT uq_pta UNIQUE (template_id, channel, field_name)
);

-- Sync metadata
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'sync_metadata')
CREATE TABLE sync_metadata (
    table_name      NVARCHAR(100)  PRIMARY KEY,
    last_synced_at  DATETIME2      NULL,
    record_count    INT            NULL,
    source          NVARCHAR(50)   DEFAULT 'csv'  -- 'csv', 'snowflake'
);

-- =====================================================
-- Validation Log (data conflict resolution history)
-- =====================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'validation_log')
CREATE TABLE validation_log (
    id              INT IDENTITY(1,1) PRIMARY KEY,
    sku             NVARCHAR(50)   NOT NULL,
    channel         NVARCHAR(50)   NOT NULL,
    field_name      NVARCHAR(100)  NOT NULL,
    cache_value     FLOAT          NULL,
    sf_value        FLOAT          NULL,
    resolution      NVARCHAR(20)   NOT NULL,
    final_value     FLOAT          NOT NULL,
    memo            NVARCHAR(1000) NULL,
    resolved_by     NVARCHAR(100)  DEFAULT 'local_user',
    resolved_at     DATETIME2      DEFAULT GETUTCDATE()
);

-- Channel Mix (Snowflake cache - raw historical data)
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'cache_channel_mix')
CREATE TABLE cache_channel_mix (
    id              INT IDENTITY(1,1) PRIMARY KEY,
    periodname      NVARCHAR(50)   NULL,
    sub_channel     NVARCHAR(100)  NULL,
    product_group   NVARCHAR(100)  NULL,
    product_category NVARCHAR(100) NULL,
    product_line    NVARCHAR(100)  NULL,
    quantity        FLOAT          NULL,
    synced_at       DATETIME2      DEFAULT GETUTCDATE()
);

-- =====================================================
-- User Roles (for RBAC)
-- =====================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'user_roles')
CREATE TABLE user_roles (
    id          INT IDENTITY(1,1) PRIMARY KEY,
    email       NVARCHAR(200) NOT NULL UNIQUE,
    role        NVARCHAR(20)  NOT NULL DEFAULT 'viewer',
    name        NVARCHAR(200) NULL,
    last_login  DATETIME2     NULL,
    created_by  NVARCHAR(100) DEFAULT 'system',
    created_at  DATETIME2     DEFAULT GETUTCDATE(),
    updated_at  DATETIME2     DEFAULT GETUTCDATE()
);
"""


def initialize_schema():
    """Create all tables if they don't exist."""
    conn = get_connection()
    cursor = conn.cursor()
    # Split on ");" to get complete CREATE TABLE statements
    # Each block is "IF NOT EXISTS ... CREATE TABLE ... )"
    blocks = INIT_SQL.split(");")
    for block in blocks:
        block = block.strip()
        # Remove comment-only blocks
        lines = [l for l in block.splitlines() if l.strip() and not l.strip().startswith("--")]
        if not lines:
            continue
        # Re-add the closing ");" that was removed by split
        sql = block + ");"
        try:
            cursor.execute(sql)
        except Exception as e:
            logger.warning(f"Schema init warning: {e}")
    conn.commit()
    conn.close()
    logger.info("Database schema initialized successfully.")


# ---------------------------------------------------------------------------
# Override CRUD Operations
# ---------------------------------------------------------------------------

def get_overrides(sku: Optional[str] = None, channel: Optional[str] = None) -> pd.DataFrame:
    """
    Read user overrides from the database.
    Returns DataFrame with columns: sku, channel, field_name, field_value, updated_by, updated_at
    """
    engine = get_sqlalchemy_engine()
    query = "SELECT sku, channel, field_name, field_value, updated_by, updated_at, notes FROM user_overrides WHERE 1=1"
    params = {}
    if sku:
        query += " AND sku = :sku"
        params["sku"] = sku
    if channel:
        query += " AND channel = :channel"
        params["channel"] = channel
    query += " ORDER BY sku, channel, field_name"

    return pd.read_sql(query, engine, params=params)


def set_override(sku: str, channel: str, field_name: str, new_value: float,
                 user: str = "local_user", notes: str = None):
    """
    Set (insert or update) an override value.
    Also logs the change in audit_log.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Get current value (if exists)
    cursor.execute(
        "SELECT field_value FROM user_overrides WHERE sku=? AND channel=? AND field_name=?",
        (sku, channel, field_name)
    )
    row = cursor.fetchone()
    old_value = row[0] if row else None

    # Upsert (MERGE)
    cursor.execute("""
        MERGE user_overrides AS target
        USING (SELECT ? AS sku, ? AS channel, ? AS field_name) AS source
        ON target.sku = source.sku AND target.channel = source.channel AND target.field_name = source.field_name
        WHEN MATCHED THEN
            UPDATE SET field_value = ?, updated_by = ?, updated_at = GETUTCDATE(), notes = ?
        WHEN NOT MATCHED THEN
            INSERT (sku, channel, field_name, field_value, updated_by, notes)
            VALUES (?, ?, ?, ?, ?, ?);
    """, (sku, channel, field_name,
          new_value, user, notes,
          sku, channel, field_name, new_value, user, notes))

    # Audit log
    cursor.execute("""
        INSERT INTO override_audit_log (sku, channel, field_name, old_value, new_value, changed_by, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (sku, channel, field_name, old_value, new_value, user, notes))

    conn.commit()
    conn.close()


def delete_override(sku: str, channel: str, field_name: str, user: str = "local_user"):
    """Delete an override (revert to Snowflake/default value)."""
    conn = get_connection()
    cursor = conn.cursor()

    # Get current value for audit
    cursor.execute(
        "SELECT field_value FROM user_overrides WHERE sku=? AND channel=? AND field_name=?",
        (sku, channel, field_name)
    )
    row = cursor.fetchone()

    if row:
        # Log deletion
        cursor.execute("""
            INSERT INTO override_audit_log (sku, channel, field_name, old_value, new_value, changed_by, notes)
            VALUES (?, ?, ?, ?, NULL, ?, 'Override deleted - reverted to default')
        """, (sku, channel, field_name, row[0], user))

        # Delete
        cursor.execute(
            "DELETE FROM user_overrides WHERE sku=? AND channel=? AND field_name=?",
            (sku, channel, field_name)
        )

    conn.commit()
    conn.close()


def get_override_audit_log(sku: Optional[str] = None, limit: int = 100) -> pd.DataFrame:
    """Get override change history."""
    engine = get_sqlalchemy_engine()
    query = "SELECT TOP(:limit) * FROM override_audit_log WHERE 1=1"
    params = {"limit": limit}
    if sku:
        query += " AND sku = :sku"
        params["sku"] = sku
    query += " ORDER BY changed_at DESC"
    return pd.read_sql(query, engine, params=params)


# ---------------------------------------------------------------------------
# Cache Operations (populate from CSV or Snowflake)
# ---------------------------------------------------------------------------

def sync_csv_to_cache():
    """
    Load all 7 reference CSV files into Azure SQL cache tables.
    This is the initial population before Snowflake is connected.

    CSV files synced:
      1. Product Directory → cache_product_directory
      2. SKU Mapping → cache_sku_mapping
      3. Retail Margin (PO Discount) → cache_po_discount
      4. Return Rate (per-SKU) → cache_return_rate_sku
      5. Outbound Shipping → cache_outbound_shipping
      6. Cost Assumptions → cache_cost_assumptions
      7. Channel Terms → cache_channel_terms
      8. S&M Expenses → cache_sm_expenses
      9. Static Cost Assumptions → cache_static_assumptions
    """
    from core.data_loader import (
        load_product_directory,
        load_po_discount, load_outbound_shipping,
        load_return_rate_by_sku, load_cost_assumptions,
        load_channel_terms, load_sm_expenses,
        load_static_cost_assumptions,
    )

    engine = get_sqlalchemy_engine()
    now = datetime.utcnow()

    # 1. Product Directory
    products = load_product_directory()
    products_db = products.rename(columns={
        "SKU": "sku",
        "Product Name": "product_name",
        "Reference SKU": "reference_sku",
        "Default MSRP": "default_msrp",
        "Default FOB": "default_fob",
        "Default Tariff Rate": "default_tariff_rate",
    })
    products_db["synced_at"] = now
    products_db = products_db[[c for c in ["sku", "product_name", "reference_sku",
                                            "default_msrp", "default_fob",
                                            "default_tariff_rate", "synced_at"]
                               if c in products_db.columns]]
    products_db.to_sql("cache_product_directory", engine, if_exists="replace", index=False)

    # 2. SKU Mapping — SKIPPED: comes from Snowflake sync only (snowflake_sync.sync_sku_mapping)
    #    CSV fallback (SF_SKU Mapping.csv) is used at read-time by data_loader.load_sku_mapping()

    # 3. PO Discount / Retail Margin
    po = load_po_discount()
    po_db = po.rename(columns={
        "SKU": "sku",
        "Channel": "channel",
        "PO_Discount_Rate": "po_discount_rate",
    })
    # Drop rows where po_discount_rate is NaN (no data, not 0)
    po_db = po_db.dropna(subset=["po_discount_rate"])
    po_db["synced_at"] = now
    po_db.to_sql("cache_po_discount", engine, if_exists="replace", index=False)

    # 4. Return Rate (per-SKU per-channel)
    rr = load_return_rate_by_sku()
    if not rr.empty:
        rr_db = rr.rename(columns={
            "SKU": "sku",
            "Channel": "channel",
            "Return_Rate": "return_rate",
        })
        rr_db = rr_db.dropna(subset=["return_rate"])
        rr_db["synced_at"] = now
        rr_db.to_sql("cache_return_rate_sku", engine, if_exists="replace", index=False)

    # 5. Outbound Shipping
    ob = load_outbound_shipping()
    if not ob.empty:
        ob_db = ob.rename(columns={
            "SKU": "sku",
            "Channel": "channel",
            "Outbound_Shipping_Cost": "outbound_shipping_cost",
        })
        ob_db = ob_db.dropna(subset=["outbound_shipping_cost"])
        ob_db["synced_at"] = now
        ob_db.to_sql("cache_outbound_shipping", engine, if_exists="replace", index=False)

    # 6. Cost Assumptions (per-SKU)
    costs = load_cost_assumptions()
    if not costs.empty:
        costs_db = costs.rename(columns={
            "SKU": "sku",
            "Inbound_Freight": "inbound_freight",
            "Warehouse_Storage": "warehouse_storage",
            "Amazon_FBA": "amazon_fba",
            "Expected_Product_Life": "expected_product_life",
        })
        costs_db["synced_at"] = now
        costs_db = costs_db[[c for c in ["sku", "inbound_freight", "warehouse_storage",
                                          "amazon_fba", "expected_product_life", "synced_at"]
                             if c in costs_db.columns]]
        costs_db.to_sql("cache_cost_assumptions", engine, if_exists="replace", index=False)

    # 7. Channel Terms
    ct = load_channel_terms()
    if not ct.empty:
        ct_db = ct.rename(columns={
            "Channel": "channel",
            "Chargeback": "chargeback",
            "Early Pay Discount": "early_pay_discount",
            "Co-Op": "co_op",
            "Freight Allowance": "freight_allowance",
            "Labor": "labor",
            "Damage Allowance": "damage_allowance",
            "End Cap": "end_cap",
            "Discount Special": "discount_special",
            "Trade Discount": "trade_discount",
            "Total Discount": "total_discount",
        })
        ct_db["synced_at"] = now
        keep_cols = ["channel", "chargeback", "early_pay_discount", "co_op",
                     "freight_allowance", "labor", "damage_allowance", "end_cap",
                     "discount_special", "trade_discount", "total_discount", "synced_at"]
        ct_db = ct_db[[c for c in keep_cols if c in ct_db.columns]]
        ct_db.to_sql("cache_channel_terms", engine, if_exists="replace", index=False)

    # 8. S&M Expenses
    sm = load_sm_expenses()
    if not sm.empty:
        sm_db = sm.rename(columns={
            "Channel": "channel",
            "CC_Platform_Fee": "cc_platform_fee",
            "Customer_Service": "customer_service",
            "Marketing": "marketing",
        })
        sm_db["synced_at"] = now
        sm_db = sm_db[[c for c in ["channel", "cc_platform_fee", "customer_service",
                                    "marketing", "synced_at"]
                       if c in sm_db.columns]]
        sm_db.to_sql("cache_sm_expenses", engine, if_exists="replace", index=False)

    # 9. Static Cost Assumptions
    static = load_static_cost_assumptions()
    if not static.empty:
        static_db = static.rename(columns={
            "Item": "key_name",
            "Value": "key_value",
        })
        static_db["synced_at"] = now
        static_db = static_db[[c for c in ["key_name", "key_value", "synced_at"]
                               if c in static_db.columns]]
        static_db.to_sql("cache_static_assumptions", engine, if_exists="replace", index=False)

    # Also sync finance-related CSVs to admin tables (for Finance Assumptions page)
    conn = get_connection()
    cursor = conn.cursor()

    # Admin Channel Terms
    if not ct.empty:
        cursor.execute("DELETE FROM admin_channel_terms")
        for _, row in ct_db.iterrows():
            ch = row.get("channel", "")
            if not ch:
                continue
            cursor.execute("""
                INSERT INTO admin_channel_terms
                (channel, chargeback, early_pay_discount, co_op, freight_allowance,
                 labor, damage_allowance, end_cap, discount_special, trade_discount, total_discount, updated_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ch,
                float(row.get("chargeback", 0) or 0),
                float(row.get("early_pay_discount", 0) or 0),
                float(row.get("co_op", 0) or 0),
                float(row.get("freight_allowance", 0) or 0),
                float(row.get("labor", 0) or 0),
                float(row.get("damage_allowance", 0) or 0),
                float(row.get("end_cap", 0) or 0),
                float(row.get("discount_special", 0) or 0),
                float(row.get("trade_discount", 0) or 0),
                float(row.get("total_discount", 0) or 0),
                "csv_sync",
            ))

    # Admin S&M Expenses
    if not sm.empty:
        cursor.execute("DELETE FROM admin_sm_expenses")
        for _, row in sm_db.iterrows():
            ch = row.get("channel", "")
            if not ch:
                continue
            cursor.execute("""
                INSERT INTO admin_sm_expenses
                (channel_name, credit_card_platform_fee, customer_service, marketing, updated_by)
                VALUES (?, ?, ?, ?, ?)
            """, (
                ch,
                float(row.get("cc_platform_fee", 0) or 0),
                float(row.get("customer_service", 0) or 0),
                float(row.get("marketing", 0) or 0),
                "csv_sync",
            ))

    conn.commit()
    conn.close()

    # Update sync metadata
    conn = get_connection()
    cursor = conn.cursor()
    tables = [
        ("cache_product_directory", len(products)),
        # cache_sku_mapping excluded — populated by Snowflake sync only
        ("cache_po_discount", len(po_db) if not po.empty else 0),
        ("cache_return_rate_sku", len(rr_db) if not rr.empty else 0),
        ("cache_outbound_shipping", len(ob_db) if not ob.empty else 0),
        ("cache_cost_assumptions", len(costs) if not costs.empty else 0),
        ("cache_channel_terms", len(ct) if not ct.empty else 0),
        ("cache_sm_expenses", len(sm) if not sm.empty else 0),
        ("cache_static_assumptions", len(static) if not static.empty else 0),
    ]
    for table_name, count in tables:
        cursor.execute("""
            MERGE sync_metadata AS target
            USING (SELECT ? AS table_name) AS source
            ON target.table_name = source.table_name
            WHEN MATCHED THEN
                UPDATE SET last_synced_at = ?, record_count = ?, source = 'csv'
            WHEN NOT MATCHED THEN
                INSERT (table_name, last_synced_at, record_count, source)
                VALUES (?, ?, ?, 'csv');
        """, (table_name, now, count, table_name, now, count))
    conn.commit()
    conn.close()

    return {t: c for t, c in tables}


# ---------------------------------------------------------------------------
# Merged Data Loader (Override > Cache — DB only)
# ---------------------------------------------------------------------------

def load_merged_data(sku: str) -> dict:
    """
    Load data for a SKU with override priority:
      1. User Override (Azure SQL user_overrides table)
      2. Cache data (Azure SQL cache tables)

    Returns dict of DataFrames ready for CPAM calculation.
    """
    engine = get_sqlalchemy_engine()

    products = pd.read_sql(
        f"SELECT * FROM cache_product_directory WHERE sku = '{sku}'", engine
    )
    overrides = pd.read_sql(
        f"SELECT * FROM user_overrides WHERE sku = '{sku}'", engine
    )

    return {
        "products": products,
        "overrides": overrides,
        "source": "azure_sql",
    }


# ---------------------------------------------------------------------------
# Admin / Debug
# ---------------------------------------------------------------------------

def get_sync_status() -> pd.DataFrame:
    """Get sync status for all cache tables."""
    try:
        engine = get_sqlalchemy_engine()
        return pd.read_sql("SELECT * FROM sync_metadata ORDER BY table_name", engine)
    except Exception as e:
        return pd.DataFrame({"error": [str(e)]})


def get_table_counts() -> dict:
    """Get row counts for all relevant tables."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        tables = [
            # Override tables
            "user_overrides", "override_audit_log",
            # Admin tables
            "admin_channel_records", "admin_channel_terms",
            "admin_static_assumptions", "admin_sm_expenses",
            # Cache tables
            "cache_product_directory", "cache_sku_mapping",
            "cache_po_discount", "cache_outbound_shipping",
            "cache_return_rate", "cache_return_rate_sku",
            "cache_cost_assumptions", "cache_sm_expenses",
            "cache_channel_terms", "cache_static_assumptions",
            "cache_channel_mix",
            # Validation
            "validation_log",
            # Template tables
            "pricing_templates", "pricing_template_channel_mix",
            "pricing_template_assumptions",
            # Auth
            "user_roles",
        ]
        counts = {}
        for t in tables:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {t}")
                counts[t] = cursor.fetchone()[0]
            except Exception:
                counts[t] = "N/A"
        conn.close()
        return counts
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# SKU Creation & Assumption Cloning
# ---------------------------------------------------------------------------

def sku_exists(sku: str) -> bool:
    """Check if a SKU already exists in cache_product_directory."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM cache_product_directory WHERE sku = ?", (sku,)
        )
        count = cursor.fetchone()[0]
        conn.close()
        return count > 0
    except Exception:
        return False


def clone_assumptions_from_ref_sku(
    new_sku: str,
    ref_sku: str,
    product_name: str,
    default_msrp: float,
    default_fob: float,
    default_tariff_rate: float,
    user: str = "local_user",
) -> dict:
    """
    Create a new SKU in cache_product_directory and clone all assumptions
    from ref_sku into the new SKU across all relevant cache tables.

    Returns dict of {table_name: rows_copied}.
    """
    conn = get_connection()
    cursor = conn.cursor()
    results = {}

    # 1. Insert into cache_product_directory
    cursor.execute("""
        INSERT INTO cache_product_directory
            (sku, product_name, reference_sku, default_msrp, default_fob, default_tariff_rate, synced_at)
        VALUES (?, ?, ?, ?, ?, ?, GETUTCDATE())
    """, (new_sku, product_name, ref_sku, default_msrp, default_fob, default_tariff_rate))
    results["cache_product_directory"] = 1

    # 2. Clone cache_po_discount
    cursor.execute("""
        INSERT INTO cache_po_discount (sku, channel, po_discount_rate, synced_at)
        SELECT ?, channel, po_discount_rate, GETUTCDATE()
        FROM cache_po_discount WHERE sku = ?
    """, (new_sku, ref_sku))
    results["cache_po_discount"] = cursor.rowcount

    # 3. Clone cache_return_rate_sku
    cursor.execute("""
        INSERT INTO cache_return_rate_sku (sku, channel, return_rate, synced_at)
        SELECT ?, channel, return_rate, GETUTCDATE()
        FROM cache_return_rate_sku WHERE sku = ?
    """, (new_sku, ref_sku))
    results["cache_return_rate_sku"] = cursor.rowcount

    # 4. Clone cache_outbound_shipping
    cursor.execute("""
        INSERT INTO cache_outbound_shipping (sku, channel, outbound_shipping_cost, synced_at)
        SELECT ?, channel, outbound_shipping_cost, GETUTCDATE()
        FROM cache_outbound_shipping WHERE sku = ?
    """, (new_sku, ref_sku))
    results["cache_outbound_shipping"] = cursor.rowcount

    # 5. Clone cache_cost_assumptions
    cursor.execute("""
        INSERT INTO cache_cost_assumptions
            (sku, inbound_freight, warehouse_storage, amazon_fba, expected_product_life, synced_at)
        SELECT ?, inbound_freight, warehouse_storage, amazon_fba, expected_product_life, GETUTCDATE()
        FROM cache_cost_assumptions WHERE sku = ?
    """, (new_sku, ref_sku))
    results["cache_cost_assumptions"] = cursor.rowcount

    # 6. Audit log entry
    cursor.execute("""
        INSERT INTO override_audit_log
            (sku, channel, field_name, old_value, new_value, changed_by, notes)
        VALUES (?, '_all_', 'sku_created', NULL, 0, ?, ?)
    """, (new_sku, user, f"SKU created, assumptions cloned from {ref_sku}"))

    conn.commit()
    conn.close()

    return results


def update_product_directory(
    sku: str,
    product_name: str,
    reference_sku: Optional[str],
    default_msrp: float,
    default_fob: float,
    default_tariff_rate: float,
    user: str = "local_user",
):
    """
    Update an existing product directory record.
    Does NOT touch assumption tables — caller handles re-clone if reference_sku changed.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE cache_product_directory
        SET product_name = ?, reference_sku = ?,
            default_msrp = ?, default_fob = ?, default_tariff_rate = ?,
            synced_at = GETUTCDATE()
        WHERE sku = ?
    """, (product_name, reference_sku, default_msrp, default_fob, default_tariff_rate, sku))
    conn.commit()
    conn.close()


def reclone_assumptions_from_ref_sku(
    sku: str,
    new_ref_sku: str,
    user: str = "local_user",
) -> dict:
    """
    Delete existing assumptions for `sku` and re-clone from `new_ref_sku`.
    Used when user changes the reference_sku on the product directory.

    Returns dict of {table_name: rows_cloned}.
    """
    conn = get_connection()
    cursor = conn.cursor()
    results = {}

    tables_config = [
        ("cache_po_discount", "sku, channel, po_discount_rate, synced_at",
         "?, channel, po_discount_rate, GETUTCDATE()"),
        ("cache_return_rate_sku", "sku, channel, return_rate, synced_at",
         "?, channel, return_rate, GETUTCDATE()"),
        ("cache_outbound_shipping", "sku, channel, outbound_shipping_cost, synced_at",
         "?, channel, outbound_shipping_cost, GETUTCDATE()"),
        ("cache_cost_assumptions", "sku, inbound_freight, warehouse_storage, amazon_fba, expected_product_life, synced_at",
         "?, inbound_freight, warehouse_storage, amazon_fba, expected_product_life, GETUTCDATE()"),
    ]

    for tbl, ins_cols, sel_expr in tables_config:
        # Delete old
        cursor.execute(f"DELETE FROM {tbl} WHERE sku = ?", (sku,))
        # Clone from new ref
        cursor.execute(f"""
            INSERT INTO {tbl} ({ins_cols})
            SELECT {sel_expr}
            FROM {tbl} WHERE sku = ?
        """, (sku, new_ref_sku))
        results[tbl] = cursor.rowcount

    # Audit
    cursor.execute("""
        INSERT INTO override_audit_log
            (sku, channel, field_name, old_value, new_value, changed_by, notes)
        VALUES (?, '_all_', 'ref_sku_changed', NULL, 0, ?, ?)
    """, (sku, user, f"Reference SKU changed to {new_ref_sku}, assumptions re-cloned"))

    conn.commit()
    conn.close()
    return results


def delete_sku(sku: str, user: str = "local_user"):
    """
    Delete a SKU from cache_product_directory and all 4 assumption tables.
    Records audit log entry.
    """
    conn = get_connection()
    cursor = conn.cursor()

    for tbl in [
        "cache_po_discount",
        "cache_return_rate_sku",
        "cache_outbound_shipping",
        "cache_cost_assumptions",
        "cache_product_directory",
    ]:
        cursor.execute(f"DELETE FROM {tbl} WHERE sku = ?", (sku,))

    cursor.execute("""
        INSERT INTO override_audit_log
            (sku, channel, field_name, old_value, new_value, changed_by, notes)
        VALUES (?, '_all_', 'sku_deleted', NULL, 0, ?, ?)
    """, (sku, user, f"SKU {sku} deleted from directory + all assumption tables"))

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Validation Log Operations
# ---------------------------------------------------------------------------

def get_validation_log(sku: Optional[str] = None, limit: int = 200) -> pd.DataFrame:
    """Get validation conflict resolution history."""
    try:
        engine = get_sqlalchemy_engine()
        query = "SELECT TOP(:limit) * FROM validation_log WHERE 1=1"
        params = {"limit": limit}
        if sku:
            query += " AND sku = :sku"
            params["sku"] = sku
        query += " ORDER BY resolved_at DESC"
        return pd.read_sql(query, engine, params=params)
    except Exception as e:
        logger.warning(f"Failed to load validation log: {e}")
        return pd.DataFrame()


def resolve_validation_conflict(
    sku: str,
    channel: str,
    field_name: str,
    cache_value: float,
    sf_value: float,
    resolution: str,
    final_value: float,
    memo: str = "",
    user: str = "local_user",
):
    """
    Record a validation conflict resolution and update the cache table.

    resolution: 'keep_cache' | 'accept_sf' | 'manual'
    field_name: 'return_rate' | 'outbound_shipping'
    """
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Insert into validation_log
    cursor.execute("""
        INSERT INTO validation_log
            (sku, channel, field_name, cache_value, sf_value, resolution, final_value, memo, resolved_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (sku, channel, field_name, cache_value, sf_value, resolution, final_value, memo, user))

    # 2. Update the cache table with the final value
    if field_name == "return_rate":
        cursor.execute("""
            MERGE cache_return_rate_sku AS target
            USING (SELECT ? AS sku, ? AS channel) AS source
            ON target.sku = source.sku AND target.channel = source.channel
            WHEN MATCHED THEN
                UPDATE SET return_rate = ?, synced_at = GETUTCDATE()
            WHEN NOT MATCHED THEN
                INSERT (sku, channel, return_rate, synced_at)
                VALUES (?, ?, ?, GETUTCDATE());
        """, (sku, channel, final_value, sku, channel, final_value))

    elif field_name == "outbound_shipping":
        cursor.execute("""
            MERGE cache_outbound_shipping AS target
            USING (SELECT ? AS sku, ? AS channel) AS source
            ON target.sku = source.sku AND target.channel = source.channel
            WHEN MATCHED THEN
                UPDATE SET outbound_shipping_cost = ?, synced_at = GETUTCDATE()
            WHEN NOT MATCHED THEN
                INSERT (sku, channel, outbound_shipping_cost, synced_at)
                VALUES (?, ?, ?, GETUTCDATE());
        """, (sku, channel, final_value, sku, channel, final_value))

    conn.commit()
    conn.close()


def batch_resolve_validation(
    rows: list[dict],
    field_name: str,
    resolution: str,
    memo: str = "",
    user: str = "local_user",
) -> int:
    """
    Batch-resolve multiple validation conflicts at once.

    rows: list of dicts, each with keys: sku, channel, cache_value, sf_value
    field_name: 'return_rate' | 'outbound_shipping'
    resolution: 'keep_cache' | 'accept_sf'
    memo: shared memo for all rows
    user: who resolved

    Returns number of rows resolved.
    """
    if not rows:
        return 0

    conn = get_connection()
    cursor = conn.cursor()
    count = 0

    for row in rows:
        sku = row["sku"]
        channel = row["channel"]
        cache_value = float(row["cache_value"])
        sf_value = float(row["sf_value"])

        if resolution == "keep_cache":
            final_value = cache_value
        elif resolution == "accept_sf":
            final_value = sf_value
        else:
            continue  # batch only supports keep_cache / accept_sf

        # 1. Insert into validation_log
        cursor.execute("""
            INSERT INTO validation_log
                (sku, channel, field_name, cache_value, sf_value, resolution, final_value, memo, resolved_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (sku, channel, field_name, cache_value, sf_value, resolution, final_value, memo, user))

        # 2. Update the cache table
        if field_name == "return_rate":
            cursor.execute("""
                MERGE cache_return_rate_sku AS target
                USING (SELECT ? AS sku, ? AS channel) AS source
                ON target.sku = source.sku AND target.channel = source.channel
                WHEN MATCHED THEN
                    UPDATE SET return_rate = ?, synced_at = GETUTCDATE()
                WHEN NOT MATCHED THEN
                    INSERT (sku, channel, return_rate, synced_at)
                    VALUES (?, ?, ?, GETUTCDATE());
            """, (sku, channel, final_value, sku, channel, final_value))

        elif field_name == "outbound_shipping":
            cursor.execute("""
                MERGE cache_outbound_shipping AS target
                USING (SELECT ? AS sku, ? AS channel) AS source
                ON target.sku = source.sku AND target.channel = source.channel
                WHEN MATCHED THEN
                    UPDATE SET outbound_shipping_cost = ?, synced_at = GETUTCDATE()
                WHEN NOT MATCHED THEN
                    INSERT (sku, channel, outbound_shipping_cost, synced_at)
                    VALUES (?, ?, ?, GETUTCDATE());
            """, (sku, channel, final_value, sku, channel, final_value))

        count += 1

    conn.commit()
    conn.close()
    return count


# ---------------------------------------------------------------------------
# User Role Management (RBAC)
# ---------------------------------------------------------------------------

def get_user_role(email: str) -> str:
    """Get role for a user email. Falls back to DEFAULT_ROLE if not found."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT role FROM user_roles WHERE email = ?", (email.lower(),))
        row = cursor.fetchone()
        conn.close()
        if row:
            return row[0]
    except Exception:
        pass
    return "editor"  # DEFAULT_ROLE


def set_user_role(email: str, role: str, name: str = None, updated_by: str = "admin"):
    """Insert or update a user role."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        MERGE user_roles AS target
        USING (SELECT ? AS email) AS source
        ON target.email = source.email
        WHEN MATCHED THEN
            UPDATE SET role = ?, name = COALESCE(?, target.name),
                       updated_at = GETUTCDATE()
        WHEN NOT MATCHED THEN
            INSERT (email, role, name, created_by)
            VALUES (?, ?, ?, ?);
    """, (email.lower(), role, name, email.lower(), role, name, updated_by))
    conn.commit()
    conn.close()


def delete_user_role(email: str):
    """Remove a user role entry."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM user_roles WHERE email = ?", (email.lower(),))
    conn.commit()
    conn.close()


def list_all_users() -> pd.DataFrame:
    """List all users and their roles."""
    try:
        engine = get_sqlalchemy_engine()
        return pd.read_sql(
            "SELECT email, role, name, last_login, created_at, updated_at FROM user_roles ORDER BY email",
            engine,
        )
    except Exception:
        return pd.DataFrame(columns=["email", "role", "name", "last_login", "created_at", "updated_at"])


def update_last_login(email: str, name: str = None):
    """Update last_login timestamp. Creates user entry if not exists."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            MERGE user_roles AS target
            USING (SELECT ? AS email) AS source
            ON target.email = source.email
            WHEN MATCHED THEN
                UPDATE SET last_login = GETUTCDATE(),
                           name = COALESCE(?, target.name)
            WHEN NOT MATCHED THEN
                INSERT (email, role, name, last_login, created_by)
                VALUES (?, 'editor', ?, GETUTCDATE(), 'auto');
        """, (email.lower(), name, email.lower(), name))
        conn.commit()
        conn.close()
    except Exception:
        pass