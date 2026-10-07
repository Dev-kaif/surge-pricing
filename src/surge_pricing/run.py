"""Run the surge pricing game and compare pricing mechanisms."""
import argparse
from pathlib import Path

import numpy as np

from surge_pricing.calibration import market_from_generated_data
from surge_pricing.dynamics import DynamicsConfig, simulate
from surge_pricing.equilibrium import Outcome, evaluate
from surge_pricing.plots import plot_results
from surge_pricing.stackelberg import revenue, solve_leader_problem, welfare

COLUMNS = ("mechanism", "surge hot", "surge calm", "drivers hot", "driver pay",
           "trips", "unmet hot", "platform", "riders", "welfare")


def print_comparison(rows: list[tuple[str, Outcome]]) -> None:
    print("{:<28}".format(COLUMNS[0]) + "".join(f"{name:>12}" for name in COLUMNS[1:]))
    for label, o in rows:
        values = (o.surge_hot, o.surge_calm, o.drivers_hot, o.earnings_hot, o.trips,
                  o.unmet_share_hot, o.platform_revenue, o.rider_surplus, o.welfare)
        formats = ("{:12.2f}", "{:12.2f}", "{:12.1f}", "{:12.3f}", "{:12.1f}",
                   "{:12.1%}", "{:12.2f}", "{:12.2f}", "{:12.2f}")
        print(f"{label:<28}" + "".join(fmt.format(v) for fmt, v in zip(formats, values)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    default_data_dir = Path(__file__).resolve().parents[2] / "data"
    parser.add_argument(
        "--data-dir", type=Path, default=default_data_dir,
        help="Directory containing trips.parquet and zone_hours.csv (default: %(default)s)",
    )
    args = parser.parse_args()

    calibration = market_from_generated_data(args.data_dir)
    market = calibration.market
    print(
        f"Calibrated from {calibration.period_description}: "
        f"hot={calibration.hot_zone}, calm={calibration.calm_zone}; "
        f"{calibration.observations_per_zone} observations per zone; "
        f"arrivals={market.rider_arrivals}, drivers={market.total_drivers:.1f}, "
        f"commission={market.commission:.3f}\n"
    )
    surge_grid = np.linspace(1.0, 3.0, 41)

    flat_price = evaluate(market, 1.0, 1.0)
    revenue_max = solve_leader_problem(market, revenue, surge_grid)
    welfare_max = solve_leader_problem(market, welfare, surge_grid)

    slow_history = simulate(market, DynamicsConfig(driver_learning_rate=0.02))
    fast_history = simulate(market, DynamicsConfig(driver_learning_rate=0.6,
                                                   surge_sensitivity=2.0, surge_smoothing=1.0))
    ratio_rule = evaluate(market, slow_history.surge_hot[-1], slow_history.surge_calm[-1],
                          slow_history.drivers_hot[-1])

    print_comparison([
        ("Flat price", flat_price),
        ("Stackelberg: max revenue", revenue_max.outcome),
        ("Stackelberg: max welfare", welfare_max.outcome),
        ("Ratio rule (end of run)", ratio_rule),
    ])
    best = revenue_max.outcome
    print(f"\nEarnings at the revenue-max equilibrium: hot {best.earnings_hot:.4f}, "
          f"calm {best.earnings_calm:.4f}")
    print(f"Hot-zone drivers after {len(slow_history.drivers_hot)} periods: "
          f"slow {slow_history.drivers_hot[-1]:.1f}, fast {fast_history.drivers_hot[-1]:.1f}")

    plot_results(market, revenue_max, slow_history, fast_history,
                 Path(__file__).parent / "results.png")


if __name__ == "__main__":
    main()
