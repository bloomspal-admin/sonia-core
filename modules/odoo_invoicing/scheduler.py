"""
Scheduler - Runs daily_invoicing on working days (Mon-Fri).
Can also be triggered manually via command line.

Usage:
  python scheduler.py          # Run the scheduler (waits for next cron time)
  python scheduler.py --now    # Run immediately (manual trigger)
  python daily_invoicing.py    # Run immediately (direct execution)
"""
import schedule
import time
import sys
import logging
from datetime import datetime
from .daily_invoicing import run_daily_invoicing

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("scheduler")


def is_working_day() -> bool:
    """Check if today is a working day (Mon-Fri)."""
    return datetime.now().weekday() < 5  # 0=Mon, 4=Fri


def scheduled_run():
    """Run invoicing only on working days."""
    if is_working_day():
        logger.info("Working day detected. Starting daily invoicing...")
        try:
            run_daily_invoicing()
        except Exception as e:
            logger.error(f"Daily invoicing failed: {e}", exc_info=True)
    else:
        logger.info("Weekend - skipping invoicing.")


def main():
    if "--now" in sys.argv:
        logger.info("Manual trigger: running immediately")
        run_daily_invoicing()
        return

    # Schedule for 6:00 AM daily (Mon-Fri check happens inside)
    schedule.every().day.at("06:00").do(scheduled_run)
    logger.info("Scheduler started. Daily invoicing set for 06:00 AM on working days.")
    logger.info("Use --now flag to run immediately.")

    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    main()
