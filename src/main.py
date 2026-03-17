import json
import logging
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

from alerts import check_alerts
from balancer_api import fetch_pools_by_ids, fetch_v2_pools_subgraph
from notion_pools import query_pool_list
from slack_notifier import send_alerts

load_dotenv()

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

    notion_api_key = os.environ.get("NOTION_API_KEY")
    notion_pools_db_id = os.environ.get("NOTION_POOLS_DB_ID")
    if not notion_api_key or not notion_pools_db_id:
        logger.error("NOTION_API_KEY and NOTION_POOLS_DB_ID environment variables must be set.")
        sys.exit(1)

    api_url: str = config["api_url"]
    chains: list[str] = config["chains"]
    snapshot_path = Path(__file__).parent.parent / config["snapshot_path"]
    v2_subgraph_url = (
        os.environ.get("BALANCER_V2_SUBGRAPH")
        or "https://api.studio.thegraph.com/query/24660/balancer-ethereum-v2/version/latest"
    )

    alert_config = config["alerts"]
    tvl_drop_threshold: float = alert_config["tvl_drop_threshold"]
    tvl_spike_threshold: float = alert_config["tvl_spike_threshold"]
    min_tvl_usd: float = alert_config["min_tvl_usd"]

    logger.info("Fetching pool list from Notion")
    pool_descriptors = query_pool_list(notion_api_key, notion_pools_db_id)
    if not pool_descriptors:
        logger.warning("No pools found in Notion database. Exiting.")
        sys.exit(0)

    logger.info("Fetching pool data from Balancer API (v2+v3)")
    current_pools = fetch_pools_by_ids(api_url, pool_descriptors, chains)

    # Fallback: v2 pools not found in API — fetch from v2 subgraph (Ethereum-only)
    found_keys = {(p["address"].lower(), p["chain"]) for p in current_pools}
    v2_mainnet_missing = [
        d for d in pool_descriptors
        if d["version"] == 2
        and d["chain"] == "MAINNET"
        and (d["address"].lower(), d["chain"]) not in found_keys
    ]
    if v2_mainnet_missing:
        mainnet_addresses = [d["address"] for d in v2_mainnet_missing]
        logger.info("Fetching %d v2 pool(s) from subgraph (API fallback)", len(mainnet_addresses))
        try:
            v2_pools = fetch_v2_pools_subgraph(v2_subgraph_url, mainnet_addresses, chain="MAINNET")
            for p in v2_pools:
                p["name"] = next(
                    (d["name"] for d in v2_mainnet_missing if d["address"].lower() == p["address"].lower()),
                    p["name"],
                )
            current_pools.extend(v2_pools)
        except Exception as exc:
            logger.warning("V2 subgraph fallback failed (skipping): %s", exc)

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
