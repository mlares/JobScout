"""Safe server-side adapter for the curriculum repository's CV generator.

The curriculum CLI owns CV selection, evidence grounding, LaTeX validation,
and compilation.  This module deliberately does not reproduce any of that
logic; it validates web input, invokes the CLI without a shell, and scopes the
resulting files to an opaque application request.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import threading
from contextlib import nullcontext
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Literal
from uuid import uuid4

from job_scout.artifact_store import clear_registry, register_files, resolve_file
from job_scout.config import get_settings

CV_FAMILIES = (
    "senior-data-science",
    "ml-engineering",
    "applied-ai-llm",
    "technical-leadership",
    "analytics-decision-science",
    "research-scientific-ml",
)
GenerationMode = Literal["ai", "offline"]
DownloadKind = Literal["tex", "notes", "pdf"]

MAX_JOB_DESCRIPTION = 80_000
MAX_COMPANY_LENGTH = 160
MAX_ROLE_LENGTH = 200
_SAFE_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,119}$")
_RANKING_LINE = re.compile(r"^\s+([a-z0-9-]+)\s+([0-9]+(?:\.[0-9]+)?)\s*(.*)$")


class CVGenerationError(RuntimeError):
    """A safe, user-displayable CV generation failure."""


class CVGenerationValidationError(CVGenerationError):
    """Invalid form input."""


class CVGenerationConfigurationError(CVGenerationError):
    """Missing or invalid server configuration."""


class CVGenerationTimeoutError(CVGenerationError):
    """The curriculum process exceeded its deadline."""


@dataclass(frozen=True)
class CVGenerationRequest:
    job_description: str
    company: str = ""
    role: str = ""
    mode: GenerationMode = "ai"
    base_family: str | None = None
    model: str | None = None
    year: int = field(default_factory=lambda: date.today().year)
    build_pdf: bool = True


@dataclass(frozen=True)
class FamilyScore:
    family: str
    score: float
    signals: tuple[str, ...] = ()


@dataclass(frozen=True)
class CVGenerationResult:
    request_id: str
    download_token: str
    application_slug: str
    mode: GenerationMode
    selected_family: str
    rankings: tuple[FamilyScore, ...]
    tex_filename: str
    notes_filename: str
    pdf_filename: str | None

    def download_url(self, kind: DownloadKind, api_origin: str = "http://localhost:8000") -> str:
        from job_scout.artifact_store import DownloadBundle

        return DownloadBundle(self.request_id, self.download_token).url(kind, api_origin)
# The curriculum build script publishes PDFs by filename, not application slug.
# Serialize the build-and-stage window so two identical company/role requests
# can never make one request serve the other's PDF.
_BUILD_LOCK = threading.Lock()


def _clean_text(value: str | None, label: str, maximum: int) -> str:
    text = (value or "").strip()
    if len(text) > maximum:
        raise CVGenerationValidationError(f"{label} must be {maximum:,} characters or fewer.")
    if "\x00" in text:
        raise CVGenerationValidationError(f"{label} contains an invalid null character.")
    return text


def validate_request(request: CVGenerationRequest) -> CVGenerationRequest:
    job = _clean_text(request.job_description, "Job description", MAX_JOB_DESCRIPTION)
    if not job:
        raise CVGenerationValidationError("Job description is required.")
    company = _clean_text(request.company, "Company", MAX_COMPANY_LENGTH)
    role = _clean_text(request.role, "Role", MAX_ROLE_LENGTH)
    if request.mode not in ("ai", "offline"):
        raise CVGenerationValidationError("Mode must be AI tailoring or offline selection.")
    if request.base_family is not None and request.base_family not in CV_FAMILIES:
        raise CVGenerationValidationError("Base CV family is not supported.")
    if request.year < 2000 or request.year > 2100:
        raise CVGenerationValidationError("Year must be between 2000 and 2100.")
    model = _clean_text(request.model, "Model", 100) or None
    return CVGenerationRequest(job, company, role, request.mode, request.base_family, model, request.year, request.build_pdf)


def unique_slug(company: str, role: str) -> str:
    """Return a readable, collision-resistant slug containing safe characters only."""
    stem = re.sub(r"[^a-z0-9]+", "-", f"{company}-{role}".lower()).strip("-")
    stem = (stem[:78].rstrip("-") or "application")
    slug = f"{stem}-{uuid4().hex[:12]}"
    if not _SAFE_SLUG.fullmatch(slug):  # defensive invariant, not user-triggerable
        raise CVGenerationValidationError("Could not create a safe application slug.")
    return slug


def _repository_root(configured: Path) -> Path:
    root = configured.expanduser().resolve()
    script = root / "scripts" / "tailor_cv.py"
    if not root.is_dir() or not script.is_file():
        raise CVGenerationConfigurationError("The configured CV repository is unavailable or incomplete.")
    return root


def _safe_environment(api_key: str, model: str | None, mode: GenerationMode) -> dict[str, str]:
    """Pass only process essentials and the credentials required by this tool."""
    allowed = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT", "WINDIR")
    environment = {name: value for name in allowed if (value := os.environ.get(name))}
    environment["PYTHONIOENCODING"] = "utf-8"
    if mode == "ai":
        environment["OPENAI_API_KEY"] = api_key
    if model:
        environment["OPENAI_MODEL"] = model
    return environment


def build_command(
    repository: Path,
    job_file: Path,
    request: CVGenerationRequest,
    slug: str,
) -> list[str]:
    command = [
        "python3",
        str(repository / "scripts" / "tailor_cv.py"),
        str(job_file),
        "--year",
        str(request.year),
        "--slug",
        slug,
    ]
    if request.company:
        command.extend(("--company", request.company))
    if request.role:
        command.extend(("--role", request.role))
    if request.base_family:
        command.extend(("--base", request.base_family))
    if request.model:
        command.extend(("--model", request.model))
    if request.mode == "offline":
        command.append("--select-only")
    if request.build_pdf:
        command.append("--build")
    return command


def _within(path: Path, parent: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(parent.resolve())
    except ValueError as exc:
        raise CVGenerationError("Generated-file location failed its security check.") from exc
    return resolved


def _parse_rankings(stdout: str) -> tuple[FamilyScore, ...]:
    rankings: list[FamilyScore] = []
    reading = False
    for line in stdout.splitlines():
        if line.strip() == "CV family ranking:":
            reading = True
            continue
        if reading and line.startswith("Selected base:"):
            break
        if reading and (match := _RANKING_LINE.match(line)):
            family, score, raw_signals = match.groups()
            if family in CV_FAMILIES:
                signals = tuple(signal.strip() for signal in raw_signals.split(",") if signal.strip())
                rankings.append(FamilyScore(family, float(score), signals))
    return tuple(rankings)


def _selected_family(stdout: str, requested: str | None, rankings: tuple[FamilyScore, ...]) -> str:
    if requested:
        return requested
    for line in stdout.splitlines():
        if not line.startswith("Selected base:"):
            continue
        selected_path = line.partition(":")[2].strip()
        for family in CV_FAMILIES:
            if f"/{family}/" in f"/{selected_path}":
                return family
    return rankings[0].family if rankings else "unknown"


def _sanitize_failure(stderr: str, repository: Path, temp_path: Path, *sensitive_values: str) -> str:
    detail = next((line.strip() for line in reversed(stderr.splitlines()) if line.strip()), "CV generation failed.")
    detail = detail.replace(str(repository), "CV repository").replace(str(temp_path), "temporary job file")
    for value in sensitive_values:
        if value:
            detail = detail.replace(value, "[redacted]")
    detail = re.sub(r"sk-[A-Za-z0-9_-]+", "[redacted]", detail)
    detail = re.sub(r"(?<!\w)/(?:[^\s/:]+/)*[^\s:]+", "[path]", detail)
    return detail[:800]


def resolve_download(request_id: str, token: str, kind: str) -> tuple[Path, str]:
    """Backward-compatible wrapper around the shared download registry."""
    try:
        return resolve_file(request_id, token, kind)
    except RuntimeError as exc:
        raise CVGenerationError(str(exc)) from exc


def clear_generation_registry() -> None:
    """Test helper; generated source files themselves remain owned by curriculum."""
    clear_registry()


def generate_cv(request: CVGenerationRequest) -> CVGenerationResult:
    """Run the curriculum CLI and register its generated artifacts."""
    request = validate_request(request)
    settings = get_settings()
    repository = _repository_root(settings.cv_repository_path)
    api_key = settings.openai_api_key.get_secret_value()
    if request.mode == "ai" and not api_key:
        raise CVGenerationConfigurationError("AI tailoring requires OPENAI_API_KEY on the server.")

    slug = unique_slug(request.company, request.role)
    request_id = uuid4().hex
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".txt", prefix="job_scout_", delete=False) as handle:
            handle.write(request.job_description)
            temporary_path = Path(handle.name)
        command = build_command(repository, temporary_path, request, slug)
        environment = _safe_environment(api_key, request.model or settings.openai_model, request.mode)
        lock = _BUILD_LOCK if request.build_pdf else nullcontext()
        with lock:
            try:
                completed = subprocess.run(
                    command,
                    cwd=repository,
                    env=environment,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=settings.cv_generation_timeout_seconds,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise CVGenerationTimeoutError(
                    f"CV generation exceeded the {settings.cv_generation_timeout_seconds}-second server timeout."
                ) from exc
            except OSError as exc:
                raise CVGenerationConfigurationError("The configured CV generator could not be started.") from exc
            if completed.returncode != 0:
                raise CVGenerationError(_sanitize_failure(completed.stderr, repository, temporary_path, api_key))

            application_root = _within(repository / "cv" / "applications" / str(request.year) / slug, repository)
            tex_files = sorted(application_root.glob("*.tex"))
            notes_path = application_root / "tailoring_notes.md"
            if len(tex_files) != 1 or not notes_path.is_file():
                raise CVGenerationError("The CV tool completed but did not produce the expected source files.")
            tex_path = _within(tex_files[0], application_root)
            notes_path = _within(notes_path, application_root)
            generated: dict[DownloadKind, Path] = {"tex": tex_path, "notes": notes_path}
            pdf_path: Path | None = None
            if request.build_pdf:
                pdf_root = _within(repository / "dist" / "applications" / str(request.year), repository)
                candidate = _within(pdf_root / tex_path.with_suffix(".pdf").name, pdf_root)
                if not candidate.is_file():
                    raise CVGenerationError("The CV tool completed but the requested PDF was not produced.")
                pdf_path = candidate
                generated["pdf"] = pdf_path

            # Downloads use immutable, per-request copies. This is essential for
            # PDFs because curriculum's dist filename omits the unique slug.
            staging = Path(tempfile.mkdtemp(prefix=f"job_scout_cv_{request_id}_"))
            files: dict[DownloadKind, Path] = {}
            try:
                for kind, source in generated.items():
                    target = staging / source.name
                    shutil.copy2(source, target)
                    files[kind] = target
            except OSError:
                shutil.rmtree(staging, ignore_errors=True)
                raise CVGenerationError("Generated files could not be prepared for download.") from None

        rankings = _parse_rankings(completed.stdout)
        selected = _selected_family(completed.stdout, request.base_family, rankings)
        bundle = register_files(files, request_id=request_id)
        return CVGenerationResult(
            request_id=request_id,
            download_token=bundle.token,
            application_slug=slug,
            mode=request.mode,
            selected_family=selected,
            rankings=rankings,
            tex_filename=tex_path.name,
            notes_filename=notes_path.name,
            pdf_filename=pdf_path.name if pdf_path else None,
        )
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
