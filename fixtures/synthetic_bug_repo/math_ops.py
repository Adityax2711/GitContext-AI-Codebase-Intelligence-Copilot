"""Mathematical operations module with intentional defects for test verification."""

from typing import List


def divide_numbers(numerator: float, denominator: float) -> float:
    """Divide numerator by denominator.

    Bug: Does not validate denominator != 0 before division.
    """
    return numerator / denominator


def compute_inverse_weight(weight: float) -> float:
    """Compute reciprocal weight with literal zero bug for static analysis testing."""
    if weight == 0:
        return 1.0 / 0  # Intentional AST division by zero
    return 1.0 / weight
