"""Regression checks for one fictional candidate across the six public CVs.

These checks guard known invariants, not the truth of arbitrary natural-language
claims. PDF checks use the shipped previews and need no LaTeX installation.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import unicodedata
from pathlib import Path

import pytest
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[3]
EXAMPLE = ROOT / "private_example"
CURRICULUM = EXAMPLE / "curriculum"
PROFILE = json.loads((EXAMPLE / "profile.json").read_text(encoding="utf-8"))
SPEC = importlib.util.spec_from_file_location("example_cv_selector", ROOT / "packages/cv-engine/tailor_cv.py")
assert SPEC and SPEC.loader
selector = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = selector
SPEC.loader.exec_module(selector)


def normalized(text: str) -> str:
    punctuation = str.maketrans({"–": "-", "—": "-", "’": "'", "‘": "'"})
    return " ".join(unicodedata.normalize("NFKC", text).translate(punctuation).split())


def source_for(family) -> str:
    return (CURRICULUM / family.source).read_text(encoding="utf-8")


def test_shared_fictional_identity_and_history():
    preamble = (CURRICULUM / "content/shared/preamble.tex").read_text(encoding="utf-8")
    history = (CURRICULUM / "content/shared/experience_compact.tex").read_text(encoding="utf-8")
    education = (CURRICULUM / "content/shared/education_links.tex").read_text(encoding="utf-8")
    facts = " ".join(fact["statement"] for fact in PROFILE["facts"])

    assert PROFILE["name"] == "John Doe"
    assert PROFILE["location"] == "Rosario, Argentina"
    assert r"\name{John}{Doe}" in preamble
    assert r"\address{Rosario}{Argentina}{}" in preamble
    assert r"\email{john.doe@example.com}" in preamble
    assert r"\cventry{2022--present}{ML Engineer}{Northstar Transit Labs (fictional)}" in history
    assert r"\cventry{2018--2022}{Data Scientist}{Meridian Analytics (fictional)}" in history
    assert r"\cventry{2017--2018}{Independent research project}{Example University (fictional)}" in history
    assert r"\cventry{2017}{BSc in Computer Science}{Example University (fictional)}" in education
    for fragment in ("Northstar Transit Labs from 2022", "Meridian Analytics from 2018 to 2022",
                     "Example University from 2017 to 2018", "BSc in Computer Science", "internally"):
        assert fragment in facts
    assert "35% in a fictional internal pilot" in facts


@pytest.mark.parametrize("family", selector.FAMILIES, ids=lambda family: family.key)
def test_variants_preserve_shared_facts_and_pilot_scope(family):
    source = source_for(family)
    for shared in ("preamble", "experience_compact", "education_links"):
        assert source.count(r"\input{content/shared/" + shared + "}") == 1
    # Positioning may change; candidate identity and employment entries are shared.
    assert not re.search(r"\\(?:name|address|email|homepage|cventry)\b", source)
    headline = source.splitlines()[0]
    assert not any(title in headline for title in ("Technical Lead", "Scientific ML", "Senior Data Scientist"))
    for line in source.splitlines():
        for number in re.findall(r"(\d+(?:\.\d+)?)\\%", line):
            assert number == "35"
            assert "pilot" in line.casefold()
    selector.validate_tex(source, source)


@pytest.mark.parametrize("family", selector.FAMILIES, ids=lambda family: family.key)
def test_each_family_receives_common_skills_and_evidence(family, monkeypatch):
    monkeypatch.setattr(selector, "REPO_ROOT", CURRICULUM)
    context = selector.read_context(CURRICULUM / family.source)
    skills = " ".join(fact["statement"] for fact in PROFILE["facts"] if fact["category"] == "skills")
    for skill in ("Python", "FastAPI", "React", "SQL", "PyTorch", "model evaluation", "production observability"):
        assert skill in skills
        assert skill in context
    for boundary in ("not a model-accuracy improvement", "measurement period are unspecified",
                     "formal Technical", "prompt evaluation", "peer-reviewed publication"):
        assert boundary in context


@pytest.mark.parametrize("family", selector.FAMILIES, ids=lambda family: family.key)
def test_distributed_pdf_matches_candidate_and_current_positioning(family):
    source_path = Path(family.source)
    pdf = CURRICULUM / "dist/short" / family.key / source_path.with_suffix(".pdf").name
    reader = PdfReader(pdf)
    assert len(reader.pages) == 1
    assert reader.metadata.author == PROFILE["name"]
    text = normalized(reader.pages[0].extract_text())
    for fragment in ("John Doe", "Rosario", "Argentina", "john.doe@example.com", "example.com/john-doe",
                     "Northstar Transit Labs (fictional)", "2022-present", "ML Engineer",
                     "Meridian Analytics (fictional)", "2018-2022", "Data Scientist",
                     "Independent research project", "2017-2018", "BSc in Computer Science",
                     "Example University (fictional)", "35%", "fictional internal pilot"):
        assert fragment in text
    assert set(re.findall(r"(\d+(?:\.\d+)?)%", text)) == {"35"}

    source = source_for(family)
    headline = source.splitlines()[0].removeprefix(r"\def\cvheadline{").removesuffix("}").replace(r"\&", "&")
    assert normalized(headline) in normalized(reader.metadata.title)
    summary = source.split(r"\small", 1)[1].split(r"\section", 1)[0].strip()
    assert normalized(summary) in text


def test_family_summaries_are_distinct():
    summaries = [source_for(family).split(r"\small", 1)[1].split(r"\section", 1)[0].strip()
                 for family in selector.FAMILIES]
    assert len(summaries) == len(set(summaries)) == 6
