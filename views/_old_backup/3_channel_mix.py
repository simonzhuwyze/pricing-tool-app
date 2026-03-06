"""
Channel Mix Page - Set estimated sales distribution by channel.
Includes historical channel mix chart for reference.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.data_loader import load_channel_mix_history, load_product_directory, CHANNELS

st.title("Channel Mix")
st.caption("Set the estimated sales distribution by channel. View historical data for reference.")

# --- Channel Mix Inputs ---
st.subheader("Channel Mix Input (%)")

# Initialize from session state
current_mix = st.session_state.get("channel_mix", {ch: 0.0 for ch in CHANNELS})

# Create input grid (4 columns)
cols = st.columns(4)
new_mix = {}
for i, ch in enumerate(CHANNELS):
    with cols[i % 4]:
        new_mix[ch] = st.number_input(
            ch,
            value=float(current_mix.get(ch, 0.0)),
            min_value=0.0,
            max_value=100.0,
            step=1.0,
            format="%.1f",
            key=f"mix_{ch}",
        )

st.session_state.channel_mix = new_mix

# Total Mix indicator
total_mix = sum(new_mix.values())
col_total, col_reset = st.columns([3, 1])
with col_total:
    if total_mix == 0:
        st.info(f"Total Mix: **{total_mix:.1f}%** — Enter channel mix values above")
    elif abs(total_mix - 100) < 0.1:
        st.success(f"Total Mix: **{total_mix:.1f}%**")
    elif total_mix < 100:
        st.warning(f"Total Mix: **{total_mix:.1f}%** (under 100%)")
    else:
        st.error(f"Total Mix: **{total_mix:.1f}%** (over 100%)")

with col_reset:
    if st.button("Reset All to 0"):
        for ch in CHANNELS:
            st.session_state[f"mix_{ch}"] = 0.0
        st.session_state.channel_mix = {ch: 0.0 for ch in CHANNELS}
        st.rerun()

# --- Active Channels Bar Chart ---
active = {ch: v for ch, v in new_mix.items() if v > 0}
if active:
    st.divider()
    st.subheader("Current Channel Mix")
    mix_df = pd.DataFrame({"Channel": active.keys(), "Mix %": active.values()})
    fig = px.bar(
        mix_df, x="Channel", y="Mix %",
        color_discrete_sequence=["#15CAB6"],
        text="Mix %",
    )
    fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
    fig.update_layout(
        yaxis_title="Mix %", xaxis_title="",
        height=350, margin=dict(t=20),
        plot_bgcolor="#F8FAFC",
    )
    st.plotly_chart(fig, use_container_width=True)

# --- Historical Channel Mix Reference ---
st.divider()
st.subheader("Historical Channel Mix (Reference)")
st.caption("Click a product line to view its actual sales distribution. Use this as a benchmark.")

history_df = load_channel_mix_history()

if not history_df.empty:
    # The file has columns: ITEM_SKU, PRODUCT_LINE, DTC US, DTC CA, TikTok Shop, ...
    # Show product line selector
    product_lines = history_df["PRODUCT_LINE"].dropna().unique().tolist() if "PRODUCT_LINE" in history_df.columns else []

    if product_lines:
        selected_line = st.selectbox("Product Line", product_lines)
        filtered = history_df[history_df["PRODUCT_LINE"] == selected_line]

        # Get channel columns (everything except ITEM_SKU and PRODUCT_LINE)
        channel_cols = [c for c in filtered.columns if c not in ["ITEM_SKU", "PRODUCT_LINE"]]

        if not filtered.empty:
            # Show average mix across all SKUs in this product line
            avg_mix = {}
            for col in channel_cols:
                vals = pd.to_numeric(
                    filtered[col].astype(str).str.replace("%", ""), errors="coerce"
                )
                avg_val = vals.mean()
                if pd.notna(avg_val) and avg_val > 0:
                    avg_mix[col] = avg_val

            if avg_mix:
                ref_df = pd.DataFrame({
                    "Channel": avg_mix.keys(),
                    "Historical Mix %": avg_mix.values(),
                })
                fig2 = px.bar(
                    ref_df, x="Channel", y="Historical Mix %",
                    color_discrete_sequence=["#007FFF"],
                    text="Historical Mix %",
                )
                fig2.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
                fig2.update_layout(
                    yaxis_title="Mix %", xaxis_title="",
                    height=350, margin=dict(t=20),
                    plot_bgcolor="#F8FAFC",
                )
                st.plotly_chart(fig2, use_container_width=True)

            # Also show the raw data table
            with st.expander("View Raw SKU Data"):
                st.dataframe(filtered, use_container_width=True, hide_index=True)
    else:
        st.info("No product line data available in the historical file.")
else:
    st.info("Historical channel mix data not found.")
