# Career App

The local product shell for the career workflow. A React interface talks to a FastAPI backend that indexes application records, imports the tracker, invokes the job-search and document engines, and records task history in SQLite.

The server binds to `127.0.0.1` by default. Candidate data and runtime state are resolved through the root `workspace.json`; this package does not contain a candidate profile or credentials.

From the repository root:

```bash
make setup
make run
```

Backend tests live in `tests/test_workspace.py`. The frontend production build is part of `make check` and CI.
