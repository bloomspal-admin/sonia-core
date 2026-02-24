"""
Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
Ã¢ÂÂ                    SonIA Core Ã¢ÂÂ Daily Tracking Orchestrator                    Ã¢ÂÂ
Ã¢ÂÂ                              BloomsPal                                        Ã¢ÂÂ
Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ

Automated daily flow:
1. Read tracking numbers from DynamoDB (READ ONLY)
2. Check FedEx API for undelivered shipments
3. Store/update results in PostgreSQL
4. Detect anomalies and create proactive claims
5. Query Odoo for client contacts
6. Send reports via WhatsApp through SonIA Agent
7. Alert admin on inconsistencies

Schedule: Daily at 4:00 AM COT (UTC-5)
"""

import logging
import sys
import json
import os
import uuid
import hashlib
import tempfile
from datetime import datetime, timezone, timedelta, date
from contextlib import asynccontextmanager
from typing import Dict, List

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse, HTMLResponse
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

import psycopg2
from psycopg2.extras import Json

import config
from modules.dynamo_reader import DynamoReader
from modules.fedex_tracker import FedExTracker, get_sonia_status
from modules.db_manager import DBManager
from modules.odoo_client import OdooClient
from modules.whatsapp_sender import WhatsAppSender
from modules.report_generator import ReportGenerator
from modules.anomaly_detector import AnomalyDetector
from modules.warehouse.parser import WarehouseParser
from modules.warehouse.processor import WarehouseProcessor
from modules.warehouse.odoo_creator import OdooSaleOrderCreator

# ============================================================================
# LOGGING
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("sonia-core")

COT = timezone(timedelta(hours=-5))

# ============================================================================
# SCHEDULER
# ============================================================================

scheduler = BackgroundScheduler(timezone="America/Bogota")


# ============================================================================
# DAILY FLOW ORCHESTRATOR
# ============================================================================

def run_daily_flow(manual: bool = False):
    """
    Main daily orchestration flow.
    This is the core function that runs every day at 4 AM COT.
    """
    start_time = datetime.now(COT)
    trigger = "manual" if manual else "scheduled"
    logger.info(f"{'='*60}")
    logger.info(f"DAILY FLOW STARTED ({trigger}) at {start_time.strftime('%Y-%m-%d %H:%M:%S')} COT")
    logger.info(f"{'='*60}")

    # Initialize modules
    db = None
    fedex = None
    run_id = None
    unmapped_tenants = set()

    try:
        # Ã¢ÂÂÃ¢ÂÂ Initialize Database Ã¢ÂÂÃ¢ÂÂ
        db = DBManager(config.DATABASE_URL)
        db.connect()
        run_id = db.start_run(run_date=date.today())
        logger.info(f"Run ID: {run_id}")

        metrics = {
            "total_shipments_read": 0,
            "new_shipments": 0,
            "shipments_checked": 0,
            "shipments_updated": 0,
            "shipments_delivered": 0,
            "claims_created": 0,
            "reports_generated": 0,
            "reports_sent": 0,
            "alerts_sent": 0,
        }
        errors = []

        # Ã¢ÂÂÃ¢ÂÂ STEP 1: Read from DynamoDB Ã¢ÂÂÃ¢ÂÂ
        logger.info("STEP 1: Reading from DynamoDB...")
        try:
            dynamo = DynamoReader(
                aws_access_key=config.AWS_ACCESS_KEY_ID,
                aws_secret_key=config.AWS_SECRET_ACCESS_KEY,
                region=config.AWS_REGION,
                table_name=config.DYNAMO_TABLE_RESERVES,
            )
            reserves = dynamo.scan_all_reserves()
            tracking_list = dynamo.extract_all_tracking_numbers(reserves)
            metrics["total_shipments_read"] = len(tracking_list)
            logger.info(f"Read {len(tracking_list)} tracking numbers from {len(reserves)} reserves")
        except Exception as e:
            logger.error(f"STEP 1 FAILED: {e}")
            errors.append({"step": "dynamo_read", "error": str(e)})
            if db and run_id:
                db.complete_run(run_id, "failed", metrics, errors)
            _send_failure_alert(f"Error leyendo DynamoDB: {e}")
            return

        # Ã¢ÂÂÃ¢ÂÂ STEP 2: Sync tracking numbers to PostgreSQL Ã¢ÂÂÃ¢ÂÂ
        logger.info("STEP 2: Syncing to PostgreSQL...")
        tenant_mapping = db.get_tenant_mapping()
        new_count = 0

        for item in tracking_list:
            tenant_id = item.get("tenant")

            # Get client info from tenant mapping
            if tenant_id not in tenant_mapping:
                unmapped_tenants.add(tenant_id)
                logger.warning(f"Tenant {tenant_id} not found in mapping, using fallback")
                client_info = {
                    "id": None,
                    "name": f"Unmapped-Tenant-{tenant_id}",
                    "odoo_company_id": None,
                }
            else:
                client_info = tenant_mapping[tenant_id]

            shipment_data = {
                "tracking_number": item["tracking_number"],
                "client_id": client_info.get("client_id"),
                "client_name_raw": client_info.get("client_name", f"Tenant-{tenant_id}"),
                "dynamo_data": json.dumps({
                    "reserve_id": item.get("reserve_id"),
                    "order_id": item.get("order_id"),
                    "package_id": item.get("package_id"),
                    "dynamo_status": item.get("dynamo_status"),
                    "tenant": tenant_id,
                }),
            }

            was_new = db.upsert_shipment(shipment_data)
            if was_new:
                new_count += 1

        metrics["new_shipments"] = new_count
        logger.info(f"Synced {len(tracking_list)} shipments ({new_count} new)")

        # Alert admin about unmapped tenants
        if unmapped_tenants:
            unmapped_list = ", ".join(str(t) for t in sorted(unmapped_tenants))
            alert_msg = f"Ã¢ÂÂ Ã¯Â¸Â *Tenants sin mapeo detectados*\n\nIDs: {unmapped_list}\n\nPor favor actualizar la tabla tenant_mapping."
            if config.ADMIN_WHATSAPP and config.SONIA_AGENT_URL:
                try:
                    whatsapp = WhatsAppSender(
                        agent_url=config.SONIA_AGENT_URL,
                        api_key=config.SONIA_AGENT_API_KEY,
                    )
                    whatsapp.send_alert_sync(config.ADMIN_WHATSAPP, alert_msg)
                    metrics["alerts_sent"] += 1
                except Exception as e:
                    logger.error(f"Failed to send unmapped tenants alert: {e}")

        # Ã¢ÂÂÃ¢ÂÂ STEP 3: Query FedEx for undelivered shipments Ã¢ÂÂÃ¢ÂÂ
        logger.info("STEP 3: Querying FedEx API...")
        undelivered = db.get_undelivered_shipments()
        logger.info(f"Found {len(undelivered)} undelivered shipments to check")

        if undelivered:
            try:
                fedex = FedExTracker(
                    client_id=config.FEDEX_API_KEY,
                    client_secret=config.FEDEX_SECRET_KEY,
                    account_number=config.FEDEX_ACCOUNT,
                    sandbox=False,
                )

                if not fedex.authenticate():
                    raise RuntimeError("FedEx authentication failed")

                # Process in batches
                batch_size = config.FEDEX_BATCH_SIZE
                updated_count = 0
                delivered_count = 0

                for i in range(0, len(undelivered), batch_size):
                    batch = undelivered[i:i + batch_size]
                    tracking_numbers = [s["tracking_number"] for s in batch]

                    results = fedex.track_batch(tracking_numbers)

                    for tn, result in results.items():
                        if result and not result.get("error"):
                            # Get the shipment to access all fields
                            shipment = next((s for s in batch if s["tracking_number"] == tn), None)
                            if shipment:
                                # Normalize status
                                sonia_status = get_sonia_status(
                                    result.get("status", "unknown"),
                                    result.get("status_detail", "")
                                )

                                # Extract delivery date and estimated delivery date
                                delivery_date = None
                                estimated_delivery_date = None

                                if result.get("latest_event"):
                                    event_date = result["latest_event"].get("date")
                                    if event_date and sonia_status == "delivered":
                                        delivery_date = event_date

                                if result.get("estimated_delivery"):
                                    estimated_delivery_date = result["estimated_delivery"]

                                # Extract destination info from latest event
                                destination_city = None
                                destination_state = None
                                destination_country = None

                                if result.get("latest_event"):
                                    loc = result["latest_event"].get("location", {})
                                    destination_city = loc.get("city")
                                    destination_state = loc.get("state")
                                    destination_country = loc.get("country")

                                update_data = {
                                    "tracking_number": tn,
                                    "sonia_status": sonia_status,
                                    "fedex_status": result.get("status_detail", ""),
                                    "fedex_status_code": result.get("status"),
                                    "delivery_date": delivery_date,
                                    "estimated_delivery_date": estimated_delivery_date,
                                    "destination_city": destination_city,
                                    "destination_state": destination_state,
                                    "destination_country": destination_country,
                                    "is_delivered": sonia_status == "delivered",
                                    "last_fedex_check": datetime.now(COT),
                                    "raw_fedex_response": json.dumps(result.get("raw_response", {})),
                                }

                                db.update_shipment_fedex_data(tn, update_data)
                                updated_count += 1

                                if sonia_status == "delivered":
                                    delivered_count += 1

                    # Respect rate limits
                    import time
                    if i + batch_size < len(undelivered):
                        time.sleep(config.FEDEX_BATCH_DELAY)

                metrics["shipments_checked"] = len(undelivered)
                metrics["shipments_updated"] = updated_count
                metrics["shipments_delivered"] = delivered_count
                logger.info(f"FedEx check complete: {updated_count} updated, {delivered_count} newly delivered")

            except Exception as e:
                logger.error(f"STEP 3 ERROR: {e}")
                errors.append({"step": "fedex_check", "error": str(e)})

        # Ã¢ÂÂÃ¢ÂÂ STEP 4: Detect anomalies (Part C) Ã¢ÂÂÃ¢ÂÂ
        logger.info("STEP 4: Detecting anomalies...")
        try:
            detector = AnomalyDetector(thresholds={
                "transit_days": config.THRESHOLD_TRANSIT_DAYS,
                "customs_days": config.THRESHOLD_CUSTOMS_DAYS,
                "delivery_attempt_days": config.THRESHOLD_DELIVERY_ATTEMPT_DAYS,
                "label_no_movement_days": config.THRESHOLD_LABEL_NO_MOVEMENT_DAYS,
            })

            # Get all undelivered shipments with updated status
            all_undelivered = db.get_undelivered_shipments()
            anomalies = detector.check_all_shipments(all_undelivered)

            claims_created = 0
            for anomaly in anomalies:
                tn = anomaly["tracking_number"]
                rule = anomaly["rule"]

                # Check if claim already exists for this tracking+rule
                if not db.claim_exists_for_tracking(tn, rule):
                    claim_data = {
                        "tracking_number": tn,
                        "client_id": anomaly.get("client_id"),
                        "client_name": anomaly.get("client_name", ""),
                        "claim_type": anomaly.get("claim_type", "otro"),
                        "description": anomaly.get("description", ""),
                        "origin": "proactivo_tracker",
                        "created_automatically": True,
                        "auto_detection_rule": rule,
                    }
                    db.create_claim(claim_data)
                    claims_created += 1
                    logger.info(f"Auto-claim created: {tn} ({rule})")

            metrics["claims_created"] = claims_created
            logger.info(f"Anomaly detection complete: {claims_created} new claims created")

        except Exception as e:
            logger.error(f"STEP 4 ERROR: {e}")
            errors.append({"step": "anomaly_detection", "error": str(e)})

        # Ã¢ÂÂÃ¢ÂÂ STEP 5: Query Odoo and send reports Ã¢ÂÂÃ¢ÂÂ
        logger.info("STEP 5: Querying Odoo and sending reports...")
        try:
            odoo = OdooClient(
                url=config.ODOO_URL,
                db=config.ODOO_DB,
                username=config.ODOO_USERNAME,
                password=config.ODOO_PASSWORD,
            )

            whatsapp = WhatsAppSender(
                agent_url=config.SONIA_AGENT_URL,
                api_key=config.SONIA_AGENT_API_KEY,
            )

            report_gen = ReportGenerator()

            if odoo.authenticate():
                # Read WhatsApp BBDD spreadsheet for contact numbers
                bbdd_contacts = []
                contacts_by_tenant = {}
                if config.ODOO_SPREADSHEET_ID:
                    try:
                        bbdd_data = odoo.get_whatsapp_bbdd(config.ODOO_SPREADSHEET_ID)
                        bbdd_contacts = bbdd_data.get("contacts", [])
                        for c in bbdd_contacts:
                            tid = c.get("tenant_id")
                            if tid and c.get("whatsapp") and c.get("rol", "").lower() == "cliente" and not c.get("bloqueo"):
                                contacts_by_tenant.setdefault(tid, []).append(c)
                        logger.info(f"Loaded {len(bbdd_contacts)} contacts from WhatsApp BBDD, {len(contacts_by_tenant)} tenants with active contacts")
                    except Exception as e:
                        logger.error(f"Error reading WhatsApp BBDD spreadsheet: {e}")
                        errors.append({"step": "whatsapp_bbdd", "error": str(e)})

                # Process each client/tenant
                for tenant_id, client_info in tenant_mapping.items():
                    client_id = client_info.get("client_id")
                    client_name = client_info.get("client_name", f"Tenant-{tenant_id}")
                    odoo_company_id = client_info.get("odoo_company_id")

                    # Get shipments for this client
                    if client_id:
                        shipments = db.get_all_shipments_for_report(client_id)

                        if not shipments:
                            continue

                        # Generate report
                        report_text = report_gen.generate_client_report(client_name, shipments)
                        metrics["reports_generated"] += 1

                        # Send report to contacts from WhatsApp BBDD spreadsheet
                        tenant_contacts = contacts_by_tenant.get(int(tenant_id), [])
                        if tenant_contacts:
                            for contact in tenant_contacts:
                                phone = contact.get("whatsapp")
                                if phone:
                                    success = whatsapp.send_report_sync(phone, report_text, client_name)
                                    if success:
                                        metrics["reports_sent"] += 1
                        else:
                            # No contacts for this tenant - alert admin
                            active_count = len([s for s in shipments if not s.get("is_delivered")])
                            alert = report_gen.generate_admin_inconsistency_alert(
                                client_name, tenant_id, active_count
                            )
                            if config.ADMIN_WHATSAPP:
                                whatsapp.send_alert_sync(config.ADMIN_WHATSAPP, alert)
                                metrics["alerts_sent"] += 1

                logger.info(f"Reports: {metrics['reports_generated']} generated, {metrics['reports_sent']} sent")
            else:
                logger.error("Failed to authenticate with Odoo")
                errors.append({"step": "odoo_auth", "error": "Authentication failed"})

        except Exception as e:
            logger.error(f"STEP 5 ERROR: {e}")
            errors.append({"step": "reports_and_whatsapp", "error": str(e)})

        # Ã¢ÂÂÃ¢ÂÂ STEP 6: Complete run Ã¢ÂÂÃ¢ÂÂ
        status = "success" if not errors else "partial"
        db.complete_run(run_id, status, metrics, errors)

        elapsed = (datetime.now(COT) - start_time).total_seconds()
        logger.info(f"{'='*60}")
        logger.info(f"DAILY FLOW COMPLETED ({status}) in {elapsed:.1f}s")
        logger.info(f"Metrics: {json.dumps({k:v for k,v in metrics.items()}, indent=2)}")
        if errors:
            logger.warning(f"Errors: {json.dumps(errors, indent=2)}")
        logger.info(f"{'='*60}")

    except Exception as e:
        logger.critical(f"CRITICAL ERROR in daily flow: {e}")
        import traceback
        traceback.print_exc()
        _send_failure_alert(f"Error crÃÂ­tico en flujo diario: {e}")
        if db and run_id:
            try:
                db.complete_run(run_id, "failed", {}, [{"step": "critical", "error": str(e)}])
            except:
                pass
    finally:
        if fedex:
            fedex.close()
        if db:
            db.close()


def _send_failure_alert(message: str):
    """Send failure alert to admin via WhatsApp."""
    try:
        if config.ADMIN_WHATSAPP and config.SONIA_AGENT_URL:
            whatsapp = WhatsAppSender(
                agent_url=config.SONIA_AGENT_URL,
                api_key=config.SONIA_AGENT_API_KEY,
            )
            whatsapp.send_alert_sync(config.ADMIN_WHATSAPP, message)
    except Exception as e:
        logger.error(f"Failed to send failure alert: {e}")


# ============================================================================
# FASTAPI APP
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup: start scheduler
    scheduler.add_job(
        run_daily_flow,
        CronTrigger(hour=config.CRON_HOUR, minute=config.CRON_MINUTE),
        id="daily_flow",
        name="SonIA Daily Tracking Flow",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(f"Scheduler started. Next run at {config.CRON_HOUR}:{config.CRON_MINUTE:02d} COT")

    yield

    # Shutdown
    scheduler.shutdown()
    logger.info("Scheduler shut down")


app = FastAPI(
    title="SonIA Core Ã¢ÂÂ BloomsPal",
    description="Daily tracking orchestrator",
    lifespan=lifespan,
)


@app.get("/")
async def health():
    """Health check endpoint."""
    now = datetime.now(COT)
    jobs = scheduler.get_jobs()
    next_run = jobs[0].next_run_time if jobs else None

    return {
        "status": "ok",
        "service": "sonia-core",
        "time": now.isoformat(),
        "scheduler": {
            "running": scheduler.running,
            "next_run": next_run.isoformat() if next_run else None,
            "jobs": len(jobs),
        },
    }


@app.post("/api/trigger")
async def trigger_manual_run(api_key: str = ""):
    """Manually trigger the daily flow (for testing)."""
    if api_key != config.SONIA_AGENT_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    import threading
    thread = threading.Thread(target=run_daily_flow, kwargs={"manual": True})
    thread.start()

    return {"status": "started", "message": "Daily flow triggered manually"}


@app.get("/api/status")
async def get_status():
    """Get the status of the last run."""
    try:
        db = DBManager(config.DATABASE_URL)
        db.connect()
        # Get last run log from daily_run_logs table
        cursor = db.conn.cursor()
        cursor.execute(
            "SELECT id, run_date, started_at, completed_at, "
            "total_shipments_read, new_shipments, shipments_checked, "
            "shipments_updated, shipments_delivered, claims_created, "
            "reports_generated, reports_sent, alerts_sent, status, errors "
            "FROM daily_run_logs ORDER BY started_at DESC LIMIT 1"
        )
        row = cursor.fetchone()
        db.close()

        if row:
            columns = [desc[0] for desc in cursor.description]
            result = dict(zip(columns, row))
            # Parse JSON errors if present
            if result.get("errors"):
                try:
                    result["errors"] = json.loads(result["errors"])
                except:
                    pass
            return result
        return {"message": "No runs yet"}
    except Exception as e:
        return {"error": str(e)}


# ============================================================================
# WAREHOUSE PROCESSING Ã¢ÂÂ In-memory preview store
# ============================================================================

_warehouse_previews: Dict[str, dict] = {}


def _check_duplicate_awbs(all_awbs: list) -> dict:
    """Check if any AWBs already exist in warehouse_billing."""
    if not all_awbs:
        return {"has_duplicates": False, "duplicates": []}
    try:
        db_url = os.environ.get("DATABASE_URL")
        if not db_url:
            return {"has_duplicates": False, "duplicates": []}
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        # Unnest JSONB arrays and check intersection
        cur.execute("""
            SELECT DISTINCT
                elem AS awb,
                brand_name,
                dispatch_date::text,
                source_filename
            FROM warehouse_billing,
                 jsonb_array_elements_text(tracking_numbers) AS elem
            WHERE elem = ANY(%s)
        """, (all_awbs,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        dupes = [{"awb": r[0], "brand_name": r[1], "dispatch_date": r[2], "source_filename": r[3]} for r in rows]
        return {"has_duplicates": len(dupes) > 0, "duplicates": dupes}
    except Exception as e:
        logger.warning(f"Could not check duplicate AWBs: {e}")
        return {"has_duplicates": False, "duplicates": []}  # token Ã¢ÂÂ preview data

# Path to SKU map (bundled in repo or loaded at startup)
_SKU_MAP_PATH = os.path.join(os.path.dirname(__file__), "sku_map.json")


def _load_sku_map() -> dict:
    """Load SKUÃ¢ÂÂproduct ID mapping."""
    if os.path.exists(_SKU_MAP_PATH):
        with open(_SKU_MAP_PATH, "r") as f:
            return json.load(f)
    logger.warning(f"SKU map not found at {_SKU_MAP_PATH}")
    return {}


# ============================================================================
# WAREHOUSE ENDPOINTS
# ============================================================================

@app.get("/warehouse", response_class=HTMLResponse)
async def warehouse_ui():
    """Serve the warehouse processing UI."""
    return WAREHOUSE_HTML


@app.post("/api/process-warehouse")
async def process_warehouse(file: UploadFile = File(...)):
    """
    Upload a warehouse Excel file, parse it, and return a preview.
    Does NOT create orders yet Ã¢ÂÂ user must confirm.
    """
    # Validate file
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Only Excel files (.xlsx) are supported")

    try:
        # Save to temp file
        content = await file.read()
        file_hash = hashlib.md5(content).hexdigest()

        tmp_dir = tempfile.mkdtemp(prefix="warehouse_")
        tmp_path = os.path.join(tmp_dir, file.filename)
        with open(tmp_path, "wb") as f:
            f.write(content)

        # Parse
        parser = WarehouseParser(tmp_path)
        parsed = parser.parse()

        # Process
        sku_map = _load_sku_map()
        processor = WarehouseProcessor(sku_map=sku_map)
        preview = processor.process(parsed)

        # --- Duplicate AWB check ---
        all_awbs = []
        for brand, bdata in preview.items():
            awbs = bdata.get("tracking_numbers", [])
            if awbs:
                all_awbs.extend(awbs)
        duplicate_result = _check_duplicate_awbs(all_awbs)

        # Generate token and store preview
        token = str(uuid.uuid4())
        _warehouse_previews[token] = {
            "filename": file.filename,
            "file_hash": file_hash,
            "created_at": datetime.now(COT).isoformat(),
            "preview": preview,
        }

        # Clean up temp file
        os.unlink(tmp_path)
        os.rmdir(tmp_dir)

        # Build response summary
        summary = {}
        for brand, data in preview.items():
            summary[brand] = {
                "partner_name": data["partner_name"],
                "partner_id": data["partner_id"],
                "unique_orders": data["unique_orders"],
                "total_boxes": data["total_boxes"],
                "boxes_detail": {k: v["count"] for k, v in data["boxes_detail"].items()},
                "total_weight_raw": data["total_weight_raw"],
                "total_weight_billed": data["total_weight_billed"],
                "freight_cost": data["freight_cost"],
                "address_fee": data["address_fee"],
                "total_logistics": data["total_logistics"],
                "total_skus_sold": data["total_skus_sold"],
                "skus": {k: {"qty": v["qty"], "product_id": v.get("product_id")} for k, v in data.get("skus", {}).items()},
                "unmapped_skus": data["unmapped_skus"],
                "dispatch_date": str(data.get("dispatch_date", "")) if data.get("dispatch_date") else None,
            }

        return {
            "status": "preview",
            "filename": file.filename,
            "token": token,
            "brands": summary,
            "has_duplicates": duplicate_result["has_duplicates"],
            "duplicates": duplicate_result["duplicates"],
        }

    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error(f"Error processing warehouse file: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Error processing file: {e}")


@app.post("/api/warehouse/confirm")
async def confirm_warehouse(token: str):
    """
    Confirm a preview and create draft sale orders in Odoo.
    """
    if token not in _warehouse_previews:
        raise HTTPException(404, "Preview not found or expired. Please upload the file again.")

    stored = _warehouse_previews[token]
    preview = stored["preview"]

    try:
        # Connect to Odoo
        creator = OdooSaleOrderCreator(
            url=config.ODOO_URL,
            db=config.ODOO_DB,
            username=config.ODOO_USERNAME,
            password=config.ODOO_PASSWORD,
        )

        if not creator.authenticate():
            raise HTTPException(500, "Failed to authenticate with Odoo")

        # Create sale orders for each dropshipper
        results = {}
        for brand, data in preview.items():
            try:
                order = creator.create_sale_order(
                    partner_id=data["partner_id"],
                    order_lines=data["order_lines"],
                    dispatch_date=data.get("dispatch_date"),
                )
                results[brand] = {
                    "status": "created",
                    "partner_name": data["partner_name"],
                    "order_id": order["order_id"],
                    "order_name": order["order_name"],
                    "amount_total": order["amount_total"],
                    "state": order["state"],
                    "url": f"{config.ODOO_URL}/odoo/sales/{order['order_id']}",
                }
                logger.info(f"Created order {order['order_name']} for {brand}")
            except Exception as e:
                logger.error(f"Failed to create order for {brand}: {e}")
                results[brand] = {
                    "status": "error",
                    "partner_name": data["partner_name"],
                    "error": str(e),
                }


        # ââ Save billing data to PostgreSQL ââââââââââââââââââââââ
        try:
            billing_conn = psycopg2.connect(config.DATABASE_URL)
            billing_cur = billing_conn.cursor()

            billing_cur.execute("""
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
                )
            """)

            dispatch_date_fallback = date.today()

            for brand, data in preview.items():
                # Use date from packing list if available
                dispatch_date = data.get("dispatch_date") or dispatch_date_fallback
                brand_result = results.get(brand, {})
                if brand_result.get("status") != "created":
                    continue

                sku_summary = {}
                for sku_code, sku_info in data.get("skus", {}).items():
                    sku_summary[sku_code] = sku_info["qty"]

                billing_cur.execute("""
                    INSERT INTO warehouse_billing (
                        dispatch_date, brand_code, brand_name, partner_id,
                        odoo_order_id, odoo_order_name,
                        unique_orders, total_boxes, total_weight_kg,
                        weight_cost, address_fee, total_cost,
                        product_count, sku_summary, tracking_numbers,
                        source_filename
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s
                    )
                """, (
                    dispatch_date, brand,
                    data.get("partner_name", ""),
                    data.get("partner_id"),
                    brand_result.get("order_id"),
                    brand_result.get("order_name"),
                    data.get("unique_orders", 0),
                    data.get("total_boxes", 0),
                    data.get("total_weight_raw", 0),
                    data.get("freight_cost", 0),
                    data.get("address_fee", 0),
                    data.get("total_logistics", 0),
                    data.get("total_skus_sold", 0),
                    Json(sku_summary) if sku_summary else None,
                    Json(data.get("tracking_numbers", [])),
                    stored.get("filename", ""),
                ))

            billing_conn.commit()
            billing_cur.close()
            billing_conn.close()
            logger.info(f"Billing data saved for {len(results)} brands")

        except Exception as billing_err:
            logger.error(f"Failed to save billing data (non-blocking): {billing_err}")
            # Non-blocking: orders are already created in Odoo

        # Remove preview after use
        del _warehouse_previews[token]

        return {
            "status": "completed",
            "filename": stored["filename"],
            "orders": results,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating orders: {e}")
        raise HTTPException(500, f"Error creating orders: {e}")


# ============================================================================
# WAREHOUSE HTML UI
# ============================================================================

WAREHOUSE_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SonIA Ã¢ÂÂ Warehouse Processor</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; color: #333; }
        .container { max-width: 1000px; margin: 0 auto; padding: 20px; }
        h1 { color: #1a1a2e; margin-bottom: 8px; font-size: 24px; }
        .subtitle { color: #666; margin-bottom: 24px; font-size: 14px; }
        .card { background: white; border-radius: 12px; padding: 24px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
        .upload-zone { border: 2px dashed #ccc; border-radius: 12px; padding: 40px; text-align: center; cursor: pointer; transition: all 0.2s; background: #fafafa; }
        .upload-zone:hover, .upload-zone.dragover { border-color: #4a90d9; background: #f0f7ff; }
        .upload-zone input { display: none; }
        .upload-zone p { color: #666; margin-top: 8px; }
        .upload-zone .icon { font-size: 48px; color: #4a90d9; }
        .btn { display: inline-block; padding: 10px 24px; border: none; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer; transition: all 0.2s; }
        .btn-primary { background: #4a90d9; color: white; }
        .btn-primary:hover { background: #357abd; }
        .btn-primary:disabled { background: #ccc; cursor: not-allowed; }
        .btn-danger { background: #e74c3c; color: white; }
        .btn-danger:hover { background: #c0392b; }
        .btn-secondary { background: #95a5a6; color: white; }
        .btn-secondary:hover { background: #7f8c8d; }
        table { width: 100%; border-collapse: collapse; margin: 12px 0; }
        th, td { padding: 10px 12px; text-align: left; border-bottom: 1px solid #eee; font-size: 13px; }
        th { background: #f8f9fa; font-weight: 600; color: #555; }
        .text-right { text-align: right; }
        .text-center { text-align: center; }
        .badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; }
        .badge-success { background: #d4edda; color: #155724; }
        .badge-error { background: #f8d7da; color: #721c24; }
        .badge-warning { background: #fff3cd; color: #856404; }
        .spinner { display: inline-block; width: 20px; height: 20px; border: 3px solid #ccc; border-top-color: #4a90d9; border-radius: 50%; animation: spin 0.8s linear infinite; }
        @keyframes spin { to { transform: rotate(360deg); } }
        .hidden { display: none; }
        .loading-text { color: #666; margin-left: 8px; }
        .brand-section { margin-bottom: 16px; padding: 16px; background: #f8f9fa; border-radius: 8px; }
        .brand-name { font-size: 16px; font-weight: 700; color: #1a1a2e; margin-bottom: 4px; }
        .brand-partner { font-size: 12px; color: #888; margin-bottom: 12px; }
        .metrics-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 8px; margin-bottom: 12px; }
        .metric { background: white; padding: 10px; border-radius: 6px; text-align: center; }
        .metric-value { font-size: 20px; font-weight: 700; color: #4a90d9; }
        .metric-label { font-size: 11px; color: #888; margin-top: 2px; }
        .total-row { font-weight: 700; background: #e8f4fd; }
        .actions { display: flex; gap: 12px; margin-top: 20px; justify-content: center; }
        .result-link { color: #4a90d9; text-decoration: none; }
        .result-link:hover { text-decoration: underline; }
        .alert { padding: 12px 16px; border-radius: 8px; margin-bottom: 16px; }
        .alert-error { background: #f8d7da; color: #721c24; }
        .alert-success { background: #d4edda; color: #155724; }
        .logo { font-size: 14px; color: #999; text-align: center; margin-top: 24px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>SonIA Ã¢ÂÂ Warehouse Processor</h1>
        <p class="subtitle">Sube el archivo Excel del warehouse para crear ordenes de venta en Odoo</p>

        <!-- Upload Section -->
        <div id="uploadSection" class="card">
            <div class="upload-zone" id="dropZone" onclick="document.getElementById('fileInput').click()">
                <div class="icon">&#128230;</div>
                <p><strong>Click o arrastra el archivo Excel aqui</strong></p>
                <p>Solo archivos .xlsx</p>
                <input type="file" id="fileInput" accept=".xlsx,.xls">
            </div>
        </div>

        <!-- Loading -->
        <div id="loadingSection" class="card hidden">
            <div class="text-center">
                <div class="spinner"></div>
                <span class="loading-text" id="loadingText">Procesando archivo...</span>
            </div>
        </div>

        <!-- Preview Section -->
        <div id="previewSection" class="hidden">
            <div class="card">
                <h2 style="margin-bottom:4px;">Preview</h2>
                <p class="subtitle" id="previewFilename"></p>
                <p id="previewFecha" style="color:#2d6a4f; font-weight:bold; margin:4px 0 12px 0; font-size:1.05em; display:none;"></p>
                <div id="previewContent"></div>
                <div id="duplicateWarning" style="display:none; background:#fff3cd; border:1px solid #ffc107; border-radius:8px; padding:16px; margin-bottom:16px;">
                        <h3 style="color:#856404; margin:0 0 8px 0;">&#9888; AWBs Duplicados Detectados</h3>
                        <p style="color:#856404; margin:0 0 8px 0;">Las siguientes guias ya fueron procesadas anteriormente:</p>
                        <div id="duplicateList" style="max-height:200px; overflow-y:auto;"></div>
                        <p style="color:#856404; margin:8px 0 0 0; font-size:0.9em;">Puedes continuar si deseas reprocesar, pero los datos se duplicaran en el billing.</p>
                    </div>
                    <div class="actions">
                    <button class="btn btn-primary" id="confirmBtn" onclick="confirmOrders()">
                        Crear Ordenes en Odoo
                    </button>
                    <button class="btn btn-secondary" onclick="resetUI()">
                        Cancelar
                    </button>
                </div>
            </div>
        </div>

        <!-- Results Section -->
        <div id="resultsSection" class="hidden">
            <div class="card">
                <h2 style="margin-bottom:12px;">Ordenes Creadas</h2>
                <div id="resultsContent"></div>
                <div class="actions">
                    <button class="btn btn-primary" onclick="resetUI()">
                        Procesar Otro Archivo
                    </button>
                </div>
            </div>
        </div>

        <p class="logo">SonIA Core &mdash; BloomsPal</p>
    </div>

    <script>
        let currentToken = null;

        // Drag & drop
        const dropZone = document.getElementById('dropZone');
        dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('dragover'); });
        dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
            if (e.dataTransfer.files.length) uploadFile(e.dataTransfer.files[0]);
        });
        document.getElementById('fileInput').addEventListener('change', (e) => {
            if (e.target.files.length) uploadFile(e.target.files[0]);
        });

        async function uploadFile(file) {
            if (!file.name.match(/\\.xlsx?$/i)) {
                alert('Solo archivos Excel (.xlsx)');
                return;
            }

            show('loadingSection');
            hide('uploadSection');
            hide('previewSection');
            hide('resultsSection');
            document.getElementById('loadingText').textContent = 'Procesando archivo...';

            const formData = new FormData();
            formData.append('file', file);

            try {
                const res = await fetch('/api/process-warehouse', { method: 'POST', body: formData });
                const data = await res.json();

                if (!res.ok) {
                    throw new Error(data.detail || 'Error procesando archivo');
                }

                currentToken = data.token;
                renderPreview(data);
                hide('loadingSection');
                show('previewSection');
            } catch (err) {
                alert('Error: ' + err.message);
            } finally {
                hide('loadingSection');
                show('uploadSection');
            }
        }

        function renderPreview(data) {
            document.getElementById('previewFilename').textContent = data.filename;
            // Show dispatch date in dedicated element
            var fechaEl = document.getElementById('previewFecha');
            var fechaFound = '';
            if (data.brands) {
                var brandKeys = Object.keys(data.brands);
                for (var i = 0; i < brandKeys.length; i++) {
                    var bd = data.brands[brandKeys[i]];
                    if (bd.dispatch_date) { fechaFound = bd.dispatch_date; break; }
                }
            }
            if (fechaFound && fechaEl) {
                fechaEl.textContent = 'Fecha de corte: ' + fechaFound;
                fechaEl.style.display = 'block';
            } else if (fechaEl) {
                fechaEl.style.display = 'none';
            }
            let html = '';

            for (const [brand, info] of Object.entries(data.brands)) {
                html += '<div class="brand-section">';
                html += '<div class="brand-name">' + brand + '</div>';
                html += '<div class="brand-partner">Partner: ' + info.partner_name + ' (ID: ' + info.partner_id + ')</div>';

                html += '<div class="metrics-grid">';
                html += metric(info.unique_orders, 'Ordenes');
                html += metric(info.total_boxes, 'Cajas');
                html += metric(info.total_skus_sold, 'SKUs');
                html += metric(info.total_weight_raw + ' kg', 'Peso Real');
                html += metric(info.total_weight_billed + ' kg', 'Peso Facturado');
                html += metric('$' + info.freight_cost.toFixed(2), 'Flete');
                html += metric('$' + info.address_fee.toFixed(2), 'Address Fee');
                html += metric('$' + info.total_logistics.toFixed(2), 'Total');
                var costPerKg = info.total_weight_raw > 0 ? (info.total_logistics / info.total_weight_raw).toFixed(2) : '0.00';
                html += metric('$' + costPerKg, 'Costo/Kg');
                html += '</div>';
                // Boxes detail
                if (Object.keys(info.boxes_detail).length > 0) {
                    html += '<table><tr><th>Tipo Caja</th><th class="text-right">Cantidad</th></tr>';
                    for (const [box, count] of Object.entries(info.boxes_detail)) {
                        html += '<tr><td>' + box + '</td><td class="text-right">' + count + '</td></tr>';
                    }
                    html += '</table>';
                }

                // SKU detail table
                if (info.skus && Object.keys(info.skus).length > 0) {
                    html += '<h4 style="margin:12px 0 6px;font-size:0.95em;color:#555;">Detalle SKUs</h4>';
                    html += '<table><tr><th>SKU Code</th><th class="text-right">Cantidad</th></tr>';
                    var skuEntries = Object.entries(info.skus);
                    skuEntries.sort(function(a,b){ return b[1].qty - a[1].qty; });
                    for (var si = 0; si < skuEntries.length; si++) {
                        var skuCode = skuEntries[si][0];
                        var skuInfo = skuEntries[si][1];
                        var rowClass = skuInfo.product_id ? '' : ' style="color:#c0392b;font-weight:bold;"';
                        html += '<tr' + rowClass + '><td>' + skuCode + '</td><td class="text-right">' + skuInfo.qty + '</td></tr>';
                    }
                    html += '</table>';
                }

                                if (info.unmapped_skus && info.unmapped_skus.length > 0) {
                    html += '<div class="alert alert-error">SKUs no mapeados: ' + info.unmapped_skus.join(', ') + '</div>';
                }

                html += '</div>';
            }

            document.getElementById('previewContent').innerHTML = html;
        
                // --- Duplicate AWB warning ---
                const dupWarning = document.getElementById('duplicateWarning');
                const dupList = document.getElementById('duplicateList');
                if (data.has_duplicates && data.duplicates && data.duplicates.length > 0) {
                    let dupHtml = '<table style="width:100%; font-size:0.85em; border-collapse:collapse;">';
                    dupHtml += '<tr style="background:#ffc107;color:#856404;"><th style="padding:4px 8px;">AWB</th><th style="padding:4px 8px;">Marca</th><th style="padding:4px 8px;">Fecha</th><th style="padding:4px 8px;">Archivo</th></tr>';
                    data.duplicates.forEach(d => {
                        dupHtml += '<tr style="border-bottom:1px solid #ffeeba;"><td style="padding:4px 8px;">' + d.awb + '</td><td style="padding:4px 8px;">' + d.brand_name + '</td><td style="padding:4px 8px;">' + (d.dispatch_date || '-') + '</td><td style="padding:4px 8px;">' + (d.source_filename || '-') + '</td></tr>';
                    });
                    dupHtml += '</table>';
                    dupList.innerHTML = dupHtml;
                    dupWarning.style.display = 'block';
                } else {
                    dupWarning.style.display = 'none';
                }
}

        function metric(value, label) {
            return '<div class="metric"><div class="metric-value">' + value + '</div><div class="metric-label">' + label + '</div></div>';
        }

        async function confirmOrders() {
            if (!currentToken) return;
            if (!confirm('Confirmar creacion de ordenes de venta en Odoo?')) return;

            const btn = document.getElementById('confirmBtn');
            btn.disabled = true;
            btn.textContent = 'Creando...';

            show('loadingSection');
            document.getElementById('loadingText').textContent = 'Creando ordenes en Odoo...';

            try {
                const res = await fetch('/api/warehouse/confirm?token=' + encodeURIComponent(currentToken), {
                    method: 'POST',
                });
                const data = await res.json();

                if (!res.ok) throw new Error(data.detail || 'Error creando ordenes');

                renderResults(data);
                hide('loadingSection');
                hide('previewSection');
                show('resultsSection');
            } catch (err) {
                hide('loadingSection');
                btn.disabled = false;
                btn.textContent = 'Crear Ordenes en Odoo';
                alert('Error: ' + err.message);
            }
        }

        function renderResults(data) {
            let html = '<p style="margin-bottom:12px">Archivo: <strong>' + data.filename + '</strong></p>';
            html += '<table><tr><th>Dropshipper</th><th>Orden</th><th class="text-right">Total</th><th>Estado</th><th>Link</th></tr>';

            for (const [brand, info] of Object.entries(data.orders)) {
                html += '<tr>';
                html += '<td>' + brand + '</td>';
                if (info.status === 'created') {
                    html += '<td>' + info.order_name + '</td>';
                    html += '<td class="text-right">$' + info.amount_total.toFixed(2) + '</td>';
                    html += '<td><span class="badge badge-success">Draft</span></td>';
                    html += '<td><a class="result-link" href="' + info.url + '" target="_blank">Ver en Odoo</a></td>';
                } else {
                    html += '<td colspan="3"><span class="badge badge-error">Error: ' + info.error + '</span></td>';
                    html += '<td></td>';
                }
                html += '</tr>';
            }
            html += '</table>';

            document.getElementById('resultsContent').innerHTML = html;
        }

        function show(id) { document.getElementById(id).classList.remove('hidden'); }
        function hide(id) { document.getElementById(id).classList.add('hidden'); }
        function resetUI() {
            currentToken = null;
            hide('previewSection');
            hide('resultsSection');
            hide('loadingSection');
            show('uploadSection');
            document.getElementById('fileInput').value = '';
        }
    </script>
</body>
</html>
"""


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=config.PORT)
