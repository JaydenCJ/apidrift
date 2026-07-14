"""Shopping cart (example fixture, v2)."""

from .money import Money


class Cart:
    """A list of priced items."""

    def __init__(self):
        self.items = []

    def add(self, name, price, quantity=1, note=None):
        self.items.append((name, price, quantity))

    def total(self):
        amount = sum(p.amount * q for _, p, q in self.items)
        return Money(amount)

    def clear(self):
        self.items = []
