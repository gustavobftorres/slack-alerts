"""
Notion API client for querying the touchpoint database.
Uses REST API with requests (no SDK). Handles pagination and property parsing.
"""

import logging
from typing import Optional
import requests

logger = logging.getLogger(__name__)

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def _parse_title(prop: dict) -> str:
    """Extract plain text from a Notion title property."""
    if prop.get("type") != "title":
        return ""
    blocks = prop.get("title", [])
    return " ".join(b.get("plain_text", "") for b in blocks).strip()


def _parse_rich_text(prop: dict) -> str:
    """Extract plain text from a Notion rich_text property."""
    if prop.get("type") != "rich_text":
        return ""
    blocks = prop.get("rich_text", [])
    return " ".join(b.get("plain_text", "") for b in blocks).strip()


def _parse_date(prop: dict) -> Optional[str]:
    """Extract start date string from a Notion date property."""
    if prop.get("type") != "date":
        return None
    d = prop.get("date")
    if not d:
        return None
    return d.get("start")


def _parse_relation_ids(prop: dict) -> list[str]:
    """Extract page IDs from a Notion relation property."""
    if prop.get("type") != "relation":
        return []
    return [r["id"] for r in prop.get("relation", [])]


def _parse_people(prop: dict) -> list[str]:
    """Extract display names from a Notion people property."""
    if prop.get("type") != "people":
        return []
    return [
        p.get("name", "—")
        for p in prop.get("people", [])
        if p.get("name")
    ]


def _fetch_page_title(api_key: str, page_id: str) -> str:
    """Fetch a Notion page and return its title."""
    url = f"{NOTION_API_BASE}/pages/{page_id}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        props = data.get("properties", {})
        for prop_name, prop_val in props.items():
            if prop_val.get("type") == "title":
                return _parse_title(prop_val)
        return ""
    except requests.RequestException as exc:
        logger.warning("Failed to fetch page %s: %s", page_id, exc)
        return ""


def _parse_partner(api_key: str, prop: dict) -> str:
    """Extract partner display string from relation or rich_text."""
    if prop.get("type") == "rich_text":
        return _parse_rich_text(prop)
    if prop.get("type") == "relation":
        ids = _parse_relation_ids(prop)
        if not ids:
            return "—"
        title = _fetch_page_title(api_key, ids[0])
        return title or "—"
    return "—"


def _parse_touchpoint(api_key: str, page: dict) -> Optional[dict]:
    """Parse a Notion page (database row) into a touchpoint dict."""
    props = page.get("properties", {})
    name = ""
    partner = "—"
    follow_up_by = None
    attendees: list[str] = []

    for prop_name, prop_val in props.items():
        if not isinstance(prop_val, dict):
            continue
        ptype = prop_val.get("type")
        if ptype == "title" and prop_name == "Name":
            name = _parse_title(prop_val)
        elif ptype in ("relation", "rich_text") and prop_name == "Partner":
            partner = _parse_partner(api_key, prop_val)
        elif ptype == "date" and prop_name == "Follow up by":
            follow_up_by = _parse_date(prop_val)
        elif ptype == "people" and prop_name == "Attendees":
            attendees = _parse_people(prop_val)

    if not name:
        name = "(Untitled)"

    return {
        "name": name,
        "partner": partner,
        "follow_up_by": follow_up_by,
        "attendees": attendees,
    }


def query_touchpoints(
    api_key: str,
    database_id: str,
    filter_payload: Optional[dict] = None,
) -> list[dict]:
    """
    Query the Notion database and return parsed touchpoint dicts.

    Each touchpoint has: name, partner, follow_up_by (date string or None).

    Handles pagination automatically.
    """
    url = f"{NOTION_API_BASE}/databases/{database_id}/query"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }

    all_touchpoints: list[dict] = []
    cursor = None

    while True:
        body: dict = {}
        if filter_payload:
            body["filter"] = filter_payload
        if cursor:
            body["start_cursor"] = cursor

        try:
            resp = requests.post(url, headers=headers, json=body, timeout=15)
            if not resp.ok:
                try:
                    err_body = resp.json()
                    logger.error(
                        "Notion API error %s: %s",
                        resp.status_code,
                        err_body.get("message", err_body),
                    )
                except Exception:
                    logger.error("Notion API error %s: %s", resp.status_code, resp.text)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            logger.error("Notion API request failed: %s", exc)
            raise

        for page in data.get("results", []):
            tp = _parse_touchpoint(api_key, page)
            if tp:
                all_touchpoints.append(tp)

        cursor = data.get("next_cursor")
        if not cursor:
            break

    logger.info("Fetched %d touchpoint(s) from Notion", len(all_touchpoints))
    return all_touchpoints
