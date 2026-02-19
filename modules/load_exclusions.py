"""Load additional excluded tracking numbers from text files. Uses strike system for unknowns."""
import os
import logging

logger = logging.getLogger(__name__)

STRIKE_THRESHOLD = 3  # Number of consecutive unknown appearances before excluding

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

    # Strike system for unknown shipments
    try:
        cursor = conn.cursor()

        # Step 1: Get all currently unknown tracking numbers (not already excluded)
        cursor.execute("""
            SELECT s.tracking_number
            FROM shipments s
            WHERE s.sonia_status = 'unknown'
            AND s.tracking_number NOT IN (SELECT tracking_number FROM excluded_shipments)
        """)
        current_unknowns = set(row[0] for row in cursor.fetchall())

        if current_unknowns:
            # Step 2: Upsert strikes - increment for current unknowns
            for tn in current_unknowns:
                cursor.execute("""
                    INSERT INTO unknown_tracking_strikes (tracking_number, strike_count, first_seen_at, last_seen_at)
                    VALUES (%s, 1, NOW(), NOW())
                    ON CONFLICT (tracking_number) DO UPDATE SET
                        strike_count = unknown_tracking_strikes.strike_count + 1,
                        last_seen_at = NOW()
                """, (tn,))

            # Step 3: Reset strikes for tracking numbers that are NO LONGER unknown
            # (they resolved to a valid status - false positive confirmed)
            cursor.execute("""
                DELETE FROM unknown_tracking_strikes
                WHERE tracking_number NOT IN (
                    SELECT tracking_number FROM shipments WHERE sonia_status = 'unknown'
                )
            """)
            resolved_count = cursor.rowcount
            if resolved_count > 0:
                logger.info(f"Cleared {resolved_count} strikes for resolved tracking numbers")

            # Step 4: Exclude tracking numbers that hit the threshold
            cursor.execute("""
                INSERT INTO excluded_shipments (tracking_number, reason)
                SELECT tracking_number, 'unknown_status_3strikes'
                FROM unknown_tracking_strikes
                WHERE strike_count >= %s
                AND tracking_number NOT IN (SELECT tracking_number FROM excluded_shipments)
            """, (STRIKE_THRESHOLD,))
            excluded_count = cursor.rowcount

            # Step 5: Clean up strikes for newly excluded ones
            if excluded_count > 0:
                cursor.execute("""
                    DELETE FROM unknown_tracking_strikes
                    WHERE tracking_number IN (SELECT tracking_number FROM excluded_shipments)
                """)
                loaded += excluded_count
                logger.info(f"Excluded {excluded_count} shipments after {STRIKE_THRESHOLD} strikes")

            conn.commit()

            # Log strike summary
            cursor.execute("SELECT COUNT(*), MAX(strike_count) FROM unknown_tracking_strikes")
            row = cursor.fetchone()
            pending_count = row[0] or 0
            max_strikes = row[1] or 0
            if pending_count > 0:
                logger.info(f"Strike status: {pending_count} tracking numbers pending ({max_strikes} max strikes)")
        else:
            logger.info("No unknown shipments found for strike processing")

    except Exception as e:
        logger.warning(f"Could not process unknown shipment strikes: {e}")
        try:
            conn.rollback()
        except:
            pass

    return loaded
