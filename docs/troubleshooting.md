# Troubleshooting and known limitations

[Setup](setup.md) · [Configuration](configuration.md) · [Usage](usage.md)

These notes describe the current version, not completed fixes. Run commands from
the repository root and do not post real credentials, CVs, prompts, or database
contents in public bug reports.

## Common startup and feature problems

| Symptom | Check or action |
|---|---|
| Missing Python environment | Run `make setup`; the launcher expects `.venv/bin/python`. |
| Python version rejected | Use Python 3.12; the workspace excludes 3.13 and later. |
| Frontend dependency engine error | On Node 22, use version 22.12 or newer. |
| “Build the interface first” | Run `make build`. |
| Missing `workspace.json` | Use `make run-demo`, or initialize personal configuration. |
| Missing profile or CV source | Review manifest paths and retain all six expected family sources. |
| Port already in use | Stop the previous server or set `CAREER_PORT` to a different local port. |
| Frontend dev server cannot reach API | Its proxy expects the backend on port 8765. |
| Demo shows unexpected records | Check `CAREER_DATA_DIR` and persisted `.demo_runtime/` state. |
| JEV unavailable or falls back to keywords | Check the TypeSafe key, `pdftotext`, and all six usable PDF previews. |
| AI ranking unavailable | Configure both a provider key and the separate saved Job Scout candidate. |
| Model call fails despite a ready indicator | Presence is not validation; check key validity, model access, quota, connectivity, and conflicting settings. |
| LaTeX cannot find class/package | Install `moderncv`, `tcolorbox`, and their dependencies; check with `kpsewhich`. |
| Build script rejects array declarations | Use Bash 4+ rather than an older system Bash or `sh`. |
| `build_cv.sh all` reports missing long sources | Build the six short family keys; the example lacks long CVs. |
| Edited CV still previews old content | Rebuild its PDF; source changes do not regenerate it automatically. |
| Cover-letter PDF complains about a URL | Supply the required real assistant/chat link, or use text-only generation. |
| Search returns no jobs | Review filters, network/source availability, and credentials for keyed sources. No cache ships by default. |
| Excel import cannot find a sheet | The expected worksheet is named `apply`; arbitrary tracker formats need adaptation. |

Restart the backend after configuration changes. If a worker reports that another
instance owns the workspace, stop that instance cleanly; do not delete an active
database or worker lock to force startup.

## CV-reader test fixtures

The four CV-reader PDFs are synthetic and committed under
`integrations/job-scout/data/fixture_cvs/`. They are covered by the public-tree
PDF allowlist and are the only PDFs allowed in that fixture directory. Fresh
checkouts and CI get them directly; no setup step is needed. If a local checkout
is missing one, restore the reviewed version from Git. To intentionally regenerate
all four after editing their source generator, run:

```bash
uv run --all-packages python integrations/job-scout/scripts/generate_fixture_cvs.py
```

Review text, metadata, and changes before committing generated fixture PDFs. Do
not replace them with real candidate documents.

## Demo mode is not a sandbox

`CAREER_DEMO=1` selects `workspace.demo.json`; it does not discard all environment
variables or block outgoing traffic. `CAREER_DATA_DIR` still overrides storage.
Launch with:

```bash
env -u CAREER_DATA_DIR make run-demo
```

This only removes that storage override for the child command. Previously created
demo records remain, and provider credentials may come from the shell, demo
secrets, or Job Scout dotenv files. For public screenshots use a fresh, secret-free
checkout and verify the displayed candidate and records before capturing them.

## Model-generated LaTeX is not securely isolated

The validator recognizes particular include syntax and prohibited command strings.
It does not implement a TeX parser or an operating-system sandbox. A review
confirmed that a harmless file outside the CV directory could be included in a
compiled PDF despite passing validation.

Copying prebuilt PDFs avoids compilation. Compile only trusted sources on a
machine with personal data. Do not rely on the validation checks to make
model-generated LaTeX safe; secure filesystem/process isolation is still needed.
Likewise, claim checks do not establish that every generated statement is true.

## Local storage does not mean offline AI

Semantic matching sends CV text and the posting to TypeSafe. Cover-letter drafting
and AI CV tailoring send relevant profile/evidence and job content to model
providers. Job Scout extraction/ranking also uses provider calls when enabled.
Standalone tracing can record content externally. Review configuration and data
handling before sending sensitive material.

Job search attempts live sources even when a fallback cache exists. The main app
does not currently expose a strict offline-search switch.

## Publication checks have limits

The main application is unauthenticated and intended for one local user. Artifact
IDs identify stored documents; they are not per-user authorization. Do not expose
the app to the internet as a shared service.

`make check-public` is a narrow guardrail. It does not scan all credential formats,
Git history, or the contents of all binary formats. Review staged files and use
dedicated secret scanning before publishing. See [Security](../SECURITY.md) for
reporting and credential-exposure handling.
