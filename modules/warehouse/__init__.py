"""
SonIA Core — Warehouse Processing Module
Parses warehouse Excel files and creates sale orders in Odoo.
"""

from .parser import WarehouseParser
from .processor import WarehouseProcessor
from .odoo_creator import OdooSaleOrderCreator

__all__ = ["WarehouseParser", "WarehouseProcessor", "OdooSaleOrderCreator"]
