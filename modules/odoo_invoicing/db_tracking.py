"""
Database tracking module (v2) - Tracks processed cortes (warehouse reports)
Manages tables in SonIA Core DB (Railway PostgreSQL) to avoid duplicate processing.
Changed from v1: Now tracks by corte_id instead of order_id.
"""
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
from typing import List, Set, Optional
import logging

logger = logging.getLogger(__name__)


class TrackingDB:
    """
    PostgreSQL-backed tracking for processed cortes.
    Tables:
      - invoicing_cortes: individual corte processing status
      - invoicing_runs: summary of each invoicing run
      - box_weights: box type -> weight mapping
    """

    def __init__(self, db_url: str):
        self.db_url = db_url
        self.conn = None

    def connect(self):
        """Connect to PostgreSQL."""
        self.conn = psycopg2.connect(self.db_url)
        logger.info("Connected to tracking DB")

    def initialize_tables(self):
        """Create tracking tables if they don't exist."""
        with self.conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS invoicing_cortes (
                    id SERIAL PRIMARY KEY,
                    corte_id TEXT UNIQUE NOT NULL,
                    tenant INT,
                    tenant_name TEXT,
                    status TEXT DEFAULT 'processed',
                    run_date TIMESTAMP,
                    total_boxes INT DEFAULT 0,
                    total_orders INT DEFAULT 0,
                    total_items INT DEFAULT 0,
                    total_weight_kg FLOAT DEFAULT 0,
                    odoo_invoice_id INT,
                    odoo_invoice_name TEXT,
                    total_products FLOAT DEFAULT 0,
                    total_logistics FLOAT DEFAULT 0,
                    total_invoice FLOAT DEFAULT 0,
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS invoicing_runs (
                    id SERIAL PRIMARY KEY,
                    run_date TIMESTAMP,
                    tenant INT,
                    tenant_name TEXT,
                    cortes_processed INT DEFAULT 0,
                    odoo_invoice_id INT,
                    odoo_invoice_name TEXT,
                    orders_count INT DEFAULT 0,
                    boxes_count INT DEFAULT 0,
                    weight_kg FLOAT DEFAULT 0,
                    total_products FLOAT DEFAULT 0,
                    total_logistics FLOAT DEFAULT 0,
                    total_amount FLOAT DEFAULT 0,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS box_weights (
                    id SERIAL PRIMARY KEY,
                    box_type TEXT UNIQUE NOT NULL,
                    weight_kg FLOAT NOT NULL,
                    tenant INT,
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)
        self.conn.commit()
        logger.info("Tracking tables initialized")

    def get_processed_corte_ids(self) -> Set[str]:
        """Get set of already-processed corte IDs."""
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT corte_id FROM invoicing_cortes WHERE status = 'processed'"
            )
            return {row[0] for row in cur.fetchall()}

    def get_box_weights(self) -> dict:
        """Get box type -> weight mapping from DB. Falls back to defaults."""
        weights = {}
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT box_type, weight_kg FROM box_weights")
                for row in cur.fetchall():
                    weights[row["box_type"]] = row["weight_kg"]
        except Exception as e:
            logger.warning(f"Could not load box weights from DB: {e}")
        return weights

    def mark_corte_processed(self, corte_id: str, **kwargs):
        """Mark a corte as successfully processed."""
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO invoicing_cortes (
                    corte_id, tenant, tenant_name, status, run_date,
                    total_boxes, total_orders, total_items, total_weight_kg,
                    odoo_invoice_id, odoo_invoice_name,
                    total_products, total_logistics, total_invoice
                ) VALUES (
                    %(corte_id)s, %(tenant)s, %(tenant_name)s, 'processed', %(run_date)s,
                    %(total_boxes)s, %(total_orders)s, %(total_items)s, %(total_weight_kg)s,
                    %(odoo_invoice_id)s, %(odoo_invoice_name)s,
                    %(total_products)s, %(total_logistics)s, %(total_invoice)s
                )
                ON CONFLICT (corte_id) DO UPDATE SET
                    status = 'processed',
                    run_date = EXCLUDED.run_date,
                    odoo_invoice_id = EXCLUDED.odoo_invoice_id,
                    odoo_invoice_name = EXCLUDED.odoo_invoice_name,
                    total_products = EXCLUDED.total_products,
                    total_logistics = EXCLUDED.total_logistics,
                    total_invoice = EXCLUDED.total_invoice
            """, {"corte_id": corte_id, **kwargs})

    def mark_corte_error(self, corte_id: str, error_message: str):
        """Mark a corte as failed with error message."""
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO invoicing_cortes (corte_id, status, error_message)
                VALUES (%s, 'error', %s)
                ON CONFLICT (corte_id) DO UPDATE SET
                    status = 'error',
                    error_message = EXCLUDED.error_message
            """, (corte_id, error_message))

    def save_run_summary(self, **kwargs):
        """Save a summary record for an invoicing run."""
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO invoicing_runs (
                    run_date, tenant, tenant_name, cortes_processed,
                    odoo_invoice_id, odoo_invoice_name,
                    orders_count, boxes_count, weight_kg,
                    total_products, total_logistics, total_amount
                ) VALUES (
                    %(run_date)s, %(tenant)s, %(tenant_name)s, %(cortes_processed)s,
                    %(odoo_invoice_id)s, %(odoo_invoice_name)s,
                    %(orders_count)s, %(boxes_count)s, %(weight_kg)s,
                    %(total_products)s, %(total_logistics)s, %(total_amount)s
                )
            """, kwargs)

    def commit(self):
        """Commit current transaction."""
        if self.conn:
            self.conn.commit()

    def close(self):
        """Close the database connection."""
        if self.conn:
            self.conn.close()
            logger.info("Tracking DB connection closed")
