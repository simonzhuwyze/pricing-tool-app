"""
Data Validation Page
Compare cache values (per-SKU assumptions) against Snowflake latest data.
Resolve conflicts: keep cache, accept Snowflake, or manual override with memo.
Supports both individual and batch resolution.
View resolution history.
"""

import streamlit as st
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.ui_helpers import styled_header, styled_divider, styled_metric_cards, styled_tabs
import streamlit_antd_components as sac

styled_header("Data Validation", "Compare per-SKU cache assumptions against Snowflake source data. Resolve conflicts individually or in batch.")

# --- Check DB connection ---
engine = None
try:
    from core.database import get_sqlalchemy_engine, get_connection
    engine = get_sqlalchemy_engine()
except Exception as e:
    st.error(f"Database connection required. Error: {e}")
    st.page_link("pages/db_admin.py", label="Go to DB Admin ->")
    st.stop()

# Import canonical sub-channel mapping from data_loader
from core.data_loader import SUBCHANNEL_MAP as RETURN_RATE_SUBCHANNEL_MAP


# ===========================================================================
# Helper: Load SKU -> product_line mapping (shared by both tabs)
# ===========================================================================
@st.cache_data(ttl=300)
def _load_sku_product_line_map() -> dict:
    """Load SKU -> product_line from cache_sku_mapping + reference_sku fallback."""
    try:
        sku_map = pd.read_sql("SELECT sku, product_line FROM cache_sku_mapping", engine)
        sku_map.columns = [c.lower() for c in sku_map.columns]
        sku_pl = dict(zip(sku_map["sku"], sku_map["product_line"]))
    except Exception:
        sku_pl = {}

    try:
        prod_dir = pd.read_sql("SELECT sku, reference_sku FROM cache_product_directory", engine)
        prod_dir.columns = [c.lower() for c in prod_dir.columns]
        ref_map = dict(zip(prod_dir["sku"], prod_dir["reference_sku"]))
    except Exception:
        ref_map = {}

    # Fill missing via reference_sku
    for sku, ref in ref_map.items():
        if sku not in sku_pl and ref and pd.notna(ref) and ref in sku_pl:
            sku_pl[sku] = sku_pl[ref]

    return sku_pl


# ===========================================================================
# Helper: Build Return Rate comparison
# ===========================================================================
def build_return_rate_comparison(skus: list) -> pd.DataFrame:
    """
    For each SKU+Channel in cache_return_rate_sku (CSV old / user edits):
    1. Look up SKU's product_line from cache_sku_mapping
    2. Find latest return_rate_12m_pct in cache_return_rate (Snowflake raw)
       for that product_line + sub_channel
    3. Convert SF pct value to decimal (SF=2.02% -> 0.0202) for comparison
    4. Show diffs sorted by magnitude

    Returns DataFrame: sku, channel, product_line, cache_value, sf_value, diff
    """
    cols = ["sku", "channel", "product_line", "cache_value", "sf_value", "diff"]
    try:
        # Load cache per-SKU return rates (CSV old data, decimal form e.g. 0.0064)
        cache_rr = pd.read_sql("SELECT sku, channel, return_rate FROM cache_return_rate_sku", engine)
        cache_rr.columns = [c.lower() for c in cache_rr.columns]

        if skus:
            cache_rr = cache_rr[cache_rr["sku"].isin(skus)]

        if cache_rr.empty:
            return pd.DataFrame(columns=cols)

        # Load SKU -> product_line mapping
        sku_pl = _load_sku_product_line_map()

        # Load Snowflake raw return rate (full history, pct form e.g. 2.02 = 2.02%)
        try:
            sf_rr = pd.read_sql("""
                SELECT product_line, sub_channel, month_start, return_rate_12m_pct
                FROM cache_return_rate
                WHERE return_rate_12m_pct IS NOT NULL
            """, engine)
            sf_rr.columns = [c.lower() for c in sf_rr.columns]
        except Exception:
            sf_rr = pd.DataFrame()

        if sf_rr.empty:
            return pd.DataFrame(columns=cols)

        # Get latest month per product_line + sub_channel
        sf_rr["month_start"] = pd.to_datetime(sf_rr["month_start"], errors="coerce")
        sf_rr = sf_rr.dropna(subset=["month_start"])
        idx = sf_rr.groupby(["product_line", "sub_channel"])["month_start"].idxmax()
        sf_latest = sf_rr.loc[idx].copy()

        # Map sub_channel to standard channel
        sf_latest["std_channel"] = sf_latest["sub_channel"].map(
            lambda x: RETURN_RATE_SUBCHANNEL_MAP.get(str(x).strip(), str(x).strip())
        )

        # Build SF lookup: (product_line_upper, std_channel) -> decimal value
        sf_dict = {}
        for _, r in sf_latest.iterrows():
            pl = str(r["product_line"]).upper()
            ch = r["std_channel"]
            pct_val = float(r["return_rate_12m_pct"] or 0)
            # Convert SF percentage to decimal: 2.02% -> 0.0202
            sf_dict[(pl, ch)] = round(pct_val / 100.0, 6)

        # Build comparison
        rows = []
        for _, row in cache_rr.iterrows():
            sku = row["sku"]
            channel = row["channel"]
            cache_val = float(row["return_rate"] or 0)

            # Get product_line for this SKU
            pl = sku_pl.get(sku, "")
            if not pl:
                continue

            # Find SF value
            sf_val = sf_dict.get((pl.upper(), channel))
            if sf_val is None:
                continue

            diff = round(cache_val - sf_val, 6)

            rows.append({
                "sku": sku,
                "channel": channel,
                "product_line": pl,
                "cache_value": cache_val,
                "sf_value": sf_val,
                "diff": diff,
            })

        result = pd.DataFrame(rows)
        if not result.empty:
            result["abs_diff"] = result["diff"].abs()
            result = result.sort_values("abs_diff", ascending=False).drop(columns=["abs_diff"])
        return result

    except Exception as e:
        st.error(f"Return rate comparison failed: {e}")
        return pd.DataFrame(columns=cols)


# ===========================================================================
# Helper: Build Outbound Shipping comparison
# ===========================================================================

# Only these 3 channels have Snowflake shipping data
SF_SHIPPING_CHANNELS = ["DTC US", "DTC CA", "TikTok Shop"]


def _has_sf_shipping_snapshot() -> bool:
    """Check if cache_outbound_shipping_sf (Snowflake raw snapshot) table exists and has data."""
    try:
        df = pd.read_sql("SELECT TOP 1 sku FROM cache_outbound_shipping_sf", engine)
        return not df.empty
    except Exception:
        return False


def build_shipping_comparison(skus: list) -> pd.DataFrame:
    """
    Compare cache_outbound_shipping (CSV user-defined SKUs) against
    cache_outbound_shipping_sf (Snowflake internal SKUs).

    **Iterate over cache (CSV) rows** for the 3 SF channels, then find the
    matching SF value via:
      1. Direct SKU match  (cache.sku == sf.sku)
      2. Reference SKU fallback  (cache_product_directory.reference_sku == sf.sku)
    If neither matches, the row is skipped (no SF data available).

    A `match_type` column indicates how the SF value was found:
      - "direct"    : cache SKU exists in SF
      - "via ref: X": matched through reference_sku X

    Returns DataFrame: sku, channel, product_line, cache_value, sf_value, diff, match_type
    """
    cols = ["sku", "channel", "product_line", "cache_value", "sf_value", "diff", "match_type"]
    try:
        # Load Snowflake raw snapshot
        has_sf = _has_sf_shipping_snapshot()
        if not has_sf:
            return pd.DataFrame(columns=cols)

        sf_ship = pd.read_sql(
            "SELECT sku, channel, outbound_shipping_cost FROM cache_outbound_shipping_sf", engine
        )
        sf_ship.columns = [c.lower() for c in sf_ship.columns]
        # Only SF channels & drop blank SKUs
        sf_ship = sf_ship[sf_ship["channel"].isin(SF_SHIPPING_CHANNELS)]
        sf_ship = sf_ship[sf_ship["sku"].str.strip().astype(bool)]

        # Build SF dict: (sf_sku, channel) -> cost
        sf_dict: dict[tuple, float] = {}
        for _, r in sf_ship.iterrows():
            sf_dict[(r["sku"], r["channel"])] = float(r["outbound_shipping_cost"] or 0)

        # Load cache (CSV) — only the 3 SF channels
        cache_ship = pd.read_sql(
            "SELECT sku, channel, outbound_shipping_cost FROM cache_outbound_shipping", engine
        )
        cache_ship.columns = [c.lower() for c in cache_ship.columns]
        cache_ship = cache_ship[cache_ship["channel"].isin(SF_SHIPPING_CHANNELS)]

        if skus:
            cache_ship = cache_ship[cache_ship["sku"].isin(skus)]

        if cache_ship.empty:
            return pd.DataFrame(columns=cols)

        # Load reference_sku mapping: cache_sku -> reference_sku
        try:
            prod_dir = pd.read_sql(
                "SELECT sku, reference_sku FROM cache_product_directory", engine
            )
            prod_dir.columns = [c.lower() for c in prod_dir.columns]
            ref_map: dict[str, str] = {}
            for _, r in prod_dir.iterrows():
                if r["reference_sku"] and pd.notna(r["reference_sku"]):
                    ref_map[r["sku"]] = str(r["reference_sku"]).strip()
        except Exception:
            ref_map = {}

        # Load product_line mapping
        sku_pl = _load_sku_product_line_map()

        # --- Iterate cache rows, find SF match ---
        rows = []
        for _, row in cache_ship.iterrows():
            sku = row["sku"]
            channel = row["channel"]
            cache_val = float(row["outbound_shipping_cost"] or 0)
            pl = sku_pl.get(sku, "")

            # 1. Direct match
            sf_val = sf_dict.get((sku, channel))
            if sf_val is not None:
                match_type = "direct"
            else:
                # 2. Reference SKU fallback
                ref_sku = ref_map.get(sku)
                if ref_sku:
                    sf_val = sf_dict.get((ref_sku, channel))
                    if sf_val is not None:
                        match_type = f"via ref: {ref_sku}"

            if sf_val is None:
                continue  # no SF data for this SKU+channel

            diff = round(cache_val - sf_val, 4)
            rows.append({
                "sku": sku,
                "channel": channel,
                "product_line": pl,
                "cache_value": cache_val,
                "sf_value": sf_val,
                "diff": diff,
                "match_type": match_type,
            })

        result = pd.DataFrame(rows)
        if not result.empty:
            result["abs_diff"] = result["diff"].abs()
            result = result.sort_values("abs_diff", ascending=False).drop(columns=["abs_diff"])
        return result

    except Exception as e:
        st.error(f"Shipping comparison failed: {e}")
        return pd.DataFrame(columns=cols)


# ===========================================================================
# Shared helper: Clear tab session state after batch resolve
# ===========================================================================
def _clear_tab_state(tab_key: str, field_name: str):
    """Clear session state for a tab so user re-validates fresh data."""
    # Map tab_key to comparison session key
    comp_key_map = {"rr": "rr_comparison_full", "ship": "ship_comparison_full"}
    comp_key = comp_key_map.get(tab_key)
    if comp_key and comp_key in st.session_state:
        del st.session_state[comp_key]
    # Clear select-all flag
    sa_key = f"{tab_key}_select_all_flag"
    if sa_key in st.session_state:
        del st.session_state[sa_key]
    # Also clear the cached sku_product_line_map so it refreshes
    _load_sku_product_line_map.clear()


# ===========================================================================
# Shared helper: Batch resolution UI block
# ===========================================================================
def _render_batch_ui(
    comparison_df: pd.DataFrame,
    field_name: str,
    tab_key: str,
    value_fmt: str = "pct",  # "pct" for return rate, "dollar" for shipping
):
    """
    Render the batch filter + select + apply UI for a comparison DataFrame.

    comparison_df must have: sku, channel, product_line, cache_value, sf_value, diff
    field_name: 'return_rate' or 'outbound_shipping'
    tab_key: unique prefix for widget keys
    value_fmt: 'pct' or 'dollar' for display formatting
    """
    if comparison_df.empty:
        return

    df = comparison_df.copy()

    # --- 1. Filters: Channel + Product Line ---
    st.markdown("#### Filter & Slice")
    col_f1, col_f2, col_f3 = st.columns(3)

    with col_f1:
        all_channels = sorted(df["channel"].dropna().unique().tolist())
        filter_channels = st.multiselect(
            "Filter by Channel",
            all_channels,
            default=[],
            key=f"{tab_key}_filter_ch",
        )

    with col_f2:
        all_pls = sorted([p for p in df["product_line"].dropna().unique().tolist() if p])
        filter_pls = st.multiselect(
            "Filter by Product Line",
            all_pls,
            default=[],
            key=f"{tab_key}_filter_pl",
        )

    with col_f3:
        show_mode = st.radio(
            "Show",
            ["Differences only", "All records"],
            horizontal=True,
            key=f"{tab_key}_show_mode",
        )

    # Apply filters
    filtered = df.copy()
    if filter_channels:
        filtered = filtered[filtered["channel"].isin(filter_channels)]
    if filter_pls:
        filtered = filtered[filtered["product_line"].isin(filter_pls)]

    if show_mode == "Differences only":
        threshold = 0.0001 if value_fmt == "pct" else 0.001
        filtered = filtered[filtered["diff"].abs() > threshold]

    if filtered.empty:
        st.success("No records match the current filters.")
        return

    # Summary stats
    diff_threshold = 0.0001 if value_fmt == "pct" else 0.001
    n_diffs = len(filtered[filtered["diff"].abs() > diff_threshold])
    n_total = len(filtered)
    if n_diffs > 0:
        st.warning(f"Showing **{n_total}** records | **{n_diffs}** with differences")
    else:
        st.success(f"Showing **{n_total}** records | All match!")

    # --- 2. Select All toggle + Data editor with checkbox ---
    # Use a session flag for "select all" so the default column value changes
    sa_key = f"{tab_key}_select_all_flag"
    if sa_key not in st.session_state:
        st.session_state[sa_key] = False

    col_sel1, col_sel2, _ = st.columns(3)
    with col_sel1:
        if st.button("Select All Visible", key=f"{tab_key}_select_all"):
            st.session_state[sa_key] = True
            st.rerun()
    with col_sel2:
        if st.button("Deselect All", key=f"{tab_key}_deselect_all"):
            st.session_state[sa_key] = False
            st.rerun()

    # Add a 'select' column for batch operations
    filtered = filtered.reset_index(drop=True)
    default_sel = st.session_state[sa_key]
    filtered.insert(0, "select", default_sel)

    # Format for display
    display_cols = {
        "select": st.column_config.CheckboxColumn("Select", default=False, width="small"),
        "sku": st.column_config.TextColumn("SKU", width="medium"),
        "channel": st.column_config.TextColumn("Channel", width="medium"),
        "product_line": st.column_config.TextColumn("Product Line", width="medium"),
    }

    if value_fmt == "pct":
        display_cols["cache_value"] = st.column_config.NumberColumn("Cache Value", format="%.4f")
        display_cols["sf_value"] = st.column_config.NumberColumn("SF Value", format="%.4f")
        display_cols["diff"] = st.column_config.NumberColumn("Diff", format="%.4f")
    else:
        display_cols["cache_value"] = st.column_config.NumberColumn("Cache Value ($)", format="$%.2f")
        display_cols["sf_value"] = st.column_config.NumberColumn("SF Value ($)", format="$%.2f")
        display_cols["diff"] = st.column_config.NumberColumn("Diff ($)", format="$%.2f")

    # Show match_type column if present (outbound shipping has it)
    has_match_type = "match_type" in filtered.columns
    if has_match_type:
        display_cols["match_type"] = st.column_config.TextColumn("Match Type", width="medium")

    disabled_cols = ["sku", "channel", "product_line", "cache_value", "sf_value", "diff"]
    if has_match_type:
        disabled_cols.append("match_type")

    edited_df = st.data_editor(
        filtered,
        column_config=display_cols,
        disabled=disabled_cols,
        use_container_width=True,
        hide_index=True,
        key=f"{tab_key}_editor",
        height=min(400, 40 + len(filtered) * 35),
    )

    # --- 3. Batch action buttons ---
    selected_rows = edited_df[edited_df["select"] == True]
    n_selected = len(selected_rows)

    st.markdown("---")
    st.markdown(f"#### Batch Actions ({n_selected} selected)")

    if n_selected == 0:
        st.info("Select rows using the checkboxes above, then use batch actions below.")
        return

    # Batch memo
    batch_memo = st.text_area(
        "Batch Memo (applies to all selected)",
        key=f"{tab_key}_batch_memo",
        placeholder="Reason for batch resolution...",
    )

    col_b1, col_b2 = st.columns(2)

    with col_b1:
        if st.button(
            f"Keep Cache for {n_selected} Selected",
            type="secondary",
            key=f"{tab_key}_batch_keep",
        ):
            from core.database import batch_resolve_validation

            rows_data = selected_rows[["sku", "channel", "cache_value", "sf_value"]].to_dict("records")
            with st.spinner(f"Applying Keep Cache to {n_selected} rows..."):
                try:
                    resolved = batch_resolve_validation(
                        rows=rows_data,
                        field_name=field_name,
                        resolution="keep_cache",
                        memo=batch_memo or f"Batch keep_cache ({n_selected} rows)",
                        user=st.session_state.get("current_user", "local_user"),
                    )
                    st.success(f"Batch resolved {resolved} rows -> Keep Cache")
                    # Clear comparison to force re-validate
                    _clear_tab_state(tab_key, field_name)
                    st.rerun()
                except Exception as e:
                    st.error(f"Batch resolve failed: {e}")

    with col_b2:
        if st.button(
            f"Accept SF for {n_selected} Selected",
            type="primary",
            key=f"{tab_key}_batch_accept",
        ):
            from core.database import batch_resolve_validation

            rows_data = selected_rows[["sku", "channel", "cache_value", "sf_value"]].to_dict("records")
            with st.spinner(f"Applying Accept SF to {n_selected} rows..."):
                try:
                    resolved = batch_resolve_validation(
                        rows=rows_data,
                        field_name=field_name,
                        resolution="accept_sf",
                        memo=batch_memo or f"Batch accept_sf ({n_selected} rows)",
                        user=st.session_state.get("current_user", "local_user"),
                    )
                    st.success(f"Batch resolved {resolved} rows -> Accept Snowflake")
                    # Clear comparison to force re-validate
                    _clear_tab_state(tab_key, field_name)
                    st.rerun()
                except Exception as e:
                    st.error(f"Batch resolve failed: {e}")

    # --- 4. Individual resolution (collapsible) ---
    with st.expander(f"Individual Resolution ({n_diffs} conflicts)", expanded=False):
        for idx, row in filtered.iterrows():
            if abs(row["diff"]) <= (0.0001 if value_fmt == "pct" else 0.001):
                continue  # skip matching rows

            if value_fmt == "pct":
                label = (
                    f"{row['sku']} | {row['channel']} | "
                    f"Cache: {row['cache_value']:.4f} vs SF: {row['sf_value']:.4f}"
                )
            else:
                label = (
                    f"{row['sku']} | {row['channel']} | "
                    f"Cache: ${row['cache_value']:.2f} vs SF: ${row['sf_value']:.2f}"
                )

            with st.expander(label):
                col1, col2, col3 = st.columns(3)
                with col1:
                    if value_fmt == "pct":
                        st.metric("Cache Value", f"{row['cache_value']:.4%}")
                    else:
                        st.metric("Cache Value", f"${row['cache_value']:.2f}")
                with col2:
                    if value_fmt == "pct":
                        st.metric("SF Value", f"{row['sf_value']:.4%}")
                    else:
                        st.metric("SF Value", f"${row['sf_value']:.2f}")
                with col3:
                    if value_fmt == "pct":
                        st.metric("Difference", f"{row['diff']:.4%}")
                    else:
                        st.metric("Difference", f"${row['diff']:.2f}")

                resolution = st.radio(
                    "Resolution",
                    ["Keep Cache", "Accept Snowflake", "Manual Override"],
                    key=f"{tab_key}_ind_res_{idx}",
                    horizontal=True,
                )

                manual_val = row["cache_value"]
                if resolution == "Manual Override":
                    fmt = "%.6f" if value_fmt == "pct" else "%.2f"
                    manual_val = st.number_input(
                        "Manual Value",
                        value=float(row["cache_value"]),
                        format=fmt,
                        key=f"{tab_key}_ind_manual_{idx}",
                    )

                memo = st.text_area("Memo", key=f"{tab_key}_ind_memo_{idx}", placeholder="Reason...")

                if st.button("Apply", key=f"{tab_key}_ind_apply_{idx}"):
                    from core.database import resolve_validation_conflict

                    if resolution == "Keep Cache":
                        final = row["cache_value"]
                        res_code = "keep_cache"
                    elif resolution == "Accept Snowflake":
                        final = row["sf_value"]
                        res_code = "accept_sf"
                    else:
                        final = manual_val
                        res_code = "manual"

                    try:
                        resolve_validation_conflict(
                            sku=row["sku"],
                            channel=row["channel"],
                            field_name=field_name,
                            cache_value=row["cache_value"],
                            sf_value=row["sf_value"],
                            resolution=res_code,
                            final_value=final,
                            memo=memo,
                            user=st.session_state.get("current_user", "local_user"),
                        )
                        if value_fmt == "pct":
                            st.success(f"Resolved: {row['sku']}/{row['channel']} -> {final:.4f} ({res_code})")
                        else:
                            st.success(f"Resolved: {row['sku']}/{row['channel']} -> ${final:.2f} ({res_code})")
                    except Exception as e:
                        st.error(f"Failed to resolve: {e}")


# ===========================================================================
# Tabs (SAC styled tabs)
# ===========================================================================
active_tab = styled_tabs(
    ["Return Rate", "Outbound Shipping", "History"],
    icons=["arrow-repeat", "truck", "clock-history"],
    key="dv_tabs",
)

# ===========================================================================
# Tab 1: Return Rate Validation
# ===========================================================================
if active_tab == "Return Rate":
    st.subheader("Return Rate: Cache vs Snowflake")
    st.caption(
        "Compares per-SKU return rates: **Cache** (`cache_return_rate_sku`, CSV old data, decimal e.g. 0.0064) "
        "vs **Snowflake** (rolling 12M `return_rate_12m_pct`, converted to decimal). "
        "SF data is matched by product_line + sub_channel mapping."
    )

    # SKU filter
    try:
        all_skus = pd.read_sql("SELECT DISTINCT sku FROM cache_return_rate_sku ORDER BY sku", engine)
        sku_list = all_skus["sku"].tolist()
    except Exception:
        sku_list = []

    selected_skus = st.multiselect("Filter by SKU (leave empty for all)", sku_list, key="val_rr_skus")

    if st.button("Validate Return Rates", type="primary", key="btn_validate_rr"):
        with st.spinner("Comparing return rates..."):
            comparison = build_return_rate_comparison(selected_skus)
        st.session_state["rr_comparison_full"] = comparison

    # Render batch UI if comparison exists
    if "rr_comparison_full" in st.session_state and not st.session_state["rr_comparison_full"].empty:
        _render_batch_ui(
            comparison_df=st.session_state["rr_comparison_full"],
            field_name="return_rate",
            tab_key="rr",
            value_fmt="pct",
        )
    elif "rr_comparison_full" in st.session_state:
        st.success("No differences found between cache and Snowflake return rates.")

# ===========================================================================
# Tab 2: Outbound Shipping Validation
# ===========================================================================
elif active_tab == "Outbound Shipping":
    st.subheader("Outbound Shipping: Cache vs Snowflake")
    st.caption(
        "Compares per-SKU shipping costs: **Cache** (CSV old data / user edits) vs "
        "**Snowflake** (latest from `SHIPPING_COST_EST_SUPPLEMENT`). "
        "Only validates **DTC US, DTC CA, TikTok Shop**. "
        "SF sync does NOT auto-overwrite cache - you decide here."
    )

    # Check if SF snapshot exists
    has_sf_snap = _has_sf_shipping_snapshot()
    if not has_sf_snap:
        st.warning(
            "No Snowflake shipping snapshot found. Run **Snowflake Sync** in DB Admin first. "
            "SF sync will pull latest data into a staging table for comparison."
        )

    # SKU filter - pull from cache (CSV) since that's the master list
    try:
        ship_skus = pd.read_sql(
            "SELECT DISTINCT sku FROM cache_outbound_shipping ORDER BY sku", engine
        )
        ship_sku_list = ship_skus["sku"].tolist()
    except Exception:
        ship_sku_list = []

    selected_ship_skus = st.multiselect("Filter by SKU", ship_sku_list, key="val_ship_skus")

    if st.button("Validate Shipping", type="primary", key="btn_validate_ship"):
        with st.spinner("Comparing shipping data..."):
            comparison = build_shipping_comparison(selected_ship_skus)
        st.session_state["ship_comparison_full"] = comparison

        # Show match stats
        if not comparison.empty and "match_type" in comparison.columns:
            n_direct = len(comparison[comparison["match_type"] == "direct"])
            n_ref = len(comparison[comparison["match_type"].str.startswith("via ref")])
            st.info(
                f"Matched **{len(comparison)}** cache SKU+channel rows to SF: "
                f"**{n_direct}** direct match, **{n_ref}** via reference SKU"
            )

    # Render batch UI if comparison exists
    if "ship_comparison_full" in st.session_state and not st.session_state["ship_comparison_full"].empty:
        _render_batch_ui(
            comparison_df=st.session_state["ship_comparison_full"],
            field_name="outbound_shipping",
            tab_key="ship",
            value_fmt="dollar",
        )
    elif "ship_comparison_full" in st.session_state:
        if has_sf_snap:
            st.success("No shipping data to compare (try different SKU filter).")
        else:
            st.info("Run Snowflake Sync first to pull shipping data.")

# ===========================================================================
# Tab 3: Validation History
# ===========================================================================
elif active_tab == "History":
    st.subheader("Validation Resolution History")
    st.caption("All past conflict resolutions with memos.")

    try:
        from core.database import get_validation_log

        # Filters
        col_h1, col_h2 = st.columns(2)
        with col_h1:
            hist_sku = st.text_input("Filter by SKU", key="hist_sku", placeholder="Leave empty for all")
        with col_h2:
            hist_limit = st.number_input("Max records", min_value=10, max_value=1000, value=100, key="hist_limit")

        log_df = get_validation_log(sku=hist_sku if hist_sku else None, limit=int(hist_limit))

        if log_df.empty:
            st.info("No validation history found.")
        else:
            st.metric("Records", len(log_df))
            st.dataframe(log_df, use_container_width=True, hide_index=True, height=500)

            # Download
            csv = log_df.to_csv(index=False).encode("utf-8")
            st.download_button("Download History CSV", csv, "validation_history.csv", "text/csv")

    except Exception as e:
        st.error(f"Failed to load validation history: {e}")
