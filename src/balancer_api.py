import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)

POOLS_QUERY = """
query GetV3Pools($chains: [GqlChain!]!) {
  poolGetPools(
    where: { protocolVersionIn: [3], chainIn: $chains }
    first: 1000
  ) {
    id
    name
    address
    chain
    dynamicData {
      totalLiquidity
      isPaused
    }
  }
}
"""


def fetch_pools(api_url: str, chains: list[str]) -> list[dict[str, Any]]:
    """
    Fetch all Balancer V3 pools for the given chains from the API.
    Returns a flat list of pool dicts with fields:
      id, name, address, chain, total_liquidity_usd, is_paused
    """
    payload = {
        "query": POOLS_QUERY,
        "variables": {"chains": chains},
    }

    try:
        response = requests.post(
            api_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=60,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.error("Failed to fetch pools from Balancer API: %s", exc)
        raise

    body = response.json()

    if "errors" in body:
        logger.error("Balancer API returned errors: %s", body["errors"])
        raise ValueError(f"GraphQL errors: {body['errors']}")

    raw_pools = body.get("data", {}).get("poolGetPools", [])
    logger.info("Fetched %d pools from Balancer V3 API", len(raw_pools))

    pools = []
    for pool in raw_pools:
        dynamic = pool.get("dynamicData") or {}
        pools.append(
            {
                "id": pool["id"],
                "name": pool.get("name", "Unknown"),
                "address": pool.get("address", ""),
                "chain": pool.get("chain", ""),
                "total_liquidity_usd": float(dynamic.get("totalLiquidity") or 0),
                "is_paused": bool(dynamic.get("isPaused", False)),
            }
        )

    return pools
