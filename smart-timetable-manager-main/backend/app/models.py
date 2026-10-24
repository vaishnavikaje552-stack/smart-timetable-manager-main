from datetime import datetime, timezone

from sqlalchemy import (
    String,
    Integer,
    Boolean,
    DateTime,
    ForeignKey,
    Text
)

from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship
)

from .database import Base

# ==========================================================
# CLASS MODEL TABLE
# ==========================================================

class ClassModel(Base):
    __tablename__ = "classes"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )

    academic_year: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        index=True
    )  # 'SY', 'TY', 'BE'

    division: Mapped[str] = mapped_column(
        String(10),
        nullable=False
    )  # 'AD1', 'AD2', 'AD3'

    name: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True
    )  # 'SY-AD1', 'SY-AD2', etc.

    department: Mapped[str] = mapped_column(
        String(100),
        default="AI&DS"
    )

    batches = relationship(
        "Batch",
        back_populates="class_model",
        cascade="all, delete-orphan",
        lazy="joined"
    )


# ==========================================================
# BATCH MODEL TABLE
# ==========================================================

class Batch(Base):
    __tablename__ = "batches"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )

    name: Mapped[str] = mapped_column(
        String(50),
        nullable=False
    )  # 'Batch A', 'Batch B', 'Batch C'

    class_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("classes.id", ondelete="CASCADE"),
        nullable=True
    )

    class_name: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True
    )

    student_count: Mapped[int] = mapped_column(
        Integer,
        default=25
    )

    active: Mapped[bool] = mapped_column(
        Boolean,
        default=True
    )

    class_model = relationship("ClassModel", back_populates="batches")


# ==========================================================
# FACULTY TABLE
# ==========================================================

class Faculty(Base):

    __tablename__ = "faculty"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    email: Mapped[str] = mapped_column(
        String(150),
        unique=True,
        nullable=False,
        index=True
    )

    faculty_id: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=True,
        index=True
    )

    password_hash: Mapped[str] = mapped_column(
        String(300),
        nullable=False
    )

    role: Mapped[str] = mapped_column(
        String(30),
        default="faculty"
    )

    department: Mapped[str] = mapped_column(
        String(100),
        default="AI&DS"
    )

    expertise: Mapped[str] = mapped_column(
        Text,
        default=""
    )

    max_hours: Mapped[int] = mapped_column(
        Integer,
        default=16
    )

    active: Mapped[bool] = mapped_column(
        Boolean,
        default=True
    )

    timetable = relationship(
        "TimetableEntry",
        back_populates="faculty",
        cascade="all, delete-orphan"
    )


# ==========================================================
# SUBJECT TABLE
# ==========================================================

class Subject(Base):

    __tablename__ = "subjects"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True
    )

    name: Mapped[str] = mapped_column(
        String(120),
        unique=True,
        nullable=False
    )

    code: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True
    )

    short_name: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True
    )

    class_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    academic_year: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True
    )

    total_units: Mapped[int] = mapped_column(
        Integer,
        default=6
    )

    completed_units: Mapped[int] = mapped_column(
        Integer,
        default=0
    )

    is_practical: Mapped[bool] = mapped_column(
        Boolean,
        default=False
    )

    faculty_id: Mapped[int | None] = mapped_column(
        ForeignKey("faculty.id"),
        nullable=True
    )


# ==========================================================
# FACULTY ASSIGNMENTS TABLE
# ==========================================================

class FacultyAssignment(Base):
    __tablename__ = "faculty_assignments"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True
    )

    faculty_id: Mapped[int] = mapped_column(
        ForeignKey("faculty.id"),
        nullable=False
    )

    subject_id: Mapped[int | None] = mapped_column(
        ForeignKey("subjects.id"),
        nullable=True
    )

    class_id: Mapped[int] = mapped_column(
        ForeignKey("classes.id"),
        nullable=False
    )

    batch: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True
    )  # 'Batch A', 'Batch B', 'Batch C', or None (entire class)

    session_type: Mapped[str] = mapped_column(
        String(20),
        default="Theory"
    )  # 'Theory', 'Practical', 'Tutorial'

    faculty = relationship("Faculty")
    subject = relationship("Subject")
    class_model = relationship("ClassModel")


# ==========================================================
# TIMETABLE TABLE
# ==========================================================

class TimetableEntry(Base):

    __tablename__ = "timetable"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )

    day: Mapped[str] = mapped_column(
        String(20),
        nullable=False
    )

    start_time: Mapped[str] = mapped_column(
        String(10),
        nullable=False
    )

    end_time: Mapped[str] = mapped_column(
        String(10),
        nullable=False
    )

    subject: Mapped[str] = mapped_column(
        String(120),
        nullable=False
    )

    class_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    room: Mapped[str] = mapped_column(
        String(80),
        nullable=False
    )

    faculty_id: Mapped[int] = mapped_column(
        ForeignKey("faculty.id"),
        nullable=False
    )

    batch: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True
    )

    is_lab: Mapped[bool] = mapped_column(
        Boolean,
        default=False
    )

    session_type: Mapped[str] = mapped_column(
        String(30),
        default="Theory"
    )

    class_id: Mapped[int | None] = mapped_column(
        ForeignKey("classes.id"),
        nullable=True
    )

    subject_id: Mapped[int | None] = mapped_column(
        ForeignKey("subjects.id"),
        nullable=True
    )

    academic_year: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True
    )

    semester: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True
    )

    faculty = relationship(
        "Faculty",
        back_populates="timetable"
    )


# ==========================================================
# ROOM TABLE
# ==========================================================

class Room(Base):

    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True
    )

    name: Mapped[str] = mapped_column(
        String(80),
        unique=True,
        nullable=False
    )

    room_type: Mapped[str] = mapped_column(
        String(30),
        default="Classroom"
    )

    capacity: Mapped[int] = mapped_column(
        Integer,
        default=60
    )

    active: Mapped[bool] = mapped_column(
        Boolean,
        default=True
    )


# ==========================================================
# SUBSTITUTE REQUEST
# ==========================================================

class SubstituteRequest(Base):

    __tablename__ = "substitute_requests"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True
    )

    requester_id: Mapped[int] = mapped_column(
        ForeignKey("faculty.id")
    )

    recommended_id: Mapped[int] = mapped_column(
        ForeignKey("faculty.id")
    )

    subject: Mapped[str] = mapped_column(
        String(120)
    )

    class_name: Mapped[str] = mapped_column(
        String(100),
        default=""
    )

    day: Mapped[str] = mapped_column(
        String(20),
        default=""
    )

    slot: Mapped[str] = mapped_column(
        String(50)
    )

    reason: Mapped[str] = mapped_column(
        Text,
        default=""
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="Pending"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc)
    )


# ==========================================================
# CONFLICT TABLE
# ==========================================================

class Conflict(Base):
    __tablename__ = "conflicts"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )

    faculty_id: Mapped[int] = mapped_column(
        ForeignKey("faculty.id"),
        nullable=False
    )

    room: Mapped[str] = mapped_column(
        String(80),
        nullable=False
    )

    day: Mapped[str] = mapped_column(
        String(20),
        nullable=False
    )

    start_time: Mapped[str] = mapped_column(
        String(10),
        nullable=False
    )

    end_time: Mapped[str] = mapped_column(
        String(10),
        nullable=False
    )

    subject: Mapped[str] = mapped_column(
        String(120),
        nullable=False
    )

    class_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    conflict_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="Pending"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc)
    )

    resolved_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=True
    )

    faculty = relationship("Faculty", backref="conflicts")


# ==========================================================
# ADMIN NOTIFICATION TABLE
# ==========================================================

class AdminNotification(Base):
    __tablename__ = "admin_notifications"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )

    conflict_id: Mapped[int] = mapped_column(
        ForeignKey("conflicts.id"),
        nullable=False
    )

    title: Mapped[str] = mapped_column(
        String(150),
        nullable=False
    )

    message: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )

    is_read: Mapped[bool] = mapped_column(
        Boolean,
        default=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc)
    )

    conflict = relationship("Conflict", backref="notifications")
