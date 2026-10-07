import numpy as np
import pandas as pd
import pytest

from surge_pricing.calibration import market_from_generated_data
from surge_pricing.dynamics import DynamicsConfig, simulate
from surge_pricing.equilibrium import drivers_in_hot_zone, evaluate
from surge_pricing.market import Market


@pytest.fixture
def market():
    return Market()


@pytest.mark.parametrize("surge_hot, surge_calm", [(1.0, 1.0), (1.5, 1.0), (1.2, 1.4)])
def test_no_driver_gains_by_switching(market, surge_hot, surge_calm):
    outcome = evaluate(market, surge_hot, surge_calm)
    assert outcome.earnings_hot == pytest.approx(outcome.earnings_calm, abs=1e-6)


def test_drivers_are_conserved(market):
    drivers_hot = drivers_in_hot_zone(market, 1.3, 1.0)
    assert 0 <= drivers_hot <= market.total_drivers


def test_same_surge_everywhere_does_not_move_drivers(market):
    baseline = drivers_in_hot_zone(market, 1.0, 1.0)
    assert drivers_in_hot_zone(market, 1.5, 1.5) == pytest.approx(baseline, abs=1e-6)


def test_surge_in_hot_zone_attracts_drivers(market):
    assert drivers_in_hot_zone(market, 1.2, 1.0) > drivers_in_hot_zone(market, 1.0, 1.0)


def test_nobody_rides_above_max_willingness_to_pay(market):
    assert market.requested_trips(0, surge=market.max_willingness_to_pay) == 0.0


def test_dynamics_settle_near_a_fixed_point(market):
    history = simulate(
        market, DynamicsConfig(driver_learning_rate=0.6, surge_smoothing=1.0)
    )
    assert np.std(history.drivers_hot[-50:]) < 1e-3


def test_calibration_uses_weekday_evening_hot_and_calm_zones(tmp_path):
    pd.DataFrame({
        "rider_fare_inr": [20.0, 10.0],
        "driver_pay_inr": [15.0, 7.5],
    }).to_parquet(tmp_path / "trips.parquet", index=False)
    pd.DataFrame({
        "hour_start": ["2025-01-06 18:00"] * 3 + ["2025-01-11 18:00"],
        "zone_name": ["Busy", "Quiet", "Middle", "Weekend only"],
        "riders_arriving": [120, 20, 60, 500],
        "drivers_active": [30, 10, 20, 100],
    }).to_csv(tmp_path / "zone_hours.csv", index=False)

    calibration = market_from_generated_data(tmp_path)

    assert calibration.hot_zone == "Busy"
    assert calibration.calm_zone == "Quiet"
    assert calibration.market.rider_arrivals == (120.0, 20.0)
    assert calibration.market.total_drivers == 40.0
    assert calibration.market.commission == pytest.approx(0.25)
