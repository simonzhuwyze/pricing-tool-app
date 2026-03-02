"""
Shared UI helpers for the Pricing Tool app.
Provides consistent styling across all pages using:
  - streamlit-antd-components (sac): tabs, dividers, alerts, tags, segmented controls
  - streamlit-extras: metric card styling, colored headers
  - streamlit-aggrid: interactive data tables with sorting/filtering

Usage:
    from core.ui_helpers import styled_header, styled_divider, styled_metric_cards
    from core.ui_helpers import styled_tabs, styled_alert, render_aggrid
"""

import streamlit as st
import pandas as pd
import streamlit_antd_components as sac
from streamlit_extras.metric_cards import style_metric_cards


# ---------------------------------------------------------------------------
# Color palette (Wyze brand-inspired)
# ---------------------------------------------------------------------------
BRAND_COLOR = "#0D8A7B"  # teal green
BRAND_ACCENT = "#FF6B35"  # orange accent
METRIC_BG = "#F8F9FA"
METRIC_BORDER = "#E0E0E0"


# ---------------------------------------------------------------------------
# Page header with colored accent
# ---------------------------------------------------------------------------
def styled_header(title: str, description: str = "", color: str = "teal"):
    """
    Render a page title with optional description.

    Args:
        title: Page title text
        description: Optional subtitle/description
        color: (unused, kept for backward compat)
    """
    st.title(title)
    if description:
        st.caption(description)


# ---------------------------------------------------------------------------
# Styled divider with label
# ---------------------------------------------------------------------------
def styled_divider(label: str = "", icon: str = None, color: str = "gray"):
    """
    Section divider with optional subheader-sized label.

    Args:
        label: Optional section title (rendered as subheader if provided)
        icon: (unused, kept for backward compat)
        color: (unused, kept for backward compat)
    """
    st.divider()
    if label:
        st.subheader(label)


# ---------------------------------------------------------------------------
# Metric card styling (call once after all st.metric calls)
# ---------------------------------------------------------------------------
def styled_metric_cards(
    background_color: str = METRIC_BG,
    border_left_color: str = BRAND_COLOR,
    border_color: str = METRIC_BORDER,
    box_shadow: bool = True,
):
    """
    Apply consistent card styling to all st.metric widgets on the page.
    Call this ONCE after all your st.metric() calls.
    """
    style_metric_cards(
        background_color=background_color,
        border_left_color=border_left_color,
        border_color=border_color,
        box_shadow=box_shadow,
    )


# ---------------------------------------------------------------------------
# SAC tabs wrapper
# ---------------------------------------------------------------------------
def styled_tabs(labels: list, icons: list = None, **kwargs) -> str:
    """
    Render styled tabs using SAC.
    Returns the selected tab label as a string.

    Args:
        labels: List of tab label strings
        icons: Optional list of Bootstrap icon names
        **kwargs: Additional sac.tabs parameters

    Returns:
        Selected tab label string
    """
    items = []
    for i, label in enumerate(labels):
        icon = icons[i] if icons and i < len(icons) else None
        items.append(sac.TabsItem(label=label, icon=icon))

    return sac.tabs(
        items=items,
        color="teal",
        variant="outline",
        use_container_width=True,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# SAC segmented control wrapper (for view mode toggles)
# ---------------------------------------------------------------------------
def styled_segmented(labels: list, icons: list = None, index: int = 0, **kwargs) -> str:
    """
    Render a segmented control (pill toggle) using SAC.
    Great replacement for st.radio(horizontal=True).

    Args:
        labels: List of option labels
        icons: Optional list of Bootstrap icon names
        index: Default selected index
        **kwargs: Additional sac.segmented parameters

    Returns:
        Selected label string
    """
    items = []
    for i, label in enumerate(labels):
        icon = icons[i] if icons and i < len(icons) else None
        items.append(sac.SegmentedItem(label=label, icon=icon))

    return sac.segmented(
        items=items,
        index=index,
        color="teal",
        size="md",
        use_container_width=kwargs.pop("use_container_width", False),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# SAC alert wrapper
# ---------------------------------------------------------------------------
def styled_alert(message: str, description: str = None, type: str = "info", icon: bool = True, **kwargs):
    """
    Render a styled alert box. Replaces st.info/warning/error/success.

    Args:
        message: Main alert text
        description: Optional detail text
        type: 'info', 'success', 'warning', 'error'
        icon: Show icon
    """
    sac.alert(
        label=message,
        description=description,
        color=type,
        icon=icon,
        variant="quote-light",
        size="md",
        **kwargs,
    )


# ---------------------------------------------------------------------------
# SAC chip filter (for multi-select filters)
# ---------------------------------------------------------------------------
def styled_chip_filter(label: str, options: list, **kwargs) -> list:
    """
    Render a chip-based multi-select filter.
    Returns list of selected values.

    Args:
        label: Filter label
        options: List of option strings
        **kwargs: Additional sac.chip parameters

    Returns:
        List of selected option strings
    """
    items = [sac.ChipItem(label=opt) for opt in options]
    result = sac.chip(
        items=items,
        label=label,
        multiple=True,
        variant="outline",
        color="teal",
        radius="md",
        **kwargs,
    )
    if result is None:
        return []
    return result if isinstance(result, list) else [result]


# ---------------------------------------------------------------------------
# AgGrid interactive table
# ---------------------------------------------------------------------------
def render_aggrid(
    df: pd.DataFrame,
    height: int = 400,
    selection: bool = False,
    editable: bool = False,
    pagination: bool = True,
    page_size: int = 20,
    fit_columns: bool = True,
    theme: str = "streamlit",
    **kwargs,
):
    """
    Render an interactive AgGrid table with sorting, filtering, and optional selection.

    Args:
        df: DataFrame to display
        height: Table height in pixels
        selection: Enable row selection with checkboxes
        editable: Make cells editable
        pagination: Enable pagination
        page_size: Rows per page (when pagination=True)
        fit_columns: Auto-fit column widths
        theme: AgGrid theme ('streamlit', 'alpine', 'balham', 'material')
        **kwargs: Additional AgGrid parameters

    Returns:
        AgGrid response object (with .data and .selected_rows)
    """
    from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode

    gb = GridOptionsBuilder.from_dataframe(df)

    # Default column config
    gb.configure_default_column(
        filterable=True,
        sortable=True,
        resizable=True,
        editable=editable,
    )

    if selection:
        gb.configure_selection(
            selection_mode="multiple",
            use_checkbox=True,
            header_checkbox=True,
        )

    if pagination:
        gb.configure_pagination(paginationAutoPageSize=False, paginationPageSize=page_size)

    if fit_columns:
        gb.configure_grid_options(domLayout="normal")

    grid_options = gb.build()

    response = AgGrid(
        df,
        gridOptions=grid_options,
        height=height,
        theme=theme,
        update_mode=GridUpdateMode.MODEL_CHANGED if editable else GridUpdateMode.SELECTION_CHANGED,
        fit_columns_on_grid_load=fit_columns,
        allow_unsafe_jscode=False,
        **kwargs,
    )

    return response
