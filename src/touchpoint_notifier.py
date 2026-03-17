"""
Slack notifier for touchpoint alerts.
Builds and sends Block Kit messages for overdue and today's touchpoints.
Groups touchpoints by Attendees so each BD sees their tasks.
"""

import logging
from collections import defaultdict
from typing import Optional

from datetime import date, datetime

import requests

logger = logging.getLogger(__name__)

UNASSIGNED = "Unassigned"


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


def _group_by_attendee(touchpoints: list[dict]) -> dict[str, list[dict]]:
    """Group touchpoints by attendee. If multiple attendees, include under each."""
    grouped: dict[str, list[dict]] = defaultdict(list)
    for tp in touchpoints:
        attendees = tp.get("attendees") or []
        if not attendees:
            grouped[UNASSIGNED].append(tp)
        else:
            for attendee in attendees:
                grouped[attendee].append(tp)
    return dict(grouped)


def _build_section_by_attendee(
    touchpoints: list[dict],
    section_title: str,
    emoji: str,
    overdue: bool = False,
    today: Optional[date] = None,
) -> list[dict]:
    """Build Slack blocks for a section, grouped by attendee."""
    grouped = _group_by_attendee(touchpoints)
    parts: list[str] = [f"{emoji} *{section_title}"]

    for attendee in sorted(grouped.keys(), key=lambda x: (x == UNASSIGNED, x)):
        items = grouped[attendee]
        parts.append(f" - {attendee}")
        for tp in items:
            parts.append(_build_touchpoint_line(tp, overdue=overdue, today=today))
        parts.append("")  # blank line between attendees

    text = "\n".join(parts).rstrip()
    return [{"type": "section", "text": {"type": "mrkdwn", "text": text}}]


def send_touchpoint_alerts(
    webhook_url: str,
    overdue: list[dict],
    today_list: list[dict],
    run_date: str,
) -> None:
    """
    Send a single Slack message with overdue and today's touchpoints.
    Groups by Attendees so each BD sees their tasks.
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
        overdue_blocks = _build_section_by_attendee(
            overdue,
            section_title="Overdue Touchpoints",
            emoji=":rotating_light:",
            overdue=True,
            today=today_dt,
        )
        blocks.extend(overdue_blocks)
        blocks.append({"type": "divider"})

    if today_list:
        today_blocks = _build_section_by_attendee(
            today_list,
            section_title="Today's Touchpoints",
            emoji=":calendar:",
            overdue=False,
        )
        blocks.extend(today_blocks)

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
