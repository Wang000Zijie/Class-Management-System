from datetime import datetime
from io import BytesIO

from flask import Blueprint, flash, redirect, render_template, request, send_file, url_for
from flask_login import login_required
from openpyxl import Workbook

from models import Assignment, Attendance, CourseSession, Semester, Student, db


courses_bp = Blueprint("courses_bp", __name__)


def _current_semester():
	return Semester.query.filter_by(status="active").order_by(Semester.id.desc()).first()


def _ensure_session_note_tasks(semester_id: int, session_id: int) -> None:
	students = Student.query.filter_by(semester_id=semester_id, status="在读").all()
	for stu in students:
		exists = Assignment.query.filter_by(
			student_id=stu.id,
			semester_id=semester_id,
			session_id=session_id,
			type="课堂笔记",
		).first()
		if not exists:
			db.session.add(
				Assignment(
					student_id=stu.id,
					semester_id=semester_id,
					session_id=session_id,
					type="课堂笔记",
					status="未提交",
				)
			)


@courses_bp.route("/")
@login_required
def list_courses():
	semester = _current_semester()
	if not semester:
		flash("请先激活学期。", "warning")
		return redirect(url_for("semester_bp.list_semesters"))

	sessions = CourseSession.query.filter_by(semester_id=semester.id).order_by(CourseSession.session_number.asc()).all()
	rows = []
	for item in sessions:
		present = Attendance.query.filter_by(session_id=item.id).filter(Attendance.status.in_(["到场", "线上"])).count()
		absent = Attendance.query.filter_by(session_id=item.id, status="缺席").count()
		rows.append({"session": item, "present": present, "absent": absent})

	if request.args.get("export") == "1":
		wb = Workbook()
		ws = wb.active
		ws.append(["课次", "主题", "日期", "地点", "形式", "主讲人", "到场/线上", "缺席"])
		for row in rows:
			sess = row["session"]
			ws.append([
				sess.session_number,
				sess.theme,
				str(sess.date),
				sess.location,
				"线上" if sess.is_online else "线下",
				sess.lecturer,
				row["present"],
				row["absent"],
			])
		stream = BytesIO()
		wb.save(stream)
		stream.seek(0)
		return send_file(stream, as_attachment=True, download_name="课次列表.xlsx", mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

	return render_template("courses/list.html", rows=rows)


@courses_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_course():
	semester = _current_semester()
	if not semester:
		flash("请先激活学期。", "warning")
		return redirect(url_for("semester_bp.list_semesters"))

	next_no = (db.session.query(db.func.max(CourseSession.session_number)).filter_by(semester_id=semester.id).scalar() or 0) + 1
	if request.method == "POST":
		date_raw = request.form.get("date")
		session_number = int(request.form.get("session_number") or next_no)
		theme = (request.form.get("theme") or "").strip()
		if session_number < 1 or not theme:
			flash("课次编号必须大于0，主题为必填。", "danger")
			return render_template("courses/form.html", course=None, next_no=next_no)
		course = CourseSession(
			semester_id=semester.id,
			session_number=session_number,
			theme=theme,
			date=datetime.strptime(date_raw, "%Y-%m-%d").date() if date_raw else datetime.utcnow().date(),
			location=(request.form.get("location") or "").strip(),
			is_online=request.form.get("is_online") == "on",
			meeting_link=(request.form.get("meeting_link") or "").strip(),
			lecturer=(request.form.get("lecturer") or "").strip(),
			notes=(request.form.get("notes") or "").strip(),
		)
		db.session.add(course)
		db.session.flush()
		_ensure_session_note_tasks(semester.id, course.id)
		db.session.commit()
		flash("课次已创建。", "success")
		return redirect(url_for("courses_bp.list_courses"))
	return render_template("courses/form.html", course=None, next_no=next_no)


@courses_bp.route("/<int:course_id>/edit", methods=["GET", "POST"])
@login_required
def edit_course(course_id: int):
	course = db.session.get(CourseSession, course_id)
	if not course:
		flash("课次不存在。", "danger")
		return redirect(url_for("courses_bp.list_courses"))

	if request.method == "POST":
		date_raw = request.form.get("date")
		session_number = int(request.form.get("session_number") or course.session_number)
		theme = (request.form.get("theme") or "").strip()
		if session_number < 1 or not theme:
			flash("课次编号必须大于0，主题为必填。", "danger")
			return render_template("courses/form.html", course=course, next_no=course.session_number)
		course.session_number = session_number
		course.theme = theme
		course.date = datetime.strptime(date_raw, "%Y-%m-%d").date() if date_raw else course.date
		course.location = (request.form.get("location") or "").strip()
		course.is_online = request.form.get("is_online") == "on"
		course.meeting_link = (request.form.get("meeting_link") or "").strip()
		course.lecturer = (request.form.get("lecturer") or "").strip()
		course.notes = (request.form.get("notes") or "").strip()
		db.session.commit()
		flash("课次信息已更新。", "success")
		return redirect(url_for("courses_bp.list_courses"))
	return render_template("courses/form.html", course=course, next_no=course.session_number)


@courses_bp.route("/<int:course_id>/delete", methods=["POST"])
@login_required
def delete_course(course_id: int):
	course = db.session.get(CourseSession, course_id)
	if not course:
		flash("课次不存在。", "danger")
		return redirect(url_for("courses_bp.list_courses"))
	db.session.delete(course)
	db.session.commit()
	flash("课次已删除，关联出勤记录已清理。", "success")
	return redirect(url_for("courses_bp.list_courses"))


@courses_bp.route("/<int:course_id>/detail")
@login_required
def course_detail(course_id: int):
	course = db.session.get(CourseSession, course_id)
	if not course:
		flash("课次不存在。", "danger")
		return redirect(url_for("courses_bp.list_courses"))

	students = Student.query.filter_by(semester_id=course.semester_id).order_by(Student.stage.asc(), Student.student_id.asc()).all()
	attendance_map = {a.student_id: a for a in Attendance.query.filter_by(session_id=course.id).all()}
	grouped = {"积极分子": [], "发展对象": [], "预备党员": []}
	present_count = 0
	for stu in students:
		rec = attendance_map.get(stu.id)
		status = rec.status if rec else "未记录"
		if status in ["到场", "线上"]:
			present_count += 1
		grouped.setdefault(stu.stage, []).append({"student": stu, "status": status})

	total = len(students)
	rate = round((present_count * 100 / total), 2) if total else 0
	return render_template("courses/detail.html", course=course, grouped=grouped, present_count=present_count, total=total, rate=rate)