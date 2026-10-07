"""What if nobody solves for equilibrium and everyone just adapts over time?"""

from dataclasses import dataclass

import numpy as np

from surge_pricing.equilibrium import evaluate
from surge_pricing.market import CALM, HOT, Market


@dataclass(frozen=True)
class DynamicsConfig:
    driver_learning_rate: float  # how fast drivers move toward the better-paying zone
    surge_sensitivity: float = 1.0  # surge added per unit of shortage
    surge_smoothing: float = 0.3  # 1.0 = jump straight to the target surge
    surge_cap: float = 1.8  # must stay below max willingness to pay / base fare
    periods: int = 400
    initial_drivers_hot: float = 50.0


@dataclass(frozen=True)
class History:
    drivers_hot: np.ndarray
    surge_hot: np.ndarray
    surge_calm: np.ndarray


def target_surge(
    market: Market, config: DynamicsConfig, zone: int, drivers: float
) -> float:
    """Ratio rule: surge grows with base-fare demand relative to driver capacity."""
    demand_at_base_fare = market.requested_trips(zone, surge=1.0)
    capacity = max(market.trips_per_driver * drivers, 1e-6)
    shortage = demand_at_base_fare / capacity - 1.0
    return float(
        np.clip(1.0 + config.surge_sensitivity * shortage, 1.0, config.surge_cap)
    )


def simulate(market: Market, config: DynamicsConfig) -> History:
    drivers_hot = config.initial_drivers_hot
    surge = {HOT: 1.0, CALM: 1.0}
    history = {"drivers_hot": [], "surge_hot": [], "surge_calm": []}

    for _ in range(config.periods):
        history["drivers_hot"].append(drivers_hot)
        history["surge_hot"].append(surge[HOT])
        history["surge_calm"].append(surge[CALM])

        # Replicator dynamics: the share in a zone grows if it pays more than the other.
        outcome = evaluate(market, surge[HOT], surge[CALM], drivers_hot)
        share_hot = drivers_hot / market.total_drivers
        pay_gap = outcome.earnings_hot - outcome.earnings_calm
        share_hot += config.driver_learning_rate * share_hot * (1 - share_hot) * pay_gap
        drivers_hot = float(np.clip(share_hot, 1e-4, 1 - 1e-4)) * market.total_drivers

        # The platform nudges each zone's surge toward the ratio rule's target.
        drivers = {HOT: drivers_hot, CALM: market.total_drivers - drivers_hot}
        for zone in (HOT, CALM):
            target = target_surge(market, config, zone, drivers[zone])
            keep = 1.0 - config.surge_smoothing
            surge[zone] = keep * surge[zone] + config.surge_smoothing * target

    return History(**{name: np.array(values) for name, values in history.items()})
