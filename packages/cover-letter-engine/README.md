# Cover-letter engine

Generates a role-specific letter from a structured candidate profile and a job description. Prompt construction constrains the model to supplied facts, and output can be rendered as text or a designed PDF.

The real profile is an ignored runtime input. A safe dry-run is available from the repository root with `make demo`.

Direct CLI usage:

```bash
uv run cover-letter generate \
  --profile examples/fictional-profile.json \
  --job examples/fictional-job-description.txt \
  --company "Northstar Transit Labs" \
  --role "Applied AI Engineer" \
  --dry-run
```

For personal use, see [provider configuration](../../docs/configuration.md#cover-letters)
and the [CLI guide](../../docs/usage.md#cover-letter-command-line). The standalone
CLI needs an explicit `--profile` and, when using the workspace's secrets file,
`CAREER_COVER_LETTER_ENV=private/secrets/cover-letter.env`. It does not select them
through `workspace.json`. PDF output needs a real assistant/chat URL in the
profile for its QR code, but does not require LaTeX.
