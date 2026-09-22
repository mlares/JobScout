# Job Scout integration

An observable LangGraph workflow for multi-source job discovery, candidate profile extraction, ranking, and evidence-grounded application preparation. Provider calls are traced with Opik when configured, while fixtures and cached sources keep the core test suite deterministic and keyless.

This integration is adapted from [jamwithai/observable-job-agent](https://github.com/jamwithai/observable-job-agent) at base revision `5839e4f`. Its MIT license is retained in this directory; see the repository [NOTICE](../../NOTICE) and [upstream record](../../docs/upstream.md).

The root Career App is the supported product entry point. To work on Job Scout directly:

```bash
uv run pytest integrations/job-scout/tests -m "not integration and not compile"
uv run ruff check integrations/job-scout
```

The phase notebooks and `docs/` explain the tracing and evaluation design.
