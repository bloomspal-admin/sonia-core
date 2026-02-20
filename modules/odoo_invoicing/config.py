"""
Configuration for BloomsPal Daily Invoicing Module (v2)
Data source: DynamoDB warehouse Excel reports (cortes)
All sensitive values come from environment variables.
"""
import os

# ─── Odoo Connection ────────────────────────────────────────────
ODOO_URL = os.getenv("ODOO_URL", "https://bloomspal.odoo.com")
ODOO_DB = os.getenv("ODOO_DB", "bloomspal")
ODOO_USER = os.getenv("ODOO_USER", "danilo@bloomspal.com")
ODOO_API_KEY = os.getenv("ODOO_API_KEY", "")

# ─── AWS DynamoDB (READ-ONLY) ────────────────────────────────────
# Same credentials as SonIA Core (region us-east-2, NOT us-east-1)
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "")
AWS_REGION = os.getenv("AWS_REGION", "us-east-2")

# DynamoDB tables containing warehouse report URLs
DYNAMO_TABLE_CARRIER_REPORTS = os.getenv("DYNAMO_TABLE_CARRIER_REPORTS", "carrier_reports")
DYNAMO_TABLE_FEDEX_CONSOLIDATIONS = os.getenv("DYNAMO_TABLE_FEDEX_CONSOLIDATIONS", "fedex_consolidations")

# ─── SonIA Core DB (Railway) - Tracking ────────────────────────
SONIA_DB_URL = os.getenv("SONIA_DB_URL", os.getenv("DATABASE_URL", ""))

# ─── Logistics Costs ───────────────────────────────────────────
COST_PER_KG = float(os.getenv("COST_PER_KG", "6.5"))       # USD per kilogram
ADDRESS_FEE = float(os.getenv("ADDRESS_FEE", "8.0"))        # USD per order (address fee)

# ─── Schedule ──────────────────────────────────────────────────
CRON_SCHEDULE = os.getenv("CRON_SCHEDULE", "0 6 * * 1-5")   # Mon-Fri at 6:00 AM
