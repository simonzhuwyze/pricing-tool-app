"""
Sensitivity Analysis - MSRP and FOB sweep analysis.
Uses resolved assumptions from session state.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.data_loader import CHANNELS
from core.cpam_engine import (
    UserInputs, calculate_channel_cpam, calculate_weighted_cpam,
)

from core.ui_helpers import styled_header
styled_header("Sensitivity Analysis", "MSRP and FOB sweep analysis with CPAM impact.")

selected_sku = st.session_state.get("selected_sku")
resolved = st.session_state.get("resolved_assumptions")

if not selected_sku or resolved is None:
    st.warning("Please select a product on the Pricing Tool page first.")
    st.page_link("views/pricing_tool_main.py", label="Go to Pricing Tool →")
    st.stop()

user_inputs_dict = st.session_state.get("user_inputs", {})
channel_mix_values = st.session_state.get("channel_mix", {})

base_msrp = user_inputs_dict.get("msrp", 0)
base_fob = user_inputs_dict.get("fob", 0)

st.caption(
    f"**{selected_sku}** - {resolved.product_info.product_name}  |  "
    f"Baseline MSRP: ${base_msrp:.2f}  |  FOB: ${base_fob:.2f}"
)


def compute_blended_cpam(msrp_val, fob_val):
    """Compute blended CPAM $ for given MSRP and FOB."""
    ui = UserInputs(
        msrp=msrp_val,
        fob=fob_val,
        tariff_rate=user_inputs_dict.get("tariff_rate", 0),
        promotion_mix=user_inputs_dict.get("promotion_mix", 0),
        promo_percentage=user_inputs_dict.get("promo_percentage", 0),
    )
    results = []
    for ch in CHANNELS:
        ca = resolved.channel_assumptions[ch]
        ca.channel_mix = channel_mix_values.get(ch, 0.0) / 100.0
        r = calculate_channel_cpam(ui, resolved.product_info, ca, resolved.static_assumptions)
        results.append(r)
    w = calculate_weighted_cpam(results)
    return w.cpam_dollar_blended if w else 0.0


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
from core.ui_helpers import styled_tabs
import streamlit_antd_components as sac

active_tab = styled_tabs(
    ["MSRP Sensitivity", "FOB Sensitivity"],
    icons=["currency-dollar", "box-seam"],
    key="sens_tabs",
)

if active_tab == "MSRP Sensitivity":
    col1, col2 = st.columns(2)
    with col1:
        msrp_step = st.number_input("Step ($)", value=5.0, step=1.0, key="msrp_step")
    with col2:
        msrp_range = st.slider("Range (±steps)", 1, 10, 5, key="msrp_range")

    if base_msrp > 0:
        sweep_values = [base_msrp + (i - msrp_range) * msrp_step for i in range(2 * msrp_range + 1)]
        cpam_values = [compute_blended_cpam(m, base_fob) for m in sweep_values]

        colors = []
        for m in sweep_values:
            if abs(m - base_msrp) < 0.01:
                colors.append("#DAA520")
            elif compute_blended_cpam(m, base_fob) >= 0:
                colors.append("#15CAB6")
            else:
                colors.append("#E74C3C")

        fig = go.Figure(go.Bar(
            x=[f"${v:.0f}" for v in sweep_values],
            y=cpam_values,
            marker_color=colors,
        ))
        fig.update_layout(
            title="Blended CPAM $ by MSRP",
            xaxis_title="MSRP", yaxis_title="CPAM $",
            height=400,
        )
        st.plotly_chart(fig, use_container_width=True)

        result_df = pd.DataFrame({
            "MSRP": [f"${v:.2f}" for v in sweep_values],
            "CPAM $": [f"${v:.2f}" for v in cpam_values],
        })
        st.dataframe(result_df, use_container_width=True, hide_index=True)
    else:
        st.warning("Set MSRP > 0 on the Pricing Tool page.")

elif active_tab == "FOB Sensitivity":
    col1, col2 = st.columns(2)
    with col1:
        fob_step = st.number_input("Step ($)", value=2.0, step=0.5, key="fob_step")
    with col2:
        fob_range = st.slider("Range (±steps)", 1, 10, 5, key="fob_range")

    if base_fob > 0:
        sweep_values = [base_fob + (i - fob_range) * fob_step for i in range(2 * fob_range + 1)]
        cpam_values = [compute_blended_cpam(base_msrp, f) for f in sweep_values]

        colors = []
        for i, f in enumerate(sweep_values):
            if abs(f - base_fob) < 0.01:
                colors.append("#DAA520")
            elif cpam_values[i] >= 0:
                colors.append("#15CAB6")
            else:
                colors.append("#E74C3C")

        fig = go.Figure(go.Bar(
            x=[f"${v:.0f}" for v in sweep_values],
            y=cpam_values,
            marker_color=colors,
        ))
        fig.update_layout(
            title="Blended CPAM $ by FOB",
            xaxis_title="FOB", yaxis_title="CPAM $",
            height=400,
        )
        st.plotly_chart(fig, use_container_width=True)

        result_df = pd.DataFrame({
            "FOB": [f"${v:.2f}" for v in sweep_values],
            "CPAM $": [f"${v:.2f}" for v in cpam_values],
        })
        st.dataframe(result_df, use_container_width=True, hide_index=True)
    else:
        st.warning("Set FOB > 0 on the Pricing Tool page.")
