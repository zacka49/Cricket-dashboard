from cricket_edge.the_odds_api import extract_match_winner_outcomes, parse_sports


def test_parse_sports_filters_active_cricket_sports() -> None:
    payload = [
        {"key": "cricket_ipl", "group": "Cricket", "title": "IPL", "active": True, "has_outrights": False},
        {"key": "soccer_epl", "group": "Soccer", "title": "EPL", "active": True, "has_outrights": False},
        {"key": "cricket_t20_blast", "group": "Cricket", "title": "T20 Blast", "active": False, "has_outrights": False},
    ]

    sports = parse_sports(payload, only_active_cricket=True)

    assert [sport.key for sport in sports] == ["cricket_ipl"]


def test_extract_match_winner_outcomes_from_h2h_market() -> None:
    payload = {
        "id": "event-1",
        "sport_key": "cricket_t20_blast",
        "sport_title": "T20 Blast",
        "commence_time": "2026-06-14T18:30:00Z",
        "home_team": "Somerset",
        "away_team": "Surrey",
        "bookmakers": [
            {
                "key": "paddypower",
                "title": "Paddy Power",
                "last_update": "2026-06-14T10:00:00Z",
                "markets": [
                    {
                        "key": "h2h",
                        "last_update": "2026-06-14T10:01:00Z",
                        "outcomes": [
                            {"name": "Somerset", "price": 2.2},
                            {"name": "Surrey", "price": 1.75},
                        ],
                    }
                ],
            },
            {
                "key": "irrelevant",
                "title": "Spread Book",
                "last_update": "2026-06-14T10:00:00Z",
                "markets": [{"key": "spreads", "outcomes": [{"name": "Somerset", "price": 1.9}]}],
            },
        ],
    }

    outcomes = extract_match_winner_outcomes(payload)

    assert [(row.selection, row.decimal_odds, row.bookmaker) for row in outcomes] == [
        ("Somerset", 2.2, "Paddy Power"),
        ("Surrey", 1.75, "Paddy Power"),
    ]
    assert {row.captured_at for row in outcomes} == {"2026-06-14T10:01:00Z"}
