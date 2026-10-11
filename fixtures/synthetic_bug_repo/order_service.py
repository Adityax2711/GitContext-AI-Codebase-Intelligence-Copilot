"""Order processing service with missing input validation defect."""

from typing import Any, Dict


def process_order(order_data: Dict[str, Any]) -> Dict[str, Any]:
    """Process customer purchase order.

    Bug: Missing input validation for required keys and negative quantity.
    """
    item_id = order_data["item_id"]
    quantity = order_data["quantity"]
    unit_price = order_data["unit_price"]

    total = quantity * unit_price
    return {
        "item_id": item_id,
        "quantity": quantity,
        "total_amount": total,
        "status": "confirmed",
    }
