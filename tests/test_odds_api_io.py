from cricket_edge.odds_api_io import extract_match_winner_outcomes, parse_events, parse_sports


def test_parse_sports_and_events() -> None:
    sports = parse_sports([{"name": "Cricket", "slug": "cricket"}])
    events = parse_events(
        [
            {
                "id": 123,
                "sport": {"name": "Cricket", "slug": "cricket"},
                "league": {"name": "T20 Blast", "slug": "t20-blast"},
                "home": "Somerset",
                "away": "Surrey",
                "date": "2026-06-12T12:00:00Z",
                "status": "pending",
            }
        ]
    )

    assert sports[0].slug == "cricket"
    assert events[0].home == "Somerset"
    assert events[0].status == "pending"


def test_extract_match_winner_outcomes_from_bet365_ml() -> None:
    payload = {
        "id": 123,
        "home": "Somerset",
        "away": "Surrey",
        "date": "2026-06-12T12:00:00Z",
        "status": "pending",
        "bookmakers": {
            "Bet365": [
                {
                    "name": "ML",
                    "updatedAt": "2026-06-12T10:00:00Z",
                    "odds": [{"home": "2.10", "away": "1.80"}],
                }
            ]
        },
    }

    outcomes = extract_match_winner_outcomes(payload)

    assert [item.selection for item in outcomes] == ["Somerset", "Surrey"]
    assert [item.decimal_odds for item in outcomes] == [2.1, 1.8]
    assert {item.bookmaker for item in outcomes} == {"Bet365"}


def test_extract_match_winner_outcomes_can_filter_bookmakers() -> None:
    payload = {
        "id": 123,
        "home": "Somerset",
        "away": "Surrey",
        "date": "2026-06-12T12:00:00Z",
        "status": "pending",
        "bookmakers": {
            "Bet365": [{"name": "ML", "odds": [{"home": "2.10", "away": "1.80"}]}],
            "Unibet": [{"name": "ML", "odds": [{"home": "2.20", "away": "1.70"}]}],
        },
    }

    outcomes = extract_match_winner_outcomes(payload, allowed_bookmakers={"Bet365"})

    assert len(outcomes) == 2
    assert {item.bookmaker for item in outcomes} == {"Bet365"}


def test_extract_match_winner_ignores_draw_and_bad_prices() -> None:
    payload = {
        "id": 123,
        "home": "Somerset",
        "away": "Surrey",
        "date": "2026-06-12T12:00:00Z",
        "status": "pending",
        "bookmakers": {
            "Bet365": [
                {
                    "name": "ML",
                    "odds": [{"home": "Infinity", "draw": "3.40", "away": "1.80"}],
                }
            ]
        },
    }

    outcomes = extract_match_winner_outcomes(payload)

    assert [item.selection for item in outcomes] == ["Surrey"]
