import hashlib
import os
from dataclasses import dataclass
from typing import List

@dataclass
class S3Object:
    key: str
    path: str
    last_modified: float
    size: int

class MockS3Bucket:
    def __init__(self, bucket_dir: str):
        self.bucket_dir = os.path.abspath(bucket_dir)
        os.makedirs(self.bucket_dir, exist_ok=True)

    def _object_path(self, key: str) -> str:
        return os.path.join(self.bucket_dir, key)

    def list_objects(self) -> List[S3Object]:
        objects = []
        for root, _, files in os.walk(self.bucket_dir):
            for file_name in files:
                path = os.path.join(root, file_name)
                key = os.path.relpath(path, self.bucket_dir).replace("\\", "/")
                stat = os.stat(path)
                objects.append(S3Object(key=key, path=path, last_modified=stat.st_mtime, size=stat.st_size))
        return sorted(objects, key=lambda obj: obj.key)

    def read_file(self, key: str) -> str:
        path = self._object_path(key)
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()

    def upload_file(self, source_path: str, key: str) -> S3Object:
        destination = self._object_path(key)
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        with open(source_path, "rb") as src, open(destination, "wb") as dst:
            dst.write(src.read())
        stat = os.stat(destination)
        return S3Object(key=key, path=destination, last_modified=stat.st_mtime, size=stat.st_size)

    def write_text(self, key: str, content: str) -> S3Object:
        destination = self._object_path(key)
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        with open(destination, "w", encoding="utf-8") as handle:
            handle.write(content)
        stat = os.stat(destination)
        return S3Object(key=key, path=destination, last_modified=stat.st_mtime, size=stat.st_size)

    def delete_object(self, key: str) -> None:
        path = self._object_path(key)
        if os.path.exists(path):
            os.remove(path)

    def compute_hash(self, key: str) -> str:
        path = self._object_path(key)
        hasher = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
