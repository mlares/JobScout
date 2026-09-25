# Running and using Career Workspace

[Setup](setup.md) · [Configuration](configuration.md) · [Troubleshooting](troubleshooting.md)

Run commands from the repository root. Complete installation and the frontend
build first. Provider-backed actions can send personal content off the machine
and incur charges; prebuilt-PDF copying and keyword matching do not need them.

## Start and stop

Fictional demo, clearing any inherited database override:

```bash
env -u CAREER_DATA_DIR make run-demo
```

Personal mode, after preparing `workspace.json` and your data:

```bash
env -u CAREER_DEMO make run
```

Open <http://127.0.0.1:8765>. Stop with **Ctrl+C**. Data persists across restarts.
For personal mode, review any deliberately configured `CAREER_DATA_DIR` before
launching; the command above leaves it in place.

To change the personal app's port:

```bash
env -u CAREER_DEMO CAREER_PORT=8877 make run
```

Open <http://127.0.0.1:8877>. These launch commands stay bound to localhost. Do not
expose the main API through a public tunnel or reverse proxy: it has no user
authentication or per-user authorization.

## Check the active profile

Open **Profile & settings**. Confirm the intended candidate name, available CV
PDFs, and configured capabilities. In the demo, all six CVs should show John Doe.
For personal use, verify that no fictional claims remain.

Readiness indicators generally check configuration presence. They do not prove
that a key is valid, a model is accessible, or every compiler dependency exists.

## Prepare and track an application

1. Search in **Search opportunities**, or paste a posting in **Prepare application**.
2. Enter the company, role, and job description, and save the application.
3. Choose **Keywords** or, when configured, **JEV**, then **Find my best CV**.
4. Select a family yourself if the match is weak; preview its existing PDF.
5. Copy the selected CV unchanged. Only rebuild sources you trust. AI-generated
   LaTeX compilation has the [documented security limitation](../SECURITY.md).
6. Optionally generate a cover-letter draft, edit it, and render its PDF.
7. Review every claim and the rendered layout before saving documents.
8. Submit the application yourself, then update its status, stage, events, and
   follow-up reminders in **Applications** and **Dashboard**.

**Sent & documents** is the local document library. Saving to “sent” does not
email a recruiter or submit an application. The app never submits automatically.
Validation catches particular problems; it does not certify factual accuracy.

## Search and cache behavior

Ordinary search does not require an AI key. Some job sources are keyless; others
need credentials. Source availability, filters, and connectivity affect results.

No offline job cache is distributed. If you supply a compatible `cached_jobs.json`,
the main app looks under `private/job-scout/` in the default personal workspace,
or `.demo_runtime/job-scout/` in the demo. A cache is a fallback: live sources are
still attempted first. It is not a network-disable option. Treat cached listings
as potentially stale and verify them at their original source.

## Optional AI job ranking

The cover-letter profile and the Job Scout candidate are different inputs:

- `private/profile.json` holds curated facts used for cover letters.
- `private/job-scout/candidate/profile.json` holds Job Scout's extracted profile,
  CV text, and preferences.

AI ranking requires the latter plus a supported provider key. To initialize it
with the standalone wizard, first configure `private/secrets/job-scout.env` as
described in [Configuration](configuration.md#job-scout-and-cv-tailoring), including
`OPIK_ENABLED=false`. Then run:

```bash
JOB_SCOUT_DATA_DIR="$PWD/private/job-scout" \
GRADIO_TEMP_DIR="$PWD/private/job-scout/gradio-tmp" \
OPIK_ENABLED=false \
uv run --all-packages \
  --env-file private/secrets/job-scout.env \
  python -m job_scout.app
```

Open <http://127.0.0.1:7860>, upload your CV, and review the extracted profile.
Extraction makes a model call and sends CV content to the configured provider.
The wizard persists the candidate in the configured Job Scout directory.
Refresh Career App, or restart it, to check AI-ranking readiness.

This advanced command is for the default personal layout, not the fictional
demo. Adapt its paths deliberately for another workspace. It also launches a
download API on port 8000; keep both services local. Stop the wizard with Ctrl+C.
You do not need it for ordinary search, keyword matching, or application tracking.

## Optional Excel tracker import

Put the source workbook at `paths.tracker` in your manifest, normally
`private/applications/JobSearch.xlsx`.

The current importer expects the project's specific format: a worksheet named
`apply`, with headers such as `company`, `role`, `post`, `status`, and
`application date`. It is not a universal spreadsheet importer.

In **Profile & settings**, choose **Preview Excel import** and inspect the proposed
records and review flags. Then use **Import Excel tracker** if the mapping is
correct. Tracking is imported into SQLite; the source workbook is not modified.

## Cover-letter command line

To inspect the fictional prompt without a model call:

```bash
make demo
```

For a personal draft, first create a UTF-8 posting file at
`private/job-description.txt` and configure your profile and provider. The
following command makes a paid provider call and writes a local text draft:

```bash
CAREER_COVER_LETTER_ENV=private/secrets/cover-letter.env \
uv run --all-packages cover-letter generate \
  --profile private/profile.json \
  --job private/job-description.txt \
  --company "Target company" \
  --role "Target role" \
  --output private/drafts/cover-letter.txt
```

Replace the company and role with the actual posting's metadata. Existing output
files at the chosen path are overwritten; choose a fresh filename to keep older
drafts. Adding `--dry-run` prints the prompt instead and makes no model call, but
that prompt contains your personal profile: do not publish its terminal output.

A `.pdf` output suffix generates a PDF and requires the profile's assistant/chat
link. The CLI generates again on each non-dry-run invocation; changing the suffix
is not a conversion of an already reviewed draft. Use the app to edit a draft and
render that reviewed text.

## Development servers

For frontend editing, start the demo backend in one terminal:

```bash
env -u CAREER_DATA_DIR make run-demo
```

In another terminal, from the same repository root:

```bash
npm run dev --prefix apps/career-app
```

Open <http://127.0.0.1:5173>. The Vite API proxy points to port 8765. If you change
the backend port, update `apps/career-app/vite.config.js` accordingly.

For backend auto-reload, use this command instead of `make run-demo`:

```bash
env -u CAREER_DATA_DIR \
  CAREER_DEMO=1 CAREER_WORKSPACE_ROOT="$PWD" \
  .venv/bin/python -m uvicorn backend.app:app \
  --app-dir apps/career-app --host 127.0.0.1 --port 8765 --reload
```

Do not run both backends against the same port/database. Outside the development
server, frontend edits need `make build`; the regular backend serves `dist/`.

## Maintenance and publication checks

Use `make help` for the command list. After pulling dependency changes, run
`make setup` and rebuild. Before publishing:

```bash
uv run --all-packages python integrations/job-scout/scripts/generate_fixture_cvs.py
make check
git status --short
git diff --check
```

`make check-public` can also be run separately. It checks tracked and unignored
files for selected patterns and paths, not all secret types or Git history.
Use a dedicated secret scanner as an additional release check. Never force-add
ignored personal files, secrets, databases, or unreviewed generated documents.

Stop the app before making a filesystem backup of `private/` and `workspace.json`.
If you customized paths, include those locations too. Keep backups access-restricted
and encrypted as appropriate; Git ignore rules are not data protection. Demo
records under `.demo_runtime/` are separate and also persist until deliberately
removed. This guide does not require deleting or resetting existing data.
