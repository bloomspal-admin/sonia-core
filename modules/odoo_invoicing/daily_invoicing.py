"""
BloomsPal Daily Sales Order Module (v3)
=======================================
Main orchestrator that runs daily on working days to:
  0. Read unprocessed warehouse reports (cortes) from DynamoDB
  1. Download and parse Excel files from warehouse
  2. Create products in Odoo (MTO) if they don't exist
  3. Create one Sale Order per dropshipper with all their new cortes
  4. Include logistics costs (weight-based + address fee)

Data Flow (v3 - Sale Orders):
  1. Connect to tracking DB -> get already-processed corte IDs
  2. Scan DynamoDB (carrier_reports + fedex_consolidations) -> find unprocessed cortes
  3. Download Excel files -> parse orders, boxes, products, tracking numbers
  4. Group cortes by tenant (dropshipper)
  5. For each dropshipper:
     a. Find/create partner in Odoo
     b. Find/create products in Odoo (with brand = dropshipper name)
     c. Calculate weight from box types / gross_weight
     d. Create consolidated Sale Order with product lines + logistics lines
     e. Log everything to tracking DB

Logistics pricing:
  - International Freight (Flete): $6.50 USD per kg
  - Address Fee: $8.00 USD per unique order/address
"""
import os
import sys
import logging
from datetime import datetime
from collections import defaultdict
from typing import List, Dict, Any

from .config import (
    ODOO_URL, ODOO_DB, ODOO_USER, ODOO_API_KEY,
    AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION,
    DYNAMO_TABLE_CARRIER_REPORTS, DYNAMO_TABLE_FEDEX_CONSOLIDATIONS,
    SONIA_DB_URL,
    COST_PER_KG, ADDRESS_FEE,
)
from .odoo_client import OdooClient
from .corte_reader import CorteReader, CorteData, ParsedCorte
from .box_weights import get_box_weight, BOX_WEIGHTS
from .db_tracking import TrackingDB

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("daily_invoicing")


def group_cortes_by_tenant(cortes: List[CorteData]) -> Dict[int, List[CorteData]]:
    """Group cortes by tenant (dropshipper ID)."""
    grouped = defaultdict(list)
    for corte in cortes:
        grouped[corte.tenant].append(corte)
    return dict(grouped)


def build_order_lines(
    cortes: List[CorteData],
    odoo: OdooClient,
    logistics_products: Dict[str, int],
    dropshipper_name: str,
    box_weights: dict,
) -> tuple:
    """
    Build Odoo sale order lines for a group of cortes from the same dropshipper.

    Returns:
        (order_lines, total_products, total_logistics, total_weight, total_boxes, total_orders)
    """
    order_lines = []
    total_products = 0.0
    total_weight = 0.0
    total_boxes_count = 0
    total_orders_set = set()

    # --- Product Lines ---
    sku_aggregated: Dict[str, Dict] = {}

    for corte in cortes:
        if not corte.parsed:
            continue

        parsed = corte.parsed

        # Count boxes and orders
        for box in parsed.boxes:
            total_boxes_count += 1
            if box.order_number:
                total_orders_set.add(box.order_number)

            # Weight: use box weight from data, or lookup from box_weights table
            if box.weight and box.weight > 0:
                total_weight += box.weight
            elif box.box_type:
                total_weight += get_box_weight(box.box_type, box_weights)

            # Items -> aggregate by SKU
            for item in box.items:
                key = f"{item.sku}:{dropshipper_name}"
                if key not in sku_aggregated:
                    odoo_product_id = odoo.find_or_create_product(
                        sku=item.sku,
                        name=item.product_name or item.sku,
                        cost=item.price,
                        weight=0.0,
                        brand=dropshipper_name,
                    )
                    sku_aggregated[key] = {
                        "product_id": odoo_product_id,
                        "sku": item.sku,
                        "name": item.product_name or item.sku,
                        "quantity": 0,
                        "price_unit": item.price,
                    }

                sku_aggregated[key]["quantity"] += item.quantity

    # Add product lines to order
    for sku, data in sku_aggregated.items():
        line_total = data["quantity"] * data["price_unit"]
        total_products += line_total

        order_lines.append({
            "product_id": data["product_id"],
            "description": f"{data['name']} ({data['sku']})",
            "quantity": data["quantity"],
            "price_unit": data["price_unit"],
        })

    # --- Logistics Lines ---
    total_logistics = 0.0
    total_orders = len(total_orders_set)

    # Weight cost: apply BloomsPal rounding rules then multiply
    # Rule: <1kg = 1kg, >=1kg round up to next 0.5kg
    billable_weight = total_weight
    weight_cost = billable_weight * COST_PER_KG
    if weight_cost > 0:
        order_lines.append({
            "product_id": logistics_products.get("freight"),
            "description": f"International Freight (Flete): {total_weight:.3f} kg (cobrado: {billable_weight:.1f} kg) x ${COST_PER_KG}/kg",
            "quantity": billable_weight,
            "price_unit": COST_PER_KG,
        })
        total_logistics += weight_cost

    # Address fee: ADDRESS_FEE ($8.00) per unique order/address
    if total_orders > 0:
        address_total = total_orders * ADDRESS_FEE
        order_lines.append({
            "product_id": logistics_products.get("address_fee"),
            "description": f"Address Fee: {total_orders} ordenes x ${ADDRESS_FEE}/orden",
            "quantity": total_orders,
            "price_unit": ADDRESS_FEE,
        })
        total_logistics += address_total

    return (
        order_lines,
        total_products,
        total_logistics,
        total_weight,
        total_boxes_count,
        total_orders,
    )


def run_daily_invoicing():
    """
    Main entry point: process unprocessed cortes and create Sale Orders in Odoo.
    Called by the scheduler (Mon-Fri 17:00 COT) or manually via API endpoint.
    """
    run_date = datetime.now()
    logger.info(f"=== Daily Sale Order Run: {run_date.isoformat()} ===")

    # Initialize clients
    tracking = TrackingDB(SONIA_DB_URL)
    reader = CorteReader(
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        aws_region=AWS_REGION,
        carrier_reports_table=DYNAMO_TABLE_CARRIER_REPORTS,
        fedex_consolidations_table=DYNAMO_TABLE_FEDEX_CONSOLIDATIONS,
    )
    odoo = OdooClient(ODOO_URL, ODOO_DB, ODOO_USER, ODOO_API_KEY)

    try:
        # Connect to tracking DB
        tracking.connect()
        tracking.initialize_tables()

        # Load box weights from DB
        box_weights = tracking.get_box_weights()
        logger.info(f"Box weights loaded: {box_weights}")

        # Get already processed corte IDs
        processed_ids = tracking.get_processed_corte_ids()
        logger.info(f"Already processed: {len(processed_ids)} cortes")

        # Fetch unprocessed cortes from DynamoDB
        new_cortes = reader.fetch_unprocessed_cortes(processed_ids)
        if not new_cortes:
            logger.info("No new cortes to process. Done!")
            return

        logger.info(f"Found {len(new_cortes)} new cortes to process")

        # Parse Excel files for each corte
        parsed_cortes = []
        for corte in new_cortes:
            try:
                parsed = reader.parse_warehouse_excel(corte)
                if parsed:
                    corte.parsed = parsed
                    parsed_cortes.append(corte)
                    logger.info(
                        f"  Parsed corte {corte.corte_id}: "
                        f"{parsed.total_boxes} boxes, {parsed.total_orders} orders, "
                        f"{parsed.total_items} items"
                    )
                else:
                    logger.warning(f"  Corte {corte.corte_id}: No parseable data in Excel")
            except Exception as e:
                logger.error(f"  Error parsing corte {corte.corte_id}: {e}")
                tracking.mark_corte_error(corte.corte_id, str(e))
                tracking.commit()

        if not parsed_cortes:
            logger.info("No parseable cortes found. Done!")
            return

        # Connect to Odoo
        odoo.connect()

        # Find existing logistics products in Odoo
        logistics_products = odoo.find_logistics_products()
        logger.info(f"Logistics products ready: {logistics_products}")

        # Group cortes by tenant (dropshipper)
        cortes_by_tenant = group_cortes_by_tenant(parsed_cortes)
        logger.info(f"Processing {len(cortes_by_tenant)} tenants")

        # Process each tenant
        for tenant_id, tenant_cortes in cortes_by_tenant.items():
            tenant_name = tenant_cortes[0].tenant_name or f"Tenant-{tenant_id}"
            logger.info(f"  Tenant: {tenant_name} ({len(tenant_cortes)} cortes)")

            try:
                # Find/create partner
                partner_id = odoo.find_or_create_partner(tenant_name)
                logger.info(f"    Partner ID: {partner_id}")

                # Build order lines
                (
                    order_lines, total_products, total_logistics,
                    total_weight, total_boxes, total_orders
                ) = build_order_lines(
                    tenant_cortes, odoo, logistics_products, tenant_name, box_weights
                )

                total_so = total_products + total_logistics

                if not order_lines:
                    logger.warning(f"    No order lines for {tenant_name}. Skipping.")
                    continue

                # Create the Sale Order
                reference = (
                    f"BloomsPal Cortes - {tenant_name} - "
                    f"{run_date.strftime('%Y-%m-%d')}"
                )
                corte_ids_str = ", ".join(c.corte_id for c in tenant_cortes)
                note = (
                    f"Orden de venta generada por SonIA (v3)\n"
                    f"Fecha: {run_date}\n"
                    f"Dropshipper: {tenant_name}\n"
                    f"Cortes incluidos: {len(tenant_cortes)}\n"
                    f"Corte IDs: {corte_ids_str}\n"
                    f"Total cajas: {total_boxes}\n"
                    f"Total ordenes: {total_orders}\n"
                    f"Peso total: {total_weight:.3f} kg\n"
                    f"Total productos: ${total_products:.2f}\n"
                    f"Total logistica: ${total_logistics:.2f}\n"
                    f"TOTAL: ${total_so:.2f}"
                )

                sale_order = odoo.create_sale_order(
                    partner_id=partner_id,
                    order_lines=order_lines,
                    reference=reference,
                    note=note,
                )

                logger.info(
                    f"    Created SO {sale_order['name']} "
                    f"(ID={sale_order['id']}) "
                    f"total=${sale_order['amount_total']:.2f}"
                )


                # Mark cortes as processed in tracking DB
                for corte in tenant_cortes:
                    tracking.mark_corte_processed(
                        corte_id=corte.corte_id,
                        tenant=tenant_id,
                        tenant_name=tenant_name,
                        run_date=run_date,
                        total_boxes=corte.total_boxes,
                        total_orders=corte.total_orders,
                        total_items=corte.total_items,
                        total_weight_kg=total_weight / len(tenant_cortes),
                        odoo_invoice_id=sale_order["id"],
                        odoo_invoice_name=sale_order["name"],
                        total_products=total_products / len(tenant_cortes),
                        total_logistics=total_logistics / len(tenant_cortes),
                        total_invoice=total_so / len(tenant_cortes),
                    )

                # Save run summary
                tracking.save_run_summary(
                    run_date=run_date,
                    tenant=tenant_id,
                    tenant_name=tenant_name,
                    cortes_processed=len(tenant_cortes),
                    odoo_invoice_id=sale_order["id"],
                    odoo_invoice_name=sale_order["name"],
                    orders_count=total_orders,
                    boxes_count=total_boxes,
                    weight_kg=total_weight,
                    total_products=total_products,
                    total_logistics=total_logistics,
                    total_amount=total_so,
                )
                tracking.commit()

                logger.info(
                    f"    Done: {tenant_name} - "
                    f"SO={sale_order['name']}, "
                    f"boxes={total_boxes}, orders={total_orders}, "
                    f"weight={total_weight:.1f}kg, "
                    f"total=${total_so:.2f}"
                )

            except Exception as e:
                logger.error(f"    Error processing {tenant_name}: {e}", exc_info=True)
                for corte in tenant_cortes:
                    tracking.mark_corte_error(corte.corte_id, str(e))
                tracking.commit()

        logger.info(f"=== Daily Sale Order Run completed at {datetime.now().isoformat()} ===")

    except Exception as e:
        logger.error(f"Fatal error in daily sale order run: {e}", exc_info=True)
        raise
    finally:
        tracking.close()


if __name__ == "__main__":
    run_daily_invoicing()
