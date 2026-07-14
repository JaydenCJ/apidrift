"""Money values and conversion helpers (example fixture, v1)."""

DEFAULT_CURRENCY = "USD"


class Money:
    """An amount in a currency."""

    def __init__(self, amount, currency=DEFAULT_CURRENCY):
        self.amount = amount
        self.currency = currency

    def rounded(self, digits=2):
        return Money(round(self.amount, digits), self.currency)

    @property
    def cents(self):
        return int(self.amount * 100)


def convert(money, currency, rate):
    """Convert ``money`` into ``currency`` at ``rate``."""
    return Money(money.amount * rate, currency)


def format_price(money, symbol="$"):
    return "{}{:.2f}".format(symbol, money.amount)
