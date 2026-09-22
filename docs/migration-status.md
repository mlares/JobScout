# Migration status

The controlled migration completed on 2026-09-21.

- Python components use Python 3.12 in one uv workspace and lockfile.
- Career App lives under `apps/career-app/` and resolves private paths through
  the workspace manifest.
- Generic cover-letter and CV tooling lives under `packages/`; candidate facts,
  CV sources, images, and generated documents remain ignored runtime inputs.
- Job Scout lives under `integrations/job-scout/` with its upstream revision,
  license, and local changes documented.
- Tests use synthetic fixtures. A public demo profile and posting live under
  `examples/`.
- CI runs linting, deterministic tests, the frontend build, and a public-tree
  privacy check.

The standalone public portfolio website remains a separate Git repository and
is not part of this product's distributable source.
