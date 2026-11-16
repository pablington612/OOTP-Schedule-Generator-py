import decimal
from decimal import Decimal

CLOSE_ENOUGH = Decimal("0.00001")


def lcm(*values):
    result = values[0]
    for v in values[1:]:
        result = result * (v // gcd(result, v))
    return result


def gcd(*values):
    result = values[0]
    for b in values[1:]:
        a = result
        while b > 0:
            a, b = b, a % b
        result = a
    return result


def is_whole_number(number):
    number = close_round(number)
    return number % 1 == 0


def close_round(number):
    rounded = decimal.Context(prec=4, rounding=decimal.ROUND_HALF_DOWN).plus(number)
    difference = rounded - number
    if difference < CLOSE_ENOUGH:
        number = rounded
    return number


def jdiv(a, b):
    """Java int division: truncates toward zero (Python's // floors)."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b > 0) else -q


def jmod(a, b):
    """Java int remainder: takes the sign of the dividend."""
    return a - b * jdiv(a, b)
