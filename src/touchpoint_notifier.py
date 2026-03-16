"""
Slack notifier for touchpoint alerts.
Builds and sends Block Kit messages for overdue and today's touchpoints.
"""

import logging
from typing import Optional
from datetime import date, datetime

import requests

logger = logging.getLogger(__name__)


def _parse_follow_up_date(follow_up_by: Optional[str]) -> Optional[date]:
    """Parse follow_up_by string to date (handles ISO date or datetime)."""
    if not follow_up_by:
        return None
    try:
        return datetime.fromisoformat(follow_up_by.replace("Z", "+00:00")).date()
    except (ValueError, TypeError):
        return None


def _days_late(follow_up_by: Optional[str], today: date) -> Optional[int]:
    """Return days overdue, or None if not overdue or date invalid."""
    d = _parse_follow_up_date(follow_up_by)
    if not d:
        return None
    delta = (today - d).days
    return delta if delta > 0 else None


def _build_touchpoint_line(tp: dict, overdue: bool = False, today: Optional[date] = None) -> str:
    """Build a single touchpoint line for Slack mrkdwn."""
    name = tp.get("name", "(Untitled)")
    partner = tp.get("partner", "—")
    follow_up_by = tp.get("follow_up_by") or "—"
    if isinstance(follow_up_by, str) and "T" in follow_up_by:
        follow_up_by = follow_up_by.split("T")[0]

    parts = [f"• *{name}*", f"Partner: {partner}", f"Follow up by: {follow_up_by}"]
    if overdue and today:
        days = _days_late(tp.get("follow_up_by"), today)
        if days is not None:
            parts.append(f"({days} day{'s' if days != 1 else ''} late)")
    return " | ".join(parts)


def send_touchpoint_alerts(
    webhook_url: str,
    overdue: list[dict],
    today_list: list[dict],
    run_date: str,
) -> None:
    """
    Send a single Slack message with overdue and today's touchpoints.
    Does nothing if both lists are empty.
    """
    if not overdue and not today_list:
        logger.info("No touchpoint alerts to send.")
        return

    today_dt = date.today()
    blocks: list[dict] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"Touchpoint Report — {run_date}",
                "emoji": True,
            },
        },
        {"type": "divider"},
    ]

    if overdue:
        overdue_lines = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": ":rotating_light: *Overdue Touchpoints*\n"
                    + "\n".join(
                        _build_touchpoint_line(tp, overdue=True, today=today_dt)
                        for tp in overdue
                    ),
                },
            },
            {"type": "divider"},
        ]
        blocks.extend(overdue_lines)

    if today_list:
        today_lines = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": ":calendar: *Today's Touchpoints*\n"
                    + "\n".join(
                        _build_touchpoint_line(tp, overdue=False) for tp in today_list
                    ),
                },
            },
        ]
        blocks.extend(today_lines)

    payload = {"blocks": blocks}

    try:
        response = requests.post(webhook_url, json=payload, timeout=15)
        response.raise_for_status()
        logger.info(
            "Touchpoint Slack notification sent (overdue: %d, today: %d).",
            len(overdue),
            len(today_list),
        )
    except requests.RequestException as exc:
        logger.error("Failed to send touchpoint Slack notification: %s", exc)
        raise
