from flask import Flask, redirect, render_template, request, url_for
from flask_login import LoginManager, current_user
from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError
from werkzeug.security import generate_password_hash

from authz import can_edit_notification_templates, can_manage_accounts, can_view_logs, role_label
from blueprints.assignments import assignments_bp
from blueprints.ai_tools import ai_tools_bp
from blueprints.attendance import attendance_bp
from blueprints.auth import auth_bp
from blueprints.courses import courses_bp
from blueprints.notifications import notifications_bp
from blueprints.scores import scores_bp
from blueprints.semester import semester_bp
from blueprints.students import students_bp
from blueprints.volunteers import volunteers_bp
from config import Config
from models import Assignment, Semester, User, VolunteerRecord, db
from services.audit_log import log_operation


def _ensure_schema_compatibility() -> None:
    inspector = inspect(db.engine)
    if "semesters" in inspector.get_table_names():
        columns = {col["name"] for col in inspector.get_columns("semesters")}
        if "period_code" not in columns:
            db.session.execute(text("ALTER TABLE semesters ADD COLUMN period_code VARCHAR(20)"))
            db.session.commit()
        if "period_positive" not in columns:
            db.session.execute(text("ALTER TABLE semesters ADD COLUMN period_positive VARCHAR(20)"))
            db.session.commit()
        if "period_development" not in columns:
            db.session.execute(text("ALTER TABLE semesters ADD COLUMN period_development VARCHAR(20)"))
            db.session.commit()
        if "period_probationary" not in columns:
            db.session.execute(text("ALTER TABLE semesters ADD COLUMN period_probationary VARCHAR(20)"))
            db.session.commit()

    if "students" in inspector.get_table_names():
        index_rows = db.session.execute(text("PRAGMA index_list('students')")).fetchall()
        has_stage_unique = False
        for idx in index_rows:
            if not idx[2]:
                continue
            idx_name = idx[1]
            idx_cols = db.session.execute(text(f"PRAGMA index_info('{idx_name}')")).fetchall()
            col_names = [col[2] for col in idx_cols]
            if col_names == ["semester_id", "student_id", "stage"]:
                has_stage_unique = True
                break

        if not has_stage_unique:
            db.session.execute(text("PRAGMA foreign_keys=OFF"))
            db.session.execute(
                text(
                    """
                    CREATE TABLE students_new (
                        id INTEGER NOT NULL PRIMARY KEY,
                        semester_id INTEGER NOT NULL,
                        name VARCHAR(80) NOT NULL,
                        student_id VARCHAR(50) NOT NULL,
                        department VARCHAR(120),
                        stage VARCHAR(20) NOT NULL,
                        contact VARCHAR(120),
                        group_number INTEGER,
                        is_group_leader BOOLEAN NOT NULL DEFAULT 0,
                        status VARCHAR(20) NOT NULL DEFAULT '在读',
                        disqualified_reason VARCHAR(255),
                        CONSTRAINT uq_student_semester_student_stage UNIQUE (semester_id, student_id, stage),
                        FOREIGN KEY(semester_id) REFERENCES semesters (id)
                    )
                    """
                )
            )
            db.session.execute(
                text(
                    """
                    INSERT INTO students_new (
                        id, semester_id, name, student_id, department, stage,
                        contact, group_number, is_group_leader, status, disqualified_reason
                    )
                    SELECT
                        id, semester_id, name, student_id, department, stage,
                        contact, group_number, is_group_leader, status, disqualified_reason
                    FROM students
                    """
                )
            )
            db.session.execute(text("DROP TABLE students"))
            db.session.execute(text("ALTER TABLE students_new RENAME TO students"))
            db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_students_semester_id ON students (semester_id)"))
            db.session.execute(text("PRAGMA foreign_keys=ON"))
            db.session.commit()


def _ensure_default_accounts() -> None:
    presets = [
        {
            "username": "admin",
            "password": "admin123",
            "role": "admin",
            "real_name": "系统管理员",
        },
        {
            "username": "buzhang",
            "password": "buzhang123",
            "role": "minister",
            "real_name": "部长账号",
        },
        {
            "username": "ganshi",
            "password": "ganshi123",
            "role": "staff",
            "real_name": "干事账号",
        },
    ]

    dirty = False
    for item in presets:
        user = User.query.filter_by(username=item["username"]).first()
        if user is None:
            user = User(
                username=item["username"],
                password_hash=generate_password_hash(item["password"]),
                role=item["role"],
                real_name=item["real_name"],
            )
            db.session.add(user)
            dirty = True
            continue

        # Keep existing passwords for existing users; only align role/name.
        if user.role != item["role"]:
            user.role = item["role"]
            dirty = True
        if not (user.real_name or "").strip():
            user.real_name = item["real_name"]
            dirty = True

    if dirty:
        db.session.commit()


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)

    with app.app_context():
        # Ensure tables exist even if init_db.py was not run yet.
        db.create_all()
        _ensure_schema_compatibility()
        _ensure_default_accounts()

    login_manager = LoginManager()
    login_manager.login_view = "auth_bp.login"
    login_manager.login_message = "请先登录后访问系统。"
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id: str):
        return db.session.get(User, int(user_id))

    app.register_blueprint(auth_bp)
    app.register_blueprint(semester_bp, url_prefix="/semester")
    app.register_blueprint(students_bp, url_prefix="/students")
    app.register_blueprint(courses_bp, url_prefix="/courses")
    app.register_blueprint(attendance_bp, url_prefix="/attendance")
    app.register_blueprint(assignments_bp, url_prefix="/assignments")
    app.register_blueprint(ai_tools_bp, url_prefix="/ai-tools")
    app.register_blueprint(volunteers_bp, url_prefix="/volunteers")
    app.register_blueprint(scores_bp, url_prefix="/scores")
    app.register_blueprint(notifications_bp, url_prefix="/notifications")

    @app.before_request
    def require_login_before_access():
        endpoint = request.endpoint or ""
        if endpoint == "static":
            return None
        if endpoint == "auth_bp.login":
            return None
        if current_user.is_authenticated:
            return None
        return redirect(url_for("auth_bp.login", next=request.path))

    @app.after_request
    def audit_mutation_requests(response):
        try:
            if request.endpoint == "static":
                return response
            if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
                return response
            if not current_user.is_authenticated:
                return response

            form_parts = []
            for key, value in request.form.items():
                if "password" in key.lower():
                    continue
                form_parts.append(f"{key}={(value or '')[:40]}")

            detail = f"status={response.status_code}"
            if form_parts:
                detail += "; form=" + ", ".join(form_parts[:6])

            log_operation(
                action=request.endpoint or request.path,
                detail=detail,
                status_code=response.status_code,
            )
        except Exception:
            db.session.rollback()

        return response

    @app.context_processor
    def inject_current_semester():
        current_semester = None
        pending_assignment_students = 0
        pending_volunteer_records = 0
        try:
            current_semester = Semester.query.filter_by(status="active").order_by(Semester.id.desc()).first()
            if current_semester:
                pending_assignment_students = (
                    db.session.query(Assignment.student_id)
                    .filter_by(semester_id=current_semester.id, status="未提交")
                    .distinct()
                    .count()
                )
                pending_volunteer_records = VolunteerRecord.query.filter_by(
                    semester_id=current_semester.id,
                    verified=False,
                ).count()
        except OperationalError:
            # DB is not fully initialized yet; keep defaults to avoid rendering failure.
            db.session.rollback()

        role = getattr(current_user, "role", None) if current_user.is_authenticated else None

        return {
            "current_semester": current_semester,
            "pending_assignment_students": pending_assignment_students,
            "pending_volunteer_records": pending_volunteer_records,
            "current_user_role_label": role_label(role),
            "can_view_logs": can_view_logs(role),
            "can_manage_accounts": can_manage_accounts(role),
            "can_edit_notification_templates": can_edit_notification_templates(role),
        }

    @app.errorhandler(404)
    def page_not_found(_error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def internal_error(_error):
        db.session.rollback()
        return render_template("errors/500.html"), 500

    @app.route("/")
    def index():
        if current_user.is_authenticated:
            return redirect(url_for("auth_bp.dashboard"))
        return redirect(url_for("auth_bp.login"))

    return app


app = create_app()


if __name__ == "__main__":
    app.run()