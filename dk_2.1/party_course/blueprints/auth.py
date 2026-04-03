from datetime import date
from io import BytesIO
import json
import os
import re

from flask import Blueprint, current_app, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import or_
from werkzeug.security import check_password_hash, generate_password_hash
from openpyxl import Workbook

from authz import ROLE_LABELS, admin_only_required, normalize_role, role_required, role_label
from models import Attendance, CourseSession, FinalScore, OperationLog, Semester, Student, User, db
from services.audit_log import log_operation
from services.deepseek_client import chat_json


auth_bp = Blueprint("auth_bp", __name__)

METHOD_LABELS = {
	"GET": "查询",
	"POST": "提交",
	"PUT": "更新",
	"PATCH": "修改",
	"DELETE": "删除",
}

ACTION_LABELS = {
	"auth_bp.login": "账号登录",
	"auth_bp.logout": "账号退出",
	"auth_bp.change_password": "修改密码",
	"auth_bp.account_list": "账号管理",
	"auth_bp.delete_account": "删除账号",
	"auth_bp.reset_account_password": "重置账号密码",
	"ai_tools_bp.index": "AI 智能同步",
	"ai_tools_bp.save_config": "保存 AI 配置",
	"scores_bp.calculate_scores": "计算综合成绩",
	"scores_bp.issue_certs": "发放证书编号",
	"scores_bp.exam_input": "录入考试成绩",
	"scores_bp.result_overview": "查看成绩总览",
	"students_bp.list_students": "查看学员列表",
	"students_bp.new_student": "新增学员",
	"students_bp.edit_student": "编辑学员",
	"students_bp.delete_student": "删除学员",
	"notifications_bp.new_template": "新建通知模板",
	"notifications_bp.edit_template": "编辑通知模板",
	"notifications_bp.delete_template": "删除通知模板",
	"notifications_bp.cleanup_other_category": "清空其他类模板",
}

DEFAULT_ROLE_PASSWORDS = {
	"minister": os.environ.get("DEFAULT_MINISTER_PASSWORD") or "buzhang123",
	"staff": os.environ.get("DEFAULT_STAFF_PASSWORD") or "ganshi123",
}


def _safe_next_url(next_url: str | None) -> str | None:
	next_url = (next_url or "").strip()
	if not next_url:
		return None
	if not next_url.startswith("/"):
		return None
	if next_url.startswith("//"):
		return None
	return next_url


def _settings_file_path() -> str:
	instance_dir = os.path.join(current_app.root_path, "instance")
	os.makedirs(instance_dir, exist_ok=True)
	return os.path.join(instance_dir, "app_settings.json")


def _read_local_settings() -> dict:
	path = _settings_file_path()
	if not os.path.exists(path):
		return {}
	try:
		with open(path, "r", encoding="utf-8") as f:
			data = json.load(f)
			return data if isinstance(data, dict) else {}
	except Exception:
		return {}


def _resolve_ai_config() -> tuple[str, str, str, bool]:
	settings = _read_local_settings()
	persisted_key = str(settings.get("DEEPSEEK_API_KEY") or "").strip()
	config_key = str(current_app.config.get("DEEPSEEK_API_KEY", "")).strip()

	if persisted_key.startswith("sk-"):
		api_key = persisted_key
	elif config_key.startswith("sk-"):
		api_key = config_key
	else:
		api_key = persisted_key or config_key

	base_url = (
		str(settings.get("DEEPSEEK_BASE_URL") or "").strip()
		or str(current_app.config.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")).strip()
		or "https://api.deepseek.com"
	)
	model = (
		str(settings.get("DEEPSEEK_MODEL") or "").strip()
		or str(current_app.config.get("DEEPSEEK_MODEL", "deepseek-chat")).strip()
		or "deepseek-chat"
	)
	return api_key, base_url, model, bool(api_key and api_key.startswith("sk-"))


def _log_translate_prompt_path() -> str:
	return os.path.join(current_app.root_path, "ai_agent_prompts", "log_translate_prompt.txt")


def _load_log_translate_prompt() -> str:
	path = _log_translate_prompt_path()
	if os.path.exists(path):
		with open(path, "r", encoding="utf-8") as f:
			text = f.read().strip()
			if text:
				return text
	return (
		"你是系统操作日志中文说明助手。"
		"输入是一组日志 JSON。"
		"请输出 JSON：{\"items\":[{\"id\":123,\"summary\":\"中文说明\"}]}。"
		"summary 要简洁、可执行、可审计，不要虚构。"
	)


def _method_label(method: str | None) -> str:
	return METHOD_LABELS.get((method or "").upper(), (method or "-").upper())


def _action_label(action: str | None) -> str:
	if not action:
		return "未知动作"
	return ACTION_LABELS.get(action, "系统操作")


def _path_label(path: str | None) -> str:
	path = (path or "").strip()
	if not path:
		return "-"
	prefix_labels = [
		("/auth/accounts", "账号管理"),
		("/auth/logs", "操作日志"),
		("/ai-tools", "AI 智能同步"),
		("/scores", "成绩与证书"),
		("/notifications", "通知模板"),
		("/students", "学员管理"),
		("/courses", "课程与签到管理"),
		("/attendance", "课程与签到管理"),
		("/assignments", "作业管理"),
		("/volunteers", "志愿时长"),
		("/semester", "学期管理"),
	]
	for prefix, label in prefix_labels:
		if path.startswith(prefix):
			return label
	return "其他模块"


def _format_detail_chinese(detail: str | None) -> str:
	detail = (detail or "").strip()
	if not detail:
		return "无补充信息"

	parts = [p.strip() for p in detail.split(";") if p.strip()]
	converted = []
	for part in parts:
		if part.startswith("status="):
			converted.append(f"响应状态：{part.split('=', 1)[1]}")
			continue
		if part.startswith("form="):
			payload = part.split("=", 1)[1]
			payload = re.sub(r"\bsemester_id\b", "学期", payload)
			payload = re.sub(r"\bstage\b", "阶段", payload)
			payload = re.sub(r"\bperiod\b", "期数", payload)
			payload = re.sub(r"\bsort\b", "排序", payload)
			converted.append(f"提交参数：{payload}")
			continue
		converted.append(part)
	return "；".join(converted)


def _local_cn_summary(item: OperationLog) -> str:
	status_text = f"状态码 {item.status_code}" if item.status_code is not None else "状态码未知"
	return (
		f"{role_label(item.role_snapshot)}账号“{item.username_snapshot}”"
		f"执行了“{_action_label(item.action)}”，"
		f"请求方式为{_method_label(item.method)}，"
		f"访问{_path_label(item.path)}，{status_text}。"
		f"{_format_detail_chinese(item.detail)}"
	)


def _translate_logs_with_ai(items: list[OperationLog]) -> dict[int, str]:
	local_map = {item.id: _local_cn_summary(item) for item in items}
	if not items:
		return local_map

	api_key, base_url, model, available = _resolve_ai_config()
	if not available:
		return local_map

	records = []
	for item in items:
		records.append(
			{
				"id": item.id,
				"username": item.username_snapshot,
				"role": item.role_snapshot,
				"action": item.action,
				"method": item.method,
				"path": item.path,
				"status_code": item.status_code,
				"detail": item.detail,
			}
		)

	try:
		system_prompt = _load_log_translate_prompt()
		user_prompt = json.dumps({"items": records}, ensure_ascii=False)
		translated = chat_json(api_key, base_url, model, system_prompt, user_prompt)
		for row in translated.get("items", []):
			if not isinstance(row, dict):
				continue
			row_id = row.get("id")
			summary = (row.get("summary") or "").strip()
			if isinstance(row_id, int) and summary:
				local_map[row_id] = summary
	except Exception:
		# Keep local Chinese summary as a deterministic fallback.
		pass

	return local_map


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
	next_url = _safe_next_url(request.args.get("next") or request.form.get("next"))
	if current_user.is_authenticated:
		return redirect(next_url or url_for("auth_bp.dashboard"))

	if request.method == "POST":
		username = (request.form.get("username") or "").strip()
		password = request.form.get("password") or ""
		user = User.query.filter_by(username=username).first()

		if user and check_password_hash(user.password_hash, password):
			login_user(user)
			return redirect(next_url or url_for("auth_bp.dashboard"))

		flash("用户名或密码错误。", "danger")

	return render_template("login.html", next_url=next_url or "")


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
	try:
		log_operation(
			action="auth_bp.logout",
			detail=f"user={current_user.username}",
			method="GET",
			path=request.path,
		)
	except Exception:
		db.session.rollback()
	logout_user()
	return redirect(url_for("auth_bp.login"))


@auth_bp.route("/auth/change_password", methods=["GET", "POST"])
@login_required
def change_password():
	if request.method == "POST":
		old_password = request.form.get("old_password") or ""
		new_password = request.form.get("new_password") or ""
		confirm_password = request.form.get("confirm_password") or ""

		if not check_password_hash(current_user.password_hash, old_password):
			flash("旧密码不正确。", "danger")
			return redirect(url_for("auth_bp.change_password"))

		if len(new_password) < 6:
			flash("新密码长度至少 6 位。", "danger")
			return redirect(url_for("auth_bp.change_password"))

		if new_password != confirm_password:
			flash("两次输入的新密码不一致。", "danger")
			return redirect(url_for("auth_bp.change_password"))

		current_user.password_hash = generate_password_hash(new_password)
		db.session.commit()
		flash("密码修改成功，请使用新密码登录。", "success")
		return redirect(url_for("auth_bp.dashboard"))

	return render_template("change_password.html")


@auth_bp.route("/auth/logs")
@login_required
@role_required("admin")
def operation_logs():
	role_filter = (request.args.get("role") or "全部").strip()
	username_filter = (request.args.get("username") or "").strip()
	keyword = (request.args.get("q") or "").strip()
	page = request.args.get("page", type=int) or 1
	per_page = request.args.get("per_page", type=int) or 20
	per_page = max(10, min(per_page, 100))
	cn_mode = (request.args.get("cn") or "1") == "1"

	query = OperationLog.query
	if role_filter != "全部":
		query = query.filter(OperationLog.role_snapshot == normalize_role(role_filter))
	if username_filter:
		query = query.filter(OperationLog.username_snapshot.contains(username_filter))
	if keyword:
		query = query.filter(
			or_(
				OperationLog.action.contains(keyword),
				OperationLog.path.contains(keyword),
				OperationLog.detail.contains(keyword),
			)
		)

	query = query.order_by(OperationLog.created_at.desc(), OperationLog.id.desc())

	if request.args.get("export") == "1":
		export_items = query.limit(5000).all()
		cn_map = _translate_logs_with_ai(export_items) if cn_mode else {item.id: _local_cn_summary(item) for item in export_items}
		wb = Workbook()
		ws = wb.active
		ws.append(["时间", "账号", "角色", "请求方式", "路径", "动作", "状态码", "原始详情", "中文说明"])
		for item in export_items:
			ws.append(
				[
					item.created_at.strftime("%Y-%m-%d %H:%M:%S") if item.created_at else "",
					item.username_snapshot,
					role_label(item.role_snapshot),
					_method_label(item.method),
					_path_label(item.path),
					_action_label(item.action),
					item.status_code if item.status_code is not None else "",
					item.detail or "",
					cn_map.get(item.id, ""),
				]
			)

		stream = BytesIO()
		wb.save(stream)
		stream.seek(0)
		return send_file(
			stream,
			as_attachment=True,
			download_name="操作日志.xlsx",
			mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
		)

	pagination = query.paginate(page=page, per_page=per_page, error_out=False)
	items = pagination.items
	cn_map = _translate_logs_with_ai(items) if cn_mode else {item.id: _local_cn_summary(item) for item in items}
	return render_template(
		"auth/logs.html",
		items=items,
		pagination=pagination,
		per_page=per_page,
		cn_mode=cn_mode,
		cn_map=cn_map,
		role_filter=role_filter,
		username_filter=username_filter,
		keyword=keyword,
		role_labels=ROLE_LABELS,
		role_label=role_label,
		method_label=_method_label,
		action_label=_action_label,
		path_label=_path_label,
		format_detail_chinese=_format_detail_chinese,
	)


@auth_bp.route("/auth/accounts", methods=["GET", "POST"])
@login_required
@admin_only_required
def account_list():
	if request.method == "POST":
		username = (request.form.get("username") or "").strip()
		real_name = (request.form.get("real_name") or "").strip()
		password = request.form.get("password") or ""
		role = normalize_role(request.form.get("role") or "staff")

		if not username:
			flash("用户名不能为空。", "danger")
			return redirect(url_for("auth_bp.account_list"))
		if len(password) < 6:
			flash("密码长度至少 6 位。", "danger")
			return redirect(url_for("auth_bp.account_list"))
		if User.query.filter_by(username=username).first():
			flash("用户名已存在，请更换。", "danger")
			return redirect(url_for("auth_bp.account_list"))

		user = User(
			username=username,
			password_hash=generate_password_hash(password),
			role=role,
			real_name=real_name or username,
		)
		db.session.add(user)
		db.session.commit()
		flash("账号已创建。", "success")
		return redirect(url_for("auth_bp.account_list"))

	role_order = {"admin": 0, "minister": 1, "staff": 2}
	users = User.query.order_by(User.created_at.asc(), User.id.asc()).all()
	users = sorted(users, key=lambda item: (role_order.get(item.role, 99), item.username.lower()))
	return render_template("auth/accounts.html", users=users, role_labels=ROLE_LABELS, role_label=role_label)


@auth_bp.route("/auth/accounts/<int:user_id>/delete", methods=["POST"])
@login_required
@admin_only_required
def delete_account(user_id: int):
	target = db.session.get(User, user_id)
	if not target:
		flash("账号不存在。", "danger")
		return redirect(url_for("auth_bp.account_list"))
	if target.id == current_user.id:
		flash("不能删除当前登录账号。", "danger")
		return redirect(url_for("auth_bp.account_list"))
	if target.username == "admin":
		flash("默认 admin 账号不允许删除。", "danger")
		return redirect(url_for("auth_bp.account_list"))

	db.session.delete(target)
	db.session.commit()
	flash("账号已删除。", "success")
	return redirect(url_for("auth_bp.account_list"))


@auth_bp.route("/auth/accounts/<int:user_id>/reset-password", methods=["POST"])
@login_required
@admin_only_required
def reset_account_password(user_id: int):
	target = db.session.get(User, user_id)
	if not target:
		flash("账号不存在。", "danger")
		return redirect(url_for("auth_bp.account_list"))
	if target.role not in DEFAULT_ROLE_PASSWORDS:
		flash("仅可重置部长/干事账号密码。", "danger")
		return redirect(url_for("auth_bp.account_list"))

	new_password = DEFAULT_ROLE_PASSWORDS[target.role]
	target.password_hash = generate_password_hash(new_password)
	db.session.commit()
	flash(f"账号 {target.username} 密码已重置为默认值。", "success")
	return redirect(url_for("auth_bp.account_list"))


@auth_bp.route("/dashboard")
@login_required
def dashboard():
	semester = Semester.query.filter_by(status="active").order_by(Semester.id.desc()).first()

	stats = {
		"total_students": 0,
		"stage_counts": {"积极分子": 0, "发展对象": 0, "预备党员": 0},
		"completed_sessions": 0,
		"total_sessions": 0,
		"attendance_rate": 0.0,
		"passed": 0,
		"failed": 0,
	}

	if semester:
		students = Student.query.filter_by(semester_id=semester.id).all()
		stats["total_students"] = len(students)
		for s in students:
			if s.stage in stats["stage_counts"]:
				stats["stage_counts"][s.stage] += 1

		sessions = CourseSession.query.filter_by(semester_id=semester.id).all()
		stats["total_sessions"] = len(sessions)
		today = date.today()
		stats["completed_sessions"] = sum(1 for item in sessions if item.date and item.date <= today)

		if students and sessions:
			student_ids = [s.id for s in students]
			session_ids = [c.id for c in sessions]
			valid_attendance = (
				Attendance.query.filter(Attendance.student_id.in_(student_ids), Attendance.session_id.in_(session_ids))
				.filter(Attendance.status.in_(["到场", "线上"]))
				.count()
			)
			stats["attendance_rate"] = round(valid_attendance * 100 / (len(students) * len(sessions)), 2)

		final_scores = FinalScore.query.filter_by(semester_id=semester.id).all()
		stats["passed"] = sum(1 for item in final_scores if item.is_passed)
		stats["failed"] = sum(1 for item in final_scores if not item.is_passed)

	return render_template("dashboard.html", stats=stats)