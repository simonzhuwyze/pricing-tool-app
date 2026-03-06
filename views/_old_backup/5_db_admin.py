"""
Database Admin Page - Connect to Azure SQL, sync data, manage overrides.
"""

import os
import streamlit as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

env_path = Path(__file__).parent.parent / ".env"


# ---------------------------------------------------------------------------
# Auto-load .env on every page render (so Streamlit process picks it up)
# ---------------------------------------------------------------------------
def _load_env_file():
    """Load .env file into os.environ if it exists."""
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                key, val = line.split("=", 1)
                val = val.strip().strip('"').strip("'")
                os.environ[key.strip()] = val

_load_env_file()


def _convert_adonet_to_pyodbc(conn_str: str) -> str:
    """
    Convert ADO.NET connection string from Azure Portal to pyodbc format.
    ADO.NET: Server=tcp:xxx,1433;Initial Catalog=db;Persist Security Info=False;User ID=user;Password=pwd;...
    pyodbc:  Driver={ODBC Driver 17 for SQL Server};Server=tcp:xxx,1433;Database=db;Uid=user;Pwd=pwd;Encrypt=yes;...
    """
    # Already has Driver= → probably already pyodbc format
    if "Driver=" in conn_str or "driver=" in conn_str:
        return conn_str

    # Parse ADO.NET key-value pairs
    parts = {}
    for segment in conn_str.split(";"):
        segment = segment.strip()
        if "=" in segment:
            k, v = segment.split("=", 1)
            parts[k.strip()] = v.strip()

    # Detect ODBC driver
    from core.database import _detect_odbc_driver
    driver = _detect_odbc_driver()

    # Map ADO.NET keys to pyodbc keys
    server = parts.get("Server", parts.get("server", ""))
    database = parts.get("Initial Catalog", parts.get("initial catalog",
               parts.get("Database", parts.get("database", ""))))
    user = parts.get("User ID", parts.get("user id",
           parts.get("Uid", parts.get("uid", ""))))
    password = parts.get("Password", parts.get("password",
               parts.get("Pwd", parts.get("pwd", ""))))

    # Remove {braces} from password if Azure Portal added them
    if password.startswith("{") and password.endswith("}"):
        password = password[1:-1]

    pyodbc_str = (
        f"Driver={{{driver}}};"
        f"Server={server};"
        f"Database={database};"
        f"Uid={user};"
        f"Pwd={password};"
        f"Encrypt=yes;"
        f"TrustServerCertificate=no;"
        f"Connection Timeout=30;"
    )
    return pyodbc_str


# ---------------------------------------------------------------------------
# Page UI
# ---------------------------------------------------------------------------
st.title("Database Admin")
st.caption("Azure SQL Database connection, data sync, and override management")

# --- Connection Configuration ---
st.subheader("1. Connection Configuration")

# Show current status
current_conn = os.environ.get("AZURE_SQL_CONN_STR", "")
if current_conn:
    # Mask password for display
    masked = current_conn
    if "Pwd=" in masked:
        start = masked.index("Pwd=") + 4
        end = masked.index(";", start) if ";" in masked[start:] else len(masked)
        masked = masked[:start] + "****" + masked[end:]
    st.success(f"Connection string loaded from .env")
    st.code(masked, language="text")
else:
    st.warning("No connection string found. Paste yours below.")

st.markdown("""
**Paste the ADO.NET connection string from Azure Portal** (it will be auto-converted to the correct format).

Azure Portal → SQL Database → Connection strings → ADO.NET
""")

# Manual connection string input
conn_input = st.text_input(
    "Connection String",
    type="password",
    help="Paste from Azure Portal. Both ADO.NET and ODBC formats are accepted.",
)

col_save, col_test = st.columns(2)

with col_save:
    if st.button("Save & Connect", disabled=not conn_input):
        # Auto-convert ADO.NET → pyodbc format
        converted = _convert_adonet_to_pyodbc(conn_input)

        # Save to .env file
        env_lines = []
        if env_path.exists():
            env_lines = env_path.read_text(encoding="utf-8").splitlines()
            env_lines = [l for l in env_lines if not l.startswith("AZURE_SQL_CONN_STR=")]
        env_lines.append(f'AZURE_SQL_CONN_STR="{converted}"')
        env_path.write_text("\n".join(env_lines) + "\n", encoding="utf-8")

        # Set in current process
        os.environ["AZURE_SQL_CONN_STR"] = converted

        if converted != conn_input:
            st.info("Auto-converted from ADO.NET to pyodbc format.")
        st.success("Connection string saved to .env")
        st.rerun()

with col_test:
    if st.button("Test Connection"):
        from core.database import test_connection
        with st.spinner("Connecting to Azure SQL..."):
            result = test_connection()
        if result["status"] == "connected":
            st.success(f"Connected to **{result['database']}**")
            st.caption(result["version"])
        else:
            st.error(f"Connection failed: {result['message']}")

            # Common error hints
            msg = result["message"].lower()
            if "login failed" in msg:
                st.warning("Check username/password in connection string")
            elif "cannot open server" in msg or "tcp provider" in msg or "timeout" in msg:
                st.warning(
                    "Check:\n"
                    "1. Server name is correct\n"
                    "2. Firewall rule allows your IP (Azure Portal → SQL Server → Networking)\n"
                    "3. Public network access is set to 'Selected networks' (not Disabled)"
                )
            elif "driver" in msg or "data source" in msg:
                st.warning(
                    "ODBC Driver issue. Make sure the Driver= field matches an installed driver.\n"
                    "Your installed drivers: " + str(__import__("pyodbc").drivers())
                )

# --- Schema Initialization ---
st.divider()
st.subheader("2. Initialize Database Schema")
st.markdown(
    "Creates all required tables (override tables + cache tables) if they don't exist."
)

if st.button("Initialize Schema"):
    from core.database import initialize_schema
    with st.spinner("Creating tables..."):
        try:
            initialize_schema()
            st.success("All tables created successfully!")
        except Exception as e:
            st.error(f"Schema initialization failed: {e}")

# --- CSV → Azure SQL Sync ---
st.divider()
st.subheader("3. Sync CSV Data to Cache")
st.markdown(
    "Upload current CSV data into Azure SQL cache tables. "
    "This populates the database with the same data you have locally."
)

if st.button("Sync CSV → Azure SQL"):
    from core.database import sync_csv_to_cache
    with st.spinner("Syncing data... This may take a minute."):
        try:
            result = sync_csv_to_cache()
            st.success("Data synced successfully!")
            for table, count in result.items():
                st.write(f"  - **{table}**: {count} rows")
        except Exception as e:
            st.error(f"Sync failed: {e}")

# --- Snowflake Sync ---
st.divider()
st.subheader("4. Snowflake Sync")
st.markdown(
    "Connect to Snowflake via SSO and pull live data into Azure SQL cache. "
    "This will open a browser window for Okta authentication."
)

# Snowflake config
sf_account = os.environ.get("SNOWFLAKE_ACCOUNT", "")
sf_user = os.environ.get("SNOWFLAKE_USER", "")

if sf_account:
    st.success(f"Snowflake config: **{sf_account}** / {sf_user}")
else:
    st.warning("Snowflake not configured yet.")
    with st.expander("Configure Snowflake"):
        sf_account_input = st.text_input("Snowflake Account", placeholder="e.g. xy12345.us-west-2")
        sf_user_input = st.text_input("Snowflake User", placeholder="e.g. simon.zhu@wyze.com")
        sf_warehouse_input = st.text_input("Warehouse", placeholder="e.g. COMPUTE_WH")
        sf_database_input = st.text_input("Database", placeholder="e.g. ANALYTICS")
        sf_schema_input = st.text_input("Schema", placeholder="e.g. PUBLIC")
        sf_role_input = st.text_input("Role (optional)", placeholder="e.g. ANALYST_ROLE")

        if st.button("Save Snowflake Config"):
            env_lines = []
            if env_path.exists():
                env_lines = env_path.read_text(encoding="utf-8").splitlines()
                env_lines = [l for l in env_lines if not l.startswith("SNOWFLAKE_")]
            env_lines.append(f'SNOWFLAKE_ACCOUNT="{sf_account_input}"')
            env_lines.append(f'SNOWFLAKE_USER="{sf_user_input}"')
            env_lines.append(f'SNOWFLAKE_WAREHOUSE="{sf_warehouse_input}"')
            env_lines.append(f'SNOWFLAKE_DATABASE="{sf_database_input}"')
            env_lines.append(f'SNOWFLAKE_SCHEMA="{sf_schema_input}"')
            if sf_role_input:
                env_lines.append(f'SNOWFLAKE_ROLE="{sf_role_input}"')
            env_lines.append('SNOWFLAKE_AUTHENTICATOR="externalbrowser"')
            env_path.write_text("\n".join(env_lines) + "\n", encoding="utf-8")

            # Set in env
            os.environ["SNOWFLAKE_ACCOUNT"] = sf_account_input
            os.environ["SNOWFLAKE_USER"] = sf_user_input
            os.environ["SNOWFLAKE_WAREHOUSE"] = sf_warehouse_input
            os.environ["SNOWFLAKE_DATABASE"] = sf_database_input
            os.environ["SNOWFLAKE_SCHEMA"] = sf_schema_input
            if sf_role_input:
                os.environ["SNOWFLAKE_ROLE"] = sf_role_input
            os.environ["SNOWFLAKE_AUTHENTICATOR"] = "externalbrowser"

            st.success("Snowflake config saved!")
            st.rerun()

col_sf_test, col_sf_sync = st.columns(2)
with col_sf_test:
    if st.button("Test Snowflake Connection"):
        from core.snowflake_sync import test_snowflake_connection
        with st.spinner("Connecting via SSO (check your browser)..."):
            result = test_snowflake_connection()
        if result["status"] == "connected":
            st.success(f"Connected! User: **{result['user']}** | DB: {result['database']}")
        else:
            st.error(f"Failed: {result['message']}")

with col_sf_sync:
    if st.button("Sync Snowflake → Azure SQL"):
        from core.snowflake_sync import sync_all
        with st.spinner("Syncing from Snowflake (check browser for SSO)..."):
            try:
                result = sync_all()
                st.success("Snowflake sync completed!")
                for table, count in result.items():
                    if isinstance(count, int):
                        st.write(f"  - **{table}**: {count} rows")
                    else:
                        st.warning(f"  - **{table}**: {count}")
            except Exception as e:
                st.error(f"Sync failed: {e}")

# Custom Snowflake query
with st.expander("Run Custom Snowflake Query"):
    custom_query = st.text_area("SQL Query", height=100, placeholder="SELECT * FROM your_table LIMIT 10")
    if st.button("Run Query", key="run_sf_query"):
        if custom_query:
            from core.snowflake_sync import run_custom_query
            with st.spinner("Running query..."):
                try:
                    result_df = run_custom_query(custom_query)
                    st.dataframe(result_df, use_container_width=True, hide_index=True)
                    st.caption(f"{len(result_df)} rows returned")
                except Exception as e:
                    st.error(f"Query failed: {e}")

# --- Database Status ---
st.divider()
st.subheader("5. Database Status")

if st.button("Refresh Status"):
    from core.database import get_table_counts, get_sync_status

    st.markdown("**Table Row Counts:**")
    counts = get_table_counts()
    if "error" in counts:
        st.error(counts["error"])
    else:
        import pandas as pd
        counts_df = pd.DataFrame([
            {"Table": k, "Rows": v} for k, v in counts.items()
        ])
        st.dataframe(counts_df, use_container_width=True, hide_index=True)

    st.markdown("**Sync Metadata:**")
    sync_df = get_sync_status()
    if not sync_df.empty:
        st.dataframe(sync_df, use_container_width=True, hide_index=True)
    else:
        st.info("No sync records yet.")

# --- Override Management ---
st.divider()
st.subheader("5. User Overrides")

tab_view, tab_add, tab_audit = st.tabs(["View Overrides", "Add Override", "Audit Log"])

with tab_view:
    if st.button("Load Overrides", key="load_overrides"):
        from core.database import get_overrides
        try:
            overrides_df = get_overrides()
            if overrides_df.empty:
                st.info("No overrides found. Data uses default values.")
            else:
                st.dataframe(overrides_df, use_container_width=True, hide_index=True)
                st.caption(f"{len(overrides_df)} override(s) total")
        except Exception as e:
            st.error(f"Failed to load overrides: {e}")

with tab_add:
    st.markdown("Manually add or update an override value:")
    col1, col2, col3 = st.columns(3)
    with col1:
        ov_sku = st.text_input("SKU", placeholder="e.g. WYZECPAN3")
    with col2:
        from core.data_loader import CHANNELS
        ov_channel = st.selectbox("Channel", ["(global)"] + CHANNELS, key="ov_channel")
    with col3:
        ov_field = st.selectbox("Field", [
            "po_discount_rate", "outbound_shipping",
            "return_rate", "inbound_freight", "warehouse_storage",
            "customer_service_rate", "cc_fee_rate", "marketing_rate",
            "msrp", "fob", "tariff_rate",
        ])
    ov_value = st.number_input("New Value", format="%.4f", key="ov_value")
    ov_notes = st.text_input("Notes (optional)", placeholder="Reason for change")

    if st.button("Save Override"):
        if ov_sku:
            from core.database import set_override
            try:
                set_override(ov_sku, ov_channel, ov_field, ov_value, notes=ov_notes or None)
                st.success(f"Override saved: {ov_sku} / {ov_channel} / {ov_field} = {ov_value}")
            except Exception as e:
                st.error(f"Failed to save: {e}")
        else:
            st.warning("Please enter a SKU.")

with tab_audit:
    if st.button("Load Audit Log", key="load_audit"):
        from core.database import get_override_audit_log
        try:
            audit_df = get_override_audit_log(limit=50)
            if audit_df.empty:
                st.info("No changes recorded yet.")
            else:
                st.dataframe(audit_df, use_container_width=True, hide_index=True)
        except Exception as e:
            st.error(f"Failed to load audit log: {e}")
