"""Payment processing and Stripe integration for SynthStore."""

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class PaymentInvoice:
    invoice_id: str
    customer_id: str
    amount_cents: int
    currency: str = "USD"
    status: str = "pending"


def calculate_tax(amount_cents: int, tax_rate: float = 0.08) -> int:
    """Calculate sales tax in cents for an item amount."""
    return int(amount_cents * tax_rate)


class StripePaymentGateway:
    """Processes online transactions through Stripe API."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.transactions: Dict[str, PaymentInvoice] = {}

    def charge_customer(self, customer_id: str, amount_cents: int) -> PaymentInvoice:
        """Execute a direct charge against the customer's card."""
        tax = calculate_tax(amount_cents)
        total = amount_cents + tax
        invoice = PaymentInvoice(
            invoice_id=f"inv_{len(self.transactions) + 1}",
            customer_id=customer_id,
            amount_cents=total,
            status="paid",
        )
        self.transactions[invoice.invoice_id] = invoice
        return invoice
