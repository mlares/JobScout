"""Supported job-search targets and their role-specific matching guidance."""

from __future__ import annotations

ROLE_OPTIONS = (
    "principal machine learning engineer",
    "staff machine learning engineer",
    "lead data scientist",
    "principal data scientist",
    "applied ai lead",
    "head of machine learning",
    "director of data science",
    "ai technical lead",
)

DEFAULT_TARGET_ROLE = ROLE_OPTIONS[0]

ROLE_GUIDANCE: dict[str, str] = {
    "principal machine learning engineer": (
        "Prioritize hands-on architecture and delivery of production ML systems, technical direction across teams, "
        "MLOps, model performance, reliability, and mentoring without requiring people-management ownership."
    ),
    "staff machine learning engineer": (
        "Prioritize cross-team technical influence, production ML engineering, scalable systems, MLOps, design reviews, "
        "and deep hands-on implementation. Treat primarily managerial roles as a weaker match."
    ),
    "lead data scientist": (
        "Prioritize leading applied data-science work while remaining hands-on: experimentation, statistical learning, "
        "ranking or predictive models, stakeholder direction, mentoring, and production impact."
    ),
    "principal data scientist": (
        "Prioritize advanced statistical and ML depth, ambiguous problem framing, experimentation, production impact, "
        "technical leadership, and influence across multiple teams without assuming direct reports."
    ),
    "applied ai lead": (
        "Prioritize ownership of applied AI products from problem framing through production, generative AI or NLP where "
        "relevant, ML architecture, evaluation, responsible delivery, and leadership of technical execution."
    ),
    "head of machine learning": (
        "Prioritize ML strategy plus credible hands-on depth, team and roadmap leadership, production architecture, hiring "
        "or mentoring, stakeholder management, and accountability for deployed ML outcomes."
    ),
    "director of data science": (
        "Prioritize organization-level data-science leadership, portfolio and roadmap ownership, people leadership, "
        "experimentation and measurement, executive communication, and demonstrated production business impact."
    ),
    "ai technical lead": (
        "Prioritize hands-on AI architecture, delivery leadership, technical decision-making, mentoring, production ML or "
        "generative-AI systems, and coordination across product and engineering."
    ),
}

ROLE_ALTERNATIVES: dict[str, tuple[str, ...]] = {
    "principal machine learning engineer": ("principal ml engineer", "lead machine learning engineer", "ml architect"),
    "staff machine learning engineer": ("staff ml engineer", "senior machine learning engineer", "ml tech lead"),
    "lead data scientist": ("data science lead", "senior data scientist", "machine learning lead"),
    "principal data scientist": ("staff data scientist", "senior data scientist", "data science architect"),
    "applied ai lead": ("applied ai engineer", "ai engineering lead", "lead ai engineer"),
    "head of machine learning": ("head of ai", "machine learning director", "ml engineering manager"),
    "director of data science": ("head of data science", "data science lead", "analytics director"),
    "ai technical lead": ("ai tech lead", "lead ai engineer", "machine learning tech lead"),
}

GENERAL_ROLE_GUIDANCE = (
    "Match the candidate's most recent, explicitly evidenced work; balance hands-on technical depth, leadership scope, "
    "seniority, and production impact without inferring an aspirational role."
)


def normalize_target_role(role: str | None) -> str:
    """Return a supported role, falling back to the default for old sessions."""
    normalized = (role or "").strip().lower()
    return normalized if normalized in ROLE_GUIDANCE else DEFAULT_TARGET_ROLE


def role_guidance(role: str | None) -> str:
    """Return matching and tailoring priorities for a supported role."""
    normalized = (role or "").strip().lower()
    return ROLE_GUIDANCE.get(normalized, GENERAL_ROLE_GUIDANCE)
