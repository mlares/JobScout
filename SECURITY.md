# Security and privacy

Do not report suspected credential or personal-data exposure in a public issue.
Use GitHub's private security-advisory feature for the repository.

Before publishing a branch, run `make check-public`. If sensitive data is ever
committed, removing the working-tree file is not sufficient: rotate exposed
credentials immediately and rewrite or replace the affected Git history before
making the repository public.

The application is designed for local use and binds to `127.0.0.1` by default.
Exposing it to a network requires an explicit authentication, authorization,
TLS, and threat-model review that is outside the current product scope.

## Current runtime limitations

- Model-generated LaTeX is not securely sandboxed. Structural checks and command
  patterns do not prevent all file reads. Compile only trusted sources on machines
  with sensitive files; prefer copying prebuilt PDFs until process/filesystem
  isolation is implemented for generated code.
- Demo mode selects fictional inputs, but retains environment overrides and
  provider configuration. In particular, `CAREER_DATA_DIR` can redirect its
  database. Use `env -u CAREER_DATA_DIR make run-demo` and a secret-free checkout
  for public demonstrations; verify the displayed records before screenshots.
- Local storage does not imply offline processing. AI features send relevant
  profile, CV, evidence, or job content to providers. Standalone Job Scout tracing
  can also record content externally when enabled.
- Main-app artifact IDs are not per-user authorization. Keep the unauthenticated
  API local; task directories are organizational boundaries, not security sandboxes.
- `make check-public` recognizes selected patterns and paths. It does not replace
  full secret scanning, history review, or inspection of binary artifacts.

See [Configuration](docs/configuration.md#configuration-precedence) and
[Troubleshooting](docs/troubleshooting.md) for operational precautions. These
instructions document limitations; they do not fix the underlying implementation.
