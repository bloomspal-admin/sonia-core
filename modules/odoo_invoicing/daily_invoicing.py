"""
BloomsPal Daily Invoicing Module (v2)
=====================================
Main orchestrator that runs daily on working days to:
  0. Read unprocessed warehouse reports (cortes) from DynamoDB
  1. Download and parse Excel files from warehouse
  2. Create products in Odoo (MTO) if they don't exist
  3. Create one invoice per dropshipper with all their new cortes
  4. Include logistics costs (weight-based + address fee)

Data Flow (v2):
  1. Connect to tracking DB → get already-processed corte IDs
  2. Scan DynamoDB (carrier_reports + fedex_consolidations) → find unprocessed cortes
  3. Download Excel files → parse orders, boxes, products, tracking numbers
  4. Group cortes by tenant (dropshipper)
  5. For each dropshipper:
     a. Find/create partner in Odoo
     b. Find/create products in Odoo (with brand = dropshipper name)
     c. Calculate weight from box types
     d. Create consolidated invoice with product lines + logistics lines
     e. Log everything to tracking DB
"""
import logging
import sys
from datetime import date
from typing import List, Dict
from collections import defaultdict

from .config import (
    ODOO_URL, ODOO_DB, ODOO_USER, ODOO_API_KEY,
    AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION,
    DYNAMO_TABLE_CARRIER_REPORTS, DYNAMO_TABLE_FEDEX_CONSOLIDATIONS,
    SONIA_DB_URL, COST_PER_KG, ADDRESS_FEE,
)
from .db_tracking import TrackingDB
from .corte_reader import CorteReader, CorteData
from .odoo_client import OdooClient
from .box_weights import get_box_weight

# ─── Logging Setup ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("daily_invoicing")


def group_cortes_by_tenant(cortes: List[CorteData]) -> Dict[int, List[CorteData]]:
    """Group cortes by tenant (dropshipper ID)."""
    grouped = defaultdict(list)
    for corte in cortes:
        grouped[corte.tenant].append(corte)
    return dict(grouped)


def build_invoice_lines(
    cortes: List[CorteData],
    odoo: OdooClient,
    logistics_products: Dict[str, int],
    dropshipper_name: str,
    box_weights: dict,
) -> tuple:
    """
    Build Odoo invoice lines for a group of cortes from the same dropshipper.

    Returns:
        (invoice_lines, total_products, total_logistics, total_weight, total_boxes, total_orders)
    """
    invoice_lines = []
    total_products = 0.0
    total_weight = 0.0
    total_boxes_count = 0
    total_orders_set = set()

    # ─── Product Lines ─────────────────────────────────────────
    # Aggregate items by SKU across all cortes for this dropshipper
    sku_aggregated: Dict[str, dict] = {}

    for corte in cortes:
        for box in corte.boxes:
            total_boxes_count += 1
            if box.order_number:
                total_orders_set.add(box.order_number)

            # Calculate weight for this box
            # Prefer DynamoDB weight (from fedex_consolidations packages data)
            if box.weight and box.weight > 0:
                box_weight = box.weight
            elif box.box_type:
                box_weight = box_weights.get(box.box_type, get_box_weight(box.box_type))
            else:
                box_weight = get_box_weight("")  # Default fallback
            total_weight += box_weight

            for item in box.items:
                key = item.sku
                if not key:
                    continue

                if key not in sku_aggregated:
                    # Create/find product in Odoo
                    odoo_product_id = odoo.find_or_create_product(
                        sku=item.sku,
                        name=item.product_name or item.sku,
                        cost=item.price,
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

    # Add product lines to invoice
    for sku, data in sku_aggregated.items():
        line_total = data["quantity"] * data["price_unit"]
        total_products += line_total

        invoice_lines.append({
            "product_id": data["product_id"],
            "description": f"{data['name']} ({data['sku']})",
            "quantity": data["quantity"],
            "price_unit": data["price_unit"],
        })

    # ─── Logistics Lines ───────────────────────────────────────
    total_logistics = 0.0
    total_orders = len(total_orders_set)

    # Weight cost: total_weight_kg * COST_PER_KG
    weight_cost = total_weight * COST_PER_KG
    if weight_cost > 0:
        invoice_lines.append({
            "product_id": logistics_products.get("LOGISTICS-WEIGHT-KG"),
            "description": f"Costo logistico por peso: {total_weight:.3f} kg x ${COST_PER_KG}/kg",
            "quantity": round(total_weight, 3),
            "price_unit": COST_PER_KG,
        })
        total_logistics += weight_cost

    # Address fee: ADDRESS_FEE per order
    if total_orders > 0:
        address_total = total_orders * ADDRESS_FEE
        invoice_lines.append({
            "product_id": logistics_products.get("LOGISTICS-ADDRESS-FEE"),
            "description": f"Address fee: {total_orders} ordenes x ${ADDRESS_FEE}/orden",
            "quantity": total_orders,
            "price_unit": ADDRESS_FEE,
        })
        total_logistics += address_total

    return (
        invoice_lines,
        total_products,
        total_logistics,
        total_weight,
        total_boxes_count,
        total_orders,
    )


def run_daily_invoicing():
    """Main function - runs the daily invoicing process."""
    run_date = date.today()
    logger.info(f"{'='*60}")
    logger.info(f"Starting Daily Invoicing (v2 - Excel/DynamoDB) - {run_date}")
    logger.info(f"{'='*60}")

    # ─── Initialize Connections ────────────────────────────────
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

        logger.info(f"New cortes to process: {len(new_cortes)}")

        # Download and parse Excel files for each corte
        parsed_cortes = []
        for corte in new_cortes:
            try:
                parsed = reader.download_and_parse_excel(corte)
                if parsed.boxes:  # Only include cortes that had parseable data
                    parsed_cortes.append(parsed)
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

        # Ensure logistics products exist in Odoo
        logistics_products = odoo.find_or_create_logistics_product()
        logger.info(f"Logistics products ready: {logistics_products}")

        # Group cortes by tenant (dropshipper)
        cortes_by_tenant = group_cortes_by_tenant(parsed_cortes)
        logger.info(f"Dropshippers with new cortes: {len(cortes_by_tenant)}")

        # ─── Process Each Dropshipper ──────────────────────────
        for tenant_id, tenant_cortes in cortes_by_tenant.items():
            tenant_name = (
                tenant_cortes[0].tenant_name
                or f"Tenant-{tenant_id}"
            )
            logger.info(f"\n--- Processing: {tenant_name} (tenant={tenant_id}) ---")
            logger.info(f"    Cortes: {len(tenant_cortes)}")

            try:
                # Find/create partner in Odoo
                partner_id = odoo.find_or_create_partner(name=tenant_name)

                # Build invoice lines
                (
                    invoice_lines,
                    total_products,
                    total_logistics,
                    total_weight,
                    total_boxes,
                    total_orders,
                ) = build_invoice_lines(
                    tenant_cortes, odoo, logistics_products, tenant_name, box_weights
                )

                total_invoice = total_products + total_logistics

                if not invoice_lines:
                    logger.warning(f"    No invoice lines for {tenant_name}. Skipping.")
                    continue

                # Create the invoice
                reference = (
                    f"BloomsPal Cortes - {tenant_name} - "
                    f"{run_date.strftime('%Y-%m-%d')}"
                )
                corte_ids_str = ", ".join(c.corte_id for c in tenant_cortes)
                narration = (
                    f"Factura automatica generada por SonIA (v2)\n"
                    f"Fecha: {run_date}\n"
                    f"Dropshipper: {tenant_name}\n"
                    f"Cortes incluidos: {len(tenant_cortes)}\n"
                    f"Corte IDs: {corte_ids_str}\n"
                    f"Total cajas: {total_boxes}\n"
                    f"Total ordenes: {total_orders}\n"
                    f"Peso total: {total_weight:.3f} kg\n"
                    f"Total productos: ${total_products:.2f}\n"
                    f"Total logistica: ${total_logistics:.2f}\n"
                    f"Total factura: ${total_invoice:.2f}"
                )

                invoice = odoo.create_invoice(
                    partner_id=partner_id,
                    invoice_lines=invoice_lines,
                    reference=reference,
                    narration=narration,
                )

                # Log each corte as processed
                for corte in tenant_cortes:
                    tracking.mark_corte_processed(
                        corte_id=corte.corte_id,
                        table_source=corte.table_source,
                        tenant=tenant_id,
                        tenant_name=tenant_name,
                        excel_url=corte.excel_url,
                        report_date=corte.report_date,
                        total_boxes=corte.total_boxes,
                        total_orders=corte.total_orders,
                        total_items=corte.total_items,
                        total_weight_kg=total_weight / len(tenant_cortes),  # Split evenly
                        odoo_invoice_id=invoice["id"],
                        odoo_invoice_name=invoice["name"],
                        total_products=total_products / len(tenant_cortes),
                        total_logistics=total_logistics / len(tenant_cortes),
                        total_invoice=total_invoice / len(tenant_cortes),
                    )

                # Save run summary
                tracking.save_run_summary(
                    run_date=run_date,
                    tenant=tenant_id,
                    tenant_name=tenant_name,
                    cortes_processed=len(tenant_cortes),
                    odoo_invoice_id=invoice["id"],
                    odoo_invoice_name=invoice["name"],
                    orders_count=total_orders,
                    boxes_count=total_boxes,
                    total_weight_kg=total_weight,
                    total_products=total_products,
                    total_logistics=total_logistics,
                    total_invoice=total_invoice,
                )

                tracking.commit()

                logger.info(
                    f"    Invoice {invoice['name']} created! "
                    f"Total: ${total_invoice:.2f} "
                    f"({len(tenant_cortes)} cortes, {total_boxes} boxes, "
                    f"{total_orders} orders, {total_weight:.3f}kg)"
                )

            except Exception as e:
                logger.error(f"    Error processing {tenant_name}: {e}", exc_info=True)
                tracking.rollback()

                # Mark all cortes as errored
                for corte in tenant_cortes:
                    tracking.mark_corte_error(corte.corte_id, str(e))

                tracking.save_run_summary(
                    run_date=run_date,
                    tenant=tenant_id,
                    tenant_name=tenant_name,
                    cortes_processed=0,
                    odoo_invoice_id=0,
                    odoo_invoice_name="",
                    orders_count=0,
                    boxes_count=0,
                    total_weight_kg=0,
                    total_products=0,
                    total_logistics=0,
                    total_invoice=0,
                    status="error",
                    error_message=str(e),
                )
                tracking.commit()

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        raise

    finally:
        tracking.close()

    logger.info(f"\n{'='*60}")
    logger.info(f"Daily Invoicing Complete - {run_date}")
    logger.info(f"{'='*60}")


if __name__ == "__main__":
    run_daily_invoicing()
