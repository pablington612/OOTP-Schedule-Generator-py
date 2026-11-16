"""
Groovy's "/" operator on integers and BigDecimals returns a BigDecimal, not an int.
This copies Groovy 2.4's BigDecimalMath.divideImpl so fractional cycle-time
arithmetic behaves exactly as it did in the original program.
"""
import decimal
from decimal import Decimal

# Java's BigDecimal add/multiply are exact; give the default context enough digits to match.
decimal.getcontext().prec = 1000

DIVISION_EXTRA_PRECISION = 10
DIVISION_MIN_SCALE = 10


def _precision(d):
    return len(d.as_tuple().digits)


def _scale(d):
    return -d.as_tuple().exponent


def div(left, right):
    left = Decimal(left)
    right = Decimal(right)
    exact = decimal.Context(prec=1000)
    result = exact.divide(left, right)
    if not exact.flags[decimal.Inexact]:
        return result
    precision = max(_precision(left), _precision(right)) + DIVISION_EXTRA_PRECISION
    result = decimal.Context(prec=precision, rounding=decimal.ROUND_HALF_UP).divide(left, right)
    scale = max(_scale(result), _scale(left), _scale(right))
    if scale > DIVISION_MIN_SCALE:
        result = result.quantize(Decimal(1).scaleb(-DIVISION_MIN_SCALE), rounding=decimal.ROUND_HALF_UP)
    return result
