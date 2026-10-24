from flask import Blueprint, request, jsonify

from ..database import get_db
from ..models import Faculty, TimetableEntry
from ..auth import current_user, require_admin, APIError

router = Blueprint("timetable", __name__, url_prefix="/timetable")


def time_overlap(start1: str, end1: str, start2: str, end2: str) -> bool:
    return start1 < end2 and start2 < end1


def timetable_response(entry: TimetableEntry) -> dict:
    return {
        "id": entry.id,
        "day": entry.day,
        "start_time": entry.start_time,
        "end_time": entry.end_time,
        "subject": entry.subject,
        "class_name": entry.class_name,
        "room": entry.room,
        "faculty_id": entry.faculty_id,
        "faculty_name": entry.faculty.name if entry.faculty else "",
        "batch": entry.batch,
        "is_lab": entry.is_lab
    }


# ==========================================================
# GET TIMETABLE
# ==========================================================

@router.route("", methods=["GET"])
@current_user
def get_timetable(user: Faculty):
    day = request.args.get("day")
    class_name = request.args.get("class_name")
    faculty_id = request.args.get("faculty_id", type=int)
    search = request.args.get("search")

    db = get_db()
    query = db.query(TimetableEntry)

    # Faculty data privacy: faculty members can only view their own timetable
    if user.role == "faculty":
        if faculty_id is not None and faculty_id != user.id:
            raise APIError("Access denied: You can only view your own timetable.", 403)
        query = query.filter(TimetableEntry.faculty_id == user.id)
    else:
        # Admin / HOD access remains unchanged
        if faculty_id is not None:
            query = query.filter(TimetableEntry.faculty_id == faculty_id)

    if day:
        query = query.filter(TimetableEntry.day == day)

    if class_name:
        query = query.filter(TimetableEntry.class_name == class_name)

    entries = query.all()

    if search:
        search_lower = search.lower()
        entries = [
            entry
            for entry in entries
            if (
                search_lower in entry.subject.lower()
                or search_lower in entry.room.lower()
                or (entry.faculty and search_lower in entry.faculty.name.lower())
            )
        ]

    return jsonify([timetable_response(entry) for entry in entries]), 200


# ==========================================================
# CLASH DETECTOR (Must precede /<int:entry_id> to avoid route conflict)
# ==========================================================

@router.route("/clashes/check", methods=["GET"])
@current_user
def detect_clashes(user: Faculty):
    db = get_db()
    entries = db.query(TimetableEntry).all()
    clashes = []

    for i in range(len(entries)):
        first = entries[i]
        for j in range(i + 1, len(entries)):
            second = entries[j]

            if first.day != second.day:
                continue

            if not time_overlap(
                first.start_time,
                first.end_time,
                second.start_time,
                second.end_time
            ):
                continue

            if first.faculty_id == second.faculty_id:
                clashes.append({
                    "type": "Faculty",
                    "message": f"{first.faculty.name} has overlapping classes" if first.faculty else "Faculty has overlapping classes",
                    "entry_1": first.id,
                    "entry_2": second.id
                })

            if first.room == second.room:
                clashes.append({
                    "type": "Room",
                    "message": f"{first.room} is double-booked",
                    "entry_1": first.id,
                    "entry_2": second.id
                })

            if first.class_name == second.class_name:
                # Batches can run simultaneously in different rooms
                if not first.batch or not second.batch or first.batch == second.batch:
                    clashes.append({
                        "type": "Class",
                        "message": f"{first.class_name} has overlapping classes" if not first.batch else f"{first.class_name} ({first.batch}) has overlapping classes",
                        "entry_1": first.id,
                        "entry_2": second.id
                    })

    return jsonify({
        "total_clashes": len(clashes),
        "status": "PASS" if len(clashes) == 0 else "CONFLICT",
        "clashes": clashes
    }), 200


# ==========================================================
# GET SINGLE TIMETABLE ENTRY
# ==========================================================

@router.route("/<int:entry_id>", methods=["GET"])
@current_user
def get_timetable_entry(entry_id: int, user: Faculty):
    db = get_db()
    entry = db.get(TimetableEntry, entry_id)

    if not entry:
        raise APIError("Timetable entry not found", 404)

    # Faculty data privacy: faculty members can only view their own timetable entries
    if user.role == "faculty" and entry.faculty_id != user.id:
        raise APIError(
            "Access denied: You can only view your own timetable entries.",
            403
        )

    return jsonify(timetable_response(entry)), 200


# ==========================================================
# CREATE TIMETABLE ENTRY (ADMIN ONLY)
# ==========================================================

@router.route("", methods=["POST"])
@require_admin
def create_timetable(admin: Faculty):
    data = request.get_json(silent=True) or {}
    db = get_db()

    faculty_id = data.get("faculty_id")
    if faculty_id is None:
        raise APIError("faculty_id is required", 400)

    faculty = db.get(Faculty, faculty_id)
    if not faculty:
        raise APIError("Faculty not found", 404)

    day = data.get("day", "")
    start_time = data.get("start_time", "")
    end_time = data.get("end_time", "")
    room = data.get("room", "")
    class_name = data.get("class_name", "")
    subject = data.get("subject", "")

    existing = db.query(TimetableEntry).filter(
        TimetableEntry.day == day
    ).all()

    conflicts = []
    for entry in existing:
        if not time_overlap(start_time, end_time, entry.start_time, entry.end_time):
            continue

        if entry.faculty_id == faculty_id:
            conflicts.append("Faculty is already scheduled")

        if entry.room == room:
            conflicts.append("Room is already occupied")

        if entry.class_name == class_name:
            batch_req = data.get("batch")
            if not batch_req or not entry.batch or batch_req == entry.batch:
                conflicts.append("Class already has another lecture")

    if conflicts:
        raise APIError(
            {
                "message": "Timetable conflict detected",
                "conflicts": list(set(conflicts))
            },
            409
        )

    timetable = TimetableEntry(
        day=day,
        start_time=start_time,
        end_time=end_time,
        subject=subject,
        class_name=class_name,
        room=room,
        faculty_id=faculty_id,
        batch=data.get("batch"),
        is_lab=bool(data.get("is_lab", False))
    )

    db.add(timetable)
    db.commit()
    db.refresh(timetable)

    return jsonify(timetable_response(timetable)), 200


# ==========================================================
# DELETE TIMETABLE ENTRY (ADMIN ONLY)
# ==========================================================

@router.route("/<int:entry_id>", methods=["DELETE"])
@require_admin
def delete_timetable(entry_id: int, admin: Faculty):
    db = get_db()
    entry = db.get(TimetableEntry, entry_id)

    if not entry:
        raise APIError("Timetable entry not found", 404)

    db.delete(entry)
    db.commit()

    return jsonify({
        "message": "Timetable entry deleted successfully",
        "entry_id": entry_id
    }), 200
