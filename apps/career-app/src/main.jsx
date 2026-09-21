import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { ArrowUpRight, BriefcaseBusiness, FileText, Search, FolderOpen, Settings2, Plus, ArrowRight, Copy, Sparkles, Check, LoaderCircle, Download, RefreshCw, PanelLeftClose, CircleAlert, LayoutDashboard, ListChecks, CalendarDays, Clock3 } from 'lucide-react';
import './styles.css';
import './tracking.css';

async function api(path, options = {}) {
  const response = await fetch('/api' + path, { ...options, headers: { 'Content-Type': 'application/json', 'X-Career-Request': '1', ...options.headers } });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Please check the fields and try again.');
  return data;
}
const post = (path, data) => api(path, { method: 'POST', body: JSON.stringify(data) });
const patch = (path, data) => api(path, { method: 'PATCH', body: JSON.stringify(data) });
const title = (key) => (key || '').replaceAll('-', ' ').replace(/\b\w/g, c => c.toUpperCase());
const when = (date) => date ? new Date(date).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : 'Imported';
const day = (value) => value ? new Date(value.length === 10 ? value + 'T12:00:00' : value).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }) : 'Not recorded';
const percent = (value) => value == null ? 'n.a.' : Math.round(value * 100) + '%';
const blank = { company: '', role: '', job_description: '', source_url: '' };
const statuses = ['draft','action_required','submitted','in_process','interview_scheduled','offer','accepted','rejected','withdrawn','ghosted','archived'];
const stages = ['application','recruiter_screen','assessment','technical_screen','hiring_manager','case_study','culture_fit','offer'];
const nav = [['dashboard', 'Dashboard', LayoutDashboard], ['applications', 'Applications', ListChecks], ['prepare', 'Prepare application', FileText], ['search', 'Search opportunities', Search], ['sent', 'Sent & documents', FolderOpen], ['settings', 'Profile & settings', Settings2]];

function App() {
  const [page, setPage] = useState('dashboard');
  const [boot, setBoot] = useState(null);
  const [form, setForm] = useState(blank);
  const [active, setActive] = useState(null);
  const [matches, setMatches] = useState([]);
  const [matchMethod, setMatchMethod] = useState('jev');
  const [family, setFamily] = useState('');
  const [rebuild, setRebuild] = useState(false);
  const [preview, setPreview] = useState(null);
  const [letter, setLetter] = useState('');
  const [letterTask, setLetterTask] = useState(null);
  const [pending, setPending] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [search, setSearch] = useState({ role: 'senior data scientist', location: 'Argentina', remote: true, limit: 10, ai_rank: false });
  const [searchTask, setSearchTask] = useState(null);
  const [filter, setFilter] = useState('');
  const [documentState, setDocumentState] = useState('all');
  const [documentKind, setDocumentKind] = useState('all');
  const [sourceFilter, setSourceFilter] = useState('all');
  const [documentDate, setDocumentDate] = useState('');
  const [mobileNav, setMobileNav] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [restored, setRestored] = useState(false);
  const [tracking, setTracking] = useState(null);
  const [applicationFilter, setApplicationFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [eventDraft, setEventDraft] = useState({ event_type: 'interview_scheduled', stage: 'recruiter_screen', scheduled_at: '', occurred_at: '', notes: '', contact_name: '' });
  const [reminderDraft, setReminderDraft] = useState({ title: 'Follow up', due_at: '', reminder_type: 'follow_up' });
  const [importReport, setImportReport] = useState(null);

  async function refresh() {
    const data = await api('/bootstrap');
    setBoot(data);
    return data;
  }
  useEffect(() => { refresh().catch(e => setError(e.message)); }, []);
  useEffect(() => {
    const handle = setInterval(() => { refresh().catch(() => {}); }, 2500);
    return () => clearInterval(handle);
  }, []);
  useEffect(() => {
    if (!preview) return;
    const previous = document.activeElement;
    const modal = document.querySelector('.preview-modal');
    const focusable = () => [...modal.querySelectorAll('button:not(:disabled),a[href],iframe')];
    focusable()[0]?.focus();
    function onKey(event) {
      if (event.key === 'Escape') setPreview(null);
      if (event.key === 'Tab') {
        const items = focusable();
        const first = items[0], last = items[items.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
    }
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('keydown', onKey); previous?.focus?.(); };
  }, [preview?.id]);
  useEffect(() => {
    if (boot && !restored) {
      setRestored(true);
      if (boot.searches?.length) setSearchTask(boot.searches[0].id);
    }
  }, [boot]);
  useEffect(() => {
    if (boot && !boot.settings.cv_match_ai_ready && matchMethod === 'jev') setMatchMethod('keyword');
  }, [boot, matchMethod]);
  const tasks = boot?.tasks || [];
  const working = tasks.filter(t => ['queued', 'running'].includes(t.status));
  const currentTasks = tasks.filter(t => t.application_id === active);
  const documents = (boot?.artifacts || []).filter(a => a.application_id === active);
  useEffect(() => {
    const doneLetter = currentTasks.find(t => t.kind === 'letter' && t.status === 'completed');
    if (doneLetter && doneLetter.id !== letterTask) {
      setLetter(doneLetter.result?.letter || ''); setLetterTask(doneLetter.id);
    }
  }, [boot, active]);

  function report(e) { setError(e.message || String(e)); }
  async function action(fn) {
    setPending(true); setError(''); setNotice('');
    try { await fn(); } catch (e) { report(e); } finally { setPending(false); }
  }
  async function saveApplication() {
    if (!form.job_description.trim()) throw new Error('Paste a job description to get started.');
    let app;
    if (active) app = await api('/applications/' + active, { method: 'PUT', body: JSON.stringify(form) });
    else app = await post('/applications', form);
    setActive(app.id); setDirty(false); await refresh(); return app;
  }
  async function run(kind, extra = {}) {
    await action(async () => {
      const app = await saveApplication();
      const task = await post('/tasks', { kind, application_id: app.id, request_id: crypto.randomUUID(), options: { family, rebuild, ...extra } });
      setNotice(kind === 'copy' ? 'Copy queued. The PDF will appear in Sent.' : 'Started. You can keep working while this runs.');
      await refresh();
      return task;
    });
  }
  async function openApplication(app) {
    if (dirty && !window.confirm('Discard the unsaved changes in this application?')) return;
    setActive(app.id); setForm({ company: app.company || '', role: app.role || '', source_url: app.source_url || '', job_description: app.job_description || '' });
    setMatches([]); setFamily(''); setPreview(null); setLetter(''); setLetterTask(null); setDirty(false); setPage('prepare'); setError(''); setNotice('');
  }
  async function openTracking(app) {
    await action(async () => {
      const detail = await api('/applications/' + app.id);
      setTracking(detail); setPage('applications');
    });
  }
  async function saveTracking() {
    await action(async () => {
      const fields = ['status','current_stage','applied_on','closed_on','source_name','employment_type','workplace_type','location','match_rating','compensation_text','next_action','next_action_due_at'];
      const body = Object.fromEntries(fields.map(key => [key, tracking[key] || null]));
      const detail = await patch('/applications/' + tracking.id + '/tracking', body);
      setTracking(detail); await refresh(); setNotice('Application tracking updated.');
    });
  }
  async function recordEvent() {
    await action(async () => {
      const body = { ...eventDraft };
      for (const key of ['scheduled_at','occurred_at']) body[key] = body[key] ? new Date(body[key]).toISOString() : null;
      const detail = await post('/applications/' + tracking.id + '/events', body);
      setTracking(detail); setEventDraft({ event_type: 'interview_scheduled', stage: 'recruiter_screen', scheduled_at: '', occurred_at: '', notes: '', contact_name: '' });
      await refresh(); setNotice('Activity recorded.');
    });
  }
  async function addReminder() {
    await action(async () => {
      await post('/applications/' + tracking.id + '/reminders', { ...reminderDraft, due_at: new Date(reminderDraft.due_at).toISOString() });
      setTracking(await api('/applications/' + tracking.id)); setReminderDraft({ title: 'Follow up', due_at: '', reminder_type: 'follow_up' });
      await refresh(); setNotice('Reminder added.');
    });
  }
  async function closeReminder(reminder, status = 'completed') {
    await action(async () => {
      await patch('/reminders/' + reminder.id, { status });
      if (tracking?.id === reminder.application_id) setTracking(await api('/applications/' + tracking.id));
      await refresh();
    });
  }
  async function inspectImport(commit = false) {
    await action(async () => {
      if (commit && !window.confirm('Import the Excel tracker into SQLite? The workbook will remain unchanged.')) return;
      const report = await post('/imports/job-search', { commit });
      setImportReport(report); if (commit) { await refresh(); setNotice(report.already_imported ? 'This workbook was already imported.' : `${report.total} tracker rows imported.`); }
    });
  }
  function newApplication() {
    if (dirty && !window.confirm('Discard the unsaved changes in this application?')) return;
    setForm(blank); setActive(null); setMatches([]); setFamily(''); setPreview(null); setLetter(''); setLetterTask(null); setDirty(false); setPage('prepare'); setError(''); setNotice('');
  }
  function change(key, value) { setForm(f => ({ ...f, [key]: value })); setDirty(true); if (key === 'job_description') { setMatches([]); setFamily(''); } }
  function chooseMatchMethod(method) { setMatchMethod(method); setMatches([]); setFamily(''); }
  const ready = Boolean(form.job_description.trim()) && !pending;
  const result = tasks.find(t => t.id === searchTask) || boot?.searches?.find(t => t.id === searchTask);
  const jobs = result?.result?.jobs || [];
  const dashboard = boot?.dashboard || { counts: {}, following: [], upcoming: [], action_required: [], statistics: { monthly: [] } };
  const stats = dashboard.statistics || { monthly: [] };
  const filteredApplications = (boot?.applications || []).filter(app =>
    (statusFilter === 'all' || app.status === statusFilter) &&
    [app.company, app.role].join(' ').toLowerCase().includes(applicationFilter.toLowerCase()));

  return <div className="shell">
    <aside className={mobileNav ? 'sidebar expanded' : 'sidebar'}>
      <a className="brand" href="#" onClick={e => { e.preventDefault(); setPage('dashboard'); }}><span className="brand-icon"><BriefcaseBusiness size={22}/></span><span>Career<span className="brand-sub">WORKSPACE</span></span></a>
      <div className="workspace-label">YOUR NEXT CHAPTER</div>
      <nav>{nav.map(([id, label, Icon]) => <button key={id} className={page === id ? 'nav-item active' : 'nav-item'} onClick={() => { setPage(id); setMobileNav(false); }}><Icon size={18}/>{label}{id === 'sent' && <span className="nav-count">{boot?.artifacts?.filter(a => a.state === 'sent').length || 0}</span>}</button>)}</nav>
      <div className="sidebar-note"><span className="live-dot"/>Local workspace<p>Your documents. Your pace.</p></div>
      <div className="account"><span className="avatar">ML</span><div><strong>{boot?.settings?.name || 'Your career workspace'}</strong><small>{boot?.settings?.location || 'Personal workspace'}</small></div></div>
    </aside>
    <main>
      <header className="topbar"><button className="mobile-toggle icon-button" aria-label="Toggle navigation" onClick={() => setMobileNav(!mobileNav)}><PanelLeftClose size={20}/></button><div className="breadcrumb">Workspace <span>/</span> {nav.find(n => n[0] === page)?.[1]}</div><div className="topbar-right">{working.length > 0 && <span className="work-status"><LoaderCircle size={14} className="spin"/>{working.length} in progress</span>}<button className="button small secondary" onClick={newApplication}><Plus size={15}/>New application</button></div></header>
      <div className="content">
        {error && <div role="alert" className="message error"><CircleAlert size={18}/><span>{error}</span><button aria-label="Dismiss error" onClick={() => setError('')}>×</button></div>}
        {notice && <div role="status" className="message success"><Check size={18}/><span>{notice}</span><button aria-label="Dismiss notice" onClick={() => setNotice('')}>×</button></div>}
        {!boot && <div className="message"><LoaderCircle className="spin" size={18}/>Connecting to your workspace…</div>}
        {page === 'dashboard' && <>
          <div className="page-heading"><div><p className="eyebrow">APPLICATION PIPELINE</p><h1>Know what needs attention<span>.</span></h1><p>Spreadsheet statuses, screenings, and conversion metrics from one source of truth.</p></div><button className="button primary" onClick={()=>setPage('applications')}><ListChecks size={16}/>Review applications</button></div>
          <div className="kpi-grid">
            {[['Tracked',dashboard.counts.total || 0,'All opportunities'],['Open',dashboard.counts.open || 0,'Active processes'],['Following',dashboard.counts.following || 0,'Under consideration'],['Upcoming',dashboard.counts.upcoming || 0,'Pending interview'],['Actions required',dashboard.counts.action_required || 0,'Finish submission'],['Interview rate',percent(stats.interview_rate),`${stats.interviews || 0} applications`]].map(([label,value,detail])=><section className="kpi-card" key={label}><span>{label}</span><strong>{value}</strong><small>{detail}</small></section>)}
          </div>
          <div className="dashboard-grid workflow-dashboard">
            <section className="panel"><div className="panel-heading"><Clock3 size={18}/><h2>Following</h2><span className="minor">{dashboard.following.length}</span></div>
              <div className="attention-list">{dashboard.following.slice(0,8).map(item=><button className="attention-row attention-main" key={item.id} onClick={()=>openTracking(item)}><div><strong>{item.company || 'Company not recorded'}</strong><span>{item.role || 'Role not recorded'}</span><small>{title(item.current_stage)}</small></div><ArrowUpRight size={15}/></button>)}{!dashboard.following.length&&<div className="empty-small"><Check size={22}/>No applications under consideration.</div>}</div>
            </section>
            <section className="panel"><div className="panel-heading"><CalendarDays size={18}/><h2>Upcoming screenings</h2><span className="minor">{dashboard.upcoming.length}</span></div>
              <div className="attention-list">{dashboard.upcoming.slice(0,8).map(item=><button className="attention-row attention-main" key={item.id} onClick={()=>openTracking(item)}><div><strong>{item.company || 'Company not recorded'}</strong><span>{item.role || 'Role not recorded'}</span><small>{item.scheduled_at ? when(item.scheduled_at) : 'Date to confirm'}</small></div><ArrowUpRight size={15}/></button>)}{!dashboard.upcoming.length&&<div className="empty-small"><CalendarDays size={22}/>No pending interviews.</div>}</div>
            </section>
            <section className="panel"><div className="panel-heading"><ListChecks size={18}/><h2>Actions required</h2><span className="minor">{dashboard.action_required.length}</span></div>
              <div className="attention-list">{dashboard.action_required.slice(0,8).map(item=><button className="attention-row attention-main" key={item.id} onClick={()=>openTracking(item)}><div><strong>{item.company || 'Company not recorded'}</strong><span>{item.role || 'Role not recorded'}</span><small>{item.next_action || 'Complete application'}</small></div><ArrowUpRight size={15}/></button>)}{!dashboard.action_required.length&&<div className="empty-small"><Check size={22}/>No incomplete submissions.</div>}</div>
            </section>
          </div>
          <div className="dashboard-grid lower-dashboard">
            <section className="panel"><div className="panel-heading"><h2>Application funnel</h2><span className="minor">All submitted applications</span></div>
              <div className="funnel-list">{[['Submitted',stats.submitted,1],['Responses',stats.responses,stats.response_rate],['Interviews',stats.interviews,stats.interview_rate],['Offers',stats.offers,stats.offer_rate],['Accepted',stats.accepted,stats.submitted ? stats.accepted/stats.submitted : null]].map(([label,count,rate])=><div className="funnel-row" key={label}><div><span>{label}</span><strong>{count || 0}</strong></div><div className="bar"><i style={{width:percent(rate === null ? 0 : rate)}}/></div><small>{percent(rate)}</small></div>)}</div>
            </section>
            <section className="panel"><div className="panel-heading"><h2>Timing and outcomes</h2></div>
              <div className="metric-list"><div><span>Median time to response</span><strong>{stats.median_days_to_response == null ? 'n.a.' : `${stats.median_days_to_response} days`}</strong></div><div><span>Median process duration</span><strong>{stats.median_process_days == null ? 'n.a.' : `${stats.median_process_days} days`}</strong></div><div><span>Rejected</span><strong>{stats.rejected || 0}</strong></div><div><span>Ghosted</span><strong>{stats.ghosted || 0}</strong></div><div><span>Offer acceptance</span><strong>{percent(stats.acceptance_rate)}</strong></div></div>
            </section>
          </div>
          {!!stats.monthly?.length && <section className="panel monthly-panel"><div className="panel-heading"><h2>Monthly applications</h2></div><div className="monthly-bars">{stats.monthly.slice(-12).map(month=><div key={month.month}><span>{month.month}</span><div className="monthly-track"><i style={{height:`${Math.max(5,Math.min(100,month.submitted/(Math.max(...stats.monthly.map(m=>m.submitted))||1)*100))}%`}}/></div><strong>{month.submitted}</strong></div>)}</div></section>}
        </>}
        {page === 'applications' && <>
          <div className="page-heading"><div><p className="eyebrow">APPLICATION RECORDS</p><h1>Manage every process<span>.</span></h1><p>Update stages, record activity, and keep the next action visible.</p></div></div>
          <div className="library-filters"><label className="search-input"><Search size={17}/><input aria-label="Search applications" placeholder="Search company or role…" value={applicationFilter} onChange={e=>setApplicationFilter(e.target.value)}/></label><select aria-label="Application status" value={statusFilter} onChange={e=>setStatusFilter(e.target.value)}><option value="all">All statuses</option>{statuses.map(item=><option key={item} value={item}>{title(item)}</option>)}</select></div>
          <div className="panel table-panel application-list-panel"><table><thead><tr><th>Opportunity</th><th>Status</th><th>Stage</th><th>Applied</th><th>Next action</th><th><span className="sr-only">Actions</span></th></tr></thead><tbody>{filteredApplications.map(item=><tr key={item.id}><td><strong>{item.company || 'Company not recorded'}</strong><small>{item.role || 'Role not recorded'}</small></td><td><span className={'pill status-'+item.status}>{title(item.status)}</span></td><td>{title(item.current_stage)}</td><td>{day(item.applied_on)}</td><td>{item.next_action || '—'}<small>{item.next_action_due_at ? when(item.next_action_due_at) : ''}</small></td><td><button className="text-button" onClick={()=>openTracking(item)}>Track<ArrowRight size={14}/></button></td></tr>)}</tbody></table>{!filteredApplications.length&&<div className="empty-small">No applications match these filters.</div>}</div>
          {tracking && <section className="tracking-workspace">
            <div className="section-title"><h2>{tracking.company || 'Company not recorded'} · {tracking.role || 'Role not recorded'}</h2><div className="inline-actions"><button className="button small secondary" onClick={()=>openApplication(tracking)}>Prepare documents</button><button className="icon-button" aria-label="Close application details" onClick={()=>setTracking(null)}>×</button></div></div>
            <div className="tracking-grid">
              <section className="panel"><div className="panel-heading"><h2>Current state</h2></div>
                <div className="two-fields"><label>Status<select value={tracking.status} onChange={e=>setTracking({...tracking,status:e.target.value})}>{statuses.map(item=><option value={item} key={item}>{title(item)}</option>)}</select></label><label>Stage<select value={tracking.current_stage} onChange={e=>setTracking({...tracking,current_stage:e.target.value})}>{stages.map(item=><option value={item} key={item}>{title(item)}</option>)}</select></label></div>
                <div className="two-fields"><label>Application date<input type="date" value={tracking.applied_on || ''} onChange={e=>setTracking({...tracking,applied_on:e.target.value})}/></label><label>Workplace<select value={tracking.workplace_type || ''} onChange={e=>setTracking({...tracking,workplace_type:e.target.value})}><option value="">Not recorded</option><option>remote</option><option>hybrid</option><option>on site</option></select></label></div>
                <div className="two-fields"><label>Source<input value={tracking.source_name || ''} onChange={e=>setTracking({...tracking,source_name:e.target.value})}/></label><label>Location<input value={tracking.location || ''} onChange={e=>setTracking({...tracking,location:e.target.value})}/></label></div>
                <label>Next action<input value={tracking.next_action || ''} onChange={e=>setTracking({...tracking,next_action:e.target.value})} placeholder="e.g. Send portfolio to recruiter"/></label>
                <label>Next action date<input type="datetime-local" value={(tracking.next_action_due_at || '').slice(0,16)} onChange={e=>setTracking({...tracking,next_action_due_at:e.target.value ? new Date(e.target.value).toISOString() : null})}/></label>
                <button className="button primary full" disabled={pending} onClick={saveTracking}>Save tracking</button>
              </section>
              <section className="panel"><div className="panel-heading"><h2>Record activity</h2></div>
                <div className="two-fields"><label>Activity<select value={eventDraft.event_type} onChange={e=>setEventDraft({...eventDraft,event_type:e.target.value})}><option value="interview_scheduled">Schedule interview</option><option value="stage_completed">Complete stage</option><option value="application_submitted">Application submitted</option><option value="offer_received">Offer received</option><option value="follow_up">Follow-up sent</option><option value="note">Note</option></select></label><label>Stage<select value={eventDraft.stage} onChange={e=>setEventDraft({...eventDraft,stage:e.target.value})}>{stages.map(item=><option value={item} key={item}>{title(item)}</option>)}</select></label></div>
                {eventDraft.event_type==='interview_scheduled'?<label>Scheduled for<input type="datetime-local" value={eventDraft.scheduled_at} onChange={e=>setEventDraft({...eventDraft,scheduled_at:e.target.value})}/></label>:<label>Occurred on<input type="datetime-local" value={eventDraft.occurred_at} onChange={e=>setEventDraft({...eventDraft,occurred_at:e.target.value})}/></label>}
                <label>Contact <span className="optional">optional</span><input value={eventDraft.contact_name} onChange={e=>setEventDraft({...eventDraft,contact_name:e.target.value})}/></label>
                <label>Notes<textarea rows={4} value={eventDraft.notes} onChange={e=>setEventDraft({...eventDraft,notes:e.target.value})}/></label>
                <button className="button primary full" disabled={pending || (eventDraft.event_type==='interview_scheduled'&&!eventDraft.scheduled_at)} onClick={recordEvent}>Record activity</button>
              </section>
              <section className="panel"><div className="panel-heading"><h2>Reminders</h2><span className="minor">{tracking.reminders?.filter(r=>r.status==='open').length || 0} open</span></div>
                <div className="reminder-list">{tracking.reminders?.filter(r=>r.status==='open').map(item=><div className="attention-row" key={item.id}><div><strong>{item.title}</strong><small>{when(item.due_at)}</small></div><button className="button small secondary" onClick={()=>closeReminder(item)}>Done</button></div>)}</div>
                <div className="two-fields"><label>Reminder<input value={reminderDraft.title} onChange={e=>setReminderDraft({...reminderDraft,title:e.target.value})}/></label><label>Due<input type="datetime-local" value={reminderDraft.due_at} onChange={e=>setReminderDraft({...reminderDraft,due_at:e.target.value})}/></label></div><button className="button secondary full" disabled={!reminderDraft.title.trim()||!reminderDraft.due_at} onClick={addReminder}>Add reminder</button>
              </section>
              <section className="panel timeline-panel"><div className="panel-heading"><h2>Timeline</h2><span className="minor">{tracking.events?.length || 0} events</span></div>
                <div className="timeline">{tracking.events?.map(item=><div className="timeline-item" key={item.id}><span/><div><strong>{title(item.event_type)}</strong><p>{title(item.stage)}{item.outcome ? ` · ${title(item.outcome)}` : ''}</p><small>{when(item.scheduled_at || item.occurred_at || item.created_at)}</small>{item.notes&&<blockquote>{item.notes}</blockquote>}</div></div>)}{!tracking.events?.length&&<div className="empty-small">No activity recorded yet.</div>}</div>
              </section>
            </div>
          </section>}
        </>}
        {page === 'prepare' && <>
          <div className="page-heading"><div><p className="eyebrow">MAKE YOUR EXPERIENCE COUNT</p><h1>Prepare your next application<span>.</span></h1><p>One job description. The right CV. A letter that sounds like you.</p></div><div className="quiet-tag"><span className="live-dot"/>{boot?.families?.length || 6} CV families</div></div>
          <div className="work-grid">
            <section className="panel description-panel"><div className="panel-heading"><span className="step">01</span><h2>The opportunity</h2><span className="minor">{active ? 'Saved application' : 'Start here'}</span></div>
              <div className="two-fields"><label>Company<input value={form.company} onChange={e => change('company', e.target.value)} placeholder="e.g. Pythian" maxLength={160}/></label><label>Role<input value={form.role} onChange={e => change('role', e.target.value)} placeholder="e.g. Lead AI/ML Engineer" maxLength={200}/></label></div>
              <label>Posting URL <span className="optional">optional</span><input type="url" value={form.source_url} onChange={e => change('source_url', e.target.value)} placeholder="https://…"/></label>
              <label>Job description<textarea className="job-text" value={form.job_description} onChange={e => change('job_description', e.target.value)} placeholder={'Paste the full job description here.\n\nInclude the responsibilities, requirements and anything that tells us what the team is looking for.'} maxLength={80000}/></label>
              <div className="field-footer"><span>{form.job_description.length.toLocaleString()} / 80,000 characters</span><span>{dirty ? 'Unsaved changes' : active ? 'Saved' : 'Text stays in this workspace'}</span></div>
              <div className="match-method"><span>Matching method</span><div className="method-toggle" role="group" aria-label="CV matching method"><button type="button" className={matchMethod === 'jev' ? 'active' : ''} aria-pressed={matchMethod === 'jev'} disabled={boot && !boot.settings.cv_match_ai_ready} onClick={() => chooseMatchMethod('jev')}>JEV</button><button type="button" className={matchMethod === 'keyword' ? 'active' : ''} aria-pressed={matchMethod === 'keyword'} onClick={() => chooseMatchMethod('keyword')}>Keywords</button></div></div>
              <button className="button primary full" disabled={!ready} onClick={() => action(async () => { await saveApplication(); const data = await post('/match', { job_description: form.job_description, method: matchMethod }); setMatches(data); setFamily(data[0]?.auto_select ? data[0].key : ''); setNotice(data[0]?.warning || (data[0]?.method === 'jev' ? 'CV families ranked semantically by JEV. You can choose a different family.' : 'CV families ranked by matching keywords. You can choose a different family.')); })}><Search size={17}/>Find my best CV<ArrowRight size={17}/></button>
              <button className="text-button full" disabled={!ready} onClick={() => action(async () => { await saveApplication(); setNotice('Application saved.'); })}>Save description for later</button>
            </section>
            <div className="right-column"><section className="panel"><div className="panel-heading"><span className="step">02</span><h2>Make it yours</h2></div>
              <div className="family-selector"><label>CV family<select value={family} onChange={e => setFamily(e.target.value)}><option value="">Automatically choose the best match</option>{(boot?.families || []).map(f => <option key={f.key} value={f.key}>{f.label}</option>)}</select></label></div>
              <label className="rebuild-option"><input type="checkbox" checked={rebuild} onChange={e=>setRebuild(e.target.checked)}/>Rebuild the reusable PDF from source before copying</label>
              {boot?.families?.find(f=>f.key===family)?.stale && <p className="helper">This family’s source is newer than its PDF. Rebuild to include those changes, or copy the existing PDF unchanged.</p>}
              {matches.length > 0 ? <div className="matches">{matches.slice(0, 3).map((m, i) => { const candidate = boot?.families?.find(f => f.key === m.key); const isJev = m.method === 'jev'; const keywordStrength = matches[0]?.score > 0 ? (m.score / matches[0].score) * 100 : 0; const aspects = isJev ? [['Role', m.components?.role_alignment?.score || 0], ['Requirements', m.components?.requirements_coverage?.score || 0], ['Seniority', m.components?.seniority_alignment?.score || 0]] : [['Keyword strength', keywordStrength]]; return <div className={'match ' + (family === m.key ? 'selected' : '')} key={m.key}><button className="match-select" onClick={() => setFamily(m.key)} aria-label={`Choose ${m.label}, ${isJev ? `${Math.round(m.score)} percent weighted relevance` : `${m.score} keyword points`}`}><div className="match-summary"><span className="match-rank">{i + 1}</span><strong>{m.label}</strong><span className="total-score"><b>{isJev ? Number(m.score).toFixed(1) : m.score}</b><small>{isJev ? 'weighted' : 'points'}</small></span></div><div className={'aspect-bars ' + (isJev ? '' : 'single')}>{aspects.map(([label, value]) => <div className="aspect-row" key={label}><span>{label}</span><span className="match-bar" role="progressbar" aria-label={`${m.label}: ${label}`} aria-valuemin="0" aria-valuemax="100" aria-valuenow={Math.round(value)}><i style={{width: `${Math.max(0, Math.min(100, value))}%`}}/></span><b>{Math.round(value)}%</b></div>)}</div></button>{candidate?.pdf_exists && <a className="match-preview" href={'/api/families/'+m.key+'/pdf'} target="_blank" rel="noreferrer" aria-label={`Preview ${m.label} CV`} title="Preview CV"><ArrowUpRight size={16}/></a>}</div>})}{!matches[0]?.auto_select && <p className="match-guidance">{matches[0]?.selection_note || 'No strong match. Choose a CV family before copying.'}</p>}<p className="match-legend">{matches[0]?.method === 'jev' ? `JEV semantic relevance · weighted total and aspect scores · 0–100${matches[0]?.model ? ` · ${matches[0].model}` : ''}` : 'Relative keyword match · bars compare these results'}</p></div> : <div className="match-placeholder"><FileText size={24}/><div><strong>Start with your strongest fit</strong><p>We’ll compare the description with your reusable CV families.</p></div></div>}
              <div className="action-list"><div className="action-row"><span className="action-icon"><Copy size={19}/></span><div><h3>Use an existing CV</h3><p>Copy the matching PDF unchanged to Sent.</p><span className="pill">PDF stays unchanged</span></div><button className="button small secondary" disabled={!ready || currentTasks.some(t => t.kind === 'copy' && ['running','queued'].includes(t.status))} onClick={() => run('copy')}>Copy to sent<ArrowUpRight size={14}/></button></div>
                <div className="action-row"><span className="action-icon gold"><Sparkles size={19}/></span><div><h3>Tailor a new CV</h3><p>Grounded in your experience and evidence.</p></div><button className="button small secondary" disabled={!ready || !boot?.settings?.cv_ai_ready || currentTasks.some(t => t.kind === 'cv' && ['running','queued'].includes(t.status))} onClick={() => run('cv')}>Generate<ArrowUpRight size={14}/></button></div>
                <div className="action-row"><span className="action-icon"><FileText size={19}/></span><div><h3>Write a cover letter</h3><p>A focused draft you can edit before saving.</p></div><button className="button small secondary" disabled={!ready || !boot?.settings?.letter_ai_ready || currentTasks.some(t => t.kind === 'letter' && ['running','queued'].includes(t.status))} onClick={() => run('letter')}>Generate<ArrowUpRight size={14}/></button></div></div>
              {boot && (!boot.settings.cv_match_ai_ready || !boot.settings.cv_ai_ready || !boot.settings.letter_ai_ready) && <p className="helper">Some AI actions need configuration. See Profile & settings.</p>}
            </section>
            <section className="panel compact-panel"><div className="panel-heading"><span className="step">03</span><h2>Review & save</h2><span className="minor">{documents.length} documents</span></div>
              {documents.length ? <div className="document-mini-list">{documents.map(a => <div className="document-mini" key={a.id}><FileText size={18}/><button className="document-name" onClick={() => setPreview(a)}><strong>{a.filename}</strong><small>{title(a.kind)} · {when(a.created_at)} · {a.state}</small></button><button className="icon-button" title="Preview" aria-label={'Preview ' + a.filename} onClick={() => setPreview(a)}><ArrowUpRight size={18}/></button></div>)}</div> : <div className="empty-small"><FolderOpen size={23}/><p>Your PDFs will appear here.<br/><span>Preview first, then keep the version you want.</span></p></div>}
            </section></div>
          </div>
          {letter && <section className="panel letter-panel"><div className="panel-heading"><h2>Your cover letter</h2><span className="minor">Editable draft</span></div><textarea aria-label="Cover letter text" value={letter} onChange={e => setLetter(e.target.value)} rows={14}/><div className="row-between"><span className="helper">{letter.trim().split(/\s+/).length} words · Review claims before saving.</span><button className="button primary" disabled={pending || !letter.trim()} onClick={() => run('letter-pdf', { letter })}><FileText size={16}/>Create PDF preview</button></div></section>}
          {currentTasks.length > 0 && <TaskList tasks={currentTasks} retry={t => action(async () => { await post('/tasks/' + t.id + '/retry', { request_id: crypto.randomUUID() }); await refresh(); })}/>}
        </>}
        {page === 'search' && <><div className="page-heading"><div><p className="eyebrow">FIND YOUR NEXT OPPORTUNITY</p><h1>A good fit starts here<span>.</span></h1><p>Search your existing sources, then prepare everything in one place.</p></div></div>
          <section className="panel search-form"><label>Target role<input value={search.role} onChange={e => setSearch({...search, role:e.target.value})} placeholder="Senior data scientist"/></label><label>Location<input value={search.location} onChange={e => setSearch({...search, location:e.target.value})}/></label><label>Results<select value={search.limit} onChange={e => setSearch({...search, limit:Number(e.target.value)})}>{[10,20,25].map(n => <option key={n}>{n}</option>)}</select></label><label className="check-label"><input type="checkbox" checked={search.remote} onChange={e => setSearch({...search, remote:e.target.checked})}/>Include remote</label><label className="check-label"><input type="checkbox" checked={search.ai_rank} disabled={!boot?.settings?.search_ai_ready} onChange={e => setSearch({...search, ai_rank:e.target.checked})}/>AI ranking</label><button className="button primary" disabled={pending || !search.role.trim()} onClick={() => action(async () => { const t = await post('/tasks', {kind:'search', request_id:crypto.randomUUID(), options:search}); setSearchTask(t.id); await refresh(); })}><Search size={17}/>Search jobs</button></section>
          <div className="section-title"><h2>{jobs.length ? `${jobs.length} opportunities` : 'Search results'}</h2><div className="inline-fields"><select aria-label="Saved searches" value={searchTask || ''} onChange={e=>setSearchTask(e.target.value)}><option value="">Select a search</option>{(boot?.searches || []).map(t=><option key={t.id} value={t.id}>{t.options.role} · {when(t.created_at)}</option>)}</select><select aria-label="Filter job source" value={sourceFilter} onChange={e=>setSourceFilter(e.target.value)}><option value="all">All sources</option>{[...new Set(jobs.map(j=>j.job.source))].map(s=><option key={s}>{s}</option>)}</select></div></div>
          {result && <TaskList tasks={[result]} retry={t=>action(async()=>{const next=await post('/tasks/'+t.id+'/retry',{request_id:crypto.randomUUID()}); setSearchTask(next.id); await refresh();})}/>}
          {result?.result?.warnings?.map((w,i)=><div key={i} className="message warning">{w}</div>)}
          <div className="job-grid">{jobs.filter(j=>sourceFilter==='all'||j.job.source===sourceFilter).map((r,i) => <article className="panel job-card" key={r.job.job_id + i}><div className="row-between"><span className="pill">{r.job.source === 'cache' ? 'Cached · verify availability' : r.job.source}</span>{r.fit_score != null && <span className="fit-score">{r.fit_score}/100 relevance</span>}</div><h2>{r.job.title}</h2><p className="company-line">{r.job.company} <span>·</span> {r.job.location}</p><div className="job-description">{r.job.description}</div><p className="helper">{r.fit_explanation || r.job.location_eligibility_reason}</p><div className="row-between"><a href={/^https?:\/\//i.test(r.job.url) ? r.job.url : undefined} target="_blank" rel="noreferrer" className="text-button">Original posting<ArrowUpRight size={14}/></a><button className="button secondary small" disabled={pending} onClick={()=>action(async()=>{if(dirty && !window.confirm('Discard unsaved changes and open this opportunity?'))return;const app=await post('/applications',{company:r.job.company,role:r.job.title,source_url:r.job.url,job_description:r.job.description});setDirty(false);setActive(app.id);setForm({company:app.company||'',role:app.role||'',source_url:app.source_url||'',job_description:app.job_description||''});setMatches([]);setFamily('');setPreview(null);setLetter('');setLetterTask(null);setPage('prepare');await refresh();})}>Prepare application<ArrowRight size={14}/></button></div></article>)}</div>
          {!jobs.length && !working.some(t=>t.id===searchTask) && <div className="empty-large"><Search size={35}/><h2>{result?.status==='completed'?'No matching opportunities this time':'Your search starts with a role'}</h2><p>{result?.status==='completed'?'Try a broader title or a different location.':'Choose a title and location above. Cached results are clearly labeled.'}</p></div>}
        </>}
        {page === 'sent' && <><div className="page-heading"><div><p className="eyebrow">EVERY VERSION, IN ONE PLACE</p><h1>Your application library<span>.</span></h1><p>Real PDFs, organized by opportunity. Saving a file does not submit an application.</p></div></div><div className="library-filters"><label className="search-input"><Search size={17}/><input aria-label="Search documents" placeholder="Search company, role or filename…" value={filter} onChange={e=>setFilter(e.target.value)}/></label><select aria-label="Document state" value={documentState} onChange={e=>setDocumentState(e.target.value)}><option value="all">All documents</option><option value="sent">Saved to sent</option><option value="draft">Drafts</option><option value="submitted">Historical submissions</option></select><select aria-label="Document type" value={documentKind} onChange={e=>setDocumentKind(e.target.value)}><option value="all">All types</option><option value="cv">CVs</option><option value="cover-letter">Cover letters</option></select><input type="date" aria-label="Created on or after" value={documentDate} onChange={e=>setDocumentDate(e.target.value)}/></div>
          <div className="panel table-panel"><table><thead><tr><th>Document</th><th>Opportunity</th><th>State</th><th>Created</th><th><span className="sr-only">Actions</span></th></tr></thead><tbody>{(boot?.artifacts || []).filter(a => [a.company,a.role,a.filename].join(' ').toLowerCase().includes(filter.toLowerCase()) && (documentState==='all'||a.state===documentState) && (documentKind==='all'||(documentKind==='cv'?a.kind.startsWith('cv'):a.kind==='cover-letter')) && (!documentDate || a.created_at?.slice(0,10)>=documentDate)).map(a=><tr key={a.id}><td><button className="document-name" onClick={()=>setPreview(a)}><strong>{a.filename}</strong><small>{title(a.kind)}</small></button></td><td>{a.company || 'Not recorded'}<small>{a.role || 'Role not recorded'}</small></td><td><span className={'pill '+(a.state==='sent'?'green':'')}>{a.state}</span></td><td>{when(a.created_at)}</td><td><button className="icon-button" aria-label={'Preview '+a.filename} onClick={()=>setPreview(a)}><ArrowUpRight size={18}/></button><a className="icon-button" href={'/api/artifacts/'+a.id+'/download'} aria-label={'Download '+a.filename}><Download size={18}/></a></td></tr>)}</tbody></table>{!boot?.artifacts?.length && <div className="empty-small">Your saved documents will appear here.</div>}</div>
          <section className="recent-section"><div className="section-title"><h2>All applications</h2></div><div className="recent-grid">{(boot?.applications||[]).filter(a=>[a.company,a.role].join(' ').toLowerCase().includes(filter.toLowerCase())).map(a=><button className="recent-card" key={a.id} onClick={()=>openApplication(a)}><BriefcaseBusiness size={20}/><div><strong>{a.company||'Company not recorded'}</strong><p>{a.role||'Role not recorded'}</p></div><ArrowUpRight size={16}/></button>)}</div></section>
        </>}
        {page === 'settings' && <>
          <div className="page-heading"><div><p className="eyebrow">BUILT ON YOUR EXPERIENCE</p><h1>Your foundations<span>.</span></h1><p>Existing career facts and generators, connected in one workspace.</p></div></div>
          <div className="settings-grid">
            <section className="panel"><h2>Candidate profile</h2><h3 className="profile-name">{boot?.settings?.name}</h3><p>{boot?.settings?.headline}</p><p className="helper">{boot?.settings?.location}</p><div className="detail-row"><span>Verified profile facts</span><strong>{boot?.settings?.fact_count || 0}</strong></div><div className="detail-row"><span>Saved search profile</span><strong>{boot?.settings?.candidate_ready?'Available':'Not yet extracted'}</strong></div><p className="helper">CVs use curriculum evidence. Letters use the maintained cover-letter profile.</p></section>
            <section className="panel"><h2>Connected capabilities</h2>{[['Semantic CV matching',boot?.settings?.cv_match_ai_ready,boot?.settings?.cv_match_model],['CV copying',true,'Offline'],['AI CV tailoring',boot?.settings?.cv_ai_ready,boot?.settings?.cv_model],['AI cover letters',boot?.settings?.letter_ai_ready,boot?.settings?.letter_model],['AI search ranking',boot?.settings?.search_ai_ready,boot?.settings?.search_model],['PDF compilation',boot?.settings?.compiler_ready,'LaTeX']].map(([label,ok,detail])=><div className="detail-row" key={label}><div><strong>{label}</strong><small>{detail}</small></div><span className={'pill '+(ok?'green':'')}>{ok?'Ready':'Needs setup'}</span></div>)}</section>
            <section className="panel"><h2>CV collection</h2>{(boot?.families||[]).map(f=><div className="detail-row" key={f.key}><div><strong>{f.label}</strong><small>{f.pdf_exists ? 'PDF available' : 'Build required'}{f.stale?' · Source changed since build':''}</small></div>{f.pdf_exists&&<a className="text-button" href={'/api/families/'+f.key+'/pdf'} target="_blank" rel="noreferrer">Preview<ArrowUpRight size={14}/></a>}</div>)}</section>
            <section className="panel"><h2>Storage & continuity</h2><p>SQLite owns application tracking. The Excel source remains unchanged.</p><div className="detail-row"><span>Saved PDF destination</span><code>sent/</code></div><div className="detail-row"><span>Applications</span><strong>{boot?.applications?.length || 0}</strong></div><div className="detail-row"><span>Interview reference</span><span className="pill green">Unchanged</span></div><div className="button-row"><button className="button secondary" disabled={pending} onClick={()=>action(async()=>{await post('/refresh',{});await refresh();setNotice('Existing applications and files refreshed.');})}><RefreshCw size={16}/>Refresh collections</button><button className="button secondary" disabled={pending} onClick={()=>inspectImport(false)}>Preview Excel import</button><button className="button primary" disabled={pending} onClick={()=>inspectImport(true)}>Import Excel tracker</button></div>{importReport&&<div className="import-report"><strong>{importReport.total} rows</strong><span>{importReport.summary ? `${importReport.summary.create || 0} new · ${importReport.summary.link || 0} links` : `${importReport.created || 0} created · ${importReport.linked || 0} linked`}</span><small>{importReport.review_count ?? ((importReport.summary?.missing_role || 0)+(importReport.summary?.missing_url || 0))} fields need review{importReport.already_imported?' · already imported':''}</small></div>}</section>
          </div>
          <TaskList tasks={tasks.slice(0,20)} retry={t=>action(async()=>{await post('/tasks/'+t.id+'/retry',{request_id:crypto.randomUUID()});await refresh();})}/>
        </>}
        <footer>Career Workspace <span>Made for your next chapter.</span></footer>
      </div>
    </main>
    {preview && <div className="modal-backdrop" onClick={()=>setPreview(null)}><section className="preview-modal" role="dialog" aria-modal="true" aria-label="Document preview" onClick={e=>e.stopPropagation()}><div className="preview-heading"><div><h2>{preview.filename}</h2><p>{preview.company} · {title(preview.kind)} · {preview.state}</p></div><button className="icon-button close" aria-label="Close preview" onClick={()=>setPreview(null)}>×</button></div><iframe title={preview.filename} src={'/api/artifacts/'+preview.id+'/download?inline=true'}/><div className="preview-actions"><span className="helper">{preview.state==='sent'?'A permanent copy is saved in sent.':'Preview the document before saving your final version.'}</span><a className="button secondary" href={'/api/artifacts/'+preview.id+'/download'}><Download size={16}/>Download PDF</a>{preview.state==='draft'&&<button className="button primary" disabled={pending} onClick={()=>action(async()=>{const saved=await post('/artifacts/'+preview.id+'/save',{});setPreview(saved);setNotice('A permanent PDF copy was saved to sent.');await refresh();})}><FolderOpen size={16}/>Save to sent</button>}</div></section></div>}
  </div>;
}

function TaskList({tasks, retry}) {
  return <section className="task-list" aria-live="polite">{tasks.map(t=><div className={'task '+(t.status==='failed'?'task-error':'')} key={t.id}>{['queued','running'].includes(t.status)?<LoaderCircle size={16} className="spin"/>:t.status==='completed'?<Check size={16}/>:<CircleAlert size={16}/>}<div><strong>{title(t.kind)} · {t.status}</strong><p>{t.error || t.message || when(t.created_at)}</p>{t.result?.warnings?.map((w,i)=><small key={i}>{w}</small>)}</div>{['failed','interrupted'].includes(t.status)&&<button className="button small secondary" onClick={()=>retry(t)}>Retry</button>}</div>)}</section>;
}
createRoot(document.getElementById('root')).render(<App/>);
