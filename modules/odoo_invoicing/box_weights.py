"""
Box type → weight reference table.
Maps box types from warehouse reports to their weight in kilograms.
Data source: Bloomspal Data.xlsx "Cajas" sheet.
"""
import logging

logger = logging.getLogger(__name__)

# ——— Box Type → Weight (kg) ——————————————————————————————————————
# Keys: box name as it appears in warehouse Excel files.
BOX_WEIGHTS: dict[str, float] = {
    "CAJA MASTER 1830 COFFEE": 0.068,  # 1830 Coffee
    "CAJA MASTER BAOBAB": 0.12,  # Baobab
    "CAJA MASTER BEBLISS": 0.12,  # Bebliss
    "CAJA MASTER BLOOMSPAL": 0.118,  # Bloomspal
    "CAJA BLOOMSPAL (NO TENER EN CUENTA)": 0.118,  # Bloomspal
    "CAJA MASTER BCC": 0.12,  # Boterro Coffee Club
    "CAJA MASTER CBTB": 0.12,  # Coffee by the Bag
    "CAJA GRANDE": 0.139,  # Dios Mio Coffee
    "CAJA MEDIANA": 0.136,  # Dios Mio Coffee
    "CAJA PEQUEÃ‘A": 0.092,  # Dios Mio Coffee
    "CAJA KIT": 2.348,  # Dios Mio Coffee
    "CAJA MASTER DON MAIZ": 0.2,  # Don Maiz
    "CAJA MASTER": 0.12,  # Eden flowers
    "Bolsa FedEx": 0.028,  # Eden flowers
    "Bolsa FedEx": 0.028,  # Eden flowers
    "CAJA MASTER GAVI": 0.219,  # GAVI
    "CAJA PROPIA HACIENDA VENECIA": 0.3,  # Hacienda Venecia
    "CAJA MASTER THG": 0.12,  # The Hair Generation
    "CAJA CARTON COSMETIQUERA THG (No tener en cuenta)": 0.1595,  # The Hair Generation
}

# Freight cost per box type (USD)
BOX_FREIGHT_COSTS: dict[str, float] = {
    "CAJA MASTER 1830 COFFEE": 4.0,
    "CAJA MASTER BAOBAB": 4.0,
    "CAJA MASTER BEBLISS": 4.0,
    "CAJA MASTER BLOOMSPAL": 4.0,
    "CAJA BLOOMSPAL (NO TENER EN CUENTA)": 4.0,
    "CAJA MASTER BCC": 4.0,
    "CAJA MASTER CBTB": 4.0,
    "CAJA GRANDE": 6.0,
    "CAJA MEDIANA": 6.0,
    "CAJA PEQUEÃ‘A": 4.0,
    "CAJA KIT": 12.0,
    "CAJA MASTER DON MAIZ": 5.0,
    "CAJA MASTER": 4.0,
    "Bolsa FedEx": 5.0,
    "Bolsa FedEx": 5.0,
    "CAJA MASTER GAVI": 5.0,
    "CAJA PROPIA HACIENDA VENECIA": 5.0,
    "CAJA MASTER THG": 4.0,
    "CAJA CARTON COSMETIQUERA THG (No tener en cuenta)": 5.0,
}

# Default weight if box type not found
DEFAULT_BOX_WEIGHT = 0.12  # kg (typical master box)

# ——— Freight pricing ————————————————————————————————————————
COST_PER_KG = 6.5   # USD per kg for International Freight
ADDRESS_FEE = 8.0    # USD per unique order/address


import math

def round_freight_weight(weight_kg: float) -> float:
    """
    Round weight for freight billing per BloomsPal rules:
    - Less than 1 kg → billed as 1 kg
    - 1 kg or more → round UP to the next 0.5 kg
      Examples: 2.3 → 2.5, 2.5 → 2.5, 2.6 → 3.0, 3.0 → 3.0
    """
    if weight_kg <= 0:
        return 0.0
    if weight_kg < 1.0:
        return 1.0
    # Round up to next 0.5
    return math.ceil(weight_kg * 2) / 2


def get_box_weight(box_type: str, db_weights: dict = None) -> float:
    """
    Get the weight for a box type.
    Priority: 1) DB weights, 2) BOX_WEIGHTS dict, 3) default.
    """
    if db_weights and box_type in db_weights:
        return db_weights[box_type]

    # Try exact match
    if box_type in BOX_WEIGHTS:
        return BOX_WEIGHTS[box_type]

    # Try case-insensitive partial match
    box_lower = box_type.lower()
    for key, weight in BOX_WEIGHTS.items():
        if box_lower in key.lower() or key.lower() in box_lower:
            return weight

    logger.warning(f"Unknown box type: '{box_type}', using default {DEFAULT_BOX_WEIGHT} kg")
    return DEFAULT_BOX_WEIGHT
