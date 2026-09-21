"""App handler wiring: on_find/on_tailor generators (Gradio-free, mocked runner)."""

from __future__ import annotations

from dataclasses import replace

import job_scout.app as app_mod
from job_scout.app import CV_GENERATE_NEW, on_find, on_tailor, on_zip, reset
from job_scout.cv_generation import CVGenerationError, CVGenerationResult, FamilyScore
from job_scout.graph.schemas import CVContent, RankedJob, TailoringPack
from job_scout.runner import RunResult, TailorResult
from tests.conftest import make_job


def _search_result() -> RunResult:
    ranked = [RankedJob(job=make_job("j1", "Data Scientist", "Acme"), fit_score=88, fit_explanation="fits")]
    return RunResult(ranked_jobs=ranked, jobs_sources=["cache"], n_jobs_ranked=1)


def _tailor_result(flags: int = 0) -> TailorResult:
    pack = TailoringPack(cv=CVContent(headline="DS", summary="s"), cover_letter="Dear team,", honesty_note="Gap: SQL.")
    return TailorResult(pack=pack, fabrication_flags=flags)


def _fake_stream(result):
    def stream(*args, **kwargs):
        yield ("status", "working…")
        yield ("result", result)

    return stream


def _generation_result(mode="offline") -> CVGenerationResult:
    return CVGenerationResult(
        request_id="request123",
        download_token="token123",
        application_slug="acme-data-scientist-abc123",
        mode=mode,
        selected_family="ml-engineering",
        rankings=(FamilyScore("ml-engineering", 12.0, ("pytorch", "mlops")),),
        tex_filename="CV_example.tex",
        notes_filename="tailoring_notes.md",
        pdf_filename="CV_example.pdf",
    )


def _mock_tailor_dependencies(monkeypatch, result=None, generation=None):
    job = make_job("j1", "Data Scientist", "Acme")
    job.description = "Original retrieved job description requiring python and sql."
    monkeypatch.setattr(app_mod, "_retrieved_job", lambda thread_id, job_id: job)
    monkeypatch.setattr(app_mod, "stream_tailor", _fake_stream(result or _tailor_result()))
    monkeypatch.setattr(app_mod, "generate_cv", lambda request: generation or _generation_result())
    monkeypatch.setattr(
        app_mod,
        "_cover_letter_download",
        lambda pack, profile: ("http://localhost:8000/api/download/cover123/cover-letter?token=cover-token", ""),
    )
    return job


def test_on_find_populates_job_dropdown(monkeypatch, sample_profile):
    monkeypatch.setattr(app_mod, "stream_search", _fake_stream(_search_result()))
    final = list(on_find("cv text", sample_profile, "t1", [], "staff machine learning engineer"))[-1]
    select = final[4]
    assert select["choices"] == [("Data Scientist — Acme (fit 88)", "j1")]
    assert select["visible"] is True


def test_results_paginate_and_filter_by_listing_source():
    ranked = [
        RankedJob(
            job=make_job(f"j{i}", f"Role {i}", f"Company {i}", source="adzuna" if i % 2 else "jsearch"),
            fit_score=90 - i,
            fit_explanation="fits",
        )
        for i in range(12)
    ]
    result = RunResult(ranked_jobs=ranked)

    first = app_mod._results_page(result, 1, app_mod.ALL_SOURCES)
    third = app_mod._results_page(result, 3, app_mod.ALL_SOURCES)
    filtered = app_mod.on_results_page(result, 3, "adzuna")

    assert len(first[1]["choices"]) == 5 and first[2] == "Page 1 of 3 · 12 jobs"
    assert len(third[1]["choices"]) == 2 and third[2] == "Page 3 of 3 · 12 jobs"
    assert filtered[3] == 1  # changing source resets pagination
    assert filtered[2] == "Page 1 of 2 · 6 jobs"
    assert all(int(value[1:]) % 2 == 1 for _, value in filtered[1]["choices"])


def test_empty_results_do_not_blame_resume_detail():
    html = app_mod._results_html(RunResult())
    assert "No eligible matches" in html
    assert "resume with more detail" not in html


def test_on_tailor_renders_pack_and_honesty_note(monkeypatch, sample_profile):
    _mock_tailor_dependencies(monkeypatch)
    final = list(on_tailor("j1", "t1", None, sample_profile))[-1]
    html = final[2]
    assert "Dear team," in html
    assert "Honesty note" in html
    assert "traced back to your CV" in html  # zero flags → quiet green line
    assert "Download cover letter in PDF" in html
    assert "Download tailored CV in PDF" in html
    assert html.index("Cover letter") < html.index("Download cover letter in PDF") < html.index("Dear team,")
    assert html.index("Tailored CV") < html.index("Download tailored CV in PDF")
    assert "/api/download/request123/pdf?token=token123" in html
    assert final[4]["visible"] is False and final[5]["visible"] is False


def test_on_tailor_shows_fabrication_warning(monkeypatch, sample_profile):
    result = _tailor_result(flags=2)
    _mock_tailor_dependencies(monkeypatch, result=result)
    final = list(on_tailor("j1", "t1", None, sample_profile))[-1]
    assert "could not be verified against your CV" in final[2]


def test_on_tailor_without_selection_stays_on_results(monkeypatch, sample_profile):
    monkeypatch.setattr(app_mod.gr, "Warning", lambda *a, **k: None)
    final = list(on_tailor(None, "t1", None, sample_profile))[-1]
    assert final[0]["visible"] is True  # page_results stays visible
    assert final[1]["visible"] is False


def test_on_tailor_renders_graceful_error(monkeypatch, sample_profile):
    result = replace(TailorResult(), errors=["tailor: no search state on this thread — run a job search first"])
    _mock_tailor_dependencies(monkeypatch, result=result)
    final = list(on_tailor("j1", "t1", None, sample_profile))[-1]
    assert "Could not tailor this job" in final[2]
    assert "run a job search first" in final[2]


def test_reset_issues_fresh_thread_id():
    first, second = reset(), reset()
    thread_index = 9  # position of thread_id in the reset outputs
    assert first[thread_index] != second[thread_index]


def test_on_zip_passes_path_through():
    assert on_zip("/tmp/export.zip") == "/tmp/export.zip"
    assert on_zip(None) is None


def test_on_tailor_uses_retrieved_description_for_closest_match(monkeypatch, sample_profile):
    captured = []
    job = _mock_tailor_dependencies(monkeypatch)
    monkeypatch.setattr(app_mod, "generate_cv", lambda request: captured.append(request) or _generation_result())

    list(on_tailor("j1", "t1", None, sample_profile))

    request = captured[0]
    assert request.job_description == job.description
    assert request.company == job.company and request.role == job.title
    assert request.mode == "offline" and request.build_pdf is True


def test_on_tailor_can_generate_new_cv_with_selected_family(monkeypatch, sample_profile):
    captured = []
    _mock_tailor_dependencies(monkeypatch, generation=_generation_result("ai"))
    monkeypatch.setattr(app_mod, "generate_cv", lambda request: captured.append(request) or _generation_result("ai"))

    final = list(
        on_tailor("j1", "t1", None, sample_profile, CV_GENERATE_NEW, "applied-ai-llm", "gpt-custom")
    )[-1]

    assert captured[0].mode == "ai"
    assert captured[0].base_family == "applied-ai-llm" and captured[0].model == "gpt-custom"
    assert "Match scores: ml-engineering: 12.0" in final[2]


def test_on_tailor_keeps_cover_letter_when_cv_generation_fails(monkeypatch, sample_profile):
    _mock_tailor_dependencies(monkeypatch)
    monkeypatch.setattr(app_mod, "generate_cv", lambda request: (_ for _ in ()).throw(CVGenerationError("build failed")))

    final = list(on_tailor("j1", "t1", None, sample_profile))[-1]

    assert "Dear team," in final[2]
    assert "Download cover letter in PDF" in final[2]
    assert "CV PDF unavailable: build failed" in final[2]
