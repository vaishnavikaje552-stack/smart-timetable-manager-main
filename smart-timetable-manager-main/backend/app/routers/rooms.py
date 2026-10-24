from flask import Blueprint, request, jsonify

from ..database import get_db
from ..models import Room, TimetableEntry, Faculty
from ..auth import current_user, APIError

router = Blueprint("rooms", __name__, url_prefix="/rooms")


# ==========================================================
# ROOM OCCUPANCY
# ==========================================================

@router.route("/occupancy", methods=["GET"])
@current_user
def room_occupancy(user: Faculty):
    day = request.args.get("day")
    start_time = request.args.get("start_time")
    end_time = request.args.get("end_time")

    if not day or not start_time or not end_time:
        raise APIError("day, start_time, and end_time parameters are required", 400)

    db = get_db()
    rooms = db.query(Room).filter(Room.active == True).all()

    occupied_rooms = []
    available_rooms = []

    for room in rooms:
        entries = db.query(TimetableEntry).filter(
            TimetableEntry.room == room.name,
            TimetableEntry.day == day
        ).all()

        occupied = False
        for entry in entries:
            if start_time < entry.end_time and entry.start_time < end_time:
                occupied = True
                break

        room_info = {
            "room_id": room.id,
            "room_name": room.name,
            "room_type": room.room_type,
            "capacity": room.capacity,
            "status": "Occupied" if occupied else "Available"
        }

        if occupied:
            occupied_rooms.append(room_info)
        else:
            available_rooms.append(room_info)

    return jsonify({
        "day": day,
        "start_time": start_time,
        "end_time": end_time,
        "occupied_rooms": occupied_rooms,
        "available_rooms": available_rooms
    }), 200
