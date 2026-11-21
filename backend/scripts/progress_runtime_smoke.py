"""Synthetic real-HTTP authentication and progress reads. Disposable test DB only."""

import hmac
import ipaddress
import json
import os
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.parse import urlencode
from uuid import uuid4

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from app.core.config import Settings
from app.db.schema import EXPECTED_SCHEMA_REVISION

settings = Settings()
assert settings.environment == "test" and settings.db_name == "medexa_foundation_test"
assert EXPECTED_SCHEMA_REVISION == "0010_progress_statistics" and os.getuid() == 10001
# Test fixtures are only in this stdin script, not in app/ or the runtime image.
token = "42424242:synthetic_runtime_token_abcdefghijklmnopqrstuvwxyz"
origin = "https://runtime.test"
child_env = os.environ | {
    "MEDEXA_TELEGRAM_BOT_TOKEN": token,
    "MEDEXA_CSRF_SIGNING_KEY": "synthetic-runtime-csrf-" + "c" * 40,
    "MEDEXA_CONTENT_CURSOR_SIGNING_KEY": "synthetic-runtime-cursor-" + "s" * 40,
    "MEDEXA_APP_ORIGIN": origin,
}
temporary = tempfile.TemporaryDirectory(prefix="medexa-progress-tls-")
key_path = Path(temporary.name) / "key.pem"
cert_path = Path(temporary.name) / "cert.pem"
private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")])
now = datetime.now(UTC)
certificate = (
    x509.CertificateBuilder()
    .subject_name(subject)
    .issuer_name(subject)
    .public_key(private_key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(now - timedelta(minutes=1))
    .not_valid_after(now + timedelta(hours=1))
    .add_extension(
        x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]),
        critical=False,
    )
    .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
    .sign(private_key, hashes.SHA256())
)
key_path.write_bytes(
    private_key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
)
key_path.chmod(0o600)
cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
context = ssl.create_default_context(cafile=str(cert_path))
jar = CookieJar()
opener = urllib.request.build_opener(
    urllib.request.HTTPSHandler(context=context), urllib.request.HTTPCookieProcessor(jar)
)
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
        "--ssl-keyfile",
        str(key_path),
        "--ssl-certfile",
        str(cert_path),
    ],
    env=child_env,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
base = f"https://127.0.0.1:{port}"
try:
    end = time.monotonic() + 10
    while True:
        try:
            with opener.open(base + "/ready", timeout=3) as response:
                assert response.status == 200
            break
        except urllib.error.URLError:
            if process.poll() is not None or time.monotonic() >= end:
                raise RuntimeError("Progress runtime not ready") from None
            time.sleep(0.05)
    fields = {
        "auth_date": str(int(time.time())),
        "query_id": str(uuid4()),
        "user": json.dumps(
            {"id": uuid4().int % (2**62) + 1, "first_name": "SYNTHETIC RUNTIME"},
            separators=(",", ":"),
        ),
    }
    secret = hmac.digest(b"WebAppData", token.encode(), "sha256")
    fields["hash"] = hmac.digest(
        secret, "\n".join(f"{k}={fields[k]}" for k in sorted(fields)).encode(), "sha256"
    ).hex()
    request = urllib.request.Request(
        base + "/api/v1/auth/telegram",
        data=json.dumps({"init_data": urlencode(fields)}).encode(),
        headers={"Origin": origin, "Content-Type": "application/json"},
    )
    with opener.open(request, timeout=3) as response:
        assert response.status == 200
        assert any(c.name == "__Host-medexa_session" and c.secure for c in jar)
    paths = [
        "/me/statistics",
        "/me/attempts",
        "/me/activity",
        "/me/progress",
        "/me/home",
        "/me/progress/topics",
        "/me/progress/disciplines",
        "/me/mistakes",
        "/me/recommendations",
        "/me/achievements",
        "/me/daily-topic",
    ]
    for path in paths:
        request = urllib.request.Request(base + "/api/v1" + path, headers={"Origin": origin})
        with opener.open(request, timeout=5) as response:
            assert response.status == 200
            body = json.load(response)
            if path == "/me/statistics":
                assert body["data"]["completed_tests"] == 0
                assert body["data"]["average_percent"] is None
            if path == "/me/attempts":
                assert body["data"] == []
    print(
        json.dumps(
            {
                "schema": EXPECTED_SCHEMA_REVISION,
                "uid": os.getuid(),
                "real_https_auth": True,
                "progress_routes": len(paths),
                "empty_owner_history": True,
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

    temporary.cleanup()
