"""
â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—
â•‘                    SonIA Core â€” Daily Tracking Orchestrator                    â•‘
â•‘                              BloomsPal                                        â•‘
â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

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
        # â”€â”€ Initialize Database â”€â”€
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

        # â”€â”€ STEP 1: Read from DynamoDB â”€â”€
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

        # â”€â”€ STEP 2: Sync tracking numbers to PostgreSQL â”€â”€
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
                "client_id": client_info.get("id"),
                "client_name_raw": client_info.get("name", f"Tenant-{tenant_id}"),
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
            alert_msg = f"âš ï¸ *Tenants sin mapeo detectados*\n\nIDs: {unmapped_list}\n\nPor favor actualizar la tabla tenant_mapping."
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

        # â”€â”€ STEP 3: Query FedEx for undelivered shipments â”€â”€
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

                    results = fedex.track_batch(tracking_unumbers)

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
                        time.sleep(config.FEDEX_BATCHA~DELAY)

                metrics["shipments_checked"] = len(undelivered)
                metrics["shipments_updated"] = updated_count
                metrics["shipments_delivered"] = delivered_count
                logger.info(f"FedEx check complete: {updated_count} updated, {delivered_count} newly delivered")

            except Exception as e:
                logger.error(f"STEP 3 ERROR: {e}")
                errors.append({"step": "fedex_check", "error": str(e)})
ÛY[ÚYHÛY[Ú[™›Ë™Ù]
šYŠBˆÛY[Û˜[YHHÛY[Ú[™›Ë™Ù]
›˜[YH‹ˆ•[˜[^İ[˜[ÚYHŠBˆÙÛ×ØÛÛ\[WÚYHÛY[Ú[™›Ë™Ù]
›ÙÛ×ØÛÛ\[WÚYŠB‚ˆÈÙ]Ú\Y[È›Üˆ\ÈÛY[ˆYˆÛY[ÚY‚ˆÚ\Y[ÈH‹™Ù]Ø[ÜÚ\Y[×Ù›Ü—Ü™\Ü
ÛY[ÚY
B‚ˆYˆ›İÚ\Y[Î‚ˆÛÛ[YB‚ˆÈÙ[™\˜]H™\Üˆ™\Üİ^H™\ÜÙÙ[‹™Ù[™\˜]WØÛY[Ü™\Ü
ÛY[Û˜[YKÚ\Y[ÊBˆY]šXÜÖÈœ™\Ü×ÙÙ[™\˜]Y—H
ÏHB‚ˆÈÙ]ÛÛXİÈœ›ÛHÙÛÈYˆÙH]™HÙÛ×ØÛÛ\[WÚYˆYˆÙÛ×ØÛÛ\[WÚY‚ˆN‚ˆÛÛXİÈHÙÛË™Ù]ØÛÛXİ×Ù›Ü—ØÛÛ\[JÙÛ×ØÛÛ\[WÚY
B‚ˆ›ÜˆÛÛXİ[ˆÛÛXİÎ‚ˆÛ™HHÛÛXİ™Ù]
Ú]Ø\ŠBˆYˆÛ™N‚ˆİXØÙ\ÜÈHÚ]Ø\œÙ[™Ü™\ÜÜŞ[˜ÊÛ™K™\Üİ^ÛY[Û˜[YJBˆYˆİXØÙ\ÜÎ‚ˆY]šXÜÖÈœ™\Ü×ÜÙ[—H
ÏHBˆ^Ù\^Ù\[Ûˆ\ÈN‚ˆÙÙÙ\‹™\œ›ÜŠˆ‘\œ›ÜˆÙ][™ÈÙÛÈÛÛXİÈ›ÜˆÛÛ\[HÛÙÛ×ØÛÛ\[WÚYNˆÙ_HŠBˆ\œ›ÜœË˜\[™
Èœİ\ˆ›ÙÛ×ØÛÛXİÈ‹™\œ›ÜˆˆİŠJ_JB‚ˆÈ8¥ 8¥ ÕTˆÙ[™[\È8¥ 8¥ ˆÙÙÙ\‹š[™›Ê”ÕTˆÙ[™[™ÈYZ[ˆ[\Ë‹‹ˆŠBˆYˆ\œ›ÜœÎ‚ˆ[\İÈH‹¸¦¨;î#È
‘SÔÈSˆ‘TÔ•HPT’SÊˆ8¥dx¥dx¥dx¥dx¥dW—ˆ‚ˆ›Üˆ\œ›Üˆ[ˆ\œ›ÜœÎ‚ˆ[\İÈ
ÏHˆˆ<'e : "{error['paste']} - {error['error']}\n"
            alert_ts += f"\nLâ”gistroé™„Report:\nI d ::% correct agode
            if config.ADMIN_WHATSAPP and config.SONIA_AGENT_URL:
                try:
                    whatsapp.send_alert_sync(config.ADMIN_WHATSAPP, alert_ts)
                    metrics["alerts_sent"] += 1
                except Exception as e:
                    logger.error(f"Failed to send error alert: {e}")

        # â”€â”€ FINAL: Complete run â”€â”€B         end_time = datetime.now(COT)
        duration = end_time - start_time
        logger.info(f"{'='*60}")
        logger.info(f"DAILY FLOW COMPLETED: {end_time.strftime('%Y-%m-%d %H:%M:%S')} COT")
        logger.info(f"Duration: {duration}")
        logger.info(f"{"safety_chSKU_MAP_PATH):
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
    Does NOT create orders yet â€” user must confirm.
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
                "unmapped_skus": data["unmapped_skus"],
            }

        return {
            "status": "preview",
            "filename": file.filename,
            "token": token,
            "brands": summary,
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

        if not        th { background: #f8f9fa; font-weight: 600; color: #555; }
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
        <h1>SonIA â€” Warehouse Processor</h1>
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
                <div id="previewContent"></div>
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
                hide('loadingSection');
                show('uploadSection');
                alert('Error: ' + err.message);
            }
        }

        function renderPreview(data) {
            document.getElementById('previewFilename').textContent = data.filename;
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
                html += '</div>';

                // Boxes detail
                if (Object.keys(info.boxes_detail).length > 0) {
                    html += '<table><tr><th>Tipo Caja</th><th class="text-right">Cantidad</th></tr>';
                    for (const [box, count] of Object.entries(info.boxes_detail)) {
                        html += '<tr><td>' + box + '</td><td class="text-right">' + count + '</td></tr>';
                    }
                    html += '</table>';
                }

                if (info.unmapped_skus && info.unmapped_skus.length > 0) {
                    html += '<div class="alert alert-error">SKUs no mapeados: ' + info.unmapped_skus.join(', ') + '</div>';
                }

                html += '</div>';
            }

            document.getElementById('previewContent').innerHTML = html;
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
