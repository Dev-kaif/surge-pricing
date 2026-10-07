"""A two-zone ride-hailing market: what riders want, what drivers earn."""
import math
from dataclasses import dataclass

HOT, CALM = 0, 1


@dataclass(frozen=True)
class Market:
    total_drivers: float = 100.0
    rider_arrivals: tuple[float, float] = (200.0, 80.0)  # (hot zone, calm zone)
    max_willingness_to_pay: float = 2.0                   # in multiples of the base fare
    base_fare: float = 1.0
    trips_per_driver: float = 1.0                         # capacity per period
    commission: float = 0.25                              # platform's cut of each fare

    def fare(self, surge: float) -> float:
        return self.base_fare * surge

    def requested_trips(self, zone: int, surge: float) -> float:
        """Riders whose willingness to pay (uniform) covers the surged fare."""
        share_willing = max(0.0, 1.0 - self.fare(surge) / self.max_willingness_to_pay)
        return self.rider_arrivals[zone] * share_willing

    def completed_trips(self, zone: int, surge: float, drivers: float) -> float:
        requests = self.requested_trips(zone, surge)
        if requests == 0 or drivers <= 0:
            return 0.0
        # Some requests never meet a free driver; more drivers means fewer misses.
        capacity = self.trips_per_driver * drivers
        return requests * (1.0 - math.exp(-capacity / requests))

    def earnings_per_driver(self, zone: int, surge: float, drivers: float) -> float:
        if self.requested_trips(zone, surge) == 0:
            return 0.0
        driver_share = 1.0 - self.commission
        if drivers < 1e-9:
            # Limit as drivers -> 0: a lone driver is never idle.
            return driver_share * self.fare(surge) * self.trips_per_driver
        trips = self.completed_trips(zone, surge, drivers)
        return driver_share * self.fare(surge) * trips / drivers

    def rider_surplus(self, zone: int, surge: float, trips: float) -> float:
        """A served rider gains, on average, half the gap between their max and the fare."""
        gap = max(0.0, self.max_willingness_to_pay - self.fare(surge))
        return trips * gap / 2.0