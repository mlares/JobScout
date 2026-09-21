from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .generator import (
    SYSTEM_INSTRUCTIONS,
    GenerationRequest,
    build_input,
    generate_letter,
    quality_warnings,
)
from .profile import load_profile


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROFILE = Path(os.getenv("CAREER_PROFILE_PATH", PROJECT_ROOT / "private/profile.json"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cover-letter")
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate = subparsers.add_parser("generate", help="Generate a tailored cover letter")
    generate.add_argument("--job", type=Path, help="Job-description text file; omit to read stdin")
    generate.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    generate.add_argument("--company")
    generate.add_argument("--role")
    generate.add_argument("--target-words", type=int)
    generate.add_argument(
        "--model",
        help="OpenAI model; defaults to COVER_LETTER_MODEL or gpt-5.6-terra",
    )
    generate.add_argument(
        "--output",
        type=Path,
        help="Write the letter here; a .pdf suffix creates a designed PDF",
    )
    generate.add_argument("--dry-run", action="store_true", help="Print the prompt without calling the API")
    return parser


def read_job_description(path: Path | None) -> str:
    if path is not None:
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise ValueError(f"Job description not found: {path}") from exc
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        raise ValueError("Pass --job or pipe a job description through stdin.")
    if not text.strip():
        raise ValueError("Job description is empty.")
    return text


def run_generate(args: argparse.Namespace) -> int:
    profile = load_profile(args.profile)
    target_words = args.target_words or profile.target_words
    if not 180 <= target_words <= 700:
        raise ValueError("--target-words must be between 180 and 700.")
    request = GenerationRequest(
        job_description=read_job_description(args.job),
        company=args.company,
        role=args.role,
        target_words=target_words,
    )

    if args.dry_run:
        print("SYSTEM INSTRUCTIONS\n\n" + SYSTEM_INSTRUCTIONS)
        print("\nINPUT\n\n" + build_input(profile, request))
        return 0

    try:
        from dotenv import load_dotenv
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("Install the project first: pip install -e .") from exc

    load_dotenv(os.getenv("CAREER_COVER_LETTER_ENV", PROJECT_ROOT / ".env"), override=False)
    model = args.model or os.getenv("COVER_LETTER_MODEL", "gpt-5.6-terra")
    letter = generate_letter(OpenAI(), profile, request, model)
    if args.output:
        if args.output.suffix.casefold() == ".pdf":
            from .pdf import render_cover_letter_pdf

            render_cover_letter_pdf(
                letter,
                profile,
                args.output,
                company=args.company,
                role=args.role,
            )
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(letter, encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(letter, end="")

    for warning in quality_warnings(letter, profile, target_words):
        print(f"Warning: {warning}", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "generate":
            return run_generate(args)
    except (ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
