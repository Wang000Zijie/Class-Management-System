from collections import defaultdict
from datetime import datetime
from io import BytesIO

from flask import Blueprint, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from openpyxl import Workbook

from models import Assignment, CourseSession, Semester, Student, db


assignments_bp = Blueprint("assignments_bp", __name__)


def _current_semester():
	return Semester.query.filter_by(status="active").order_by(Semester.id.desc()).first()


def _ensure_student_assignment_set(student: Student, semester: Semester):
	sessions = CourseSession.query.filter_by(semester_id=semester.id).all()
	for session in sessions:
		if not Assignment.query.filter_by(student_id=student.id, semester_id=semester.id, session_id=session.id, type="课堂笔记").first():
			db.session.add(Assignment(student_id=student.id, semester_id=semester.id, session_id=session.id, type="课堂笔记", status="未提交"))
	for tp in ["个人心得", "小组讨论纪要"]:
		if not Assignment.query.filter_by(student_id=student.id, semester_id=semester.id, session_id=None, type=tp).first():
			db.session.add(Assignment(student_id=student.id, semester_id=semester.id, session_id=None, type=tp, status="未提交"))


def _ensure_assignment_sets_for_students(students: list[Student], semester: Semester) -> bool:
	if not students:
		return False

	sessions = CourseSession.query.filter_by(semester_id=semester.id).all()
	student_ids = [stu.id for stu in students]
	existing_keys = {
		(row[0], row[1], row[2])
		for row in db.session.query(Assignment.student_id, Assignment.type, Assignment.session_id)
		.filter(Assignment.semester_id == semester.id, Assignment.student_id.in_(student_ids))
		.all()
	}

	dirty = False
	for stu in students:
		for session in sessions:
			key = (stu.id, "课堂笔记", session.id)
			if key in existing_keys:
				continue
			db.session.add(
				Assignment(
					student_id=stu.id,
					semester_id=semester.id,
					session_id=session.id,
					type="课堂笔记",
					status="未提交",
				)
			)
			existing_keys.add(key)
			dirty = True

		for tp in ["个人心得", "小组讨论纪要"]:
			key = (stu.id, tp, None)
			if key in existing_keys:
				continue
			db.session.add(
				Assignment(
					student_id=stu.id,
					semester_id=semester.id,
					session_id=None,
					type=tp,
					status="未提交",
				)
			)
			existing_keys.add(key)
			dirty = True

	return dirty


@assignments_bp.route("/")
@login_required
def assignments_overview():
	semester = _current_semester()
	if not semester:
		flash("请先激活学期。", "warning")
		return redirect(url_for("semester_bp.list_semesters"))

	stage = request.args.get("stage", "全部")
	period = (request.args.get("period") or "全部").strip()
	group = request.args.get("group")
	uncompleted = request.args.get("uncompleted") == "1"

	query = Student.query.filter_by(semester_id=semester.id)
	if stage != "全部":
		query = query.filter_by(stage=stage)
	if group and group.isdigit():
		query = query.filter_by(group_number=int(group))
	students = query.order_by(Student.student_id.asc()).all()
	if _ensure_assignment_sets_for_students(students, semester):
		db.session.commit()

	total_sessions = CourseSession.query.filter_by(semester_id=semester.id).count()
	student_ids = [stu.id for stu in students]
	assignment_map: dict[int, list[Assignment]] = defaultdict(list)
	if student_ids:
		for item in Assignment.query.filter(Assignment.semester_id == semester.id, Assignment.student_id.in_(student_ids)).all():
			assignment_map[item.student_id].append(item)

	rows = []
	for stu in students:
		stu_period = semester.period_for_stage(stu.stage)
		if period != "全部" and stu_period != period:
			continue
		items = assignment_map.get(stu.id, [])
		notes = [i for i in items if i.type == "课堂笔记"]
		note_submitted = sum(1 for i in notes if i.status in ["已提交", "已通过"])
		reflection = next((i for i in items if i.type == "个人心得"), None)
		summary = next((i for i in items if i.type == "小组讨论纪要"), None)
		finished = note_submitted >= total_sessions and reflection and reflection.status == "已通过" and summary and summary.status == "已通过"
		if uncompleted and finished:
			continue
		rows.append({
			"student": stu,
			"stage_period": stu_period,
			"note_text": f"{note_submitted}/{total_sessions}",
			"reflection": reflection.status if reflection else "未提交",
			"summary": summary.status if summary else "未提交",
			"finished": bool(finished),
		})

	period_options = []
	for p in [semester.period_positive, semester.period_development, semester.period_probationary]:
		v = (p or "").strip()
		if v and v not in period_options:
			period_options.append(v)
	return render_template(
		"assignments/overview.html",
		rows=rows,
		stage=stage,
		period=period,
		period_options=period_options,
		group=group or "",
		uncompleted=uncompleted,
	)


@assignments_bp.route("/student/<int:student_id>", methods=["GET", "POST"])
@login_required
def student_assignment_detail(student_id: int):
	student = db.session.get(Student, student_id)
	if not student:
		flash("学员不存在。", "danger")
		return redirect(url_for("assignments_bp.assignments_overview"))

	semester = db.session.get(Semester, student.semester_id)
	_ensure_student_assignment_set(student, semester)

	if request.method == "POST":
		assignment_id = request.form.get("assignment_id", type=int)
		item = db.session.get(Assignment, assignment_id)
		if item and item.student_id == student.id:
			item.status = request.form.get("status") or item.status
			item.word_count = request.form.get("word_count", type=int) or 0
			item.review_note = (request.form.get("review_note") or "").strip()
			item.reviewed_by = current_user.username
			if item.status in ["已提交", "已通过"] and not item.submitted_at:
				item.submitted_at = datetime.utcnow()
			db.session.commit()
			flash("作业状态已更新。", "success")
		return redirect(url_for("assignments_bp.student_assignment_detail", student_id=student.id))

	items = Assignment.query.filter_by(student_id=student.id, semester_id=student.semester_id).order_by(Assignment.type.asc(), Assignment.id.asc()).all()
	return render_template("assignments/student_detail.html", student=student, items=items)


@assignments_bp.route("/batch_update", methods=["GET", "POST"])
@login_required
def batch_update():
	semester = _current_semester()
	if not semester:
		flash("请先激活学期。", "warning")
		return redirect(url_for("semester_bp.list_semesters"))

	assignment_type = request.values.get("assignment_type", "课堂笔记")
	students = Student.query.filter_by(semester_id=semester.id).order_by(Student.student_id.asc()).all()
	student_ids = [stu.id for stu in students]
	existing_items = []
	if student_ids:
		existing_items = (
			Assignment.query.filter(
				Assignment.semester_id == semester.id,
				Assignment.type == assignment_type,
				Assignment.student_id.in_(student_ids),
			)
			.order_by(Assignment.id.asc())
			.all()
		)
	existing_map: dict[int, Assignment] = {}
	for item in existing_items:
		existing_map.setdefault(item.student_id, item)

	if request.method == "POST" and request.form.get("save") == "1":
		for stu in students:
			item = existing_map.get(stu.id)
			if not item:
				item = Assignment(student_id=stu.id, semester_id=semester.id, type=assignment_type, status="未提交")
				db.session.add(item)
				existing_map[stu.id] = item
			item.word_count = request.form.get(f"word_{stu.id}", type=int) or 0
			item.status = request.form.get(f"status_{stu.id}") or item.status
			item.reviewed_by = current_user.username
			if item.status in ["已提交", "已通过"] and not item.submitted_at:
				item.submitted_at = datetime.utcnow()
		db.session.commit()
		flash("批量更新完成。", "success")
		return redirect(url_for("assignments_bp.batch_update", assignment_type=assignment_type))

	item_map = {stu.id: existing_map.get(stu.id) for stu in students}
	return render_template("assignments/batch.html", students=students, assignment_type=assignment_type, item_map=item_map)


@assignments_bp.route("/summary")
@login_required
def assignment_summary_export():
	semester = _current_semester()
	if not semester:
		flash("请先激活学期。", "warning")
		return redirect(url_for("assignments_bp.assignments_overview"))

	wb = Workbook()
	ws = wb.active
	ws.append(["姓名", "阶段", "课堂笔记", "个人心得", "小组讨论纪要", "是否全部完成"])

	students = Student.query.filter_by(semester_id=semester.id).order_by(Student.stage.asc(), Student.student_id.asc()).all()
	total_sessions = CourseSession.query.filter_by(semester_id=semester.id).count()
	student_ids = [stu.id for stu in students]
	assignment_map: dict[int, list[Assignment]] = defaultdict(list)
	if student_ids:
		for item in Assignment.query.filter(Assignment.semester_id == semester.id, Assignment.student_id.in_(student_ids)).all():
			assignment_map[item.student_id].append(item)

	for stu in students:
		items = assignment_map.get(stu.id, [])
		notes = [i for i in items if i.type == "课堂笔记" and i.status == "已通过"]
		reflection = next((i for i in items if i.type == "个人心得"), None)
		summary = next((i for i in items if i.type == "小组讨论纪要"), None)
		done = len(notes) >= total_sessions and reflection and reflection.status == "已通过" and summary and summary.status == "已通过"
		ws.append([
			stu.name,
			stu.stage,
			f"{len(notes)}/{total_sessions}",
			reflection.status if reflection else "未提交",
			summary.status if summary else "未提交",
			"是" if done else "否",
		])

	stream = BytesIO()
	wb.save(stream)
	stream.seek(0)
	return send_file(stream, as_attachment=True, download_name="作业汇总.xlsx", mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")