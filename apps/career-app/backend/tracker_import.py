from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import urlsplit, urlunsplit
from uuid import NAMESPACE_URL, uuid4, uuid5
import xml.etree.ElementTree as ET
from zipfile import ZipFile

from .store import now


MAIN_NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PACKAGE_REL_NS = 'http://schemas.openxmlformats.org/package/2006/relationships'
NS = {'m': MAIN_NS, 'r': REL_NS}

STATUSES = {
    'draft', 'action_required', 'submitted', 'in_process', 'interview_scheduled',
    'offer', 'accepted', 'rejected', 'withdrawn', 'ghosted', 'archived',
}
STAGES = {
    'application', 'recruiter_screen', 'assessment', 'technical_screen',
    'hiring_manager', 'case_study', 'culture_fit', 'offer',
}
TERMINAL_STATUSES = {'accepted', 'rejected', 'withdrawn', 'ghosted', 'archived'}
STATUS_MAP = {
    'presented': 'submitted',
    'under consideration': 'in_process',
    'pending interview': 'interview_scheduled',
    'finish submission': 'action_required',
    'prepare': 'draft',
    'rejected': 'rejected',
    'ghosted': 'ghosted',
    'stalled': 'ghosted',
    'active freelance': 'accepted',
    'active part time': 'accepted',
    'job platform': 'archived',
}
STAGE_COLUMNS = [
    ('HR init', 'recruiter_screen'),
    ('virtual asessment', 'assessment'),
    ('tech screening', 'technical_screen'),
    ('leader screening', 'hiring_manager'),
    ('business case', 'case_study'),
    ('culture fit', 'culture_fit'),
]


def _text(node):
    return ''.join(part.text or '' for part in node.iter(f'{{{MAIN_NS}}}t'))


def _column_index(reference):
    letters = re.match(r'[A-Z]+', reference or '')
    value = 0
    for char in letters.group(0) if letters else '':
        value = value * 26 + ord(char) - 64
    return value - 1


def read_sheet(path: Path, sheet_name='apply'):
    """Read values from an XLSX worksheet using only the Python standard library."""
    with ZipFile(path) as book:
        shared = []
        if 'xl/sharedStrings.xml' in book.namelist():
            root = ET.fromstring(book.read('xl/sharedStrings.xml'))
            shared = [_text(item) for item in root.findall('m:si', NS)]

        workbook = ET.fromstring(book.read('xl/workbook.xml'))
        sheet = next((s for s in workbook.findall('m:sheets/m:sheet', NS)
                      if s.attrib.get('name') == sheet_name), None)
        if sheet is None:
            raise ValueError(f'Worksheet {sheet_name!r} was not found in the tracker.')
        relation_id = sheet.attrib[f'{{{REL_NS}}}id']
        relationships = ET.fromstring(book.read('xl/_rels/workbook.xml.rels'))
        target = next((r.attrib['Target'] for r in relationships.findall(f'{{{PACKAGE_REL_NS}}}Relationship')
                       if r.attrib.get('Id') == relation_id), None)
        if not target:
            raise ValueError('The tracker worksheet relationship is missing.')
        sheet_path = target.lstrip('/') if target.startswith('/xl/') else 'xl/' + target.lstrip('/')
        if target.startswith('/xl/'):
            sheet_path = target.lstrip('/')

        root = ET.fromstring(book.read(sheet_path))
        rows = []
        for row in root.findall('m:sheetData/m:row', NS):
            values = {}
            for cell in row.findall('m:c', NS):
                index = _column_index(cell.attrib.get('r'))
                kind = cell.attrib.get('t')
                value_node = cell.find('m:v', NS)
                if kind == 'inlineStr':
                    inline = cell.find('m:is', NS)
                    value = _text(inline) if inline is not None else ''
                elif value_node is None:
                    value = None
                else:
                    raw = value_node.text or ''
                    if kind == 's':
                        value = shared[int(raw)]
                    elif kind == 'b':
                        value = raw == '1'
                    elif kind in ('str', 'e'):
                        value = raw
                    else:
                        try:
                            numeric = float(raw)
                            value = int(numeric) if numeric.is_integer() else numeric
                        except ValueError:
                            value = raw
                values[index] = value
            width = max(values, default=-1) + 1
            rows.append((int(row.attrib.get('r', len(rows) + 1)), [values.get(i) for i in range(width)]))
    return rows


def normalize_header(value):
    return re.sub(r'\s+', ' ', str(value or '').strip()).lower()


def normalize(value):
    value = unicodedata.normalize('NFKD', str(value or '')).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]+', ' ', value.lower()).strip()


def clean(value):
    return str(value or '').strip()


def canonical_url(value):
    value = clean(value)
    if not value.startswith(('http://', 'https://')):
        return ''
    split = urlsplit(value)
    host = split.netloc.lower().removeprefix('www.')
    path = split.path.rstrip('/')
    return urlunsplit((split.scheme.lower(), host, path, '', ''))


def excel_date(value):
    if isinstance(value, (int, float)) and 1 <= value <= 80000:
        return (date(1899, 12, 30) + timedelta(days=int(value))).isoformat()
    match = re.match(r'\s*(20\d{2})-(\d{2})-(\d{2})', clean(value))
    if match:
        try:
            return date(*(int(part) for part in match.groups())).isoformat()
        except ValueError:
            return None
    return None


def at_noon(day):
    return f'{day}T15:00:00+00:00' if day else None


def row_fingerprint(row):
    payload = json.dumps(row, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


class TrackerImporter:
    def __init__(self, store, root: Path, tracker: Path):
        self.store = store
        self.root = Path(root)
        self.tracker = Path(tracker)

    def source_rows(self):
        if not self.tracker.is_file():
            raise KeyError('The JobSearch tracker was not found.')
        rows = read_sheet(self.tracker, 'apply')
        if not rows:
            return []
        headers = [normalize_header(value) for value in rows[0][1]]
        results = []
        for source_row, values in rows[1:]:
            record = {headers[index]: values[index] if index < len(values) else None
                      for index in range(len(headers)) if headers[index]}
            if not clean(record.get('company')):
                continue
            results.append((source_row, record))
        return results

    @staticmethod
    def application_basis(record):
        url = canonical_url(record.get('post'))
        if url:
            return 'url|' + url
        company = normalize(record.get('company'))
        role = normalize(record.get('role'))
        applied = excel_date(record.get('application date')) or ''
        return f'fields|{company}|{role}|{applied}|{normalize(record.get("found"))}'

    @classmethod
    def application_key(cls, record, source_row, duplicate_bases):
        basis = cls.application_basis(record)
        if duplicate_bases[basis] > 1:
            basis += f'|row:{source_row}'
        return 'jobsearch:' + hashlib.sha256(basis.encode()).hexdigest()

    @staticmethod
    def mapped(record):
        raw_status = normalize(record.get('status'))
        applied = clean(record.get('applied')).lower() in ('true', '1', 'yes', 'sent direct message')
        status = STATUS_MAP.get(raw_status, 'submitted' if applied else 'draft')
        applied_on = excel_date(record.get('application date')) if applied else None
        stage = 'application'
        stage_events = []
        today = date.today().isoformat()
        for column, stage_name in STAGE_COLUMNS:
            value = record.get(column.lower())
            if value in (None, ''):
                continue
            stage = stage_name
            event_date = excel_date(value)
            future = bool(event_date and event_date > today and status == 'interview_scheduled')
            stage_events.append({
                'event_type': 'interview_scheduled' if future else 'stage_completed',
                'stage': stage_name,
                'occurred_at': None if future else at_noon(event_date),
                'scheduled_at': at_noon(event_date) if future else None,
                'completed_at': None if future else at_noon(event_date),
                'notes': clean(value) if not event_date or '\n' in clean(value) else '',
            })
        if status == 'interview_scheduled' and stage == 'application':
            stage = 'recruiter_screen'
        if status == 'accepted':
            stage = 'offer'
        last_news = excel_date(record.get('last news'))
        activity_dates = [value for value in [applied_on, last_news] +
                          [excel_date(record.get(column.lower())) for column, _ in STAGE_COLUMNS] if value]
        last_activity = at_noon(max(activity_dates)) if activity_dates else None
        closed_on = last_news if status in TERMINAL_STATUSES else None
        return {
            'company': clean(record.get('company')),
            'role': clean(record.get('role')),
            'job_description': clean(record.get('about the job'))[:80000],
            'source_url': clean(record.get('post')) if canonical_url(record.get('post')) else '',
            'status': status,
            'current_stage': stage,
            'applied_on': applied_on,
            'closed_on': closed_on,
            'source_name': clean(record.get('found')),
            'employment_type': clean(record.get('type')),
            'workplace_type': clean(record.get('remote?')),
            'location': clean(record.get('location')),
            'match_rating': clean(record.get('match')),
            'compensation_text': clean(record.get('pretended')),
            'next_action': clean(record.get('next steps')),
            'last_activity_at': last_activity,
            'stage_events': stage_events,
            'comments': clean(record.get('comments')),
            'feedback': clean(record.get('feedback')),
            'tracking_url': clean(record.get('track')),
            'follow_up_url': clean(record.get('follow up')),
            'raw_status': clean(record.get('status')),
        }

    @staticmethod
    def _find_match(db, mapped, import_key, company_count, allowed_ids=None):
        def allowed(row):
            return allowed_ids is None or row['id'] in allowed_ids
        row = db.execute('SELECT * FROM applications WHERE import_key=?', (import_key,)).fetchone()
        if row and allowed(row):
            return dict(row), 'existing import key'
        url = canonical_url(mapped['source_url'])
        if url:
            candidates = [dict(row) for row in db.execute("SELECT * FROM applications WHERE source_url != ''")
                          if allowed(row) and canonical_url(row['source_url']) == url]
            if len(candidates) == 1:
                return candidates[0], 'posting URL'
        company, role = normalize(mapped['company']), normalize(mapped['role'])
        candidates = [dict(row) for row in db.execute('SELECT * FROM applications')
                      if allowed(row) and normalize(row['company']) == company and normalize(row['role']) == role and role]
        if len(candidates) == 1:
            return candidates[0], 'company and role'
        if company_count[company] == 1:
            candidates = [dict(row) for row in db.execute('SELECT * FROM applications')
                          if allowed(row) and normalize(row['company']) == company and not normalize(row['role'])]
            if len(candidates) == 1:
                return candidates[0], 'unique company with missing role'
        return None, ''

    def preview(self):
        source = self.source_rows()
        company_count = Counter(normalize(record.get('company')) for _, record in source)
        duplicates = Counter(self.application_basis(record) for _, record in source)
        summary = Counter()
        rows = []
        with self.store.connection() as db:
            for source_row, record in source:
                mapped = self.mapped(record)
                key = self.application_key(record, source_row, duplicates)
                match, reason = self._find_match(db, mapped, key, company_count)
                result = 'link' if match else 'create'
                summary[result] += 1
                if not mapped['role']:
                    summary['missing_role'] += 1
                if not mapped['source_url']:
                    summary['missing_url'] += 1
                rows.append({'source_row': source_row, 'company': mapped['company'], 'role': mapped['role'],
                             'status': mapped['status'], 'result': result, 'match_reason': reason,
                             'application_id': match['id'] if match else None})
        return {'source': self.tracker.name, 'sheet': 'apply', 'total': len(source),
                'summary': dict(summary), 'rows': rows}

    def run(self):
        source_hash = hashlib.sha256(self.tracker.read_bytes()).hexdigest()
        existing = self.store.one('SELECT * FROM import_batches WHERE source_sha256=?', (source_hash,))
        if existing:
            result = json.loads(existing['summary'])
            result['already_imported'] = True
            result['batch_id'] = existing['id']
            return result

        source = self.source_rows()
        company_count = Counter(normalize(record.get('company')) for _, record in source)
        duplicates = Counter(self.application_basis(record) for _, record in source)
        batch_id = str(uuid4())
        stamp = now()
        counts = Counter()
        review = []
        plans = {}
        with self.store.connection() as planning_db:
            for source_row, record in source:
                mapped = self.mapped(record)
                import_key = self.application_key(record, source_row, duplicates)
                match, reason = self._find_match(planning_db, mapped, import_key, company_count)
                plans[source_row] = (match['id'] if match else None, reason)
        with self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT INTO import_batches(id,source_path,source_sha256,source_sheet,status,created_at) VALUES (?,?,?,?,?,?)',
                       (batch_id, str(self.tracker.relative_to(self.root)), source_hash, 'apply', 'running', stamp))
            for source_row, record in source:
                mapped = self.mapped(record)
                fingerprint = row_fingerprint(record)
                import_key = self.application_key(record, source_row, duplicates)
                planned_id, reason = plans[source_row]
                row = db.execute('SELECT * FROM applications WHERE id=?', (planned_id,)).fetchone() if planned_id else None
                application = dict(row) if row else None
                if application:
                    application_id = application['id']
                    result = 'linked'
                    updates = {key: mapped[key] for key in (
                        'company', 'role', 'job_description', 'source_url', 'status', 'current_stage',
                        'applied_on', 'closed_on', 'source_name', 'employment_type', 'workplace_type',
                        'location', 'match_rating', 'compensation_text', 'next_action', 'last_activity_at')}
                    db.execute('''UPDATE applications SET company=:company,role=:role,job_description=:job_description,
                                  source_url=:source_url,status=:status,current_stage=:current_stage,
                                  applied_on=:applied_on,closed_on=:closed_on,source_name=:source_name,
                                  employment_type=:employment_type,workplace_type=:workplace_type,location=:location,
                                  match_rating=:match_rating,compensation_text=:compensation_text,
                                  next_action=:next_action,last_activity_at=:last_activity_at,
                                  import_source='JobSearch.xlsx',import_key=:import_key,legacy_data=:legacy_data,
                                  updated_at=:updated_at WHERE id=:id''',
                               {**application, **updates, 'import_key': import_key, 'updated_at': stamp,
                                'legacy_data': json.dumps({'source_row': source_row, 'raw_status': mapped['raw_status'],
                                                           'tracking_url': mapped['tracking_url'],
                                                           'follow_up_url': mapped['follow_up_url']}, ensure_ascii=False),
                                'id': application_id})
                else:
                    application_id = str(uuid5(NAMESPACE_URL, import_key))
                    year = (mapped['applied_on'] or date.today().isoformat())[:4]
                    folder_name = re.sub(r'[^a-z0-9]+', '-', (mapped['company'] + '-' + mapped['role']).lower()).strip('-')[:70] or 'application'
                    folder = f'applications/{year}/{folder_name}-{application_id[:8]}'
                    db.execute('''INSERT INTO applications(
                                  id,company,role,job_description,source_url,folder,imported,created_at,updated_at,
                                  status,current_stage,applied_on,closed_on,source_name,employment_type,workplace_type,
                                  location,match_rating,compensation_text,next_action,last_activity_at,import_source,
                                  import_key,legacy_data) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                               (application_id, mapped['company'], mapped['role'], mapped['job_description'],
                                mapped['source_url'], folder, 1, stamp, stamp, mapped['status'], mapped['current_stage'],
                                mapped['applied_on'], mapped['closed_on'], mapped['source_name'], mapped['employment_type'],
                                mapped['workplace_type'], mapped['location'], mapped['match_rating'], mapped['compensation_text'],
                                mapped['next_action'], mapped['last_activity_at'], 'JobSearch.xlsx', import_key,
                                json.dumps({'source_row': source_row, 'raw_status': mapped['raw_status'],
                                            'tracking_url': mapped['tracking_url'], 'follow_up_url': mapped['follow_up_url']},
                                           ensure_ascii=False)))
                    result = 'created'
                    reason = ''

                self._events_and_reminder(db, application_id, import_key, mapped, stamp)
                message = reason
                if not mapped['role'] or not mapped['source_url']:
                    missing = ', '.join(label for condition, label in (
                        (not mapped['role'], 'role'), (not mapped['source_url'], 'posting URL')) if condition)
                    review.append({'source_row': source_row, 'company': mapped['company'], 'missing': missing})
                    message = (message + '; ' if message else '') + 'Missing ' + missing
                db.execute('''INSERT INTO import_rows(id,batch_id,source_sheet,source_row,fingerprint,
                              application_id,result,raw_data,message) VALUES (?,?,?,?,?,?,?,?,?)''',
                           (str(uuid4()), batch_id, 'apply', source_row, fingerprint, application_id, result,
                            json.dumps(record, ensure_ascii=False, default=str), message))
                counts[result] += 1

            summary = {'batch_id': batch_id, 'source': self.tracker.name, 'sheet': 'apply', 'total': len(source),
                       'created': counts['created'], 'linked': counts['linked'], 'review_count': len(review),
                       'review': review[:100], 'already_imported': False}
            db.execute('UPDATE import_batches SET status=?,summary=?,completed_at=? WHERE id=?',
                       ('completed', json.dumps(summary, ensure_ascii=False), now(), batch_id))
        return summary

    @staticmethod
    def _events_and_reminder(db, application_id, import_key, mapped, stamp):
        # A changed workbook is the source of truth for imported events and reminders.
        # Keep user-created activity intact by touching only source-keyed records.
        source_prefix = f'{import_key}:%'
        db.execute('DELETE FROM reminders WHERE source_key LIKE ?', (source_prefix,))
        db.execute('DELETE FROM application_events WHERE source_key LIKE ?', (source_prefix,))

        def event(suffix, event_type, stage='application', occurred_at=None, scheduled_at=None,
                  completed_at=None, outcome='', notes=''):
            db.execute('''INSERT INTO application_events(
                          id,application_id,event_type,stage,occurred_at,scheduled_at,completed_at,outcome,
                          notes,source,source_key,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                       (str(uuid4()), application_id, event_type, stage, occurred_at, scheduled_at, completed_at,
                        outcome, notes, 'JobSearch.xlsx', f'{import_key}:{suffix}', stamp))

        if mapped['applied_on']:
            event('submitted', 'application_submitted', occurred_at=at_noon(mapped['applied_on']),
                  completed_at=at_noon(mapped['applied_on']))
        for index, item in enumerate(mapped['stage_events']):
            event(f'stage:{index}:{item["stage"]}', **item)
        if mapped['status'] in TERMINAL_STATUSES:
            event('outcome', 'status_changed', stage=mapped['current_stage'],
                  occurred_at=at_noon(mapped['closed_on']) or mapped['last_activity_at'],
                  completed_at=at_noon(mapped['closed_on']) or mapped['last_activity_at'],
                  outcome=mapped['status'], notes=mapped['feedback'])
        note_parts = [part for part in (mapped['comments'], mapped['feedback']) if part]
        if note_parts:
            event('notes', 'note', stage=mapped['current_stage'], occurred_at=mapped['last_activity_at'],
                  notes='\n\n'.join(note_parts))

        if mapped['status'] in {'submitted', 'in_process', 'action_required'}:
            base = mapped['last_activity_at'][:10] if mapped['last_activity_at'] else mapped['applied_on']
            if base:
                days = 3 if mapped['status'] == 'in_process' else 7
                due = date.fromisoformat(base) + timedelta(days=days)
                title = mapped['next_action'] or ('Complete application' if mapped['status'] == 'action_required' else 'Follow up')
                db.execute('''INSERT INTO reminders(
                              id,application_id,reminder_type,title,due_at,status,source_key,created_at,updated_at)
                              VALUES (?,?,?,?,?,'open',?,?,?)''',
                           (str(uuid4()), application_id,
                            'action' if mapped['status'] == 'action_required' else 'follow_up', title,
                            at_noon(due.isoformat()), f'{import_key}:reminder', stamp, stamp))
