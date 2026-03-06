"""
Template Manager
Save/load pricing templates to Azure SQL.

A template captures a complete pricing session:
  - SKU + user inputs (MSRP, FOB, tariff, promo)
  - Channel mix percentages
  - Snapshot of all resolved channel assumptions at save time

Templates are identified by template_key = "{sku}::{template_name}::{user}".
"""

from dataclasses import dataclass
from typing import Optional, List, Dict
import pandas as pd
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class TemplateSummary:
    """Lightweight template metadata for list views."""
    id: int
    template_key: str
    sku: str
    template_name: str
    created_by: str
    created_at: datetime
    updated_at: datetime
    msrp: float
    fob: float
    tariff_rate: float
    promotion_mix: float
    promo_percentage: float
    notes: str
    is_active: bool


def _get_engine():
    """Get SQLAlchemy engine. Returns None if unavailable."""
    try:
        from core.database import get_sqlalchemy_engine
        return get_sqlalchemy_engine()
    except Exception:
        return None


def _get_conn():
    """Get pyodbc connection."""
    from core.database import get_connection
    return get_connection()


# ---------------------------------------------------------------------------
# List / Search
# ---------------------------------------------------------------------------
def list_templates(
    sku: Optional[str] = None,
    user: Optional[str] = None,
    active_only: bool = True,
) -> pd.DataFrame:
    """
    List templates. Returns DataFrame with summary columns.
    Filters by SKU and/or user if provided.
    """
    engine = _get_engine()
    if engine is None:
        return pd.DataFrame()

    query = "SELECT * FROM pricing_templates WHERE 1=1"
    params = {}
    if sku:
        query += " AND sku = :sku"
        params["sku"] = sku
    if user:
        query += " AND created_by = :user"
        params["user"] = user
    if active_only:
        query += " AND (is_active = 1 OR is_active IS NULL)"
    query += " ORDER BY updated_at DESC"

    try:
        return pd.read_sql(query, engine, params=params)
    except Exception as e:
        logger.warning(f"Failed to list templates: {e}")
        return pd.DataFrame()


def get_template_by_id(template_id: int) -> Optional[dict]:
    """Load a full template (inputs + channel mix + assumption snapshot)."""
    engine = _get_engine()
    if engine is None:
        return None

    try:
        # Master record
        master = pd.read_sql(
            f"SELECT * FROM pricing_templates WHERE id = {template_id}", engine
        )
        if master.empty:
            return None
        master_row = master.iloc[0].to_dict()

        # Channel mix
        mix_df = pd.read_sql(
            f"SELECT channel, mix_pct FROM pricing_template_channel_mix WHERE template_id = {template_id}",
            engine,
        )
        channel_mix = dict(zip(mix_df["channel"], mix_df["mix_pct"]))

        # Assumption snapshot
        assumptions_df = pd.read_sql(
            f"SELECT channel, field_name, field_value FROM pricing_template_assumptions WHERE template_id = {template_id}",
            engine,
        )

        return {
            "master": master_row,
            "channel_mix": channel_mix,
            "assumptions": assumptions_df,
        }
    except Exception as e:
        logger.warning(f"Failed to load template {template_id}: {e}")
        return None


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------
def save_template(
    sku: str,
    template_name: str,
    user: str,
    user_inputs: dict,
    channel_mix: Dict[str, float],
    resolved_assumptions=None,
    notes: str = "",
) -> int:
    """
    Save a pricing template. Returns the new template ID.

    If a template with the same sku + template_name + user already exists,
    it is updated (upsert behavior).
    """
    conn = _get_conn()
    cursor = conn.cursor()

    template_key = f"{sku}::{template_name}::{user}"
    msrp = user_inputs.get("msrp", 0)
    fob = user_inputs.get("fob", 0)
    tariff_rate = user_inputs.get("tariff_rate", 0)
    promotion_mix = user_inputs.get("promotion_mix", 0)
    promo_percentage = user_inputs.get("promo_percentage", 0)

    # Check if template already exists
    cursor.execute(
        "SELECT id FROM pricing_templates WHERE template_key = ?",
        (template_key,),
    )
    existing = cursor.fetchone()

    if existing:
        template_id = existing[0]
        # Update master record (also ensure is_active = 1 in case it was soft-deleted)
        cursor.execute("""
            UPDATE pricing_templates
            SET msrp = ?, fob = ?, tariff_rate = ?, promotion_mix = ?,
                promo_percentage = ?, notes = ?, is_active = 1, updated_at = GETUTCDATE()
            WHERE id = ?
        """, (msrp, fob, tariff_rate, promotion_mix, promo_percentage, notes, template_id))

        # Clear old channel mix and assumptions
        cursor.execute("DELETE FROM pricing_template_channel_mix WHERE template_id = ?", (template_id,))
        cursor.execute("DELETE FROM pricing_template_assumptions WHERE template_id = ?", (template_id,))
    else:
        # Insert new
        cursor.execute("""
            INSERT INTO pricing_templates
            (template_key, sku, template_name, created_by, msrp, fob, tariff_rate,
             promotion_mix, promo_percentage, notes, is_active)
            OUTPUT INSERTED.id
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """, (template_key, sku, template_name, user, msrp, fob, tariff_rate,
              promotion_mix, promo_percentage, notes))
        template_id = int(cursor.fetchone()[0])

    # Insert channel mix
    for ch, pct in channel_mix.items():
        if pct > 0:
            cursor.execute(
                "INSERT INTO pricing_template_channel_mix (template_id, channel, mix_pct) VALUES (?, ?, ?)",
                (template_id, ch, pct),
            )

    # Insert assumption snapshot
    if resolved_assumptions is not None:
        for entry in resolved_assumptions.resolution_log:
            cursor.execute("""
                INSERT INTO pricing_template_assumptions
                (template_id, channel, field_name, field_value)
                VALUES (?, ?, ?, ?)
            """, (template_id, entry.channel, entry.field_name, entry.value))

    conn.commit()
    conn.close()
    return template_id


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------
def delete_template(template_id: int):
    """Soft-delete a template (set is_active = 0)."""
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE pricing_templates SET is_active = 0, updated_at = GETUTCDATE() WHERE id = ?",
        (template_id,),
    )
    conn.commit()
    conn.close()


def hard_delete_template(template_id: int):
    """Permanently delete a template and all related records (cascade)."""
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM pricing_templates WHERE id = ?", (template_id,))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Load into session
# ---------------------------------------------------------------------------
def load_template_to_session(template_id: int) -> Optional[dict]:
    """
    Load a template and return a dict ready to apply to session state:
    {
        "sku": str,
        "user_inputs": {...},
        "channel_mix": {channel: pct, ...},
    }
    """
    data = get_template_by_id(template_id)
    if data is None:
        return None

    master = data["master"]

    return {
        "sku": master["sku"],
        "template_name": master.get("template_name", ""),
        "user_inputs": {
            "msrp": float(master.get("msrp", 0) or 0),
            "fob": float(master.get("fob", 0) or 0),
            "tariff_rate": float(master.get("tariff_rate", 0) or 0),
            "promotion_mix": float(master.get("promotion_mix", 0) or 0),
            "promo_percentage": float(master.get("promo_percentage", 0) or 0),
        },
        "channel_mix": data["channel_mix"],
        "notes": master.get("notes", ""),
    }
