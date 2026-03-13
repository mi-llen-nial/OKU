from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Group, GroupMembership, Recommendation, Result, Subject, Test, TestSession, User
from app.schemas.teacher import GroupAnalyticsResponse, GroupStudentMetric, GroupTrendPoint, GroupWeakTopicsResponse, WeakTopicItem
from app.schemas.tests import HistoryItemResponse, ProgressPoint, StudentProgressResponse, SubjectStat


def _localized_subject_pair_for_history(*, subject: Subject, session: TestSession | None) -> tuple[str, str]:
    exam_kind = str(session.exam_kind).strip().lower() if session and session.exam_kind else None
    if exam_kind == "ent":
        return "ЕНТ", "ҰБТ"
    if exam_kind == "ielts":
        return "IELTS", "IELTS"
    if exam_kind == "group_custom":
        configured_title = str((session.exam_config_json or {}).get("title", "")).strip() if session else ""
        if configured_title:
            return configured_title, configured_title
    return subject.name_ru, subject.name_kz


def build_student_history(db: Session, student_id: int) -> list[HistoryItemResponse]:
    rows = db.execute(
        select(Test, Subject, Result, Recommendation, TestSession)
        .join(Subject, Subject.id == Test.subject_id)
        .join(Result, Result.test_id == Test.id)
        .outerjoin(Recommendation, Recommendation.test_id == Test.id)
        .outerjoin(TestSession, TestSession.test_id == Test.id)
        .where(Test.student_id == student_id)
        .order_by(Test.created_at.desc())
    ).all()

    history: list[HistoryItemResponse] = []
    for test, subject, result, recommendation, session in rows:
        exam_kind = str(session.exam_kind).strip().lower() if session and session.exam_kind else None
        subject_name_ru, subject_name_kz = _localized_subject_pair_for_history(subject=subject, session=session)
        subject_name = subject_name_ru if test.language.value == "RU" else subject_name_kz

        history.append(
            HistoryItemResponse(
                test_id=test.id,
                subject_id=subject.id,
                subject_name=subject_name,
                subject_name_ru=subject_name_ru,
                subject_name_kz=subject_name_kz,
                exam_kind=exam_kind,
                difficulty=test.difficulty,
                language=test.language,
                mode=test.mode,
                created_at=test.created_at,
                percent=round(result.percent, 2),
                warning_count=int(session.warning_count if session else 0),
                weak_topics=list(recommendation.weak_topics_json if recommendation else []),
            )
        )
    return history


def build_student_progress(db: Session, student_id: int) -> StudentProgressResponse:
    rows = db.execute(
        select(Test, Subject, Result, TestSession)
        .join(Subject, Subject.id == Test.subject_id)
        .join(Result, Result.test_id == Test.id)
        .outerjoin(TestSession, TestSession.test_id == Test.id)
        .where(Test.student_id == student_id)
        .order_by(Test.created_at.asc())
    ).all()

    if not rows:
        return StudentProgressResponse(
            total_tests=0,
            total_warnings=0,
            avg_percent=0.0,
            best_percent=0.0,
            weak_topics=["Недостаточно данных"],
            trend=[],
            subject_stats=[],
        )

    percents: list[float] = []
    total_warnings = 0
    trend: list[ProgressPoint] = []
    subject_buckets: defaultdict[int, list[float]] = defaultdict(list)
    subject_names: dict[int, tuple[str, str]] = {}

    for test, subject, result, session in rows:
        percents.append(result.percent)
        total_warnings += int(session.warning_count if session else 0)
        trend.append(ProgressPoint(date=test.created_at.date().isoformat(), percent=round(result.percent, 2)))
        subject_buckets[subject.id].append(result.percent)
        subject_names[subject.id] = (subject.name_ru, subject.name_kz)

    subject_stats = [
        SubjectStat(
            subject_id=subject_id,
            subject_name=subject_names[subject_id][0],
            subject_name_ru=subject_names[subject_id][0],
            subject_name_kz=subject_names[subject_id][1],
            tests_count=len(values),
            avg_percent=round(sum(values) / len(values), 2),
        )
        for subject_id, values in subject_buckets.items()
    ]
    subject_stats.sort(key=lambda item: item.avg_percent, reverse=True)

    weak_counter = Counter()
    weak_rows = db.scalars(
        select(Recommendation.weak_topics_json)
        .join(Test, Test.id == Recommendation.test_id)
        .where(Test.student_id == student_id)
    ).all()
    for weak_topics in weak_rows:
        for topic in weak_topics:
            weak_counter[topic] += 1

    weak_topics = [topic for topic, _ in weak_counter.most_common(5)] or ["Недостаточно данных"]

    return StudentProgressResponse(
        total_tests=len(percents),
        total_warnings=total_warnings,
        avg_percent=round(sum(percents) / len(percents), 2),
        best_percent=round(max(percents), 2),
        weak_topics=weak_topics,
        trend=trend,
        subject_stats=subject_stats,
    )


def build_group_analytics(db: Session, group_id: int) -> GroupAnalyticsResponse:
    group = db.get(Group, group_id)
    if not group:
        raise ValueError("Группа не найдена")

    students = db.execute(
        select(User)
        .join(GroupMembership, GroupMembership.student_id == User.id)
        .where(GroupMembership.group_id == group_id)
    ).scalars().all()

    metrics: list[GroupStudentMetric] = []
    all_percents: list[float] = []
    trend_bucket: defaultdict[str, list[float]] = defaultdict(list)

    for student in students:
        progress_rows = db.execute(
            select(Test.created_at, Result.percent)
            .join(Result, Result.test_id == Test.id)
            .where(Test.student_id == student.id)
            .order_by(Test.created_at.asc())
        ).all()

        if progress_rows:
            percents = [row.percent for row in progress_rows]
            last_percent = progress_rows[-1].percent
            avg_percent = sum(percents) / len(percents)
            all_percents.extend(percents)
            for row in progress_rows:
                trend_bucket[row.created_at.date().isoformat()].append(row.percent)
        else:
            avg_percent = 0.0
            last_percent = None

        metrics.append(
            GroupStudentMetric(
                student_id=student.id,
                student_name=student.full_name or student.username,
                tests_count=len(progress_rows),
                avg_percent=round(avg_percent, 2),
                last_percent=round(last_percent, 2) if last_percent is not None else None,
            )
        )

    metrics.sort(key=lambda item: item.avg_percent, reverse=True)

    trend = [
        GroupTrendPoint(date=date, avg_percent=round(sum(values) / len(values), 2))
        for date, values in sorted(trend_bucket.items(), key=lambda pair: datetime.fromisoformat(pair[0]))
    ]

    group_avg = round(sum(all_percents) / len(all_percents), 2) if all_percents else 0.0

    return GroupAnalyticsResponse(
        group_id=group.id,
        group_name=group.name,
        students=metrics,
        group_avg_percent=group_avg,
        trend=trend,
    )


def build_group_weak_topics(db: Session, group_id: int) -> GroupWeakTopicsResponse:
    group = db.get(Group, group_id)
    if not group:
        raise ValueError("Группа не найдена")

    weak_counter = Counter()
    rows = db.scalars(
        select(Recommendation.weak_topics_json)
        .join(Test, Test.id == Recommendation.test_id)
        .join(GroupMembership, GroupMembership.student_id == Test.student_id)
        .where(GroupMembership.group_id == group_id)
    ).all()

    for weak_topics in rows:
        for topic in weak_topics:
            weak_counter[topic] += 1

    weak_topics = [WeakTopicItem(topic=topic, count=count) for topic, count in weak_counter.most_common(10)]

    return GroupWeakTopicsResponse(group_id=group.id, group_name=group.name, weak_topics=weak_topics)
