from datetime import datetime

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="staff")
    real_name = db.Column(db.String(80), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class OperationLog(db.Model):
    __tablename__ = "operation_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    username_snapshot = db.Column(db.String(80), nullable=False)
    role_snapshot = db.Column(db.String(20), nullable=True)
    action = db.Column(db.String(160), nullable=False)
    method = db.Column(db.String(10), nullable=True)
    path = db.Column(db.String(255), nullable=True)
    status_code = db.Column(db.Integer, nullable=True)
    detail = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    user = db.relationship("User", lazy="joined")


class Semester(db.Model):
    __tablename__ = "semesters"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    period_code = db.Column(db.String(20), nullable=True)
    period_positive = db.Column(db.String(20), nullable=True)
    period_development = db.Column(db.String(20), nullable=True)
    period_probationary = db.Column(db.String(20), nullable=True)
    year = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="active")

    exam_weight = db.Column(db.Integer, nullable=False, default=40)
    attendance_weight = db.Column(db.Integer, nullable=False, default=30)
    assignment_weight = db.Column(db.Integer, nullable=False, default=20)
    volunteer_weight = db.Column(db.Integer, nullable=False, default=10)
    pass_threshold = db.Column(db.Float, nullable=False, default=60.0)
    volunteer_target_hours = db.Column(db.Float, nullable=False, default=0.0)

    min_attendance_sessions = db.Column(db.Integer, nullable=False, default=2)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    students = db.relationship("Student", back_populates="semester", cascade="all, delete-orphan")
    course_sessions = db.relationship("CourseSession", back_populates="semester", cascade="all, delete-orphan")
    assignments = db.relationship("Assignment", back_populates="semester", cascade="all, delete-orphan")
    volunteer_records = db.relationship(
        "VolunteerRecord", back_populates="semester", cascade="all, delete-orphan"
    )
    exam_records = db.relationship("ExamRecord", back_populates="semester", cascade="all, delete-orphan")
    final_scores = db.relationship("FinalScore", back_populates="semester", cascade="all, delete-orphan")

    def period_for_stage(self, stage: str) -> str:
        if stage == "积极分子":
            return (self.period_positive or "").strip()
        if stage == "发展对象":
            return (self.period_development or "").strip()
        if stage == "预备党员":
            return (self.period_probationary or "").strip()
        return ""

    def period_label_for_stage(self, stage: str) -> str:
        code = self.period_for_stage(stage)
        if not code:
            return ""
        term = (self.name or "").strip() or str(self.year)
        return f"{code}期（{term}）"


class Student(db.Model):
    __tablename__ = "students"
    __table_args__ = (
        db.UniqueConstraint("semester_id", "student_id", "stage", name="uq_student_semester_student_stage"),
    )

    id = db.Column(db.Integer, primary_key=True)
    semester_id = db.Column(db.Integer, db.ForeignKey("semesters.id"), nullable=False, index=True)
    name = db.Column(db.String(80), nullable=False)
    student_id = db.Column(db.String(50), nullable=False)
    department = db.Column(db.String(120), nullable=True)
    stage = db.Column(db.String(20), nullable=False)
    contact = db.Column(db.String(120), nullable=True)
    group_number = db.Column(db.Integer, nullable=True)
    is_group_leader = db.Column(db.Boolean, nullable=False, default=False)
    status = db.Column(db.String(20), nullable=False, default="在读")
    disqualified_reason = db.Column(db.String(255), nullable=True)

    semester = db.relationship("Semester", back_populates="students")
    attendances = db.relationship("Attendance", back_populates="student", cascade="all, delete-orphan")
    assignments = db.relationship("Assignment", back_populates="student", cascade="all, delete-orphan")
    volunteer_records = db.relationship(
        "VolunteerRecord", back_populates="student", cascade="all, delete-orphan"
    )
    exam_records = db.relationship("ExamRecord", back_populates="student", cascade="all, delete-orphan")
    final_scores = db.relationship("FinalScore", back_populates="student", cascade="all, delete-orphan")


class CourseSession(db.Model):
    __tablename__ = "course_sessions"
    __table_args__ = (
        db.UniqueConstraint("semester_id", "session_number", name="uq_semester_session_number"),
    )

    id = db.Column(db.Integer, primary_key=True)
    semester_id = db.Column(db.Integer, db.ForeignKey("semesters.id"), nullable=False, index=True)
    session_number = db.Column(db.Integer, nullable=False)
    theme = db.Column(db.String(200), nullable=False)
    date = db.Column(db.Date, nullable=False)
    location = db.Column(db.String(200), nullable=True)
    is_online = db.Column(db.Boolean, nullable=False, default=False)
    meeting_link = db.Column(db.String(255), nullable=True)
    lecturer = db.Column(db.String(120), nullable=True)
    notes = db.Column(db.Text, nullable=True)

    semester = db.relationship("Semester", back_populates="course_sessions")
    attendances = db.relationship("Attendance", back_populates="session", cascade="all, delete-orphan")
    assignments = db.relationship("Assignment", back_populates="session", cascade="all")


class Attendance(db.Model):
    __tablename__ = "attendances"
    __table_args__ = (
        db.UniqueConstraint("student_id", "session_id", name="uq_attendance_student_session"),
    )

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False, index=True)
    session_id = db.Column(db.Integer, db.ForeignKey("course_sessions.id"), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default="到场")
    leave_reason = db.Column(db.String(255), nullable=True)
    checked_by = db.Column(db.String(80), nullable=True)
    checked_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    student = db.relationship("Student", back_populates="attendances")
    session = db.relationship("CourseSession", back_populates="attendances")


class Assignment(db.Model):
    __tablename__ = "assignments"
    __table_args__ = (
        db.UniqueConstraint("student_id", "semester_id", "session_id", "type", name="uq_assignment_unique_task"),
    )

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False, index=True)
    semester_id = db.Column(db.Integer, db.ForeignKey("semesters.id"), nullable=False, index=True)
    session_id = db.Column(db.Integer, db.ForeignKey("course_sessions.id"), nullable=True, index=True)
    type = db.Column(db.String(30), nullable=False)
    word_count = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(20), nullable=False, default="未提交")
    submitted_at = db.Column(db.DateTime, nullable=True)
    reviewed_by = db.Column(db.String(80), nullable=True)
    review_note = db.Column(db.Text, nullable=True)

    student = db.relationship("Student", back_populates="assignments")
    semester = db.relationship("Semester", back_populates="assignments")
    session = db.relationship("CourseSession", back_populates="assignments")


class VolunteerRecord(db.Model):
    __tablename__ = "volunteer_records"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False, index=True)
    semester_id = db.Column(db.Integer, db.ForeignKey("semesters.id"), nullable=False, index=True)
    activity_name = db.Column(db.String(200), nullable=False)
    hours = db.Column(db.Float, nullable=False, default=0.0)
    proof_note = db.Column(db.String(255), nullable=True)
    verified = db.Column(db.Boolean, nullable=False, default=False)
    verified_by = db.Column(db.String(80), nullable=True)
    verified_at = db.Column(db.DateTime, nullable=True)

    student = db.relationship("Student", back_populates="volunteer_records")
    semester = db.relationship("Semester", back_populates="volunteer_records")


class ExamRecord(db.Model):
    __tablename__ = "exam_records"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False, index=True)
    semester_id = db.Column(db.Integer, db.ForeignKey("semesters.id"), nullable=False, index=True)
    score = db.Column(db.Float, nullable=False)
    exam_time = db.Column(db.DateTime, nullable=True)
    is_cheating = db.Column(db.Boolean, nullable=False, default=False)
    cheating_note = db.Column(db.String(255), nullable=True)

    student = db.relationship("Student", back_populates="exam_records")
    semester = db.relationship("Semester", back_populates="exam_records")


class FinalScore(db.Model):
    __tablename__ = "final_scores"
    __table_args__ = (
        db.UniqueConstraint("student_id", "semester_id", name="uq_final_score_student_semester"),
    )

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False, index=True)
    semester_id = db.Column(db.Integer, db.ForeignKey("semesters.id"), nullable=False, index=True)
    attendance_score = db.Column(db.Float, nullable=False, default=0.0)
    assignment_score = db.Column(db.Float, nullable=False, default=0.0)
    volunteer_score = db.Column(db.Float, nullable=False, default=0.0)
    exam_score = db.Column(db.Float, nullable=False, default=0.0)
    total_score = db.Column(db.Float, nullable=False, default=0.0)
    is_passed = db.Column(db.Boolean, nullable=False, default=False)
    cert_number = db.Column(db.String(64), nullable=True)
    cert_issued_at = db.Column(db.DateTime, nullable=True)

    student = db.relationship("Student", back_populates="final_scores")
    semester = db.relationship("Semester", back_populates="final_scores")


class NotificationTemplate(db.Model):
    __tablename__ = "notification_templates"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(20), nullable=False, default="其他")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )