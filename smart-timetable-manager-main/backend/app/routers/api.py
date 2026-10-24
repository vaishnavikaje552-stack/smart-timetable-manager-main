from flask import Blueprint, request, jsonify
from sqlalchemy.orm import Session
from sqlalchemy import func, text

from ..database import get_db, DB_PATH
from ..models import Faculty, TimetableEntry, Subject, Room, ClassModel, FacultyAssignment, Conflict, Batch, SubstituteRequest
from ..security import verify_password, create_access_token
from ..auth import current_user, require_admin, APIError

api_router = Blueprint("api_v1", __name__, url_prefix="/api")


# ==========================================================
# 1. HEALTH CHECK (DATABASE CONNECTIVITY CHECK)
# ==========================================================

@api_router.route("/health", methods=["GET"])
def api_health():
    db = get_db()
    try:
        # Actively test database connection
        db.execute(text("SELECT 1"))
        faculty_count = db.query(Faculty).count()
        timetable_count = db.query(TimetableEntry).count()
        return jsonify({
            "status": "ok",
            "database": "connected",
            "database_file": DB_PATH,
            "records": {
                "faculty": faculty_count,
                "timetable": timetable_count
            },
            "service": "Smart Timetable Manager Flask Backend"
        }), 200
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e)
        }), 500


# ==========================================================
# 2. AUTHENTICATION (LOGIN, LOGOUT, ME)
# ==========================================================

@api_router.route("/auth/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or {}
    email_clean = str(data.get("email") or data.get("username") or "").strip().lower()
    fac_id_clean = str(data.get("faculty_id") or "").strip().upper()
    password = str(data.get("password") or "")
    requested_role = str(data.get("role") or "").strip().lower()

    if not email_clean or not password:
        raise APIError("Email / Username and Password are required.", 400)

    db = get_db()

    # Domain alias support (.edu vs .local)
    alt_email = (
        email_clean.replace("@edunova.edu", "@edunova.local")
        if "@edunova.edu" in email_clean
        else email_clean.replace("@edunova.local", "@edunova.edu")
    )

    user = db.query(Faculty).filter(
        (Faculty.email == email_clean) |
        (Faculty.email == alt_email) |
        (Faculty.faculty_id == email_clean.upper()) |
        (Faculty.faculty_id == fac_id_clean)
    ).first()

    # Designate Dr. Dhanraj R. Dhotre as primary HOD & Administrator
    if email_clean in ("admin", "adm-101", "hod", "drdhotre@edunova.edu", "dhotre", "admin@edunova.edu", "admin@edunova.local"):
        dhotre = db.query(Faculty).filter(
            (Faculty.faculty_id == "FAC-DRD") | (Faculty.email == "drdhotre@edunova.edu")
        ).first()
        if dhotre:
            user = dhotre
        elif not user:
            user = db.query(Faculty).filter(Faculty.role == "admin").first()

    if not user or not verify_password(password, user.password_hash):
        raise APIError("Invalid email, Faculty ID, or password.", 401)

    if not user.active:
        raise APIError("User account is inactive. Please contact the administrator.", 403)

    # If faculty ID was provided, verify it matches
    if fac_id_clean and user.faculty_id:
        if fac_id_clean.upper() != user.faculty_id.upper() and fac_id_clean.upper() != f"FAC-{user.id}":
            raise APIError("Faculty ID does not match the registered account.", 401)

    # Role enforcement: Do not allow faculty to log in as admin
    if requested_role == "admin" and user.role not in ("admin", "hod"):
        raise APIError("Access denied: You do not have administrator privileges.", 403)

    token = create_access_token(user.id, user.role)

    return jsonify({
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "faculty_id": user.faculty_id or (f"FAC-{100 + user.id}" if user.role == "faculty" else "ADM-101"),
            "name": user.name,
            "email": user.email,
            "role": user.role,
            "department": user.department
        }
    }), 200


@api_router.route("/auth/logout", methods=["POST"])
def api_logout():
    return jsonify({"message": "Logged out successfully"}), 200


@api_router.route("/auth/me", methods=["GET"])
@current_user
def api_auth_me(user: Faculty):
    return jsonify({
        "id": user.id,
        "faculty_id": user.faculty_id or (f"FAC-{100 + user.id}" if user.role == "faculty" else "ADM-101"),
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "department": user.department,
        "expertise": [x.strip() for x in user.expertise.split(",") if x.strip()] if user.expertise else []
    }), 200


# ==========================================================
# 3. FACULTY PROFILE & TIMETABLE
# ==========================================================

@api_router.route("/faculty/me", methods=["GET"])
@current_user
def api_faculty_me(user: Faculty):
    db = get_db()
    
    # Calculate scheduled classes, subjects, and batches
    entries = db.query(TimetableEntry).filter(TimetableEntry.faculty_id == user.id).all()
    assigned_classes = sorted(list({e.class_name for e in entries if e.class_name}))
    assigned_subjects = sorted(list({e.subject for e in entries if e.subject}))
    assigned_batches = sorted(list({e.batch for e in entries if e.batch}))

    # Fallback from FacultyAssignment table if timetable entries not yet populated
    if not assigned_classes:
        assignments = db.query(FacultyAssignment).filter(FacultyAssignment.faculty_id == user.id).all()
        assigned_classes = sorted(list({a.class_model.name for a in assignments if a.class_model}))
        assigned_subjects = sorted(list({a.subject.name for a in assignments if a.subject}))
        assigned_batches = sorted(list({a.batch for a in assignments if a.batch}))

    return jsonify({
        "id": user.id,
        "faculty_id": user.faculty_id or f"FAC-{100 + user.id}",
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "department": user.department,
        "expertise": [x.strip() for x in user.expertise.split(",") if x.strip()] if user.expertise else [],
        "max_hours": user.max_hours,
        "current_hours": len(entries),
        "assigned_classes": assigned_classes,
        "assigned_subjects": assigned_subjects,
        "assigned_batches": assigned_batches
    }), 200


@api_router.route("/faculty/timetable", methods=["GET"])
@current_user
def api_faculty_timetable(user: Faculty):
    day = request.args.get("day")
    class_name = request.args.get("class_name")
    session_type = request.args.get("session_type")
    academic_year = request.args.get("academic_year")

    db = get_db()
    query = db.query(TimetableEntry)

    # Non-admin only sees own timetable
    if user.role != "admin":
        query = query.filter(TimetableEntry.faculty_id == user.id)
    else:
        # Admin can view specified faculty or own
        target_fac_id = request.args.get("faculty_id", type=int)
        if target_fac_id:
            query = query.filter(TimetableEntry.faculty_id == target_fac_id)
        else:
            query = query.filter(TimetableEntry.faculty_id == user.id)

    if day:
        query = query.filter(TimetableEntry.day == day)
    if class_name:
        alt_class = class_name.replace(" ", "-") if " " in class_name else class_name.replace("-", " ")
        query = query.filter((TimetableEntry.class_name == class_name) | (TimetableEntry.class_name == alt_class))
    if session_type:
        query = query.filter(TimetableEntry.session_type == session_type)
    if academic_year:
        query = query.filter(TimetableEntry.academic_year == academic_year)

    entries = query.order_by(TimetableEntry.day, TimetableEntry.start_time).all()

    results = []
    for e in entries:
        fac_code = e.faculty.faculty_id if (e.faculty and e.faculty.faculty_id) else f"FAC-{e.faculty_id}"
        fac_name = e.faculty.name if e.faculty else ""
        sess_type = getattr(e, "session_type", "Practical" if e.is_lab else "Theory")
        results.append({
            "id": e.id,
            "day": e.day,
            "start_time": e.start_time,
            "end_time": e.end_time,
            "startTime": e.start_time,
            "endTime": e.end_time,
            "displayTime": f"{e.start_time} - {e.end_time}",
            "subject": e.subject,
            "class_name": e.class_name,
            "classDiv": e.class_name,
            "room": e.room,
            "faculty_id": e.faculty_id,
            "facultyId": fac_code,
            "faculty_name": fac_name,
            "facultyName": fac_name,
            "batch": e.batch,
            "is_lab": e.is_lab,
            "session_type": sess_type,
            "type": "Lab Practical" if e.is_lab else sess_type,
            "academic_year": getattr(e, "academic_year", None),
            "semester": getattr(e, "semester", None)
        })

    return jsonify(results), 200


# ==========================================================
# 4. CLASSES & SUBJECTS
# ==========================================================

@api_router.route("/classes", methods=["GET"])
@current_user
def api_get_classes(user: Faculty):
    db = get_db()
    classes = db.query(ClassModel).order_by(ClassModel.academic_year, ClassModel.division).all()
    results = []
    for c in classes:
        # Practical batches for this class
        batches = db.query(Batch).filter(
            (Batch.class_id == c.id) | (Batch.class_name == c.name)
        ).order_by(Batch.name).all()

        # Verified subjects for this class
        subjects = db.query(Subject).filter(
            (Subject.class_name == c.name) | (Subject.class_name == c.name.replace("-", " "))
        ).all()

        # Assigned class teacher from faculty assignments if configured
        teacher_assignment = db.query(FacultyAssignment).filter(
            FacultyAssignment.class_id == c.id,
            FacultyAssignment.session_type == "Class Teacher"
        ).first()
        class_teacher = teacher_assignment.faculty.name if (teacher_assignment and teacher_assignment.faculty) else None

        total_students = sum(b.student_count for b in batches) if batches else 0

        results.append({
            "id": c.id,
            "academic_year": c.academic_year,
            "division": c.division,
            "name": c.name,
            "displayName": c.name.replace("-", " "),
            "department": c.department,
            "total_students": total_students,
            "class_teacher": class_teacher,
            "batches": [
                {
                    "id": b.id,
                    "name": b.name,
                    "student_count": b.student_count,
                    "active": b.active
                }
                for b in batches
            ],
            "subjects": [
                {
                    "id": s.id,
                    "name": s.name,
                    "code": getattr(s, "code", None),
                    "short_name": getattr(s, "short_name", None),
                    "is_practical": getattr(s, "is_practical", False)
                }
                for s in subjects
            ]
        })
    return jsonify(results), 200


@api_router.route("/batches", methods=["GET"])
@current_user
def api_get_batches(user: Faculty):
    db = get_db()
    class_name = request.args.get("class_name")
    query = db.query(Batch)
    if class_name:
        alt_class = class_name.replace(" ", "-") if " " in class_name else class_name.replace("-", " ")
        query = query.filter((Batch.class_name == class_name) | (Batch.class_name == alt_class))
    batches = query.order_by(Batch.class_name, Batch.name).all()
    return jsonify([
        {
            "id": b.id,
            "name": b.name,
            "class_id": b.class_id,
            "class_name": b.class_name,
            "student_count": b.student_count,
            "active": b.active
        }
        for b in batches
    ]), 200


@api_router.route("/batches", methods=["POST"])
@require_admin
def api_create_batch(admin: Faculty):
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    class_name = str(data.get("class_name", "")).strip()
    class_id = data.get("class_id")
    student_count = int(data.get("student_count", 25))

    if not name:
        raise APIError("Batch name is required.", 400)

    db = get_db()
    new_batch = Batch(
        name=name,
        class_id=class_id,
        class_name=class_name,
        student_count=student_count,
        active=True
    )
    db.add(new_batch)
    db.commit()
    db.refresh(new_batch)

    return jsonify({
        "message": "Batch created successfully",
        "batch": {
            "id": new_batch.id,
            "name": new_batch.name,
            "class_id": new_batch.class_id,
            "class_name": new_batch.class_name,
            "student_count": new_batch.student_count,
            "active": new_batch.active
        }
    }), 201


@api_router.route("/classes/<class_id>/timetable", methods=["GET"])
@current_user
def api_get_class_timetable(class_id, user: Faculty):
    db = get_db()
    
    # Resolve class_id by id or name
    cls = None
    if str(class_id).isdigit():
        cls = db.get(ClassModel, int(class_id))
    if not cls:
        cls = db.query(ClassModel).filter(
            (ClassModel.name == class_id) | (ClassModel.name == str(class_id).replace(" ", "-"))
        ).first()

    cls_name = cls.name if cls else class_id
    entries = db.query(TimetableEntry).filter(TimetableEntry.class_name == cls_name).order_by(
        TimetableEntry.day, TimetableEntry.start_time
    ).all()

    return jsonify([
        {
            "id": e.id,
            "day": e.day,
            "start_time": e.start_time,
            "end_time": e.end_time,
            "subject": e.subject,
            "class_name": e.class_name,
            "room": e.room,
            "faculty_id": e.faculty_id,
            "faculty_name": e.faculty.name if e.faculty else "",
            "batch": e.batch,
            "is_lab": e.is_lab,
            "session_type": getattr(e, "session_type", "Practical" if e.is_lab else "Theory")
        }
        for e in entries
    ]), 200


@api_router.route("/subjects", methods=["GET"])
@current_user
def api_get_subjects(user: Faculty):
    db = get_db()
    academic_year = request.args.get("academic_year")
    class_name = request.args.get("class_name")

    query = db.query(Subject)
    if academic_year:
        query = query.filter(Subject.academic_year == academic_year)
    if class_name:
        query = query.filter(Subject.class_name == class_name)

    subjects = query.all()
    return jsonify([
        {
            "id": s.id,
            "name": s.name,
            "code": getattr(s, "code", None),
            "short_name": getattr(s, "short_name", None),
            "class_name": s.class_name,
            "academic_year": getattr(s, "academic_year", None),
            "total_units": s.total_units,
            "completed_units": s.completed_units,
            "is_practical": getattr(s, "is_practical", False)
        }
        for s in subjects
    ]), 200


# ==========================================================
# 5. ADMIN DASHBOARD & MANAGEMENT
# ==========================================================

@api_router.route("/admin/dashboard", methods=["GET"])
@require_admin
def api_admin_dashboard(admin: Faculty):
    db = get_db()

    total_faculty = db.query(Faculty).filter(Faculty.active == True).count()
    total_classes = db.query(ClassModel).count()
    total_subjects = db.query(Subject).count()
    total_entries = db.query(TimetableEntry).count()
    total_rooms = db.query(Room).filter(Room.active == True).count()
    total_conflicts = db.query(Conflict).filter(Conflict.status == "Pending").count()

    classes = db.query(ClassModel).all()
    class_list = [{"id": c.id, "name": c.name, "academic_year": c.academic_year} for c in classes]

    faculty_list = db.query(Faculty).filter(Faculty.active == True).all()
    faculty_summary = [
        {
            "id": f.id,
            "faculty_id": f.faculty_id or f"FAC-{100 + f.id}",
            "name": f.name,
            "email": f.email,
            "role": f.role,
            "max_hours": f.max_hours,
            "current_hours": db.query(TimetableEntry).filter(TimetableEntry.faculty_id == f.id).count()
        }
        for f in faculty_list
    ]

    return jsonify({
        "total_faculty": total_faculty,
        "total_classes": total_classes,
        "total_subjects": total_subjects,
        "total_timetable_entries": total_entries,
        "total_rooms": total_rooms,
        "total_conflicts": total_conflicts,
        "classes": class_list,
        "faculty_summary": faculty_summary
    }), 200


@api_router.route("/admin/faculty", methods=["GET"])
@require_admin
def api_admin_faculty(admin: Faculty):
    db = get_db()
    faculty_list = db.query(Faculty).order_by(Faculty.role, Faculty.name).all()

    return jsonify([
        {
            "id": f.id,
            "faculty_id": f.faculty_id or (f"FAC-{100 + f.id}" if f.role == "faculty" else "ADM-101"),
            "name": f.name,
            "email": f.email,
            "role": f.role,
            "department": f.department,
            "expertise": [x.strip() for x in f.expertise.split(",") if x.strip()] if f.expertise else [],
            "max_hours": f.max_hours,
            "current_hours": db.query(TimetableEntry).filter(TimetableEntry.faculty_id == f.id).count(),
            "active": f.active
        }
        for f in faculty_list
    ]), 200


@api_router.route("/admin/timetable", methods=["GET"])
@require_admin
def api_admin_timetable(admin: Faculty):
    db = get_db()
    class_name = request.args.get("class_name")
    day = request.args.get("day")
    faculty_id = request.args.get("faculty_id", type=int)
    room = request.args.get("room")

    query = db.query(TimetableEntry)
    if class_name:
        alt_class = class_name.replace(" ", "-") if " " in class_name else class_name.replace("-", " ")
        query = query.filter((TimetableEntry.class_name == class_name) | (TimetableEntry.class_name == alt_class))
    if day:
        query = query.filter(TimetableEntry.day == day)
    if faculty_id:
        query = query.filter(TimetableEntry.faculty_id == faculty_id)
    if room:
        query = query.filter(TimetableEntry.room == room)

    entries = query.order_by(TimetableEntry.day, TimetableEntry.start_time).all()

    return jsonify([
        {
            "id": e.id,
            "day": e.day,
            "start_time": e.start_time,
            "end_time": e.end_time,
            "startTime": e.start_time,
            "endTime": e.end_time,
            "displayTime": f"{e.start_time} - {e.end_time}",
            "subject": e.subject,
            "class_name": e.class_name,
            "classDiv": e.class_name,
            "room": e.room,
            "faculty_id": e.faculty_id,
            "facultyId": e.faculty.faculty_id if (e.faculty and e.faculty.faculty_id) else f"FAC-{e.faculty_id}",
            "faculty_name": e.faculty.name if e.faculty else "",
            "facultyName": e.faculty.name if e.faculty else "",
            "batch": e.batch,
            "is_lab": e.is_lab,
            "session_type": getattr(e, "session_type", "Practical" if e.is_lab else "Theory"),
            "type": "Lab Practical" if e.is_lab else getattr(e, "session_type", "Theory")
        }
        for e in entries
    ]), 200


# ==========================================================
# 6. GENERAL TIMETABLE ENDPOINT (FILTERABLE)
# ==========================================================

@api_router.route("/timetable", methods=["GET"])
@current_user
def api_get_timetable(user: Faculty):
    db = get_db()
    class_name = request.args.get("class_name")
    day = request.args.get("day")
    faculty_id = request.args.get("faculty_id", type=int)
    batch = request.args.get("batch")
    room = request.args.get("room")
    session_type = request.args.get("session_type")

    query = db.query(TimetableEntry)

    if class_name:
        alt_class = class_name.replace(" ", "-") if " " in class_name else class_name.replace("-", " ")
        query = query.filter((TimetableEntry.class_name == class_name) | (TimetableEntry.class_name == alt_class))

    if day:
        query = query.filter(TimetableEntry.day == day)

    if faculty_id:
        query = query.filter(TimetableEntry.faculty_id == faculty_id)

    if batch:
        query = query.filter((TimetableEntry.batch == batch) | (TimetableEntry.batch.is_(None)))

    if room:
        query = query.filter(TimetableEntry.room == room)

    if session_type:
        query = query.filter(TimetableEntry.session_type == session_type)

    entries = query.order_by(TimetableEntry.day, TimetableEntry.start_time).all()

    return jsonify([
        {
            "id": e.id,
            "day": e.day,
            "start_time": e.start_time,
            "end_time": e.end_time,
            "startTime": e.start_time,
            "endTime": e.end_time,
            "displayTime": f"{e.start_time} - {e.end_time}",
            "subject": e.subject,
            "class_name": e.class_name,
            "classDiv": e.class_name,
            "room": e.room,
            "faculty_id": e.faculty_id,
            "facultyId": e.faculty.faculty_id if (e.faculty and e.faculty.faculty_id) else f"FAC-{e.faculty_id}",
            "faculty_name": e.faculty.name if e.faculty else "",
            "facultyName": e.faculty.name if e.faculty else "",
            "batch": e.batch,
            "is_lab": e.is_lab,
            "session_type": getattr(e, "session_type", "Practical" if e.is_lab else "Theory"),
            "type": "Lab Practical" if e.is_lab else getattr(e, "session_type", "Theory")
        }
        for e in entries
    ]), 200


# ==========================================================
# 7. FACULTY DIRECTORY
# ==========================================================

@api_router.route("/faculty", methods=["GET"])
@current_user
def api_get_faculty(user: Faculty):
    db = get_db()
    if user.role == "admin":
        faculty_list = db.query(Faculty).order_by(Faculty.role, Faculty.name).all()
    else:
        faculty_list = db.query(Faculty).filter(Faculty.active == True).order_by(Faculty.name).all()

    return jsonify([
        {
            "id": f.id,
            "faculty_id": f.faculty_id or (f"FAC-{100 + f.id}" if f.role == "faculty" else "ADM-101"),
            "name": f.name,
            "email": f.email,
            "role": f.role,
            "department": f.department,
            "expertise": [x.strip() for x in f.expertise.split(",") if x.strip()] if f.expertise else [],
            "max_hours": f.max_hours,
            "current_hours": db.query(TimetableEntry).filter(TimetableEntry.faculty_id == f.id).count(),
            "active": f.active
        }
        for f in faculty_list
    ]), 200


# ==========================================================
# 8. ROOMS INFORMATION & OCCUPANCY
# ==========================================================

@api_router.route("/rooms", methods=["GET"])
@current_user
def api_get_rooms(user: Faculty):
    db = get_db()
    day = request.args.get("day")
    start_time = request.args.get("start_time")
    end_time = request.args.get("end_time")

    rooms = db.query(Room).filter(Room.active == True).order_by(Room.name).all()

    results = []
    for r in rooms:
        occupied = False
        occupied_by = None

        if day and start_time and end_time:
            # Check overlap with timetable entries
            entries = db.query(TimetableEntry).filter(
                TimetableEntry.room == r.name,
                TimetableEntry.day == day
            ).all()
            for entry in entries:
                if start_time < entry.end_time and entry.start_time < end_time:
                    occupied = True
                    occupied_by = f"{entry.class_name}: {entry.subject}"
                    break

        results.append({
            "id": r.id,
            "name": r.name,
            "room_type": r.room_type,
            "capacity": r.capacity,
            "active": r.active,
            "status": "Occupied" if occupied else "Available",
            "occupied_details": occupied_by
        })

    return jsonify(results), 200


# ==========================================================
# 9. ANALYTICS & DASHBOARD METRICS
# ==========================================================

@api_router.route("/analytics", methods=["GET"])
@current_user
def api_get_analytics(user: Faculty):
    db = get_db()

    total_faculty = db.query(Faculty).filter(Faculty.active == True).count()
    total_classes = db.query(ClassModel).count()
    total_timetable_entries = db.query(TimetableEntry).count()
    total_rooms = db.query(Room).filter(Room.active == True).count()
    total_subjects = db.query(Subject).count()

    # Workload breakdown
    faculty_list = db.query(Faculty).filter(Faculty.active == True).all()
    workload_summary = []
    for f in faculty_list:
        hours = db.query(TimetableEntry).filter(TimetableEntry.faculty_id == f.id).count()
        workload_summary.append({
            "faculty_id": f.id,
            "faculty_code": f.faculty_id or f"FAC-{f.id}",
            "name": f.name,
            "current_hours": hours,
            "max_hours": f.max_hours,
            "status": "High" if hours >= f.max_hours * 0.75 else ("Medium" if hours >= f.max_hours * 0.4 else "Low")
        })

    return jsonify({
        "department": "Artificial Intelligence & Data Science (AI & DS)",
        "total_faculty": total_faculty,
        "total_classes": total_classes,
        "total_timetable_entries": total_timetable_entries,
        "total_rooms": total_rooms,
        "total_subjects": total_subjects,
        "classes": [c.name for c in db.query(ClassModel).all()],
        "workload_summary": workload_summary
    }), 200


# ==========================================================
# 7B. FACULTY MANAGEMENT (ADMIN OPERATIONS)
# ==========================================================

@api_router.route("/faculty", methods=["POST"])
@require_admin
def api_create_faculty(admin: Faculty):
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    email_clean = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", "")).strip()
    fac_code = str(data.get("faculty_id", "")).strip().upper()
    role = str(data.get("role", "faculty")).strip().lower()
    dept = str(data.get("department", "AI&DS")).strip()
    max_hours = int(data.get("max_hours", 16))
    expertise = data.get("expertise", "")
    if isinstance(expertise, list):
        expertise = ",".join(str(x) for x in expertise)

    if not name or not email_clean or not password:
        raise APIError("Name, institutional email, and password are required.", 400)

    db = get_db()
    if db.query(Faculty).filter(Faculty.email == email_clean).first():
        raise APIError("A faculty member with this email address already exists.", 409)

    if fac_code and db.query(Faculty).filter(Faculty.faculty_id == fac_code).first():
        raise APIError("A faculty member with this Faculty ID already exists.", 409)

    if not fac_code:
        next_count = db.query(Faculty).count() + 1
        fac_code = f"FAC-{100 + next_count}"

    from ..security import hash_password
    new_faculty = Faculty(
        name=name,
        email=email_clean,
        faculty_id=fac_code,
        password_hash=hash_password(password),
        role=role,
        department=dept,
        expertise=str(expertise),
        max_hours=max_hours,
        active=True
    )
    db.add(new_faculty)
    db.commit()
    db.refresh(new_faculty)

    return jsonify({
        "message": f"Faculty member {new_faculty.name} added successfully",
        "faculty": {
            "id": new_faculty.id,
            "faculty_id": new_faculty.faculty_id,
            "name": new_faculty.name,
            "email": new_faculty.email,
            "role": new_faculty.role,
            "department": new_faculty.department,
            "expertise": [x.strip() for x in new_faculty.expertise.split(",") if x.strip()] if new_faculty.expertise else [],
            "max_hours": new_faculty.max_hours,
            "active": new_faculty.active
        }
    }), 201


@api_router.route("/faculty/<int:faculty_id>", methods=["PUT"])
@require_admin
def api_update_faculty(faculty_id: int, admin: Faculty):
    data = request.get_json(silent=True) or {}
    db = get_db()
    faculty = db.get(Faculty, faculty_id)
    if not faculty:
        raise APIError("Faculty not found", 404)

    if "name" in data and str(data["name"]).strip():
        faculty.name = str(data["name"]).strip()
    if "email" in data and str(data["email"]).strip():
        clean_email = str(data["email"]).strip().lower()
        if clean_email != faculty.email:
            existing = db.query(Faculty).filter(Faculty.email == clean_email).first()
            if existing and existing.id != faculty.id:
                raise APIError("Email address is already in use by another account.", 409)
            faculty.email = clean_email
    if "department" in data:
        faculty.department = str(data["department"]).strip()
    if "role" in data:
        faculty.role = str(data["role"]).strip().lower()
    if "max_hours" in data:
        faculty.max_hours = int(data["max_hours"])
    if "expertise" in data:
        exp = data["expertise"]
        faculty.expertise = ",".join(str(x) for x in exp) if isinstance(exp, list) else str(exp)
    if "active" in data:
        faculty.active = bool(data["active"])
    if data.get("password"):
        from ..security import hash_password
        faculty.password_hash = hash_password(str(data["password"]))

    db.commit()
    db.refresh(faculty)

    return jsonify({
        "message": f"Faculty member {faculty.name} updated successfully",
        "faculty": {
            "id": faculty.id,
            "faculty_id": faculty.faculty_id or f"FAC-{faculty.id}",
            "name": faculty.name,
            "email": faculty.email,
            "role": faculty.role,
            "department": faculty.department,
            "expertise": [x.strip() for x in faculty.expertise.split(",") if x.strip()] if faculty.expertise else [],
            "max_hours": faculty.max_hours,
            "active": faculty.active
        }
    }), 200


@api_router.route("/faculty/<int:faculty_id>", methods=["DELETE"])
@require_admin
def api_delete_faculty(faculty_id: int, admin: Faculty):
    db = get_db()
    faculty = db.get(Faculty, faculty_id)
    if not faculty:
        raise APIError("Faculty not found", 404)

    # Soft deactivation: preserves historical timetables and audit records
    faculty.active = False
    db.commit()

    return jsonify({
        "message": f"Faculty member {faculty.name} has been deactivated. Historical records and timetables are preserved.",
        "faculty_id": faculty.id,
        "active": False
    }), 200


@api_router.route("/faculty/<int:faculty_id>/toggle-status", methods=["POST"])
@require_admin
def api_toggle_faculty_status(faculty_id: int, admin: Faculty):
    db = get_db()
    faculty = db.get(Faculty, faculty_id)
    if not faculty:
        raise APIError("Faculty not found", 404)

    faculty.active = not faculty.active
    db.commit()

    return jsonify({
        "message": f"Faculty member {faculty.name} status updated to {'Active' if faculty.active else 'Inactive'}.",
        "faculty_id": faculty.id,
        "active": faculty.active
    }), 200


@api_router.route("/faculty/assign", methods=["POST"])
@require_admin
def api_assign_faculty(admin: Faculty):
    data = request.get_json(silent=True) or {}
    faculty_id = data.get("faculty_id")
    subject_id = data.get("subject_id")
    class_id = data.get("class_id")
    batch = data.get("batch")
    session_type = data.get("session_type", "Theory")

    if not faculty_id or not class_id:
        raise APIError("faculty_id and class_id are required.", 400)

    db = get_db()
    faculty = db.get(Faculty, faculty_id)
    if not faculty:
        raise APIError("Faculty member not found", 404)
    if not faculty.active:
        raise APIError("Cannot assign duties to an inactive faculty member.", 400)

    class_obj = db.get(ClassModel, class_id)
    if not class_obj:
        raise APIError("Class division not found", 404)

    assignment = FacultyAssignment(
        faculty_id=faculty_id,
        subject_id=subject_id,
        class_id=class_id,
        batch=batch,
        session_type=session_type
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    return jsonify({
        "message": "Faculty assignment created successfully",
        "assignment_id": assignment.id,
        "faculty_name": faculty.name,
        "class_name": class_obj.name,
        "batch": batch,
        "session_type": session_type
    }), 201


# ==========================================================
# 7C. ABSENCE & REPLACEMENT REQUESTS (DATABASE BACKED)
# ==========================================================

@api_router.route("/substitutes/requests", methods=["GET"])
@current_user
def api_get_substitute_requests(user: Faculty):
    db = get_db()
    query = db.query(SubstituteRequest)

    # Faculty privacy: ordinary faculty only see requests they initiated or received
    if user.role != "admin":
        query = query.filter(
            (SubstituteRequest.requester_id == user.id) |
            (SubstituteRequest.recommended_id == user.id)
        )

    requests = query.order_by(SubstituteRequest.created_at.desc()).all()

    results = []
    for r in requests:
        requester = db.get(Faculty, r.requester_id)
        substitute = db.get(Faculty, r.recommended_id)
        results.append({
            "id": r.id,
            "requester_id": r.requester_id,
            "requester_name": requester.name if requester else "Faculty",
            "requester_faculty_id": requester.faculty_id if (requester and requester.faculty_id) else f"FAC-{r.requester_id}",
            "recommended_id": r.recommended_id,
            "recommended_name": substitute.name if substitute else "Faculty",
            "recommended_faculty_id": substitute.faculty_id if (substitute and substitute.faculty_id) else f"FAC-{r.recommended_id}",
            "subject": r.subject,
            "class_name": r.class_name,
            "day": r.day,
            "slot": r.slot,
            "reason": r.reason,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None
        })

    return jsonify(results), 200
