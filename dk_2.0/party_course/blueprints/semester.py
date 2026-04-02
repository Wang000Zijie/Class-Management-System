from io import BytesIO

from flask import Blueprint, flash, redirect, render_template, request, send_file, url_for
from flask_login import login_required
from openpyxl import Workbook

from models import CourseSession, Semester, Student, db


semester_bp = Blueprint("semester_bp", __name__)


def _parse_semester_form(semester: Semester | None = None):
	name = (request.form.get("name") or "").strip()
	period_positive = (request.form.get("period_positive") or "").strip()
	period_development = (request.form.get("period_development") or "").strip()
	period_probationary = (request.form.get("period_probationary") or "").strip()
	year = int(request.form.get("year") or 0)
	exam_weight = int(request.form.get("exam_weight") or 0)
	attendance_weight = int(request.form.get("attendance_weight") or 0)
	assignment_weight = int(request.form.get("assignment_weight") or 0)
	volunteer_weight = int(request.form.get("volunteer_weight") or 0)
	min_attendance_sessions = int(request.form.get("min_attendance_sessions") or 2)
	pass_threshold = float(request.form.get("pass_threshold") or 60)
	volunteer_target_hours = float(request.form.get("volunteer_target_hours") or 0)

	if not name:
		raise ValueError("学期名称不能为空")
	if year < 2000 or year > 2100:
		raise ValueError("年份范围应在 2000-2100")
	for val, label in [
		(exam_weight, "考试权重"),
		(attendance_weight, "出勤权重"),
		(assignment_weight, "作业权重"),
		(volunteer_weight, "志愿权重"),
	]:
		if val < 0 or val > 100:
			raise ValueError(f"{label}必须在 0-100 之间")
	if min_attendance_sessions < 0:
		raise ValueError("最低出勤次数不能小于 0")
	if pass_threshold < 0 or pass_threshold > 100:
		raise ValueError("通过分数线必须在 0-100 之间")
	if volunteer_target_hours < 0:
		raise ValueError("志愿目标时长不能小于 0")

	if exam_weight + attendance_weight + assignment_weight + volunteer_weight != 100:
		raise ValueError("四项成绩权重合计必须为 100")

	target = semester or Semester()
	target.name = name
	target.period_code = ""
	target.period_positive = period_positive
	target.period_development = period_development
	target.period_probationary = period_probationary
	target.year = year
	target.exam_weight = exam_weight
	target.attendance_weight = attendance_weight
	target.assignment_weight = assignment_weight
	target.volunteer_weight = volunteer_weight
	target.min_attendance_sessions = min_attendance_sessions
	target.pass_threshold = pass_threshold
	target.volunteer_target_hours = volunteer_target_hours
	return target


@semester_bp.route("/list")
@login_required
def list_semesters():
	semesters = Semester.query.order_by(Semester.year.desc(), Semester.id.desc()).all()
	rows = []
	for sem in semesters:
		rows.append(
			{
				"semester": sem,
				"student_count": Student.query.filter_by(semester_id=sem.id).count(),
				"course_count": CourseSession.query.filter_by(semester_id=sem.id).count(),
			}
		)
	if request.args.get("export") == "1":
		wb = Workbook()
		ws = wb.active
		ws.append(["学期名称", "积极分子期数", "发展对象期数", "预备党员期数", "年份", "状态", "学员数", "课次数", "权重(考/勤/作/志)", "最低出勤"])
		for row in rows:
			sem = row["semester"]
			ws.append([
				sem.name,
				sem.period_positive or "",
				sem.period_development or "",
				sem.period_probationary or "",
				sem.year,
				sem.status,
				row["student_count"],
				row["course_count"],
				f"{sem.exam_weight}/{sem.attendance_weight}/{sem.assignment_weight}/{sem.volunteer_weight}",
				sem.min_attendance_sessions,
			])
		stream = BytesIO()
		wb.save(stream)
		stream.seek(0)
		return send_file(stream, as_attachment=True, download_name="学期列表.xlsx", mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

	return render_template("semester/list.html", rows=rows)


@semester_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_semester():
	if request.method == "POST":
		try:
			sem = _parse_semester_form()
			sem.status = "inactive"
			db.session.add(sem)
			db.session.commit()
			flash("学期创建成功。", "success")
			return redirect(url_for("semester_bp.list_semesters"))
		except ValueError as exc:
			flash(str(exc), "danger")
	return render_template("semester/form.html", semester=None)


@semester_bp.route("/<int:semester_id>/edit", methods=["GET", "POST"])
@login_required
def edit_semester(semester_id: int):
	sem = db.session.get(Semester, semester_id)
	if not sem:
		flash("学期不存在。", "danger")
		return redirect(url_for("semester_bp.list_semesters"))

	if request.method == "POST":
		try:
			_parse_semester_form(sem)
			db.session.commit()
			flash("学期信息已更新。", "success")
			return redirect(url_for("semester_bp.list_semesters"))
		except ValueError as exc:
			flash(str(exc), "danger")
	return render_template("semester/form.html", semester=sem)


@semester_bp.route("/<int:semester_id>/activate", methods=["POST"])
@login_required
def activate_semester(semester_id: int):
	target = db.session.get(Semester, semester_id)
	if not target:
		flash("学期不存在。", "danger")
		return redirect(url_for("semester_bp.list_semesters"))

	Semester.query.update({Semester.status: "inactive"})
	target.status = "active"
	db.session.commit()
	flash(f"已激活学期：{target.name}", "success")
	return redirect(url_for("semester_bp.list_semesters"))


@semester_bp.route("/<int:semester_id>/copy")
@login_required
def copy_semester(semester_id: int):
	source = db.session.get(Semester, semester_id)
	if not source:
		flash("学期不存在。", "danger")
		return redirect(url_for("semester_bp.list_semesters"))

	copied = Semester(
		name=f"{source.name}-复制",
		period_code="",
		period_positive=source.period_positive,
		period_development=source.period_development,
		period_probationary=source.period_probationary,
		year=source.year,
		status="inactive",
		exam_weight=source.exam_weight,
		attendance_weight=source.attendance_weight,
		assignment_weight=source.assignment_weight,
		volunteer_weight=source.volunteer_weight,
		min_attendance_sessions=source.min_attendance_sessions,
		pass_threshold=source.pass_threshold,
		volunteer_target_hours=source.volunteer_target_hours,
	)
	db.session.add(copied)
	db.session.commit()
	flash("已复制学期配置。", "success")
	return redirect(url_for("semester_bp.list_semesters"))