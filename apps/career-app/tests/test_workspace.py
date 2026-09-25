import asyncio
import importlib.util
import json
import shutil
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

import httpx
import pytest
from backend.app import create_app
from backend.service import CareerService, sha
from backend.store import Store

WORKSPACE = Path(__file__).resolve().parents[3]
HEADERS = {'X-Career-Request': '1'}
JOB_SCOUT_IMPORTABLE = importlib.util.find_spec('job_scout') is not None


def api_calls(app, calls):
    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url='http://testserver') as client:
            return [await client.request(method, path, **options) for method, path, options in calls]
    return asyncio.run(run())


@pytest.fixture
def service(tmp_path, monkeypatch):
    for key in ('OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'GROQ_API_KEY', 'GOOGLE_API_KEY', 'TYPESAFE_API_KEY'):
        monkeypatch.delenv(key, raising=False)
    root = tmp_path / 'career'
    root.mkdir()
    manifest = json.loads((WORKSPACE / 'workspace.demo.json').read_text())
    (root / 'workspace.json').write_text(json.dumps(manifest))
    curriculum = WORKSPACE / manifest['paths']['curriculum']
    shutil.copytree(curriculum, root / manifest['paths']['curriculum'],
                    ignore=shutil.ignore_patterns('build', '__pycache__', '*.pyc'))
    profile = root / manifest['paths']['profile']
    profile.parent.mkdir(parents=True, exist_ok=True)
    profile.write_text(json.dumps({
        'name': 'Example Candidate', 'headline': 'Data professional', 'location': 'Example City',
        'links': [{'label': 'Assistant', 'url': 'https://example.test/assistant'}],
        'facts': [{'category': 'work', 'statement': 'Built reliable systems.'}],
    }))
    shutil.copytree(WORKSPACE / 'packages/cv-engine', root / 'packages/cv-engine')
    applications = root / manifest['paths']['applications']
    applications.mkdir(parents=True)
    (applications / 'index.json').write_text('{"applications": []}')
    return CareerService(root=root)


@pytest.fixture
def app_record(service):
    return service.save_application({'company': 'Test Co', 'role': 'ML Engineer',
                                     'job_description': 'Production machine learning engineer. PyTorch, CUDA, deployment and MLOps.',
                                     'source_url': 'https://example.com/job'})


def fake_bridge(service):
    def run(request):
        target = service.data / 'tasks' / request['task_id'] / 'output.pdf'
        target.parent.mkdir(parents=True)
        source = service.family_pdf('ml-engineering')
        shutil.copy2(source, target)
        return {'pdf': str(target), 'family': 'ml-engineering', 'method': 'exact-copy', 'source_sha256': sha(source)}
    return run


def test_copy_preserves_bytes_and_survives_restart(service, app_record, monkeypatch):
    monkeypatch.setattr(service, 'call_bridge', fake_bridge(service))
    task = service.enqueue('copy', app_record['id'], {}, str(uuid4()))
    service.run_task(task['id'])
    result = service.store.task(task['id'])
    assert result['status'] == 'completed'
    path, artifact = service.file(result['result']['artifact_id'])
    assert path.is_relative_to(service.sent)
    assert not path.is_symlink()
    assert sha(path) == sha(service.family_pdf('ml-engineering'))
    assert artifact['state'] == 'sent'
    reopened = CareerService(root=service.root)
    reopened_path, reopened_record = reopened.file(artifact['id'])
    assert reopened_record['id'] == artifact['id']
    assert reopened_path.read_bytes() == path.read_bytes()


def test_duplicate_request_and_save_are_idempotent(service, app_record):
    request_id = str(uuid4())
    first = service.enqueue('copy', app_record['id'], {}, request_id)
    second = service.enqueue('copy', app_record['id'], {}, request_id)
    assert first['id'] == second['id']
    draft = service.add_pdf(app_record['id'], service.family_pdf('ml-engineering'), 'cv-tailored', 'draft', {})
    saved = service.save_to_sent(draft['id'])
    assert service.save_to_sent(draft['id'])['id'] == saved['id']
    assert len(list(service.sent.rglob('*.pdf'))) == 1


def test_concurrent_saves_never_overwrite(service, app_record):
    source = service.family_pdf('ml-engineering')
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: service.add_pdf(app_record['id'], source, 'cv-matched', 'sent', {}), range(4)))
    assert len({r['path'] for r in results}) == 4
    assert all(sha(service.root / r['path']) == sha(source) for r in results)


def test_task_keeps_original_description_when_application_is_edited(service, app_record, monkeypatch):
    task = service.enqueue('copy', app_record['id'], {}, str(uuid4()))
    service.save_application({**{k: app_record[k] for k in ('company', 'role', 'job_description', 'source_url')},
                              'job_description': 'A completely different role'}, app_record['id'])
    observed = []
    def bridge(request):
        observed.append(request['application']['job_description'])
        return fake_bridge(service)(request)
    monkeypatch.setattr(service, 'call_bridge', bridge)
    service.run_task(task['id'])
    assert observed == [app_record['job_description']]


def test_failed_task_has_no_artifact_and_retry_is_explicit(service, app_record, monkeypatch):
    def fail(_request):
        raise RuntimeError('PDF compilation failed')
    monkeypatch.setattr(service, 'call_bridge', fail)
    task = service.enqueue('copy', app_record['id'], {}, str(uuid4()))
    service.run_task(task['id'])
    assert service.store.task(task['id'])['status'] == 'failed'
    assert service.bootstrap()['artifacts'] == []
    retried = service.retry(task['id'], str(uuid4()))
    assert retried['id'] != task['id'] and retried['status'] == 'queued'


def test_restart_marks_running_as_interrupted_without_repeating(service, app_record):
    task = service.enqueue('copy', app_record['id'], {}, str(uuid4()))
    service.store.execute("UPDATE tasks SET status='running' WHERE id=?", (task['id'],))
    service.start()
    service.close()
    assert service.store.task(task['id'])['status'] == 'interrupted'
    assert not service.bootstrap()['artifacts']


def test_api_validation_origin_and_download_paths(service):
    bad = {'job_description': 'test', 'source_url': 'javascript:alert(1)'}
    responses = api_calls(create_app(service, start_worker=False), [
        ('POST', '/api/applications', {'json': {}}),
        ('POST', '/api/refresh', {'json': {}, 'headers': {**HEADERS, 'Origin': 'https://evil.example'}}),
        ('POST', '/api/applications', {'json': bad, 'headers': HEADERS}),
        ('POST', '/api/applications', {'json': {'job_description': '  '}, 'headers': HEADERS}),
        ('GET', '/api/artifacts/not-a-uuid/download', {}),
        ('GET', '/api/artifacts/' + str(uuid4()) + '/download', {}),
        ('GET', '/api/bootstrap', {'headers': {'Host': 'evil.example'}}),
        ('POST', '/api/match', {'json': {'job_description': 'Machine learning engineer PyTorch CUDA deployment'}, 'headers': HEADERS}),
        ('GET', '/api/bootstrap', {}),
    ])
    assert [response.status_code for response in responses[:7]] == [403, 403, 422, 422, 422, 404, 400]
    assert responses[7].status_code == 200
    assert responses[7].json()[0]['key'] == 'ml-engineering'
    assert 'OPENAI_API_KEY' not in json.dumps(responses[8].json())


def test_match_api_accepts_method_and_rejects_unknown_method(service):
    responses = api_calls(create_app(service, start_worker=False), [
        ('POST', '/api/match', {'json': {
            'job_description': 'Machine learning engineer PyTorch CUDA deployment',
            'method': 'keyword',
        }, 'headers': HEADERS}),
        ('POST', '/api/match', {'json': {
            'job_description': 'Machine learning engineer',
            'method': 'mystery',
        }, 'headers': HEADERS}),
    ])

    assert responses[0].status_code == 200
    assert responses[0].json()[0]['method'] == 'keyword'
    assert responses[1].status_code == 422


def test_jev_score_is_normalized_and_composed(monkeypatch):
    from backend import jev

    answers = {}
    raw_scores = {'role_alignment': 4.0, 'requirements_coverage': 3.0, 'seniority_alignment': 2.0}
    for key, score in raw_scores.items():
        answers[key] = SimpleNamespace(score=score, confidence=.8, probabilities={int(score): 1.0})

    class FakeClient:
        def __init__(self, **_options):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def system_one(self, **_request):
            return SimpleNamespace(model='jev-test', scores=answers,
                                   usage=SimpleNamespace(input_tokens=123, output_tokens=20))

    monkeypatch.setattr(jev, 'TypeSafeClient', FakeClient)

    result = jev.score_cv('job', 'cv', 'secret', 'jev-test')

    assert result['score'] == pytest.approx(.825)
    assert result['confidence'] == pytest.approx(.8)
    assert result['components']['role_alignment']['score'] == 1.0
    assert result['model'] == 'jev-test'


def test_pdf_text_cache_uses_pdf_hash(tmp_path, monkeypatch):
    from backend import jev

    pdf = tmp_path / 'cv.pdf'
    cache = tmp_path / 'cache'
    pdf.write_bytes(b'%PDF-first')
    calls = []

    def extract(*_args, **_kwargs):
        calls.append(True)
        return SimpleNamespace(returncode=0, stdout='Extracted CV text\f')

    monkeypatch.setattr(jev.subprocess, 'run', extract)
    first = jev.extract_pdf_text(pdf, cache, 'ml-engineering')
    second = jev.extract_pdf_text(pdf, cache, 'ml-engineering')
    pdf.write_bytes(b'%PDF-second')
    third = jev.extract_pdf_text(pdf, cache, 'ml-engineering')

    assert first == second == third == 'Extracted CV text'
    assert len(calls) == 2
    assert len(list(cache.glob('ml-engineering-v1-*.txt'))) == 2


def test_semantic_cv_ranking_replaces_keyword_scores(service, monkeypatch):
    import backend.service as service_module

    monkeypatch.setenv('TYPESAFE_API_KEY', 'test-key')

    def rank(_job, candidates, _key, _model, _cache):
        results = []
        for candidate in candidates:
            best = candidate['key'] == 'applied-ai-llm'
            value = .82 if best else .40
            components = {name: {'score': value, 'confidence': .9, 'probabilities': {'3': 1.0}}
                          for name in ('role_alignment', 'requirements_coverage', 'seniority_alignment')}
            results.append({**candidate, 'score': value, 'confidence': .9, 'components': components,
                            'model': 'jev-test', 'usage': {'input_tokens': 100, 'output_tokens': 10}})
        return sorted(results, key=lambda item: -item['score'])

    monkeypatch.setattr(service_module, 'rank_families_with_jev', rank)
    rows = service.families('Build agentic retrieval systems and production RAG applications.')

    assert rows[0]['key'] == 'applied-ai-llm'
    assert rows[0]['score'] == 82.0
    assert rows[0]['method'] == 'jev'
    assert rows[0]['auto_select'] is True
    assert rows[0]['signals'] == ['Role 82%', 'Requirements 82%', 'Seniority 82%']


def test_keyword_matching_can_be_selected_when_jev_is_configured(service, monkeypatch):
    import backend.service as service_module

    monkeypatch.setenv('TYPESAFE_API_KEY', 'test-key')
    monkeypatch.setattr(service_module, 'rank_families_with_jev',
                        lambda *_args, **_kwargs: pytest.fail('JEV should not be called for keyword matching'))

    rows = service.families('Machine learning engineer using PyTorch and CUDA in production.',
                            method='keyword')

    assert rows[0]['key'] == 'ml-engineering'
    assert rows[0]['method'] == 'keyword'


def test_jev_failure_falls_back_to_keyword_ranking(service, monkeypatch):
    import backend.service as service_module

    monkeypatch.setenv('TYPESAFE_API_KEY', 'test-key')
    monkeypatch.setattr(service_module, 'rank_families_with_jev',
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(service_module.JevError('TypeSafe unavailable.')))

    rows = service.families('Machine learning engineer using PyTorch and CUDA in production.')

    assert rows[0]['key'] == 'ml-engineering'
    assert rows[0]['method'] == 'keyword-fallback'
    assert rows[0]['auto_select'] is True
    assert 'Keyword matching was used instead' in rows[0]['warning']


def test_missing_provider_key_is_not_a_silent_copy(service, app_record):
    with pytest.raises(ValueError, match='OPENAI_API_KEY'):
        service.enqueue('cv', app_record['id'], {}, str(uuid4()))
    with pytest.raises(ValueError, match='OPENAI_API_KEY'):
        service.enqueue('letter', app_record['id'], {}, str(uuid4()))
    assert service.bootstrap()['tasks'] == []


def test_unknown_family_and_reference_paths_are_rejected(service, app_record):
    with pytest.raises(ValueError, match='supported CV'):
        service.enqueue('copy', app_record['id'], {'family': '../../secrets'}, str(uuid4()))
    with pytest.raises(ValueError, match='outside'):
        service.contained(service.root / '../private')
    with pytest.raises(ValueError, match='read-only'):
        service.contained(service.root / service.manifest['components']['interviews']['path'] / 'test.pdf')


def test_import_is_repeatable_and_does_not_overwrite_edits(service):
    folder = service.root / service.manifest['paths']['applications'] / 'undated/imported'
    folder.mkdir(parents=True)
    original = {'schema_version': 1, 'id': str(uuid4()), 'company': 'Imported', 'role': 'Engineer', 'artifacts': []}
    meta = folder / 'application.json'
    meta.write_text(json.dumps(original))
    (service.root / service.manifest['paths']['application_index']).write_text(json.dumps({'applications': [
        {'path': str(folder.relative_to(service.root)), 'metadata': str(meta.relative_to(service.root))}]}))
    service.import_collections()
    service.save_application({'company': 'Edited', 'role': 'Engineer', 'job_description': 'A role', 'source_url': ''}, original['id'])
    service.import_collections()
    assert service.application(original['id'])['company'] == 'Edited'
    assert json.loads(meta.read_text()) == original


def test_real_bridge_copy_uses_original_pdf_without_ai(service, app_record):
    # Use the already installed interpreter, but all outputs belong to the fixture.
    service.scout = WORKSPACE / 'integrations/job-scout'
    task = service.enqueue('copy', app_record['id'], {'family': 'ml-engineering'}, str(uuid4()))
    service.run_task(task['id'])
    result = service.store.task(task['id'])
    assert result['status'] == 'completed', result
    assert result['result']['method'] == 'exact-copy'
    path, _ = service.file(result['result']['artifact_id'])
    assert sha(path) == sha(service.family_pdf('ml-engineering'))


def test_demo_flag_ignores_personal_config_and_uses_example_inputs(service, app_record, monkeypatch):
    root = service.root
    shutil.copy2(WORKSPACE / 'workspace.demo.json', root / 'workspace.demo.json')
    (root / 'workspace.json').write_text('personal config is not used in demo mode')
    monkeypatch.setenv('CAREER_DEMO', '1')

    demo = CareerService(root=root)
    demo.scout = WORKSPACE / 'integrations/job-scout'
    assert demo.private == root / '.demo_runtime'
    assert demo.curriculum == root / 'private_example/curriculum'
    task = demo.enqueue('copy', app_record['id'], {'family': 'ml-engineering'}, str(uuid4()))
    demo.run_task(task['id'])
    assert demo.store.task(task['id'])['status'] == 'completed'
    assert not (root / 'private').exists()


def test_real_cover_letter_renderer_with_edited_text(service, app_record):
    service.letters = WORKSPACE / 'packages/cover-letter-engine'
    task = service.enqueue('letter-pdf', app_record['id'], {'letter': 'Dear hiring team,\n\nThis is an offline PDF rendering check.\n\nExample Candidate'}, str(uuid4()))
    service.run_task(task['id'])
    result = service.store.task(task['id'])
    assert result['status'] == 'completed', result
    from pypdf import PdfReader
    path, record = service.file(result['result']['artifact_id'])
    assert 'offline PDF rendering check' in PdfReader(path).pages[0].extract_text()
    assert record['state'] == 'draft'


@pytest.mark.skipif(not shutil.which('pdflatex'), reason='LaTeX is not installed')
def test_real_rebuild_is_isolated_and_keeps_original_family_pdf(service, app_record):
    original = service.family_pdf('ml-engineering')
    before = sha(original)
    service.scout = WORKSPACE / 'integrations/job-scout'
    task = service.enqueue('copy', app_record['id'], {'family': 'ml-engineering', 'rebuild': True}, str(uuid4()))
    service.run_task(task['id'])
    result = service.store.task(task['id'])
    assert result['status'] == 'completed', result
    assert result['result']['method'] == 'built-existing-source'
    assert sha(original) == before
    from pypdf import PdfReader
    path, _ = service.file(result['result']['artifact_id'])
    assert len(PdfReader(path).pages) >= 1
    assert not (service.curriculum / 'build').exists()


def test_retry_keeps_original_input_after_application_edit(service, app_record, monkeypatch):
    def fail(_request):
        raise RuntimeError('Deliberate test failure')
    monkeypatch.setattr(service, 'call_bridge', fail)
    task = service.enqueue('copy', app_record['id'], {}, str(uuid4()))
    service.run_task(task['id'])
    fields = {k: app_record[k] for k in ('company', 'role', 'job_description', 'source_url')}
    service.save_application({**fields, 'job_description': 'A new unrelated role'}, app_record['id'])
    retried = service.retry(task['id'], str(uuid4()))
    payload = json.loads(service.store.one('SELECT payload FROM tasks WHERE id=?', (retried['id'],))['payload'])
    assert payload['application']['job_description'] == fields['job_description']


@pytest.mark.parametrize('remote', [False, True])
@pytest.mark.skipif(not JOB_SCOUT_IMPORTABLE, reason='Runs in the separate Python 3.12 Job Scout environment')
def test_search_adapter_preserves_query_and_filters_eligibility(service, monkeypatch, remote):
    from backend.bridge import main
    from job_scout.graph.schemas import JobPosting
    from job_scout.tools import jobs_api

    monkeypatch.setenv('OPIK_ENABLED', 'false')
    calls = []
    def search(query, **options):
        calls.append((query, options))
        rows = [('local', 'Argentina', False)] if not options['remote'] else [
            ('global', 'Worldwide', True), ('restricted', 'United States only', True)]
        return [JobPosting(job_id=name, title='Research engineer', company=name,
                           location=location, remote=is_remote, source='cache',
                           description='Research position', url='https://example.com/' + name)
                for name, location, is_remote in rows], ['cache']
    monkeypatch.setattr(jobs_api, 'run_search', search)
    request = service.root / 'search-request.json'
    request.write_text(json.dumps({'root': str(service.root), 'output': str(service.data / 'search-test'),
                                   'kind': 'search', 'task_id': str(uuid4()),
                                   'options': {'role': 'Research engineer', 'location': 'Argentina',
                                               'remote': remote, 'limit': 10}}))
    result = main(request)
    assert all(query == 'Research engineer' for query, _ in calls)
    assert len(calls) == (2 if remote else 1)
    assert [row['job']['job_id'] for row in result['jobs']] == (['local', 'global'] if remote else ['local'])
    assert result['ranking'] == 'source-order'
    assert all(row['fit_score'] is None for row in result['jobs'])
    assert result['warnings']


def test_schema_upgrade_is_backed_up_and_preserves_v1_rows(tmp_path):
    database = tmp_path / 'career.sqlite3'
    with sqlite3.connect(database) as db:
        db.executescript('''
            CREATE TABLE applications (
                id TEXT PRIMARY KEY, company TEXT NOT NULL, role TEXT NOT NULL,
                job_description TEXT NOT NULL, source_url TEXT NOT NULL DEFAULT '',
                folder TEXT NOT NULL, imported INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE tasks (
                id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL, kind TEXT NOT NULL,
                application_id TEXT REFERENCES applications(id), status TEXT NOT NULL,
                payload TEXT NOT NULL, result TEXT, message TEXT NOT NULL DEFAULT '', error TEXT,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE artifacts (
                id TEXT PRIMARY KEY, application_id TEXT NOT NULL REFERENCES applications(id),
                kind TEXT NOT NULL, state TEXT NOT NULL, path TEXT UNIQUE NOT NULL,
                filename TEXT NOT NULL, sha256 TEXT NOT NULL, provenance TEXT NOT NULL,
                saved_from TEXT UNIQUE REFERENCES artifacts(id), created_at TEXT NOT NULL
            );
            INSERT INTO applications VALUES ('old','Legacy Co','Scientist','Role','',
                'applications/legacy',1,'2026-01-01','2026-01-01');
            PRAGMA user_version=1;
        ''')
    store = Store(database)
    assert store.one('PRAGMA user_version')['user_version'] == 2
    assert store.one('SELECT company,status,current_stage FROM applications WHERE id="old"') == {
        'company': 'Legacy Co', 'status': 'draft', 'current_stage': 'application'}
    assert database.with_name('career.sqlite3.pre-v2.bak').is_file()


def test_tracking_events_reminders_dashboard_and_statistics(service, app_record):
    tracked = service.update_tracking(app_record['id'], {
        'status': 'submitted', 'current_stage': 'application', 'applied_on': '2026-09-01',
        'next_action': 'Check recruiter response'})
    assert tracked['status'] == 'submitted'
    assert any(item['reminder_type'] == 'follow_up' for item in tracked['reminders'])

    scheduled = service.add_event(app_record['id'], {
        'event_type': 'interview_scheduled', 'stage': 'recruiter_screen',
        'scheduled_at': '2099-10-10T14:00:00+00:00', 'occurred_at': None, 'completed_at': None,
        'outcome': '', 'contact_name': 'Recruiter', 'notes': 'Initial screening'})
    assert scheduled['status'] == 'interview_scheduled'
    assert service.dashboard()['counts']['upcoming'] == 1
    stats = service.statistics()
    assert stats['submitted'] == 1 and stats['interviews'] == 1
    assert stats['interview_rate'] == 1.0

    following = service.update_tracking(app_record['id'], {
        'status': 'in_process', 'current_stage': 'recruiter_screen'})
    assert following['status'] == 'in_process'
    assert service.dashboard()['counts']['following'] == 1

    action_required = service.update_tracking(app_record['id'], {
        'status': 'action_required', 'current_stage': 'application'})
    assert action_required['status'] == 'action_required'
    assert service.dashboard()['counts']['action_required'] == 1

    rejected = service.update_tracking(app_record['id'], {
        'status': 'rejected', 'current_stage': 'recruiter_screen'})
    assert rejected['closed_on']
    assert all(item['status'] != 'open' for item in rejected['reminders'])


def test_tracking_api_contract(service, app_record):
    app = create_app(service, start_worker=False)
    responses = api_calls(app, [
        ('PATCH', f'/api/applications/{app_record["id"]}/tracking', {
            'headers': HEADERS, 'json': {'status': 'submitted', 'applied_on': '2026-09-01'}}),
        ('POST', f'/api/applications/{app_record["id"]}/events', {
            'headers': HEADERS, 'json': {'event_type': 'interview_scheduled',
                                        'stage': 'recruiter_screen',
                                        'scheduled_at': '2099-10-10T14:00:00+00:00'}}),
        ('GET', f'/api/applications/{app_record["id"]}', {}),
        ('GET', '/api/dashboard', {}),
    ])
    assert [response.status_code for response in responses] == [200, 200, 200, 200]
    assert responses[2].json()['status'] == 'interview_scheduled'
    assert responses[3].json()['counts']['upcoming'] == 1


def test_excel_tracker_import_preview_commit_and_repeat(service):
    tracker = service.root / service.manifest['paths']['tracker']
    headers = ('Company', 'Role', 'Post', 'Status', 'Applied', 'Application date', 'HR init', 'Last news')
    records = (
        ('Northstar Transit Labs', 'ML Engineer', 'https://example.com/job/1', 'Presented', 'Yes', '2026-01-10', '', ''),
        ('Meridian Analytics', 'Data Scientist', 'https://example.com/job/2', 'Pending Interview', 'Yes', '2026-02-01', '2099-01-15', ''),
        ('Quartz Research', 'Research Scientist', 'https://example.com/job/3', 'Rejected', 'Yes', '2026-03-01', '', '2026-03-21'),
    )

    def row_xml(number, values):
        cells = ''.join(f'<c r="{chr(65 + index)}{number}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'
                        for index, value in enumerate(values))
        return f'<row r="{number}">{cells}</row>'

    rows = row_xml(1, headers) + ''.join(row_xml(index, values) for index, values in enumerate(records, 2))
    with ZipFile(tracker, 'w', compression=ZIP_DEFLATED) as workbook:
        workbook.writestr('[Content_Types].xml',
                          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                          '<Default Extension="xml" ContentType="application/xml"/>'
                          '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                          '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                          '</Types>')
        workbook.writestr('_rels/.rels',
                          '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                          '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                          '</Relationships>')
        workbook.writestr('xl/workbook.xml',
                          '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                          'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                          '<sheets><sheet name="apply" sheetId="1" r:id="rId1"/></sheets></workbook>')
        workbook.writestr('xl/_rels/workbook.xml.rels',
                          '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                          '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
                          '</Relationships>')
        workbook.writestr('xl/worksheets/sheet1.xml',
                          '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                          f'<sheetData>{rows}</sheetData></worksheet>')
    preview = service.import_tracker(False)
    assert preview['total'] == 3
    assert preview['summary']['create'] == 3

    result = service.import_tracker(True)
    assert result['created'] == 3 and result['linked'] == 0
    assert service.store.one('SELECT COUNT(*) AS count FROM import_rows')['count'] == 3
    assert service.store.one("SELECT COUNT(*) AS count FROM applications WHERE import_source='JobSearch.xlsx'")['count'] == 3
    repeated = service.import_tracker(True)
    assert repeated['already_imported'] is True
    assert service.store.one('SELECT COUNT(*) AS count FROM import_batches')['count'] == 1
    imported_events = service.store.one('SELECT COUNT(*) AS count FROM application_events WHERE source="JobSearch.xlsx"')['count']

    # XLSX files remain valid with trailing bytes; this simulates an uploaded revision
    # with the same source rows and verifies reconciliation rather than duplication.
    tracker.write_bytes(tracker.read_bytes() + b'\n')
    revised = service.import_tracker(True)
    assert revised['linked'] == 3 and revised['created'] == 0
    assert service.store.one('SELECT COUNT(*) AS count FROM import_batches')['count'] == 2
    assert service.store.one('SELECT COUNT(*) AS count FROM application_events WHERE source="JobSearch.xlsx"')['count'] == imported_events
