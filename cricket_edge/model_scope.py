from __future__ import annotations

from typing import Any


T20_MODEL_SCOPE = "T20"


def infer_cricket_format(*labels: object) -> str:
    """Infer a fixture format from provider competition metadata.

    Unknown formats intentionally remain unknown: a T20 model must not treat a
    generic cricket fixture as T20 simply because a provider omitted the label.
    """
    text = " ".join(str(label or "").lower() for label in labels)
    if "odi" in text or "one day" in text:
        return "ODI"
    if "test match" in text or "test series" in text or "cricket_test" in text:
        return "Test"
    if "t20" in text or "twenty20" in text or "ipl" in text:
        return T20_MODEL_SCOPE
    return "Unknown"


def fixture_is_t20_eligible(fixture: dict[str, Any]) -> bool:
    """Return true only when the fixture is safely in the active T20 scope."""
    competition_format = infer_cricket_format(fixture.get("competition"))
    if competition_format in {"ODI", "Test"}:
        return False
    fixture_format = str(fixture.get("format") or "").strip().upper()
    return fixture_format == T20_MODEL_SCOPE and competition_format in {T20_MODEL_SCOPE, "Unknown"}
