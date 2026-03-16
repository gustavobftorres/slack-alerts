"""
Touchpoint alert logic: fetch overdue and today's touchpoints from Notion.
"""

from datetime import date

from notion_client import query_touchpoints


def get_overdue_touchpoints(api_key: str, database_id: str) -> list[dict]:
    """
    Return touchpoints where Follow up by < today and Followed up = false.
    """
    today = date.today()
    today_str = today.isoformat()
    filter_payload = {
        "and": [
            {"property": "Follow up by", "date": {"before": today_str}},
            {"property": "Followed up", "checkbox": {"equals": False}},
        ]
    }
    return query_touchpoints(api_key, database_id, filter_payload)


def get_today_touchpoints(api_key: str, database_id: str) -> list[dict]:
    """
    Return touchpoints where Follow up by = today and Followed up = false.
    """
    today = date.today()
    today_str = today.isoformat()
    filter_payload = {
        "and": [
            {"property": "Follow up by", "date": {"equals": today_str}},
            {"property": "Followed up", "checkbox": {"equals": False}},
        ]
    }
    return query_touchpoints(api_key, database_id, filter_payload)
