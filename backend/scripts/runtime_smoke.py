"""Run via stdin in the built image with --network none; synthetic input only."""

import asyncio
import hashlib
import json
import os
from pathlib import Path

import app.main  # noqa: F401 -- production imports
import app.publishing.worker  # noqa: F401 -- production publication queue
from app.core.config import Settings
from app.db.schema import EXPECTED_SCHEMA_REVISION
from app.imports.runner import run_parser
from app.imports.store import Store
from app.imports.templates import document


async def main() -> None:
    assert os.getuid() == 10001
    assert not Path("/app/tests").exists() and not Path("/app/scripts").exists()
    assert EXPECTED_SCHEMA_REVISION == "0008_learning_attempts"
    store = Store(
        Settings(
            db_name="medexa_foundation_test",
            db_user="synthetic",
            db_password="synthetic-runtime-only",
            import_storage_dir="/var/lib/medexa-imports",
        )
    )
    key = "a" * 32
    raw = document("xlsx", [["SYNTHETIC", "SYNTHETIC", "RUNTIME TEST", "A", "B", "A"]])
    store.path(key).write_bytes(raw)

    async def check() -> None:
        pass

    output, metrics, _ = await run_parser(
        store, key, "xlsx", hashlib.sha256(raw).hexdigest(), check
    )
    assert metrics["count"] == 1 and json.loads(output.read_text())["errors"] == []
    print(json.dumps({"uid": os.getuid(), "schema": EXPECTED_SCHEMA_REVISION, "parser": metrics}))


asyncio.run(main())
