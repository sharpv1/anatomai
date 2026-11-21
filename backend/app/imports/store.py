import asyncio
import hashlib
import os
import re
import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import Request

from app.core.config import Settings
from app.core.errors import ApplicationError
from app.imports.limits import UPLOAD_BYTES


class Store:
    def __init__(self, settings: Settings) -> None:
        root = settings.import_storage_dir
        if root is None:
            raise ApplicationError("IMPORT_NOT_CONFIGURED", "Импорт пока не настроен.", 503)
        code_root = Path(__file__).resolve().parents[2]
        forbidden = [code_root, Path("/app"), Path("/var/www"), Path("/usr/share/nginx/html")]
        for ancestor in Path(__file__).resolve().parents:
            if (ancestor / ".git").exists():
                forbidden.append(ancestor)
                break
        if root.resolve() != root or any(root.is_relative_to(path) for path in forbidden):
            raise ApplicationError(
                "IMPORT_STORAGE_UNSAFE", "Нужен отдельный приватный каталог импорта.", 503
            )
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = root.stat()
        if info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise ApplicationError(
                "IMPORT_STORAGE_UNSAFE",
                "Проверьте владельца и приватные права каталога импорта.",
                503,
            )
        self.root = root

    def path(self, key: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}", key):
            raise ApplicationError("IMPORT_STORAGE_UNSAFE", "Файл недоступен.", 503)
        path = self.root / key
        if path.is_symlink():
            raise ApplicationError("IMPORT_STORAGE_UNSAFE", "Файл недоступен.", 503)
        return path

    async def upload(self, request: Request) -> tuple[str, str, int]:
        if shutil.disk_usage(self.root).free < 256 * 1024 * 1024:
            raise ApplicationError("IMPORT_STORAGE_FULL", "Недостаточно места для импорта.", 503)
        key = uuid4().hex
        path = self.path(key)
        digest = hashlib.sha256()
        size = 0
        try:
            # Each read/write is bounded. No ZIP/XML parsing in the HTTP process.
            with path.open("xb") as target:
                os.chmod(path, 0o600)
                async with asyncio.timeout(60):
                    async for chunk in request.stream():
                        size += len(chunk)
                        if size > UPLOAD_BYTES:
                            raise ApplicationError("REQUEST_TOO_LARGE", "Файл больше 10 MB.", 413)
                        digest.update(chunk)
                        await asyncio.to_thread(target.write, chunk)
            if size < 22:
                raise ApplicationError("FILE_FORMAT", "Нужен непустой XLSX/DOCX файл.", 422)
            with path.open("rb") as file:
                if file.read(4) != b"PK\x03\x04":
                    raise ApplicationError(
                        "FILE_FORMAT", "Нужен файл XLSX/DOCX, не старый XLS/DOC.", 422
                    )
            return key, digest.hexdigest(), size
        except TimeoutError:
            path.unlink(missing_ok=True)
            raise ApplicationError("UPLOAD_TIMEOUT", "Загрузка превысила 60 секунд.", 408) from None
        except BaseException:
            path.unlink(missing_ok=True)
            raise
