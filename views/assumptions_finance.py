"""
Admin Assumptions Page - Editable internal assumption tables.
All data lives in Azure SQL. CSV files are only used for initial import
(via DB Admin > Sync CSV). After that, all changes are made here and
persist in the cloud.

Tables managed:
  1. Channel Records - Master channel list with type/order
  2. Channel Terms - Retail discount rates per channel
  3. Static Cost Assumptions - UID, Royalties, Cloud Cost, EOS
  4. Sales & Marketing Expenses - CC fees, CS, Marketing rates per channel
"""

import os
import streamlit as st
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Auto-load .env
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            key, val = line.split("=", 1)
            os.environ[key.strip()] = val.strip().strip('"').strip("'")


from core.ui_helpers import styled_header, styled_divider, styled_tabs
from core.auth import require_permission
import streamlit_antd_components as sac

styled_header("Finance Assumptions", "Internal assumptions managed by Finance. All data stored in Azure SQL.", color="indigo")
require_permission("edit_assumptions", "Finance Assumptions")

# Check DB connection (required)
try:
    from core.database import get_connection, get_sqlalchemy_engine
    engine = get_sqlalchemy_engine()
    # Quick connection check
    pd.read_sql("SELECT 1", engine)
    db_connected = True
except Exception as e:
    db_connected = False
    st.error(f"Database not connected: {e}")
    st.info("Go to **DB Admin** page to configure the connection and run **Initialize Schema** + **Sync CSV** first.")
    st.stop()


def load_table(table_name: str) -> pd.DataFrame:
    """Load a table from Azure SQL."""
    try:
        return pd.read_sql(f"SELECT * FROM {table_name} ORDER BY id", engine)
    except Exception as e:
        st.error(f"Failed to load {table_name}: {e}")
        return pd.DataFrame()


# =====================================================
# Tab Layout (SAC styled tabs)
# =====================================================
active_tab = styled_tabs(
    ["Channel Records", "Channel Terms", "Static Assumptions", "S&M Expenses"],
    icons=["list-ul", "receipt", "gear-wide-connected", "megaphone"],
    key="fin_tabs",
)


# =====================================================
# Tab 1: Channel Records
# =====================================================
if active_tab == "Channel Records":
    st.subheader("Channel Records")
    st.caption("Master list of sales channels. Add/remove channels here.")

    try:
        df_channels = load_table("admin_channel_records")
    except Exception:
        df_channels = pd.DataFrame(columns=["channel", "channel_type", "display_order"])

    display_cols = ["channel", "channel_type", "display_order"]
    for c in display_cols:
        if c not in df_channels.columns:
            df_channels[c] = "" if c != "display_order" else 0

    edited_channels = st.data_editor(
        df_channels[display_cols],
        use_container_width=True,
        num_rows="dynamic",
        column_config={
            "channel": st.column_config.TextColumn("Channel", help="Channel name", required=True),
            "channel_type": st.column_config.SelectboxColumn(
                "Channel Type",
                options=["DTC", "Retail", "Marketplace", "Other"],
                required=True,
            ),
            "display_order": st.column_config.NumberColumn("Order", min_value=1, max_value=99, step=1),
        },
        key="edit_channels",
    )

    if st.button("Save Channel Records", key="save_channels"):
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM admin_channel_records")
            for _, row in edited_channels.iterrows():
                if pd.notna(row["channel"]) and row["channel"]:
                    cursor.execute(
                        "INSERT INTO admin_channel_records (channel, channel_type, display_order, updated_by) VALUES (?, ?, ?, ?)",
                        (row["channel"], row["channel_type"], int(row.get("display_order", 0) or 0), "admin"),
                    )
            conn.commit()
            conn.close()
            st.success(f"Saved {len(edited_channels)} channel records!")
        except Exception as e:
            st.error(f"Save failed: {e}")


# =====================================================
# Tab 2: Channel Terms
# =====================================================
elif active_tab == "Channel Terms":
    st.subheader("Channel Terms")
    st.caption("Retail discount/allowance rates per channel. Values are decimals (0.04 = 4%).")

    try:
        df_terms = load_table("admin_channel_terms")
    except Exception:
        df_terms = pd.DataFrame()

    term_cols = [
        "channel", "chargeback", "early_pay_discount", "co_op",
        "freight_allowance", "labor", "damage_allowance",
        "end_cap", "discount_special", "trade_discount", "total_discount",
    ]
    for c in term_cols:
        if c not in df_terms.columns:
            df_terms[c] = 0.0

    edited_terms = st.data_editor(
        df_terms[term_cols],
        use_container_width=True,
        num_rows="dynamic",
        column_config={
            "channel": st.column_config.TextColumn("Channel", required=True),
            "chargeback": st.column_config.NumberColumn("Chargeback", format="%.4f", min_value=0.0, max_value=1.0),
            "early_pay_discount": st.column_config.NumberColumn("Early Pay Disc.", format="%.4f", min_value=0.0, max_value=1.0),
            "co_op": st.column_config.NumberColumn("Co-Op", format="%.4f", min_value=0.0, max_value=1.0),
            "freight_allowance": st.column_config.NumberColumn("Freight Allow.", format="%.4f", min_value=0.0, max_value=1.0),
            "labor": st.column_config.NumberColumn("Labor", format="%.4f", min_value=0.0, max_value=1.0),
            "damage_allowance": st.column_config.NumberColumn("Damage Allow.", format="%.4f", min_value=0.0, max_value=1.0),
            "end_cap": st.column_config.NumberColumn("End Cap", format="%.4f", min_value=0.0, max_value=1.0),
            "discount_special": st.column_config.NumberColumn("Disc. Special", format="%.4f", min_value=0.0, max_value=1.0),
            "trade_discount": st.column_config.NumberColumn("Trade Disc.", format="%.4f", min_value=0.0, max_value=1.0),
            "total_discount": st.column_config.NumberColumn("Total Discount", format="%.4f", min_value=0.0, max_value=1.0),
        },
        key="edit_terms",
    )

    col_auto, col_save = st.columns([3, 1])
    with col_auto:
        if st.checkbox("Auto-calculate Total Discount (sum of all components)"):
            component_cols = [
                "chargeback", "early_pay_discount", "co_op", "freight_allowance",
                "labor", "damage_allowance", "end_cap", "discount_special", "trade_discount",
            ]
            edited_terms["total_discount"] = edited_terms[component_cols].sum(axis=1)
            st.dataframe(
                edited_terms[["channel", "total_discount"]].rename(columns={"total_discount": "Calculated Total"}),
                hide_index=True,
            )

    with col_save:
        if st.button("Save Channel Terms", key="save_terms"):
            try:
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("DELETE FROM admin_channel_terms")
                for _, row in edited_terms.iterrows():
                    if pd.notna(row["channel"]) and row["channel"]:
                        cursor.execute("""
                            INSERT INTO admin_channel_terms
                            (channel, chargeback, early_pay_discount, co_op, freight_allowance,
                             labor, damage_allowance, end_cap, discount_special, trade_discount, total_discount, updated_by)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            row["channel"],
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
                            "admin",
                        ))
                conn.commit()
                conn.close()
                st.success(f"Saved {len(edited_terms)} channel terms!")
            except Exception as e:
                st.error(f"Save failed: {e}")


# =====================================================
# Tab 3: Static Cost Assumptions
# =====================================================
elif active_tab == "Static Assumptions":
    st.subheader("Static Cost Assumptions")
    st.caption("Global cost assumptions applied across all products/channels.")

    try:
        df_static = load_table("admin_static_assumptions")
    except Exception:
        df_static = pd.DataFrame(columns=["item", "unit", "value", "cost_type"])

    static_cols = ["item", "unit", "value", "cost_type"]
    for c in static_cols:
        if c not in df_static.columns:
            df_static[c] = ""

    edited_static = st.data_editor(
        df_static[static_cols],
        use_container_width=True,
        num_rows="dynamic",
        column_config={
            "item": st.column_config.TextColumn("Item", required=True),
            "unit": st.column_config.SelectboxColumn(
                "Unit",
                options=["dollar", "pct_net_rev", "pct_landed", "dollar_monthly"],
                required=True,
            ),
            "value": st.column_config.NumberColumn("Value", format="%.4f", min_value=0.0, max_value=999.0),
            "cost_type": st.column_config.SelectboxColumn(
                "Cost Type",
                options=["Other Cost", "S&M", "Revenue"],
            ),
        },
        key="edit_static",
    )

    # Show current values in a clear format
    with st.expander("Value Reference"):
        for _, row in edited_static.iterrows():
            unit = row.get("unit", "")
            val = row.get("value", 0)
            if pd.isna(val):
                val = 0
            if unit == "dollar":
                display = f"${val:.2f} per unit"
            elif unit == "pct_net_rev":
                display = f"{val:.1%} of Net Revenue"
            elif unit == "pct_landed":
                display = f"{val:.1%} of Landed Cost"
            elif unit == "dollar_monthly":
                display = f"${val:.2f} per month"
            else:
                display = f"{val}"
            st.write(f"**{row.get('item', '')}**: {display}")

    if st.button("Save Static Assumptions", key="save_static"):
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM admin_static_assumptions")
            for _, row in edited_static.iterrows():
                if pd.notna(row["item"]) and row["item"]:
                    cursor.execute("""
                        INSERT INTO admin_static_assumptions (item, unit, value, cost_type, updated_by)
                        VALUES (?, ?, ?, ?, ?)
                    """, (row["item"], row["unit"], float(row.get("value", 0) or 0), row.get("cost_type", ""), "admin"))
            conn.commit()
            conn.close()
            st.success(f"Saved {len(edited_static)} static assumptions!")
        except Exception as e:
            st.error(f"Save failed: {e}")


# =====================================================
# Tab 4: Sales & Marketing Expenses
# =====================================================
elif active_tab == "S&M Expenses":
    st.subheader("Sales & Marketing Expenses")
    st.caption("S&M expense rates per channel. Values are decimals (0.03 = 3%).")

    try:
        df_sm = load_table("admin_sm_expenses")
    except Exception:
        df_sm = pd.DataFrame(columns=["channel_name", "credit_card_platform_fee", "customer_service", "marketing"])

    sm_cols = ["channel_name", "credit_card_platform_fee", "customer_service", "marketing"]
    for c in sm_cols:
        if c not in df_sm.columns:
            df_sm[c] = 0.0

    edited_sm = st.data_editor(
        df_sm[sm_cols],
        use_container_width=True,
        num_rows="dynamic",
        column_config={
            "channel_name": st.column_config.TextColumn("Channel", required=True),
            "credit_card_platform_fee": st.column_config.NumberColumn(
                "CC & Platform Fee", format="%.4f", min_value=0.0, max_value=1.0,
                help="Credit Card & Platform Fee rate",
            ),
            "customer_service": st.column_config.NumberColumn(
                "Customer Service", format="%.4f", min_value=0.0, max_value=1.0,
            ),
            "marketing": st.column_config.NumberColumn(
                "Marketing", format="%.4f", min_value=0.0, max_value=1.0,
            ),
        },
        key="edit_sm",
    )

    # Show total S&M per channel
    edited_sm["total_sm"] = (
        edited_sm["credit_card_platform_fee"].fillna(0)
        + edited_sm["customer_service"].fillna(0)
        + edited_sm["marketing"].fillna(0)
    )
    st.caption("**Total S&M Rate per Channel:**")
    summary = edited_sm[["channel_name", "total_sm"]].copy()
    summary["total_sm"] = summary["total_sm"].apply(lambda x: f"{x:.1%}")
    st.dataframe(summary.rename(columns={"channel_name": "Channel", "total_sm": "Total S&M"}),
                 hide_index=True, use_container_width=False)

    if st.button("Save S&M Expenses", key="save_sm"):
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM admin_sm_expenses")
            for _, row in edited_sm.iterrows():
                if pd.notna(row["channel_name"]) and row["channel_name"]:
                    cursor.execute("""
                        INSERT INTO admin_sm_expenses (channel_name, credit_card_platform_fee, customer_service, marketing, updated_by)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        row["channel_name"],
                        float(row.get("credit_card_platform_fee", 0) or 0),
                        float(row.get("customer_service", 0) or 0),
                        float(row.get("marketing", 0) or 0),
                        "admin",
                    ))
            conn.commit()
            conn.close()
            st.success(f"Saved {len(edited_sm)} S&M expense records!")
        except Exception as e:
            st.error(f"Save failed: {e}")
