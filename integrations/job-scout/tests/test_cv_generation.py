"""Server-side curriculum CLI adapter: validation, isolation, and downloads."""

from __future__ import annotations

import os
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

import job_scout.cv_generation as cvg


def _repository(tmp_path: Path) -> Path:
    repository = tmp_path / "curriculum"
    (repository / "scripts").mkdir(parents=True)
    (repository / "scripts" / "tailor_cv.py").write_text("# test fixture\n", encoding="utf-8")
    return repository


def _settings(repository: Path, key: str = "server-secret-key") -> SimpleNamespace:
    return SimpleNamespace(
        cv_repository_path=repository,
        openai_api_key=SecretStr(key),
        openai_model="gpt-test",
        cv_generation_timeout_seconds=420,
    )


def _successful_runner(repository: Path, seen: list[dict] | None = None):
    def run(command, **kwargs):
        year = command[command.index("--year") + 1]
        slug = command[command.index("--slug") + 1]
        source = repository / "cv" / "applications" / year / slug
        source.mkdir(parents=True)
        tex = source / "CV_example_role.tex"
        tex.write_text("\\documentclass{moderncv}\n", encoding="utf-8")
        (source / "tailoring_notes.md").write_text("# Notes\n", encoding="utf-8")
        if "--build" in command:
            dist = repository / "dist" / "applications" / year
            dist.mkdir(parents=True, exist_ok=True)
            (dist / tex.with_suffix(".pdf").name).write_bytes(b"%PDF-1.4\n")
        if seen is not None:
            seen.append({"command": list(command), "kwargs": kwargs, "job_file": Path(command[2])})
        stdout = """CV family ranking:
  ml-engineering                12.0  pytorch, mlops
  applied-ai-llm                 5.0  llm
Selected base: cv/short/ml-engineering/CV_ml_engineering.tex
Wrote: source.tex
"""
        return subprocess.CompletedProcess(command, 0, stdout, "")

    return run


@pytest.fixture(autouse=True)
def _empty_registry():
    cvg.clear_generation_registry()
    yield
    cvg.clear_generation_registry()


def test_ai_command_construction_never_contains_api_key(tmp_path):
    repository = _repository(tmp_path)
    request = cvg.CVGenerationRequest(
        "Need production ML and PyTorch",
        company="Example; rm -rf /",
        role="Staff ML Engineer",
        mode="ai",
        base_family="ml-engineering",
        model="gpt-test",
        year=2026,
        build_pdf=True,
    )
    command = cvg.build_command(repository, tmp_path / "job.txt", request, "safe-abc123")

    assert command[:3] == ["python3", str(repository / "scripts" / "tailor_cv.py"), str(tmp_path / "job.txt")]
    assert command[command.index("--company") + 1] == "Example; rm -rf /"
    assert "--select-only" not in command
    assert "--base" in command and "--model" in command and "--build" in command
    assert "server-secret-key" not in command


def test_offline_command_explicitly_selects_only(tmp_path):
    request = cvg.CVGenerationRequest("job", mode="offline", build_pdf=False)
    command = cvg.build_command(tmp_path, tmp_path / "job.txt", request, "safe-abc123")
    assert "--select-only" in command
    assert "--build" not in command


def test_ai_mode_fails_before_subprocess_without_api_key(tmp_path, monkeypatch):
    repository = _repository(tmp_path)
    monkeypatch.setattr(cvg, "get_settings", lambda: _settings(repository, key=""))
    called = False

    def forbidden(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(cvg.subprocess, "run", forbidden)
    with pytest.raises(cvg.CVGenerationConfigurationError, match="OPENAI_API_KEY"):
        cvg.generate_cv(cvg.CVGenerationRequest("A real job description", mode="ai"))
    assert called is False


@pytest.mark.parametrize(
    ("generation_request", "message"),
    [
        (cvg.CVGenerationRequest(""), "required"),
        (cvg.CVGenerationRequest("x" * 80_001), "80,000"),
        (cvg.CVGenerationRequest("job", base_family="../../secret.tex"), "not supported"),
        (cvg.CVGenerationRequest("job", year=1999), "between 2000 and 2100"),
        (cvg.CVGenerationRequest("job", company="x" * 161), "160"),
    ],
)
def test_request_validation(generation_request, message):
    with pytest.raises(cvg.CVGenerationValidationError, match=message):
        cvg.validate_request(generation_request)


def test_success_parses_files_scores_and_cleans_temporary_job(tmp_path, monkeypatch):
    repository = _repository(tmp_path)
    seen: list[dict] = []
    monkeypatch.setattr(cvg, "get_settings", lambda: _settings(repository))
    monkeypatch.setattr(cvg.subprocess, "run", _successful_runner(repository, seen))

    result = cvg.generate_cv(
        cvg.CVGenerationRequest("Need production ML and PyTorch", company="Example", role="Staff MLE", year=2026)
    )

    assert result.selected_family == "ml-engineering"
    assert cvg._SAFE_SLUG.fullmatch(result.application_slug)
    assert result.rankings[0] == cvg.FamilyScore("ml-engineering", 12.0, ("pytorch", "mlops"))
    assert result.tex_filename == "CV_example_role.tex"
    assert result.notes_filename == "tailoring_notes.md"
    assert result.pdf_filename == "CV_example_role.pdf"
    assert not seen[0]["job_file"].exists()
    assert seen[0]["kwargs"]["cwd"] == repository
    assert seen[0]["kwargs"]["capture_output"] is True
    assert "shell" not in seen[0]["kwargs"]
    assert seen[0]["kwargs"]["env"]["OPENAI_API_KEY"] == "server-secret-key"
    assert "server-secret-key" not in seen[0]["command"]


def test_offline_mode_does_not_pass_openai_key_in_environment(tmp_path, monkeypatch):
    repository = _repository(tmp_path)
    seen: list[dict] = []
    monkeypatch.setattr(cvg, "get_settings", lambda: _settings(repository))
    monkeypatch.setattr(cvg.subprocess, "run", _successful_runner(repository, seen))

    cvg.generate_cv(cvg.CVGenerationRequest("job", mode="offline", build_pdf=False))

    assert "--select-only" in seen[0]["command"]
    assert "OPENAI_API_KEY" not in seen[0]["kwargs"]["env"]


def test_subprocess_failure_redacts_key_and_temp_path(tmp_path, monkeypatch, capsys):
    repository = _repository(tmp_path)
    seen_job: list[Path] = []
    monkeypatch.setattr(cvg, "get_settings", lambda: _settings(repository))

    def fail(command, **kwargs):
        seen_job.append(Path(command[2]))
        return subprocess.CompletedProcess(command, 1, "", f"error: server-secret-key at {command[2]}")

    monkeypatch.setattr(cvg.subprocess, "run", fail)
    with pytest.raises(cvg.CVGenerationError) as caught:
        cvg.generate_cv(cvg.CVGenerationRequest("job"))
    assert "server-secret-key" not in str(caught.value)
    assert str(seen_job[0]) not in str(caught.value)
    assert not seen_job[0].exists()
    captured = capsys.readouterr()
    assert "server-secret-key" not in captured.out + captured.err


def test_subprocess_timeout_is_safe_and_cleans_temp_file(tmp_path, monkeypatch):
    repository = _repository(tmp_path)
    seen_job: list[Path] = []
    monkeypatch.setattr(cvg, "get_settings", lambda: _settings(repository))

    def timeout(command, **kwargs):
        seen_job.append(Path(command[2]))
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(cvg.subprocess, "run", timeout)
    with pytest.raises(cvg.CVGenerationTimeoutError, match="420-second"):
        cvg.generate_cv(cvg.CVGenerationRequest("job"))
    assert not seen_job[0].exists()


def test_unique_slugs_are_safe_and_do_not_collide():
    with ThreadPoolExecutor(max_workers=8) as pool:
        slugs = list(pool.map(lambda _: cvg.unique_slug("ACME / Labs", "Staff AI & ML"), range(50)))
    assert len(set(slugs)) == 50
    assert all(cvg._SAFE_SLUG.fullmatch(slug) for slug in slugs)


def test_concurrent_generations_do_not_overwrite(tmp_path, monkeypatch):
    repository = _repository(tmp_path)
    seen: list[dict] = []
    monkeypatch.setattr(cvg, "get_settings", lambda: _settings(repository))
    monkeypatch.setattr(cvg.subprocess, "run", _successful_runner(repository, seen))
    request = cvg.CVGenerationRequest("job", mode="offline", year=2026, build_pdf=False)

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(cvg.generate_cv, [request] * 8))

    slugs = [item["command"][item["command"].index("--slug") + 1] for item in seen]
    assert len(set(slugs)) == 8
    assert len({result.request_id for result in results}) == 8


def test_downloads_are_token_authorized_and_request_scoped(tmp_path, monkeypatch):
    repository = _repository(tmp_path)
    monkeypatch.setattr(cvg, "get_settings", lambda: _settings(repository))
    monkeypatch.setattr(cvg.subprocess, "run", _successful_runner(repository))
    first = cvg.generate_cv(cvg.CVGenerationRequest("job one", mode="offline", build_pdf=True))
    second = cvg.generate_cv(cvg.CVGenerationRequest("job two", mode="offline", build_pdf=True))

    path, filename = cvg.resolve_download(first.request_id, first.download_token, "tex")
    assert path.is_file() and filename == first.tex_filename
    pdf_path, pdf_filename = cvg.resolve_download(first.request_id, first.download_token, "pdf")
    assert pdf_path.is_file() and pdf_filename == first.pdf_filename
    assert repository not in pdf_path.parents  # immutable per-request staging, not shared dist
    with pytest.raises(cvg.CVGenerationError):
        cvg.resolve_download(first.request_id, second.download_token, "tex")
    with pytest.raises(cvg.CVGenerationError):
        cvg.resolve_download("../../etc", first.download_token, "tex")
    with pytest.raises(cvg.CVGenerationError):
        cvg.resolve_download(first.request_id, first.download_token, "../../passwd")


def test_fastapi_download_route_uses_registry_authorization(tmp_path, monkeypatch):
    import job_scout.api as api_module

    repository = _repository(tmp_path)
    monkeypatch.setattr(cvg, "get_settings", lambda: _settings(repository))
    monkeypatch.setattr(cvg.subprocess, "run", _successful_runner(repository))
    result = cvg.generate_cv(cvg.CVGenerationRequest("job", mode="offline", build_pdf=True))
    app = api_module.create_app()
    endpoint = next(
        route.endpoint for route in app.routes if getattr(route, "path", "") == "/api/download/{request_id}/{kind}"
    )

    response = endpoint(result.request_id, "pdf", result.download_token)
    assert Path(response.path).is_file()
    assert response.filename == result.pdf_filename
    with pytest.raises(api_module.HTTPException) as caught:
        endpoint(result.request_id, "pdf", "wrong-token")
    assert caught.value.status_code == 404


@pytest.mark.integration
@pytest.mark.skipif(os.environ.get("RUN_CV_INTEGRATION") != "1", reason="set RUN_CV_INTEGRATION=1 to write curriculum artifacts")
def test_real_curriculum_cli_offline_selection(monkeypatch):
    repository = Path(os.environ.get("CV_REPOSITORY_PATH", "private/curriculum"))
    if not (repository / "scripts" / "tailor_cv.py").is_file():
        pytest.skip("curriculum repository is not available")
    monkeypatch.setattr(cvg, "get_settings", lambda: _settings(repository, key=""))
    result = cvg.generate_cv(
        cvg.CVGenerationRequest(
            "Production machine learning role requiring PyTorch, MLOps, deployment, and monitoring.",
            company="Pytest Integration",
            role="Machine Learning Engineer",
            mode="offline",
            year=2026,
            build_pdf=False,
        )
    )
    source_dir = repository / "cv" / "applications" / "2026" / result.application_slug
    try:
        assert result.selected_family == "ml-engineering"
        assert (source_dir / result.tex_filename).is_file()
        assert (source_dir / result.notes_filename).is_file()
        assert result.pdf_filename is None
    finally:
        shutil.rmtree(source_dir, ignore_errors=True)
