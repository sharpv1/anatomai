from collections.abc import Callable
from typing import TypeVar

from app.core.errors import ApplicationError

F = TypeVar("F", bound=Callable[..., object])
SELF_PERMISSIONS = frozenset(
    {
        "identity.self.read",
        "identity.preferences.write",
        "identity.sessions.read",
        "identity.sessions.revoke",
    }
)
ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "student": SELF_PERMISSIONS,
    "content_editor": SELF_PERMISSIONS | {"content.draft.write"},
    "content_reviewer": SELF_PERMISSIONS | {"content.publish"},
    "support": SELF_PERMISSIONS | {"support.read"},
    "billing_admin": SELF_PERMISSIONS | {"billing.manage"},
    "admin": SELF_PERMISSIONS
    | {"roles.manage", "content.draft.write", "content.publish", "support.read", "billing.manage"},
}


def access(permission: str) -> Callable[[F], F]:
    def decorate(function: F) -> F:
        setattr(function, "medexa_permission", permission)  # noqa: B010 -- typed callable metadata
        return function

    return decorate


def authorize(roles: set[str], permission: str) -> None:
    permissions = frozenset().union(*(ROLE_PERMISSIONS.get(role, frozenset()) for role in roles))
    if permission not in permissions:
        raise ApplicationError("ACCESS_DENIED", "Доступ запрещён.", 403)
    if permission not in SELF_PERMISSIONS:
        # No administrative HTTP operation can bypass the future MFA implementation.
        raise ApplicationError("MFA_REQUIRED", "Требуется дополнительное подтверждение.", 403)
