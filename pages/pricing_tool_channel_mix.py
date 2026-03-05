"""
Channel Mix Page - Edit sales distribution by channel.
Smart Fill from Snowflake historical data, manual override, yearly view.
Product Line selector: quick pick (current / reference SKU) or manual
cascade (Product Group -> Product Category -> Product Line).
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.data_loader import CHANNELS
from core.ui_helpers import styled_header

styled_header("Channel Mix", "Edit sales distribution by channel. Smart Fill from Snowflake historical data.")

selected_sku = st.session_state.get("selected_sku")
resolved = st.session_state.get("resolved_assumptions")

if not selected_sku or resolved is None:
    st.warning("Please select a product on the Pricing Tool page first.")
    st.page_link("pages/pricing_tool_main.py", label="Go to Pricing Tool ->")
    st.stop()

st.caption(f"Product: **{selected_sku}** - {resolved.product_info.product_name}")
st.caption(
    f"Product Group: **{resolved.product_info.product_group or 'N/A'}** | "
    f"Product Category: **{resolved.product_info.product_category or 'N/A'}** | "
    f"Product Line: **{resolved.product_info.product_line or 'N/A'}**"
)

# ===========================================================================
# Section 1: Product Line Selector for Smart Fill
# ===========================================================================
st.subheader("1. Select Product Line for Channel Mix")
st.caption("Choose which Product Line's historical channel mix to use for Smart Fill.")

# --- Load SKU mapping for the cascading dropdown ---
def _normalize_hierarchy(df):
    """Normalize column names and build hierarchy from raw SKU mapping DataFrame."""
    if df is None or df.empty:
        return pd.DataFrame(columns=["Product_Group", "Product_Category", "Product_Line"])

    col_map = {}
    for c in df.columns:
        cl = c.lower().replace(" ", "_")
        if "product_group" in cl:
            col_map[c] = "Product_Group"
        elif "product_category" in cl or "product_family" in cl:
            col_map[c] = "Product_Category"
        elif "product_line" in cl:
            col_map[c] = "Product_Line"
    df = df.rename(columns=col_map)

    keep = [c for c in ["Product_Group", "Product_Category", "Product_Line"] if c in df.columns]
    if not keep:
        return pd.DataFrame(columns=["Product_Group", "Product_Category", "Product_Line"])

    hierarchy = df[keep].drop_duplicates().dropna(subset=["Product_Line"])
    if "Product_Category" not in hierarchy.columns:
        hierarchy["Product_Category"] = "Other"
    hierarchy["Product_Group"] = hierarchy["Product_Group"].fillna("Unknown")
    hierarchy["Product_Category"] = hierarchy["Product_Category"].fillna("Other")
    return hierarchy.sort_values(["Product_Group", "Product_Category", "Product_Line"]).reset_index(drop=True)


@st.cache_data(ttl=300)
def _load_hierarchy():
    """Load the full Product Group -> Category -> Line hierarchy."""
    # Try DB first
    try:
        from core.database import get_sqlalchemy_engine
        engine = get_sqlalchemy_engine()
        df = pd.read_sql_table("cache_sku_mapping", engine)
        cols_lower = [c.lower() for c in df.columns]
        if "product_category" not in cols_lower:
            df = None
        elif not df.empty:
            result = _normalize_hierarchy(df)
            if not result.empty:
                return result
    except Exception:
        pass

    # No CSV fallback — DB is the single source of truth
    return pd.DataFrame(columns=["Product_Group", "Product_Category", "Product_Line"])


hierarchy_df = _load_hierarchy()

# Refresh button if hierarchy is empty
if hierarchy_df.empty:
    st.warning("SKU mapping data not loaded. Try refreshing or run Snowflake Sync from DB Admin page.")
    if st.button("Refresh SKU Mapping"):
        _load_hierarchy.clear()
        st.rerun()

# --- Build quick-pick options ---
current_pl = resolved.product_info.product_line or ""
ref_sku = resolved.product_info.reference_sku or ""
ref_pl = ""

if ref_sku:
    try:
        from core.assumption_resolver import resolve_product_info
        ref_info = resolve_product_info(ref_sku)
        ref_pl = ref_info.product_line or ""
    except Exception:
        pass

# Build the quick-pick choices
quick_options = []
quick_option_map = {}  # label -> product_line

if current_pl:
    label_current = f"{current_pl}  (Current SKU: {selected_sku})"
    quick_options.append(label_current)
    quick_option_map[label_current] = current_pl

if ref_pl and ref_pl != current_pl:
    label_ref = f"{ref_pl}  (Reference SKU: {ref_sku})"
    quick_options.append(label_ref)
    quick_option_map[label_ref] = ref_pl

MANUAL_LABEL = "Manual Override (select from hierarchy)"
quick_options.append(MANUAL_LABEL)

# --- Quick pick dropdown ---
col_pick, col_info = st.columns([3, 1])
with col_pick:
    # Determine default index
    saved_pl = st.session_state.get("channel_mix_product_line", "")
    default_idx = 0
    if saved_pl:
        for i, opt in enumerate(quick_options):
            if quick_option_map.get(opt) == saved_pl:
                default_idx = i
                break

    selected_option = st.selectbox(
        "Product Line Source",
        quick_options,
        index=default_idx,
        key="pl_source_selector",
    )

with col_info:
    if selected_option != MANUAL_LABEL:
        chosen_pl = quick_option_map[selected_option]
        st.success(f"Using: **{chosen_pl}**")

# --- Manual override: cascading dropdowns ---
if selected_option == MANUAL_LABEL:
    st.markdown("---")
    st.caption("Drill down: Product Group -> Product Category -> Product Line")

    if hierarchy_df.empty:
        st.warning("No SKU mapping data available for manual selection. You can still enter channel mix manually below.")
        chosen_pl = ""
    else:
        col_g, col_c, col_l = st.columns(3)

        # Level 1: Product Group
        groups = sorted(hierarchy_df["Product_Group"].unique())
        with col_g:
            default_group_idx = 0
            if resolved.product_info.product_group and resolved.product_info.product_group in groups:
                default_group_idx = groups.index(resolved.product_info.product_group)
            sel_group = st.selectbox("Product Group", groups, index=default_group_idx, key="manual_pg")

        # Level 2: Product Category (filtered by group)
        cats_filtered = hierarchy_df[hierarchy_df["Product_Group"] == sel_group]["Product_Category"].unique()
        cats = sorted(cats_filtered)
        with col_c:
            default_cat_idx = 0
            if resolved.product_info.product_category and resolved.product_info.product_category in cats:
                default_cat_idx = cats.index(resolved.product_info.product_category)
            sel_cat = st.selectbox("Product Category", cats, index=default_cat_idx, key="manual_pc")

        # Level 3: Product Line (filtered by group + category)
        lines_filtered = hierarchy_df[
            (hierarchy_df["Product_Group"] == sel_group) &
            (hierarchy_df["Product_Category"] == sel_cat)
        ]["Product_Line"].unique()
        lines = sorted(lines_filtered)
        with col_l:
            default_line_idx = 0
            if saved_pl and saved_pl in lines:
                default_line_idx = lines.index(saved_pl)
            elif resolved.product_info.product_line and resolved.product_info.product_line in lines:
                default_line_idx = lines.index(resolved.product_info.product_line)
            sel_line = st.selectbox("Product Line", lines, index=default_line_idx, key="manual_pl")

        chosen_pl = sel_line
        st.info(f"Manual selection: **{sel_group}** > **{sel_cat}** > **{sel_line}**")
else:
    chosen_pl = quick_option_map.get(selected_option, current_pl)

# Save chosen product line to session state
st.session_state["channel_mix_product_line"] = chosen_pl

# ===========================================================================
# Section 2: Smart Fill
# ===========================================================================
st.divider()
st.subheader("2. Smart Fill (from Snowflake History)")

col_sf1, col_sf2 = st.columns([3, 1])
with col_sf1:
    months = st.slider("Historical months for smart fill", 3, 24, 12)
with col_sf2:
    if st.button("Smart Fill", type="primary"):
        if not chosen_pl:
            st.warning("No Product Line selected. Choose one above first.")
        else:
            try:
                from core.channel_mix_engine import compute_smart_fill

                with st.spinner(f"Computing channel mix from '{chosen_pl}'..."):
                    smart_mix = compute_smart_fill(chosen_pl, months=months)
                    if sum(smart_mix.values()) > 0:
                        st.session_state.channel_mix = smart_mix
                        # Also update widget keys so number_inputs reflect new values
                        for ch_key, val in smart_mix.items():
                            st.session_state[f"mix_{ch_key}"] = float(val)
                        st.success(f"Channel mix loaded from '{chosen_pl}' (last {months} months)!")
                        st.rerun()
                    else:
                        st.warning(f"No historical data for product line '{chosen_pl}'. Enter mix manually.")
            except Exception as e:
                st.error(f"Smart fill failed: {e}")
                st.info("Enter channel mix manually below.")

# ===========================================================================
# Section 3: Manual Input Grid
# ===========================================================================
st.subheader("3. Channel Mix Input")

mix_values = st.session_state.get("channel_mix", {ch: 0.0 for ch in CHANNELS})

# Initialize session state keys for each channel if not set
for ch in CHANNELS:
    if f"mix_{ch}" not in st.session_state:
        st.session_state[f"mix_{ch}"] = float(mix_values.get(ch, 0.0))

# Display in 4-column grid
cols = st.columns(4)
new_mix = {}
for i, ch in enumerate(CHANNELS):
    with cols[i % 4]:
        new_mix[ch] = st.number_input(
            ch,
            min_value=0.0,
            max_value=100.0,
            step=1.0,
            format="%.1f",
            key=f"mix_{ch}",
        )

st.session_state.channel_mix = new_mix

# Total validation
total = sum(new_mix.values())
if total == 0:
    st.info("No channel mix set. Enter percentages above (should sum to 100%).")
elif abs(total - 100) < 0.1:
    st.success(f"Total: {total:.1f}%")
elif total < 100:
    st.warning(f"Total: {total:.1f}% (need {100 - total:.1f}% more)")
else:
    st.error(f"Total: {total:.1f}% (exceeds 100% by {total - 100:.1f}%)")

# Reset button
if st.button("Reset All to 0%"):
    st.session_state.channel_mix = {ch: 0.0 for ch in CHANNELS}
    for ch in CHANNELS:
        st.session_state[f"mix_{ch}"] = 0.0
    st.rerun()

# ===========================================================================
# Section 4: Visualization
# ===========================================================================
active = {ch: v for ch, v in new_mix.items() if v > 0}
if active:
    st.subheader("Channel Distribution")
    fig = px.bar(
        x=list(active.keys()),
        y=list(active.values()),
        labels={"x": "Channel", "y": "Mix %"},
        color=list(active.values()),
        color_continuous_scale=["#15CAB6", "#323447"],
    )
    fig.update_layout(showlegend=False, height=350)
    st.plotly_chart(fig, use_container_width=True)

# ===========================================================================
# Section 5: Yearly Channel Mix (Historical)
# ===========================================================================
st.divider()
st.subheader("4. Yearly Channel Mix (Historical)")

if not chosen_pl:
    st.info("Select a Product Line above to view yearly channel mix history.")
else:
    try:
        from core.channel_mix_engine import get_yearly_channel_mix

        yearly = get_yearly_channel_mix(chosen_pl)
        if not yearly.empty:
            st.caption(f"Product Line: **{chosen_pl}**")
            st.dataframe(yearly, use_container_width=True, hide_index=True)
        else:
            st.info(f"No yearly channel mix data for '{chosen_pl}'. Sync Snowflake data from DB Admin page.")
    except Exception as e:
        st.info(f"Yearly data not available: {e}")
