#!/usr/bin/env python3
"""Rewrite known internal references after importing private workspace data."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APPLICATIONS = ROOT / "private" / "applications"
REPLACEMENTS = {
    "../../../tools/cover-letters/": "../../../cover-letter/",
    "tools/career-app/data/career.sqlite3": "private/career-app/data/career.sqlite3",
}


def rewrite(value):
    if isinstance(value, str):
        for old, new in REPLACEMENTS.items():
            if value.startswith(old):
                return new + value[len(old):]
        return value
    if isinstance(value, list):
        return [rewrite(item) for item in value]
    if isinstance(value, dict):
        return {key: rewrite(item) for key, item in value.items()}
    return value


def main() -> None:
    changed = 0
    for path in APPLICATIONS.rglob("application.json"):
        original = json.loads(path.read_text(encoding="utf-8"))
        migrated = rewrite(original)
        if migrated != original:
            path.write_text(json.dumps(migrated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            changed += 1
    index_path = APPLICATIONS / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    for entry in index.get("applications", []):
        for field in ("path", "metadata"):
            value = entry.get(field)
            if isinstance(value, str) and value.startswith("applications/"):
                entry[field] = "private/" + value
                changed += 1
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"rewrote {changed} private application metadata files")


if __name__ == "__main__":
    main()
