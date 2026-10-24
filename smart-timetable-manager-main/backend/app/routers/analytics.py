from flask import Blueprint, request, jsonify

from ..database import get_db
from ..models import Faculty, TimetableEntry, Subject
from ..auth import current_user, APIError

router = Blueprint("analytics", __name__, url_prefix="/analytics")


# ==========================================================
# 1. FACULTY WORKLOAD ANALYTICS
# ==========================================================

@router.route("/workload", methods=["GET"])
@current_user
def workload_analytics(user: Faculty):
    faculty_id = request.args.get("faculty_id", type=int)
    db = get_db()

    # Faculty data privacy: faculty members can only view their own workload
    if user.role == "faculty":
        if faculty_id is not None and faculty_id != user.id:
            raise APIError("Access denied: You can only view your own workload.", 403)
        faculty_list = [user]
    else:
        # Admin / HOD retains authorized access to department / specific faculty workload
        if faculty_id is not None:
            faculty_list = db.query(Faculty).filter(
                Faculty.id == faculty_id,
                Faculty.active == True
            ).all()
        else:
            faculty_list = db.query(Faculty).filter(
                Faculty.department == user.department,
                Faculty.active == True
            ).all()

    analytics = []
    for faculty in faculty_list:
        current_hours = db.query(TimetableEntry).filter(
            TimetableEntry.faculty_id == faculty.id
        ).count()

        max_hours = faculty.max_hours
        remaining_hours = max(max_hours - current_hours, 0)

        if current_hours >= max_hours:
            workload_status = "Full"
        elif current_hours >= max_hours * 0.75:
            workload_status = "High"
        elif current_hours >= max_hours * 0.50:
            workload_status = "Medium"
        else:
            workload_status = "Low"

        analytics.append({
            "faculty_id": faculty.id,
            "faculty_name": faculty.name,
            "current_hours": current_hours,
            "max_hours": max_hours,
            "remaining_hours": remaining_hours,
            "workload_status": workload_status
        })

    return jsonify({
        "department": user.department,
        "faculty_workload": analytics
    }), 200


# ==========================================================
# 2. SYLLABUS PROGRESS
# ==========================================================

@router.route("/syllabus", methods=["GET"])
@current_user
def syllabus_progress(user: Faculty):
    faculty_id = request.args.get("faculty_id", type=int)
    db = get_db()

    # Faculty data privacy: faculty members can only view their own syllabus progress
    if user.role == "faculty":
        if faculty_id is not None and faculty_id != user.id:
            raise APIError(
                "Access denied: You can only view your own syllabus progress.",
                403
            )
        target_faculty = user
    else:
        # Admin / HOD can view any faculty's syllabus progress
        if faculty_id is not None:
            target_faculty = db.get(Faculty, faculty_id)
            if not target_faculty:
                raise APIError("Faculty not found", 404)
        else:
            target_faculty = user

    subjects = db.query(Subject).filter(
        Subject.faculty_id == target_faculty.id
    ).all()

    progress = []
    for subject in subjects:
        total_units = subject.total_units
        completed_units = subject.completed_units
        if total_units > 0:
            percentage = (completed_units / total_units) * 100
        else:
            percentage = 0

        progress.append({
            "subject_id": subject.id,
            "subject": subject.name,
            "class_name": subject.class_name,
            "total_units": total_units,
            "completed_units": completed_units,
            "remaining_units": max(total_units - completed_units, 0),
            "progress_percentage": round(percentage, 2)
        })

    return jsonify({
        "faculty": target_faculty.name,
        "department": target_faculty.department,
        "subjects": progress
    }), 200


# ==========================================================
# 3. DASHBOARD STATISTICS
# ==========================================================

@router.route("/dashboard", methods=["GET"])
@current_user
def dashboard_statistics(user: Faculty):
    db = get_db()

    if user.role == "faculty":
        # Faculty member sees strictly their own timetable assignments and syllabus stats
        timetable_count = db.query(TimetableEntry).filter(
            TimetableEntry.faculty_id == user.id
        ).count()

        subject_count = db.query(Subject).filter(
            Subject.faculty_id == user.id
        ).count()

        total_units = 0
        completed_units = 0
        subjects = db.query(Subject).filter(
            Subject.faculty_id == user.id
        ).all()

        for subject in subjects:
            total_units += subject.total_units
            completed_units += subject.completed_units

        syllabus_percentage = (
            (completed_units / total_units * 100) if total_units > 0 else 0
        )
        remaining_units = max(total_units - completed_units, 0)

        return jsonify({
            "faculty": user.name,
            "department": user.department,
            "assigned_classes": timetable_count,
            "subjects": subject_count,
            "total_syllabus_units": total_units,
            "completed_syllabus_units": completed_units,
            "remaining_syllabus_units": remaining_units,
            "syllabus_progress_percentage": round(syllabus_percentage, 2)
        }), 200
    else:
        # Admin / HOD sees institutional department stats
        faculty_count = db.query(Faculty).filter(
            Faculty.department == user.department,
            Faculty.active == True
        ).count()

        timetable_count = db.query(TimetableEntry).count()
        subject_count = db.query(Subject).count()

        total_units = 0
        completed_units = 0
        subjects = db.query(Subject).all()

        for subject in subjects:
            total_units += subject.total_units
            completed_units += subject.completed_units

        syllabus_percentage = (
            (completed_units / total_units * 100) if total_units > 0 else 0
        )
        remaining_units = max(total_units - completed_units, 0)

        return jsonify({
            "admin": user.name,
            "department": user.department,
            "faculty_count": faculty_count,
            "assigned_classes": timetable_count,
            "subjects": subject_count,
            "total_syllabus_units": total_units,
            "completed_syllabus_units": completed_units,
            "remaining_syllabus_units": remaining_units,
            "syllabus_progress_percentage": round(syllabus_percentage, 2)
        }), 200
