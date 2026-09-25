---
name: career-workspace
description: "Develop, configure, test, document, or review the Career Workspace repository and its fictional demo. Use for this project's local Career App, CV/cover-letter engines, Job Scout integration, and publication-readiness reviews; not general job-search advice."
---

# Career Workspace

Work on the requested part of Career Workspace while keeping public fixtures,
personal candidate data, and provider-backed operations separate. Do not expand a
review or explanation into implementation, deployment, credential rotation, or
publication without the corresponding user request.

## Locate the project and choose context

Identify the repository from the current directory or a user-supplied path. Verify
`workspace.example.json`, `apps/career-app/`, `packages/cv-engine/`, and
`integrations/job-scout/` before acting. If the repository is unavailable, ask for
its location; do not search unrelated personal directories.

All project paths below are relative to that repository root, not this skill's
installation directory. Treat source code as authoritative when documentation
and implementation disagree. Read only the guides relevant to the task:

| Task | Start with |
|---|---|
| Installation or demo | `docs/setup.md`, `Makefile`, `apps/career-app/run.sh` |
| Personal data or provider configuration | `docs/configuration.md`, `workspace.example.json`, `workspace.demo.json`, `apps/career-app/backend/service.py` |
| Daily workflow, CLI, development servers | `docs/usage.md` and the affected component README |
| Reproduce a failure | `docs/troubleshooting.md` and the affected tests |
| Privacy, security, publishing, LinkedIn draft | `SECURITY.md` and [release-review guidance](references/release-review.md) |

Do not load `private/`, `workspace.json`, secrets files, or existing databases just
to understand the code. Read personal inputs only when the user's task requires
them, and keep them out of public examples and diagnostic output.

## Component boundaries

- `apps/career-app/src/main.jsx`: React workflow. `backend/app.py`: API and local
  request guards. `backend/service.py`: workspace paths, tasks, orchestration.
  `backend/store.py`: SQLite. `backend/bridge.py`: per-task subprocess integration.
  Use `apps/career-app/tests/test_workspace.py` for app regressions.
- `packages/cv-engine/`: six keyword-scored CV families, optional model tailoring,
  and LaTeX builds. Preserve the family source/PDF path contract unless changing
  that contract is the actual task. Keyword matching is not semantic CV analysis.
- `packages/cover-letter-engine/`: structured candidate facts, draft generation,
  and ReportLab PDF rendering. Cover-letter PDFs do not require LaTeX; the current
  renderer requires an assistant/chat link for its QR code.
- `integrations/job-scout/`: discovery, profile extraction, AI ranking, validation,
  and optional tracing/evaluation. Preserve the attribution in `NOTICE`,
  `docs/upstream.md`, and its MIT license when modifying or describing it.

Keep the curated cover-letter profile distinct from Job Scout's saved candidate:
their schemas and consumers differ. Changing one does not initialize the other.

## Data and runtime boundaries

- `private_example/` and `examples/` are public fixtures. Keep a consistent
  fictional identity, currently John Doe, across profile, sources, evidence, PDFs,
  links, and metadata. When borrowing a personal layout, substitute every private
  fact, contact detail, photo, QR target, and identifying metadata; do not merely
  rename the candidate. Do not overwrite the original template.
- `private/`, personal `workspace.json`, and `.demo_runtime/` are ignored runtime
  inputs/state. Build tests and diagnostics from synthetic temporary fixtures,
  not the user's CVs, tracker, saved applications, or live database.
- Demo mode chooses a manifest, not a sandbox. Check the current `CAREER_DATA_DIR`
  precedence and provider environment before running. Prefer a public-only
  temporary checkout for isolation-sensitive testing. `env -u CAREER_DATA_DIR`
  alone does not remove provider keys or secrets-file settings.
- Check readiness and worker configuration separately: their environment merging
  currently differs, and the bridge merges Job Scout and cover-letter secrets.
  Never claim per-engine credential isolation without verifying it.
- Keep local startup on `127.0.0.1`. The main API has no user authentication;
  workspace path checks and artifact UUIDs are not per-user authorization.
- Provider calls can transmit CV/profile/job text and incur charges. Use dry runs,
  explicit keyword matching, and mocked providers unless a live action is within
  the user's request. A ready indicator does not validate a key or model.
- LaTeX compilation of generated text is not securely sandboxed in the reviewed
  version. Do not test a bypass against real sensitive files. Use harmless markers
  and an isolated filesystem when investigating; regex validation is not a TeX
  security boundary. Recheck the implementation before repeating a historical
  finding or claiming it is fixed.

## Verify the requested change

Use focused tests while developing, then verification proportional to the change.
The existing root commands are the source of truth; do not duplicate their logic
or install dependencies merely for a documentation-only task.

- App/engine changes: run the relevant tests and, when feasible, `make check`.
- UI changes: run `make build` and exercise the changed flow with fictional data.
- CV/template changes: compile trusted sources only when relevant; inspect PDF
  rendering and extracted text/metadata. Keep distributed previews consistent.
- Documentation changes: validate local links, shell/JSON examples, and claims
  against current code. Do not execute examples that send data or overwrite files
  just to check their syntax.
- Changes to paths or privacy controls: verify manifest selection in the bridge,
  task output containment, and absence of reads/writes to personal inputs using
  temporary synthetic fixtures.

Before default tests on a fresh checkout, check whether the synthetic CV-reader
PDF fixtures exist. If still absent, generate them with the existing helper:

```bash
uv run --all-packages python integrations/job-scout/scripts/generate_fixture_cvs.py
make check
```

Do not count this manual workaround as proof that unmodified clean-checkout CI
passes. `make check` excludes `integration` and `compile` tests. Report exclusions
and untested live-provider paths; do not freeze a historical passing-test count.

Run `make check-public` and `git diff --check` for public-file edits. The former
checks selected paths and patterns, not all secrets or history. For cache permission
errors, use an allowed task-specific temporary cache directory or request the
required access; do not change unrelated global configuration.

Conclude with the result, relevant file links, verification actually performed,
and remaining limitations. Distinguish documented precautions from implemented
fixes, and local source publication from authenticated public deployment.
