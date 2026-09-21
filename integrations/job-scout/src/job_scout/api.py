"""Minimal FastAPI server for capability-scoped generated-file downloads."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from job_scout.artifact_store import ArtifactAccessError, resolve_file

DOWNLOAD_PORT = 8000


def create_app() -> FastAPI:
    """Create the download-only backend; no credentials are exposed here."""
    app = FastAPI(title="Job Scout downloads", docs_url=None, redoc_url=None)

    @app.get("/api/download/{request_id}/{kind}")
    def download(request_id: str, kind: str, token: str = "") -> FileResponse:
        try:
            path, filename = resolve_file(request_id, token, kind)
        except ArtifactAccessError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        media_types = {
            "cover-letter": "application/pdf",
            "pdf": "application/pdf",
            "tex": "application/x-tex",
            "notes": "text/markdown",
        }
        return FileResponse(path, filename=filename, media_type=media_types.get(kind, "application/octet-stream"))

    return app


def serve_in_thread(port: int = DOWNLOAD_PORT) -> None:
    """Serve downloads beside Gradio in the same process and registry."""
    import threading

    import uvicorn

    server = uvicorn.Server(uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True, name="job-scout-downloads").start()


def main() -> None:
    """Run the download API by itself for diagnostics."""
    import uvicorn

    uvicorn.run(create_app(), host="127.0.0.1", port=DOWNLOAD_PORT)


if __name__ == "__main__":
    main()
