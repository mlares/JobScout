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
