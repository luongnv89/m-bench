"""Confidence intervals for solve rates (issue #87).

Each suite has 8-28 tasks, so one task flipping moves a solve rate by several
points, and a fixed "differences under N points are noise" rule cannot know
how many generations stand behind a number. These intervals are derived from
the data instead: a 95% Wilson score interval for one rate, and Newcombe's
hybrid score interval (built from two Wilson intervals) for the difference
between two rates. A difference whose interval contains zero is not a result.

Both treat every generation as an independent Bernoulli trial. Samples of one
task are correlated, so with few tasks the true uncertainty is if anything
wider than quoted -- the report says so.
"""
import math

#: two-sided 95%
Z = 1.959963984540054


def wilson(successes, n, z=Z):
    """95% Wilson score interval for ``successes`` out of ``n``, or None if n < 1."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        return None
    if n < 1:
        return None
    k = min(max(float(successes), 0.0), n)
    p = k / n
    z2 = z * z
    denom = 1 + z2 / n
    centre = (p + z2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def rate_interval(rate, n):
    """Wilson interval for a rate observed over ``n`` generations, or None."""
    if rate is None or not n:
        return None
    return wilson(round(rate * n), n)


def newcombe(p1, n1, p2, n2):
    """95% interval for ``p1 - p2`` (Newcombe's method 10), or None.

    Built from each rate's Wilson interval, so it behaves at 0 % and 100 %
    where the textbook normal approximation collapses to a zero-width interval.
    """
    a, b = rate_interval(p1, n1), rate_interval(p2, n2)
    if a is None or b is None:
        return None
    k1, k2 = round(p1 * n1) / n1, round(p2 * n2) / n2
    d = k1 - k2
    lo = d - math.sqrt((k1 - a[0]) ** 2 + (b[1] - k2) ** 2)
    hi = d + math.sqrt((a[1] - k1) ** 2 + (k2 - b[0]) ** 2)
    return lo, hi
