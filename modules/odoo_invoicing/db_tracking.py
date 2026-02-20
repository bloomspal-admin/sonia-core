"""
Database tracking module (v2) - Tracks processed cortes (warehouse reports)
Manages tables in SonIA Core DB (Railway PostgreSQL) to avoid duplicate invoicing.

Changed from v1: Now tracks by corte_id instead of order_id.
"""
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
from typing import List, Set, Optional
import logging

logger = logging.getLogger(__name__)

