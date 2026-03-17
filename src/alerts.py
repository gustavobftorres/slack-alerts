import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class AlertType(str, Enum):
    TVL_DROP = "tvl_drop"
    TVL_SPIKE = "tvl_spike"
    POOL_PAUSED = "pool_paused"


@dataclass
class Alert:
    alert_type: AlertType
    pool_id: str
    pool_name: str
    pool_address: str
    chain: str
    current_tvl_usd: float
    previous_tvl_usd: float | None = None
    version: int = 3

    @property
    def tvl_change_pct(self) -> float | None:
        if self.previous_tvl_usd is None or self.previous_tvl_usd == 0:
            return None
        return (self.current_tvl_usd - self.previous_tvl_usd) / self.previous_tvl_usd


def check_alerts(
    current_pools: list[dict[str, Any]],
    previous_snapshot: dict[str, Any],
    tvl_drop_threshold: float,
    tvl_spike_threshold: float,
    min_tvl_usd: float,
) -> list[Alert]:
    """
    Compare current pool data against the previous snapshot and return
    a list of triggered alerts.

    Args:
        current_pools: list of pool dicts from the Balancer API.
        previous_snapshot: dict mapping pool_id -> pool data from last run.
        tvl_drop_threshold: fractional drop (e.g. 0.10 = 10%) that triggers a TVL drop alert.
        tvl_spike_threshold: fractional gain (e.g. 0.50 = 50%) that triggers a TVL spike alert.
        min_tvl_usd: pools with current TVL below this value are ignored.
    """
    triggered: list[Alert] = []

    for pool in current_pools:
        pool_id = pool["id"]
        current_tvl = pool["total_liquidity_usd"]
        is_paused = pool["is_paused"]

        if current_tvl < min_tvl_usd:
            continue

        previous = previous_snapshot.get(pool_id)

        if previous is None:
            logger.debug("Pool %s not in previous snapshot — skipping delta checks", pool_id)
        else:
            previous_tvl = float(previous.get("total_liquidity_usd", 0))

            if previous_tvl > 0:
                change = (current_tvl - previous_tvl) / previous_tvl

                if change <= -tvl_drop_threshold:
                    triggered.append(
                        Alert(
                            alert_type=AlertType.TVL_DROP,
                            pool_id=pool_id,
                            pool_name=pool["name"],
                            pool_address=pool["address"],
                            chain=pool["chain"],
                            current_tvl_usd=current_tvl,
                            previous_tvl_usd=previous_tvl,
                            version=pool.get("version", 3),
                        )
                    )
                    logger.info(
                        "TVL_DROP triggered for pool %s: %.1f%%",
                        pool_id,
                        change * 100,
                    )

                elif change >= tvl_spike_threshold:
                    triggered.append(
                        Alert(
                            alert_type=AlertType.TVL_SPIKE,
                            pool_id=pool_id,
                            pool_name=pool["name"],
                            pool_address=pool["address"],
                            chain=pool["chain"],
                            current_tvl_usd=current_tvl,
                            previous_tvl_usd=previous_tvl,
                            version=pool.get("version", 3),
                        )
                    )
                    logger.info(
                        "TVL_SPIKE triggered for pool %s: +%.1f%%",
                        pool_id,
                        change * 100,
                    )

        was_paused = bool((previous or {}).get("is_paused", False))
        if is_paused and not was_paused:
            triggered.append(
                Alert(
                    alert_type=AlertType.POOL_PAUSED,
                    pool_id=pool_id,
                    pool_name=pool["name"],
                    pool_address=pool["address"],
                    chain=pool["chain"],
                    current_tvl_usd=current_tvl,
                    previous_tvl_usd=None,
                    version=pool.get("version", 3),
                )
            )
            logger.info("POOL_PAUSED triggered for pool %s", pool_id)

    logger.info("%d alert(s) triggered in total", len(triggered))
    return triggered
