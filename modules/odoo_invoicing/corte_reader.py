"""
Corte Reader (v2.1) - Reads warehouse reports from DynamoDB + S3 Excel files.

Actual DynamoDB table structures (discovered 2026-02-20):

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
  - confirmationJobId (string)
  - status ("FINALIZED")
  - trackingNumber (master tracking)
  - packagesCount (int)
  - packages: [{weight, id, reserveId, trackingNumber, tenant, reservePackageId}]
  - urlWarehouseReport (warehouse Excel URL)
  - urlMaster, urlCRNs
  - bills: [{tenant: int, url: "s3://bill_report/...xlsx"}]
  - createdAt, updatedAt (ISO strings)

S3 bucket: packaging-files (us-east-2)
  - Warehouse reports: supplier_instructions/{id}-{uuid}.xlsx
  - Bill reports: bill_report/{tenant}-{uuid}.xlsx
  - Carrier reports: carrier_reports/{batchNumber}-{uuid}.txt

Flow:
  1. Scan DynamoDB tables for records with urlWarehouseReport
  2. Filter out already-processed cortes
  3. Download Excel files from S3 (using requests, no CORS on server)
  4. Parse them to extract: orders, boxes, products, tracking numbers
  5. Return structured data ready for invoicing
"""
import boto3
import requests
import io
import logging
from decimal import Decimal
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ─── Data Classes ─────────────────────────────────────────────────

@dataclass
class BoxItem:
    """A product inside a box."""
    sku: str
    product_name: str = ""
    quantity: int = 1
    price: float = 0.0


@dataclass
class Box:
    """A box/package within a corte."""
    box_id: str = ""
    box_type: str = ""
    tracking_number: str = ""
    order_number: str = ""
    weight: float = 0.0  # From DynamoDB packages data
    items: List[BoxItem] = field(default_factory=list)


@dataclass
class CorteData:
    """Parsed data from a single warehouse report (corte)."""
    corte_id: str  # Unique ID: "{table}:{record_id}"
    table_source: str  # "carrier_reports" or "fedex_consolidations"
    excel_url: str
    tenant: int = 0
    tenant_name: str = ""
    report_date: str = ""
    boxes: List[Box] = field(default_factory=list)
    sku_summary: Dict[str, int] = field(default_factory=dict)
    # Bill report URLs per tenant
    bill_urls: Dict[int, str] = field(default_factory=dict)
    # Metadata
    dynamo_record: Dict[str, Any] = field(default_factory=dict)

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


# ─── DynamoDB + S3 Reader ─────────────────────────────────────────

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
        self.dynamo = boto3.resource("dynamodb", **self.aws_config)
        self.s3 = boto3.client("s3", **self.aws_config)
        self.carrier_reports_table = carrier_reports_table
        self.fedex_consolidations_table = fedex_consolidations_table

    def fetch_unprocessed_cortes(
        self, processed_corte_ids: Set[str]
    ) -> List[CorteData]:
        """
        Scan both DynamoDB tables and return cortes that:
        - Have a non-empty urlWarehouseReport
        - Status is FINALIZED
        - Haven't been processed yet
        """
        all_cortes = []

        for table_name in [self.carrier_reports_table, self.fedex_consolidations_table]:
            try:
                cortes = self._scan_table_for_cortes(table_name, processed_corte_ids)
                all_cortes.extend(cortes)
                logger.info(f"Found {len(cortes)} unprocessed cortes in {table_name}")
            except Exception as e:
                logger.error(f"Error scanning {table_name}: {e}")

        logger.info(f"Total unprocessed cortes: {len(all_cortes)}")
        return all_cortes

    def _scan_table_for_cortes(
        self, table_name: str, processed_ids: Set[str]
    ) -> List[CorteData]:
        """Scan a single DynamoDB table for finalized records with urlWarehouseReport."""
        table = self.dynamo.Table(table_name)
        cortes = []

        scan_kwargs = {
            "FilterExpression":
                "attribute_exists(urlWarehouseReport) AND #s = :finalized",
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

                # Build corte ID from the record's primary key
                record_id = str(item.get("id", ""))
                corte_id = f"{table_name}:{record_id}"

                if corte_id in processed_ids:
                    continue

                # Extract bill URLs per tenant
                bill_urls = {}
                for bill in item.get("bills", []):
                    t = bill.get("tenant")
                    u = bill.get("url", "")
                    if t is not None and u:
                        bill_urls[int(t)] = u

                # Extract tenant from bills or packages
                tenant = 0
                if bill_urls:
                    tenant = next(iter(bill_urls.keys()))

                # For fedex_consolidations, also check packages for tenant
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
                            tracking_number=str(pkg.get("trackingNumber", "")),
                            weight=float(pkg.get("weight", 0)),
                        )
                        boxes.append(box)