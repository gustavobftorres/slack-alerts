import logging
from datetime import UTC, datetime

import requests

from alerts import Alert, AlertType

logger = logging.getLogger(__name__)

BALANCER_POOL_URL = "https://balancer.fi/pools/{chain_slug}/v{version}/{address}"

# Map API chain enum to Balancer URL slug (MAINNET -> ethereum, etc.)
CHAIN_TO_SLUG: dict[str, str] = {
    "MAINNET": "ethereum",
    "ARBITRUM": "arbitrum",
    "BASE": "base",
    "POLYGON": "polygon",
    "GNOSIS": "gnosis",
    "AVALANCHE": "avalanche",
    "OPTIMISM": "optimism",
}

ALERT_EMOJI = {
    AlertType.TVL_DROP: ":red_circle:",
    AlertType.TVL_SPIKE: ":large_green_circle:",
    AlertType.POOL_PAUSED: ":warning:",
}

ALERT_TITLE = {
    AlertType.TVL_DROP: "TVL Drop Alert",
    AlertType.TVL_SPIKE: "TVL Spike Alert",
    AlertType.POOL_PAUSED: "Pool Paused",
}


def _format_usd(value: float) -> str:
    if value >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    if value >= 1_000:
        return f"${value / 1_000:.1f}K"
    return f"${value:.2f}"


def _build_alert_block(alert: Alert) -> list[dict]:
    emoji = ALERT_EMOJI[alert.alert_type]
    title = ALERT_TITLE[alert.alert_type]
    chain = alert.chain.capitalize()
    version = getattr(alert, "version", 3)
    chain_slug = CHAIN_TO_SLUG.get(alert.chain, alert.chain.lower())
    pool_url = BALANCER_POOL_URL.format(
        chain_slug=chain_slug, version=version, address=alert.pool_address
    )

    header = f"{emoji} *{title}* — Balancer V{version}"
    pool_line = f"Pool: *<{pool_url}|{alert.pool_name}>* ({chain})"

    lines = [header, pool_line]

    if alert.alert_type in (AlertType.TVL_DROP, AlertType.TVL_SPIKE):
        lines.append(f"TVL yesterday:  {_format_usd(alert.previous_tvl_usd or 0)}")
        lines.append(f"TVL today:      {_format_usd(alert.current_tvl_usd)}")
        if alert.tvl_change_pct is not None:
            sign = "+" if alert.tvl_change_pct > 0 else ""
            lines.append(f"Change:         *{sign}{alert.tvl_change_pct * 100:.1f}%*")

    if alert.alert_type == AlertType.POOL_PAUSED:
        lines.append(f"Current TVL:    {_format_usd(alert.current_tvl_usd)}")
        lines.append("The pool has been paused since the last daily check.")

    return [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "\n".join(lines)},
        },
        {"type": "divider"},
    ]


def _build_summary_header(alert_count: int, run_date: str) -> list[dict]:
    return [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"Balancer Daily Report — {run_date}",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{alert_count} alert(s)* triggered in the last 24 hours.",
            },
        },
        {"type": "divider"},
    ]


def send_alerts(webhook_url: str, alerts: list[Alert]) -> None:
    """
    Send all triggered alerts as a single formatted Slack message.
    Does nothing if the alerts list is empty.
    """
    if not alerts:
        logger.info("No alerts to send.")
        return

    run_date = datetime.now(UTC).strftime("%Y-%m-%d")
    blocks: list[dict] = _build_summary_header(len(alerts), run_date)

    for alert in alerts:
        blocks.extend(_build_alert_block(alert))

    payload = {"blocks": blocks}

    try:
        response = requests.post(webhook_url, json=payload, timeout=15)
        response.raise_for_status()
        logger.info("Slack notification sent successfully (%d alerts).", len(alerts))
    except requests.RequestException as exc:
        logger.error("Failed to send Slack notification: %s", exc)
        raise
