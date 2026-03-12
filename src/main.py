import json
import logging
import os
import sys
from pathlib import Path

import yaml

from alerts import check_alerts
from balancer_api import fetch_pools
from slack_notifier import send_alerts

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def load_snapshot(snapshot_path: Path) -> dict:
    if not snapshot_path.exists() or snapshot_path.stat().st_size == 0:
        logger.info("No previous snapshot found at %s — first run.", snapshot_path)
        return {}
    with open(snapshot_path) as f:
        return json.load(f)


def save_snapshot(snapshot_path: Path, pools: list[dict]) -> None:
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    data = {pool["id"]: pool for pool in pools}
    with open(snapshot_path, "w") as f:
        json.dump(data, f, indent=2)
    logger.info("Snapshot saved to %s (%d pools).", snapshot_path, len(pools))


def main() -> None:
    config = load_config()

    slack_webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not slack_webhook_url:
        logger.error("SLACK_WEBHOOK_URL environment variable is not set.")
        sys.exit(1)

    api_url: str = config["api_url"]
    chains: list[str] = config["chains"]
    snapshot_path = Path(__file__).parent.parent / config["snapshot_path"]

    alert_config = config["alerts"]
    tvl_drop_threshold: float = alert_config["tvl_drop_threshold"]
    tvl_spike_threshold: float = alert_config["tvl_spike_threshold"]
    min_tvl_usd: float = alert_config["min_tvl_usd"]

    logger.info("Fetching Balancer V3 pools for chains: %s", chains)
    current_pools = fetch_pools(api_url, chains)

    previous_snapshot = load_snapshot(snapshot_path)

    triggered_alerts = check_alerts(
        current_pools=current_pools,
        previous_snapshot=previous_snapshot,
        tvl_drop_threshold=tvl_drop_threshold,
        tvl_spike_threshold=tvl_spike_threshold,
        min_tvl_usd=min_tvl_usd,
    )

    send_alerts(slack_webhook_url, triggered_alerts)

    save_snapshot(snapshot_path, current_pools)

    logger.info("Daily check complete. %d alert(s) sent.", len(triggered_alerts))


if __name__ == "__main__":
    main()
