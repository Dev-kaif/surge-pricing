"""Simulated Mumbai ride-hailing data.

Writes two files:
  trips.parquet   completed trips, with fares in Indian rupees and distances in kilometres
  zone_hours.csv  the hidden truth for every zone and hour (arrivals, drivers, surge,
                  unmet demand), which real data never gives you
"""
import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

MAX_WILLINGNESS_TO_PAY = 2.0     # riders' limit, as a multiple of the un-surged fare
TRIPS_PER_DRIVER_HOUR = 1.0
COMMISSION = 0.25
FLEET_SIZE = 260                 # drivers online at the busiest hour, across all zones
SURGE_SENSITIVITY = 0.6
SURGE_CAP = 1.8
RAIN_DEMAND_BOOST = 1.25
START_DATE = pd.Timestamp("2025-01-06")   # a Monday


@dataclass(frozen=True)
class Zone:
    zone_id: int
    name: str
    riders_per_hour: float   # average arrivals when the demand profile equals 1.0
    pattern: str             # "commute", "nightlife", "airport" or "residential"


ZONES = (
    Zone(1, "BKC", 150, "commute"),
    Zone(2, "Bandra", 110, "nightlife"),
    Zone(3, "CSMIA Airport", 100, "airport"),
    Zone(4, "Lower Parel", 90, "commute"),
    Zone(5, "Powai", 55, "residential"),
    Zone(6, "Borivali", 40, "residential"),
)


def bump(hour: float, center: float, width: float) -> float:
    """Smooth peak around `center` that wraps around midnight."""
    distance = min(abs(hour - center), 24 - abs(hour - center))
    return float(np.exp(-0.5 * (distance / width) ** 2))


def demand_profile(pattern: str, hour: int, is_weekend: bool) -> float:
    if pattern == "commute":
        if is_weekend:
            return 0.30 + 0.50 * bump(hour, 13, 3.5)
        return 0.25 + 1.00 * bump(hour, 8.5, 1.5) + 1.10 * bump(hour, 18, 2.0)
    if pattern == "nightlife":
        if is_weekend:
            return 0.25 + 1.30 * bump(hour, 23.5, 2.5)
        return 0.20 + 0.80 * bump(hour, 22, 2.2)
    if pattern == "airport":
        return 0.50 + 0.60 * bump(hour, 6, 2.0) + 0.50 * bump(hour, 17, 3.0)
    if is_weekend:  # residential
        return 0.25 + 0.50 * bump(hour, 12, 4.0)
    return 0.20 + 1.20 * bump(hour, 7.5, 1.5) + 0.60 * bump(hour, 19, 2.0)


def driver_activity(hour: int) -> float:
    """Share of the fleet online: fewer drivers overnight."""
    busy = bump(hour, 9, 4) + bump(hour, 18, 4) + 0.5 * bump(hour, 23, 3)
    return 0.45 + 0.55 * min(1.0, busy)


def rainy_hours(rng: np.random.Generator, days: int) -> np.ndarray:
    raining = np.zeros(days * 24, dtype=bool)
    for day in range(days):
        if rng.random() < 0.3:
            start = day * 24 + int(rng.integers(6, 20))
            raining[start:start + int(rng.integers(2, 7))] = True
    return raining


def make_trips(rng: np.random.Generator, zone: Zone, hour_start: pd.Timestamp,
               surge: float, count: int, crowding: float) -> pd.DataFrame:
    """Trip records for the `count` rides completed in one zone during one hour."""
    request_time = hour_start + pd.to_timedelta(rng.uniform(0, 3600, count), unit="s")
    wait_minutes = np.minimum(rng.exponential(2.0 + 4.0 * crowding, count), 25)
    pickup_time = request_time + pd.to_timedelta(wait_minutes, unit="m")

    airport_boost = 0.6 if zone.pattern == "airport" else 0.0
    kilometres = np.clip(rng.lognormal(1.5 + airport_boost, 0.6, count), 0.5, 60)
    speed_kmph = np.clip(rng.normal(22, 5, count), 7, 45)
    trip_seconds = kilometres / speed_kmph * 3600
    fare = (35 + 12 * kilometres + 1.2 * trip_seconds / 60) * surge

    commission = np.clip(rng.normal(COMMISSION, 0.04, count), 0.05, 0.5)
    zone_ids = [z.zone_id for z in ZONES]
    return pd.DataFrame({
        "ride_platform": rng.choice(["Uber", "Ola", "Rapido"], count, p=[0.5, 0.35, 0.15]),
        "request_datetime": request_time,
        "pickup_datetime": pickup_time,
        "dropoff_datetime": pickup_time + pd.to_timedelta(trip_seconds, unit="s"),
        "pickup_zone_id": zone.zone_id,
        "dropoff_zone_id": rng.choice(zone_ids, count),
        "trip_km": kilometres.round(2),
        "trip_seconds": trip_seconds.round().astype(int),
        "rider_fare_inr": fare.round(2),
        "driver_pay_inr": (fare * (1 - commission)).round(2),
    })


def simulate(days: int, seed: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    raining = rainy_hours(rng, days)
    trip_frames, truth_rows = [], []

    for day in range(days):
        for hour in range(24):
            hour_start = START_DATE + pd.Timedelta(days=day, hours=hour)
            is_weekend = hour_start.dayofweek >= 5
            is_raining = bool(raining[day * 24 + hour])

            expected_riders = np.array(
                [z.riders_per_hour * demand_profile(z.pattern, hour, is_weekend) for z in ZONES]
            )
            expected_riders *= RAIN_DEMAND_BOOST if is_raining else 1.0
            expected_riders *= rng.lognormal(0.0, 0.15, len(ZONES))
            riders = rng.poisson(expected_riders)

            # Drivers under-weight the busiest zones, which is what creates shortages.
            weights = expected_riders ** 0.8
            drivers = rng.poisson(FLEET_SIZE * driver_activity(hour) * weights / weights.sum())

            capacity = TRIPS_PER_DRIVER_HOUR * np.maximum(drivers, 1)
            shortage = riders * (1 - 1 / MAX_WILLINGNESS_TO_PAY) / capacity - 1
            surge = 1 + SURGE_SENSITIVITY * shortage + rng.normal(0, 0.04, len(ZONES))
            surge = np.round(np.clip(surge, 1.0, SURGE_CAP) * 20) / 20

            requests = rng.binomial(riders, 1 - surge / MAX_WILLINGNESS_TO_PAY)
            match_probability = np.where(
                requests > 0, 1 - np.exp(-capacity / np.maximum(requests, 1)), 0.0)
            completed = rng.binomial(requests, match_probability)

            for i, zone in enumerate(ZONES):
                crowding = float(np.clip(requests[i] / capacity[i], 0, 2))
                trip_frames.append(
                    make_trips(rng, zone, hour_start, surge[i], int(completed[i]), crowding))
                truth_rows.append({
                    "hour_start": hour_start, "zone_id": zone.zone_id, "zone_name": zone.name,
                    "raining": is_raining, "riders_arriving": int(riders[i]),
                    "surge_multiplier": float(surge[i]), "requests": int(requests[i]),
                    "drivers_active": int(drivers[i]), "completed_trips": int(completed[i]),
                    "unmet_requests": int(requests[i] - completed[i]),
                })

    trips = pd.concat(trip_frames, ignore_index=True).sort_values("request_datetime")
    return trips.reset_index(drop=True), pd.DataFrame(truth_rows)


def print_summary(trips: pd.DataFrame, truth: pd.DataFrame) -> None:
    take_rate = 1 - trips["driver_pay_inr"].sum() / trips["rider_fare_inr"].sum()
    surged = truth[truth["surge_multiplier"] > 1.0]
    print(f"{len(trips):,} completed trips over {truth['hour_start'].nunique() // 24} days")
    print(f"Take rate seen in the trip file: {take_rate:.3f} (true value {COMMISSION})")
    print(f"Zone-hours with surge: {len(surged) / len(truth):.1%}, "
          f"average surge when on: {surged['surge_multiplier'].mean():.2f}, "
          f"max {truth['surge_multiplier'].max():.2f}")

    by_zone = truth.groupby("zone_name").agg(
        riders_arriving=("riders_arriving", "mean"), requests=("requests", "mean"),
        completed=("completed_trips", "mean"), drivers=("drivers_active", "mean"))
    by_zone["unmet_share"] = 1 - by_zone["completed"] / by_zone["requests"]
    print("\nHourly averages per zone (the trip file only shows 'completed'):")
    print(by_zone.round(1).sort_values("riders_arriving", ascending=False).to_string())

    evening = truth[(truth["hour_start"].dt.dayofweek < 5)
                    & truth["hour_start"].dt.hour.between(17, 19)]
    peak = evening.groupby("zone_name")[["riders_arriving", "drivers_active"]].mean()
    hot, calm = peak["riders_arriving"].idxmax(), peak["riders_arriving"].idxmin()
    print(f"\nWeekday 17:00-19:59 inputs for the surge game ({hot} vs {calm}):")
    print(f"Market(total_drivers={peak.loc[[hot, calm], 'drivers_active'].sum():.0f}, "
          f"rider_arrivals=({peak.loc[hot, 'riders_arriving']:.0f}, "
          f"{peak.loc[calm, 'riders_arriving']:.0f}), commission={take_rate:.2f})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--days", type=int, default=28)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", type=Path, default=Path("data"))
    args = parser.parse_args()

    trips, truth = simulate(args.days, args.seed)
    args.out.mkdir(parents=True, exist_ok=True)
    trips.to_parquet(args.out / "trips.parquet", index=False)
    truth.to_csv(args.out / "zone_hours.csv", index=False)
    print_summary(trips, truth)
    print(f"\nSaved to {args.out}/")


if __name__ == "__main__":
    main()
