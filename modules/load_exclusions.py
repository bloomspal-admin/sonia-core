"""Load additional excluded tracking numbers from text files."""
import os
import logging

logger = logging.getLogger(__name__)


def load_exclusions_from_files(conn):
    """Read tracking numbers from excluded_tracking_*.txt files and insert into excluded_shipments."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    loaded = 0
    for fname in sorted(os.listdir(base_dir)):
        if fname.startswith('excluded_tracking_') and fname.endswith('.txt'):
            filepath = os.path.join(base_dir, fname)
            try:
                with open(filepath, 'r') as f:
                    tracking_numbers = [line.strip() for line in f if line.strip()]
                if not tracking_numbers:
                    continue
                cursor = conn.cursor()
                for tn in tracking_numbers:
                    cursor.execute(
                        "INSERT INTO excluded_shipments (tracking_number, reason) VALUES (%s, 'claim') ON CONFLICT (tracking_number) DO NOTHING",
                        (tn,)
                    )
                conn.commit()
                loaded += len(tracking_numbers)
                logger.info(f"Loaded {len(tracking_numbers)} exclusions from {fname}")
            except Exception as e:
                logger.error(f"Error loading exclusions from {fname}: {e}")
                try:
                    conn.rollback()
                except:
                    pass
    return loaded
