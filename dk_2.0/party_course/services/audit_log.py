from flask import has_request_context, request
from flask_login import current_user

from models import OperationLog, db


def log_operation(
    action: str,
    detail: str | None = None,
    method: str | None = None,
    path: str | None = None,
    status_code: int | None = None,
    commit: bool = True,
) -> None:
    user_id = None
    username = "anonymous"
    role = "anonymous"

    if current_user.is_authenticated:
        user_id = getattr(current_user, "id", None)
        username = getattr(current_user, "username", "anonymous") or "anonymous"
        role = getattr(current_user, "role", "anonymous") or "anonymous"

    if has_request_context():
        method = method or request.method
        path = path or request.path

    payload = {
        "user_id": user_id,
        "username_snapshot": username,
        "role_snapshot": role,
        "action": action,
        "method": method,
        "path": path,
        "status_code": status_code,
        "detail": detail,
    }

    if commit:
        with db.engine.begin() as conn:
            conn.execute(OperationLog.__table__.insert().values(**payload))
    else:
        db.session.add(OperationLog(**payload))
