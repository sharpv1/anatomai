import asyncio
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.imports.errors import ImportFileError
from app.imports.limits import PARSER_SECONDS
from app.imports.store import Store


async def run_parser(
    store: Store, key: str, fmt: str, digest: str, check: Any
) -> tuple[Path, dict[str, Any], Path]:
    work = store.root / ("work-" + uuid4().hex)
    work.mkdir(mode=0o700)
    output, summary = work / "rows.jsonl", work / "summary.json"
    process = None
    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-I",
            "-m",
            "app.imports.parser_process",
            str(store.path(key)),
            str(output),
            str(summary),
            fmt,
            digest,
            cwd=work,
            env={"PATH": os.defpath, "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"},
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True,
        )
        async with asyncio.timeout(PARSER_SECONDS):
            while process.returncode is None:
                await check()
                try:
                    await asyncio.wait_for(process.wait(), timeout=0.5)
                except TimeoutError:
                    pass
        if not summary.exists() or summary.stat().st_size > 4096:
            raise ImportFileError("PARSER_LIMIT")
        result = json.loads(summary.read_text())
        if result.get("error_code"):
            raise ImportFileError(result["error_code"])
        if process.returncode != 0:
            raise ImportFileError("PARSER_LIMIT")
        return output, result, work
    except BaseException as exc:
        if process is not None and process.returncode is None:
            process.kill()
            await process.wait()
        shutil.rmtree(work, ignore_errors=True)
        if isinstance(exc, TimeoutError):
            raise ImportFileError("PARSER_LIMIT") from None
        raise
