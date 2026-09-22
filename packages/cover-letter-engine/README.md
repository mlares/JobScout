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
