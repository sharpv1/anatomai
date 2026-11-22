"""Real browser -> same-origin HTTPS proxy -> TLS FastAPI -> disposable PostgreSQL 16.
Run with backend/.venv/bin/python after the opt-in production build.
Never connects to a supplied database; creates and removes its own Docker container.
"""

import asyncio
import hmac
import http.client
import http.server
import ipaddress
import json
import os
import secrets
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode
from uuid import uuid4

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))


def port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def run(*args, **kwargs):
    return subprocess.run(args, check=True, text=True, **kwargs)


async def seed():
    from app.content.models import (
        Discipline,
        Question,
        QuestionOption,
        QuestionRevision,
        TestDefinition,
        Topic,
        TopicQuestion,
    )
    from app.core.config import Settings
    from app.db.database import Database
    from app.main import create_app

    assert callable(create_app)  # Loads all FK targets, including identity models.

    db = Database(Settings())
    try:
        await db.check_ready()
        async with db.sessions.begin() as session:
            d = Discipline(
                id=uuid4(),
                slug="synthetic-6b",
                title="SYNTHETIC HTTPS ANATOMY",
                icon_key="anatomy",
                color_token="blue",
                status="published",
            )
            session.add(d)
            await session.flush()
            t = Topic(
                id=uuid4(),
                discipline_id=d.id,
                slug="synthetic-heart",
                title="SYNTHETIC HTTPS TOPIC",
                status="published",
            )
            session.add(t)
            await session.flush()
            # Dedicated short test makes a real deadline/finalizer scenario practical.
            definition = TestDefinition(
                id=uuid4(),
                topic_id=t.id,
                slug="timeout",
                title="SYNTHETIC DEADLINE",
                exam_duration_seconds=4,
                status="published",
            )
            session.add(definition)
            await session.flush()
            for i in range(2):
                q = Question(
                    id=uuid4(), external_source="synthetic-https-6b", external_id=str(i)
                )
                session.add(q)
                await session.flush()
                rev = QuestionRevision(
                    id=uuid4(),
                    question_id=q.id,
                    revision_number=1,
                    text=f"SYNTHETIC HTTPS QUESTION {i + 1}",
                    explanation="SYNTHETIC SERVER EXPLANATION",
                    fingerprint=(str(i + 1) * 64),
                )
                session.add(rev)
                await session.flush()
                session.add_all(
                    [
                        QuestionOption(
                            id=uuid4(),
                            revision_id=rev.id,
                            position=j,
                            code=chr(65 + j),
                            text=f"SYNTHETIC OPTION {j}",
                            is_correct=j == 0,
                        )
                        for j in range(2)
                    ]
                )
                await session.flush()
                rev.status = "published"
                await session.flush()
                q.current_revision_id = rev.id
                session.add(TopicQuestion(topic_id=t.id, question_id=q.id, position=i))
                await session.flush()
            return str(t.id), str(definition.id)
    finally:
        await db.dispose()


def launch(user_id):
    fields = {
        "auth_date": str(int(time.time())),
        "query_id": str(uuid4()),
        "user": json.dumps(
            {"id": user_id, "first_name": "SYNTHETIC HTTPS"}, separators=(",", ":")
        ),
    }
    secret = hmac.digest(
        b"WebAppData", os.environ["MEDEXA_TELEGRAM_BOT_TOKEN"].encode(), "sha256"
    )
    fields["hash"] = hmac.digest(
        secret, "\n".join(f"{k}={fields[k]}" for k in sorted(fields)).encode(), "sha256"
    ).hex()
    return urlencode(fields)


with (
    tempfile.TemporaryDirectory(prefix="medexa6b-https-") as temporary,
    ExitStack() as files,
):
    tmp = Path(temporary)
    name = "medexa6b-e2e-" + uuid4().hex[:10]
    children = []
    server = None
    try:
        secret = secrets.token_urlsafe(32)
        pg_env = tmp / "postgres.env"
        pg_env.write_text(
            f"POSTGRES_DB=medexa_foundation_test\nPOSTGRES_USER=medexa_foundation_test\nPOSTGRES_PASSWORD={secret}\n"
        )
        pg_env.chmod(0o600)
        run(
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "--memory=256m",
            "--cpus=1",
            "--env-file",
            str(pg_env),
            "--tmpfs",
            "/var/lib/postgresql/data:rw,size=256m",
            "-p",
            "127.0.0.1::5432",
            "postgres:16-alpine",
            stdout=subprocess.DEVNULL,
        )
        for _ in range(120):
            if (
                subprocess.run(
                    [
                        "docker",
                        "exec",
                        name,
                        "pg_isready",
                        "-U",
                        "medexa_foundation_test",
                    ],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                ).returncode
                == 0
            ):
                break
            time.sleep(0.1)
        else:
            raise RuntimeError("Disposable PostgreSQL not ready")
        mapped = run(
            "docker", "port", name, "5432/tcp", capture_output=True
        ).stdout.strip()
        db_port = int(mapped.rsplit(":", 1)[1])
        tls_port, api_port = port(), port()
        origin = f"https://127.0.0.1:{tls_port}"
        os.environ.update(
            {
                "MEDEXA_ENVIRONMENT": "test",
                "MEDEXA_DB_HOST": "127.0.0.1",
                "MEDEXA_DB_PORT": str(db_port),
                "MEDEXA_DB_NAME": "medexa_foundation_test",
                "MEDEXA_DB_USER": "medexa_foundation_test",
                "MEDEXA_DB_PASSWORD": secret,
                "MEDEXA_APP_ORIGIN": origin,
                "MEDEXA_TELEGRAM_BOT_TOKEN": "42424242:synthetic_6b_token_abcdefghijklmnopqrstuvwxyz",
                "MEDEXA_CSRF_SIGNING_KEY": secrets.token_urlsafe(40),
                "MEDEXA_CONTENT_CURSOR_SIGNING_KEY": secrets.token_urlsafe(40),
            }
        )
        run(sys.executable, "-m", "alembic", "upgrade", "head", cwd=BACKEND)
        if "--check-backend" in sys.argv:
            os.environ["MEDEXA_RUN_DB_TESTS"] = "1"
            run(
                str(BACKEND / ".venv/bin/ruff"),
                "check",
                "app",
                "migrations",
                "tests",
                cwd=BACKEND,
            )
            run(
                str(BACKEND / ".venv/bin/ruff"),
                "format",
                "--check",
                "app",
                "migrations",
                "tests",
                cwd=BACKEND,
            )
            run(str(BACKEND / ".venv/bin/mypy"), "app", cwd=BACKEND)
            test_env = dict(os.environ)
            for variable in (
                "MEDEXA_TELEGRAM_BOT_TOKEN",
                "MEDEXA_CSRF_SIGNING_KEY",
                "MEDEXA_CONTENT_CURSOR_SIGNING_KEY",
                "MEDEXA_APP_ORIGIN",
            ):
                test_env.pop(variable, None)
            run(sys.executable, "-m", "pytest", "-q", cwd=BACKEND, env=test_env)
        topic, definition = asyncio.run(seed())
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")])
        now = datetime.now(UTC)
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(hours=1))
            .add_extension(
                x509.SubjectAlternativeName(
                    [x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
                ),
                critical=False,
            )
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .sign(key, hashes.SHA256())
        )
        certpath, keypath = tmp / "cert.pem", tmp / "key.pem"
        certpath.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        keypath.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        keypath.chmod(0o600)
        ca = ssl.create_default_context(cafile=str(certpath))
        api_log = files.enter_context(open(tmp / "api.log", "w"))
        api = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:create_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                str(api_port),
                "--no-access-log",
                "--no-proxy-headers",
                "--ssl-keyfile",
                str(keypath),
                "--ssl-certfile",
                str(certpath),
            ],
            cwd=BACKEND,
            stdout=api_log,
            stderr=api_log,
        )
        children.append(api)
        for _ in range(150):
            try:
                conn = http.client.HTTPSConnection(
                    "127.0.0.1", api_port, context=ca, timeout=1
                )
                conn.request("GET", "/ready")
                ready = conn.getresponse().status == 200
                conn.close()
                if ready:
                    break
            except OSError:
                pass
            time.sleep(0.1)
        else:
            raise RuntimeError("TLS FastAPI not ready")
        finalizer = subprocess.Popen(
            [sys.executable, "-m", "app.attempts.finalizer"],
            cwd=BACKEND,
            stdout=api_log,
            stderr=api_log,
        )
        children.append(finalizer)

        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(ROOT / "dist"), **kwargs)

            def log_message(self, *args):
                pass

            def forward(self):
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length) if length else None
                headers = {
                    k: v
                    for k, v in self.headers.items()
                    if k.lower() not in ("host", "connection", "accept-encoding")
                }
                conn = http.client.HTTPSConnection(
                    "127.0.0.1", api_port, context=ca, timeout=15
                )
                try:
                    conn.request(self.command, self.path, body, headers)
                    response = conn.getresponse()
                    data = response.read()
                    self.send_response(response.status)
                    for k, v in response.getheaders():
                        if k.lower() not in (
                            "transfer-encoding",
                            "connection",
                            "content-length",
                        ):
                            self.send_header(k, v)
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                finally:
                    conn.close()

            def do_GET(self):
                if self.path.startswith("/api/"):
                    self.forward()
                else:
                    super().do_GET()

            do_POST = forward
            do_PUT = forward

        server = http.server.ThreadingHTTPServer(("127.0.0.1", tls_port), Handler)
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.load_cert_chain(certpath, keypath)
        server.socket = tls.wrap_socket(server.socket, server_side=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        fixture_path = tmp / "fixture.json"
        fixture_path.write_text(
            json.dumps(
                {
                    "origin": origin,
                    "topic": topic,
                    "definition": definition,
                    "defaultBuild": True,
                    "initData": launch(uuid4().int % (2**52) + 1),
                }
            )
        )
        fixture_path.chmod(0o600)
        dbcheck = tmp / "check.py"
        dbcheck.write_text(
            "import asyncio, sys\nsys.path.insert(0," + repr(str(BACKEND)) + ")\n"
            "from app.core.config import Settings\nfrom sqlalchemy.ext.asyncio import create_async_engine\n"
            "from sqlalchemy import text\n"
            "async def check():\n e=create_async_engine(Settings().database_url)\n"
            " async with e.connect() as c:\n"
            "  phase=sys.argv[1] if len(sys.argv)>1 else 'final'\n"
            '  n=await c.scalar(text("SELECT count(*) FROM attempts"))\n'
            "  if phase=='start':\n   assert n==1\n"
            "   assert await c.scalar(text(\"SELECT count(*) FROM attempts WHERE status='in_progress'\"))==1\n"
            "  elif phase=='learning':\n   assert n==1\n"
            "   assert await c.scalar(text(\"SELECT count(*) FROM attempts WHERE status='completed'\"))==1\n"
            '   assert await c.scalar(text("SELECT count(*) FROM attempt_responses"))==2\n'
            "  else:\n   assert n==3\n"
            "   assert await c.scalar(text(\"SELECT count(*) FROM attempts WHERE status='completed'\"))==3\n"
            "   assert await c.scalar(text(\"SELECT count(*) FROM attempts WHERE finish_reason='timeout'\"))==1\n"
            '   assert await c.scalar(text("SELECT count(*) FROM attempt_responses"))==6\n'
            " await e.dispose()\nasyncio.run(check())\n"
        )
        os.environ["MEDEXA_E2E_PYTHON"] = sys.executable
        os.environ["MEDEXA_E2E_DB_CHECK"] = str(dbcheck)
        # Only this synthetic launch is handed to the browser, never a real Telegram token.
        run("node", "tests/backend-attempts-https.mjs", str(fixture_path), cwd=ROOT)
        print(
            "REAL_HTTPS_E2E_PASS: PostgreSQL16, head0010, HMAC, Secure cookies, Learning, Exam, resume, timeout/finalizer, statistics"
        )
    finally:
        if server:
            server.shutdown()
            server.server_close()
        for child in reversed(children):
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        subprocess.run(
            ["docker", "rm", "-f", name],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
