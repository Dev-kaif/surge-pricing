"""Turn generated zone-hour and trip data into a two-zone game market."""

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from surge_pricing.market import Market


@dataclass(frozen=True)
class MarketCalibration:
    """A market plus the data choices used to construct it."""

    market: Market
    hot_zone: str
    calm_zone: str
    observations_per_zone: int
    period_description: str


def market_from_generated_data(
    data_dir: Path, *, start_hour: int = 17, end_hour: int = 19
) -> MarketCalibration:
    """Build a two-zone market from the generated weekday evening data.

    The zone with the highest mean rider arrivals becomes the hot zone and the
    lowest becomes the calm zone.  The game then represents drivers choosing
    between those two zones during a representative one-hour period.
    """
    trips_path = data_dir / "trips.parquet"
    truth_path = data_dir / "zone_hours.csv"
    if not trips_path.exists() or not truth_path.exists():
        raise FileNotFoundError(
            f"Expected {trips_path} and {truth_path}. Run data/simulate_data.py first."
        )

    trips = pd.read_parquet(trips_path, columns=["rider_fare_inr", "driver_pay_inr"])
    truth = pd.read_csv(truth_path, parse_dates=["hour_start"])
    required = {"hour_start", "zone_name", "riders_arriving", "drivers_active"}
    missing = required.difference(truth.columns)
    if missing:
        raise ValueError(f"zone_hours.csv is missing columns: {', '.join(sorted(missing))}")
    if trips.empty or truth.empty:
        raise ValueError("Generated trip and zone-hour data must not be empty.")

    is_weekday_evening = (
        (truth["hour_start"].dt.dayofweek < 5)
        & truth["hour_start"].dt.hour.between(start_hour, end_hour)
    )
    window = truth.loc[is_weekday_evening]
    if window.empty:
        raise ValueError("No zone-hours match the requested calibration window.")

    by_zone = window.groupby("zone_name", sort=False).agg(
        rider_arrivals=("riders_arriving", "mean"),
        drivers_active=("drivers_active", "mean"),
        observations=("zone_name", "size"),
    )
    hot_zone = str(by_zone["rider_arrivals"].idxmax())
    calm_zone = str(by_zone["rider_arrivals"].idxmin())
    selected = by_zone.loc[[hot_zone, calm_zone]]

    gross_fares = trips["rider_fare_inr"].sum()
    if gross_fares <= 0:
        raise ValueError("Trip fares must sum to a positive value.")
    commission = float(1 - trips["driver_pay_inr"].sum() / gross_fares)

    market = Market(
        total_drivers=float(selected["drivers_active"].sum()),
        rider_arrivals=(
            float(selected.loc[hot_zone, "rider_arrivals"]),
            float(selected.loc[calm_zone, "rider_arrivals"]),
        ),
        commission=commission,
    )
    return MarketCalibration(
        market=market,
        hot_zone=hot_zone,
        calm_zone=calm_zone,
        observations_per_zone=int(selected["observations"].min()),
        period_description=f"weekdays, {start_hour:02d}:00-{end_hour:02d}:59",
    )
