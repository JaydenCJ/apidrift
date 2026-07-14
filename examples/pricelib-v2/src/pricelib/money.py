"""Money values and conversion helpers (example fixture, v2).

Compared to v1 this intentionally ships one accidental breaking change
(`convert` made `rate` keyword-only, `format_price` was deleted) alongside
harmless additions — exactly the mix apidrift exists to catch.
"""

DEFAULT_CURRENCY = "EUR"


class Money:
    """An amount in a currency."""

    def __init__(self, amount, currency=DEFAULT_CURRENCY):
        self.amount = amount
        self.currency = currency

    def rounded(self, digits=2, mode="half-even"):
        return Money(round(self.amount, digits), self.currency)

    @property
    def cents(self):
        return int(self.amount * 100)


def convert(money, currency, *, rate):
    """Convert ``money`` into ``currency`` at ``rate``."""
    return Money(money.amount * rate, currency)
