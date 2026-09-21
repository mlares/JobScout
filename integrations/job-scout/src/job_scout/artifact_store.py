"""In-process capability registry for generated application downloads."""

from __future__ import annotations

import re
import secrets
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

_SAFE_KIND = re.compile(r"^[a-z][a-z0-9-]{0,39}$")


class ArtifactAccessError(RuntimeError):
    """A requested artifact is absent or not authorized."""


@dataclass(frozen=True)
class DownloadBundle:
    request_id: str
    token: str

    def url(self, kind: str, api_origin: str = "http://localhost:8000") -> str:
        safe_token = quote(self.token, safe="")
        return f"{api_origin}/api/download/{self.request_id}/{kind}?token={safe_token}"


@dataclass(frozen=True)
class _Entry:
    token: str
    files: Mapping[str, Path]


_REGISTRY: dict[str, _Entry] = {}
_LOCK = threading.Lock()


def register_files(
    files: Mapping[str, Path],
    *,
    request_id: str | None = None,
    token: str | None = None,
) -> DownloadBundle:
    """Register exact server paths behind an opaque request id and token."""
    if not files or any(not _SAFE_KIND.fullmatch(kind) for kind in files):
        raise ArtifactAccessError("Generated-file types failed validation.")
    resolved = {kind: path.resolve() for kind, path in files.items()}
    if any(not path.is_file() for path in resolved.values()):
        raise ArtifactAccessError("A generated file is unavailable.")
    bundle = DownloadBundle(request_id or uuid4().hex, token or secrets.token_urlsafe(32))
    with _LOCK:
        if bundle.request_id in _REGISTRY:
            raise ArtifactAccessError("Generated-file request id already exists.")
        _REGISTRY[bundle.request_id] = _Entry(bundle.token, resolved)
    return bundle


def resolve_file(request_id: str, token: str, kind: str) -> tuple[Path, str]:
    """Resolve one registered file without accepting a client filesystem path."""
    if not _SAFE_KIND.fullmatch(kind):
        raise ArtifactAccessError("Unknown generated-file type.")
    with _LOCK:
        entry = _REGISTRY.get(request_id)
    if entry is None or not secrets.compare_digest(entry.token, token):
        raise ArtifactAccessError("Generated file is unavailable for this request.")
    path = entry.files.get(kind)
    if path is None or not path.is_file():
        raise ArtifactAccessError("Generated file is unavailable for this request.")
    return path, path.name


def clear_registry() -> None:
    """Clear registrations; artifact lifecycle remains owned by each producer."""
    with _LOCK:
        _REGISTRY.clear()
