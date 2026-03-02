"""
Quick script to run full Snowflake → Azure SQL sync.
Usage: python run_sync.py
Will open browser for SSO authentication.
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from core.snowflake_sync import sync_all

print("=" * 60)
print("Snowflake → Azure SQL Full Sync")
print("=" * 60)
print("\nConnecting to Snowflake (check your browser for SSO)...\n")

results = sync_all()

print("\n" + "=" * 60)
print("Sync Results:")
print("=" * 60)
for table, count in results.items():
    if isinstance(count, int):
        print(f"  ✅ {table}: {count:,} rows")
    else:
        print(f"  ❌ {table}: {count}")

print("\nDone!")
