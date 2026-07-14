"""pricelib — a deliberately small fake library used by the apidrift examples."""

from .cart import Cart
from .money import Money, convert
from .tax import with_tax

__version__ = "1.5.0"
