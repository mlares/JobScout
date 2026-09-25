# Setup and first run

[Configuration](configuration.md) · [Usage](usage.md) · [Troubleshooting](troubleshooting.md)

Start with the fictional John Doe demo, then configure personal data and optional
providers. All commands below run from the repository root, in Bash.

This is a local, single-user application, not a public hosting recipe. The main
API has no user authentication. Keep it bound to localhost and read the
[security limitations](../SECURITY.md) before enabling model-backed features.

## Prerequisites

- Git and Make.
- Python 3.12; the Python projects require `>=3.12,<3.13`.
- `uv` for Python environment and dependency management.
- Node.js 22, version 22.12 or newer within that release line, and npm. The
  frontend lockfile requires at least Node 22.12 on the Node 22 line.

The instructions target Linux/Bash. The backend uses Unix-specific `fcntl`
locking, so native Windows is not supported; use a Linux environment such as
WSL. LaTeX builds also require Bash 4 or newer; macOS's older system Bash may
not support the build script's associative arrays.

Check the tools before installing project dependencies:

```bash
python3 --version
uv --version
node --version
npm --version
make --version
```

Extra software depends on the feature:

| Feature | Credentials | Additional requirement |
|---|---|---|
| Application tracking | None | None |
| Keyword CV-family matching | None | None |
| Preview/copy the included CV PDFs | None | None |
| Live job search | Some sources are keyless | Internet access |
| Semantic CV matching with JEV | TypeSafe key | Poppler's `pdftotext` |
| Generate cover letters | OpenAI key | Internet; no LaTeX |
| Rebuild trusted CV sources | None | LaTeX and Bash 4+ |
| AI CV tailoring | OpenAI key | LaTeX; see the security warning below |

## Install and build

From your existing checkout:

```bash
make setup
make build
```

`make setup` installs locked Python dependencies into `.venv/` and frontend
dependencies into `apps/career-app/node_modules/`. `make build` creates the
frontend under `apps/career-app/dist/`, which the backend serves.

You do not need to activate the virtual environment. Initial installation needs
network access unless all dependencies are already cached.

## Launch the fictional demo

```bash
env -u CAREER_DATA_DIR make run-demo
```

Open <http://127.0.0.1:8765>. You should see John Doe's profile and six CV families
with prebuilt PDF previews. Try the fictional posting in
[`examples/fictional-job-description.txt`](../examples/fictional-job-description.txt).
Select **Keywords** for local matching, then preview or copy a CV.

The flag-based equivalent is:

```bash
env -u CAREER_DATA_DIR CAREER_DEMO=1 make run
```

The prefix clears an inherited database-directory override for this command only.
Without it, `CAREER_DATA_DIR` can make demo mode open a different database.

Demo mode reads `workspace.demo.json`, `private_example/profile.json`, and
`private_example/curriculum/`. With the default configuration, records and
generated files go under ignored `.demo_runtime/`; it does not replace
`workspace.json`. Treat `private_example/` as a public input fixture: never put
personal facts or secrets there.

The demo flag is not a network or credential sandbox. It retains process
credentials, can load demo secrets files, and Job Scout can also read dotenv
files. For a credential-free demonstration, use a fresh checkout without local
secrets, select **Keywords**, and leave AI ranking off. Search still contacts
external sources. See [configuration precedence](configuration.md#configuration-precedence).

Stop the server with **Ctrl+C**. Records remain available on the next launch.
To change the port:

```bash
env -u CAREER_DATA_DIR CAREER_PORT=8877 make run-demo
```

Then open <http://127.0.0.1:8877>.

### Prompt-only demo

```bash
make demo
```

This prints the fictional cover-letter prompt. It does not start a server, call
a model, or produce a finished cover letter.

## Run the checks

Four fictional CV-reader test PDFs are included in the repository at
`integrations/job-scout/data/fixture_cvs/`. A fresh checkout needs no fixture
generation; run the quality gate directly:

```bash
make check
```

If you deliberately update these public synthetic examples, regenerate them with
`uv run --all-packages python integrations/job-scout/scripts/generate_fixture_cvs.py`,
review the PDF contents, and include the resulting changes in your commit.

`make check` runs lint, deterministic tests, the frontend build, and the
public-tree check. Tests marked `integration` or `compile` are excluded, so a
passing result does not validate live credentials or every LaTeX path. See
[troubleshooting](troubleshooting.md) for known limitations.

## Next: personal configuration

Follow [Configuration](configuration.md) to create `workspace.json`, prepare your
profile and CV family, and optionally configure providers. Then use
[Usage](usage.md) for daily operation, development servers, and standalone tools.

Do not enable AI-generated LaTeX compilation on a machine with sensitive files
until it is securely sandboxed. The existing checks are not a filesystem-access
boundary. Copying the supplied PDFs does not compile LaTeX.
