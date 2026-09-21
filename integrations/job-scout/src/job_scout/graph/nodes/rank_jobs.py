"""Score each fetched job against the profile, one LLM call per batch.

The LLM returns lean ``JobScore`` objects keyed by ``job_id``; we pair each back
to its ``JobPosting`` to build a ``RankedJob``.
"""

from __future__ import annotations

import contextvars
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor

from job_scout.config import get_settings
from job_scout.graph.prompts.rank_jobs import RANK_JOBS_PROMPT
from job_scout.graph.schemas import JobPosting, JobScores, Profile, RankedJob
from job_scout.graph.state import AgentState
from job_scout.llm import ensure_budget, get_chat_model
from job_scout.role_targets import ROLE_GUIDANCE, normalize_target_role, role_guidance
from job_scout.tools.jobs_api import is_argentina_location

# Batch size is a latency knob (SCOUT_RANK_BATCH): output tokens — and so batch
# latency — scale with jobs per batch, and batches run in parallel, so smaller
# batches shave the slowest-batch time at the cost of a few more LLM calls.
MAX_PARALLEL_BATCHES = 4
MIN_RECOMMENDATION_SCORE = 1


def _render_profile(profile: Profile, target_role: str | None = None) -> str:
    """Format the profile as plain text for the ranking prompt."""
    raw_role = (target_role or "").strip().lower()
    displayed_role = normalize_target_role(raw_role) if raw_role in ROLE_GUIDANCE else (target_role or "not selected")
    return (
        f"Name: {profile.name}\n"
        f"Seniority: {profile.seniority}\n"
        f"Roles: {', '.join(profile.primary_roles)}\n"
        f"Skills: {', '.join(profile.skills)}\n"
        f"Years experience: {profile.years_experience}\n"
        f"Locations: {', '.join(profile.locations)}\n"
        f"Remote ok: {profile.remote_ok}\n"
        f"Selected target role: {displayed_role}"
    )


def _render_jobs(jobs: list[JobPosting]) -> str:
    """Format a batch of jobs as plain text for the ranking prompt."""
    return "\n\n---\n\n".join(
        f"job_id: {job.job_id}\n"
        f"title: {job.title}\n"
        f"company: {job.company}\n"
        f"location: {job.location} (remote: {job.remote})\n"
        f"location_eligibility: {job.location_eligibility} — {job.location_eligibility_reason}\n"
        f"description: {job.description[:3000]}"
        for job in jobs
    )


def _batches(items: list[JobPosting], size: int) -> Iterator[list[JobPosting]]:
    """Yield ``items`` in chunks of ``size``."""
    for i in range(0, len(items), size):
        yield items[i : i + size]


def rank_jobs(state: AgentState) -> dict:
    """Score each fetched job against the profile and return them sorted by fit.

    Jobs already scored in a previous pass (reformulation loops merge new
    fetches into ``state["jobs"]``) keep their scores — the profile hasn't
    changed, so re-scoring them would only re-spend the same LLM calls. Only
    genuinely new postings go to the model.
    """
    settings = get_settings()
    profile = state["profile"]
    selected_role = state.get("target_role")
    target_role = (
        normalize_target_role(selected_role)
        if selected_role
        else ((profile.primary_roles or ["best CV-supported role"])[0]).lower()
    )
    argentina_search = (state.get("residence_country") or "").strip().lower() == "argentina" or any(
        is_argentina_location(location) for location in profile.locations
    )
    jobs = state.get("jobs", [])
    if not jobs:
        return {"ranked_jobs": []}

    ranked: list[RankedJob] = list(state.get("ranked_jobs") or [])
    already_scored = {r.job.job_id for r in ranked}
    to_score = [job for job in jobs if job.job_id not in already_scored]
    if not to_score:
        ranked.sort(key=lambda r: r.fit_score, reverse=True)
        return {"ranked_jobs": ranked}

    by_id = {job.job_id: job for job in to_score}
    calls = state.get("llm_calls", 0)
    batch_size = settings.scout_rank_batch
    n_batches = (len(to_score) + batch_size - 1) // batch_size
    ensure_budget(calls, n_batches, settings.max_llm_calls_per_run)

    model = get_chat_model(settings.scout_model, temperature=0.0).with_structured_output(JobScores)

    def score_batch(batch: list[JobPosting]) -> JobScores:
        prompt = RANK_JOBS_PROMPT.format(
            target_role=target_role,
            role_guidance=role_guidance(selected_role),
            geography_rules=(
                "The candidate resides in Argentina. Geographic eligibility is a hard requirement:\n"
                "- Eligible: Argentina-based, or remote accepting Argentina, LATAM, Latin America, South America, "
                "the Americas, worldwide, or anywhere.\n"
                "- Ineligible: remote restricted to the US, Canada, Europe, UK, EU, EMEA, APAC, or another "
                "incompatible country/region.\n"
                '- If location_eligibility is "ineligible", score 0-15 and name the restriction as the first gap.\n'
                '- If location_eligibility is "unknown", cap the score at 55 and state that Argentina eligibility '
                "must be confirmed."
                if argentina_search
                else "Evaluate geographic compatibility from the candidate locations and each posting."
            ),
            profile=_render_profile(profile, target_role),
            jobs=_render_jobs(batch),
        )
        return model.invoke(prompt)

    # Batches are independent, so they run concurrently — ranking latency is the
    # slowest batch, not the sum. copy_context() carries LangChain's callback
    # contextvars into the worker threads, so Opik spans and token/cost tracking
    # still attach to the run (the whole point of this repo).
    batches = list(_batches(to_score, batch_size))
    if len(batches) == 1:
        results = [score_batch(batches[0])]
    else:
        with ThreadPoolExecutor(max_workers=min(len(batches), MAX_PARALLEL_BATCHES)) as pool:
            futures = [pool.submit(contextvars.copy_context().run, score_batch, batch) for batch in batches]
            results = [future.result() for future in futures]
    calls += len(batches)

    for result in results:
        for score in result.scores:
            job = by_id.get(score.job_id)
            if job is None:
                continue
            fit_score = score.fit_score
            gaps = list(score.gaps)
            if argentina_search and job.location_eligibility == "unknown":
                fit_score = min(fit_score, 55)
                if not any("argentina" in gap.lower() or "location" in gap.lower() for gap in gaps):
                    gaps.insert(0, "Confirm that the employer accepts remote candidates residing in Argentina.")
            elif argentina_search and job.location_eligibility == "ineligible":
                fit_score = min(fit_score, 15)
                gaps.insert(0, job.location_eligibility_reason)
            # The model scores every fetched posting, including explicit
            # rejections. A zero is useful evaluation output but is not a job
            # recommendation and must not enter UI or tailoring state.
            if fit_score < MIN_RECOMMENDATION_SCORE:
                continue
            ranked.append(
                RankedJob(
                    job=job,
                    fit_score=fit_score,
                    fit_explanation=score.fit_explanation,
                    matched_skills=score.matched_skills,
                    gaps=gaps,
                )
            )

    ranked.sort(key=lambda r: r.fit_score, reverse=True)
    return {"ranked_jobs": ranked, "llm_calls": calls}
