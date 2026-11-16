"""Document storage. Local disk today; a GCS implementation can be added here
with the same two methods and selected through settings.storage_backend."""

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


def get_storage() -> DocumentStorage:
    if settings.storage_backend == "local":
        return LocalStorage(settings.documents_dir)
    raise NotImplementedError(f"Storage backend '{settings.storage_backend}' is not implemented yet")
