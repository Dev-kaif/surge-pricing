"""Figures for the surge pricing game."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from surge_pricing.dynamics import History
from surge_pricing.equilibrium import evaluate
from surge_pricing.market import Market
from surge_pricing.stackelberg import LeaderSolution


def plot_results(
    market: Market,
    revenue_solution: LeaderSolution,
    slow_history: History,
    fast_history: History,
    path: Path,
) -> None:
    surge_levels = revenue_solution.surge_grid
    # Surge only in the hot zone; the calm zone keeps the base fare.
    sweep = [evaluate(market, surge, 1.0) for surge in surge_levels]

    figure, axes = plt.subplots(2, 2, figsize=(12, 9))

    ax = axes[0, 0]
    ax.plot(surge_levels, [o.drivers_hot for o in sweep], lw=2, label="hot zone")
    ax.plot(
        surge_levels,
        [market.total_drivers - o.drivers_hot for o in sweep],
        lw=2,
        label="calm zone",
    )
    ax.set(
        xlabel="hot-zone surge (calm zone stays at 1.0)",
        ylabel="drivers at equilibrium",
        title="Surge pulls drivers in, but starves the calm zone",
    )
    ax.legend()

    ax = axes[0, 1]
    ax.plot(
        surge_levels,
        [o.platform_revenue for o in sweep],
        lw=2,
        label="platform revenue",
    )
    ax.plot(surge_levels, [o.rider_surplus for o in sweep], lw=2, label="rider surplus")
    ax.plot(surge_levels, [o.driver_income for o in sweep], lw=2, label="driver income")
    ax.plot(
        surge_levels,
        [o.welfare for o in sweep],
        lw=2,
        ls="--",
        color="black",
        label="total welfare",
    )
    ax.set(xlabel="hot-zone surge", title="Who gains and loses as surge rises")
    ax.legend()

    ax = axes[1, 0]
    image = ax.imshow(
        revenue_solution.payoffs.T,
        origin="lower",
        aspect="auto",
        cmap="viridis",
        extent=[surge_levels[0], surge_levels[-1], surge_levels[0], surge_levels[-1]],
    )
    best = revenue_solution.outcome
    ax.plot(
        best.surge_hot,
        best.surge_calm,
        "r*",
        markersize=16,
        label=f"best for platform ({best.surge_hot:.2f}, {best.surge_calm:.2f})",
    )
    ax.set(
        xlabel="hot-zone surge",
        ylabel="calm-zone surge",
        title="Platform revenue (the leader's payoff)",
    )
    ax.legend(loc="upper right")
    figure.colorbar(image, ax=ax)

    ax = axes[1, 1]
    ax.plot(slow_history.drivers_hot, lw=2, label="slow driver adaptation")
    ax.plot(fast_history.drivers_hot, lw=1.5, alpha=0.8, label="fast driver adaptation")
    ax.set(
        xlabel="period",
        ylabel="drivers in hot zone",
        title="Drivers and surge rule adapting over time",
    )
    ax.legend()

    figure.tight_layout()
    figure.savefig(path, dpi=130)
