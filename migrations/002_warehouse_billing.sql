-- Migration 002: warehouse_billing table
-- Stores billing data for each warehouse dispatch, per brand/dropshipper.
-- Used by Metabase dashboards for tenant billing visibility.

CREATE TABLE IF NOT EXISTS warehouse_billing (
    id              SERIAL PRIMARY KEY,
    dispatch_date   DATE NOT NULL,
    brand_code      VARCHAR(20) NOT NULL,
    brand_name      VARCHAR(100) NOT NULL,
    partner_id      INTEGER NOT NULL,
    tenant_id       INTEGER,
    odoo_order_id   INTEGER,
    odoo_order_name VARCHAR(50),
    unique_orders   INTEGER NOT NULL DEFAULT 0,
    total_boxes     INTEGER NOT NULL DEFAULT 0,
    total_weight_kg NUMERIC(10,4) NOT NULL DEFAULT 0,
    weight_cost     NUMERIC(10,2) NOT NULL DEFAULT 0,
    address_fee     NUMERIC(10,2) NOT NULL DEFAULT 0,
    total_cost      NUMERIC(10,2) NOT NULL DEFAULT 0,
    product_count   INTEGER NOT NULL DEFAULT 0,
    sku_summary     JSONB,
    tracking_numbers JSONB,
    source_filename VARCHAR(255),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_wb_brand ON warehouse_billing(brand_code);
CREATE INDEX IF NOT EXISTS idx_wb_date ON warehouse_billing(dispatch_date);
CREATE INDEX IF NOT EXISTS idx_wb_partner ON warehouse_billing(partner_id);
CREATE INDEX IF NOT EXISTS idx_wb_tenant ON warehouse_billing(tenant_id);
CREATE INDEX IF NOT EXISTS idx_wb_date_brand ON warehouse_billing(dispatch_date, brand_code);
