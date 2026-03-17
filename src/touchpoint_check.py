"""
Entry point for touchpoint alerts.
Runs Monday summary (overdue + today) or daily (today only) based on weekday.
"""

import logging
import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    force=True,
)
logger = logging.getLogger(__name__)

from touchpoint_alerts import get_overdue_touchpoints, get_today_touchpoints
from touchpoint_notifier import send_touchpoint_alerts


def main() -> None:
    slack_webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    notion_api_key = os.environ.get("NOTION_API_KEY")
    notion_db_id = os.environ.get("NOTION_TOUCHPOINT_DB_ID")

    if not slack_webhook_url:
        logger.error("SLACK_WEBHOOK_URL environment variable is not set.")
        sys.exit(1)
    if not notion_api_key:
        logger.error("NOTION_API_KEY environment variable is not set.")
        sys.exit(1)
    if not notion_db_id:
        logger.error("NOTION_TOUCHPOINT_DB_ID environment variable is not set.")
        sys.exit(1)

    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    force_monday = "--monday" in sys.argv
    is_monday = datetime.now(timezone.utc).weekday() == 0 or force_monday

    if force_monday:
        logger.info("Running in Monday mode (--monday flag).")

    overdue: list[dict] = []
    if is_monday:
        logger.info("Monday run: fetching overdue and today's touchpoints.")
        overdue = get_overdue_touchpoints(notion_api_key, notion_db_id)
    else:
        logger.info("Daily run: fetching today's touchpoints only.")

    today_list = get_today_touchpoints(notion_api_key, notion_db_id)

    send_touchpoint_alerts(slack_webhook_url, overdue, today_list, run_date)
    logger.info("Touchpoint check complete.")


if __name__ == "__main__":
    main()
