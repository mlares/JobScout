"""Execute one existing generator in its own interpreter; stdout is JSON only.

All request/output paths are created by the server. No browser-provided path is
accepted. This bridge never writes to the original tool repositories.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path


def main(request_path):
    request = json.loads(Path(request_path).read_text())
    root = Path(request['root'])
    output = Path(request['output'])
    output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((root / 'workspace.json').read_text())
    curriculum = root / manifest['paths']['curriculum']
    kind = request['kind']
    app = request.get('application', {})
    options = request.get('options', {})
    if kind in ('copy', 'cv'):
        from job_scout.config import get_settings
        settings = get_settings()
        sys.path.insert(0, str(root / 'packages/cv-engine'))
        from tailor_cv import FAMILIES, rank_families
        rankings = rank_families(app['job_description'])
        chosen = options.get('family')
        if chosen:
            family = next((f for f in FAMILIES if f.key == chosen), None)
            if family is None:
                raise ValueError('Choose a supported CV family.')
        else:
            if not rankings or rankings[0][1] <= 0:
                raise ValueError('No meaningful keyword match. Choose a CV family explicitly.')
            family = rankings[0][0]
        pdf = curriculum / 'dist/short' / family.key / Path(family.source).with_suffix('.pdf').name
        if kind == 'copy' and pdf.is_file() and not options.get('rebuild'):
            target = output / pdf.name
            shutil.copy2(pdf, target)
            return {'pdf': str(target), 'family': family.key, 'source_pdf': str(pdf),
                    'source_sha256': hashlib.sha256(pdf.read_bytes()).hexdigest(), 'method': 'exact-copy'}
        if kind == 'cv' and not settings.openai_api_key.get_secret_value():
            raise ValueError('AI CV tailoring needs OPENAI_API_KEY in the job agent environment.')
        # Isolate both LaTeX build output and application sources per task.
        isolated = output / 'curriculum'
        for relative in ('scripts', 'content', 'evidence', 'references', 'vendor', 'assets', 'docs', 'cv/short', 'cv/long'):
            shutil.copytree(curriculum / relative, isolated / relative,
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.git'), dirs_exist_ok=True)
        env = os.environ.copy()
        env['OPENAI_API_KEY'] = settings.openai_api_key.get_secret_value() if kind == 'cv' else ''
        env['OPENAI_MODEL'] = settings.openai_model
        if kind == 'cv':
            job = output / 'job.txt'
            job.write_text(app['job_description'])
            command = [sys.executable, str(isolated / 'scripts/tailor_cv.py'), str(job), '--base', family.key,
                       '--company', app['company'] or 'Unknown company', '--role', app['role'] or 'Target role',
                       '--slug', request['task_id'], '--year', str(request['year']), '--build']
        else:
            command = ['bash', str(isolated / 'scripts/build_cv.sh'), family.key]
        completed = subprocess.run(command, cwd=isolated, env=env, text=True, capture_output=True, timeout=600)
        if completed.returncode:
            raise RuntimeError('CV generation or PDF compilation failed. Check the configured model and LaTeX installation; original CVs were not changed.')
        found = list((isolated / ('dist/applications' if kind == 'cv' else 'dist/short')).rglob('*.pdf'))
        if len(found) != 1:
            raise RuntimeError('The generator did not produce exactly one PDF.')
        target = output / found[0].name
        shutil.copy2(found[0], target)
        return {'pdf': str(target), 'family': family.key, 'method': 'ai-tailoring' if kind == 'cv' else 'built-existing-source',
                'model': settings.openai_model if kind == 'cv' else None,
                'source_sha256': hashlib.sha256((curriculum / family.source).read_bytes()).hexdigest()}

    if kind in ('letter', 'letter-pdf'):
        from cover_letters.generator import GenerationRequest, generate_letter, quality_warnings
        from cover_letters.profile import load_profile
        from dotenv import load_dotenv
        secret_path = root / manifest.get('secrets', {}).get('cover_letter', 'private/secrets/cover-letter.env')
        load_dotenv(secret_path, override=False)
        profile_path = root / manifest['paths']['profile']
        profile = load_profile(profile_path)
        model = os.getenv('COVER_LETTER_MODEL', 'gpt-5.6-terra')
        if kind == 'letter':
            if not os.getenv('OPENAI_API_KEY'):
                raise ValueError('Cover-letter generation needs OPENAI_API_KEY in the cover-letter environment.')
            from openai import OpenAI
            letter = generate_letter(OpenAI(timeout=240, max_retries=0), profile,
                                     GenerationRequest(app['job_description'], app['company'], app['role'], profile.target_words), model)
            (output / 'cover-letter.txt').write_text(letter)
            return {'letter': letter, 'model': model, 'profile_sha256': hashlib.sha256(profile_path.read_bytes()).hexdigest(),
                    'warnings': quality_warnings(letter, profile, profile.target_words)}
        from cover_letters.pdf import render_cover_letter_pdf
        letter = options['letter']
        target = output / 'cover-letter.pdf'
        (output / 'cover-letter.txt').write_text(letter)
        render_cover_letter_pdf(letter, profile, target, company=app['company'], role=app['role'])
        return {'pdf': str(target), 'profile_sha256': hashlib.sha256(profile_path.read_bytes()).hexdigest(),
                'warnings': quality_warnings(letter, profile, profile.target_words)}

    if kind == 'search':
        # Disable optional external tracing for this local app; source clients and
        # ranking still use the existing job agent configuration.
        os.environ['OPIK_ENABLED'] = 'false'
        from job_scout.candidate_store import effective_profile, load_candidate
        from job_scout.runner import stream_search
        from job_scout.tools.jobs_api import filter_for_argentina, is_argentina_location, run_search
        role = options.get('role', 'senior data scientist')
        location = options.get('location', 'Argentina')
        remote = options.get('remote', True)
        limit = options.get('limit', 10)
        argentina = is_argentina_location(location)
        if options.get('ai_rank'):
            # The original wizard has a fixed role menu. Register a custom title
            # only in this isolated process so it is never silently substituted.
            from job_scout.role_targets import GENERAL_ROLE_GUIDANCE, ROLE_GUIDANCE
            ROLE_GUIDANCE.setdefault(role.strip().lower(), GENERAL_ROLE_GUIDANCE)
            candidate = load_candidate()
            if not candidate:
                raise ValueError('AI ranking needs the saved candidate profile from Job Scout. Use ordinary search first.')
            profile = effective_profile(candidate.profile, {'locations': [location], 'remote': remote})
            result = None
            for event, value in stream_search(profile, cv_text=candidate.cv_text, thread_id=request['task_id'],
                                             tags=['career-workspace'], target_role=role,
                                             residence_country='Argentina' if argentina else None, max_jobs=limit):
                if event == 'result':
                    result = value
            if result is None or result.failed:
                raise RuntimeError('AI job ranking failed. Check the search model configuration or try ordinary search.')
            warnings = list(result.errors)
            if any(r.job.source == 'cache' for r in result.ranked_jobs):
                warnings.append('Some results are cached examples. Confirm that the original posting is still open.')
            return {'jobs': [r.model_dump() for r in result.ranked_jobs], 'warnings': warnings,
                    'sources': result.jobs_sources, 'ranking': 'ai'}
        if argentina:
            jobs, sources = run_search(role, location='Argentina', country='ar', remote=False,
                                       limit=limit, include_remote_source=False)
            if remote:
                remote_jobs, remote_sources = run_search(role, location=None, country='ar', remote=True, limit=limit)
                jobs += remote_jobs
                sources = list(dict.fromkeys(sources + remote_sources))
            jobs = filter_for_argentina(list({(j.company.lower(), j.title.lower()): j for j in jobs}.values()))
        else:
            jobs, sources = run_search(role, location=location, remote=remote, limit=limit, include_remote_source=remote)
        if not remote:
            jobs = [j for j in jobs if not j.remote]
        warnings = []
        if any(j.source == 'cache' for j in jobs):
            warnings.append('Some results are cached examples from the existing tool. Confirm the posting is still open.')
        return {'jobs': [{'job': j.model_dump(), 'fit_score': None,
                          'fit_explanation': 'Source order · AI ranking is off.' +
                          (' ' + j.location_eligibility_reason if argentina else '')} for j in jobs[:limit]],
                'sources': sources, 'warnings': warnings, 'ranking': 'source-order'}
    raise ValueError('Unknown operation')


if __name__ == '__main__':
    try:
        # Some underlying libraries print diagnostics. Do not expose those or
        # provider credentials in the application protocol.
        with redirect_stdout(io.StringIO()):
            result = main(sys.argv[1])
        print(json.dumps({'ok': True, 'result': result}))
    except (ValueError, RuntimeError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}))
        sys.exit(1)
    except Exception:
        print(json.dumps({'ok': False, 'error': 'The operation failed. Check the provider configuration and local tool dependencies, then retry.'}))
        sys.exit(1)
