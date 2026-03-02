#!/bin/bash
# startup.sh - Alternative non-Docker deployment (e.g., Azure App Service with Python)
# Set this as the startup command in Azure App Service:
#   bash startup.sh

# Install ODBC driver if not present (Azure App Service Linux)
if ! dpkg -l | grep -q msodbcsql17; then
    curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" > /etc/apt/sources.list.d/mssql-release.list
    apt-get update
    ACCEPT_EULA=Y apt-get install -y msodbcsql17 unixodbc-dev
fi

# Install Python dependencies
pip install -r requirements.txt

# Start Streamlit
streamlit run app.py \
    --server.port=${PORT:-8501} \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --browser.gatherUsageStats=false
