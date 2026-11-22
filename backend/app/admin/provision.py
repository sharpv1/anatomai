"""Operator TTY only. No HTTP enrollment/recovery and no secret-bearing argv."""

import argparse
import asyncio
import base64
import getpass
import secrets
import sys

from app.admin.mfa import provision
from app.core.config import Settings
from app.core.errors import ApplicationError
from app.db.database import Database


async def run(telegram_id: int, secret: str, proof: str, recovery: str | None) -> list[str]:
    settings = Settings()
    database = Database(settings)
    try:
        await database.check_ready()
        async with database.sessions.begin() as db:
            return await provision(db, settings, telegram_id, secret, proof, recovery=recovery)
    finally:
        await database.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Operator-only MEDEXA TOTP enrollment/recovery")
    parser.add_argument("--telegram-user-id", type=int, required=True)
    parser.add_argument("--recover", action="store_true")
    parser.add_argument("--confirm", action="store_true", required=True)
    args = parser.parse_args()
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        parser.error("Private interactive TTY required; do not redirect provisioning output")
    if not 0 < args.telegram_user_id <= 2**63 - 1:
        parser.error("Invalid numeric Telegram ID")
    recovery = getpass.getpass("Existing single-use recovery code: ") if args.recover else None
    secret = base64.b32encode(secrets.token_bytes(20)).decode()
    print("Configure an authenticator for MEDEXA / Telegram ID", args.telegram_user_id)
    print("TOTP: SHA1, 6 digits, 30 seconds. Private provisioning secret:", secret)
    proof = getpass.getpass("Current authenticator code: ")
    try:
        codes = asyncio.run(run(args.telegram_user_id, secret, proof, recovery))
    except ApplicationError as exc:
        raise SystemExit(exc.code) from None
    except Exception:
        raise SystemExit("MFA_PROVISION_FAILED: check configuration/readiness privately") from None
    print("MFA saved. All previous sessions revoked. Wait for the next TOTP time step.")
    print("Store these one-use recovery codes privately; they cannot be retrieved again:")
    for code in codes:
        print(code)


if __name__ == "__main__":
    main()
