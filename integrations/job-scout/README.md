# Job Scout integration

An observable LangGraph workflow for multi-source job discovery, candidate profile extraction, ranking, and evidence-grounded application preparation. Provider calls are traced with Opik when configured, while fixtures and cached sources keep the core test suite deterministic and keyless.

This integration is adapted from [jamwithai/observable-job-agent](https://github.com/jamwithai/observable-job-agent) at base revision `5839e4f`. Its MIT license is retained in this directory; see the repository [NOTICE](../../NOTICE) and [upstream record](../../docs/upstream.md).

The root Career App is the supported product entry point. To work on Job Scout directly:

```bash
uv run pytest integrations/job-scout/tests -m "not integration and not compile"
uv run ruff check integrations/job-scout
```

The four fictional CV-reader fixture PDFs are committed under
`integrations/job-scout/data/fixture_cvs/`, so tests run from a fresh checkout.
Regenerate them with `uv run --all-packages python integrations/job-scout/scripts/generate_fixture_cvs.py`
only when intentionally changing the examples, and review the resulting PDFs
before committing them. See the workspace
[configuration guide](../../docs/configuration.md#job-scout-and-cv-tailoring) for
provider keys and the [AI-ranking setup](../../docs/usage.md#optional-ai-job-ranking)
for launching the standalone wizard with private candidate storage. The main app
and wizard use a saved Job Scout candidate that is separate from the cover-letter
profile. No offline job cache is included in the public tree.

The phase notebooks and `docs/` explain the tracing and evaluation design.
