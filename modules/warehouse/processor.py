"""
SonIA Core ÃÂÃÂ¢ÃÂÃÂÃÂÃÂ Warehouse Processor
Takes parsed warehouse data and calculates freight costs, address fees,
and builds sale order previews for each dropshipper.
"""

import logging
import math
import json
from typing import Dict, List, Any, Optional
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP

logger = logging.getLogger(__name__)

# ÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂ Box weights (GROSS WEIGHT ÃÂÃÂ¢ÃÂÃÂÃÂÃÂ full box as shipped) ÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂ
# Source: Bloomspal Data.xlsx ÃÂÃÂ¢ÃÂÃÂÃÂÃÂ Cajas tab ÃÂÃÂ¢ÃÂÃÂÃÂÃÂ "GROSS WEIGHT EN KILOS"
BOX_WEIGHTS: Dict[str, float] = {
    "CAJA MASTER 1830 COFFEE": 1.0,
    "CAJA MASTER BAOBAB": 1.0,
    "CAJA MASTER BEBLISS": 1.0,
    "CAJA MASTER BLOOMSPAL": 1.0,
    "CAJA BLOOMSPAL (NO TENER EN CUENTA)": 1.0,
    "CAJA MASTER BCC": 1.0,
    "CAJA MASTER CBTB": 1.0,
    "CAJA GRANDE": 1.65,
    "CAJA MEDIANA": 1.65,
    "CAJA PEQUEÃÂÃÂÃÂÃÂA": 1.0,
    "CAJA KIT": 3.0,
    "CAJA MASTER DON MAIZ": 3.19,
    "CAJA MASTER": 1.0,
    "BOLSA FEDEX": 1.0,
    "CAJA MASTER GAVI": 1.0,
    "CAJA PROPIA HACIENDA VENECIA": 1.51,
    "CAJA MASTER THG": 1.0,
    "CAJA CARTON COSMETIQUERA THG": 2.0,
}

DEFAULT_BOX_WEIGHT = 1.0  # kg

# ÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂ Freight pricing ÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂ
COST_PER_KG = 6.5    # USD per kg
ADDRESS_FEE = 8.0     # USD per unique order/address

# ÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂ Dropshipper ÃÂÃÂ¢ÃÂÃÂÃÂÃÂ Odoo partner mapping ÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂ
DROPSHIPPER_PARTNERS: Dict[str, Dict[str, Any]] = {
    "DIOS MIO COFFEE": {"partner_id": 2750, "partner_name": "Dios Mio Coffee LLC"},
    "GAVI": {"partner_id": 3891, "partner_name": "GAVICO BRANDS CORP"},
    "HACIENDA VENECIA": {"partner_id": 38954, "partner_name": "Hacienda Venecia"},
    "THE HAIR GENERATION": {"partner_id": 2859, "partner_name": "THE HAIR GENERATION LLC"},
    "COOCENTRAL": {"partner_id": 3931, "partner_name": "Cooperativa Central de Caficultores del Huila"},
    "DON MAIZ": {"partner_id": 840, "partner_name": "DON MAIZ SAS"},
    "CAFE ENLACE": {"partner_id": 875, "partner_name": "Federacion Nacional de Cafeteros - FNC"},
    "KAFFETO": {"partner_id": 3935, "partner_name": "KAFFETO GOURMET, LLC"},
}

# ÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂ Logistics product IDs in Odoo ÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂÃÂÃÂ¢ÃÂÃÂÃÂÃÂ
LOGISTICS_WEIGHT_PRODUCT_ID = 5788   # "Costo Logistico por Peso (por Kg)"
LOGISTICS_ADDRESS_FEE_PRODUCT_ID = 5789  # "Address Fee (por Orden)"


def _get_box_weight(box_type: str) -> float:
    """Get GROSS WEIGHT for a box type with fuzzy matching."""
    # Exact match
    if box_type in BOX_WEIGHTS:
        return BOX_WEIGHTS[box_type]

    # Case-insensitive match
    box_upper = box_type.upper().strip()
    for key, weight in BOX_WEIGHTS.items():
        if box_upper == key.upper():
            return weight

    # Partial match
    for key, weight in BOX_WEIGHTS.items():
        if box_upper in key.upper() or key.upper() in box_upper:
            return weight

    logger.warning(f"Unknown box type: '{box_type}', using default {DEFAULT_BOX_WEIGHT} kg")
    return DEFAULT_BOX_WEIGHT


def _round_freight_weight(weight_kg: float) -> float:
    """
    Round weight for freight billing:
      - Less than 1 kg ÃÂÃÂ¢ÃÂÃÂÃÂÃÂ billed as 1 kg
      - ÃÂÃÂ¢ÃÂÃÂÃÂÃÂ¥ 1 kg ÃÂÃÂ¢ÃÂÃÂÃÂÃÂ round UP to next 0.5 kg
    """
    if weight_kg <= 0:
        return 0.0
    if weight_kg < 1.0:
        return 1.0
    return math.ceil(weight_kg * 2) / 2


# Folder-name aliases that map to the same partner as an existing brand
BRAND_ALIASES: Dict[str, str] = {
    "DMC WALMART": "DIOS MIO COFFEE",
    "DMC ANDRES CARNE DE RES": "DIOS MIO COFFEE",
    "DMC KITS": "DIOS MIO COFFEE",
    "DMC": "DIOS MIO COFFEE",
    "FNC": "CAFE ENLACE",
    "FNC - CAFE ENLACE": "CAFE ENLACE",
}


def _resolve_partner(brand_name: str) -> Optional[Dict[str, Any]]:
    """Map a brand name from warehouse to Odoo partner info."""
    name_upper = brand_name.upper().strip()

    # Exact match
    if name_upper in DROPSHIPPER_PARTNERS:
        return DROPSHIPPER_PARTNERS[name_upper]

    # Check aliases
    if name_upper in BRAND_ALIASES:
        return DROPSHIPPER_PARTNERS.get(BRAND_ALIASES[name_upper])

    # Partial match
    for key, info in DROPSHIPPER_PARTNERS.items():
        if key in name_upper or name_upper in key:
            return info

    # Alias partial match
    for alias, target in BRAND_ALIASES.items():
        if alias in name_upper or name_upper in alias:
            return DROPSHIPPER_PARTNERS.get(target)

    logger.warning(f"No partner mapping found for brand: '{brand_name}'")
    return None


class WarehouseProcessor:
    """Process parsed warehouse data into sale order previews."""

    def __init__(self, sku_map: Dict[str, int] = None):
        """
        Args:
            sku_map: Dict mapping SKU strings to Odoo product IDs.
        """
        self.sku_map = sku_map or {}

    def load_sku_map(self, path: str):
        """Load SKUÃÂÃÂ¢ÃÂÃÂÃÂÃÂproduct ID mapping from a JSON file."""
        with open(path, "r") as f:
            self.sku_map = json.load(f)
        logger.info(f"Loaded {len(self.sku_map)} SKU mappings from {path}")

    def process(self, parsed_data: Dict[str, Dict]) -> Dict[str, Dict[str, Any]]:
        """
        Process parsed warehouse data and build sale order previews.

        Args:
            parsed_data: Output from WarehouseParser.parse()

        Returns:
            {
                "Dios Mio Coffee": {
                    "partner_id": 2750,
                    "partner_name": "Dios Mio Coffee LLC",
                    "unique_orders": 8,
                    "boxes_detail": {
                        "CAJA PEQUEÃÂÃÂÃÂÃÂA": {"count": 5, "weight_per_box": 1.0, "total_weight": 5.0},
                        ...
                    },
                    "total_boxes": 7,
                    "total_weight_raw": 8.3,
                    "total_weight_billed": 8.5,
                    "freight_cost": 55.25,
                    "address_fee": 64.0,
                    "total_logistics": 119.25,
                    "skus": {"DMC12BMGS": {"qty": 4, "product_id": 5594}, ...},
                    "total_skus_sold": 12,
                    "unmapped_skus": [],
                    "order_lines": [...],
                }
            }
        """
        result = {}

        for brand, data in parsed_data.items():
            partner_info = _resolve_partner(brand)
            if not partner_info:
                logger.error(f"Skipping brand '{brand}': no partner mapping")
                continue

            # Calculate box weights
            boxes_detail = {}
            total_weight_raw = 0.0

            for box_type, count in data.get("boxes", {}).items():
                weight = _get_box_weight(box_type)
                total = weight * count
                boxes_detail[box_type] = {
                    "count": count,
                    "weight_per_box": weight,
                    "total_weight": round(total, 2),
                }
                total_weight_raw += total

            total_weight_raw = round(total_weight_raw, 2)
            total_weight_billed = total_weight_raw  # No rounding ÃÂÃÂ¢ÃÂÃÂÃÂÃÂ bill exact weight

            # Calculate costs
            unique_orders = data.get("unique_orders", 0)
            freight_cost = round(total_weight_billed * COST_PER_KG, 2)
            address_fee = round(unique_orders * ADDRESS_FEE, 2)
            total_logistics = round(freight_cost + address_fee, 2)

            # Map SKUs to product IDs
            skus_detail = {}
            unmapped_skus = []

            for sku, qty in data.get("skus", {}).items():
                product_id = self.sku_map.get(sku)
                if product_id:
                    skus_detail[sku] = {"qty": qty, "product_id": product_id}
                else:
                    unmapped_skus.append(sku)
                    logger.warning(f"SKU '{sku}' not found in SKU map for brand '{brand}'")

            # Build order lines for Odoo
            order_lines = []

            # Product lines (all at $0.00)
            for sku, info in skus_detail.items():
                order_lines.append({
                    "product_id": info["product_id"],
                    "sku": sku,
                            "product_uom_qty": info["qty"],
                    "price_unit": 0.0,
                })

            # Logistics: freight by weight
            if total_weight_billed > 0:
                order_lines.append({
                    "product_id": LOGISTICS_WEIGHT_PRODUCT_ID,
                    "sku": "LOGISTICS-WEIGHT-KG",
                    "name": "Costo LogÃÂÃÂÃÂÃÂ­stico por Peso (por Kg)",
                    "product_uom_qty": total_weight_billed,
                    "price_unit": COST_PER_KG,
                })

            # Logistics: address fee
            if unique_orders > 0:
                order_lines.append({
                    "product_id": LOGISTICS_ADDRESS_FEE_PRODUCT_ID,
                    "sku": "LOGISTICS-ADDRESS-FEE",
                    "name": "Address Fee (por Orden)",
                    "product_uom_qty": unique_orders,
                    "price_unit": ADDRESS_FEE,
                })

            result[brand] = {
                "partner_id": partner_info["partner_id"],
                "partner_name": partner_info["partner_name"],
                "unique_orders": unique_orders,
                "boxes_detail": boxes_detail,
                "total_boxes": data.get("total_boxes", sum(d["count"] for d in boxes_detail.values())),
                "total_weight_raw": total_weight_raw,
                "total_weight_billed": total_weight_billed,
                "freight_cost": freight_cost,
                "address_fee": address_fee,
                "total_logistics": total_logistics,
                "skus": skus_detail,
                "total_skus_sold": data.get("total_skus_sold", sum(i["qty"] for i in skus_detail.values())),
                "unmapped_skus": unmapped_skus,
                "order_lines": order_lines,
                "tracking_numbers": data.get("tracking_numbers", []),
                "dispatch_date": data.get("dispatch_date"),
            }

            logger.info(
                f"  {brand}: weight={total_weight_raw}ÃÂÃÂ¢ÃÂÃÂÃÂÃÂ{total_weight_billed}kg, "
                f"freight=${freight_cost}, addr=${address_fee}, total=${total_logistics}"
            )

        return result
