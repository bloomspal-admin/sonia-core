"""
BloomsPal Daily Invoicing Module (odoo_invoicing)
Reads warehouse reports from DynamoDB + S3 Excel files and creates Odoo invoices.
"""
from .daily_invoicing import run_daily_invoicing

__all__ = ["run_daily_invoicing"]
