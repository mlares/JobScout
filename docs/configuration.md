# Configuration

[Setup](setup.md) · [Usage](usage.md) · [Troubleshooting](troubleshooting.md)

All commands run from the repository root. This guide describes the current
implementation, including configuration limitations; it does not imply those
limitations have been fixed.

## Choose a workspace

The backend selects one manifest at startup:

| Launch mode | Manifest | Profile and CV inputs | Default runtime database |
|---|---|---|---|
| `make run-demo` or `CAREER_DEMO=1 make run` | `workspace.demo.json` | `private_example/` | `.demo_runtime/career-app/data/career.sqlite3` |
| `make run`, with `CAREER_DEMO` unset | `workspace.json` | As configured, normally `private/` | `private/career-app/data/career.sqlite3` |

`CAREER_DATA_DIR` overrides the database and task directory in either mode. Use
an absolute path inside the workspace's ignored private area if you deliberately
set it; file-management operations enforce workspace containment. For demos,
use `env -u CAREER_DATA_DIR make run-demo` to avoid an inherited override.

## Create a personal workspace

For a new installation, initialize missing files without replacing existing ones:

```bash
if [ ! -e workspace.json ]; then
  cp workspace.example.json workspace.json
fi
mkdir -p private/secrets
if [ ! -e private/profile.json ]; then
  cp private_example/profile.json private/profile.json
fi
if [ ! -e private/curriculum ]; then
  cp -R private_example/curriculum private/curriculum
fi
```

If you already have personal files, keep them and review their paths instead.
The copied inputs still describe a fictional candidate: replace all invented
facts and rebuild the PDFs before using them for real applications.

The default layout is:

```text
workspace.json
private/
├── profile.json
├── curriculum/
│   ├── cv/short/
│   ├── content/shared/
│   ├── evidence/
│   └── dist/short/
├── secrets/
│   ├── career-app.env
│   ├── cover-letter.env
│   └── job-scout.env
├── applications/
├── sent/
├── career-app/data/
└── job-scout/
```

Some directories are created when their features are used. There is no need to
create an empty tracker or application-index file merely to start the app.

### Manifest fields

Use [`workspace.example.json`](../workspace.example.json) as the complete template.
Relative manifest paths are resolved against the repository root.

| Field | Purpose |
|---|---|
| `private_root` | Base for the default database/task directory and Job Scout state |
| `paths.profile` | Structured cover-letter profile and displayed candidate identity |
| `paths.curriculum` | CV sources, shared content, evidence, and prebuilt PDFs |
| `paths.applications` | Application folders and preparation metadata |
| `paths.application_index` | Optional existing application collection index |
| `paths.sent` | Saved document copies |
| `paths.tracker` | Optional Excel tracker to import |
| `secrets.career_app` | Semantic CV-matching configuration |
| `secrets.cover_letter` | Cover-letter credentials and model |
| `secrets.job_scout` | Job discovery, ranking, and CV-tailoring configuration |
| `components` | Component locations and excluded interview-reference path |

Changing `private_root` does not rewrite other paths in the manifest. Keep the
explicit paths consistent. The `runtime.data_dir` and `runtime.bind_host` entries
are currently descriptive, not authoritative: the backend defaults to
`<private_root>/career-app/data`, and `run.sh` binds to `127.0.0.1`.
`CAREER_PORT` controls the launch port. Do not rely on `CAREER_PRIVATE_ROOT` to
reconfigure the main application; edit the manifest.

## Prepare the candidate profile

Edit `private/profile.json`. Its structure includes:

```json
{
  "name": "John Doe",
  "location": "Rosario, Argentina",
  "headline": "Fictional machine learning engineer",
  "links": [
    {"label": "Portfolio assistant", "url": "https://example.com/john-doe-assistant"}
  ],
  "facts": [
    {"category": "work", "statement": "Built a fictional document-classification prototype."}
  ],
  "preferences": {"target_words": 300}
}
```

This example is not a real candidate record. Supply your own verified facts.
A nonempty `name` and nonempty `facts` list are required; each fact needs a
string `statement`. The cover-letter CLI accepts target lengths from 180 to 700
words. Keep dates, titles, employers, and metrics consistent with your CVs.

The cover-letter PDF renderer currently requires a link whose label contains
`assistant` or `chat`, because it creates a QR code. Without such a real link,
use text-only generation; removing the PDF requirement needs a code change.

## Prepare the CV family and LaTeX

The six family keys and source filenames are currently fixed:

| Family | Source under `curriculum/cv/short/` |
|---|---|
| `senior-data-science` | `senior-data-science/CV_senior_data_science.tex` |
| `ml-engineering` | `ml-engineering/CV_ml_engineering.tex` |
| `applied-ai-llm` | `applied-ai-llm/CV_applied_ai_llm.tex` |
| `technical-leadership` | `technical-leadership/CV_technical_leadership.tex` |
| `analytics-decision-science` | `analytics-decision-science/CV_analytics_decision_science.tex` |
| `research-scientific-ml` | `research-scientific-ml/CV_research_scientific_ml.tex` |

Preserve this layout. For example, ML engineering's PDF belongs at
`private/curriculum/dist/short/ml-engineering/CV_ml_engineering.pdf`.

Edit the shared identity/formatting, experience, education, and evidence under
`content/shared/` and `evidence/`, as well as each family-specific source. Remove
every fictional claim, not just the name. Editing `.tex` does not refresh PDFs.
The app does not provide a general DOCX/template-import workflow or a configurable
family catalog.

LaTeX is optional for trying the prebuilt demo and unnecessary for cover-letter
PDF rendering. Maintaining or tailoring this CV source format requires LaTeX.
The example uses `pdflatex`, `moderncv`, and `tcolorbox`, plus their dependencies
and fonts. Check your installation:

```bash
pdflatex --version
kpsewhich moderncv.cls
kpsewhich tcolorbox.sty
bash --version
```

Use Bash 4 or newer. Build a trusted personal source:

```bash
CV_REPOSITORY_PATH=private/curriculum \
  bash packages/cv-engine/build_cv.sh ml-engineering
```

To rebuild all six short families:

```bash
for family in \
  senior-data-science \
  ml-engineering \
  applied-ai-llm \
  technical-leadership \
  analytics-decision-science \
  research-scientific-ml
do
  CV_REPOSITORY_PATH=private/curriculum \
    bash packages/cv-engine/build_cv.sh "$family"
done
```

Do not use `build_cv.sh all` with just the example collection: it also expects
long academic and industry CV sources. Inspect every rebuilt PDF.

Building trusted sources is different from compiling model-generated code. The
current LaTeX checks are not a sandbox. Leave AI-generated CV compilation unused
on machines with sensitive data until filesystem and process isolation are
implemented; see [Security](../SECURITY.md).

## Configure optional provider credentials

Create the files with a local editor; do not paste actual keys into shell commands,
public examples, screenshots, or logs. Restrict secrets-file permissions to your
account. `.gitignore` prevents routine Git inclusion; it does not encrypt files.

For personal mode the paths are `private/secrets/`. For deliberately enabling
providers in demo mode, use the same filenames under `.demo_runtime/secrets/`.
Never put secrets under `private_example/`.

All `...` and model-name values below are placeholders, not usable credentials.
Replace them before enabling a feature. Presence indicators are not credential
validation, and model availability depends on your provider account.

### Semantic CV matching

In `career-app.env`:

```dotenv
TYPESAFE_API_KEY=...
```

Optionally set `TYPESAFE_MODEL` to override the model selected in the code.
Install Poppler's `pdftotext` and check `pdftotext -v`. Choose **JEV** in the app
to score extracted CV text against the job description. This sends those texts
to TypeSafe. **Keywords** uses local family-scoring rules instead.

### Cover letters

In `cover-letter.env`:

```dotenv
OPENAI_API_KEY=...
COVER_LETTER_MODEL=your-supported-model-id
```

Drafting sends the profile and job description to the configured model. PDF
rendering uses ReportLab and does not require LaTeX.

### Job Scout and CV tailoring

In `job-scout.env`:

```dotenv
OPENAI_API_KEY=...
SCOUT_MODEL=openai:your-supported-model-id
OPENAI_MODEL=your-supported-model-id
OPIK_ENABLED=false
```

`SCOUT_MODEL` controls Job Scout extraction/ranking; `OPENAI_MODEL` controls the
main CV-tailoring engine. They are separate from `COVER_LETTER_MODEL`.
Configuring a key does not resolve the LaTeX compilation risk.

Optional job-source credentials also belong in `job-scout.env`:

```dotenv
JSEARCH_API_KEY=...
ADZUNA_APP_ID=...
ADZUNA_APP_KEY=...
```

Ordinary search can use keyless sources without these. AI job ranking additionally
needs a [saved Job Scout candidate](usage.md#optional-ai-job-ranking).

### Configuration precedence

There is not yet one consistent precedence rule across every component:

- The main app's readiness display and semantic matching merge the relevant
  manifest secrets file with process environment variables; process values win.
- The generation/search worker starts with the process environment, then applies
  `job-scout.env`, then `cover-letter.env`. Duplicate values from the latter win.
  It sets its own CV-repository and Job Scout data paths from the active workspace.
- Job Scout settings can additionally read `integrations/job-scout/.env` and a
  working-directory `.env`. Do not assume clearing a shell key makes it keyless.
- The standalone cover-letter CLI reads `CAREER_COVER_LETTER_ENV`, or its package
  `.env` by default; it does not select secrets through `workspace.json`.

Use the manifest-designated files for the main app, avoid conflicting exported
variables, and do not assume separate OpenAI credentials remain isolated between
engines. If both engine files define `OPENAI_API_KEY`, keep them consistent for
this version. A root `.env` alone does not reliably configure the whole app.
Restart after changing configuration.

The main app disables Opik tracing for its search path. Standalone Job Scout can
enable tracing separately; inspect what it records before using personal data.
Keep `OPIK_ENABLED=false` when following the standalone instructions here.
