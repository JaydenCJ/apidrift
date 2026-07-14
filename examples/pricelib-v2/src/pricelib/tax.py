"""Tax helpers (new module in the v2 example fixture)."""

from .money import Money


def with_tax(money, percent=10.0):
    return Money(money.amount * (1 + percent / 100), money.currency)
