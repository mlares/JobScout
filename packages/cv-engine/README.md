# CV engine

Explainable CV-family selection plus guarded, optional model-backed tailoring.
The offline selector scores role phrases and skills deterministically. The
tailoring path validates LaTeX structure, blocks dangerous commands and new
includes, and rejects known unsupported claims before writing output.

Set `CV_REPOSITORY_PATH` to a local candidate CV collection. Candidate-specific
LaTeX, evidence, images, and generated documents remain private inputs. Unit
tests exercise ranking, path containment, input validation, and LaTeX guards.
