"""The platform's side of the game: pick surge levels, anticipating driver behaviour."""

from dataclasses import dataclass
from typing import Callable

import numpy as np

from surge_pricing.equilibrium import Outcome, evaluate
from surge_pricing.market import Market


def revenue(outcome: Outcome) -> float:
    return outcome.platform_revenue


def welfare(outcome: Outcome) -> float:
    return outcome.welfare


@dataclass(frozen=True)
class LeaderSolution:
    outcome: Outcome
    surge_grid: np.ndarray
    payoffs: (
        np.ndarray
    )  # payoffs[i, j]: hot zone at surge_grid[i], calm zone at surge_grid[j]


def solve_leader_problem(
    market: Market, objective: Callable[[Outcome], float], surge_grid: np.ndarray
) -> LeaderSolution:
    """Try every surge pair; drivers best-respond to each (leader moves first)."""
    size = len(surge_grid)
    payoffs = np.empty((size, size))
    for i, surge_hot in enumerate(surge_grid):
        for j, surge_calm in enumerate(surge_grid):
            payoffs[i, j] = objective(evaluate(market, surge_hot, surge_calm))

    best_hot, best_calm = np.unravel_index(payoffs.argmax(), payoffs.shape)
    best = evaluate(market, surge_grid[best_hot], surge_grid[best_calm])
    return LeaderSolution(best, surge_grid, payoffs)
