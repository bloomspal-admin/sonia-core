"""
Box type → weight reference table.
Maps box types used in warehouse reports to their weight in kilograms.

NOTE: These values need to be confirmed with the warehouse team.
Update the BOX_WEIGHTS dict with actual box types from the Excel reports.
"""
import logging

logger = logging.getLogger(__name__)

# ─── Box Type → Weight (kg) ──────────────────────────────────────
# Keys should match exactly the box type names in the warehouse Excel files.
# TODO: Danny needs to provide the actual box types and their weights.
#       Below are placeholder examples that must be replaced.
BOX_WEIGHTS: dict[str, float] = {
    # "BoxTypeName": weight_in_kg
    "HB": 12.0,       # Half Box (placeholder)
    "QB": 6.0,        # Quarter Box (placeholder)
    "EB": 4.0,        # Eighth Box (placeholder)
    "FB": 24.0,       # Full Box (placeholder)
    # Add more as they appear in the Excel files
}

# Default weight if box type is not found (kg)
DEFAULT_BOX_WEIGHT_KG = 10.0


def get_box_weight(box_type: str) -> float:
    """
    Get the weight in kg for a given box type.
    Returns DEFAULT_BOX_WEIGHT_KG if box type is unknown.
    """
    weight = BOX_WEIGHTS.get(box_type)
    if weight is None:
        # Try case-insensitive match
        for key, val in BOX_WEIGHTS.items():
            if key.lower() == box_type.lower():
                return val
        logger.warning(
            f"Unknown box type '{box_type}', using default {DEFAULT_BOX_WEIGHT_KG} kg. "
            f"Please add this box type to box_weights.py"
        )
        return DEFAULT_BOX_WEIGHT_KG
    return weight


def calculate_total_weight(boxes: list[dict]) -> float:
    """
    Calculate total weight from a list of boxes.
    Each box dict should have 'box_type' and optionally 'quantity' keys.
    """
    total = 0.0
    for box in boxes:
        box_type = box.get("box_type", "")
        quantity = box.get("quantity", 1)
        weight = get_box_weight(box_type)
        total += weight * quantity
    return total
