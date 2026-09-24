"""
File storage with two interchangeable backends.

``local``    — a directory on disk.  Used in development and as the offline
               demo-day fallback, where no network call may be required.
``supabase`` — Supabase Storage over its REST API, used in deployment because
               Render's disk does not survive a redeploy.

Uploaded files are never written under their original name.  The stored path is
``<prefix>/<sha256>.<ext>``, which gives three things at once: traversal is
impossible regardless of what the filename contained, identical uploads
deduplicate naturally, and the content hash that the duplicate-document check
(SRS Step 4) already computed is reused as the object key.

The Supabase client is raw ``httpx`` rather than ``supabase-py``: it is one
authenticated PUT and one GET, and the SDK would pull a large dependency tree
onto a 512 MB instance for no benefit.
"""

from __future__ import annotations

import shutil
from abc import ABC, abstractmethod
from pathlib import Path

import httpx

from src.core.config import settings
from src.core.errors import AppError
from src.core.logging import get_logger

log = get_logger("storage")

_EXTENSION_BY_FORMAT = {
    "PDF": "pdf", "DOCX": "docx", "TXT": "txt", "MD": "md", "CSV": "csv",
}


class StorageError(AppError):
    code = "STORAGE_ERROR"
    status_code = 502


class StorageBackend(ABC):
    """Minimal object-store interface."""

    @abstractmethod
    def save(self, data: bytes, *, key: str, content_type: str) -> str:
        """Persist bytes and return the stored path."""

    @abstractmethod
    def load(self, path: str) -> bytes:
        """Read bytes back. Raises StorageError when absent."""

    @abstractmethod
    def delete(self, path: str) -> None:
        """Remove an object. Missing objects are not an error."""

    @abstractmethod
    def exists(self, path: str) -> bool: ...


class LocalStorage(StorageBackend):
    """Files under ``settings.storage_local_dir``."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root or settings.storage_local_dir).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        candidate = (self.root / key).resolve()
        # Defence in depth: keys are machine-generated, but a path that escapes
        # the root must never be written even if a caller passes one through.
        if not candidate.is_relative_to(self.root):
            raise StorageError("Refusing to access a path outside the storage root.")
        return candidate

    def save(self, data: bytes, *, key: str, content_type: str) -> str:
        target = self._resolve(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        log.info("stored_local", key=key, bytes=len(data))
        return key

    def load(self, path: str) -> bytes:
        target = self._resolve(path)
        if not target.exists():
            raise StorageError(f"Stored file not found: {path}")
        return target.read_bytes()

    def delete(self, path: str) -> None:
        target = self._resolve(path)
        if target.exists():
            target.unlink()

    def exists(self, path: str) -> bool:
        return self._resolve(path).exists()

    def clear(self) -> None:
        """Test/demo-reset helper."""
        if self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True, exist_ok=True)


class SupabaseStorage(StorageBackend):
    """Supabase Storage over its REST API."""

    def __init__(self) -> None:
        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise StorageError(
                "STORAGE_BACKEND=supabase requires SUPABASE_URL and "
                "SUPABASE_SERVICE_ROLE_KEY to be configured."
            )
        self.bucket = settings.supabase_storage_bucket
        self.base = f"{settings.supabase_url.rstrip('/')}/storage/v1"
        self._headers = {
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
            "apikey": settings.supabase_service_role_key,
        }

    def save(self, data: bytes, *, key: str, content_type: str) -> str:
        url = f"{self.base}/object/{self.bucket}/{key}"
        try:
            response = httpx.post(
                url,
                content=data,
                headers={
                    **self._headers,
                    "Content-Type": content_type,
                    # Re-uploading identical content must not fail the request.
                    "x-upsert": "true",
                },
                timeout=60.0,
            )
        except httpx.HTTPError as exc:
            raise StorageError(f"Upload to object storage failed: {exc}") from exc

        if response.status_code not in (200, 201):
            raise StorageError(
                f"Object storage rejected the upload ({response.status_code}).",
                details={"body": response.text[:300]},
            )
        log.info("stored_supabase", key=key, bytes=len(data))
        return key

    def load(self, path: str) -> bytes:
        url = f"{self.base}/object/{self.bucket}/{path}"
        try:
            response = httpx.get(url, headers=self._headers, timeout=60.0)
        except httpx.HTTPError as exc:
            raise StorageError(f"Download from object storage failed: {exc}") from exc
        if response.status_code == 404:
            raise StorageError(f"Stored file not found: {path}")
        if response.status_code != 200:
            raise StorageError(
                f"Object storage returned {response.status_code} for {path}."
            )
        return response.content

    def delete(self, path: str) -> None:
        url = f"{self.base}/object/{self.bucket}/{path}"
        try:
            httpx.delete(url, headers=self._headers, timeout=30.0)
        except httpx.HTTPError as exc:  # pragma: no cover - best effort
            log.warning("storage_delete_failed", path=path, error=str(exc))

    def exists(self, path: str) -> bool:
        url = f"{self.base}/object/info/{self.bucket}/{path}"
        try:
            return httpx.head(url, headers=self._headers, timeout=15.0).status_code == 200
        except httpx.HTTPError:
            return False


_CONTENT_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain",
    "md": "text/markdown",
    "csv": "text/csv",
}


def object_key(file_hash: str, file_format: str, *, prefix: str = "documents") -> str:
    """Content-addressed storage key: identical bytes reuse the same object."""
    extension = _EXTENSION_BY_FORMAT.get(str(file_format).upper(), "bin")
    return f"{prefix}/{file_hash[:2]}/{file_hash}.{extension}"


def content_type_for(file_format: str) -> str:
    extension = _EXTENSION_BY_FORMAT.get(str(file_format).upper(), "bin")
    return _CONTENT_TYPES.get(extension, "application/octet-stream")


_backend: StorageBackend | None = None


def get_storage() -> StorageBackend:
    """Return the configured backend (cached)."""
    global _backend
    if _backend is None:
        if settings.storage_backend.lower() == "supabase":
            _backend = SupabaseStorage()
        else:
            _backend = LocalStorage()
        log.info("storage_backend_selected", backend=type(_backend).__name__)
    return _backend


def reset_storage_backend() -> None:
    """Clear the cached backend (tests, and after a config change)."""
    global _backend
    _backend = None
