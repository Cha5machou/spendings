"""Document storage: local disk or a Cloud Storage bucket, selected with STORAGE_BACKEND."""

import uuid
from pathlib import Path
from typing import Protocol

from app.config import settings


class DocumentStorage(Protocol):
    def save(self, filename: str, content: bytes) -> str: ...

    def read(self, stored_path: str) -> bytes: ...


class LocalStorage:
    def __init__(self, root: Path):
        self.root = root

    def save(self, filename: str, content: bytes) -> str:
        safe_name = Path(filename).name
        stored_name = f"{uuid.uuid4().hex}_{safe_name}"
        (self.root / stored_name).write_bytes(content)
        return stored_name

    def read(self, stored_path: str) -> bytes:
        return (self.root / stored_path).read_bytes()


class GcsStorage:
    """Documents in a Cloud Storage bucket (Application Default Credentials on Cloud Run)."""

    def __init__(self, bucket_name: str):
        from google.cloud import storage

        self.bucket = storage.Client().bucket(bucket_name)

    def save(self, filename: str, content: bytes) -> str:
        stored_name = f"documents/{uuid.uuid4().hex}_{Path(filename).name}"
        self.bucket.blob(stored_name).upload_from_string(content)
        return stored_name

    def read(self, stored_path: str) -> bytes:
        return self.bucket.blob(stored_path).download_as_bytes()


def get_storage() -> DocumentStorage:
    if settings.storage_backend == "local":
        return LocalStorage(settings.documents_dir)
    if settings.storage_backend == "gcs":
        if not settings.gcs_bucket:
            raise RuntimeError("STORAGE_BACKEND=gcs needs GCS_BUCKET")
        return GcsStorage(settings.gcs_bucket)
    raise NotImplementedError(f"Storage backend '{settings.storage_backend}' is not implemented")
