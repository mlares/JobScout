from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CandidateProfile:
    data: dict[str, Any]

    @property
    def name(self) -> str:
        return str(self.data["name"])

    @property
    def target_words(self) -> int:
        preferences = self.data.get("preferences", {})
        return int(preferences.get("target_words", 350))

    @property
    def location(self) -> str:
        return str(self.data.get("location", ""))

    @property
    def headline(self) -> str:
        return str(self.data.get("headline", ""))

    @property
    def chat_url(self) -> str:
        for link in self.data.get("links", []):
            if not isinstance(link, dict):
                continue
            label = str(link.get("label", "")).casefold()
            url = link.get("url")
            if isinstance(url, str) and url and ("assistant" in label or "chat" in label):
                return url
        raise ValueError("Profile must contain a chat or assistant URL for the PDF QR code.")

    def as_prompt_json(self) -> str:
        return json.dumps(self.data, ensure_ascii=False, indent=2)


def load_profile(path: Path) -> CandidateProfile:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Profile not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in profile {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("Profile must be a JSON object.")
    if not isinstance(data.get("name"), str) or not data["name"].strip():
        raise ValueError("Profile must contain a non-empty 'name'.")
    facts = data.get("facts")
    if not isinstance(facts, list) or not facts:
        raise ValueError("Profile must contain a non-empty 'facts' list.")
    for index, fact in enumerate(facts):
        if not isinstance(fact, dict) or not isinstance(fact.get("statement"), str):
            raise ValueError(f"Profile fact {index} must contain a string 'statement'.")
    return CandidateProfile(data)
