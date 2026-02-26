from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_password_hash
from app.db.base import Base
from app.db.session import engine
from app.models import Group, GroupMembership, PreferredLanguage, StudentProfile, Subject, User, UserRole


DEMO_SUBJECTS = [
    {"name_ru": "Математика", "name_kz": "Математика"},
    {"name_ru": "Физика", "name_kz": "Физика"},
    {"name_ru": "Русский язык", "name_kz": "Орыс тілі"},
    {"name_ru": "Английский язык", "name_kz": "Ағылшын тілі"},
    {"name_ru": "Биология", "name_kz": "Биология"},
    {"name_ru": "Информатика", "name_kz": "Информатика"},
    {"name_ru": "Алгебра", "name_kz": "Алгебра"},
    {"name_ru": "Геометрия", "name_kz": "Геометрия"},
    {"name_ru": "Химия", "name_kz": "Химия"},
    {"name_ru": "История", "name_kz": "Тарих"},
]


DEMO_USERS = [
    {
        "email": "teacher@oku.local",
        "full_name": "Марина Преподаватель",
        "username": "teacher_demo",
        "password": "teacher123",
        "role": UserRole.teacher,
    },
    {
        "email": "student1@oku.local",
        "full_name": "Студент Демо 1",
        "username": "student_demo_1",
        "password": "student123",
        "role": UserRole.student,
        "preferred_language": PreferredLanguage.ru,
        "education_level": "school",
        "direction": "Общий профиль",
    },
    {
        "email": "student2@oku.local",
        "full_name": "Студент Демо 2",
        "username": "student_demo_2",
        "password": "student123",
        "role": UserRole.student,
        "preferred_language": PreferredLanguage.kz,
        "education_level": "college",
        "direction": "Информатика",
    },
]


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_compatible_schema()
    if not settings.seed_demo_data:
        return

    with Session(engine) as db:
        _seed_subjects(db)
        _seed_demo_users(db)
        db.commit()


def _ensure_compatible_schema() -> None:
    with engine.begin() as connection:
        inspector = inspect(connection)
        table_names = set(inspector.get_table_names())

        if "users" in table_names:
            user_columns = {column["name"] for column in inspector.get_columns("users")}
            if "full_name" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN full_name VARCHAR(255)"))

        if "student_profiles" in table_names:
            profile_columns = {column["name"] for column in inspector.get_columns("student_profiles")}
            if "education_level" not in profile_columns:
                connection.execute(text("ALTER TABLE student_profiles ADD COLUMN education_level VARCHAR(32)"))
            if "direction" not in profile_columns:
                connection.execute(text("ALTER TABLE student_profiles ADD COLUMN direction VARCHAR(255)"))

        if "groups" in table_names:
            group_columns = {column["name"] for column in inspector.get_columns("groups")}
            if "teacher_id" not in group_columns:
                connection.execute(text("ALTER TABLE groups ADD COLUMN teacher_id INTEGER REFERENCES users(id) ON DELETE SET NULL"))

        if "group_invitations" in table_names:
            invitation_columns = {column["name"] for column in inspector.get_columns("group_invitations")}
            if "group_id" not in invitation_columns:
                connection.execute(
                    text("ALTER TABLE group_invitations ADD COLUMN group_id INTEGER REFERENCES groups(id) ON DELETE SET NULL")
                )

        if "test_sessions" in table_names:
            session_columns = {column["name"] for column in inspector.get_columns("test_sessions")}
            if "warning_limit" not in session_columns:
                connection.execute(text("ALTER TABLE test_sessions ADD COLUMN warning_limit INTEGER"))
            if "exam_kind" not in session_columns:
                connection.execute(text("ALTER TABLE test_sessions ADD COLUMN exam_kind VARCHAR(32)"))
            if "exam_config_json" not in session_columns:
                connection.execute(text("ALTER TABLE test_sessions ADD COLUMN exam_config_json JSON"))


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
            full_name=user_data.get("full_name"),
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
                    education_level=user_data.get("education_level"),
                    direction=user_data.get("direction"),
                )
            )
            db.add(GroupMembership(student_id=user.id, group_id=group.id))

    teacher_demo = db.scalar(select(User).where(User.username == "teacher_demo"))
    if teacher_demo and group.teacher_id is None:
        group.teacher_id = teacher_demo.id
