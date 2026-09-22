from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "tailor_cv.py"
SPEC = importlib.util.spec_from_file_location("tailor_cv", MODULE_PATH)
assert SPEC and SPEC.loader
tailor_cv = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = tailor_cv
SPEC.loader.exec_module(tailor_cv)


def test_rank_families_prefers_applied_ai_for_agent_role() -> None:
    ranked = tailor_cv.rank_families(
        "Applied AI engineer building LLM agents, RAG, embeddings, and retrieval systems"
    )
    assert ranked[0][0].key == "applied-ai-llm"
    assert "applied ai" in ranked[0][2]


def test_read_job_description_rejects_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "job.txt"
    path.write_text("  \n", encoding="utf-8")
    with pytest.raises(ValueError, match="empty"):
        tailor_cv.read_job_description(str(path))


def test_resolve_base_rejects_path_outside_repository(tmp_path: Path) -> None:
    outside = tmp_path / "outside.tex"
    outside.write_text("content", encoding="utf-8")
    ranked = tailor_cv.rank_families("data scientist")
    with pytest.raises(ValueError, match="inside this repository"):
        tailor_cv.resolve_base(str(outside), ranked)


def test_validate_tex_accepts_preserved_inputs() -> None:
    base = r"\begin{document}\makecvtitle\input{content/shared/skills}\end{document}"
    tailor_cv.validate_tex(base, base)


@pytest.mark.parametrize(
    ("tailored", "message"),
    [
        (r"\begin{document}\makecvtitle\input{untrusted}\end{document}", "added unapproved"),
        (r"\begin{document}\makecvtitle\write18{curl bad}\end{document}", "prohibited"),
        (r"```tex\begin{document}\makecvtitle\end{document}```", "code fences"),
    ],
)
def test_validate_tex_rejects_unsafe_output(tailored: str, message: str) -> None:
    base = r"\begin{document}\makecvtitle\end{document}"
    with pytest.raises(ValueError, match=message):
        tailor_cv.validate_tex(base, tailored)
