import re
from io import BytesIO

from flask import Blueprint, flash, redirect, render_template, request, send_file, url_for
from flask_login import login_required
from openpyxl import Workbook

from authz import role_required
from models import NotificationTemplate, db


notifications_bp = Blueprint("notifications_bp", __name__)


@notifications_bp.route("/")
@login_required
def template_list():
	items = NotificationTemplate.query.order_by(NotificationTemplate.category.asc(), NotificationTemplate.id.desc()).all()
	categories = sorted({item.category for item in items})
	grouped = {}
	for item in items:
		grouped.setdefault(item.category, []).append(item)
	if request.args.get("export") == "1":
		wb = Workbook()
		ws = wb.active
		ws.append(["分类", "标题", "内容"])
		for item in items:
			ws.append([item.category, item.title, item.content])
		stream = BytesIO()
		wb.save(stream)
		stream.seek(0)
		return send_file(stream, as_attachment=True, download_name="通知模板.xlsx", mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
	return render_template("notifications/list.html", grouped=grouped, categories=categories)


@notifications_bp.route("/new", methods=["GET", "POST"])
@login_required
@role_required("admin")
def new_template():
	if request.method == "POST":
		title = (request.form.get("title") or "").strip()
		content = (request.form.get("content") or "").strip()
		if not title or not content:
			flash("标题和模板内容不能为空。", "danger")
			categories = [c[0] for c in db.session.query(NotificationTemplate.category).distinct().all()]
			return render_template("notifications/form.html", item=None, categories=categories)
		item = NotificationTemplate(
			title=title,
			category=(request.form.get("category") or "未分类").strip(),
			content=content,
		)
		db.session.add(item)
		db.session.commit()
		flash("模板已创建。", "success")
		return redirect(url_for("notifications_bp.template_list"))
	categories = [c[0] for c in db.session.query(NotificationTemplate.category).distinct().all()]
	return render_template("notifications/form.html", item=None, categories=categories)


@notifications_bp.route("/<int:item_id>/edit", methods=["GET", "POST"])
@login_required
@role_required("admin")
def edit_template(item_id: int):
	item = db.session.get(NotificationTemplate, item_id)
	if not item:
		flash("模板不存在。", "danger")
		return redirect(url_for("notifications_bp.template_list"))

	if request.method == "POST":
		title = (request.form.get("title") or "").strip()
		content = (request.form.get("content") or "").strip()
		if not title or not content:
			flash("标题和模板内容不能为空。", "danger")
			categories = [c[0] for c in db.session.query(NotificationTemplate.category).distinct().all()]
			return render_template("notifications/form.html", item=item, categories=categories)
		item.title = title
		item.category = (request.form.get("category") or "未分类").strip()
		item.content = content
		db.session.commit()
		flash("模板已更新。", "success")
		return redirect(url_for("notifications_bp.template_list"))
	categories = [c[0] for c in db.session.query(NotificationTemplate.category).distinct().all()]
	return render_template("notifications/form.html", item=item, categories=categories)


@notifications_bp.route("/<int:item_id>/delete", methods=["POST"])
@login_required
@role_required("admin")
def delete_template(item_id: int):
	item = db.session.get(NotificationTemplate, item_id)
	if not item:
		flash("模板不存在。", "danger")
		return redirect(url_for("notifications_bp.template_list"))
	db.session.delete(item)
	db.session.commit()
	flash("模板已删除。", "success")
	return redirect(url_for("notifications_bp.template_list"))


@notifications_bp.route("/cleanup-other", methods=["POST"])
@login_required
@role_required("admin")
def cleanup_other_category():
	deleted = NotificationTemplate.query.filter_by(category="其他").delete()
	db.session.commit()
	flash(f"已删除“其他”分类模板 {deleted} 条。", "success")
	return redirect(url_for("notifications_bp.template_list"))


@notifications_bp.route("/<int:item_id>/use", methods=["GET", "POST"])
@login_required
def use_template(item_id: int):
	item = db.session.get(NotificationTemplate, item_id)
	if not item:
		flash("模板不存在。", "danger")
		return redirect(url_for("notifications_bp.template_list"))

	variables = sorted(set(re.findall(r"\{\{\s*([^{}\s]+)\s*\}\}", item.content)))
	values = {v: request.values.get(v, "") for v in variables}
	rendered = item.content
	for key, val in values.items():
		rendered = re.sub(r"\{\{\s*" + re.escape(key) + r"\s*\}\}", val, rendered)

	return render_template("notifications/use.html", item=item, variables=variables, values=values, rendered=rendered)