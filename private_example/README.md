# Fictional local demo data

All names, employers, projects, dates, and outcomes in this folder are invented.
The six CVs describe one fictional candidate, John Doe. The example LaTeX
sources and their prebuilt PDFs may be published; real candidate material must
remain in the ignored `private/` directory or outside this repository.

## One candidate, six views

John's common history is a BSc in Computer Science (2017), an independent
university project (2017-2018), a Data Scientist role at Meridian Analytics
(2018-2022), and an ML Engineer role at Northstar Transit Labs (2022-present).
Employers, actual job titles, dates, education, and outcomes stay the same.
Only positioning and the selection of project evidence change:

| Family key | Focus of the same candidate's experience |
|---|---|
| `senior-data-science` | Forecasting, experiment analysis, and model evaluation |
| `ml-engineering` | Monitored classification services and reproducible evaluation |
| `analytics-decision-science` | Dashboards, operational interpretation, and reviewable decisions |
| `applied-ai-llm` | Retrieval, source citations, and an assistant evaluation set |
| `technical-leadership` | Working-group coordination and junior-analyst mentoring |
| `research-scientific-ml` | Image-classification uncertainty and reproducible internal research |

Family keys are stable application-routing labels, not claims of seniority,
formal management, LLM specialization, or research credentials. The headlines
reflect the narrower evidence actually available. The 35% reduction refers only
to manual triage time in a fictional internal pilot; no baseline, sample size,
or measurement period is supplied.

The CV engine reads `curriculum/evidence/` and shared LaTeX; the cover-letter
engine reads `profile.json`. Update these together when changing fictional facts.
Regression tests check shared identity/history, common skill evidence, approved
numbers, and the distributed PDF text and metadata. They do not prove the truth
of arbitrary prose or replace editorial review.

## Run the demo

To try the app from a fresh clone without credentials or a LaTeX installation:

```bash
make setup
make build
env -u CAREER_DATA_DIR make run-demo
```

Open <http://127.0.0.1:8765>, paste the fictional posting from
`examples/fictional-job-description.txt`, and compare or copy the CV families.
With the default demo configuration, application records and generated files go
to ignored `.demo_runtime/`, and `workspace.json` is not replaced. The command
above clears an inherited `CAREER_DATA_DIR` override; without it, another database
can be opened. The flag does not disable provider credentials or network access.
Search attempts live sources, and no offline cache is included. AI generation
needs your own provider key. Existing PDF previews and keyword matching need
neither credentials nor LaTeX. `make demo` is a separate prompt-only example.

Read the [setup guide](../docs/setup.md) and [configuration guide](../docs/configuration.md)
before using personal data or enabling providers.

The source files under `curriculum/cv/short/` use a compact blue `moderncv`
layout inspired by the private CV template. The photo and QR header are omitted,
and every contact detail, employer, and accomplishment is fictional.
Rebuilding a CV requires `pdflatex`, Bash 4+, and the `moderncv` and `tcolorbox`
LaTeX packages and their dependencies; using the prebuilt previews does not.
Rebuild one trusted example family with:

```bash
CV_REPOSITORY_PATH=private_example/curriculum bash packages/cv-engine/build_cv.sh ml-engineering
```

This demo is a published input fixture. Do not replace its files with personal
CVs, credentials, or generated submissions.

Model-generated LaTeX compilation is not securely sandboxed. See the
[security limitations](../SECURITY.md) before enabling tailoring.
