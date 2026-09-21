"""LaTeX renderer: escaping, dual-document compilation, and degradation."""

from __future__ import annotations

import shutil

import pytest

from job_scout.graph.schemas import CVContent, ExperienceEntry, TailoredBullet, TailoringPack
from job_scout.renderer import (
    OVERLEAF_HINT,
    latex_escape,
    pdflatex_path,
    render_application_pdfs,
    render_cover_letter_tex,
    render_pdf,
    render_tex,
)

_HAS_COMPILER = shutil.which("pdflatex") is not None or shutil.which("tectonic") is not None


@pytest.mark.parametrize(
    ("raw", "escaped"),
    [
        ("A & B", r"A \& B"),
        ("100%", r"100\%"),
        ("$5", r"\$5"),
        ("#1", r"\#1"),
        ("snake_case", r"snake\_case"),
        ("{braces}", r"\{braces\}"),
        ("~home", r"\textasciitilde{}home"),
        ("x^2", r"x\textasciicircum{}2"),
        ("a\\b", r"a\textbackslash{}b"),
        ("plain text", "plain text"),
    ],
)
def test_latex_escape(raw, escaped):
    assert latex_escape(raw) == escaped


def test_latex_escape_backslash_then_special_chars():
    # A backslash followed by an escapable char must not double-escape.
    assert latex_escape("\\&") == r"\textbackslash{}\&"


def _cv() -> CVContent:
    return CVContent(
        headline="ML Engineer & Data Scientist",  # deliberate LaTeX special char
        summary="Ships models with 100% test coverage.",
        experience=[
            ExperienceEntry(
                role="ML Engineer",
                company="C&A Analytics",
                dates="2020-2026",
                bullets=[TailoredBullet(text="Cut costs by 20% via smart_caching", corpus_ref="cv-bullet-001")],
            )
        ],
        skills=["Python", "SQL", "CI/CD"],
        education=["M.Sc. Computer Science, TU Munich"],
    )


def test_render_tex_escapes_user_content():
    tex = render_tex(_cv(), candidate_name="Jane & Co")
    assert r"Jane \& Co" in tex
    assert r"ML Engineer \& Data Scientist" in tex
    assert r"C\&A Analytics" in tex
    assert r"20\%" in tex
    assert r"smart\_caching" in tex
    # No unescaped specials sneak through from user values.
    assert "Jane & Co" not in tex


def test_render_tex_is_a_complete_document():
    tex = render_tex(_cv(), candidate_name="Jane")
    assert tex.strip().startswith(r"\documentclass")
    assert tex.strip().endswith(r"\end{document}")
    assert r"\begin{itemize}" in tex


def test_render_tex_handles_empty_sections():
    cv = CVContent(headline="X", summary="Y")
    tex = render_tex(cv, candidate_name="Jane")
    assert "Experience" not in tex
    assert "Skills" not in tex
    assert "Education" not in tex


def test_render_pdf_degrades_without_a_compiler(tmp_path, monkeypatch):
    import job_scout.renderer as renderer_mod

    monkeypatch.setattr(renderer_mod, "tectonic_path", lambda: None)
    monkeypatch.setattr(renderer_mod, "pdflatex_path", lambda: None)
    result = render_pdf(_cv(), "Jane", tmp_path)
    assert result.tex_path.exists()
    assert result.pdf_path is None
    assert result.message == OVERLEAF_HINT


@pytest.mark.compile
@pytest.mark.skipif(not _HAS_COMPILER, reason="no LaTeX compiler installed")
def test_render_pdf_compiles_with_available_compiler(tmp_path):
    result = render_pdf(_cv(), "Jane & Co", tmp_path)
    assert result.pdf_path is not None
    assert result.pdf_path.exists()
    assert result.pdf_path.stat().st_size > 1000


def test_cover_letter_tex_escapes_and_separates_paragraphs():
    tex = render_cover_letter_tex(
        "Dear A&B,\n\nI improved quality by 20%.\n\nSincerely,\nJane & Co", "Jane & Co", headline="ML & AI"
    )
    assert r"Jane \& Co" in tex
    assert r"Dear A\&B," in tex
    assert r"20\%." in tex
    assert tex.index(r"Dear A\&B,") < tex.index(r"I improved quality by 20\%.")
    assert r"Sincerely,\\[5pt]Jane \& Co" in tex


@pytest.mark.compile
@pytest.mark.skipif(not _HAS_COMPILER, reason="no LaTeX compiler installed")
def test_render_application_compiles_both_pdfs(tmp_path):
    from pypdf import PdfReader

    pack = TailoringPack(
        cv=_cv(),
        cover_letter="Dear Hiring Team,\n\nI build grounded ML systems.\n\nSincerely,\nJane",
    )
    rendered = render_application_pdfs(pack, "Jane & Co", tmp_path, location="Argentina")
    assert rendered.cv.pdf_path is not None and rendered.cv.pdf_path.exists()
    assert rendered.cover_letter.pdf_path is not None and rendered.cover_letter.pdf_path.exists()
    assert rendered.message == ""
    assert len(PdfReader(rendered.cv.pdf_path).pages) <= 2
    assert len(PdfReader(rendered.cover_letter.pdf_path).pages) == 1
    assert pdflatex_path() or shutil.which("tectonic")
