"""Drivers' side of the game: where do they go, and what does everyone get?"""
from dataclasses import dataclass

from surge_pricing.market import CALM, HOT, Market


@dataclass(frozen=True)
class Outcome:
    surge_hot: float
    surge_calm: float
    drivers_hot: float
    earnings_hot: float
    earnings_calm: float
    trips: float
    unmet_share_hot: float
    unmet_share_calm: float
    platform_revenue: float
    rider_surplus: float
    driver_income: float

    @property
    def welfare(self) -> float:
        return self.rider_surplus + self.driver_income + self.platform_revenue


def drivers_in_hot_zone(market: Market, surge_hot: float, surge_calm: float) -> float:
    """Nash equilibrium of the driver game: no driver gains by switching zones.

    Adding a driver to the hot zone lowers hot-zone earnings and raises
    calm-zone earnings, so the earnings gap is decreasing and bisection works.
    """
    total = market.total_drivers

    def hot_zone_advantage(drivers_hot: float) -> float:
        hot = market.earnings_per_driver(HOT, surge_hot, drivers_hot)
        calm = market.earnings_per_driver(CALM, surge_calm, total - drivers_hot)
        return hot - calm

    if hot_zone_advantage(0.0) <= 0:
        return 0.0       # calm zone pays more even when the hot zone is empty
    if hot_zone_advantage(total) >= 0:
        return total     # hot zone pays more even when everyone is there

    low, high = 0.0, total
    while high - low > 1e-9:
        middle = (low + high) / 2
        if hot_zone_advantage(middle) > 0:
            low = middle
        else:
            high = middle
    return (low + high) / 2


def evaluate(market: Market, surge_hot: float, surge_calm: float,
             drivers_hot: float | None = None) -> Outcome:
    """Outcome for given surge levels. Drivers settle at equilibrium unless fixed."""
    if drivers_hot is None:
        drivers_hot = drivers_in_hot_zone(market, surge_hot, surge_calm)
    drivers = {HOT: drivers_hot, CALM: market.total_drivers - drivers_hot}
    surge = {HOT: surge_hot, CALM: surge_calm}

    trips = {z: market.completed_trips(z, surge[z], drivers[z]) for z in (HOT, CALM)}
    requests = {z: market.requested_trips(z, surge[z]) for z in (HOT, CALM)}
    fare_revenue = sum(market.fare(surge[z]) * trips[z] for z in (HOT, CALM))

    def unmet_share(zone: int) -> float:
        return 1.0 - trips[zone] / requests[zone] if requests[zone] > 0 else 1.0

    return Outcome(
        surge_hot=surge_hot,
        surge_calm=surge_calm,
        drivers_hot=drivers_hot,
        earnings_hot=market.earnings_per_driver(HOT, surge_hot, drivers[HOT]),
        earnings_calm=market.earnings_per_driver(CALM, surge_calm, drivers[CALM]),
        trips=sum(trips.values()),
        unmet_share_hot=unmet_share(HOT),
        unmet_share_calm=unmet_share(CALM),
        platform_revenue=market.commission * fare_revenue,
        rider_surplus=sum(market.rider_surplus(z, surge[z], trips[z]) for z in (HOT, CALM)),
        driver_income=(1.0 - market.commission) * fare_revenue,
    )