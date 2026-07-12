"""Central authorization rules for BeachOps control-plane actions."""

from __future__ import annotations

from beachops.domain.models import UserMode
from beachops.domain.security import Role


_ROLE_RANK = {
    Role.VIEWER: 10,
    Role.OPERATOR: 20,
    Role.OWNER: 30,
}


class AuthorizationError(PermissionError):
    """Raised when an actor does not have the required role."""


def has_role(role: Role | None, minimum: Role) -> bool:
    return role is not None and _ROLE_RANK[role] >= _ROLE_RANK[minimum]


def can_read(role: Role | None) -> bool:
    return has_role(role, Role.VIEWER)


def can_write(role: Role | None) -> bool:
    return has_role(role, Role.OPERATOR)


def can_approve(role: Role | None) -> bool:
    return role == Role.OWNER


def can_use_mode(role: Role | None, mode: UserMode) -> bool:
    if mode == UserMode.ASK:
        return can_read(role)
    return can_write(role)


def require_role(role: Role | None, minimum: Role) -> None:
    if not has_role(role, minimum):
        raise AuthorizationError(f"{minimum.value} role required")


def require_owner(role: Role | None) -> None:
    if role != Role.OWNER:
        raise AuthorizationError("owner role required")

