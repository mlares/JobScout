#!/usr/bin/env bash
set -euo pipefail
app_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
workspace_root="$(cd "$app_root/../.." && pwd)"
runtime="$workspace_root/.venv/bin/python"
if [[ ! -x "$runtime" ]]; then
  printf 'The Career Workspace environment is missing. Run: cd "%s" && uv sync --all-packages --all-groups\n' "$workspace_root" >&2
  exit 1
fi
if [[ ! -f "$app_root/dist/index.html" ]]; then
  printf 'Build the interface first: cd "%s" && npm install && npm run build\n' "$app_root" >&2
  exit 1
fi
cd "$app_root"
export PYTHONDONTWRITEBYTECODE=1
export CAREER_WORKSPACE_ROOT="$workspace_root"
exec "$runtime" -m uvicorn backend.app:app --host 127.0.0.1 --port "${CAREER_PORT:-8765}"
