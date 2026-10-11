"""Test suite for math_ops containing both passing and failing assertions."""

import pytest
from math_ops import divide_numbers
from clean_service import format_user_name


def test_format_user_name_passing():
    """Clean test that passes cleanly."""
    result = format_user_name("alice", "smith")
    assert result == "Alice Smith"


def test_divide_zero_division_failing():
    """Failing test demonstrating zero division crash."""
    # This invocation triggers ZeroDivisionError: division by zero
    result = divide_numbers(10.0, 0.0)
    assert result == 0.0
