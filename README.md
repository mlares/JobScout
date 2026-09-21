# Career Workspace Template

Shareable, single-repository foundation for a local job-application workspace.
It contains application software, reusable engines, integration boundaries, and
synthetic examples. It deliberately contains no candidate profile, CV, job
tracker, application documents, credentials, or runtime database.

## Status

The Career App, cover-letter engine, and Job Scout integration source have been
migrated without their environments, credentials, candidate records, or output.
The candidate-specific collections reside under the ignored `private/` boundary.
See [CLASSIFICATION.md](CLASSIFICATION.md) for the reviewed boundary.

## Intended layout

```text
apps/career-app/              Local UI and operational API
packages/cover-letter-engine/ Generic cover-letter generation package
packages/cv-engine/           Generic CV selection, tailoring, and build package
integrations/job-scout/       Adapter or documented upstream dependency boundary
examples/                     Synthetic, safe-to-publish fixtures
private/                      Local-only candidate data; ignored except its README
```

Copy `workspace.example.json` to a local, ignored `workspace.json` and point it
at local private data before running any migrated software. Add secrets only to
local `.env` files derived from `.env.example`.

## Local setup

Use Python 3.12 for every Python component. From the repository root, install
the shared environment with `uv sync --all-packages --all-groups`; install the
Career App frontend with `npm ci --prefix apps/career-app`, then build it with
`npm run build --prefix apps/career-app`. Copy `workspace.example.json` to
`workspace.json`. The private data and secret files are local-only and ignored.

No license has been selected yet. Do not publish or redistribute this repository
until a license is chosen and all imported third-party code has retained its
required notices.
