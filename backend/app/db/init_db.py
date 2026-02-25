from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_password_hash
from app.db.base import Base
from app.db.session import engine
from app.models import Group, GroupMembership, PreferredLanguage, StudentProfile, Subject, User, UserRole


DEMO_SUBJECTS = [
    {"name_ru": "Математика", "name_kz": "Математика"},
    {"name_ru": "Физика", "name_kz": "Физика"},
    {"name_ru": "История", "name_kz": "Тарих"},
]


DEMO_USERS = [
    {
        "email": "teacher@oku.local",
        "username": "teacher_demo",
        "password": "teacher123",
        "role": UserRole.teacher,
    },
    {
        "email": "student1@oku.local",
        "username": "student_demo_1",
        "password": "student123",
        "role": UserRole.student,
        "preferred_language": PreferredLanguage.ru,
    },
    {
        "email": "student2@oku.local",
        "username": "student_demo_2",
        "password": "student123",
        "role": UserRole.student,
        "preferred_language": PreferredLanguage.kz,
    },
]


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    if not settings.seed_demo_data:
        return

    with Session(engine) as db:
        _seed_subjects(db)
        _seed_demo_users(db)
        db.commit()


def _seed_subjects(db: Session) -> None:
    existing = {s.name_ru for s in db.scalars(select(Subject)).all()}
    for subject in DEMO_SUBJECTS:
        if subject["name_ru"] not in existing:
            db.add(Subject(**subject))


def _seed_demo_users(db: Session) -> None:
    group = db.scalar(select(Group).where(Group.name == "A-101"))
    if not group:
        group = Group(name="A-101")
        db.add(group)
        db.flush()

    for user_data in DEMO_USERS:
        existing = db.scalar(select(User).where(User.email == user_data["email"]))
        if existing:
            continue

        user = User(
            email=user_data["email"],
            username=user_data["username"],
            password_hash=get_password_hash(user_data["password"]),
            role=user_data["role"],
        )
        db.add(user)
        db.flush()

        if user.role == UserRole.student:
            preferred_language = user_data.get("preferred_language", PreferredLanguage.ru)
            db.add(
                StudentProfile(
                    user_id=user.id,
                    group_id=group.id,
                    preferred_language=preferred_language,
                )
            )
            db.add(GroupMembership(student_id=user.id, group_id=group.id))
