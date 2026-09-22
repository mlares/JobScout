# Contributing

Use Python 3.12 and Node.js 22. Run `make setup` once, then `make check` before
opening a pull request.

Keep changes within the component boundaries documented in the root README.
Tests and examples must use fictional people, employers, contact details, and
metrics. Never commit a real CV, profile, tracker, job description, application,
credential, database, or generated submission.

Networked tests must carry the `integration` marker; LaTeX-compiler-dependent
tests must carry `compile`. The default quality gate must remain deterministic
and usable without API keys.

Changes derived from Job Scout upstream must update `docs/upstream.md` when the
recorded base revision changes and must preserve its MIT license.
