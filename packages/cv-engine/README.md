# CV engine

Explainable CV-family selection plus guarded, optional model-backed tailoring.
The offline selector scores role phrases and skills deterministically. The
tailoring path validates selected LaTeX structure, command/include patterns, and
known unsupported claims before writing output. These checks neither establish
factual correctness nor securely sandbox compilation of generated LaTeX.

Set `CV_REPOSITORY_PATH` to a local candidate CV collection. Candidate-specific
LaTeX, evidence, images, and generated documents remain private inputs. Unit
tests exercise ranking, path containment, input validation, and LaTeX guards.

See [CV and LaTeX configuration](../../docs/configuration.md#prepare-the-cv-family-and-latex)
for the six-family layout, packages, and build commands. The fictional demo ships
prebuilt PDFs and needs no LaTeX. Read [Security](../../SECURITY.md) before enabling
model-generated CV compilation on a machine with sensitive files.
