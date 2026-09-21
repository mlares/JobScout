"""Fetch jobs for an explicit target role or via automatic LLM tool selection.

The UI's human-selected role is used verbatim. Legacy callers without a target
retain LLM tool selection. Argentina residents get separate local and eligible-
remote lanes. On a reformulation loop, the query stays within the role family.
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from job_scout.config import get_settings
from job_scout.graph.schemas import JobPosting
from job_scout.graph.state import AgentState
from job_scout.llm import ensure_budget, get_chat_model
from job_scout.role_targets import normalize_target_role
from job_scout.tools.jobs_api import filter_for_argentina, is_argentina_location, run_search, search_jobs

# Per-fetch limit comes from settings (SCOUT_MAX_JOBS, default 10 — it drives
# ranking latency directly: 10 jobs = 2 LLM batches ≈ half a minute end to end).
# The merged ceiling bounds growth across reformulation loops, so a broadened
# search can still ADD jobs beyond the per-fetch limit without ballooning.
MERGED_CEILING = 25

# Job boards match the query against posting TITLES, so a query that reads like
# a skill list matches nothing. Both gpt-4.1-nano and gpt-4o-mini used to answer
# this prompt with 80-200 characters of keyword soup ("Senior Data Scientist AI
# Engineer deep learning neural networks LLMs RAG systems..."), Adzuna returned
# zero for it, and the cascade fell through to the remote-only board — whose
# generic listings were then ranked and presented as the candidate's top matches.
_SYSTEM = (
    "You are a job search assistant. Call the search_jobs tool exactly once.\n"
    "The query goes verbatim to job boards, which match it against job TITLES. "
    "So write it as a job title someone would actually post: the candidate's "
    "current role at the right seniority, and NOTHING else. Two to four words.\n"
    "Never append skills, technologies, tools or synonyms. Every extra term "
    "narrows the match, and a long query returns nothing at all.\n"
    "Good: 'senior data scientist' · 'machine learning engineer' · 'staff backend engineer'\n"
    "Bad:  'senior data scientist AI engineer deep learning LLMs RAG vector databases'\n"
    "Pick a country code from their location and set the remote flag from their preference."
)

# A prompt is a request, not a guarantee, so the constraint is also enforced
# here. Real titles run 2-4 words; 6 leaves room for "(all genders)"-style
# padding without letting a skill list through.
MAX_QUERY_WORDS = 6


def _build_prompt(state: AgentState) -> str:
    """Describe the candidate to the LLM, adding reformulation guidance if looping."""
    profile = state["profile"]
    lines = [
        f"Seniority: {profile.seniority}",
        f"Recent / primary roles: {', '.join(profile.primary_roles) or 'unknown'}",
        f"Key skills: {', '.join(profile.skills[:15])}",
        f"Summary: {profile.raw_summary or 'n/a'}",
        f"Locations: {', '.join(profile.locations) or 'unknown'}",
        f"Open to remote: {profile.remote_ok}",
    ]
    reformulated = state.get("search_query")
    if state.get("reformulation_count", 0) and reformulated:
        lines.append(
            f"\nThe previous search returned too few good matches. Use this broader query and search again: {reformulated!r}"
        )
    return "\n".join(lines)


def fetch_jobs(state: AgentState) -> dict:
    """Run the job search with LLM-chosen arguments and merge results into state."""
    settings = get_settings()
    search_limit = max(1, min(int(state.get("search_limit") or settings.scout_max_jobs), MERGED_CEILING))
    calls = state.get("llm_calls", 0)
    profile = state["profile"]
    target_role = normalize_target_role(state.get("target_role")) if state.get("target_role") else ""
    errors = list(state.get("errors", []))

    reformulated = state.get("search_query") if state.get("reformulation_count", 0) else None
    if state.get("target_role"):
        # A human-selected title is a stronger signal than another model call.
        # Reformulation may choose a nearby title, but the initial query is exact.
        query, dropped = _trim_query(reformulated or target_role)
        calls_used = 0
        country, remote = None, profile.remote_ok
    else:
        query, dropped, calls_used, country, remote, issued_tool_call = _llm_query(state, profile, settings)
        if not issued_tool_call:
            errors.append("fetch_jobs: LLM issued no tool call; used profile-derived query")
    ensure_budget(calls, calls_used, settings.max_llm_calls_per_run)
    calls += calls_used
    if dropped:
        errors.append(f"fetch_jobs: query trimmed to {MAX_QUERY_WORDS} words, dropped {dropped!r}")

    argentina_search = (state.get("residence_country") or "").strip().lower() == "argentina" or any(
        is_argentina_location(loc) for loc in profile.locations
    )
    if argentina_search:
        local_jobs: list[JobPosting] = []
        local_sources: list[str] = []
        if profile.locations:
            local_jobs, local_sources = run_search(
                query=query,
                location="Argentina",
                country="ar",
                remote=False,
                limit=search_limit,
                include_remote_source=False,
            )
        remote_jobs: list[JobPosting] = []
        remote_sources: list[str] = []
        if profile.remote_ok:
            remote_jobs, remote_sources = run_search(
                query=query, location=None, country="ar", remote=True, limit=search_limit
            )
        jobs = filter_for_argentina(_dedupe_with_existing(local_jobs, remote_jobs))
        sources = list(dict.fromkeys([*local_sources, *remote_sources]))
    else:
        location = profile.locations[0] if profile.locations else None
        jobs, sources = run_search(
            query=query,
            location=location,
            country=country if not state.get("target_role") else None,
            remote=remote if not state.get("target_role") else profile.remote_ok,
            limit=search_limit,
        )

    jobs = _dedupe_with_existing(state.get("jobs", []), jobs)[:MERGED_CEILING]

    return {
        "jobs": jobs,
        "search_query": query,
        "target_role": target_role,
        "jobs_sources": sources,
        "errors": errors,
        "llm_calls": calls,
    }


def _llm_query(state: AgentState, profile, settings) -> tuple[str, str, int, str | None, bool, bool]:
    """Legacy automatic role selection for non-UI callers without a target."""
    model_name = settings.scout_fetch_model or settings.scout_model
    model = get_chat_model(model_name, temperature=0.0).bind_tools([search_jobs])
    message = model.invoke([SystemMessage(_SYSTEM), HumanMessage(_build_prompt(state))])
    if message.tool_calls:
        args = message.tool_calls[0]["args"]
        query = args.get("query") or " ".join(profile.primary_roles[:2])
        query, dropped = _trim_query(query)
        country = args.get("country")
        remote = bool(args.get("remote", profile.remote_ok))
    else:
        query = " ".join(profile.primary_roles[:2]) or " ".join(profile.skills[:3])
        query, dropped = _trim_query(query)
        country = None
        remote = profile.remote_ok
    return query, dropped, 1, country, remote, bool(message.tool_calls)


def _trim_query(query: str) -> tuple[str, str]:
    """Cut a query back to a title-length phrase.

    Returns the kept phrase and whatever was dropped (empty when nothing was).
    Keeping the *first* words is deliberate: both models we tested lead with the
    role title and then trail off into skills, so the front of the string is the
    part worth searching for.
    """
    words = query.split()
    if len(words) <= MAX_QUERY_WORDS:
        return query.strip(), ""
    return " ".join(words[:MAX_QUERY_WORDS]), " ".join(words[MAX_QUERY_WORDS:])


def _dedupe_with_existing(existing: list[JobPosting], new: list[JobPosting]) -> list[JobPosting]:
    """On a reformulation loop, merge new results with prior ones, deduped."""
    seen = {(j.title.strip().lower(), j.company.strip().lower()) for j in existing}
    merged = list(existing)
    for job in new:
        key = (job.title.strip().lower(), job.company.strip().lower())
        if key not in seen:
            seen.add(key)
            merged.append(job)
    return merged
