import json
import os
import re
from datetime import datetime
from hashlib import md5

from flask import Blueprint, current_app, flash, render_template, request
from flask_login import login_required

from authz import role_required
from models import Assignment, CourseSession, ExamRecord, Semester, Student, VolunteerRecord, db
from services.deepseek_client import chat_json


ai_tools_bp = Blueprint("ai_tools_bp", __name__)

VALID_STAGES = {"积极分子", "发展对象", "预备党员"}
VALID_ASSIGNMENT_STATUSES = {"未提交", "已提交", "已通过", "已退回"}
VALID_STUDENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-]{2,29}$")
NAME_TRAILING_NOISE_RE = re.compile(r"(考试|成绩|作业|志愿|更新|备注|通过|未提交|已提交|已通过|已退回).*$")
NATURAL_SPLIT_RE = re.compile(r"[。；;\n]|(?:以及|还有|并且|然后)")


def _norm_name_for_match(value) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    return re.sub(r"[\s\-_,，。；;、()（）\[\]【】]", "", text)


def _normalize_student_id(value) -> str | None:
    text = _norm_unknown(value)
    if not text:
        return None
    text = str(text).strip()
    upper_text = text.upper()
    if re.fullmatch(r"AI-[A-Z0-9]{4,20}", upper_text):
        return upper_text
    if VALID_STUDENT_ID_RE.fullmatch(text):
        return text
    return None


def _clean_name(value) -> str | None:
    text = _norm_unknown(value)
    if not text:
        return None
    text = str(text).strip()
    text = re.sub(r"[（(].*?[）)]", "", text)
    text = NAME_TRAILING_NOISE_RE.sub("", text)
    text = re.sub(r"[0-9０-９]+(?:分|小时|h|H)?$", "", text)
    text = text.strip("，,；;。:：-_ ")
    return text or None


def _extract_number_by_keywords(text: str, keywords: list[str]) -> float | None:
    text = str(text or "")
    for kw in keywords:
        pattern = rf"{re.escape(kw)}[^0-9\-]{{0,8}}(-?\d+(?:\.\d+)?)"
        match = re.search(pattern, text)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                continue
    return None


def _guess_name_from_clause(clause: str) -> str | None:
    clause = str(clause or "")
    # Try common imperative patterns first.
    patterns = [
        r"(?:更新一下|更新|修改|把|将|给)?([\u4e00-\u9fff]{2,8})(?:的数据|同学|，|,|的|\s|$)",
        r"([\u4e00-\u9fff]{2,8})(?:，|,|他的|她的|的|\s|$)",
    ]
    stop_words = {
        "更新一下",
        "更新",
        "修改",
        "数据",
        "同学",
        "他的",
        "她的",
        "考试",
        "分数",
        "成绩",
        "志愿",
        "时长",
    }
    for pattern in patterns:
        match = re.search(pattern, clause)
        if not match:
            continue
        cand = _clean_name(match.group(1))
        if not cand:
            continue
        if cand in stop_words:
            continue
        if any(word in cand for word in ["考试", "成绩", "志愿", "更新", "数据"]):
            continue
        return cand
    return None


def _fallback_parse_sync_with_students(text: str, students: list[Student]) -> dict:
    records_map: dict[str, dict] = {}

    clauses = [item.strip() for item in NATURAL_SPLIT_RE.split(text) if item and item.strip()]
    sorted_students = sorted(students, key=lambda item: len(item.name or ""), reverse=True)

    for clause in clauses:
        matched_students = [stu for stu in sorted_students if stu.name and stu.name in clause]
        score = _extract_number_by_keywords(clause, ["考试分数", "考试成绩", "考试", "分数", "成绩"])
        volunteer = _extract_number_by_keywords(clause, ["志愿时长", "志愿服务", "志愿"])

        if matched_students:
            for stu in matched_students:
                rec = records_map.setdefault(
                    stu.name,
                    {
                        "name": stu.name,
                        "student_id": stu.student_id,
                        "department": stu.department,
                        "stage": stu.stage,
                        "group_number": stu.group_number,
                        "note_completed": None,
                        "note_total": None,
                        "reflection_status": None,
                        "summary_status": None,
                        "exam_score": None,
                        "volunteer_hours": None,
                    },
                )
                if score is not None:
                    rec["exam_score"] = score
                if volunteer is not None:
                    rec["volunteer_hours"] = volunteer
            continue

        guessed_name = _guess_name_from_clause(clause)
        if guessed_name and (score is not None or volunteer is not None):
            rec = records_map.setdefault(
                guessed_name,
                {
                    "name": guessed_name,
                    "student_id": None,
                    "department": None,
                    "stage": None,
                    "group_number": None,
                    "note_completed": None,
                    "note_total": None,
                    "reflection_status": None,
                    "summary_status": None,
                    "exam_score": None,
                    "volunteer_hours": None,
                },
            )
            if score is not None:
                rec["exam_score"] = score
            if volunteer is not None:
                rec["volunteer_hours"] = volunteer

    if records_map:
        return {"records": list(records_map.values())}
    return _fallback_parse_sync(text)


def _to_int(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = _norm_unknown(value)
    if not text:
        return None
    match = re.search(r"-?\d+", text)
    return int(match.group(0)) if match else None


def _to_float(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = _norm_unknown(value)
    if not text:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(match.group(0)) if match else None


def _is_low_confidence_name(name: str | None) -> bool:
    cleaned_name = _clean_name(name)
    if not cleaned_name:
        return True
    text = str(cleaned_name).strip()
    if len(text) < 2 or len(text) > 12:
        return True
    if any(ch.isdigit() for ch in text):
        return True
    noise_tokens = ["考试", "作业", "志愿", "更新", "备注", "通过", "未提交", "已提交"]
    return any(token in text for token in noise_tokens)


def _normalize_record(row: dict) -> dict:
    data = row if isinstance(row, dict) else {}
    stage = _norm_unknown(data.get("stage"))
    reflection_status = _norm_unknown(data.get("reflection_status"))
    summary_status = _norm_unknown(data.get("summary_status"))

    note_completed = _to_int(data.get("note_completed"))
    note_total = _to_int(data.get("note_total"))
    if note_completed is not None and note_completed < 0:
        note_completed = None
    if note_total is not None and note_total < 0:
        note_total = None

    exam_score = _to_float(data.get("exam_score"))
    if exam_score is not None and not (0 <= exam_score <= 100):
        exam_score = None
    volunteer_hours = _to_float(data.get("volunteer_hours"))
    if volunteer_hours is not None and volunteer_hours < 0:
        volunteer_hours = None
    group_number = _to_int(data.get("group_number"))
    if group_number is not None and group_number <= 0:
        group_number = None

    return {
        "name": _clean_name(data.get("name") or data.get("student_name")),
        "student_id": _normalize_student_id(data.get("student_id")),
        "department": _norm_unknown(data.get("department")),
        "stage": stage if stage in VALID_STAGES else None,
        "group_number": group_number,
        "note_completed": note_completed,
        "note_total": note_total,
        "reflection_status": reflection_status if reflection_status in VALID_ASSIGNMENT_STATUSES else None,
        "summary_status": summary_status if summary_status in VALID_ASSIGNMENT_STATUSES else None,
        "exam_score": exam_score,
        "volunteer_hours": volunteer_hours,
    }


def _extract_name_hints(source_text: str) -> list[str]:
    hints: set[str] = set()
    for raw_line in source_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = _split_fields(line)
        if not parts:
            continue
        name_hint = _clean_name(parts[0])
        name_norm = _norm_name_for_match(name_hint)
        if name_norm:
            hints.add(name_norm)
    return sorted(hints)


def _select_context_students(source_text: str, students: list[Student]) -> list[Student]:
    hints = _extract_name_hints(source_text)
    if not hints:
        return students
    candidates = []
    for stu in students:
        stu_name_norm = _norm_name_for_match(stu.name)
        if any(hint in stu_name_norm or stu_name_norm in hint for hint in hints):
            candidates.append(stu)

    # Keep context compact when we can narrow to a meaningful subset.
    if 0 < len(candidates) <= 120:
        return candidates
    return students


def _build_student_context(students: list[Student]) -> str:
    payload = [
        {
            "name": stu.name,
            "student_id": stu.student_id,
            "department": stu.department,
            "stage": stu.stage,
            "group_number": stu.group_number,
        }
        for stu in students
    ]
    return json.dumps(payload, ensure_ascii=False)


def _compose_user_prompt_with_context(source_text: str, students: list[Student]) -> str:
    context_students = _select_context_students(source_text, students)
    context_json = _build_student_context(context_students)
    return (
        "以下是当前学期学员名册（JSON 数组），请仅用于学员识别与字段标准化：\n"
        f"{context_json}\n\n"
        "规则补充：\n"
        "1) 输入名字不完整（如只有姓或部分名字）时，优先结合名册和同条记录中的支部/阶段/小组进行匹配。\n"
        "2) 如果能唯一确定到名册学员，请补全 name 与 student_id。\n"
        "3) 无法唯一确定时，不要乱猜，student_id 必须设为 null。\n"
        "4) 严禁把考试分数、作业状态、控制词（如“更新一下”）写入 name 或 student_id。\n"
        "5) 若文本含“郑常见考试100分”这类混合字段，应拆分为 name=郑常见、exam_score=100。\n"
        "6) 只输出 JSON。\n\n"
        "原始待解析文本：\n"
        f"{source_text}"
    )


def _resolve_ai_runtime_config() -> tuple[dict, str, str, str, bool]:
    persisted = _read_persistent_settings()

    persisted_key = str(persisted.get("DEEPSEEK_API_KEY") or "").strip()
    config_key = str(current_app.config.get("DEEPSEEK_API_KEY", "")).strip()

    if persisted_key.startswith("sk-"):
        api_key = persisted_key
    elif config_key.startswith("sk-"):
        api_key = config_key
    else:
        api_key = persisted_key or config_key

    base_url = (
        str(persisted.get("DEEPSEEK_BASE_URL") or "").strip()
        or str(current_app.config.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")).strip()
        or "https://api.deepseek.com"
    )
    model = (
        str(persisted.get("DEEPSEEK_MODEL") or "").strip()
        or str(current_app.config.get("DEEPSEEK_MODEL", "deepseek-chat")).strip()
        or "deepseek-chat"
    )
    return persisted, api_key, base_url, model, bool(api_key and api_key.startswith("sk-"))


def _settings_file_path() -> str:
    instance_dir = os.path.join(current_app.root_path, "instance")
    os.makedirs(instance_dir, exist_ok=True)
    return os.path.join(instance_dir, "app_settings.json")


def _history_file_path() -> str:
    instance_dir = os.path.join(current_app.root_path, "instance")
    os.makedirs(instance_dir, exist_ok=True)
    return os.path.join(instance_dir, "ai_sync_history.jsonl")


def _sync_prompt_file_path() -> str:
    return os.path.join(current_app.root_path, "ai_agent_prompts", "smart_sync_prompt.txt")


def _load_sync_prompt() -> str:
    path = _sync_prompt_file_path()
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            text = f.read().strip()
            if text:
                return text
    return (
        "你是教务数据同步器。仅输出 JSON。"
        "返回 records 数组，每项字段均可选："
        "name, student_id, department, stage, group_number,"
        "note_completed, note_total, reflection_status, summary_status,"
        "exam_score, volunteer_hours。"
        "未知值请输出 null；如输入包含图片说明、截图标记、无关描述，请忽略。"
    )


def _read_persistent_settings() -> dict:
    path = _settings_file_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_persistent_settings(settings: dict) -> None:
    path = _settings_file_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


def _append_history(action: str, raw_text: str, parsed: dict, summary: dict) -> None:
    record = {
        "time": datetime.utcnow().isoformat(),
        "action": action,
        "summary": summary,
        "raw_text": raw_text,
        "parsed": parsed,
    }
    with open(_history_file_path(), "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _current_semester():
    return Semester.query.filter_by(status="active").order_by(Semester.id.desc()).first()


def _norm_unknown(value):
    if value is None:
        return None
    text = str(value).strip().strip("，,；;。")
    if text in ["", "未知", "无", "-", "--", "N/A", "n/a", "暂无", "未填写"]:
        return None
    return text


def _split_fields(line: str):
    normalized = (
        line.replace("\t", ",")
        .replace("，", ",")
        .replace("；", ",")
        .replace(";", ",")
        .replace("、", ",")
    )
    return [p.strip() for p in normalized.split(",") if p.strip()]


def _fallback_parse_students(text: str):
    rows = []
    current_department = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        # Line like "先进控制与智能系统科研团队党支部" acts as context header.
        if all(sep not in line for sep in [",", "，", "\t"]) and "党支部" in line:
            current_department = line
            continue

        parts = _split_fields(line)
        if len(parts) < 1:
            continue

        # Flexible mapping for 1~5+ fields: name, student_id, department, stage, group_number
        name = _norm_unknown(parts[0])
        student_id = _norm_unknown(parts[1]) if len(parts) > 1 else None
        department = _norm_unknown(parts[2]) if len(parts) > 2 else None
        stage = _norm_unknown(parts[3]) if len(parts) > 3 else None
        group_raw = _norm_unknown(parts[4]) if len(parts) > 4 else None

        if department is None:
            department = current_department

        group_number = int(group_raw) if group_raw and str(group_raw).isdigit() else None

        if not name:
            continue

        rows.append(
            {
                "name": name,
                "student_id": student_id,
                "department": department,
                "stage": stage,
                "group_number": group_number,
            }
        )
    return {"students": rows}


def _fallback_parse_assignments(text: str):
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = _split_fields(line)
        if len(parts) < 4:
            continue
        note_completed = 0
        note_total = 0
        if "/" in parts[1]:
            a, b = parts[1].split("/", 1)
            note_completed = int(a) if a.isdigit() else 0
            note_total = int(b) if b.isdigit() else 0
        rows.append(
            {
                "student_name": _norm_unknown(parts[0]),
                "note_completed": note_completed,
                "note_total": note_total,
                "reflection_status": _norm_unknown(parts[2]),
                "summary_status": _norm_unknown(parts[3]),
            }
        )
    return {"assignments": rows}


def _fallback_parse_sync(text: str):
    base = _fallback_parse_students(text)
    records = []
    for row in base.get("students", []):
        records.append(
            {
                "name": row.get("name"),
                "student_id": row.get("student_id"),
                "department": row.get("department"),
                "stage": row.get("stage"),
                "group_number": row.get("group_number"),
            }
        )
    return {"records": records}


def _ensure_assignment_tasks(student: Student, semester: Semester):
    sessions = CourseSession.query.filter_by(semester_id=semester.id).order_by(CourseSession.session_number.asc()).all()
    for session in sessions:
        exists = Assignment.query.filter_by(
            student_id=student.id,
            semester_id=semester.id,
            session_id=session.id,
            type="课堂笔记",
        ).first()
        if not exists:
            db.session.add(
                Assignment(
                    student_id=student.id,
                    semester_id=semester.id,
                    session_id=session.id,
                    type="课堂笔记",
                    status="未提交",
                )
            )

    for tp in ["个人心得", "小组讨论纪要"]:
        exists = Assignment.query.filter_by(
            student_id=student.id,
            semester_id=semester.id,
            session_id=None,
            type=tp,
        ).first()
        if not exists:
            db.session.add(
                Assignment(
                    student_id=student.id,
                    semester_id=semester.id,
                    session_id=None,
                    type=tp,
                    status="未提交",
                )
            )


def _resolve_student(semester: Semester, row: dict, students: list[Student] | None = None):
    sid = _normalize_student_id(row.get("student_id"))
    name = _clean_name(row.get("name") or row.get("student_name"))
    stage = _norm_unknown(row.get("stage"))
    students = students if students is not None else Student.query.filter_by(semester_id=semester.id).all()
    stu = None
    if sid and stage in VALID_STAGES:
        stu = next((item for item in students if item.student_id == sid and item.stage == stage), None)
    if not stu and sid:
        stu = next((item for item in students if item.student_id == sid), None)
    if not stu and name:
        stu = next((item for item in students if item.name == name), None)

    if not stu and name:
        # Fuzzy candidate matching for partial names such as "郑".
        name_norm = _norm_name_for_match(name)
        if name_norm:
            candidates = [
                item
                for item in students
                if name_norm in _norm_name_for_match(item.name) or _norm_name_for_match(item.name) in name_norm
            ]

            department = _norm_unknown(row.get("department"))
            if department and len(candidates) > 1:
                dep_norm = _norm_name_for_match(department)
                filtered = [
                    item
                    for item in candidates
                    if dep_norm and dep_norm in _norm_name_for_match(item.department or "")
                ]
                if filtered:
                    candidates = filtered

            if stage in VALID_STAGES and len(candidates) > 1:
                filtered = [item for item in candidates if item.stage == stage]
                if filtered:
                    candidates = filtered

            group_number = _to_int(row.get("group_number"))
            if group_number is not None and len(candidates) > 1:
                filtered = [item for item in candidates if item.group_number == group_number]
                if filtered:
                    candidates = filtered

            if len(candidates) == 1:
                stu = candidates[0]

    return stu, sid, name


def _ensure_student_id(semester: Semester, name: str, sid: str | None) -> str:
    if sid:
        return sid
    digest = md5(f"{semester.id}:{name}".encode("utf-8")).hexdigest()[:6].upper()
    return f"AI-{digest}"


@ai_tools_bp.route("/", methods=["GET", "POST"])
@login_required
@role_required("admin", "staff")
def index():
    semester = _current_semester()
    _persisted, api_key, base_url, model, api_loaded = _resolve_ai_runtime_config()
    if not semester:
        flash("请先激活学期后再进行 AI 智能同步。", "warning")
        return render_template(
            "ai_tools/index.html",
            api_loaded=api_loaded,
            deepseek_base_url=base_url,
            deepseek_model=model,
        )

    if request.method == "POST":
        source_text = (request.form.get("source_text") or "").strip()
        if not source_text:
            flash("请输入待处理文本。", "danger")
            return render_template(
                "ai_tools/index.html",
                api_loaded=api_loaded,
                deepseek_base_url=base_url,
                deepseek_model=model,
            )

        semester_students = Student.query.filter_by(semester_id=semester.id).order_by(Student.id.asc()).all()

        try:
            system_prompt = _load_sync_prompt()
            if api_key:
                if not api_key.startswith("sk-"):
                    flash("DeepSeek API Key 格式异常，已回退本地解析。", "warning")
                    parsed = _fallback_parse_sync_with_students(source_text, semester_students)
                else:
                    try:
                        ai_user_prompt = _compose_user_prompt_with_context(source_text, semester_students)
                        parsed = chat_json(api_key, base_url, model, system_prompt, ai_user_prompt)
                    except Exception as exc:
                        flash(f"DeepSeek 解析失败，已回退本地解析：{exc}", "danger")
                        parsed = _fallback_parse_sync_with_students(source_text, semester_students)
            else:
                parsed = _fallback_parse_sync_with_students(source_text, semester_students)

            created = 0
            updated = 0
            assignment_changed = 0
            exam_changed = 0
            volunteer_changed = 0

            unresolved_records = 0
            normalized_records = [_normalize_record(row) for row in parsed.get("records", [])]

            for row in normalized_records:
                stu, sid, name = _resolve_student(semester, row, semester_students)
                if not stu:
                    if not name or _is_low_confidence_name(name):
                        unresolved_records += 1
                        continue
                    stu = Student(
                        semester_id=semester.id,
                        name=name,
                        student_id=_ensure_student_id(semester, name, sid),
                        stage=row.get("stage") or "积极分子",
                        status="在读",
                    )
                    db.session.add(stu)
                    db.session.flush()
                    semester_students.append(stu)
                    created += 1
                else:
                    updated += 1

                if sid:
                    stu.student_id = sid
                if name:
                    stu.name = name
                department = _norm_unknown(row.get("department"))
                if department:
                    stu.department = department
                stage = row.get("stage")
                if stage in VALID_STAGES:
                    stu.stage = stage
                group = _to_int(row.get("group_number"))
                if group is not None:
                    stu.group_number = group

                _ensure_assignment_tasks(stu, semester)

                note_completed = _to_int(row.get("note_completed"))
                if note_completed is not None:
                    notes = (
                        Assignment.query.filter_by(student_id=stu.id, semester_id=semester.id, type="课堂笔记")
                        .order_by(Assignment.session_id.asc())
                        .all()
                    )
                    for idx, item in enumerate(notes):
                        item.status = "已通过" if idx < note_completed else "未提交"
                    assignment_changed += 1

                for tp, key in [("个人心得", "reflection_status"), ("小组讨论纪要", "summary_status")]:
                    st = _norm_unknown(row.get(key))
                    if st in VALID_ASSIGNMENT_STATUSES:
                        target = Assignment.query.filter_by(
                            student_id=stu.id,
                            semester_id=semester.id,
                            type=tp,
                            session_id=None,
                        ).first()
                        if target:
                            target.status = st
                            assignment_changed += 1

                exam_score = _to_float(row.get("exam_score"))
                if exam_score is not None and 0 <= exam_score <= 100:
                    rec = ExamRecord.query.filter_by(student_id=stu.id, semester_id=semester.id).first()
                    if not rec:
                        rec = ExamRecord(student_id=stu.id, semester_id=semester.id)
                        db.session.add(rec)
                    rec.score = exam_score
                    rec.exam_time = datetime.utcnow()
                    exam_changed += 1

                volunteer_hours = _to_float(row.get("volunteer_hours"))
                if volunteer_hours is not None and volunteer_hours >= 0:
                    db.session.add(
                        VolunteerRecord(
                            student_id=stu.id,
                            semester_id=semester.id,
                            activity_name="AI导入补录",
                            hours=volunteer_hours,
                            proof_note="AI 同步导入",
                            verified=False,
                        )
                    )
                    volunteer_changed += 1

            db.session.commit()
            summary_text = (
                f"智能同步完成：新增学员 {created}，更新学员 {updated}，"
                f"作业更新 {assignment_changed}，考试更新 {exam_changed}，志愿更新 {volunteer_changed}。"
            )
            if unresolved_records:
                summary_text += f" 有 {unresolved_records} 条记录未能可靠匹配学员，已跳过。"
            flash(summary_text, "success")
            _append_history(
                "sync",
                source_text,
                parsed,
                {
                    "created": created,
                    "updated": updated,
                    "assignment_changed": assignment_changed,
                    "exam_changed": exam_changed,
                    "volunteer_changed": volunteer_changed,
                    "unresolved_records": unresolved_records,
                },
            )

        except Exception as exc:
            db.session.rollback()
            flash(f"AI 处理失败：{exc}", "danger")

    return render_template(
        "ai_tools/index.html",
        api_loaded=api_loaded,
        deepseek_base_url=base_url,
        deepseek_model=model,
    )


@ai_tools_bp.route("/save-config", methods=["POST"])
@login_required
@role_required("admin")
def save_config():
    try:
        existing = _read_persistent_settings()
        key = (request.form.get("deepseek_api_key") or "").strip()
        base_url = (request.form.get("deepseek_base_url") or "").strip() or "https://api.deepseek.com"
        model = (request.form.get("deepseek_model") or "").strip() or "deepseek-chat"

        if key:
            existing["DEEPSEEK_API_KEY"] = key
        existing["DEEPSEEK_BASE_URL"] = base_url
        existing["DEEPSEEK_MODEL"] = model
        _write_persistent_settings(existing)
        flash("DeepSeek 配置已保存，下一次智能同步立即生效。", "success")
    except Exception as exc:
        flash(f"保存配置失败: {exc}", "danger")

    settings = existing if "existing" in locals() else {}
    active_key = str(settings.get("DEEPSEEK_API_KEY") or "").strip()
    active_base_url = settings.get("DEEPSEEK_BASE_URL") or (base_url if "base_url" in locals() else "https://api.deepseek.com")
    active_model = settings.get("DEEPSEEK_MODEL") or (model if "model" in locals() else "deepseek-chat")
    return render_template(
        "ai_tools/index.html",
        api_loaded=bool(active_key and active_key.startswith("sk-")),
        deepseek_base_url=active_base_url,
        deepseek_model=active_model,
    )