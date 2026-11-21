from collections.abc import Callable
from typing import TypeVar

from app.core.errors import ApplicationError

# Only implemented medical-draft routes can consume a verified MFA grant.
# Publish/review/import/roles/payment permissions remain fail-closed.
MFA_HTTP_PERMISSIONS = frozenset({"content.admin.read", "content.draft.write"})

F = TypeVar("F", bound=Callable[..., object])
SELF_PERMISSIONS = frozenset(
    {
        "identity.self.read",
        "content.read",
        "identity.preferences.write",
        "identity.sessions.read",
        "identity.sessions.revoke",
    }
)
ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "student": SELF_PERMISSIONS,
    "content_editor": SELF_PERMISSIONS
    | {"content.draft.write", "content.admin.read", "content.publish", "admin.step_up"},
    "content_reviewer": SELF_PERMISSIONS
    | {"content.publish", "content.admin.read", "admin.step_up"},
    "support": SELF_PERMISSIONS | {"support.read"},
    "billing_admin": SELF_PERMISSIONS | {"billing.manage", "admin.step_up"},
    "admin": SELF_PERMISSIONS
    | {
        "roles.manage",
        "content.draft.write",
        "content.admin.read",
        "admin.step_up",
        "content.publish",
        "content.import.publish",
        "support.read",
        "billing.manage",
    },
}


def access(permission: str) -> Callable[[F], F]:
    def decorate(function: F) -> F:
        setattr(function, "medexa_permission", permission)  # noqa: B010 -- typed callable metadata
        return function

    return decorate


def authorize(roles: set[str], permission: str, *, mfa_verified: bool = False) -> None:
    permissions = frozenset().union(*(ROLE_PERMISSIONS.get(role, frozenset()) for role in roles))
    if permission not in permissions:
        raise ApplicationError("ACCESS_DENIED", "Доступ запрещён.", 403)
    if (
        permission not in SELF_PERMISSIONS
        and permission != "admin.step_up"
        and not (mfa_verified and permission in MFA_HTTP_PERMISSIONS)
    ):
        # All other privileged operations stay closed until their own stage.
        raise ApplicationError("MFA_REQUIRED", "Требуется дополнительное подтверждение.", 403)
