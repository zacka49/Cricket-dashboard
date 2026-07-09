from __future__ import annotations

import math
from typing import Iterable


def parse_decimal_odds(raw: object) -> float | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        value = float(text)
        return value if math.isfinite(value) and value > 1.0 else None
    except ValueError:
        pass
    if "/" not in text:
        return None
    left, right = text.split("/", 1)
    try:
        denominator = float(right)
        if denominator <= 0:
            return None
        value = 1.0 + (float(left) / denominator)
        return value if math.isfinite(value) and value > 1.0 else None
    except ValueError:
        return None


def implied_probability(decimal_odds: float) -> float:
    if decimal_odds <= 1.0:
        raise ValueError("Decimal odds must be greater than 1.0.")
    return 1.0 / decimal_odds


def overround(decimal_odds: Iterable[float]) -> float:
    return sum(implied_probability(float(odds)) for odds in decimal_odds)


def no_vig_probabilities(decimal_odds: Iterable[float]) -> list[float]:
    odds = [float(value) for value in decimal_odds]
    book_overround = overround(odds)
    if book_overround <= 0:
        raise ValueError("Overround must be positive.")
    return [implied_probability(value) / book_overround for value in odds]
