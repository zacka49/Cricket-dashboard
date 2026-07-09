import pytest

from cricket_edge.odds_math import implied_probability, no_vig_probabilities, overround, parse_decimal_odds


def test_parse_decimal_odds_supports_decimal_and_fractional() -> None:
    assert parse_decimal_odds("2.50") == 2.5
    assert parse_decimal_odds("3/2") == 2.5
    assert parse_decimal_odds("") is None
    assert parse_decimal_odds("NaN") is None
    assert parse_decimal_odds("Infinity") is None
    assert parse_decimal_odds("1e309") is None
    assert parse_decimal_odds("1.00") is None
    assert parse_decimal_odds("0") is None


def test_no_vig_probabilities_normalize_book_margin() -> None:
    odds = [1.91, 1.91]

    assert round(implied_probability(1.91), 4) == 0.5236
    assert round(overround(odds), 4) == 1.0471
    assert no_vig_probabilities(odds) == pytest.approx([0.5, 0.5], abs=1e-6)


def test_invalid_implied_probability_rejects_non_bettable_odds() -> None:
    with pytest.raises(ValueError):
        implied_probability(1.0)
