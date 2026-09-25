# Contributing

Use Python 3.12 and Node.js 22.12 or newer within Node 22. Run `make setup` once.
The four small, synthetic CV-reader fixture PDFs are committed in
`integrations/job-scout/data/fixture_cvs/`, so a fresh checkout can run the full
default quality gate directly:

```bash
make check
```

Run this command from the repository root before opening a pull request. See
[Setup](docs/setup.md) and [Usage](docs/usage.md#development-servers) for installation
and development-server instructions. Regenerate the fixtures only when
intentionally updating these reviewed examples, using
`uv run --all-packages python integrations/job-scout/scripts/generate_fixture_cvs.py`.

Keep changes within the component boundaries documented in the root README.
Tests and examples must use fictional people, employers, contact details, and
metrics. Never commit a real CV, profile, tracker, job description, application,
credential, database, or generated submission.

Networked tests must carry the `integration` marker; LaTeX-compiler-dependent
tests must carry `compile`. The default quality gate must remain deterministic
and usable without API keys.

Changes derived from Job Scout upstream must update `docs/upstream.md` when the
recorded base revision changes and must preserve its MIT license.
