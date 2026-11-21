"""Isolated runtime image smoke over loopback against the disposable PG16 database."""

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

from app.attempts.finalizer import run_once
from app.core.config import Settings
from app.db.database import Database
from app.db.schema import EXPECTED_SCHEMA_REVISION


async def worker_check():
    database = Database(Settings())
    try:
        await database.check_ready()
        # The CI database has no expired committed exams; an empty poll is safe.
        await run_once(database)
    finally:
        await database.dispose()


assert os.getuid() == 10001
assert EXPECTED_SCHEMA_REVISION == "0009_exam_attempts"
asyncio.run(worker_check())
with socket.socket() as probe:
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
process = subprocess.Popen(
    [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:create_app",
        "--factory",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--no-access-log",
        "--no-proxy-headers",
    ],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
try:
    end = time.monotonic() + 10
    while True:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/live", timeout=1) as response:
                assert response.status == 200
            break
        except urllib.error.URLError:
            if process.poll() is not None or time.monotonic() >= end:
                raise RuntimeError("Runtime API did not become live") from None
            time.sleep(0.05)
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/ready", timeout=3) as response:
        assert response.status == 200
    print(
        json.dumps(
            {
                "uid": os.getuid(),
                "schema": EXPECTED_SCHEMA_REVISION,
                "live": True,
                "ready": True,
                "finalizer_poll": True,
            }
        )
    )
finally:
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)
