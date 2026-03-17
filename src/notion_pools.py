"""
Notion API client for querying the pools database.
Parses pool URLs to extract address, chain, and version for Balancer v2/v3 monitoring.
"""

import logging
import re
from typing import Optional

import requests

logger = logging.getLogger(__name__)

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

# Balancer pool URL pattern:
# - https://balancer.fi/pools/{chain}/{version}/{address}
# - https://test.balancer.fi/pools/{chain}/{version}/{address}
BALANCER_POOL_URL_PATTERN = re.compile(
    r"https?://(?:[a-zA-Z0-9-]+\.)?balancer\.fi/pools/([^/]+)/(v[23])/(0x[a-fA-F0-9]{40})"
)

CHAIN_SLUG_TO_API: dict[str, str] = {
    "ethereum": "MAINNET",
    "arbitrum": "ARBITRUM",
    "base": "BASE",
    "polygon": "POLYGON",
    "gnosis": "GNOSIS",
    "avalanche": "AVALANCHE",
    "optimism": "OPTIMISM",
    "hyperevm": "HYPEREVM",
    "plasma": "PLASMA",
    "monad": "MONAD",
}


def _parse_title(prop: dict) -> str:
    """Extract plain text from a Notion title property."""
    if prop.get("type") != "title":
        return ""
    blocks = prop.get("title", [])
    return " ".join(b.get("plain_text", "") for b in blocks).strip()


def _parse_url(prop: dict) -> str:
    """Extract URL string from a Notion url property."""
    if prop.get("type") != "url":
        return ""
    return (prop.get("url") or "").strip()


def _parse_select_or_status(prop: dict) -> str:
    """Extract selected value from a Notion select or status property."""
    if prop.get("type") == "select":
        sel = prop.get("select")
        return sel.get("name", "") if sel else ""
    if prop.get("type") == "status":
        st = prop.get("status")
        return st.get("name", "") if st else ""
    return ""


def _parse_pool_url(url: str) -> Optional[dict]:
    """
    Parse a Balancer pool URL into address, chain (API enum), and version.

    Returns dict with keys: address, chain, version (2 or 3), or None if unparseable.
    """
    if not url:
        return None
    match = BALANCER_POOL_URL_PATTERN.search(url)
    if not match:
        return None
    chain_slug, version_str, address = match.groups()
    chain_slug = chain_slug.lower()
    chain = CHAIN_SLUG_TO_API.get(chain_slug)
    if not chain:
        logger.warning("Unknown chain slug in URL %s: %s", url, chain_slug)
        return None
    version = 3 if version_str == "v3" else 2
    return {
        "address": address,
        "chain": chain,
        "version": version,
    }


def _parse_pool_row(page: dict) -> Optional[dict]:
    """Parse a Notion database row into a pool descriptor."""
    props = page.get("properties", {})
    name = ""
    url_str = ""
    status = ""

    for prop_name, prop_val in props.items():
        if not isinstance(prop_val, dict):
            continue
        ptype = prop_val.get("type")
        if ptype == "title" and prop_name == "Name":
            name = _parse_title(prop_val)
        elif ptype == "url" and prop_name == "Url":
            url_str = _parse_url(prop_val)
        elif ptype in ("select", "status") and prop_name == "Status":
            status = _parse_select_or_status(prop_val)

    parsed = _parse_pool_url(url_str)
    if not parsed:
        logger.warning("Skipping row (unparseable URL): name=%r url=%r", name, url_str)
        return None

    return {
        "address": parsed["address"],
        "chain": parsed["chain"],
        "version": parsed["version"],
        "name": name or "(Untitled)",
        "status": status,
    }


def query_pool_list(
    api_key: str,
    database_id: str,
    filter_payload: Optional[dict] = None,
) -> list[dict]:
    """
    Query the Notion pools database and return parsed pool descriptors.

    Each descriptor has: address, chain (API enum), version (2 or 3), name, status.

    Handles pagination automatically. Skips rows with unparseable URLs.
    """
    url = f"{NOTION_API_BASE}/databases/{database_id}/query"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }

    all_pools: list[dict] = []
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
            pool = _parse_pool_row(page)
            if pool:
                all_pools.append(pool)

        cursor = data.get("next_cursor")
        if not cursor:
            break

    logger.info("Fetched %d pool(s) from Notion", len(all_pools))
    return all_pools
