"""Search service containing boundary condition and off-by-one errors."""

from typing import List, Optional


def find_item_by_index(items: List[str], target_index: int) -> str:
    """Retrieve item at target index.

    Bug: Uses <= len(items) instead of < len(items), triggering off-by-one IndexError.
    """
    if target_index <= len(items):
        return items[target_index]
    raise IndexError("Index out of range")
