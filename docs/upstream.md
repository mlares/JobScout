# Upstream provenance

## Job Scout

- Upstream: <https://github.com/jamwithai/observable-job-agent>
- License: MIT; retained at `integrations/job-scout/LICENSE`
- Imported base revision: `5839e4f`
- Local location: `integrations/job-scout/`

The imported code was adapted for a private-data-safe monorepo and extended with application artifacts, additional provider handling, CV and cover-letter generation, deterministic validation, and evaluation coverage.

When updating from upstream:

1. fetch and review the upstream diff from the recorded base revision;
2. preserve the upstream copyright and MIT license;
3. reapply local privacy and workspace-path boundaries deliberately;
4. run `make check` and the relevant opt-in integration tests;
5. update the revision and local-change summary here and in `NOTICE`.
