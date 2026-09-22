#!/usr/bin/env python3
"""Select and optionally tailor a CV family for a raw job description.

The selector is deterministic and works offline. When OPENAI_API_KEY is set, the
selected LaTeX entry point is tailored with the OpenAI Responses API. The family
sources and shared content are never modified.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import textwrap
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(os.getenv("CV_REPOSITORY_PATH", Path(__file__).resolve().parents[1])).resolve()
DEFAULT_MODEL = "gpt-5"
API_URL = "https://api.openai.com/v1/responses"


@dataclass(frozen=True)
class Family:
    key: str
    source: str
    phrases: tuple[str, ...]
    keywords: tuple[str, ...]


FAMILIES = (
    Family(
        "senior-data-science",
        "cv/short/senior-data-science/CV_senior_data_science.tex",
        ("data scientist", "applied statistics", "predictive modeling"),
        ("python", "sql", "statistics", "forecasting", "experimentation", "bayesian", "kpi", "stakeholder", "classification"),
    ),
    Family(
        "ml-engineering",
        "cv/short/ml-engineering/CV_ml_engineering.tex",
        ("machine learning engineer", "ml engineer", "production ml", "training pipeline"),
        ("pytorch", "tensorflow", "mlops", "mlflow", "onnx", "cuda", "deployment", "monitoring", "feature store", "kubernetes"),
    ),
    Family(
        "applied-ai-llm",
        "cv/short/applied-ai-llm/CV_applied_ai_llm.tex",
        ("ai engineer", "applied ai", "generative ai", "large language model"),
        ("llm", "rag", "agent", "agents", "embedding", "embeddings", "prompt", "langchain", "retrieval", "vector", "genai"),
    ),
    Family(
        "technical-leadership",
        "cv/short/technical-leadership/CV_technical_leadership.tex",
        ("technical lead", "tech lead", "engineering manager", "head of data", "staff engineer", "principal"),
        ("leadership", "roadmap", "okrs", "mentoring", "hiring", "strategy", "architecture", "manager", "director", "standards"),
    ),
    Family(
        "analytics-decision-science",
        "cv/short/analytics-decision-science/CV_analytics_decision_science.tex",
        ("decision scientist", "product analytics", "marketing analytics", "analytics scientist"),
        ("causal", "experimentation", "a/b", "metrics", "kpi", "dashboard", "marketing", "customer behavior", "insights", "forecasting"),
    ),
    Family(
        "research-scientific-ml",
        "cv/short/research-scientific-ml/CV_research_scientific_ml.tex",
        ("research scientist", "research engineer", "scientific machine learning", "medical ai"),
        ("research", "scientific", "computer vision", "hpc", "uncertainty", "calibration", "reproducibility", "volumetric", "publication", "phd"),
    ),
)


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z][a-z0-9+#.-]{1,}", normalize(text)))


def rank_families(job_description: str) -> list[tuple[Family, float, list[str]]]:
    """Rank families with an explainable, deterministic keyword score."""
    haystack = normalize(job_description)
    words = tokens(job_description)
    ranked: list[tuple[Family, float, list[str]]] = []
    for family in FAMILIES:
        score = 0.0
        matches: list[str] = []
        for phrase in family.phrases:
            count = haystack.count(phrase)
            if count:
                score += 5.0 + min(count - 1, 2) * 1.5
                matches.append(phrase)
        for keyword in family.keywords:
            matched = keyword in haystack if " " in keyword or "/" in keyword else keyword in words
            if matched:
                score += 1.0
                matches.append(keyword)
        ranked.append((family, score, matches))
    return sorted(ranked, key=lambda item: (-item[1], item[0].key))


def resolve_base(value: str | None, ranked: list[tuple[Family, float, list[str]]]) -> tuple[str, Path]:
    if not value:
        family = ranked[0][0]
        return family.key, REPO_ROOT / family.source
    for family in FAMILIES:
        if value == family.key:
            return family.key, REPO_ROOT / family.source
    path = Path(value)
    if not path.is_absolute():
        path = REPO_ROOT / path
    path = path.resolve()
    try:
        path.relative_to(REPO_ROOT)
    except ValueError as exc:
        raise ValueError("--base must be a family key or a .tex file inside this repository") from exc
    if path.suffix != ".tex" or not path.is_file():
        raise ValueError(f"Base CV does not exist or is not a .tex file: {path}")
    return "custom", path


def read_job_description(path: str) -> str:
    content = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    if not content.strip():
        raise ValueError("The job description is empty")
    if len(content) > 80_000:
        raise ValueError("The job description exceeds the 80,000-character safety limit")
    return content.strip()


def read_context(base_path: Path) -> str:
    context_paths = (
        base_path,
        REPO_ROOT / "content/shared/experience_compact.tex",
        REPO_ROOT / "content/shared/experience_medical.tex",
        REPO_ROOT / "evidence/cv_numerical_entries.md",
        REPO_ROOT / "evidence/undocumented_claims.md",
        REPO_ROOT / "evidence/project_evidence.md",
    )
    sections = []
    for path in context_paths:
        sections.append(f"\n===== {path.relative_to(REPO_ROOT)} =====\n{path.read_text(encoding='utf-8')}")
    return "".join(sections)


OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["company", "role", "tex", "tailoring_notes"],
    "properties": {
        "company": {"type": "string"},
        "role": {"type": "string"},
        "tex": {"type": "string"},
        "tailoring_notes": {"type": "string"},
    },
}


def build_prompt(
    job_description: str,
    family_key: str,
    context: str,
    company_hint: str | None = None,
    role_hint: str | None = None,
) -> str:
    return textwrap.dedent(
        f"""
        Tailor the selected CV entry point for the job description below.

        SELECTED FAMILY: {family_key}
        COMPANY HINT: {company_hint or 'not supplied'}
        ROLE HINT: {role_hint or 'not supplied'}

        Hard requirements:
        - Return the COMPLETE compilable LaTeX source in `tex`, without Markdown fences.
        - Modify only application-level positioning: title, summary, impact-chip selection/order,
          core expertise, and the final role-relevant evidence section.
        - Preserve all personal/contact data, document setup, shared experience input, education
          input, and begin/end document structure from the base.
        - Never inline, rewrite, or invent employment history from shared files.
        - Use only experience, skills, projects, outcomes, and numbers supported by the supplied
          repository context. Never infer a skill merely because the job asks for it.
        - Claims listed as pending or unchecked in undocumented_claims.md are forbidden.
        - Preserve attribution: company/project scale is context, not sole personal impact.
        - Prefer an ATS-friendly two-page result. You may omit header_photo_qr when the posting
          calls for ATS simplicity or a strict file-size limit; otherwise preserve it.
        - Escape LaTeX special characters correctly. Do not add packages, files, URLs, shell
          commands, or new input/include directives.
        - In `tailoring_notes`, explain the family choice, strongest matches, keyword coverage,
          omissions/gaps, evidence boundaries, and formatting decisions.
        - Extract company and role conservatively. Use "Unknown company" when absent.

        JOB DESCRIPTION
        =====
        {job_description}

        REPOSITORY CONTEXT
        =====
        {context}
        """
    ).strip()


def extract_output_text(response: dict[str, Any]) -> str:
    pieces: list[str] = []
    for item in response.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                pieces.append(content["text"])
    if not pieces:
        raise RuntimeError("OpenAI response did not contain output text")
    return "".join(pieces)


def call_openai(api_key: str, model: str, prompt: str) -> dict[str, str]:
    payload = {
        "model": model,
        "instructions": "You are a truthful CV editor. Follow the supplied evidence boundaries exactly.",
        "input": prompt,
        "max_output_tokens": 14_000,
        "store": False,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "tailored_cv",
                "strict": True,
                "schema": OUTPUT_SCHEMA,
            }
        },
    }
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API returned HTTP {exc.code}: {detail[:1000]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach the OpenAI API: {exc.reason}") from exc
    result = json.loads(extract_output_text(body))
    return {key: str(result[key]).strip() for key in OUTPUT_SCHEMA["required"]}


def input_paths(tex: str) -> set[str]:
    return set(re.findall(r"\\(?:input|include)\{([^}]+)\}", tex))


def validate_tex(base: str, tailored: str) -> None:
    errors: list[str] = []
    if "```" in tailored:
        errors.append("model returned Markdown code fences")
    for marker in (r"\begin{document}", r"\end{document}", r"\makecvtitle"):
        if marker not in tailored:
            errors.append(f"missing required LaTeX marker {marker}")
    base_inputs = input_paths(base)
    tailored_inputs = input_paths(tailored)
    allowed_inputs = set(base_inputs)
    missing = base_inputs - tailored_inputs - {"content/shared/header_photo_qr"}
    added = tailored_inputs - allowed_inputs
    if missing:
        errors.append(f"removed required input(s): {', '.join(sorted(missing))}")
    if added:
        errors.append(f"added unapproved input(s): {', '.join(sorted(added))}")
    dangerous = (r"\write18", r"\openout", r"\immediate\write", "shell-escape")
    if any(command in tailored for command in dangerous):
        errors.append("contains a prohibited file or shell command")
    forbidden_claims = (
        r"20\s*M\+?\s+(?:daily\s+)?(?:mobile\s+)?users",
        r"(?:nearly\s+)?2\\?%",
        r"90\\?%.*OKR",
        r"1[,\.]?000\+?\s+students",
        r"six\s+(?:complete\s+)?A/B experiments",
        r"two\s+production\s+(?:recommendation\s+)?models",
        r"five\s+satisfied\s+clients",
    )
    for pattern in forbidden_claims:
        if re.search(pattern, tailored, flags=re.IGNORECASE):
            errors.append(f"contains an uncertified claim matching /{pattern}/")
    if errors:
        raise ValueError("Generated LaTeX failed validation:\n- " + "\n- ".join(errors))


def slugify(value: str) -> str:
    value = normalize(value)
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value[:80] or "unknown-role"


def score_markdown(ranked: list[tuple[Family, float, list[str]]]) -> str:
    lines = ["| Family | Score | Matched signals |", "|---|---:|---|"]
    for family, score, matches in ranked:
        signals = ", ".join(matches) if matches else "—"
        lines.append(f"| `{family.key}` | {score:.1f} | {signals} |")
    return "\n".join(lines)


def offline_result(base: str, family_key: str, ranked: list[tuple[Family, float, list[str]]], company: str | None, role: str | None) -> dict[str, str]:
    notes = textwrap.dedent(
        f"""
        ## Offline selection

        No API key was supplied, so the closest reusable family was copied without
        model-generated wording changes.

        - Selected family: `{family_key}`
        - Company: {company or 'Unknown company'}
        - Role: {role or 'Unknown role'}

        ## Match scores

        {score_markdown(ranked)}

        Review the copied source manually before submitting it.
        """
    ).strip()
    return {
        "company": company or "Unknown company",
        "role": role or "Unknown role",
        "tex": base,
        "tailoring_notes": notes,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Choose the closest CV family and optionally tailor it with OpenAI.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("job_description", help="UTF-8 text file, or - to read stdin")
    parser.add_argument("--base", help="family key or repository-relative .tex path; skips automatic selection")
    parser.add_argument("--company", help="override/inform the company name")
    parser.add_argument("--role", help="override/inform the role title")
    parser.add_argument("--slug", help="application folder name")
    parser.add_argument("--year", type=int, default=dt.date.today().year)
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL", DEFAULT_MODEL))
    parser.add_argument("--select-only", action="store_true", help="copy the closest family without calling OpenAI")
    parser.add_argument("--build", action="store_true", help="compile the generated application PDF")
    parser.add_argument("--force", action="store_true", help="overwrite an existing generated source and notes")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        job = read_job_description(args.job_description)
        ranked = rank_families(job)
        family_key, base_path = resolve_base(args.base, ranked)
        base = base_path.read_text(encoding="utf-8")
        api_key = os.environ.get("OPENAI_API_KEY")
        use_api = bool(api_key) and not args.select_only

        print("CV family ranking:")
        for family, score, matches in ranked:
            print(f"  {family.key:28} {score:5.1f}  {', '.join(matches[:6])}")
        print(f"Selected base: {base_path.relative_to(REPO_ROOT)}")

        if use_api:
            context = read_context(base_path)
            result = call_openai(
                api_key,
                args.model,
                build_prompt(job, family_key, context, args.company, args.role),
            )
            validate_tex(base, result["tex"])
        else:
            if not api_key and not args.select_only:
                print("OPENAI_API_KEY is not set; copying the selected family unchanged.")
            result = offline_result(base, family_key, ranked, args.company, args.role)

        company = args.company or result["company"]
        role = args.role or result["role"]
        folder_slug = args.slug or slugify(f"{company}-{role}")
        application_dir = REPO_ROOT / "cv" / "applications" / str(args.year) / folder_slug
        tex_name = f"CV_{slugify(company).replace('-', '_')}_{slugify(role).replace('-', '_')}.tex"
        tex_path = application_dir / tex_name
        notes_path = application_dir / "tailoring_notes.md"
        existing = [path for path in (tex_path, notes_path) if path.exists()]
        if existing and not args.force:
            names = ", ".join(str(path.relative_to(REPO_ROOT)) for path in existing)
            raise FileExistsError(f"Refusing to overwrite {names}; pass --force to replace")

        application_dir.mkdir(parents=True, exist_ok=True)
        tex_path.write_text(result["tex"].rstrip() + "\n", encoding="utf-8")
        notes_header = f"# {company} — {role}\n\n- Generated from: `{base_path.relative_to(REPO_ROOT)}`\n- Model: `{args.model if use_api else 'none (offline selection)'}`\n\n"
        notes_path.write_text(notes_header + result["tailoring_notes"].strip() + "\n", encoding="utf-8")
        print(f"Wrote: {tex_path.relative_to(REPO_ROOT)}")
        print(f"Wrote: {notes_path.relative_to(REPO_ROOT)}")

        if args.build:
            subprocess.run(
                [str(REPO_ROOT / "scripts/build_cv.sh"), "file", str(tex_path.relative_to(REPO_ROOT))],
                cwd=REPO_ROOT,
                check=True,
            )
            print(f"Built PDF under dist/applications/{args.year}/")
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
