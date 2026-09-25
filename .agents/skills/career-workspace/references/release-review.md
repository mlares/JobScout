# Publication, credential, and article reviews

Use this reference only for an actual review, security investigation, or publication
task. A normal UI change does not require a full historical security audit.

## Establish the release being assessed

Inspect the current Git status and distinguish committed content from uncommitted
changes. Identify the available history and refs. Review a repository publication
separately from internet-facing deployment: the main local app is not a shared,
authenticated service. Do not publish, push, change repository visibility, rotate
keys, or rewrite history as a side effect of an assessment.

Read `README.md`, `SECURITY.md`, `.gitignore`, `scripts/check_public_tree.py`,
`Makefile`, and the relevant `.github/workflows/` definitions. Consult the source
behind a security claim rather than treating documentation as proof.

## Reproduce the public installation

Verify the files another developer would receive, not only the original working
directory, which may contain ignored dependencies, CVs, and configuration.

- For a committed release, use its tracked tree. For a proposed release containing
  uncommitted changes, identify that scope explicitly. The checker's
  `git ls-files -z --cached --others --exclude-standard` inventory can help; respect
  deletions, submodules, and symlinks rather than following them into private data.
- Use a dedicated temporary copy. Do not copy the entire workspace, `private/`,
  `workspace.json`, `.demo_runtime/`, secrets, `.venv/`, or `node_modules/`. The
  public `private/README.md` is not personal input.
- Attempt the documented dependency installation and test/build commands when
  authorized and feasible. Note cache reuse, unavailable network access, and
  skipped checks. Never use live credentials to make an offline smoke test pass.
- The four small synthetic CV-reader PDF fixtures are committed and explicitly
  allowlisted. Confirm a fresh public snapshot contains exactly those fixtures;
  do not treat local ignored generator output as evidence that checkout CI has them.
- Smoke-test fictional bootstrap, six PDF previews, explicit keyword selection,
  and copy/download when relevant. Check that output stays in the intended
  temporary runtime. Do not silently fall back to the real personal manifest.

## Assess exposure and runtime risk separately

Run the public-tree checker, but explain its scope. For an exposure audit, include
available Git history and relevant ignored-file rules. Use a dedicated local
secret scanner if available, redacting results. Include PDF text/metadata, archive
members, and notebook outputs when those formats are distributed.

Report filenames, locations, and credential types, not secret values. Compare
known local credential values only when necessary for the authorized audit, in
memory and without printing or persisting them. Do not upload personal files or
credentials to an external scanner. A pattern scan with no findings is not a
guarantee that every credential format was examined.

Check the distinction between Git cleanliness and runtime exposure:

- Can demo storage be redirected by environment overrides?
- Are settings/readiness and worker credential precedence consistent?
- Do provider calls or tracing transmit candidate material?
- Are artifact downloads merely workspace-scoped, or actually authorized per user?
- Does generated LaTeX run with access to personal files or credentials?

Demonstrate suspected issues with synthetic inputs and harmless markers only.
Report confirmed behavior separately from hypothetical exploitation. Never
strengthen a denylist into a claim of complete sandboxing or claim verification.

## Review the LinkedIn article

Read `docs/linkedin-article-draft.md` and check its actual feature claims against
the implementation. Preserve the user's voice and distinguish suggestions from
edits; rewrite the draft only when requested.

Check for:

- A clear problem, practical workflow, and accurate local-only status.
- An explicit distinction between local storage and provider-bound data.
- LaTeX being optional for the prebuilt demo but required by the current personal
  CV source/build workflow; cover letters use a different renderer.
- No claim that a cache disables network calls, a UUID authenticates downloads,
  or deterministic checks certify every generated fact.
- Evaluation provenance, dataset size, metric definition, and any conflicting
  results. Report historical experiments as such, not as newly reproduced results
  or checks automatically included in `make check`.
- Accurate tracing scope: the main app's search path disables Opik; standalone
  Job Scout can enable it separately.
- Upstream credit consistent with `NOTICE` and `docs/upstream.md`, a real project
  link, and no draft placeholders or personal data in screenshots.

Keep lengthy installation instructions in `docs/setup.md`, `docs/configuration.md`,
and `docs/usage.md` rather than duplicating them throughout the article.

## Hand off the assessment

Lead with concrete findings ordered by impact, each with a source location and
observed consequence. Then summarize what works, test/install evidence, scan
coverage, and checks not performed. State separately whether the project is ready
for source publication, a local demo, and public service deployment. Do not label
a precaution, manual workaround, or uncommitted change as a shipped fix.
