"""The UI role menu and prompt guidance stay complete and deterministic."""

from job_scout.graph.prompts.rank_jobs import RANK_JOBS_PROMPT
from job_scout.graph.prompts.tailor import TAILOR_PROMPT
from job_scout.role_targets import ROLE_ALTERNATIVES, ROLE_GUIDANCE, ROLE_OPTIONS, role_guidance


def test_every_role_has_distinct_guidance_and_reformulations():
    assert len(ROLE_OPTIONS) == 8
    assert set(ROLE_OPTIONS) == set(ROLE_GUIDANCE) == set(ROLE_ALTERNATIVES)
    assert len(set(ROLE_GUIDANCE.values())) == len(ROLE_OPTIONS)
    assert all(len(alternatives) >= 3 for alternatives in ROLE_ALTERNATIVES.values())


def test_every_role_renders_into_ranking_and_tailoring_prompts():
    for role in ROLE_OPTIONS:
        guidance = role_guidance(role)
        ranking = RANK_JOBS_PROMPT.format(
            target_role=role,
            role_guidance=guidance,
            geography_rules="Argentina rules",
            profile="profile",
            jobs="jobs",
        )
        tailoring = TAILOR_PROMPT.format(
            target_role=role,
            role_guidance=guidance,
            research_rule="",
            profile="profile",
            corpus="corpus",
            job="job",
            research="none",
        )
        assert role in ranking and guidance in ranking
        assert role in tailoring and guidance in tailoring
