"""The download-only API enforces request and token scoping."""

from pathlib import Path

import pytest
from fastapi import HTTPException

from job_scout.api import create_app
from job_scout.artifact_store import ArtifactAccessError, clear_registry, register_files, resolve_file


@pytest.fixture(autouse=True)
def _clean_registry():
    clear_registry()
    yield
    clear_registry()


def _download_endpoint():
    app = create_app()
    return next(route.endpoint for route in app.routes if getattr(route, "path", "") == "/api/download/{request_id}/{kind}")


def test_download_returns_only_the_registered_file(tmp_path: Path):
    pdf = tmp_path / "application.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    bundle = register_files({"pdf": pdf})

    response = _download_endpoint()(bundle.request_id, "pdf", bundle.token)

    assert Path(response.path) == pdf.resolve()
    assert response.filename == "application.pdf"
    assert response.media_type == "application/pdf"


def test_download_rejects_wrong_token_and_cross_request_access(tmp_path: Path):
    first_file = tmp_path / "first.pdf"
    second_file = tmp_path / "second.pdf"
    first_file.write_bytes(b"first")
    second_file.write_bytes(b"second")
    first = register_files({"pdf": first_file})
    second = register_files({"pdf": second_file})

    endpoint = _download_endpoint()
    with pytest.raises(HTTPException) as wrong_token:
        endpoint(first.request_id, "pdf", "wrong")
    with pytest.raises(HTTPException) as cross_request:
        endpoint(first.request_id, "pdf", second.token)
    assert wrong_token.value.status_code == 404
    assert cross_request.value.status_code == 404


@pytest.mark.parametrize("kind", ["../pdf", "../../etc/passwd", "PDF", ""])
def test_artifact_registry_rejects_path_traversal_and_invalid_kinds(tmp_path: Path, kind: str):
    pdf = tmp_path / "application.pdf"
    pdf.write_bytes(b"pdf")
    bundle = register_files({"pdf": pdf})

    with pytest.raises(ArtifactAccessError):
        resolve_file(bundle.request_id, bundle.token, kind)


def test_duplicate_request_ids_are_refused(tmp_path: Path):
    pdf = tmp_path / "application.pdf"
    pdf.write_bytes(b"pdf")
    register_files({"pdf": pdf}, request_id="same")
    with pytest.raises(ArtifactAccessError, match="already exists"):
        register_files({"pdf": pdf}, request_id="same")
