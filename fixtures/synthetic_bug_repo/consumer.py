"""Consumer module demonstrating cross-module caller dependencies."""

from math_ops import divide_numbers


def compute_ratio(numerator: float, denominator: float) -> float:
    """Compute ratio between two measurements using math_ops."""
    return divide_numbers(numerator, denominator)
