"""
Corte Reader (v3) - Reads warehouse reports from DynamoDB + S3 Excel files.

Actual DynamoDB table structures:

carrier_reports:
  - id (PK, UUID)
  - carrierReportData (JSON string)
  - carrierId (e.g. "FEDEX_IPD_TXT")
  - status ("FINALIZED")
  - url (carrier report file URL)
  - urlWarehouseReport (warehouse Excel URL - may be missing)
  - bills: [{tenant: int, url: "s3://bill_report/...xlsx"}]
  - batchNumbers: [int]
  - trackingNumberMaster (string)
  - createdAt, updatedAt (ISO strings)

fedex_consolidations:
  - id (PK, UUID)
  - shipmentId (UUID, links to carrier_report)
  - status ("FINALIZED")
  - trackingNumber (master tracking)
  - packagesCount (int)
  - packages: [{weight, id, reserveId, trackingNumber, tenant, reservePackageId}]
  - urlWarehouseReport (warehouse Excel URL)
  - bills: [{tenant: int, url: "s3://bill_report/...xlsx"}]
  - createdAt, updatedAt (ISO strings)

S3 bucket: packages-files-prod (us-east-2)
"""
import boto3
import io
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional, Any

logger = logging.getLogger(__name__)

try:
    import openpyxl
except ImportError:
    openpyxl = None
    logger.warning("openpyxl not installed - Excel parsing will be limited")


# ——— Data Classes ————————————————————————————————————————

@dataclass
class BoxItem:
    """A single product item inside a box."""
    sku: str = ""
    product_name: str = ""
    quantity: int = 1
    price: float = 0.0
    weight: float = 0.0


@dataclass
class Box:
    """A shipping box/package in a corte."""
    box_id: str = ""
    box_type: str = ""
    weight: float = 0.0
    tracking_number: str = ""
    order_number: str = ""
    items: List[BoxItem] = field(default_factory=list)


@dataclass
class ParsedCorte:
    """Result of parsing a warehouse Excel report."""
    boxes: List[Box] = field(default_factory=list)

    @property
    def total_boxes(self) -> int:
        return len(self.boxes)

    @property
    def total_orders(self) -> int:
        return len({b.order_number for b in self.boxes if b.order_number})

    @property
    def total_items(self) -> int:
        return sum(sum(item.quantity for item in box.items) for box in self.boxes)

    @property
    def total_weight(self) -> float:
        return sum(b.weight for b in self.boxes)


@dataclass
class CorteData:
    """A warehouse report (corte) from DynamoDB with optional parsed data."""
    corte_id: str = ""
    table_source: str = ""
    record_id: str = ""
    tenant: int = 0
    tenant_name: str = ""
    warehouse_report_url: str = ""
    bill_urls: Dict[int, str] = field(default_factory=dict)
    master_tracking: str = ""
    status: str = ""
    created_at: str = ""
    boxes: List[Box] = field(default_factory=list)
    parsed: Optional[ParsedCorte] = None

    @property
    def total_boxes(self) -> int:
        if self.parsed:
            return self.parsed.total_boxes
        return len(self.boxes)

    @property
    def total_orders(self) -> int:
        if self.parsed:
            return self.parsed.total_orders
        return len({b.order_number for b in self.boxes if b.order_number})

    @property
    def total_items(self) -> int:
        if self.parsed:
            return self.parsed.total_items
        return sum(sum(item.quantity for item in box.items) for box in self.boxes)


# ——— DynamoDB + S3 Reader ————————————————————————————————————

class CorteReader:
    """Reads warehouse reports from DynamoDB and parses their Excel files."""

    def __init__(
        self,
        aws_access_key_id: str,
        aws_secret_access_key: str,
        aws_region: str = "us-east-2",
        carrier_reports_table: str = "carrier_reports",
        fedex_consolidations_table: str = "fedex_consolidations",
    ):
        self.aws_config = {
            "region_name": aws_region,
            "aws_access_key_id": aws_access_key_id,
            "aws_secret_access_key": aws_secret_access_key,
        }
        self.carrier_reports_table = carrier_reports_table
        self.fedex_consolidations_table = fedex_consolidations_table

    def fetch_unprocessed_cortes(self, processed_ids: Set[str]) -> List[CorteData]:
        """
        Scan DynamoDB tables for FINALIZED cortes not yet processed.
        Returns list of CorteData objects.
        """
        dynamodb = boto3.resource("dynamodb", **self.aws_config)

        cortes = []

        # Scan carrier_reports
        cr_cortes = self._scan_table_for_cortes(
            dynamodb, self.carrier_reports_table, processed_ids
        )
        cortes.extend(cr_cortes)
        logger.info(f"carrier_reports: found {len(cr_cortes)} unprocessed")

        # Scan fedex_consolidations
        fc_cortes = self._scan_table_for_cortes(
            dynamodb, self.fedex_consolidations_table, processed_ids
        )
        cortes.extend(fc_cortes)
        logger.info(f"fedex_consolidations: found {len(fc_cortes)} unprocessed")

        return cortes

    def _scan_table_for_cortes(
        self, dynamodb, table_name: str, processed_ids: Set[str]
    ) -> List[CorteData]:
        """Scan a single DynamoDB table for unprocessed FINALIZED cortes."""
        table = dynamodb.Table(table_name)
        cortes = []

        scan_kwargs = {
            "FilterExpression": "attribute_exists(urlWarehouseReport) AND #s = :finalized",
            "ExpressionAttributeNames": {"#s": "status"},
            "ExpressionAttributeValues": {":finalized": "FINALIZED"},
        }
        done = False
        start_key = None

        while not done:
            if start_key:
                scan_kwargs["ExclusiveStartKey"] = start_key

            response = table.scan(**scan_kwargs)
            items = response.get("Items", [])

            for item in items:
                url = item.get("urlWarehouseReport", "")
                if not url or str(url).strip() == "":
                    continue

                record_id = str(item.get("id", ""))
                corte_id = f"{table_name}:{record_id}"

                if corte_id in processed_ids:
                    continue

                # Extract bill URLs per tenant
                bill_urls = {}
                for bill in item.get("bills", []):
                    if isinstance(bill, dict):
                        t = bill.get("tenant")
                        u = bill.get("url", "")
                        if t is not None and u:
                            bill_urls[int(t)] = u

                # Extract tenant from bills or packages
                tenant = 0
                if bill_urls:
                    tenant = next(iter(bill_urls.keys()))

                packages = item.get("packages", [])
                if packages and isinstance(packages, list) and not tenant:
                    first_pkg = packages[0] if packages else {}
                    if isinstance(first_pkg, dict):
                        tenant = int(first_pkg.get("tenant", 0))

                # Pre-populate boxes from DynamoDB packages data
                boxes = []
                for pkg in packages:
                    if isinstance(pkg, dict):
                        box = Box(
                            box_id=str(pkg.get("id", "")),
                            weight=float(pkg.get("weight", 0) or 0),
                            tracking_number=str(pkg.get("trackingNumber", "")),
                        )
                        boxes.append(box)

                corte = CorteData(
                    corte_id=corte_id,
                    table_source=table_name,
                    record_id=record_id,
                    tenant=tenant,
                    warehouse_report_url=str(url),
                    bill_urls=bill_urls,
                    master_tracking=str(item.get("trackingNumber", item.get("trackingNumberMaster", ""))),
                    status=str(item.get("status", "")),
                    created_at=str(item.get("createdAt", "")),
                    boxes=boxes,
                )
                cortes.append(corte)

            start_key = response.get("LastEvaluatedKey")
            if not start_key:
                done = True

        return cortes

    def _download_from_s3(self, s3_url: str) -> bytes:
        """Download a file from S3 given an s3:// URL or https URL."""
        s3 = boto3.client("s3", **self.aws_config)

        if s3_url.startswith("s3://"):
            # Parse s3://bucket/key
            parts = s3_url.replace("s3://", "").split("/", 1)
            bucket = parts[0]
            key = parts[1] if len(parts) > 1 else ""
        elif "s3.amazonaws.com" in s3_url:
            # Parse https://bucket.s3.region.amazonaws.com/key
            from urllib.parse import urlparse
            parsed = urlparse(s3_url)
            bucket = parsed.hostname.split(".")[0]
            key = parsed.path.lstrip("/")
        else:
            # Try as bucket/key directly
            parts = s3_url.split("/", 1)
            bucket = parts[0]
            key = parts[1] if len(parts) > 1 else ""

        logger.info(f"Downloading from S3: bucket={bucket}, key={key}")
        response = s3.get_object(Bucket=bucket, Key=key)
        return response["Body"].read()

    def parse_warehouse_excel(self, corte: CorteData) -> Optional[ParsedCorte]:
        """
        Download and parse the warehouse Excel report for a corte.
        Returns a ParsedCorte with boxes and items, or None if parsing fails.

        The Excel file typically has columns like:
        - Tracking number
        - Order number / Reference
        - Product SKU / Name
        - Quantity
        - Weight
        - Box type
        """
        if not openpyxl:
            logger.error("openpyxl not installed - cannot parse Excel files")
            return None

        url = corte.warehouse_report_url
        if not url:
            logger.warning(f"No warehouse report URL for corte {corte.corte_id}")
            return None

        try:
            # Download Excel file
            excel_data = self._download_from_s3(url)
            wb = openpyxl.load_workbook(io.BytesIO(excel_data), read_only=True, data_only=True)

            boxes_dict: Dict[str, Box] = {}

            for sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                rows = list(ws.iter_rows(values_only=True))
                if not rows:
                    continue

                # Find header row (look for tracking/order/sku keywords)
                header_row = None
                header_idx = 0
                for i, row in enumerate(rows[:10]):
                    row_str = " ".join(str(c).lower() for c in row if c)
                    if any(kw in row_str for kw in ["tracking", "guia", "orden", "order", "sku"]):
                        header_row = [str(c).strip().lower() if c else "" for c in row]
                        header_idx = i
                        break

                if not header_row:
                    continue

                # Map column indices
                col_map = {}
                for idx, col_name in enumerate(header_row):
                    if any(k in col_name for k in ["tracking", "guia"]):
                        col_map.setdefault("tracking", idx)
                    elif any(k in col_name for k in ["order", "orden", "pedido", "referenc"]):
                        col_map.setdefault("order", idx)
                    elif any(k in col_name for k in ["sku", "codigo", "code", "ref"]):
                        col_map.setdefault("sku", idx)
                    elif any(k in col_name for k in ["product", "producto", "descripcion", "nombre", "name"]):
                        col_map.setdefault("product_name", idx)
                    elif any(k in col_name for k in ["qty", "quantity", "cantidad", "cant"]):
                        col_map.setdefault("quantity", idx)
                    elif any(k in col_name for k in ["price", "precio", "valor", "value"]):
                        col_map.setdefault("price", idx)
                    elif any(k in col_name for k in ["weight", "peso", "kg"]):
                        col_map.setdefault("weight", idx)
                    elif any(k in col_name for k in ["box", "caja", "type", "tipo"]):
                        col_map.setdefault("box_type", idx)

                # Parse data rows
                for row in rows[header_idx + 1:]:
                    if not row or all(c is None for c in row):
                        continue

                    def get_val(key, default=""):
                        if key in col_map and col_map[key] < len(row):
                            v = row[col_map[key]]
                            return v if v is not None else default
                        return default

                    tracking = str(get_val("tracking", "")).strip()
                    order_num = str(get_val("order", "")).strip()
                    sku = str(get_val("sku", "")).strip()
                    product_name = str(get_val("product_name", "")).strip()
                    qty = 1
                    try:
                        qty = int(float(get_val("quantity", 1)))
                    except (ValueError, TypeError):
                        qty = 1
                    price = 0.0
                    try:
                        price = float(get_val("price", 0))
                    except (ValueError, TypeError):
                        price = 0.0
                    weight = 0.0
                    try:
                        weight = float(get_val("weight", 0))
                    except (ValueError, TypeError):
                        weight = 0.0
                    box_type = str(get_val("box_type", "")).strip()

                    if not tracking and not order_num and not sku:
                        continue

                    # Group by tracking number (each tracking = one box)
                    box_key = tracking or order_num or sku
                    if box_key not in boxes_dict:
                        # Try to get weight from pre-populated DynamoDB data
                        dynamo_weight = 0.0
                        for pre_box in corte.boxes:
                            if pre_box.tracking_number == tracking:
                                dynamo_weight = pre_box.weight
                                break

                        boxes_dict[box_key] = Box(
                            box_id=box_key,
                            box_type=box_type,
                            weight=weight or dynamo_weight,
                            tracking_number=tracking,
                            order_number=order_num,
                        )

                    if sku:
                        boxes_dict[box_key].items.append(BoxItem(
                            sku=sku,
                            product_name=product_name,
                            quantity=qty,
                            price=price,
                            weight=weight,
                        ))

            wb.close()

            parsed = ParsedCorte(boxes=list(boxes_dict.values()))
            logger.info(
                f"Parsed Excel for {corte.corte_id}: "
                f"{parsed.total_boxes} boxes, {parsed.total_orders} orders, "
                f"{parsed.total_items} items, {parsed.total_weight:.1f} kg"
            )
            return parsed

        except Exception as e:
            logger.error(f"Error parsing Excel for {corte.corte_id}: {e}", exc_info=True)
            return None
