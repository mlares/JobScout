from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .service import CareerService


class ApplicationInput(BaseModel):
    company: str = Field(default='', max_length=160)
    role: str = Field(default='', max_length=200)
    job_description: str = Field(min_length=1, max_length=80000)
    source_url: str = Field(default='', max_length=2048)

    @field_validator('source_url')
    @classmethod
    def url(cls, value):
        if value and urlparse(value).scheme not in ('http', 'https'):
            raise ValueError('Use an http or https posting URL.')
        return value

    @field_validator('job_description')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('Paste a job description.')
        return value


class MatchInput(BaseModel):
    job_description: str = Field(min_length=1, max_length=80000)
    method: Literal['jev', 'keyword'] = 'jev'


class Options(BaseModel):
    family: str = Field(default='', max_length=80)
    rebuild: bool = False
    letter: str = Field(default='', max_length=25000)
    role: str = Field(default='senior data scientist', min_length=1, max_length=160)
    location: str = Field(default='Argentina', max_length=160)
    remote: bool = True
    limit: Literal[10, 20, 25] = 10
    ai_rank: bool = False


class TaskInput(BaseModel):
    kind: Literal['copy', 'cv', 'letter', 'letter-pdf', 'search']
    application_id: UUID | None = None
    request_id: UUID
    options: Options = Field(default_factory=Options)


class RetryInput(BaseModel):
    request_id: UUID


class TrackingInput(BaseModel):
    status: Literal['draft', 'action_required', 'submitted', 'in_process', 'interview_scheduled',
                    'offer', 'accepted', 'rejected', 'withdrawn', 'ghosted', 'archived'] | None = None
    current_stage: Literal['application', 'recruiter_screen', 'assessment', 'technical_screen',
                           'hiring_manager', 'case_study', 'culture_fit', 'offer'] | None = None
    applied_on: str | None = None
    closed_on: str | None = None
    source_name: str | None = Field(default=None, max_length=160)
    employment_type: str | None = Field(default=None, max_length=80)
    workplace_type: str | None = Field(default=None, max_length=80)
    location: str | None = Field(default=None, max_length=200)
    match_rating: str | None = Field(default=None, max_length=40)
    compensation_text: str | None = Field(default=None, max_length=200)
    next_action: str | None = Field(default=None, max_length=500)
    next_action_due_at: str | None = None


class EventInput(BaseModel):
    event_type: Literal['application_submitted', 'interview_scheduled', 'stage_completed',
                        'offer_received', 'status_changed', 'follow_up', 'note']
    stage: Literal['application', 'recruiter_screen', 'assessment', 'technical_screen',
                   'hiring_manager', 'case_study', 'culture_fit', 'offer'] | None = None
    occurred_at: str | None = None
    scheduled_at: str | None = None
    completed_at: str | None = None
    outcome: str = Field(default='', max_length=80)
    contact_name: str = Field(default='', max_length=200)
    notes: str = Field(default='', max_length=10000)


class ReminderInput(BaseModel):
    reminder_type: Literal['follow_up', 'preparation', 'action'] = 'follow_up'
    title: str = Field(min_length=1, max_length=500)
    due_at: str


class ReminderUpdate(BaseModel):
    status: Literal['open', 'completed', 'dismissed']
    due_at: str | None = None


class ImportInput(BaseModel):
    commit: bool = False


def create_app(service=None, start_worker=True):
    @asynccontextmanager
    async def lifespan(app):
        app.state.service = service or CareerService()
        if start_worker:
            app.state.service.start()
        try:
            yield
        finally:
            if start_worker:
                app.state.service.close()

    app = FastAPI(title='Career Workspace', docs_url=None, redoc_url=None, lifespan=lifespan)
    if service is not None:
        app.state.service = service
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', '[::1]', 'testserver'])

    @app.middleware('http')
    async def local_requests(request: Request, call_next):
        if request.url.path.startswith('/api') and request.method not in ('GET', 'HEAD', 'OPTIONS'):
            origin = request.headers.get('origin')
            if request.headers.get('x-career-request') != '1':
                return JSONResponse({'detail': 'Use the Career Workspace interface for this action.'}, status_code=403)
            if origin and (urlparse(origin).hostname not in ('127.0.0.1', 'localhost', '::1') or urlparse(origin).scheme != 'http'):
                return JSONResponse({'detail': 'Only the local app can perform this action.'}, status_code=403)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        if request.url.path.startswith('/api'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.exception_handler(KeyError)
    async def missing(_request, exc):
        return JSONResponse({'detail': str(exc).strip("'")}, status_code=404)

    @app.exception_handler(ValueError)
    async def invalid(_request, exc):
        return JSONResponse({'detail': str(exc)}, status_code=400)

    def svc(request):
        return request.app.state.service

    @app.get('/api/bootstrap')
    async def bootstrap(request: Request):
        return svc(request).bootstrap()

    @app.get('/api/dashboard')
    async def dashboard(request: Request):
        return svc(request).dashboard()

    @app.get('/api/statistics')
    async def statistics(request: Request, date_from: str | None = None, date_to: str | None = None):
        return svc(request).statistics(date_from, date_to)

    @app.get('/api/applications')
    async def applications(request: Request, status: str | None = None, stage: str | None = None,
                     due: str | None = None, search: str | None = None):
        return svc(request).applications(status, stage, due, search)

    @app.get('/api/applications/{application_id}')
    async def application(application_id: UUID, request: Request):
        return svc(request).application_detail(str(application_id))

    @app.post('/api/match')
    async def match(body: MatchInput, request: Request):
        return svc(request).families(body.job_description, method=body.method)

    @app.post('/api/applications')
    async def create_application(body: ApplicationInput, request: Request):
        return svc(request).save_application(body.model_dump())

    @app.put('/api/applications/{application_id}')
    async def update_application(application_id: UUID, body: ApplicationInput, request: Request):
        return svc(request).save_application(body.model_dump(), str(application_id))

    @app.patch('/api/applications/{application_id}/tracking')
    async def update_tracking(application_id: UUID, body: TrackingInput, request: Request):
        return svc(request).update_tracking(str(application_id), body.model_dump(exclude_unset=True))

    @app.post('/api/applications/{application_id}/events')
    async def add_event(application_id: UUID, body: EventInput, request: Request):
        return svc(request).add_event(str(application_id), body.model_dump())

    @app.post('/api/applications/{application_id}/reminders')
    async def add_reminder(application_id: UUID, body: ReminderInput, request: Request):
        return svc(request).add_reminder(str(application_id), body.model_dump())

    @app.patch('/api/reminders/{reminder_id}')
    async def update_reminder(reminder_id: UUID, body: ReminderUpdate, request: Request):
        return svc(request).update_reminder(str(reminder_id), body.status, body.due_at)

    @app.post('/api/imports/job-search')
    async def import_job_search(body: ImportInput, request: Request):
        return svc(request).import_tracker(body.commit)

    @app.post('/api/tasks')
    async def create_task(body: TaskInput, request: Request):
        return svc(request).enqueue(body.kind, str(body.application_id) if body.application_id else None,
                                    body.options.model_dump(), str(body.request_id))

    @app.post('/api/tasks/{task_id}/retry')
    async def retry(task_id: UUID, body: RetryInput, request: Request):
        return svc(request).retry(str(task_id), str(body.request_id))

    @app.get('/api/tasks/{task_id}')
    async def task(task_id: UUID, request: Request):
        result = svc(request).store.task(str(task_id))
        if not result:
            raise KeyError('Task not found')
        return result

    @app.post('/api/artifacts/{artifact_id}/save')
    async def save(artifact_id: UUID, request: Request):
        return svc(request).save_to_sent(str(artifact_id))

    @app.get('/api/artifacts/{artifact_id}/download')
    async def download(artifact_id: UUID, request: Request, inline: bool = False):
        path, record = svc(request).file(str(artifact_id))
        return FileResponse(path, media_type='application/pdf', filename=record['filename'],
                            content_disposition_type='inline' if inline else 'attachment')

    @app.get('/api/families/{family}/pdf')
    async def family_pdf(family: str, request: Request):
        return FileResponse(svc(request).family_pdf(family), media_type='application/pdf', content_disposition_type='inline')

    @app.post('/api/refresh')
    async def refresh(request: Request):
        svc(request).import_collections()
        return {'ok': True}

    dist = Path(__file__).resolve().parents[1] / 'dist'
    if dist.is_dir():
        app.mount('/', StaticFiles(directory=dist, html=True), name='frontend')
    else:
        @app.get('/')
        def development():
            return {'app': 'Career Workspace', 'interface': 'http://127.0.0.1:5173', 'build': 'npm run build'}
    return app


app = create_app()
