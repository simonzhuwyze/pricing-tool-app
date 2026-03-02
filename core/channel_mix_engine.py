"""
Channel Mix Engine
Provides "smart fill" functionality using historical channel mix data
from Snowflake (cache_channel_mix in Azure SQL).
"""

import pandas as pd
from typing import Dict, Optional

from core.data_loader import CHANNELS, SUBCHANNEL_MAP


def _get_channel_mix_data(engine=None) -> Optional[pd.DataFrame]:
    """Load channel mix data from Azure SQL cache or return None."""
    if engine is None:
        try:
            from core.database import get_sqlalchemy_engine
            engine = get_sqlalchemy_engine()
        except Exception:
            return None

    try:
        df = pd.read_sql_table("cache_channel_mix", engine)
        return df if df is not None and not df.empty else None
    except Exception:
        return None


def compute_smart_fill(
    product_line: str,
    months: int = 12,
    engine=None,
) -> Dict[str, float]:
    """
    Given a product_line, aggregate last N months of channel mix data,
    normalize to 100%, return dict {channel: pct}.

    Steps:
    1. Query cache_channel_mix WHERE product_line matches
    2. Filter to last N months by PERIODNAME or date column
    3. Sum QUANTITY per SUB_CHANNEL across all months
    4. Map sub-channel names to standard channel names
    5. Calculate percentage, normalize to sum=100
    """
    df = _get_channel_mix_data(engine)
    if df is None or df.empty:
        return {ch: 0.0 for ch in CHANNELS}

    # Normalize column names to lowercase
    df.columns = [c.lower() for c in df.columns]

    # Filter by product line
    pl_col = None
    for candidate in ["product_line", "productline"]:
        if candidate in df.columns:
            pl_col = candidate
            break

    if pl_col is None:
        return {ch: 0.0 for ch in CHANNELS}

    filtered = df[df[pl_col].str.upper() == product_line.upper()].copy()
    if filtered.empty:
        return {ch: 0.0 for ch in CHANNELS}

    # Find date column and filter to last N months
    date_col = None
    for candidate in ["periodname", "period_name", "month_start", "date"]:
        if candidate in filtered.columns:
            date_col = candidate
            break

    if date_col:
        filtered[date_col] = pd.to_datetime(filtered[date_col], errors="coerce")
        filtered = filtered.dropna(subset=[date_col])
        if not filtered.empty:
            max_date = filtered[date_col].max()
            cutoff = max_date - pd.DateOffset(months=months)
            filtered = filtered[filtered[date_col] > cutoff]

    if filtered.empty:
        return {ch: 0.0 for ch in CHANNELS}

    # Find quantity column
    qty_col = None
    for candidate in ["quantity", "qty", "revenue", "units"]:
        if candidate in filtered.columns:
            qty_col = candidate
            break

    if qty_col is None:
        # If no quantity column, count rows as proxy
        qty_col = "_count"
        filtered[qty_col] = 1

    # Find sub-channel column
    sub_ch_col = None
    for candidate in ["sub_channel", "subchannel", "channel"]:
        if candidate in filtered.columns:
            sub_ch_col = candidate
            break

    if sub_ch_col is None:
        return {ch: 0.0 for ch in CHANNELS}

    # Aggregate by sub-channel
    filtered[qty_col] = pd.to_numeric(filtered[qty_col], errors="coerce").fillna(0)
    agg = filtered.groupby(sub_ch_col)[qty_col].sum().reset_index()

    # Map to standard channel names
    result = {ch: 0.0 for ch in CHANNELS}
    total = agg[qty_col].sum()

    if total == 0:
        return result

    for _, row in agg.iterrows():
        sub_ch = str(row[sub_ch_col])
        mapped = SUBCHANNEL_MAP.get(sub_ch, sub_ch)
        if mapped in result:
            result[mapped] += float(row[qty_col])

    # Normalize to 100%
    result_total = sum(result.values())
    if result_total > 0:
        for ch in result:
            result[ch] = round(result[ch] / result_total * 100, 2)

    return result


def get_yearly_channel_mix(
    product_line: str,
    engine=None,
) -> pd.DataFrame:
    """
    Return yearly channel mix for display.
    Pivot: rows=year, columns=channel, values=mix%.
    """
    df = _get_channel_mix_data(engine)
    if df is None or df.empty:
        return pd.DataFrame()

    df.columns = [c.lower() for c in df.columns]

    # Find product line column
    pl_col = None
    for candidate in ["product_line", "productline"]:
        if candidate in df.columns:
            pl_col = candidate
            break

    if pl_col is None:
        return pd.DataFrame()

    filtered = df[df[pl_col].str.upper() == product_line.upper()].copy()
    if filtered.empty:
        return pd.DataFrame()

    # Find date column
    date_col = None
    for candidate in ["periodname", "period_name", "month_start", "date"]:
        if candidate in filtered.columns:
            date_col = candidate
            break

    if date_col is None:
        return pd.DataFrame()

    filtered[date_col] = pd.to_datetime(filtered[date_col], errors="coerce")
    filtered = filtered.dropna(subset=[date_col])
    filtered["Year"] = filtered[date_col].dt.year

    # Find quantity and sub-channel columns
    qty_col = None
    for candidate in ["quantity", "qty", "revenue", "units"]:
        if candidate in filtered.columns:
            qty_col = candidate
            break
    if qty_col is None:
        qty_col = "_count"
        filtered[qty_col] = 1

    sub_ch_col = None
    for candidate in ["sub_channel", "subchannel", "channel"]:
        if candidate in filtered.columns:
            sub_ch_col = candidate
            break
    if sub_ch_col is None:
        return pd.DataFrame()

    filtered[qty_col] = pd.to_numeric(filtered[qty_col], errors="coerce").fillna(0)

    # Map sub-channel names
    filtered["Mapped_Channel"] = filtered[sub_ch_col].map(
        lambda x: SUBCHANNEL_MAP.get(str(x), str(x))
    )

    # Aggregate by year and mapped channel
    agg = filtered.groupby(["Year", "Mapped_Channel"])[qty_col].sum().reset_index()

    # Pivot
    pivot = agg.pivot_table(
        index="Year",
        columns="Mapped_Channel",
        values=qty_col,
        fill_value=0,
    )

    # Normalize each row to 100%
    row_totals = pivot.sum(axis=1)
    for col in pivot.columns:
        pivot[col] = (pivot[col] / row_totals * 100).round(2)

    # Reorder columns to match standard channel order
    ordered = [c for c in CHANNELS if c in pivot.columns]
    other = [c for c in pivot.columns if c not in CHANNELS]
    pivot = pivot[ordered + other]

    return pivot.reset_index()
