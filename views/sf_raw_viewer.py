"""
Snowflake Raw Data Viewer
Browse cached Snowflake data: Return Rate, Outbound Shipping, Channel Mix, SKU Mapping.
Filters, search, and CSV download for each dataset.
"""

import streamlit as st
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.ui_helpers import styled_header
from core.auth import require_permission
styled_header("Snowflake Raw Data", "Browse cached Snowflake data synced to Azure SQL. Use DB Admin to trigger a new sync.", color="cyan")
require_permission("sync_snowflake", "SF Raw Data")

# --- Check DB connection ---
engine = None
try:
    from core.database import get_sqlalchemy_engine
    engine = get_sqlalchemy_engine()
except Exception as e:
    st.error(f"Database connection required. Error: {e}")
    st.page_link("views/db_admin.py", label="Go to DB Admin ->")
    st.stop()


def _load_table(table_name: str) -> pd.DataFrame:
    """Load a cache table from Azure SQL."""
    try:
        df = pd.read_sql_table(table_name, engine)
        return df if df is not None else pd.DataFrame()
    except Exception as e:
        st.warning(f"Could not load {table_name}: {e}")
        return pd.DataFrame()


def _csv_download(df: pd.DataFrame, filename: str):
    """Add a CSV download button."""
    if not df.empty:
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label=f"Download {filename}",
            data=csv,
            file_name=filename,
            mime="text/csv",
        )


# --- Tabs ---
from core.ui_helpers import styled_tabs
import streamlit_antd_components as sac

active_tab = styled_tabs(
    ["Return Rate", "Outbound Shipping", "Channel Mix", "SKU Mapping"],
    icons=["arrow-repeat", "truck", "pie-chart", "diagram-3"],
    key="sf_tabs",
)

# ===========================================================================
# Tab 1: Return Rate (cache_return_rate - Snowflake full history)
# ===========================================================================
if active_tab == "Return Rate":
    st.subheader("Return Rate History (Snowflake)")
    st.caption("Source: `DATA_MART.FINANCE.ROLLING_RETURN_RATE_SELLIN` -> `cache_return_rate`")

    df_rr = _load_table("cache_return_rate")
    if df_rr.empty:
        st.info("No return rate data found. Sync from Snowflake in DB Admin.")
    else:
        # Also try to load the full Snowflake cache if columns exist
        df_rr.columns = [c.lower() for c in df_rr.columns]

        # Filters
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            if "product_line" in df_rr.columns:
                pl_options = ["All"] + sorted(df_rr["product_line"].dropna().unique().tolist())
                sel_pl = st.selectbox("Product Line", pl_options, key="rr_pl")
            else:
                sel_pl = "All"
        with col_f2:
            ch_col = "channel" if "channel" in df_rr.columns else "sub_channel" if "sub_channel" in df_rr.columns else None
            if ch_col:
                ch_options = ["All"] + sorted(df_rr[ch_col].dropna().unique().tolist())
                sel_ch = st.selectbox("Channel", ch_options, key="rr_ch")
            else:
                sel_ch = "All"
        with col_f3:
            if "month_start" in df_rr.columns:
                df_rr["month_start"] = pd.to_datetime(df_rr["month_start"], errors="coerce")
                min_date = df_rr["month_start"].min()
                max_date = df_rr["month_start"].max()
                if pd.notna(min_date) and pd.notna(max_date):
                    date_range = st.date_input(
                        "Date Range",
                        value=(min_date.date(), max_date.date()),
                        key="rr_date",
                    )
                else:
                    date_range = None
            else:
                date_range = None

        filtered = df_rr.copy()
        if sel_pl != "All" and "product_line" in filtered.columns:
            filtered = filtered[filtered["product_line"] == sel_pl]
        if sel_ch != "All" and ch_col:
            filtered = filtered[filtered[ch_col] == sel_ch]
        if date_range and len(date_range) == 2 and "month_start" in filtered.columns:
            filtered = filtered[
                (filtered["month_start"] >= pd.Timestamp(date_range[0])) &
                (filtered["month_start"] <= pd.Timestamp(date_range[1]))
            ]

        st.metric("Records", len(filtered))
        st.dataframe(filtered, use_container_width=True, hide_index=True, height=500)
        _csv_download(filtered, "return_rate_raw.csv")

# ===========================================================================
# Tab 2: Outbound Shipping
# ===========================================================================
elif active_tab == "Outbound Shipping":
    st.subheader("Outbound Shipping (Snowflake)")
    st.caption("Source: `DATA_MART.FINANCE.SHIPPING_COST_EST_SUPPLEMENT` -> `cache_outbound_shipping`")

    df_ship = _load_table("cache_outbound_shipping")
    if df_ship.empty:
        st.info("No outbound shipping data found. Sync from Snowflake in DB Admin.")
    else:
        df_ship.columns = [c.lower() for c in df_ship.columns]

        # Filters
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            sku_search = st.text_input("Search SKU", placeholder="e.g. WYZECPAN", key="ship_sku")
        with col_s2:
            if "channel" in df_ship.columns:
                ship_ch_opts = ["All"] + sorted(df_ship["channel"].dropna().unique().tolist())
                sel_ship_ch = st.selectbox("Channel", ship_ch_opts, key="ship_ch")
            else:
                sel_ship_ch = "All"

        filtered_ship = df_ship.copy()
        if sku_search and "sku" in filtered_ship.columns:
            filtered_ship = filtered_ship[
                filtered_ship["sku"].str.contains(sku_search, case=False, na=False)
            ]
        if sel_ship_ch != "All" and "channel" in filtered_ship.columns:
            filtered_ship = filtered_ship[filtered_ship["channel"] == sel_ship_ch]

        st.metric("Records", len(filtered_ship))
        st.dataframe(filtered_ship, use_container_width=True, hide_index=True, height=500)
        _csv_download(filtered_ship, "outbound_shipping_raw.csv")

# ===========================================================================
# Tab 3: Channel Mix
# ===========================================================================
elif active_tab == "Channel Mix":
    st.subheader("Channel Mix History (Snowflake)")
    st.caption("Source: `FINANCE_TEAM_DB.REFERENCES.PRICING_TOOL_CHANNEL_MIX` -> `cache_channel_mix`")

    df_mix = _load_table("cache_channel_mix")
    if df_mix.empty:
        st.info("No channel mix data found. Sync from Snowflake in DB Admin.")
    else:
        df_mix.columns = [c.lower() for c in df_mix.columns]

        # Filters
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            if "product_line" in df_mix.columns:
                mix_pl_opts = ["All"] + sorted(df_mix["product_line"].dropna().unique().tolist())
                sel_mix_pl = st.selectbox("Product Line", mix_pl_opts, key="mix_pl")
            else:
                sel_mix_pl = "All"
        with col_m2:
            if "periodname" in df_mix.columns:
                period_opts = ["All"] + sorted(df_mix["periodname"].dropna().unique().tolist(), reverse=True)
                sel_period = st.selectbox("Period", period_opts, key="mix_period")
            else:
                sel_period = "All"

        filtered_mix = df_mix.copy()
        if sel_mix_pl != "All" and "product_line" in filtered_mix.columns:
            filtered_mix = filtered_mix[filtered_mix["product_line"] == sel_mix_pl]
        if sel_period != "All" and "periodname" in filtered_mix.columns:
            filtered_mix = filtered_mix[filtered_mix["periodname"] == sel_period]

        st.metric("Records", len(filtered_mix))
        st.dataframe(filtered_mix, use_container_width=True, hide_index=True, height=500)
        _csv_download(filtered_mix, "channel_mix_raw.csv")

# ===========================================================================
# Tab 4: SKU Mapping
# ===========================================================================
elif active_tab == "SKU Mapping":
    st.subheader("SKU Mapping (Snowflake)")
    st.caption("Source: `DATA_MART.FINANCE.SKU_MAPPING` -> `cache_sku_mapping`")

    df_sku = _load_table("cache_sku_mapping")
    if df_sku.empty:
        st.info("No SKU mapping data found. Sync from Snowflake in DB Admin.")
    else:
        df_sku.columns = [c.lower() for c in df_sku.columns]

        # Search
        sku_map_search = st.text_input(
            "Search by SKU, Product Group, or Product Line",
            placeholder="e.g. WYZECPAN or Cameras",
            key="sku_map_search",
        )

        filtered_sku = df_sku.copy()
        if sku_map_search:
            mask = pd.Series(False, index=filtered_sku.index)
            for col in filtered_sku.columns:
                if filtered_sku[col].dtype == "object":
                    mask = mask | filtered_sku[col].str.contains(sku_map_search, case=False, na=False)
            filtered_sku = filtered_sku[mask]

        st.metric("Records", len(filtered_sku))
        st.dataframe(filtered_sku, use_container_width=True, hide_index=True, height=500)
        _csv_download(filtered_sku, "sku_mapping_raw.csv")
