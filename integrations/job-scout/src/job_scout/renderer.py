"""Render a validated application pack to CV and cover-letter PDFs.

The template pipes every user-derived value through the ``tex`` escape filter,
so LLM output can never inject LaTeX. The compiler strategy mirrors the proven
``../curriculum/scripts/build_cv.sh`` workflow: use ``pdflatex`` when present,
then fall back to tectonic.

Degradation contract: rendering must never fail a run. If no compiler is
available or compilation fails, the ``.tex`` file is still written and the
result carries a human-readable pointer instead of a PDF path.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, PackageLoader

from job_scout.graph.schemas import CVContent, TailoringPack

_COMPILE_TIMEOUT_S = 120

OVERLEAF_HINT = (
    "neither pdflatex nor tectonic is installed — download the .tex file and compile it on overleaf.com "
    "(New Project → Upload)."
)

# Order matters: backslash first, since the replacements introduce backslashes.
_TEX_REPLACEMENTS = [
    ("\\", r"\textbackslash{}"),
    ("&", r"\&"),
    ("%", r"\%"),
    ("$", r"\$"),
    ("#", r"\#"),
    ("_", r"\_"),
    ("{", r"\{"),
    ("}", r"\}"),
    ("~", r"\textasciitilde{}"),
    ("^", r"\textasciicircum{}"),
]


@dataclass
class RenderResult:
    """Outcome of one render: the .tex always, the PDF when a compiler works."""

    tex_path: Path
    pdf_path: Path | None = None
    message: str = ""


@dataclass
class ApplicationRenderResult:
    """The two independently downloadable documents in an application pack."""

    cv: RenderResult
    cover_letter: RenderResult

    @property
    def message(self) -> str:
        return "; ".join(message for message in [self.cv.message, self.cover_letter.message] if message)


def latex_escape(text: str) -> str:
    """Escape LaTeX special characters in user-derived text."""
    # \textbackslash{} contains braces, which must not be re-escaped: replace
    # backslashes with a placeholder first, braces next, then resolve it.
    text = str(text).replace("\\", "\x00")
    for char, replacement in _TEX_REPLACEMENTS[1:]:
        text = text.replace(char, replacement)
    return text.replace("\x00", r"\textbackslash{}")


def _environment() -> Environment:
    """Jinja2 env with LaTeX-safe delimiters (``<< >>`` / ``<% %>``)."""
    env = Environment(
        loader=PackageLoader("job_scout", "templates"),
        variable_start_string="<<",
        variable_end_string=">>",
        block_start_string="<%",
        block_end_string="%>",
        comment_start_string="<#",
        comment_end_string="#>",
        autoescape=False,  # noqa: S701 - LaTeX, not HTML; the |tex filter escapes
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["tex"] = latex_escape
    return env


def render_tex(cv: CVContent, candidate_name: str) -> str:
    """Render the tailored CV to LaTeX source."""
    template = _environment().get_template("cv.tex.j2")
    return template.render(cv=cv, name=candidate_name, location="")


def render_cover_letter_tex(
    cover_letter: str,
    candidate_name: str,
    *,
    headline: str = "",
    location: str = "",
) -> str:
    """Render plain cover-letter text as safe, separated LaTeX paragraphs."""
    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", cover_letter.strip()) if paragraph.strip()]
    blocks = [
        {
            "lines": [line.strip() for line in paragraph.splitlines() if line.strip()],
            "closing": bool(re.match(r"^(sincerely|best regards|kind regards|regards)[,\s]", paragraph, re.IGNORECASE)),
        }
        for paragraph in paragraphs
    ]
    template = _environment().get_template("cover_letter.tex.j2")
    return template.render(name=candidate_name, headline=headline, location=location, blocks=blocks)


def tectonic_path() -> str | None:
    """Absolute path of the tectonic binary, or ``None`` when not installed."""
    return shutil.which("tectonic")


def pdflatex_path() -> str | None:
    """Absolute path of the pdflatex binary used by the curriculum project."""
    return shutil.which("pdflatex")


def _compile(tex_path: Path) -> RenderResult:
    """Compile one trusted template without allowing LaTeX shell commands."""
    pdflatex = pdflatex_path()
    tectonic = tectonic_path()
    if pdflatex is None and tectonic is None:
        return RenderResult(tex_path=tex_path, message=OVERLEAF_HINT)

    if pdflatex is not None:
        command = [
            pdflatex,
            "-interaction=nonstopmode",
            "-halt-on-error",
            "-no-shell-escape",
            "-output-directory=.",
            tex_path.name,
        ]
        attempts = 2
        compiler = "pdflatex"
    else:
        command = [tectonic or "tectonic", tex_path.name, "--outdir", "."]
        attempts = 1
        compiler = "tectonic"

    try:
        proc = None
        for _ in range(attempts):
            proc = subprocess.run(
                command,
                cwd=tex_path.parent,
                capture_output=True,
                text=True,
                timeout=_COMPILE_TIMEOUT_S,
            )
            if proc.returncode != 0:
                break
    except (OSError, subprocess.TimeoutExpired) as exc:
        return RenderResult(tex_path=tex_path, message=f"{compiler} failed to run ({exc}); {OVERLEAF_HINT}")

    pdf_path = tex_path.with_suffix(".pdf")
    if proc is None or proc.returncode != 0 or not pdf_path.exists():
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-3:] if proc else []
        return RenderResult(tex_path=tex_path, message=f"{compiler} compile failed: " + " / ".join(tail))
    return RenderResult(tex_path=tex_path, pdf_path=pdf_path)


def render_pdf(cv: CVContent, candidate_name: str, out_dir: Path) -> RenderResult:
    """Write the CV ``.tex`` and compile it with the available compiler.

    ``out_dir`` should be a temp/scratch directory chosen by the caller — never
    inside the repo. Never raises: every failure mode returns a ``RenderResult``
    with ``pdf_path=None`` and an actionable ``message``.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    tex_path = out_dir / "tailored_cv.tex"
    tex_path.write_text(render_tex(cv, candidate_name), encoding="utf-8")

    return _compile(tex_path)


def render_application_pdfs(
    pack: TailoringPack,
    candidate_name: str,
    out_dir: Path,
    *,
    location: str = "",
) -> ApplicationRenderResult:
    """Compile the validated CV and cover letter into separate PDFs."""
    out_dir.mkdir(parents=True, exist_ok=True)

    cv_tex_path = out_dir / "tailored_cv.tex"
    cv_tex_path.write_text(
        _environment().get_template("cv.tex.j2").render(cv=pack.cv, name=candidate_name, location=location),
        encoding="utf-8",
    )

    letter_tex_path = out_dir / "cover_letter.tex"
    letter_tex_path.write_text(
        render_cover_letter_tex(
            pack.cover_letter,
            candidate_name,
            headline=pack.cv.headline,
            location=location,
        ),
        encoding="utf-8",
    )

    return ApplicationRenderResult(cv=_compile(cv_tex_path), cover_letter=_compile(letter_tex_path))
