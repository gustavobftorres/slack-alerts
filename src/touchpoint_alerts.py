"""
Touchpoint alert logic: fetch overdue and today's touchpoints from Notion.
"""

from datetime import date

from notion_client import query_touchpoints


def _base_filters() -> list[dict]:
    """Filters applied to both overdue and today queries."""
    return [
        {"property": "Followed up", "checkbox": {"equals": False}},
        {"property": "Type", "select": {"does_not_equal": "Call"}},
    ]


def get_overdue_touchpoints(api_key: str, database_id: str) -> list[dict]:
    """
    Return touchpoints where Follow up by < today, Followed up = false, Type != Call.
    """
    today = date.today()
    today_str = today.isoformat()
    filter_payload = {
        "and": [
            {"property": "Follow up by", "date": {"before": today_str}},
            *_base_filters(),
        ]
    }
    return query_touchpoints(api_key, database_id, filter_payload)


def get_today_touchpoints(api_key: str, database_id: str) -> list[dict]:
    """
    Return touchpoints where Follow up by = today, Followed up = false, Type != Call.
    """
    today = date.today()
    today_str = today.isoformat()
    filter_payload = {
        "and": [
            {"property": "Follow up by", "date": {"equals": today_str}},
            *_base_filters(),
        ]
    }
    return query_touchpoints(api_key, database_id, filter_payload)
