"""
Box type - GROSS WEIGHT reference table.
Maps box types from warehouse reports to their GROSS WEIGHT in kilograms.
GROSS WEIGHT = weight of box + products inside (as shipped).
Data source: Bloomspal Data.xlsx "Cajas" sheet, column "GROSS WEIGHT EN KILOS".
"""
import logging

logger = logging.getLogger(__name__)

# Box Type -> GROSS WEIGHT (kg) - weight of the full box as shipped
# Keys: box name as it appears in warehouse Excel files.
BOX_WEIGHTS: dict[str, float] = {
    "CAJA MASTER 1830 COFFEE": 1.0,    # 1830 Coffee
    "CAJA MASTER BAOBAB": 1.0,         # Baobab
    "CAJA MASTER BEBLISS": 1.0,        # Bebliss
    "CAJA MASTER BLOOMSPAL": 1.0,      # Bloomspal
    "CAJA MASTER BCC": 1.0,            # Boterro Coffee Club
    "CAJA MASTER CBTB": 1.0,           # Coffee by the Bag
    "CAJA GRANDE": 1.65,               # Dios Mio Coffee
    "CAJA MEDIANA": 1.65,              # Dios Mio Coffee
    "CAJA PEQUE\u00d1A": 1.0,          # Dios Mio Coffee
    "CAJA KIT": 3.0,                   # Dios Mio Coffee
    "CAJA MASTER DON MAIZ": 3.19,      # Don Maiz
    "CAJA MASTER": 1.0,                # Eden flowers
    "BOLSA FEDEX": 1.0,                # Eden flowers
    "CAJA MASTER GAVI": 1.0,           # GAVI
    "CAJA PROPIA HACIENDA VENECIA": 1.51,  # Hacienda Venecia
    "CAJA MASTER THG": 1.0,            # The Hair Generation
    "CAJA CARTON COSMETIQUERA THG": 2.0,   # The Hair Generation
}

# Default weight if box type not found
DEFAULT_BOX_WEIGHT = 1.0  # kg

# Freight pricing
COST_PER_KG = 6.5   # USD per kg for International Freight
ADDRESS_FEE = 8.0    # USD per unique order/address


def get_box_weight(box_type: str, db_weights: dict = None) -> float:
    """
    Get the GROSS WEIGHT for a box type.
    Priority: 1) DB weights, 2) BOX_WEIGHTS dict, 3) case-insensitive match, 4) default.
    """
    if db_weights and box_type in db_weights:
        return db_weights[box_type]

    # Try exact match
    if box_type in BOX_WEIGHTS:
        return BOX_WEIGHTS[box_type]

    # Try case-insensitive match
    box_upper = box_type.upper().strip()
    for key, weight in BOX_WEIGHTS.items():
        if key.upper() == box_upper:
            return weight

    # Try partial match (e.g., "CAJA PEQUE" matches "CAJA PEQUEÑA")
    for key, weight in BOX_WEIGHTS.items():
        if box_upper in key.upper() or key.upper() in box_upper:
            return weight

    logger.warning(f"Unknown box type: '{box_type}', using default {DEFAULT_BOX_WEIGHT} kg")
    return DEFAULT_BOX_WEIGHT
