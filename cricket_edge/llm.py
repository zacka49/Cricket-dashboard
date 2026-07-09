from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .config import SETTINGS


@dataclass
class LLMResult:
    ok: bool
    text: str
    data: dict[str, Any]
    error: str = ""


class LocalLLMClient:
    """Tiny Ollama client with deterministic fallback behavior upstream."""

    def __init__(self, base_url: str | None = None, model: str | None = None, timeout: int = 20) -> None:
        self.base_url = (base_url or SETTINGS.ollama_base_url).rstrip("/")
        self.model = model or SETTINGS.ollama_model
        self.timeout = timeout

    def generate_json(self, system: str, prompt: str) -> LLMResult:
        payload = {
            "model": self.model,
            "prompt": f"{system}\n\n{prompt}\n\nReturn only valid JSON.",
            "stream": False,
            "options": {"temperature": 0.1, "num_ctx": 4096},
        }
        request = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
            body = json.loads(raw)
            text = str(body.get("response", "")).strip()
            return LLMResult(True, text, _safe_json_object(text))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            return LLMResult(False, "", {}, str(exc))


def _safe_json_object(text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                parsed = json.loads(text[start : end + 1])
                return parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                return {}
    return {}
