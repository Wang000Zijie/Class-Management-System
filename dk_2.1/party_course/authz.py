from functools import wraps

from flask import flash, redirect, request, url_for
from flask_login import current_user


ROLE_LABELS = {
    "admin": "主席",
    "minister": "部长",
    "staff": "干事",
}


def normalize_role(role: str | None) -> str:
    value = (role or "staff").strip().lower()
    if value not in ROLE_LABELS:
        return "staff"
    return value


def role_label(role: str | None) -> str:
    return ROLE_LABELS.get(normalize_role(role), "干事")


def can_view_logs(role: str | None) -> bool:
    return normalize_role(role) in {"admin", "minister"}


def can_manage_accounts(role: str | None) -> bool:
    return normalize_role(role) == "admin"


def can_edit_notification_templates(role: str | None) -> bool:
    return normalize_role(role) in {"admin", "minister"}


def _expand_allowed_roles(roles: tuple[str, ...]) -> set[str]:
    allowed: set[str] = set()
    for role in roles:
        value = normalize_role(role)
        if value == "admin":
            # Minister has the same operational permissions as chair/admin except account management.
            allowed.update({"admin", "minister"})
        else:
            allowed.add(value)
    return allowed


def role_required(*roles):
    def decorator(func):
        allowed_roles = _expand_allowed_roles(roles)

        @wraps(func)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth_bp.login"))
            if normalize_role(getattr(current_user, "role", None)) not in allowed_roles:
                flash("当前账号无权限执行该操作。", "danger")
                return redirect(request.referrer or url_for("auth_bp.dashboard"))
            return func(*args, **kwargs)

        return wrapper

    return decorator


def admin_only_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth_bp.login"))
        if normalize_role(getattr(current_user, "role", None)) != "admin":
            flash("仅主席账号可执行该操作。", "danger")
            return redirect(request.referrer or url_for("auth_bp.dashboard"))
        return func(*args, **kwargs)

    return wrapper