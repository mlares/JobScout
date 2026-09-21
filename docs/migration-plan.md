# Controlled migration plan

1. Select one target Python release after running the Job Scout test suite and
   document-generation smoke test on it. Keep independent package dependency
   groups in the monorepo; a single repository does not require one giant
   dependency set.
2. Migrate Career App source into `apps/career-app/`, replacing absolute paths
   and personal author metadata with neutral package metadata.
3. Extract generic cover-letter code into `packages/cover-letter-engine/` and
   replace the real profile, brand assets, postings, and output with synthetic
   fixtures.
4. Extract only reusable CV tooling into `packages/cv-engine/`; retain candidate
   CV text, evidence, PDFs, photos, and LaTex content under private storage.
5. Import or reference Job Scout only after recording its upstream revision,
   license, notices, and the review of local modifications.
6. Add tests that run exclusively on synthetic fixtures and verify that an
   external private-data root works through configuration.
7. Run secret, personal-data, absolute-path, and license checks before the
   first public commit. Create the public history from this clean scaffold, not
   from an existing private repository history.
