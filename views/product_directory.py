"""
Product Directory - Browse, search, and manage all products.
- View: Enriched with SKU mapping (product_group, product_category, product_line).
- Edit: Click "Edit" to modify a product's fields via confirmation dialog.
  Changing reference_sku warns that all assumptions will be re-cloned.
- Create: Add new SKU and clone assumptions from Reference SKU.
- Delete: Remove SKU and all associated assumptions (with confirmation).
"""

import streamlit as st
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.ui_helpers import styled_header, styled_divider, styled_metric_cards, render_aggrid, styled_alert
import streamlit_antd_components as sac

styled_header("Product Directory", "All products with SKU mapping enrichment. Select a row to use it in the Pricing Tool.")

# ---------------------------------------------------------------------------
# DB connection check (shared across all sections)
# ---------------------------------------------------------------------------
db_available = False
engine = None
try:
    from core.database import (
        get_connection, get_sqlalchemy_engine, sku_exists,
        clone_assumptions_from_ref_sku, update_product_directory,
        reclone_assumptions_from_ref_sku, delete_sku,
    )
    engine = get_sqlalchemy_engine()
    pd.read_sql("SELECT 1", engine)
    db_available = True
except Exception:
    pass

# ---------------------------------------------------------------------------
# Load & merge data (from Azure SQL)
# ---------------------------------------------------------------------------
def _load_products_from_db():
    """Load product directory from Azure SQL."""
    try:
        df = pd.read_sql_table("cache_product_directory", engine)
        col_map = {}
        for c in df.columns:
            cl = c.lower()
            if cl == "sku": col_map[c] = "SKU"
            elif cl == "product_name": col_map[c] = "Product Name"
            elif cl == "reference_sku": col_map[c] = "Reference SKU"
            elif cl == "default_msrp": col_map[c] = "Default MSRP"
            elif cl == "default_fob": col_map[c] = "Default FOB"
            elif cl == "default_tariff_rate": col_map[c] = "Default Tariff Rate"
        return df.rename(columns=col_map)
    except Exception:
        return pd.DataFrame()

def _load_sku_mapping_from_db():
    """Load SKU mapping from Azure SQL."""
    try:
        df = pd.read_sql_table("cache_sku_mapping", engine)
        col_map = {}
        for c in df.columns:
            cl = c.lower()
            if cl in ("item", "sku"): col_map[c] = "SKU"
            elif "product_group" in cl: col_map[c] = "Product_Group"
            elif "product_category" in cl: col_map[c] = "Product_Category"
            elif "product_line" in cl: col_map[c] = "Product_Line"
        return df.rename(columns=col_map)
    except Exception:
        return pd.DataFrame()

if not db_available:
    st.error("Database connection required. Go to Settings > DB Admin to check connection.")
    st.stop()

products = _load_products_from_db()
sku_map = _load_sku_mapping_from_db()

if products.empty:
    st.error("No products found in database. Run CSV Sync from DB Admin page first.")
    st.stop()

if not sku_map.empty and "SKU" in sku_map.columns:
    merged = products.merge(sku_map, on="SKU", how="left")
else:
    merged = products.copy()

# Build helper dicts from directory
prod_dict = {}
for _, row in products.iterrows():
    prod_dict[row["SKU"]] = {
        "product_name": row.get("Product Name", ""),
        "reference_sku": row.get("Reference SKU", ""),
        "default_msrp": float(row.get("Default MSRP", 0) or 0),
        "default_fob": float(row.get("Default FOB", 0) or 0),
        "default_tariff_rate": float(row.get("Default Tariff Rate", 0) or 0),
    }

# ---------------------------------------------------------------------------
# Search & display
# ---------------------------------------------------------------------------
search = st.text_input("Search by SKU or Product Name", placeholder="e.g. WYZECPAN or Doorbell")
if search:
    mask = (
        merged["SKU"].str.contains(search, case=False, na=False) |
        merged["Product Name"].str.contains(search, case=False, na=False)
    )
    filtered = merged[mask]
else:
    filtered = merged

render_aggrid(
    filtered,
    height=min(len(filtered) * 35 + 60, 600),
    selection=False,
    pagination=True,
    page_size=25,
)

# Stats
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Total Products", len(products))
with col2:
    has_ref = products["Reference SKU"].notna() & (products["Reference SKU"] != "")
    st.metric("With Reference SKU", has_ref.sum())
with col3:
    st.metric("Showing", len(filtered))
styled_metric_cards()

# Quick select for Pricing Tool
styled_divider(label="Quick Select", icon="cursor-fill")
st.caption("Select a product to jump directly to the Pricing Tool.")

quick_options = [""] + (filtered["SKU"] + " - " + filtered["Product Name"].fillna("")).tolist()
quick_select = st.selectbox("Select Product", quick_options, key="pd_quick_select")

if quick_select:
    sku = quick_select.split(" - ")[0].strip()
    st.session_state.selected_sku = sku
    st.session_state.resolved_assumptions = None
    st.session_state.user_inputs = {
        "msrp": 0.0, "fob": 0.0, "tariff_rate": 0.0,
        "promotion_mix": 0.0, "promo_percentage": 0.0,
    }
    st.page_link("views/pricing_tool_main.py", label=f"Go to Pricing Tool with {sku} ->")

# ===========================================================================
# Edit Existing Product (dialog)
# ===========================================================================
from core.auth import has_permission
_can_edit = has_permission("create_sku")

styled_divider(label="Edit Product", icon="pencil-square")

if not _can_edit:
    st.info("View-only mode. Contact an admin for edit/create permissions.")
elif not db_available:
    st.warning("Database connection required. Check Settings > DB Admin.")
else:
    existing_skus = sorted(products["SKU"].unique().tolist())
    edit_select = st.selectbox(
        "Select SKU to edit",
        [""] + existing_skus,
        key="pd_edit_select",
        format_func=lambda x: f"{x} - {prod_dict[x]['product_name']}" if x and x in prod_dict else x,
    )

    if edit_select and edit_select in prod_dict:
        cur = prod_dict[edit_select]

        with st.form(key="edit_product_form"):
            st.caption(f"Editing: **{edit_select}**")

            col_a, col_b = st.columns(2)
            with col_a:
                edit_name = st.text_input("Product Name", value=cur["product_name"], key="ed_name")
            with col_b:
                ref_options = ["(none)"] + existing_skus
                cur_ref = cur["reference_sku"] if cur["reference_sku"] and pd.notna(cur["reference_sku"]) else "(none)"
                cur_ref_idx = ref_options.index(cur_ref) if cur_ref in ref_options else 0
                edit_ref = st.selectbox("Reference SKU", ref_options, index=cur_ref_idx, key="ed_ref")

            col_c, col_d, col_e = st.columns(3)
            with col_c:
                edit_msrp = st.number_input("Default MSRP ($)", value=cur["default_msrp"], min_value=0.0, max_value=9999.0, step=1.0, key="ed_msrp")
            with col_d:
                edit_fob = st.number_input("Default FOB ($)", value=cur["default_fob"], min_value=0.0, max_value=9999.0, step=0.5, key="ed_fob")
            with col_e:
                edit_tariff = st.number_input("Default Tariff Rate (%)", value=cur["default_tariff_rate"] * 100.0, min_value=0.0, max_value=100.0, step=0.5, key="ed_tariff")

            new_ref_val = edit_ref if edit_ref != "(none)" else None
            old_ref_val = cur["reference_sku"] if cur["reference_sku"] and pd.notna(cur["reference_sku"]) else None

            # Detect reference SKU change
            ref_changed = (new_ref_val or "") != (old_ref_val or "")

            if ref_changed and new_ref_val:
                st.warning(
                    f"Reference SKU will change from **{old_ref_val or '(none)'}** to **{new_ref_val}**. "
                    f"This will **overwrite all 4 assumption tables** (PO Discount, Return Rate, "
                    f"Outbound Shipping, Product Costs) for **{edit_select}** with values from **{new_ref_val}**."
                )
                confirm_reclone = st.checkbox(
                    "I confirm: overwrite current assumptions with new reference SKU's values",
                    key="ed_confirm_reclone",
                )
            else:
                confirm_reclone = True  # no ref change, no confirmation needed

            submitted = st.form_submit_button("Save Changes", type="primary")

            if submitted:
                if not edit_name.strip():
                    st.error("Product Name cannot be empty.")
                elif ref_changed and new_ref_val and not confirm_reclone:
                    st.error("Please confirm the assumption overwrite checkbox above.")
                else:
                    try:
                        # 1. Update directory record
                        update_product_directory(
                            sku=edit_select,
                            product_name=edit_name.strip(),
                            reference_sku=new_ref_val,
                            default_msrp=edit_msrp,
                            default_fob=edit_fob,
                            default_tariff_rate=edit_tariff / 100.0,  # UI shows %, DB stores decimal
                            user=st.session_state.get("current_user", "local_user"),
                        )

                        # 2. If reference SKU changed, re-clone assumptions
                        if ref_changed and new_ref_val:
                            clone_result = reclone_assumptions_from_ref_sku(
                                sku=edit_select,
                                new_ref_sku=new_ref_val,
                                user=st.session_state.get("current_user", "local_user"),
                            )
                            st.success(
                                f"Updated **{edit_select}** and re-cloned assumptions from **{new_ref_val}**: "
                                + ", ".join(f"{k}: {v} rows" for k, v in clone_result.items())
                            )
                        else:
                            st.success(f"Updated **{edit_select}** successfully.")

                        # Clear caches
                        try:
                            from core.assumption_resolver import clear_cache
                            clear_cache()
                        except Exception:
                            pass
                        st.rerun()

                    except Exception as e:
                        st.error(f"Failed to save: {e}")

    # --- Delete SKU ---
    if edit_select and edit_select in prod_dict:
        with st.expander("Delete this SKU", expanded=False):
            st.error(
                f"This will permanently delete **{edit_select}** from the Product Directory "
                f"and remove all associated assumption data (PO Discount, Return Rate, "
                f"Outbound Shipping, Product Costs)."
            )
            confirm_delete = st.text_input(
                f'Type "{edit_select}" to confirm deletion',
                key="ed_confirm_delete",
            )
            if st.button("Delete SKU", type="primary", key="btn_delete_sku"):
                if confirm_delete.strip() == edit_select:
                    try:
                        delete_sku(
                            sku=edit_select,
                            user=st.session_state.get("current_user", "local_user"),
                        )
                        st.success(f"Deleted **{edit_select}** and all associated assumptions.")
                        try:
                            from core.assumption_resolver import clear_cache
                            clear_cache()
                        except Exception:
                            pass
                        st.rerun()
                    except Exception as e:
                        st.error(f"Delete failed: {e}")
                else:
                    st.error(f'Please type exactly "{edit_select}" to confirm.')

# ===========================================================================
# Create New SKU
# ===========================================================================
styled_divider(label="Create New SKU", icon="plus-circle-fill")

if not _can_edit:
    st.info("View-only mode. Contact an admin for edit/create permissions.")
elif not db_available:
    st.warning("Database connection required to create new SKUs. Check DB connection in Settings > DB Admin.")
else:
    with st.expander("Add a new product and clone assumptions from Reference SKU", expanded=False):
        existing_skus = sorted(products["SKU"].unique().tolist())
        ref_options = [""] + [
            f"{row['SKU']} - {row.get('Product Name', '')}"
            for _, row in products.iterrows()
        ]

        with st.form(key="create_sku_form"):
            col_a, col_b = st.columns(2)
            with col_a:
                new_sku = st.text_input("New SKU", placeholder="e.g. WYZECPAN-V3", key="new_sku_input")
            with col_b:
                new_name = st.text_input("Product Name", placeholder="e.g. Wyze Cam Pan v3", key="new_name_input")

            ref_select = st.selectbox(
                "Reference SKU (clone assumptions from)",
                ref_options,
                key="new_ref_sku_select",
                help="All assumptions (PO Discount, Return Rate, Outbound Shipping, Product Costs) will be cloned from this SKU.",
            )

            col_c, col_d, col_e = st.columns(3)
            with col_c:
                new_msrp = st.number_input("Default MSRP ($)", min_value=0.0, max_value=9999.0, value=0.0, step=1.0, key="new_msrp")
            with col_d:
                new_fob = st.number_input("Default FOB ($)", min_value=0.0, max_value=9999.0, value=0.0, step=0.5, key="new_fob")
            with col_e:
                new_tariff = st.number_input("Default Tariff Rate (%)", min_value=0.0, max_value=100.0, value=0.0, step=0.5, key="new_tariff")

            submitted = st.form_submit_button("Create SKU & Clone Assumptions", type="primary")

        if submitted:
            ref_sku_val = ref_select.split(" - ")[0].strip() if ref_select else ""
            if not new_sku.strip():
                st.error("SKU cannot be empty.")
            elif not new_name.strip():
                st.error("Product Name cannot be empty.")
            elif not ref_sku_val:
                st.error("Please select a Reference SKU.")
            elif sku_exists(new_sku.strip()):
                st.error(f"SKU '{new_sku.strip()}' already exists in the database.")
            else:
                try:
                    result = clone_assumptions_from_ref_sku(
                        new_sku=new_sku.strip(),
                        ref_sku=ref_sku_val,
                        product_name=new_name.strip(),
                        default_msrp=new_msrp,
                        default_fob=new_fob,
                        default_tariff_rate=new_tariff / 100.0,  # UI shows %, DB stores decimal
                        user=st.session_state.get("current_user", "local_user"),
                    )
                    try:
                        from core.assumption_resolver import clear_cache
                        clear_cache()
                    except Exception:
                        pass
                    # Signal Pricing Tool to refresh product cache on next load
                    st.session_state["_refresh_products"] = True
                    st.success(f"SKU **{new_sku.strip()}** created successfully! Refresh the page to see it in the table.")
                    st.json(result)
                except Exception as e:
                    st.error(f"Failed to create SKU: {e}")
