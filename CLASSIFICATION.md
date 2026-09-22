# Source classification

Classification completed 2026-09-21 against the private source workspace. This
ledger is an allowlist guide: a resource is not eligible for the shareable
repository merely because it is not named here.

| Current resource | Classification | Destination / decision | Rationale |
| --- | --- | --- | --- |
| `tools/career-app` source | Shareable after review | `apps/career-app/` | Generic local application UI/API, but remove identity metadata, home paths, local history files, and all runtime data. |
| `tools/career-app/data/`, `.env`, `.venv`, `node_modules/` | Private/generated | local ignored paths | SQLite records, task inputs, CV text cache, keys, and installed dependencies must never enter Git. |
| `tools/cover-letters/src/` | Shareable after review | `packages/cover-letter-engine/` | Generic generator code. |
| Cover-letter candidate profile, assets, examples, output | Private or replace | `private/profile.json`; synthetic `examples/` | Candidate facts, branded assets, postings, and generated letters are personal. The tracked profile must be removed from any public history. |
| `tools/observable-job-agent` | Third-party fork/dependency | `integrations/job-scout/` | Upstream is MIT. Preserve copyright/license notices and isolate personal modifications for review. |
| `tools/observable-job-agent/.env`, `data/candidate/`, caches, output, `.venv` | Private/generated | local ignored paths | Credentials, candidate data, cached postings, artifacts, and dependencies. |
| `curriculum` | Private candidate content | external `private/curriculum/` | CV sources, evidence, photos, publications, and tailored variants identify the candidate. Extract only generic build code later. |
| `applications/`, `sent/` | Private operational data | external `private/applications/`, `private/sent/` | Tracker, job descriptions, contacts, notes, and submitted documents. |
| `resources/` | Mostly private assets | external `private/resources/` | Certificates, media, agreements, research and report assets; review individual generic templates only. |
| `preparation/interviews` | External reference | documented dependency; do not vendor by default | Separate third-party/rehearsal repository with its own history and environment. |
| `preparation/practice`, `assessments` | Private | external `private/preparation/` | Personal notes and employer exercises. |
| Public-site repository | Separate public site | remain separate | A public-facing identity site is not part of a reusable career-tool product. |
| `archive/` | Private historical archive | retain outside template | Contains migration history and prior private documents; never publish. |
| root docs and `workspace.json` | Rewrite as generic docs/config | root + `workspace.example.json` | Existing files reveal names, paths, employer history, and personal resource locations. |

## Completed migration controls

- Candidate profiles, application records, runtime data, and generated output
  are excluded through the ignored `private/` boundary.
- Migrated components resolve paths through `workspace.json` and environment
  variables rather than machine-specific absolute paths.
- All Python components target Python 3.12 and share one locked environment.
- Job Scout's upstream URL, revision, MIT license, and local modifications are
  recorded in `NOTICE` and `docs/upstream.md`.
- The root project is MIT licensed and CI runs tests, linting, a frontend build,
  and the public-tree privacy gate.
