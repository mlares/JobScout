from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3


SCHEMA_VERSION = 2


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._backup_before_upgrade()
        with self.connection() as db:
            self._migrate(db)

    def _backup_before_upgrade(self):
        if not self.path.is_file() or self.path.stat().st_size == 0:
            return
        with sqlite3.connect(self.path) as source:
            version = source.execute('PRAGMA user_version').fetchone()[0]
            if version >= SCHEMA_VERSION:
                return
            backup = self.path.with_name(f'{self.path.name}.pre-v{SCHEMA_VERSION}.bak')
            if not backup.exists():
                with sqlite3.connect(backup) as destination:
                    source.backup(destination)

    @staticmethod
    def _migrate(db):
        version = db.execute('PRAGMA user_version').fetchone()[0]
        if version == 0:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS applications (
                    id TEXT PRIMARY KEY, company TEXT NOT NULL, role TEXT NOT NULL,
                    job_description TEXT NOT NULL, source_url TEXT NOT NULL DEFAULT '',
                    folder TEXT NOT NULL, imported INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL, kind TEXT NOT NULL,
                    application_id TEXT REFERENCES applications(id), status TEXT NOT NULL,
                    payload TEXT NOT NULL, result TEXT, message TEXT NOT NULL DEFAULT '',
                    error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_tasks_application_created
                    ON tasks(application_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_tasks_status_created ON tasks(status, created_at);
                CREATE TABLE IF NOT EXISTS artifacts (
                    id TEXT PRIMARY KEY, application_id TEXT NOT NULL REFERENCES applications(id),
                    kind TEXT NOT NULL, state TEXT NOT NULL, path TEXT UNIQUE NOT NULL,
                    filename TEXT NOT NULL, sha256 TEXT NOT NULL, provenance TEXT NOT NULL,
                    saved_from TEXT UNIQUE REFERENCES artifacts(id), created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_artifacts_application_created
                    ON artifacts(application_id, created_at DESC);
                PRAGMA user_version=1;
            ''')
            version = 1

        if version == 1:
            existing = {row['name'] for row in db.execute('PRAGMA table_info(applications)')}
            additions = {
                'status': "TEXT NOT NULL DEFAULT 'draft'",
                'current_stage': "TEXT NOT NULL DEFAULT 'application'",
                'applied_on': 'TEXT',
                'closed_on': 'TEXT',
                'source_name': "TEXT NOT NULL DEFAULT ''",
                'employment_type': "TEXT NOT NULL DEFAULT ''",
                'workplace_type': "TEXT NOT NULL DEFAULT ''",
                'location': "TEXT NOT NULL DEFAULT ''",
                'match_rating': "TEXT NOT NULL DEFAULT ''",
                'compensation_text': "TEXT NOT NULL DEFAULT ''",
                'next_action': "TEXT NOT NULL DEFAULT ''",
                'next_action_due_at': 'TEXT',
                'last_activity_at': 'TEXT',
                'import_source': "TEXT NOT NULL DEFAULT ''",
                'import_key': 'TEXT',
                'legacy_data': "TEXT NOT NULL DEFAULT '{}'",
            }
            for name, definition in additions.items():
                if name not in existing:
                    db.execute(f'ALTER TABLE applications ADD COLUMN {name} {definition}')
            db.executescript('''
                CREATE UNIQUE INDEX IF NOT EXISTS idx_applications_import_key
                    ON applications(import_key) WHERE import_key IS NOT NULL;
                CREATE INDEX IF NOT EXISTS idx_applications_status_applied
                    ON applications(status, applied_on DESC);
                CREATE INDEX IF NOT EXISTS idx_applications_next_action
                    ON applications(next_action_due_at) WHERE next_action_due_at IS NOT NULL;

                CREATE TABLE IF NOT EXISTS application_events (
                    id TEXT PRIMARY KEY,
                    application_id TEXT NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
                    event_type TEXT NOT NULL,
                    stage TEXT NOT NULL DEFAULT 'application',
                    occurred_at TEXT,
                    scheduled_at TEXT,
                    completed_at TEXT,
                    outcome TEXT NOT NULL DEFAULT '',
                    contact_name TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT 'manual',
                    source_key TEXT UNIQUE,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_events_application_time
                    ON application_events(application_id, occurred_at DESC, scheduled_at DESC);
                CREATE INDEX IF NOT EXISTS idx_events_scheduled
                    ON application_events(scheduled_at) WHERE scheduled_at IS NOT NULL;

                CREATE TABLE IF NOT EXISTS reminders (
                    id TEXT PRIMARY KEY,
                    application_id TEXT NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
                    event_id TEXT REFERENCES application_events(id) ON DELETE SET NULL,
                    reminder_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    due_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    completed_at TEXT,
                    source_key TEXT UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_reminders_status_due
                    ON reminders(status, due_at);

                CREATE TABLE IF NOT EXISTS import_batches (
                    id TEXT PRIMARY KEY,
                    source_path TEXT NOT NULL,
                    source_sha256 TEXT NOT NULL UNIQUE,
                    source_sheet TEXT NOT NULL,
                    status TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    completed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS import_rows (
                    id TEXT PRIMARY KEY,
                    batch_id TEXT NOT NULL REFERENCES import_batches(id) ON DELETE CASCADE,
                    source_sheet TEXT NOT NULL,
                    source_row INTEGER NOT NULL,
                    fingerprint TEXT NOT NULL,
                    application_id TEXT REFERENCES applications(id) ON DELETE SET NULL,
                    result TEXT NOT NULL,
                    raw_data TEXT NOT NULL,
                    message TEXT NOT NULL DEFAULT '',
                    UNIQUE(batch_id, source_sheet, source_row)
                );
                CREATE INDEX IF NOT EXISTS idx_import_rows_application
                    ON import_rows(application_id);
                PRAGMA user_version=2;
            ''')
            version = 2

        if version != SCHEMA_VERSION:
            raise RuntimeError(f'Unsupported career database schema version: {version}')

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def rows(self, sql, args=()):
        with self.connection() as db:
            return [dict(row) for row in db.execute(sql, args).fetchall()]

    def one(self, sql, args=()):
        rows = self.rows(sql, args)
        return rows[0] if rows else None

    def execute(self, sql, args=()):
        with self.connection() as db:
            db.execute(sql, args)

    def task(self, task_id):
        row = self.one('SELECT * FROM tasks WHERE id=?', (task_id,))
        return self.decode_task(row) if row else None

    @staticmethod
    def decode_task(row):
        row = dict(row)
        payload = json.loads(row.pop('payload'))
        row['options'] = payload.get('options', {})
        row['result'] = json.loads(row['result']) if row['result'] else None
        return row
