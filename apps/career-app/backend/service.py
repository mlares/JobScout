from __future__ import annotations

import fcntl
import hashlib
import importlib.util
import json
import os
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import threading
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from statistics import median
from uuid import NAMESPACE_URL, uuid4, uuid5

from dotenv import dotenv_values

from .jev import DEFAULT_MODEL as DEFAULT_JEV_MODEL
from .jev import JevError
from .jev import rank_families as rank_families_with_jev
from .store import Store, now
from .tracker_import import STAGES, STATUSES, TERMINAL_STATUSES, TrackerImporter

MIN_SEMANTIC_SCORE = 55
MIN_SEMANTIC_CONFIDENCE = .35
MIN_SEMANTIC_MARGIN = 3


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def slug(value):
    return re.sub(r'[^a-z0-9]+', '-', value.lower()).strip('-')[:80] or 'application'


class CareerService:
    def __init__(self, root=None, data=None):
        self.root = Path(root or os.getenv('CAREER_WORKSPACE_ROOT') or Path(__file__).resolve().parents[3]).resolve()
        self.manifest = json.loads((self.root / 'workspace.json').read_text())
        self.private = (self.root / self.manifest.get('private_root', 'private')).resolve()
        self.secrets = self.manifest.get('secrets', {})
        self.data = Path(data or os.getenv('CAREER_DATA_DIR') or self.private / 'career-app/data').resolve()
        self.sent = self.root / self.manifest['paths'].get('sent', 'sent')
        self.store = Store(self.data / 'career.sqlite3')
        self.stop = threading.Event()
        self.thread = None
        self.process = None
        self.process_lock = threading.Lock()
        self.worker_lock = None
        self.curriculum = self.root / self.manifest['paths']['curriculum']
        self.app_root = self.root / self.manifest['components']['career_app']['path']
        self.scout = self.root / self.manifest['components']['job_scout']['path']
        self.letters = self.root / self.manifest['components']['cover_letters']['path']
        spec = importlib.util.spec_from_file_location('career_cv_selector_' + uuid4().hex, self.curriculum / 'scripts/tailor_cv.py')
        self.selector = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = self.selector
        spec.loader.exec_module(self.selector)
        self.import_collections()

    def contained(self, path, parent=None):
        path = Path(path).resolve()
        parent = Path(parent or self.root).resolve()
        if not path.is_relative_to(parent):
            raise ValueError('File path is outside the allowed workspace.')
        # Interview material is never a file-management target.
        reference = (self.root / self.manifest['components']['interviews']['path']).resolve()
        if path.is_relative_to(reference):
            raise ValueError('The interview reference is read-only and outside this app.')
        return path

    def app_environment(self):
        path = self.root / self.secrets.get('career_app', 'private/secrets/career-app.env')
        values = dotenv_values(path) if path.is_file() else {}
        values.update(os.environ)
        return values

    @staticmethod
    def _automatic_choice(rows):
        for row in rows:
            row['auto_select'] = False
        if not rows:
            return rows
        if rows[0]['method'] == 'jev':
            margin = rows[0]['score'] - rows[1]['score'] if len(rows) > 1 else rows[0]['score']
            rows[0]['auto_select'] = (rows[0]['score'] >= MIN_SEMANTIC_SCORE and
                                      rows[0]['confidence'] >= MIN_SEMANTIC_CONFIDENCE and
                                      margin >= MIN_SEMANTIC_MARGIN)
            if not rows[0]['auto_select']:
                rows[0]['selection_note'] = 'The semantic result is weak or too close to the runner-up. Choose a CV family.'
        else:
            rows[0]['auto_select'] = rows[0]['score'] > 0
            if not rows[0]['auto_select']:
                rows[0]['selection_note'] = 'No meaningful match. Choose a CV family.'
        return rows

    def families(self, job='', method='auto'):
        if method not in ('auto', 'jev', 'keyword'):
            raise ValueError('Choose either Jev or keyword CV matching.')
        shared_sources = list((self.curriculum / 'content').rglob('*.tex')) + list((self.curriculum / 'assets').glob('*'))
        shared_mtime = max((p.stat().st_mtime for p in shared_sources if p.is_file()), default=0)
        rows = []
        for family, score, signals in self.selector.rank_families(job):
            source = self.curriculum / family.source
            pdf = self.curriculum / 'dist/short' / family.key / source.with_suffix('.pdf').name
            rows.append({'key': family.key, 'label': family.key.replace('-', ' ').title(), 'score': score,
                         'signals': signals, 'pdf_exists': pdf.is_file(), 'method': 'keyword',
                         'stale': pdf.is_file() and max(shared_mtime, source.stat().st_mtime) > pdf.stat().st_mtime,
                         'source': str(source.relative_to(self.root))})
        if not job.strip() or method == 'keyword':
            return self._automatic_choice(rows)
        environment = self.app_environment()
        api_key = (environment.get('TYPESAFE_API_KEY') or '').strip()
        if not api_key:
            return self._automatic_choice(rows)
        candidates = []
        for row in rows:
            if not row['pdf_exists']:
                rows[0]['warning'] = 'Semantic matching needs every reusable CV PDF. Keyword matching was used instead.'
                rows[0]['method'] = 'keyword-fallback'
                return self._automatic_choice(rows)
            candidates.append({'key': row['key'], 'pdf': self.family_pdf(row['key'])})
        try:
            semantic = rank_families_with_jev(job, candidates, api_key,
                                              environment.get('TYPESAFE_MODEL') or DEFAULT_JEV_MODEL,
                                              self.data / 'cv-text')
        except JevError as exc:
            for row in rows:
                row['method'] = 'keyword-fallback'
            rows[0]['warning'] = f'{exc} Keyword matching was used instead.'
            return self._automatic_choice(rows)
        metadata = {row['key']: row for row in rows}
        ranked = []
        component_labels = {'role_alignment': 'Role', 'requirements_coverage': 'Requirements',
                            'seniority_alignment': 'Seniority'}
        for result in semantic:
            row = metadata[result['key']]
            components = {key: {'score': round(value['score'] * 100, 1),
                                'confidence': round(value['confidence'], 3),
                                'probabilities': value['probabilities']}
                          for key, value in result['components'].items()}
            row.update({'score': round(result['score'] * 100, 1),
                        'confidence': round(result['confidence'], 3),
                        'signals': [f'{component_labels[key]} {components[key]["score"]:.0f}%'
                                    for key in component_labels],
                        'components': components, 'method': 'jev', 'model': result['model'],
                        'usage': result['usage']})
            ranked.append(row)
        return self._automatic_choice(ranked)

    def family_pdf(self, key):
        family = next((f for f in self.selector.FAMILIES if f.key == key), None)
        if not family:
            raise KeyError('Unknown CV family')
        path = self.contained(self.curriculum / 'dist/short' / key / Path(family.source).with_suffix('.pdf').name)
        if not path.is_file():
            raise KeyError('This CV PDF has not been built yet.')
        return path

    def settings(self):
        profile_path = self.root / self.manifest['paths']['profile']
        profile = json.loads(profile_path.read_text())
        scout_env = {**dotenv_values(self.root / self.secrets.get('job_scout', 'private/secrets/job-scout.env')), **os.environ}
        letter_env = {**dotenv_values(self.root / self.secrets.get('cover_letter', 'private/secrets/cover-letter.env')), **os.environ}
        app_env = self.app_environment()
        model = scout_env.get('SCOUT_MODEL') or 'openai:gpt-4o-mini'
        provider = model.split(':')[0]
        search_key = {'openai': 'OPENAI_API_KEY', 'anthropic': 'ANTHROPIC_API_KEY', 'groq': 'GROQ_API_KEY', 'google_genai': 'GOOGLE_API_KEY'}.get(provider)
        candidate = (self.private / 'job-scout/candidate/profile.json').is_file()
        return {'name': profile.get('name', ''), 'headline': profile.get('headline', ''),
                'location': profile.get('location', ''), 'fact_count': len(profile.get('facts', [])),
                'cv_ai_ready': bool(scout_env.get('OPENAI_API_KEY')),
                'letter_ai_ready': bool(letter_env.get('OPENAI_API_KEY')),
                'search_ai_ready': bool(candidate and search_key and scout_env.get(search_key)),
                'cv_match_ai_ready': bool(app_env.get('TYPESAFE_API_KEY')),
                'candidate_ready': candidate, 'compiler_ready': bool(shutil.which('pdflatex')),
                'cv_model': scout_env.get('OPENAI_MODEL') or 'gpt-5',
                'letter_model': letter_env.get('COVER_LETTER_MODEL') or 'gpt-5.6-terra',
                'search_model': model,
                'cv_match_model': app_env.get('TYPESAFE_MODEL') or DEFAULT_JEV_MODEL}

    def application(self, app_id):
        app = self.store.one('SELECT * FROM applications WHERE id=?', (app_id,))
        if not app:
            raise KeyError('Application not found')
        return app

    def save_application(self, fields, app_id=None):
        stamp = now()
        if app_id:
            app = self.application(app_id)
            self.store.execute('UPDATE applications SET company=?,role=?,job_description=?,source_url=?,updated_at=? WHERE id=?',
                               (fields['company'], fields['role'], fields['job_description'], fields['source_url'], stamp, app_id))
        else:
            app_id = str(uuid4())
            name = slug(fields['company'] + '-' + fields['role']) + '-' + app_id[:8]
            folder = self.contained(self.root / self.manifest['paths']['applications'] / stamp[:4] / name)
            folder.mkdir(parents=True, exist_ok=False)
            self.store.execute('''INSERT INTO applications(
                               id,company,role,job_description,source_url,folder,imported,created_at,updated_at)
                               VALUES (?,?,?,?,?,?,?,?,?)''',
                               (app_id, fields['company'], fields['role'], fields['job_description'], fields['source_url'],
                                str(folder.relative_to(self.root)), 0, stamp, stamp))
            app = self.application(app_id)
        # Existing imported source metadata remains untouched. The app's DB owns
        # current preparation fields; the Excel tracker is never written here.
        if not app['imported']:
            folder = self.contained(self.root / app['folder'])
            (folder / 'job-description.txt').write_text(fields['job_description'])
            metadata = {'schema_version': 1, 'id': app_id, 'company': fields['company'], 'role': fields['role'],
                        'status': None, 'applied_at': None, 'source_url': fields['source_url'],
                        'job_description': 'job-description.txt', 'cv_source': None, 'artifacts': [],
                        'managed_by': 'career-app', 'artifact_registry': 'private/career-app/data/career.sqlite3'}
            (folder / 'application.json').write_text(json.dumps(metadata, indent=2) + '\n')
        return self.application(app_id)

    def import_collections(self):
        index_path = self.root / self.manifest['paths']['application_index']
        if not index_path.is_file():
            return
        for entry in json.loads(index_path.read_text()).get('applications', []):
            metadata_path = self.contained(self.root / entry['metadata'])
            meta = json.loads(metadata_path.read_text())
            folder = self.contained(self.root / entry['path'])
            text = ''
            if meta.get('job_description'):
                source = self.contained(folder / meta['job_description'])
                if source.is_file():
                    text = source.read_text()[:80000]
            stamp = now()
            self.store.execute('''INSERT OR IGNORE INTO applications(
                               id,company,role,job_description,source_url,folder,imported,created_at,updated_at)
                               VALUES (?,?,?,?,?,?,?,?,?)''',
                               (meta['id'], meta.get('company') or '', meta.get('role') or '', text,
                                meta.get('source_url') or '', str(folder.relative_to(self.root)), 1, stamp, stamp))
            for item in meta.get('artifacts', []):
                path = self.contained(folder / item['path'])
                if path.suffix.lower() != '.pdf' or not path.is_file():
                    continue
                relative = str(path.relative_to(self.root))
                if self.store.one('SELECT id FROM artifacts WHERE path=?', (relative,)):
                    continue
                key = str(uuid5(NAMESPACE_URL, 'career-artifact:' + relative))
                kind = 'cover-letter' if 'cover' in path.name.lower() or path.name.startswith('CL_') or path.is_relative_to(self.letters) else 'cv-imported'
                state = 'submitted' if item.get('state') == 'submitted' else 'draft'
                self.store.execute('INSERT OR IGNORE INTO artifacts VALUES (?,?,?,?,?,?,?,?,?,?)',
                                   (key, meta['id'], kind, state, relative, path.name, sha(path),
                                    json.dumps({'method': 'imported', 'original_path': relative}), None, stamp))

    def artifact(self, artifact_id):
        row = self.store.one('''SELECT a.*,p.company,p.role FROM artifacts a JOIN applications p
                               ON p.id=a.application_id WHERE a.id=?''', (artifact_id,))
        if not row:
            raise KeyError('Document not found')
        row['provenance'] = json.loads(row['provenance'])
        return row

    def file(self, artifact_id):
        row = self.artifact(artifact_id)
        path = self.contained(self.root / row['path'])
        if not path.is_file():
            raise KeyError('The original document is no longer at its recorded location.')
        return path, row

    def add_pdf(self, application_id, source, kind, state, provenance, saved_from=None):
        app = self.application(application_id)
        source = self.contained(source)
        if source.suffix.lower() != '.pdf' or not source.is_file():
            raise ValueError('The generator did not return a valid PDF file.')
        with source.open('rb') as stream:
            if stream.read(5) != b'%PDF-':
                raise ValueError('The generator did not return a valid PDF file.')
        # One transaction allocates a version and records the copy. A repeated
        # save of the same draft returns its original saved copy.
        with self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if saved_from:
                previous = db.execute('SELECT id FROM artifacts WHERE saved_from=?', (saved_from,)).fetchone()
                if previous:
                    return self.artifact(previous['id'])
            count = db.execute('SELECT COUNT(*) FROM artifacts WHERE application_id=? AND kind=? AND state=?',
                               (application_id, kind, state)).fetchone()[0]
            artifact_id = str(uuid4())
            folder = self.sent / now()[:4] / (slug(app['company'] + '-' + app['role']) + '-' + application_id[:8]) if state == 'sent' else self.root / app['folder'] / 'drafts'
            folder = self.contained(folder)
            folder.mkdir(parents=True, exist_ok=True)
            version = count + 1
            target = folder / f'{kind}-v{version:03d}.pdf'
            while target.exists():
                version += 1
                target = folder / f'{kind}-v{version:03d}.pdf'
            # Exclusive creation avoids overwriting manually added files too.
            with source.open('rb') as original, target.open('xb') as copied:
                shutil.copyfileobj(original, copied)
                copied.flush()
                os.fsync(copied.fileno())
            stamp = now()
            db.execute('INSERT INTO artifacts VALUES (?,?,?,?,?,?,?,?,?,?)',
                       (artifact_id, application_id, kind, state, str(target.relative_to(self.root)),
                        target.name, sha(target), json.dumps(provenance), saved_from, stamp))
        return self.artifact(artifact_id)

    def save_to_sent(self, artifact_id):
        path, artifact = self.file(artifact_id)
        if artifact['state'] != 'draft':
            return artifact
        return self.add_pdf(artifact['application_id'], path, artifact['kind'], 'sent',
                            artifact['provenance'], saved_from=artifact_id)

    def enqueue(self, kind, application_id, options, request_id, snapshot=None):
        previous = self.store.one('SELECT id FROM tasks WHERE request_id=?', (request_id,))
        if previous:
            return self.store.task(previous['id'])
        app = self.application(application_id) if application_id else None
        if snapshot is not None:
            app = snapshot
        if kind != 'search' and (not app or not app['job_description'].strip()):
            raise ValueError('Save a job description before generating documents.')
        if options.get('family') and options['family'] not in {f.key for f in self.selector.FAMILIES}:
            raise ValueError('Choose a supported CV family.')
        configuration = self.settings()
        if kind == 'cv' and not configuration['cv_ai_ready']:
            raise ValueError('Configure the job agent OPENAI_API_KEY before requesting AI CV tailoring.')
        if kind == 'letter' and not configuration['letter_ai_ready']:
            raise ValueError('Configure the cover-letter OPENAI_API_KEY before requesting AI generation.')
        if kind == 'search' and options.get('ai_rank') and not configuration['search_ai_ready']:
            raise ValueError('AI ranking needs a supported provider key and the saved Job Scout candidate profile.')
        if kind == 'letter-pdf' and not options.get('letter', '').strip():
            raise ValueError('The cover letter cannot be empty.')
        if kind in ('copy', 'cv') and not options.get('family'):
            rankings = self.families(app['job_description'])
            if not rankings or not rankings[0].get('auto_select'):
                raise ValueError(rankings[0].get('selection_note', 'Choose a CV family explicitly.') if rankings else
                                 'Choose a CV family explicitly.')
            options = {**options, 'family': rankings[0]['key']}
        payload = {'application': app, 'options': options}
        task_id = str(uuid4())
        stamp = now()
        try:
            self.store.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                               (task_id, request_id, kind, application_id, 'queued', json.dumps(payload), None,
                                'Waiting for the document worker.', None, stamp, stamp))
        except sqlite3.IntegrityError:
            previous = self.store.one('SELECT id FROM tasks WHERE request_id=?', (request_id,))
            if previous:
                return self.store.task(previous['id'])
            raise
        return self.store.task(task_id)

    def retry(self, task_id, request_id):
        original = self.store.one('SELECT * FROM tasks WHERE id=?', (task_id,))
        if not original:
            raise KeyError('Task not found')
        if original['status'] not in ('failed', 'interrupted'):
            raise ValueError('Only failed or interrupted tasks can be retried.')
        # Insert the original input snapshot atomically before the worker can claim it.
        payload = json.loads(original['payload'])
        return self.enqueue(original['kind'], original['application_id'], payload['options'], request_id,
                            snapshot=payload.get('application'))

    def start(self):
        self.worker_lock = (self.data / 'worker.lock').open('a')
        try:
            fcntl.flock(self.worker_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Career Workspace is already running for this data directory. Use one server process.') from None
        self.store.execute("UPDATE tasks SET status='interrupted',error='The app stopped during this operation. Retry to run it again.',updated_at=? WHERE status='running'", (now(),))
        self.thread = threading.Thread(target=self.worker, name='career-worker', daemon=True)
        self.thread.start()

    def close(self):
        self.stop.set()
        with self.process_lock:
            if self.process and self.process.poll() is None:
                os.killpg(self.process.pid, signal.SIGTERM)
        if self.thread:
            self.thread.join(timeout=5)
        if self.worker_lock:
            fcntl.flock(self.worker_lock, fcntl.LOCK_UN)
            self.worker_lock.close()

    def worker(self):
        while not self.stop.is_set():
            row = self.store.one("SELECT id FROM tasks WHERE status='queued' ORDER BY created_at LIMIT 1")
            if row:
                self.run_task(row['id'])
            else:
                self.stop.wait(.4)

    def call_bridge(self, request):
        interpreter = Path(sys.executable)
        job_dir = self.contained(self.data / 'tasks' / request['task_id'])
        job_dir.mkdir(parents=True, exist_ok=True)
        path = job_dir / 'request.json'
        request['output'] = str(job_dir)
        path.write_text(json.dumps(request))
        environment = os.environ.copy()
        environment['PYTHONDONTWRITEBYTECODE'] = '1'
        environment['OPIK_ENABLED'] = 'false'
        # One workspace environment imports the two component source trees directly.
        environment['PYTHONPATH'] = os.pathsep.join((str(self.scout / 'src'), str(self.letters / 'src')))
        environment.update({key: value for key, value in dotenv_values(
            self.root / self.secrets.get('job_scout', 'private/secrets/job-scout.env')).items() if value is not None})
        environment.update({key: value for key, value in dotenv_values(
            self.root / self.secrets.get('cover_letter', 'private/secrets/cover-letter.env')).items() if value is not None})
        environment['CV_REPOSITORY_PATH'] = str(self.curriculum)
        environment['JOB_SCOUT_DATA_DIR'] = str(self.private / 'job-scout')
        with self.process_lock:
            if self.stop.is_set():
                raise RuntimeError('Application is shutting down.')
            self.process = subprocess.Popen([str(interpreter), str(Path(__file__).with_name('bridge.py')), str(path)],
                                            cwd=self.root, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                            text=True, start_new_session=True)
            process = self.process
        try:
            stdout, _stderr = process.communicate(timeout=660)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
            raise RuntimeError('The operation timed out. No existing files were overwritten; you can retry.') from None
        finally:
            with self.process_lock:
                self.process = None
        try:
            reply = json.loads(stdout)
        except (ValueError, UnboundLocalError):
            raise RuntimeError('The tool stopped before returning a result. Check its local dependencies and retry.') from None
        if not reply.get('ok'):
            raise RuntimeError(reply.get('error', 'The tool failed.'))
        return reply['result']

    def run_task(self, task_id):
        with self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT * FROM tasks WHERE id=? AND status='queued'", (task_id,)).fetchone()
            if not row:
                return
            db.execute("UPDATE tasks SET status='running',message=?,updated_at=? WHERE id=?", ('Working on your request…', now(), task_id))
        payload = json.loads(row['payload'])
        app = payload.get('application')
        try:
            request = {'root': str(self.root), 'task_id': task_id, 'kind': row['kind'], 'year': int(now()[:4]), **payload}
            result = self.call_bridge(request)
            if 'pdf' in result:
                source = self.contained(result.pop('pdf'), self.data / 'tasks' / task_id)
                kind = {'copy': 'cv-matched', 'cv': 'cv-tailored', 'letter-pdf': 'cover-letter'}[row['kind']]
                provenance = {**result, 'task_id': task_id,
                              'job_description_sha256': hashlib.sha256(app['job_description'].encode()).hexdigest()}
                artifact = self.add_pdf(row['application_id'], source, kind,
                                        'sent' if row['kind'] == 'copy' else 'draft', provenance)
                result['artifact_id'] = artifact['id']
                if row['kind'] == 'copy' and result.get('method') == 'exact-copy' and any(f['key'] == result.get('family') and f['stale'] for f in self.families()):
                    result.setdefault('warnings', []).append('Copied the existing PDF unchanged. Its source is newer; rebuild the reusable CV if you need the source changes.')
            message = 'Copied to sent.' if row['kind'] == 'copy' else 'Complete. Your result is saved.'
            self.store.execute("UPDATE tasks SET status='completed',result=?,message=?,updated_at=? WHERE id=?", (json.dumps(result), message, now(), task_id))
        except Exception as exc:
            status = 'interrupted' if self.stop.is_set() else 'failed'
            message = str(exc) if isinstance(exc, (ValueError, RuntimeError)) else 'Operation failed. Existing files are unchanged; please retry.'
            self.store.execute('UPDATE tasks SET status=?,error=?,updated_at=? WHERE id=?', (status, message, now(), task_id))

    @staticmethod
    def _timestamp(value, field='Date'):
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        except ValueError as exc:
            raise ValueError(f'{field} must be an ISO date and time.') from exc
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC).isoformat()

    def applications(self, status=None, stage=None, due=None, search=None):
        conditions, args = [], []
        if status:
            conditions.append('status=?')
            args.append(status)
        if stage:
            conditions.append('current_stage=?')
            args.append(stage)
        if due == 'overdue':
            conditions.append("EXISTS (SELECT 1 FROM reminders r WHERE r.application_id=applications.id AND r.status='open' AND r.due_at < ?)")
            args.append(now())
        if search:
            conditions.append("LOWER(company || ' ' || role) LIKE ?")
            args.append('%' + search.lower() + '%')
        where = ' WHERE ' + ' AND '.join(conditions) if conditions else ''
        return self.store.rows('SELECT * FROM applications' + where +
                               ' ORDER BY COALESCE(last_activity_at,updated_at) DESC', args)

    def application_detail(self, app_id):
        application = self.application(app_id)
        application['events'] = self.store.rows('''SELECT * FROM application_events WHERE application_id=?
                                                   ORDER BY COALESCE(scheduled_at,occurred_at,created_at) DESC''', (app_id,))
        application['reminders'] = self.store.rows('''SELECT * FROM reminders WHERE application_id=?
                                                      ORDER BY status='open' DESC,due_at''', (app_id,))
        application['artifacts'] = self.store.rows('''SELECT * FROM artifacts WHERE application_id=?
                                                      ORDER BY created_at DESC''', (app_id,))
        return application

    def update_tracking(self, app_id, fields):
        application = self.application(app_id)
        status = fields.get('status', application['status'])
        stage = fields.get('current_stage', application['current_stage'])
        if status not in STATUSES:
            raise ValueError('Choose a supported application status.')
        if stage not in STAGES:
            raise ValueError('Choose a supported application stage.')
        editable = ('status', 'current_stage', 'applied_on', 'closed_on', 'source_name', 'employment_type',
                    'workplace_type', 'location', 'match_rating', 'compensation_text', 'next_action',
                    'next_action_due_at')
        values = {key: fields.get(key, application.get(key)) for key in editable}
        for key in ('source_name', 'employment_type', 'workplace_type', 'location', 'match_rating',
                    'compensation_text', 'next_action'):
            values[key] = values[key] or ''
        if values['applied_on']:
            try:
                date.fromisoformat(values['applied_on'])
            except ValueError as exc:
                raise ValueError('Application date must be YYYY-MM-DD.') from exc
        if status == 'submitted' and not values['applied_on']:
            values['applied_on'] = date.today().isoformat()
        if status in TERMINAL_STATUSES and not values['closed_on']:
            values['closed_on'] = date.today().isoformat()
        if status not in TERMINAL_STATUSES:
            values['closed_on'] = None
        values['next_action_due_at'] = self._timestamp(values['next_action_due_at'], 'Next action date')
        stamp = now()
        with self.store.connection() as db:
            db.execute('''UPDATE applications SET status=:status,current_stage=:current_stage,
                          applied_on=:applied_on,closed_on=:closed_on,source_name=:source_name,
                          employment_type=:employment_type,workplace_type=:workplace_type,location=:location,
                          match_rating=:match_rating,compensation_text=:compensation_text,next_action=:next_action,
                          next_action_due_at=:next_action_due_at,last_activity_at=:last_activity_at,
                          updated_at=:updated_at WHERE id=:id''',
                       {**values, 'last_activity_at': stamp, 'updated_at': stamp, 'id': app_id})
            if status != application['status'] or stage != application['current_stage']:
                db.execute('''INSERT INTO application_events(
                              id,application_id,event_type,stage,occurred_at,completed_at,outcome,notes,source,created_at)
                              VALUES (?,?,?,?,?,?,?,?,?,?)''',
                           (str(uuid4()), app_id, 'status_changed', stage, stamp, stamp, status,
                            f'{application["status"]} → {status}', 'manual', stamp))
            if status == 'submitted' and application['status'] != 'submitted':
                self._insert_default_reminder(db, app_id, 'follow_up', 'Follow up',
                                              datetime.now(UTC) + timedelta(days=7), stamp)
            if values['next_action'] and values['next_action_due_at']:
                db.execute('''INSERT INTO reminders(id,application_id,reminder_type,title,due_at,status,created_at,updated_at)
                              VALUES (?,?,?,?,?,'open',?,?)''',
                           (str(uuid4()), app_id, 'action', values['next_action'], values['next_action_due_at'], stamp, stamp))
            if status in TERMINAL_STATUSES:
                db.execute("UPDATE reminders SET status='dismissed',updated_at=? WHERE application_id=? AND status='open'",
                           (stamp, app_id))
        return self.application_detail(app_id)

    @staticmethod
    def _insert_default_reminder(db, app_id, kind, title, due, stamp, event_id=None):
        open_same = db.execute('''SELECT id FROM reminders WHERE application_id=? AND reminder_type=?
                                  AND status='open' LIMIT 1''', (app_id, kind)).fetchone()
        if not open_same:
            db.execute('''INSERT INTO reminders(id,application_id,event_id,reminder_type,title,due_at,status,created_at,updated_at)
                          VALUES (?,?,?,?,?,?,'open',?,?)''',
                       (str(uuid4()), app_id, event_id, kind, title, due.astimezone(UTC).isoformat(), stamp, stamp))

    def add_event(self, app_id, fields):
        application = self.application(app_id)
        stage = fields.get('stage') or application['current_stage']
        if stage not in STAGES:
            raise ValueError('Choose a supported application stage.')
        event_type = fields['event_type']
        occurred = self._timestamp(fields.get('occurred_at'), 'Event date')
        scheduled = self._timestamp(fields.get('scheduled_at'), 'Scheduled date')
        completed = self._timestamp(fields.get('completed_at'), 'Completion date')
        outcome = fields.get('outcome', '')
        if outcome and event_type == 'status_changed' and outcome not in STATUSES:
            raise ValueError('Choose a supported application status.')
        if event_type == 'interview_scheduled' and not scheduled:
            raise ValueError('A scheduled interview needs a date and time.')
        stamp = now()
        event_id = str(uuid4())
        next_status = application['status']
        if event_type == 'application_submitted':
            next_status = 'submitted'
        elif event_type == 'interview_scheduled':
            next_status = 'interview_scheduled'
        elif event_type == 'stage_completed':
            next_status = 'in_process'
        elif event_type == 'offer_received':
            next_status, stage = 'offer', 'offer'
        elif event_type == 'status_changed' and outcome:
            next_status = outcome
        activity = completed or occurred or scheduled or stamp
        with self.store.connection() as db:
            db.execute('''INSERT INTO application_events(
                          id,application_id,event_type,stage,occurred_at,scheduled_at,completed_at,outcome,
                          contact_name,notes,source,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                       (event_id, app_id, event_type, stage, occurred, scheduled, completed, outcome,
                        fields.get('contact_name', ''), fields.get('notes', ''), 'manual', stamp))
            applied_on = application['applied_on']
            if event_type == 'application_submitted' and not applied_on:
                applied_on = (occurred or stamp)[:10]
            closed_on = application['closed_on']
            if next_status in TERMINAL_STATUSES and not closed_on:
                closed_on = activity[:10]
            elif next_status not in TERMINAL_STATUSES:
                closed_on = None
            db.execute('''UPDATE applications SET status=?,current_stage=?,applied_on=?,closed_on=?,
                          last_activity_at=?,updated_at=? WHERE id=?''',
                       (next_status, stage, applied_on, closed_on, activity, stamp, app_id))
            if event_type == 'application_submitted':
                self._insert_default_reminder(db, app_id, 'follow_up', 'Follow up',
                                              datetime.fromisoformat(activity) + timedelta(days=7), stamp, event_id)
            elif event_type == 'stage_completed':
                self._insert_default_reminder(db, app_id, 'follow_up', 'Follow up after interview',
                                              datetime.fromisoformat(activity) + timedelta(days=3), stamp, event_id)
            elif event_type == 'interview_scheduled':
                due = datetime.fromisoformat(scheduled) - timedelta(days=1)
                self._insert_default_reminder(db, app_id, 'preparation', 'Prepare for interview', due, stamp, event_id)
            if next_status in TERMINAL_STATUSES:
                db.execute("UPDATE reminders SET status='dismissed',updated_at=? WHERE application_id=? AND status='open'",
                           (stamp, app_id))
        return self.application_detail(app_id)

    def add_reminder(self, app_id, fields):
        self.application(app_id)
        due = self._timestamp(fields['due_at'], 'Reminder date')
        stamp = now()
        reminder_id = str(uuid4())
        self.store.execute('''INSERT INTO reminders(
                           id,application_id,reminder_type,title,due_at,status,created_at,updated_at)
                           VALUES (?,?,?,?,?,'open',?,?)''',
                           (reminder_id, app_id, fields.get('reminder_type', 'follow_up'), fields['title'], due, stamp, stamp))
        return self.store.one('SELECT * FROM reminders WHERE id=?', (reminder_id,))

    def update_reminder(self, reminder_id, status, due_at=None):
        if status not in ('open', 'completed', 'dismissed'):
            raise ValueError('Choose a supported reminder status.')
        reminder = self.store.one('SELECT * FROM reminders WHERE id=?', (reminder_id,))
        if not reminder:
            raise KeyError('Reminder not found')
        due = self._timestamp(due_at, 'Reminder date') if due_at else reminder['due_at']
        stamp = now()
        completed = stamp if status == 'completed' else None
        self.store.execute('UPDATE reminders SET status=?,due_at=?,completed_at=?,updated_at=? WHERE id=?',
                           (status, due, completed, stamp, reminder_id))
        return self.store.one('SELECT * FROM reminders WHERE id=?', (reminder_id,))

    def import_tracker(self, commit=False):
        tracker = self.contained(self.root / self.manifest['paths']['tracker'])
        importer = TrackerImporter(self.store, self.root, tracker)
        return importer.run() if commit else importer.preview()

    def statistics(self, date_from=None, date_to=None):
        conditions, args = ['applied_on IS NOT NULL'], []
        if date_from:
            conditions.append('applied_on>=?')
            args.append(date_from)
        if date_to:
            conditions.append('applied_on<=?')
            args.append(date_to)
        submitted = self.store.rows('SELECT * FROM applications WHERE ' + ' AND '.join(conditions), args)
        ids = {row['id'] for row in submitted}
        events = self.store.rows('SELECT * FROM application_events')
        by_app = {}
        for event in events:
            by_app.setdefault(event['application_id'], []).append(event)
        interview_stages = {'recruiter_screen', 'assessment', 'technical_screen', 'hiring_manager', 'case_study', 'culture_fit'}
        interviewed = {app_id for app_id in ids if any(e['stage'] in interview_stages and
                       e['event_type'] in ('stage_completed', 'interview_scheduled') for e in by_app.get(app_id, []))}
        responded = {app_id for app_id in ids if any(e['event_type'] not in ('application_submitted', 'note', 'follow_up')
                     for e in by_app.get(app_id, []))}
        offers = {row['id'] for row in submitted if row['status'] in ('offer', 'accepted') or
                  any(e['event_type'] == 'offer_received' for e in by_app.get(row['id'], []))}
        accepted = {row['id'] for row in submitted if row['status'] == 'accepted'}
        rejected = {row['id'] for row in submitted if row['status'] == 'rejected'}
        ghosted = {row['id'] for row in submitted if row['status'] == 'ghosted'}
        first_response_days, process_days = [], []
        for row in submitted:
            start = date.fromisoformat(row['applied_on'])
            response_dates = []
            for event in by_app.get(row['id'], []):
                if event['event_type'] not in ('application_submitted', 'note', 'follow_up'):
                    value = event['occurred_at'] or event['scheduled_at'] or event['created_at']
                    if value:
                        response_dates.append(datetime.fromisoformat(value).date())
            if response_dates:
                first_response_days.append(max(0, (min(response_dates) - start).days))
            if row['closed_on']:
                process_days.append(max(0, (date.fromisoformat(row['closed_on']) - start).days))
        months = {}
        for row in submitted:
            month = row['applied_on'][:7]
            entry = months.setdefault(month, {'month': month, 'submitted': 0, 'interviews': 0, 'offers': 0, 'accepted': 0})
            entry['submitted'] += 1
            entry['interviews'] += row['id'] in interviewed
            entry['offers'] += row['id'] in offers
            entry['accepted'] += row['id'] in accepted
        total = len(submitted)
        def rate(count, denominator=total):
            return round(count / denominator, 4) if denominator else None
        return {'submitted': total, 'responses': len(responded), 'interviews': len(interviewed),
                'offers': len(offers), 'accepted': len(accepted), 'rejected': len(rejected), 'ghosted': len(ghosted),
                'response_rate': rate(len(responded)), 'interview_rate': rate(len(interviewed)),
                'offer_rate': rate(len(offers)), 'acceptance_rate': rate(len(accepted), len(offers)),
                'median_days_to_response': round(median(first_response_days), 1) if first_response_days else None,
                'median_process_days': round(median(process_days), 1) if process_days else None,
                'monthly': sorted(months.values(), key=lambda item: item['month'])}

    def dashboard(self):
        applications = self.applications()
        following = self.store.rows('''SELECT * FROM applications WHERE status='in_process'
                                      ORDER BY COALESCE(last_activity_at, updated_at) DESC LIMIT 100''')
        upcoming = self.store.rows('''SELECT a.*,
                                      (SELECT MIN(e.scheduled_at) FROM application_events e
                                       WHERE e.application_id=a.id AND e.scheduled_at IS NOT NULL
                                         AND e.completed_at IS NULL) AS scheduled_at
                                      FROM applications a WHERE a.status='interview_scheduled'
                                      ORDER BY scheduled_at IS NULL, scheduled_at, a.updated_at DESC LIMIT 50''')
        action_required = self.store.rows('''SELECT * FROM applications WHERE status='action_required'
                                            ORDER BY COALESCE(last_activity_at, updated_at) DESC LIMIT 100''')
        open_statuses = {'submitted', 'in_process', 'interview_scheduled', 'offer', 'action_required'}
        return {'counts': {'total': len(applications),
                           'open': sum(row['status'] in open_statuses for row in applications),
                           'following': len(following), 'upcoming': len(upcoming),
                           'action_required': len(action_required)},
                'following': following, 'upcoming': upcoming, 'action_required': action_required,
                'statistics': self.statistics()}

    def bootstrap(self):
        artifacts = self.store.rows('''SELECT a.*,p.company,p.role FROM artifacts a JOIN applications p
                                       ON p.id=a.application_id ORDER BY a.created_at DESC''')
        for artifact in artifacts:
            artifact['provenance'] = json.loads(artifact['provenance'])
        tasks = [self.store.decode_task(t) for t in self.store.rows('SELECT * FROM tasks ORDER BY created_at DESC LIMIT 100')]
        return {'applications': self.applications(),
                'artifacts': artifacts, 'tasks': tasks, 'searches': [t for t in tasks if t['kind'] == 'search'],
                'families': self.families(), 'settings': self.settings(), 'dashboard': self.dashboard()}
