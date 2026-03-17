import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)

V3_POOLS_QUERY = """
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

V2_V3_POOLS_QUERY = """
query GetPools($chains: [GqlChain!]!) {
  poolGetPools(
    where: { protocolVersionIn: [2, 3], chainIn: $chains }
    first: 2000
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

V2_SUBGRAPH_QUERY = """
query GetV2Pools($addresses: [Bytes!]!) {
  pools(where: { address_in: $addresses }) {
    id
    address
    name
    totalLiquidity
    swapEnabled
  }
}
"""


def _normalize_pool(pool: dict) -> dict[str, Any]:
    """Convert raw API/subgraph pool to unified format."""
    dynamic = pool.get("dynamicData") or {}
    return {
        "id": pool.get("id") or pool.get("address", ""),
        "name": pool.get("name", "Unknown"),
        "address": pool.get("address", ""),
        "chain": pool.get("chain", ""),
        "total_liquidity_usd": float(dynamic.get("totalLiquidity") or pool.get("totalLiquidity") or 0),
        "is_paused": bool(
            dynamic.get("isPaused", False) if "dynamicData" in pool else not pool.get("swapEnabled", True)
        ),
    }


def fetch_pools(api_url: str, chains: list[str]) -> list[dict[str, Any]]:
    """
    Fetch all Balancer V3 pools for the given chains from the API.
    Returns a flat list of pool dicts with fields:
      id, name, address, chain, total_liquidity_usd, is_paused
    """
    payload = {
        "query": V3_POOLS_QUERY,
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

    return [_normalize_pool(p) for p in raw_pools]


def fetch_pools_by_ids(
    api_url: str,
    pool_descriptors: list[dict[str, Any]],
    chains: list[str],
) -> list[dict[str, Any]]:
    """
    Fetch Balancer v2 and v3 pools from the API, filtered to only include
    pools matching the given descriptors (address, chain, version).

    pool_descriptors: list of dicts with keys address, chain, version
    Returns pool dicts with id, name, address, chain, total_liquidity_usd, is_paused, version
    """
    if not pool_descriptors:
        return []

    wanted = {(d["address"].lower(), d["chain"]) for d in pool_descriptors}
    version_by_key = {(d["address"].lower(), d["chain"]): d["version"] for d in pool_descriptors}
    name_by_key = {(d["address"].lower(), d["chain"]): d.get("name", "Unknown") for d in pool_descriptors}

    payload = {
        "query": V2_V3_POOLS_QUERY,
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
    pools: list[dict[str, Any]] = []

    for pool in raw_pools:
        addr = (pool.get("address") or "").lower()
        chain = pool.get("chain", "")
        key = (addr, chain)
        if key not in wanted:
            continue
        normalized = _normalize_pool(pool)
        normalized["version"] = version_by_key.get(key, 3)
        if name_by_key.get(key) and name_by_key[key] != "Unknown":
            normalized["name"] = name_by_key[key]
        pools.append(normalized)

    logger.info("Fetched %d matching pool(s) from Balancer API (v2+v3)", len(pools))
    return pools


def fetch_v2_pools_subgraph(
    subgraph_url: str,
    addresses: list[str],
    chain: str = "MAINNET",
) -> list[dict[str, Any]]:
    """
    Fetch v2 pool data from the Balancer v2 subgraph.
    Used as fallback when pools are not found in the V3 API.

    Note: The default subgraph URL is Ethereum-only. For other chains,
    use the appropriate chain-specific subgraph URL.
    """
    if not addresses:
        return []

    # Subgraph expects checksummed or lowercase addresses
    addrs = [a.lower() if a.startswith("0x") else a for a in addresses]

    payload = {
        "query": V2_SUBGRAPH_QUERY,
        "variables": {"addresses": addrs},
    }

    try:
        response = requests.post(
            subgraph_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.error("Failed to fetch v2 pools from subgraph: %s", exc)
        raise

    body = response.json()
    if "errors" in body:
        logger.error("V2 subgraph returned errors: %s", body["errors"])
        raise ValueError(f"GraphQL errors: {body['errors']}")

    raw_pools = body.get("data", {}).get("pools", [])
    pools: list[dict[str, Any]] = []

    for pool in raw_pools:
        addr = pool.get("address", "")
        pools.append({
            "id": pool.get("id", addr),
            "name": pool.get("name", "Unknown"),
            "address": addr,
            "chain": chain,
            "total_liquidity_usd": float(pool.get("totalLiquidity") or 0),
            "is_paused": not bool(pool.get("swapEnabled", True)),
            "version": 2,
        })

    logger.info("Fetched %d v2 pool(s) from subgraph", len(pools))
    return pools
