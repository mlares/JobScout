"""Prompt for the job-ranking node.

Maintainer note: this prompt is intentionally left unoptimized (it is the target
of the Phase 3 prompt optimizer). Keep it to clear instructions and the correct
output schema — no few-shot examples or chain-of-thought scaffolding.
"""

RANK_JOBS_PROMPT_NAME = "rank_jobs"

RANK_JOBS_PROMPT = """You are evaluating whether a candidate should spend time applying to each job.
Use only evidence present in the candidate profile and job description.

Selected target role: {target_role}
Role-specific priorities: {role_guidance}

{geography_rules}

For geographically eligible jobs, score using these weights:
- 30 points: selected-role and responsibility alignment.
- 25 points: required technical skills supported by the profile.
- 20 points: seniority and leadership-scope alignment.
- 15 points: relevant domain and production experience.
- 10 points: preferred qualifications.

Give most weight to recent industry experience. Academic and scientific-computing experience is supporting evidence, not
a substitute for an explicit production requirement. Separate must-haves from preferences. Scores above 80 require strong
evidence across role, core requirements, seniority, and geography; scores above 90 require near-complete must-have coverage.

For each job, return:
- fit_score: an integer from 0 to 100 for how well the job matches the candidate.
- Use 0 only for a definite rejection; zero-score jobs are omitted from recommendations.
- fit_explanation: 2-4 sentences stating geographic eligibility, the strongest CV-backed evidence, and the main gaps.
- matched_skills: the candidate's skills that are relevant to this job.
- gaps: requirements the candidate seems to lack.

Candidate profile:
{profile}

Jobs to score:
{jobs}
"""
