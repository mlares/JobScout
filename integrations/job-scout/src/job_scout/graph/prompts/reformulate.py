"""Prompt for the query-reformulation node (see prompts/__init__.py)."""

REFORMULATE_PROMPT_NAME = "reformulate"

REFORMULATE_PROMPT = """The previous job search returned too few good matches. Produce one alternative job title that
stays within the selected role family and remains well supported by the candidate profile.

Selected target role: {target_role}
Role-specific priorities: {role_guidance}
Suggested adjacent titles: {allowed_titles}

Prefer an untried suggested title. Do not drift into academic roles, generic executive roles, or an unrelated discipline.
Use 2-5 words and do not append skills, technologies, locations, or Boolean operators.

Candidate profile:
{profile}

Previous search query:
{previous_query}

Return only the new search query text, nothing else.
"""
