#!/usr/bin/env python3
"""Fail when Git would publish private data, credentials, or local paths."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_PRIVATE = {"private/README.md"}
SENSITIVE_SUFFIXES = {".docx", ".key", ".pem", ".sqlite", ".sqlite3", ".xlsx"}
ALLOWED_EXAMPLE_PDFS = {
    'private_example/curriculum/dist/short/senior-data-science/CV_senior_data_science.pdf',
    'private_example/curriculum/dist/short/ml-engineering/CV_ml_engineering.pdf',
    'private_example/curriculum/dist/short/applied-ai-llm/CV_applied_ai_llm.pdf',
    'private_example/curriculum/dist/short/technical-leadership/CV_technical_leadership.pdf',
    'private_example/curriculum/dist/short/analytics-decision-science/CV_analytics_decision_science.pdf',
    'private_example/curriculum/dist/short/research-scientific-ml/CV_research_scientific_ml.pdf',
    'integrations/job-scout/data/fixture_cvs/junior_ds_us.pdf',
    'integrations/job-scout/data/fixture_cvs/senior_mle_eu.pdf',
    'integrations/job-scout/data/fixture_cvs/career_changer_in.pdf',
    'integrations/job-scout/data/fixture_cvs/german_pm_de.pdf',
}
TEXT_SUFFIXES = {
    "",
    ".css",
    ".html",
    ".ipynb",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".py",
    ".sh",
    ".tex",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
CONTENT_RULES = {
    "absolute home path": re.compile(r"/(?:home|Users)/[A-Za-z0-9._-]+/"),
    "workspace-specific absolute path": re.compile("/store/" + r"career(?:/|\b)"),
    "populated secret": re.compile(
        r"(?m)^[ \t]*(?:export[ \t]+)?"
        r"(?:OPENAI_API_KEY|OPIK_API_KEY|TYPESAFE_API_KEY|JSEARCH_API_KEY)"
        r"[ \t]*=[ \t]*(?!\.\.\.|$|#)[^\s#]+"
    ),
}


def public_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [item.decode("utf-8") for item in result.stdout.split(b"\0") if item]


def main() -> int:
    problems: list[str] = []
    files = public_files()
    for relative in files:
        path = ROOT / relative
        if relative.startswith("private/") and relative not in ALLOWED_PRIVATE:
            problems.append(f"tracked private path: {relative}")
        if path.suffix.casefold() in SENSITIVE_SUFFIXES:
            problems.append(f"tracked sensitive file type: {relative}")
        if path.suffix.casefold() == '.pdf' and relative not in ALLOWED_EXAMPLE_PDFS:
            problems.append(f"unreviewed PDF: {relative}")
        if not path.is_file() or path.suffix.casefold() not in TEXT_SUFFIXES:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for label, pattern in CONTENT_RULES.items():
            if pattern.search(content):
                problems.append(f"{label}: {relative}")

    if problems:
        print("Public-tree check failed:", file=sys.stderr)
        for problem in sorted(set(problems)):
            print(f"- {problem}", file=sys.stderr)
        return 1
    print(f"Public-tree check passed ({len(files)} tracked or unignored files).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
