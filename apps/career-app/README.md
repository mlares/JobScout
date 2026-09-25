# Career App

The local product shell for the career workflow. A React interface talks to a FastAPI backend that indexes application records, imports the tracker, invokes the job-search and document engines, and records task history in SQLite.

The server binds to `127.0.0.1`. Personal inputs are configured through the root `workspace.json`; `CAREER_DEMO=1` selects `workspace.demo.json`. The main API has no user authentication and is intended for local use only.

To try the fictional John Doe demo from the repository root:

```bash
make setup
make build
env -u CAREER_DATA_DIR make run-demo
```

Open <http://127.0.0.1:8765>. After configuring personal data, use `env -u CAREER_DEMO make run` instead. Check any custom `CAREER_DATA_DIR` before launching personal mode.

See [Setup](../../docs/setup.md), [Configuration](../../docs/configuration.md), [Usage](../../docs/usage.md), and [Troubleshooting](../../docs/troubleshooting.md) for complete instructions, provider configuration, and development servers.

Backend tests live in `tests/test_workspace.py`. The frontend production build is part of `make check` and CI. The full test suite currently needs the documented [synthetic-fixture generation step](../../docs/troubleshooting.md#missing-test-fixtures) on a fresh checkout.
