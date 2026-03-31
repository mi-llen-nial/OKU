from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone
from io import BytesIO
import logging
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import joinedload, selectinload

from app.core.deps import CurrentUser, DBSession, require_role
from app.models import (
    Answer,
    CatalogQuestion,
    DifficultyLevel,
    Group,
    GroupMembership,
    GroupTeacherAssignment,
    InstitutionMembership,
    InstitutionMembershipRole,
    InstitutionMembershipStatus,
    PreferredLanguage,
    Question,
    QuestionType,
    Recommendation,
    Result,
    Subject,
    Test,
    StudentQuestionCoverage,
    TeacherAuthoredTest,
    TeacherAuthoredTestGroup,
    TestAssignment,
    TestModerationStatus,
    TestMode,
    TestSession,
    StudentProfile,
    User,
    UserRole,
)
from app.schemas.tests import (
    GenerateExamTestRequest,
    GenerateMistakesTestRequest,
    GenerateTestRequest,
    GeneratedQuestionPayload,
    QuestionFeedback,
    QuestionResponse,
    RecommendationResponse,
    ResultResponse,
    TestWarningSignal,
    SubmitTestRequest,
    SubmitTestResponse,
    TestResponse,
    TestResultDetailsResponse,
)
from app.schemas.test_pipeline import RuntimeAnswerRequest, RuntimeAnswerResponse, RuntimeStateAnswer, RuntimeStateResponse
from app.services.cache import cache
from app.services.attempt_runtime import attempt_runtime_service
from app.services.custom_tests import normalize_custom_test_time_limit_seconds
from app.services.evaluation import evaluate_answers
from app.services.question_catalog import question_catalog_service
from app.services.recommendation_service import RecommendationFacts, recommendation_service
from app.services.subject_selector import subject_selector_registry
from app.services.test_assembly import test_assembly_service
from app.services.tts import TTSProviderUnavailableError, TTSServiceError, tts_service

router = APIRouter(prefix="/tests", tags=["tests"])
logger = logging.getLogger(__name__)


def _invalidate_student_dashboard_cache(student_id: int) -> None:
    cache.delete_many(
        f"student:{student_id}:history:v1",
        f"student:{student_id}:progress:v1",
        f"student:{student_id}:dashboard:v1",
        f"student:{student_id}:history:v2",
        f"student:{student_id}:progress:v2",
        f"student:{student_id}:dashboard:v2",
        f"student:{student_id}:group-tests:v2",
    )


def _invalidate_teacher_custom_results_cache_for_submitted_test(*, db: DBSession, test: Test) -> None:
    session = test.session
    if not session or str(session.exam_kind or "").strip().lower() != "group_custom":
        return

    config = session.exam_config_json or {}
    raw_custom_test_id = config.get("custom_test_id")
    if isinstance(raw_custom_test_id, str) and raw_custom_test_id.isdigit():
        custom_test_id = int(raw_custom_test_id)
    elif isinstance(raw_custom_test_id, int):
        custom_test_id = raw_custom_test_id
    else:
        return

    if custom_test_id <= 0:
        return

    teacher_id = db.scalar(
        select(TeacherAuthoredTest.teacher_id).where(TeacherAuthoredTest.id == custom_test_id)
    )
    if not teacher_id:
        return

    cache.delete_pattern(f"teacher:{int(teacher_id)}:custom-test:{custom_test_id}:results:*")


@router.post("/generate", response_model=TestResponse)
@router.post("/assemble", response_model=TestResponse)
def generate_test(
    payload: GenerateTestRequest,
    db: DBSession,
    current_user: User = Depends(require_role(UserRole.student)),
) -> TestResponse:
    subject = db.get(Subject, payload.subject_id)
    if not subject:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Предмет не найден")

    raw_warning_limit = getattr(payload, "warning_limit", None)
    if raw_warning_limit is None:
        normalized_warning_limit = 10
    else:
        normalized_warning_limit = int(raw_warning_limit)
        if normalized_warning_limit <= 0:
            normalized_warning_limit = 10

    test = test_assembly_service.assemble_from_catalog(
        db=db,
        student=current_user,
        subject=subject,
        difficulty=payload.difficulty,
        language=payload.language,
        mode=payload.mode,
        num_questions=payload.num_questions,
        time_limit_minutes=payload.time_limit_minutes,
        warning_limit=normalized_warning_limit,
    )
    return _build_test_response(test)


@router.post("/{test_id}/answer", response_model=RuntimeAnswerResponse)
def answer_test_question(
    test_id: int,
    payload: RuntimeAnswerRequest,
    db: DBSession,
    current_user: User = Depends(require_role(UserRole.student)),
) -> RuntimeAnswerResponse:
    outcome = attempt_runtime_service.answer_question(
        db=db,
        student=current_user,
        test_id=test_id,
        question_id=payload.question_id,
        student_answer_json=payload.student_answer_json,
        latency_ms=payload.latency_ms,
    )
    return RuntimeAnswerResponse(
        question_id=outcome.question_id,
        is_correct=outcome.is_correct,
        score=outcome.score,
        answered_count=outcome.answered_count,
        total_questions=outcome.total_questions,
        warning_count=outcome.warning_count,
    )


@router.get("/{test_id}/state", response_model=RuntimeStateResponse)
def get_test_state(
    test_id: int,
    db: DBSession,
    current_user: User = Depends(require_role(UserRole.student)),
) -> RuntimeStateResponse:
    state = attempt_runtime_service.get_state(db=db, student=current_user, test_id=test_id)
    test = state.test
    session = test.session
    if session is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Сессия теста не найдена")

    answers_by_question_id: dict[int, Answer] = {}
    for question in test.questions:
        if not question.answers:
            continue
        latest = sorted(question.answers, key=lambda item: item.id)[-1]
        answers_by_question_id[int(question.id)] = latest

    answers = [
        RuntimeStateAnswer(
            question_id=int(question.id),
            answered=int(question.id) in answers_by_question_id,
            score=(
                float(answers_by_question_id[int(question.id)].score)
                if int(question.id) in answers_by_question_id
                else None
            ),
            is_correct=(
                bool(answers_by_question_id[int(question.id)].is_correct)
                if int(question.id) in answers_by_question_id
                else None
            ),
        )
        for question in sorted(test.questions, key=lambda item: item.id)
    ]

    answered_count = sum(1 for item in answers if item.answered)
    return RuntimeStateResponse(
        test_id=test.id,
        submitted=state.submitted,
        created_at=test.created_at,
        started_at=session.started_at,
        submitted_at=session.submitted_at,
        elapsed_seconds=state.elapsed_seconds,
        time_limit_seconds=session.time_limit_seconds,
        warning_limit=session.warning_limit,
        warning_count=int(session.warning_count or 0),
        warning_events=state.warning_events,
        answered_count=answered_count,
        total_questions=len(test.questions),
        answers=answers,
    )


@router.post("/generate-from-custom/{custom_test_id}", response_model=TestResponse)
def generate_test_from_custom_template(
    custom_test_id: int,
    db: DBSession,
    current_user: User = Depends(require_role(UserRole.student)),
) -> TestResponse:
    memberships = db.scalars(
        select(GroupMembership)
        .where(GroupMembership.student_id == current_user.id)
        .order_by(GroupMembership.group_id.asc())
    ).all()
    if not memberships:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Вы не состоите в группе. Доступ к групповым тестам закрыт.",
        )
    student_group_ids = sorted({int(item.group_id) for item in memberships if int(item.group_id) > 0})
    if not student_group_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Вы не состоите в группе. Доступ к групповым тестам закрыт.",
        )

    custom_test = db.execute(
        select(TeacherAuthoredTest)
        .options(
            selectinload(TeacherAuthoredTest.questions),
            selectinload(TeacherAuthoredTest.assignments),
        )
        .join(TestAssignment, TestAssignment.test_id == TeacherAuthoredTest.id)
        .where(
            TeacherAuthoredTest.id == custom_test_id,
            TestAssignment.group_id.in_(student_group_ids),
            TeacherAuthoredTest.moderation_status == TestModerationStatus.approved,
        )
    ).unique().scalar_one_or_none()

    assignment_group_id: int | None = None
    if custom_test is not None:
        assignment_group_id = next(
            (
                int(link.group_id)
                for link in custom_test.assignments
                if int(link.group_id) in student_group_ids
            ),
            None,
        )

    if custom_test is None:
        custom_test = db.execute(
        select(TeacherAuthoredTest)
        .options(
            selectinload(TeacherAuthoredTest.questions),
            selectinload(TeacherAuthoredTest.group_links),
        )
        .join(TeacherAuthoredTestGroup, TeacherAuthoredTestGroup.test_id == TeacherAuthoredTest.id)
        .where(
            TeacherAuthoredTest.id == custom_test_id,
            TeacherAuthoredTestGroup.group_id.in_(student_group_ids),
            TeacherAuthoredTest.institution_id.is_(None),
        )
        ).unique().scalar_one_or_none()
    if not custom_test:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Групповой тест не найден")
    if custom_test.institution_id is not None and custom_test.moderation_status != TestModerationStatus.approved:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Этот тест ещё не прошёл модерацию и недоступен для прохождения.",
        )
    if custom_test.institution_id is not None and assignment_group_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Этот тест не назначен вашей группе.",
        )
    if not custom_test.questions:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="В выбранном тесте нет вопросов")
    if custom_test.due_date and custom_test.due_date < date.today():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Срок сдачи теста истёк.",
        )
    assigned_group_id = assignment_group_id
    if assigned_group_id is None:
        assigned_group_id = next(
            (
                int(link.group_id)
                for link in sorted(custom_test.group_links, key=lambda item: item.group_id)
                if int(link.group_id) in student_group_ids
            ),
            student_group_ids[0],
        )

    completed_group_tests = db.scalars(
        select(Test)
        .join(TestSession, TestSession.test_id == Test.id)
        .options(joinedload(Test.session), joinedload(Test.result))
        .where(
            Test.student_id == current_user.id,
            TestSession.exam_kind == "group_custom",
            TestSession.submitted_at.is_not(None),
        )
        .order_by(Test.created_at.asc(), Test.id.asc())
    ).all()
    already_completed = False
    for completed in completed_group_tests:
        if not completed.session or not completed.result:
            continue
        config = completed.session.exam_config_json or {}
        raw_custom_test_id = config.get("custom_test_id")
        resolved_custom_test_id = 0
        if isinstance(raw_custom_test_id, str) and raw_custom_test_id.isdigit():
            resolved_custom_test_id = int(raw_custom_test_id)
        elif isinstance(raw_custom_test_id, int):
            resolved_custom_test_id = int(raw_custom_test_id)
        if resolved_custom_test_id == custom_test.id:
            already_completed = True
            break
    if already_completed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Этот групповой тест уже пройден. Повторное прохождение недоступно.",
        )

    profile = db.get(StudentProfile, current_user.id)
    language = profile.preferred_language if profile and profile.preferred_language else PreferredLanguage.ru
    subject = _get_or_create_group_custom_subject(db)

    test = Test(
        student_id=current_user.id,
        subject_id=subject.id,
        difficulty=DifficultyLevel.medium,
        language=language,
        mode=TestMode.text,
    )
    db.add(test)
    db.flush()
    db.add(
        TestSession(
            test_id=test.id,
            time_limit_seconds=max(60, normalize_custom_test_time_limit_seconds(custom_test.time_limit_seconds)),
            warning_limit=max(0, int(custom_test.warning_limit)),
            pipeline_version="unified_v1",
            exam_kind="group_custom",
            exam_config_json={
                "title": custom_test.title,
                "custom_test_id": custom_test.id,
                "group_id": assigned_group_id,
            },
        )
    )

    ordered_questions = sorted(custom_test.questions, key=lambda item: item.order_index)
    for source in ordered_questions:
        try:
            normalized_type = QuestionType(source.question_type)
        except ValueError:
            normalized_type = QuestionType.short_text

        if normalized_type not in {QuestionType.single_choice, QuestionType.short_text}:
            normalized_type = QuestionType.short_text

        test.questions.append(
            Question(
                test_id=test.id,
                type=normalized_type,
                prompt=str(source.prompt or "").strip(),
                options_json=dict(source.options_json or {}) if source.options_json else None,
                correct_answer_json=dict(source.correct_answer_json or {}),
                explanation_json={
                    "topic": custom_test.title,
                    "custom_test_id": custom_test.id,
                    "custom_question_id": source.id,
                },
                tts_text=None,
            )
        )

    db.commit()
    db.refresh(test)
    return _build_test_response(test)


@router.post("/generate-exam", response_model=TestResponse)
def generate_exam_test(
    payload: GenerateExamTestRequest,
    db: DBSession,
    current_user: User = Depends(require_role(UserRole.student)),
) -> TestResponse:
    if payload.exam_type == "ent":
        return _generate_ent_exam_test(db=db, current_user=current_user, payload=payload)
    return _generate_ielts_exam_test(db=db, current_user=current_user, payload=payload)


def _generate_ent_exam_test(*, db: DBSession, current_user: User, payload: GenerateExamTestRequest) -> TestResponse:
    subject_lookup = _build_subject_lookup(db)
    history_subject = _find_subject_by_aliases(subject_lookup, ["история", "всемирная история"])
    math_subject = _find_subject_by_aliases(subject_lookup, ["математика"])
    reading_subject = _find_subject_by_aliases(subject_lookup, ["русский язык", "орыс тілі"])
    if not history_subject or not math_subject or not reading_subject:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Не удалось сформировать ЕНТ: отсутствуют обязательные предметы в базе.",
        )

    profile_candidates = {
        _normalize_subject_name(subject.name_ru): subject
        for subject in subject_lookup.values()
        if _normalize_subject_name(subject.name_ru) in {"математика", "физика", "биология", "химия", "информатика"}
    }
    if payload.ent_profile_subject_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Для ЕНТ выберите профильный предмет.",
        )

    primary_profile = db.get(Subject, payload.ent_profile_subject_id)
    if not primary_profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Профильный предмет не найден")
    primary_key = _normalize_subject_name(primary_profile.name_ru)
    if primary_key not in profile_candidates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Для ЕНТ можно выбрать только один из 5 профильных предметов: математика, физика, биология, химия, информатика.",
        )

    profile_pair_by_primary = {
        "математика": "физика",
        "физика": "математика",
        "биология": "химия",
        "химия": "биология",
        "информатика": "математика",
    }
    secondary_key = profile_pair_by_primary.get(primary_key, "математика")
    secondary_profile = profile_candidates.get(secondary_key)
    if not secondary_profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Не удалось подобрать вторую профильную дисциплину для ЕНТ.",
        )

    sections = [
        {
            "code": "ent_history",
            "title": "История Казахстана",
            "subject": history_subject,
            "count": 20,
            "mode": TestMode.text,
            "difficulty_order": [DifficultyLevel.medium, DifficultyLevel.easy, DifficultyLevel.hard],
        },
        {
            "code": "ent_math_literacy",
            "title": "Математическая грамотность",
            "subject": math_subject,
            "count": 10,
            "mode": TestMode.text,
            "difficulty_order": [DifficultyLevel.easy, DifficultyLevel.medium, DifficultyLevel.hard],
        },
        {
            "code": "ent_reading_literacy",
            "title": "Грамотность чтения",
            "subject": reading_subject,
            "count": 10,
            "mode": TestMode.text,
            "difficulty_order": [DifficultyLevel.medium, DifficultyLevel.easy, DifficultyLevel.hard],
        },
        {
            "code": "ent_profile_primary",
            "title": f"Профиль 1: {primary_profile.name_ru}",
            "subject": primary_profile,
            "count": 40,
            "mode": TestMode.text,
            "difficulty_order": [DifficultyLevel.hard, DifficultyLevel.medium, DifficultyLevel.easy],
        },
        {
            "code": "ent_profile_secondary",
            "title": f"Профиль 2: {secondary_profile.name_ru}",
            "subject": secondary_profile,
            "count": 40,
            "mode": TestMode.text,
            "difficulty_order": [DifficultyLevel.hard, DifficultyLevel.medium, DifficultyLevel.easy],
        },
    ]

    used_catalog_question_ids: set[int] = set()
    used_catalog_content_hashes: set[str] = set()
    used_prompt_keys: set[str] = set()
    generated_questions: list[Any] = []
    global_index = 0

    for section_index, section in enumerate(sections, start=1):
        section_questions = _collect_exam_section_questions(
            db=db,
            student_id=current_user.id,
            subject=section["subject"],
            language=payload.language,
            mode=section["mode"],
            count=section["count"],
            base_seed=f"ent::{current_user.id}::{section['subject'].id}::{section['code']}",
            difficulty_order=section["difficulty_order"],
            used_catalog_question_ids=used_catalog_question_ids,
            used_catalog_content_hashes=used_catalog_content_hashes,
            used_prompt_keys=used_prompt_keys,
        )

        for position, question in enumerate(section_questions, start=1):
            global_index += 1
            generated_questions.append(
                _decorate_exam_question(
                    question=question,
                    exam_kind="ent",
                    section_code=section["code"],
                    section_title=section["title"],
                    section_order=section_index,
                    section_position=position,
                    global_position=global_index,
                )
            )

    test = Test(
        student_id=current_user.id,
        subject_id=primary_profile.id,
        difficulty=DifficultyLevel.hard,
        language=payload.language,
        mode=TestMode.text,
    )
    db.add(test)
    db.flush()
    db.add(
        TestSession(
            test_id=test.id,
            time_limit_seconds=240 * 60,
            warning_limit=1,
            pipeline_version="unified_v1",
            exam_kind="ent",
            exam_config_json={
                "title": "ЕНТ",
                "total_questions": 120,
                "max_score": 140,
                "pass_score": 50,
                "auto_submit_on_warning": True,
                "profile_primary_subject_id": primary_profile.id,
                "profile_secondary_subject_id": secondary_profile.id,
                "sections": [
                    {
                        "code": item["code"],
                        "title": item["title"],
                        "duration_minutes": None,
                        "question_count": item["count"],
                    }
                    for item in sections
                ],
            },
        )
    )

    for generated_question in generated_questions:
        test.questions.append(
            Question(
                test_id=test.id,
                type=generated_question.type,
                prompt=generated_question.prompt,
                options_json=generated_question.options_json,
                correct_answer_json=generated_question.correct_answer_json,
                explanation_json=generated_question.explanation_json,
                tts_text=generated_question.tts_text,
            )
        )

    db.commit()
    db.refresh(test)
    return _build_test_response(test)


def _generate_ielts_exam_test(*, db: DBSession, current_user: User, payload: GenerateExamTestRequest) -> TestResponse:
    subject_lookup = _build_subject_lookup(db)
    english_subject = _find_subject_by_aliases(subject_lookup, ["английский язык", "ағылшын тілі"])
    if not english_subject:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Не удалось сформировать IELTS: предмет «Английский язык» отсутствует в базе.",
        )

    sections = [
        {
            "code": "ielts_listening",
            "title": "Listening",
            "duration_minutes": 30,
            "count": 20,
            "mode": TestMode.audio,
            "difficulty_order": [DifficultyLevel.medium, DifficultyLevel.easy, DifficultyLevel.hard],
            "postprocess": "as_is",
        },
        {
            "code": "ielts_reading",
            "title": "Reading",
            "duration_minutes": 60,
            "count": 20,
            "mode": TestMode.text,
            "difficulty_order": [DifficultyLevel.medium, DifficultyLevel.hard, DifficultyLevel.easy],
            "postprocess": "as_is",
        },
        {
            "code": "ielts_writing",
            "title": "Writing",
            "duration_minutes": 60,
            "count": 10,
            "mode": TestMode.oral,
            "difficulty_order": [DifficultyLevel.hard, DifficultyLevel.medium, DifficultyLevel.easy],
            "postprocess": "to_short_text",
        },
        {
            "code": "ielts_speaking",
            "title": "Speaking",
            "duration_minutes": 14,
            "count": 10,
            "mode": TestMode.oral,
            "difficulty_order": [DifficultyLevel.hard, DifficultyLevel.medium, DifficultyLevel.easy],
            "postprocess": "to_oral",
        },
    ]

    used_catalog_question_ids: set[int] = set()
    used_catalog_content_hashes: set[str] = set()
    used_prompt_keys: set[str] = set()
    generated_questions: list[Any] = []
    global_index = 0

    for section_index, section in enumerate(sections, start=1):
        section_questions = _collect_exam_section_questions(
            db=db,
            student_id=current_user.id,
            subject=english_subject,
            language=payload.language,
            mode=section["mode"],
            count=section["count"],
            base_seed=f"ielts::{current_user.id}::{section['code']}",
            difficulty_order=section["difficulty_order"],
            used_catalog_question_ids=used_catalog_question_ids,
            used_catalog_content_hashes=used_catalog_content_hashes,
            used_prompt_keys=used_prompt_keys,
        )

        for position, question in enumerate(section_questions, start=1):
            converted = question
            if section["postprocess"] == "to_short_text":
                converted = _convert_question_to_short_text(question=question, language=payload.language)
            elif section["postprocess"] == "to_oral":
                converted = _convert_question_to_oral(question=question, language=payload.language)

            global_index += 1
            generated_questions.append(
                _decorate_exam_question(
                    question=converted,
                    exam_kind="ielts",
                    section_code=section["code"],
                    section_title=section["title"],
                    section_order=section_index,
                    section_position=position,
                    global_position=global_index,
                )
            )

    total_minutes = sum(int(item["duration_minutes"]) for item in sections)
    test = Test(
        student_id=current_user.id,
        subject_id=english_subject.id,
        difficulty=DifficultyLevel.hard,
        language=payload.language,
        mode=TestMode.text,
    )
    db.add(test)
    db.flush()
    db.add(
        TestSession(
            test_id=test.id,
            time_limit_seconds=total_minutes * 60,
            warning_limit=1,
            pipeline_version="unified_v1",
            exam_kind="ielts",
            exam_config_json={
                "title": "IELTS",
                "total_questions": len(generated_questions),
                "auto_submit_on_warning": True,
                "sections": [
                    {
                        "code": item["code"],
                        "title": item["title"],
                        "duration_minutes": item["duration_minutes"],
                        "question_count": item["count"],
                    }
                    for item in sections
                ],
            },
        )
    )

    for generated_question in generated_questions:
        test.questions.append(
            Question(
                test_id=test.id,
                type=generated_question.type,
                prompt=generated_question.prompt,
                options_json=generated_question.options_json,
                correct_answer_json=generated_question.correct_answer_json,
                explanation_json=generated_question.explanation_json,
                tts_text=generated_question.tts_text,
            )
        )

    db.commit()
    db.refresh(test)
    return _build_test_response(test)


@router.post("/generate-from-mistakes", response_model=TestResponse)
def generate_test_from_mistakes(
    payload: GenerateMistakesTestRequest,
    db: DBSession,
    current_user: User = Depends(require_role(UserRole.student)),
) -> TestResponse:
    wrong_questions = _load_wrong_questions(
        db=db,
        student_id=current_user.id,
        subject_id=payload.subject_id,
    )
    if not wrong_questions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Недостаточно ошибок в истории. Пройдите обычный тест и вернитесь к повторению.",
        )

    selected_subject_id = payload.subject_id
    if selected_subject_id is None:
        subject_counter = Counter(test.subject_id for _, test in wrong_questions)
        selected_subject_id = subject_counter.most_common(1)[0][0]

    questions_for_subject = [(question, source_test) for question, source_test in wrong_questions if source_test.subject_id == selected_subject_id]
    if payload.language is not None:
        questions_for_subject = [(question, source_test) for question, source_test in questions_for_subject if source_test.language == payload.language]
    selected_pairs = questions_for_subject[: payload.num_questions]
    if not selected_pairs:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Для выбранных параметров нет ошибок в истории.")

    selected_subject = db.get(Subject, selected_subject_id)
    if not selected_subject:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Предмет не найден")

    selected_language = payload.language or selected_pairs[0][1].language
    test = Test(
        student_id=current_user.id,
        subject_id=selected_subject.id,
        difficulty=payload.difficulty,
        language=selected_language,
        mode=TestMode.text,
    )
    db.add(test)
    db.flush()
    db.add(TestSession(test_id=test.id, time_limit_seconds=None, pipeline_version="unified_v1"))

    for source_question, source_test in selected_pairs:
        normalized_type = source_question.type
        if normalized_type not in {QuestionType.single_choice, QuestionType.multi_choice, QuestionType.short_text}:
            normalized_type = QuestionType.short_text

        prompt = source_question.prompt
        if normalized_type == QuestionType.short_text:
            if selected_language == PreferredLanguage.ru and "краткий" not in prompt.lower():
                prompt = f"{prompt} Дайте краткий текстовый ответ."
            if selected_language == PreferredLanguage.kz and "қысқа" not in prompt.lower():
                prompt = f"{prompt} Қысқа мәтіндік жауап беріңіз."

        cloned = Question(
            test_id=test.id,
            type=normalized_type,
            prompt=prompt,
            options_json=dict(source_question.options_json or {}) if source_question.options_json else None,
            correct_answer_json=source_question.correct_answer_json,
            explanation_json={
                **source_question.explanation_json,
                "source_test_id": source_test.id,
                "review_mode": "mistakes",
            },
            tts_text=None,
        )
        test.questions.append(cloned)

    db.commit()
    db.refresh(test)
    return _build_test_response(test)


@router.get("/{test_id}", response_model=TestResponse)
def get_test(test_id: int, db: DBSession, current_user: CurrentUser) -> TestResponse:
    test = _load_test(db, test_id)
    _assert_access(db, test, current_user)
    return _build_test_response(test)


@router.get("/{test_id}/questions/{question_id}/tts")
def get_question_tts_audio(
    test_id: int,
    question_id: int,
    db: DBSession,
    current_user: CurrentUser,
    voice: str | None = None,
) -> StreamingResponse:
    test = _load_test(db, test_id)
    _assert_access(db, test, current_user)

    question = next((item for item in test.questions if item.id == question_id), None)
    if not question:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Вопрос не найден")

    text = _build_question_tts_narration(question=question, language=test.language)
    if not text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Текст вопроса пуст")

    try:
        audio = tts_service.synthesize(text=text, language=test.language, voice=voice)
    except TTSProviderUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except TTSServiceError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return StreamingResponse(
        BytesIO(audio.audio_bytes),
        media_type=audio.content_type,
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'inline; filename="test-{test_id}-q-{question_id}.mp3"',
        },
    )


@router.post("/{test_id}/submit", response_model=SubmitTestResponse)
def submit_test(
    test_id: int,
    payload: SubmitTestRequest,
    db: DBSession,
    current_user: User = Depends(require_role(UserRole.student)),
) -> SubmitTestResponse:
    test = _load_test(db, test_id)
    if test.student_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нельзя отправить тест другого студента")

    submit_outcome = attempt_runtime_service.submit_test(
        db=db,
        student=current_user,
        test_id=test_id,
        answers=[
            {"question_id": item.question_id, "student_answer_json": item.student_answer_json}
            for item in payload.answers
        ],
        telemetry=payload.telemetry,
    )
    runtime_test = submit_outcome.test
    runtime_session = runtime_test.session
    runtime_result = runtime_test.result
    runtime_recommendation = runtime_test.recommendation

    if runtime_session is None or runtime_result is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Не удалось завершить тест.")

    _invalidate_student_dashboard_cache(current_user.id)
    _invalidate_teacher_custom_results_cache_for_submitted_test(db=db, test=runtime_test)

    recommendation_payload = _build_recommendation_response_payload(
        recommendation=runtime_recommendation,
        fallback_weak_topics=list(submit_outcome.evaluation.weak_topics),
    )

    return SubmitTestResponse(
        test_id=runtime_test.id,
        result=ResultResponse(
            total_score=float(runtime_result.total_score),
            max_score=float(runtime_result.max_score),
            percent=float(runtime_result.percent),
            elapsed_seconds=int(runtime_session.elapsed_seconds or 0),
            time_limit_seconds=runtime_session.time_limit_seconds,
            warning_count=int(runtime_session.warning_count or 0),
        ),
        integrity_warnings=[TestWarningSignal.model_validate(item) for item in submit_outcome.warning_events],
        feedback=submit_outcome.evaluation.feedback,
        recommendation=RecommendationResponse(**recommendation_payload),
    )


@router.get("/{test_id}/result", response_model=TestResultDetailsResponse)
def get_test_result(test_id: int, db: DBSession, current_user: CurrentUser) -> TestResultDetailsResponse:
    test = _load_test(db, test_id)
    _assert_access(db, test, current_user)

    if not test.result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Результат не найден")

    _ensure_bilingual_recommendation(db=db, test=test)

    persisted_feedback, fallback_weak_topics = _build_feedback_from_persisted_answers(test)
    recommendation = test.recommendation
    session = test.session
    warning_events = _normalize_warning_events_json(session.warning_events_json if session else [])
    recommendation_payload = _build_recommendation_response_payload(
        recommendation=recommendation,
        fallback_weak_topics=fallback_weak_topics,
    )
    return TestResultDetailsResponse(
        test_id=test.id,
        submitted_at=test.result.created_at,
        result=_build_result_response(result=test.result, session=session),
        integrity_warnings=warning_events,
        feedback=persisted_feedback,
        recommendation=RecommendationResponse(**recommendation_payload),
    )


@router.post("/{test_id}/recommendations/regenerate", response_model=RecommendationResponse)
def regenerate_recommendations(
    test_id: int,
    db: DBSession,
    current_user: User = Depends(require_role(UserRole.student)),
) -> RecommendationResponse:
    test = _load_test(db, test_id)
    if test.student_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нельзя обновить рекомендации для чужого теста")

    if not test.recommendation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Рекомендации не найдены")

    current_weak_topics = list(test.recommendation.weak_topics_json)
    warning_count = int(test.session.warning_count if test.session else 0)
    percent = float(test.result.percent if test.result else 0.0)
    recommendation_payloads, weak_topics = recommendation_service.build_bilingual(
        subject=test.subject,
        facts=RecommendationFacts(
            percent=percent,
            warning_count=warning_count,
            weak_topics=current_weak_topics,
        ),
    )
    generated = recommendation_payloads[test.language]
    generated_ru = recommendation_payloads[PreferredLanguage.ru]
    generated_kz = recommendation_payloads[PreferredLanguage.kz]

    test.recommendation.weak_topics_json = weak_topics
    test.recommendation.advice_text = generated.advice_text
    test.recommendation.advice_text_ru = generated_ru.advice_text
    test.recommendation.advice_text_kz = generated_kz.advice_text
    test.recommendation.generated_tasks_json = generated.generated_tasks
    test.recommendation.generated_tasks_ru_json = generated_ru.generated_tasks
    test.recommendation.generated_tasks_kz_json = generated_kz.generated_tasks
    db.commit()
    _invalidate_student_dashboard_cache(current_user.id)

    return RecommendationResponse(
        weak_topics=weak_topics,
        advice_text=generated.advice_text,
        generated_tasks=generated.generated_tasks,
        advice_text_ru=generated_ru.advice_text,
        advice_text_kz=generated_kz.advice_text,
        generated_tasks_ru=generated_ru.generated_tasks,
        generated_tasks_kz=generated_kz.generated_tasks,
    )


def _build_recommendation_response_payload(
    *,
    recommendation: Recommendation | None,
    fallback_weak_topics: list[str],
) -> dict[str, Any]:
    if not recommendation:
        return {
            "weak_topics": list(fallback_weak_topics),
            "advice_text": "",
            "generated_tasks": [],
            "advice_text_ru": "",
            "advice_text_kz": "",
            "generated_tasks_ru": [],
            "generated_tasks_kz": [],
        }

    advice_text_ru = (
        str(recommendation.advice_text_ru).strip()
        if recommendation.advice_text_ru is not None
        else str(recommendation.advice_text).strip()
    )
    advice_text_kz = (
        str(recommendation.advice_text_kz).strip()
        if recommendation.advice_text_kz is not None
        else advice_text_ru
    )
    generated_tasks_legacy = (
        list(recommendation.generated_tasks_json)
        if isinstance(recommendation.generated_tasks_json, list)
        else []
    )
    generated_tasks_ru = (
        list(recommendation.generated_tasks_ru_json)
        if isinstance(recommendation.generated_tasks_ru_json, list)
        else list(generated_tasks_legacy)
    )
    generated_tasks_kz = (
        list(recommendation.generated_tasks_kz_json)
        if isinstance(recommendation.generated_tasks_kz_json, list)
        else list(generated_tasks_ru)
    )

    # Keep legacy fields for backward compatibility with older clients.
    return {
        "weak_topics": list(recommendation.weak_topics_json) if isinstance(recommendation.weak_topics_json, list) else list(fallback_weak_topics),
        "advice_text": str(recommendation.advice_text or ""),
        "generated_tasks": generated_tasks_legacy,
        "advice_text_ru": advice_text_ru,
        "advice_text_kz": advice_text_kz,
        "generated_tasks_ru": generated_tasks_ru,
        "generated_tasks_kz": generated_tasks_kz,
    }


def _ensure_bilingual_recommendation(*, db: DBSession, test: Test) -> None:
    recommendation = test.recommendation
    if not recommendation:
        return
    if not test.result:
        return

    has_ru = bool(str(recommendation.advice_text_ru or "").strip()) and isinstance(
        recommendation.generated_tasks_ru_json, list
    )
    has_kz = bool(str(recommendation.advice_text_kz or "").strip()) and isinstance(
        recommendation.generated_tasks_kz_json, list
    )
    if has_ru and has_kz:
        return

    warning_count = int(test.session.warning_count if test.session else 0)
    percent = float(test.result.percent)
    weak_topics = list(recommendation.weak_topics_json or [])
    try:
        payloads, _ = recommendation_service.build_bilingual(
            subject=test.subject,
            facts=RecommendationFacts(
                percent=percent,
                warning_count=warning_count,
                weak_topics=weak_topics,
            ),
        )
        payload_ru = payloads[PreferredLanguage.ru]
        payload_kz = payloads[PreferredLanguage.kz]
        recommendation.advice_text_ru = payload_ru.advice_text
        recommendation.advice_text_kz = payload_kz.advice_text
        recommendation.generated_tasks_ru_json = payload_ru.generated_tasks
        recommendation.generated_tasks_kz_json = payload_kz.generated_tasks
        if test.language == PreferredLanguage.kz:
            recommendation.advice_text = payload_kz.advice_text
            recommendation.generated_tasks_json = payload_kz.generated_tasks
        else:
            recommendation.advice_text = payload_ru.advice_text
            recommendation.generated_tasks_json = payload_ru.generated_tasks
        db.commit()
        db.refresh(test)
    except Exception as exc:  # noqa: BLE001
        # Keep backward compatibility: if bilingual build fails, return legacy recommendation as-is.
        logger.warning("Failed to refresh bilingual recommendation for test_id=%s: %s", test.id, exc)
        db.rollback()


def _normalize_subject_name(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower().replace("ё", "е"))


def _build_subject_lookup(db: DBSession) -> dict[str, Subject]:
    lookup: dict[str, Subject] = {}
    for subject in db.scalars(select(Subject)).all():
        lookup[_normalize_subject_name(subject.name_ru)] = subject
        lookup[_normalize_subject_name(subject.name_kz)] = subject
    return lookup


def _find_subject_by_aliases(lookup: dict[str, Subject], aliases: list[str]) -> Subject | None:
    for alias in aliases:
        subject = lookup.get(_normalize_subject_name(alias))
        if subject:
            return subject
    return None


def _collect_exam_section_questions(
    *,
    db: DBSession,
    student_id: int,
    subject: Subject,
    language: PreferredLanguage,
    mode: TestMode,
    count: int,
    base_seed: str,
    difficulty_order: list[DifficultyLevel],
    used_catalog_question_ids: set[int],
    used_catalog_content_hashes: set[str],
    used_prompt_keys: set[str],
) -> list[Any]:
    question_catalog_service.ensure_subject_catalog_ready(db=db, subject=subject)

    difficulty_sequence: list[DifficultyLevel] = []
    for level in [*difficulty_order, DifficultyLevel.medium, DifficultyLevel.easy, DifficultyLevel.hard]:
        if level not in difficulty_sequence:
            difficulty_sequence.append(level)

    candidate_pool: list[CatalogQuestion] = []
    seen_candidate_ids: set[int] = set()
    fetch_limit = max(240, count * 12)
    for difficulty in difficulty_sequence:
        rows = question_catalog_service.get_published_candidates(
            db=db,
            subject_id=subject.id,
            difficulty=difficulty,
            language=language,
            mode=mode,
            limit=fetch_limit,
        )
        for row in rows:
            row_id = int(row.id)
            if row_id in seen_candidate_ids:
                continue
            seen_candidate_ids.add(row_id)
            candidate_pool.append(row)

    if not candidate_pool:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "INSUFFICIENT_QUESTION_POOL",
                "message": f"Для секции «{subject.name_ru}» нет опубликованных вопросов.",
            },
        )

    coverage_map = _load_student_coverage_for_catalog_ids(
        db=db,
        student_id=student_id,
        catalog_question_ids=[int(row.id) for row in candidate_pool],
    )
    weak_topics = _collect_weak_topics_from_attempts(
        db=db,
        student_id=student_id,
        subject_id=subject.id,
    )
    selector = subject_selector_registry.get(subject=subject)
    ranked_pool = selector.select(
        subject=subject,
        candidates=candidate_pool,
        coverage_map=coverage_map,
        weak_topics=weak_topics,
        limit=max(count * 4, count + 20),
        seed=f"{base_seed}::selector",
    )
    if not ranked_pool:
        ranked_pool = candidate_pool

    selected: list[GeneratedQuestionPayload] = []
    section_question_keys: set[str] = set()

    def try_add_question(candidate: GeneratedQuestionPayload) -> bool:
        question_key = _exam_question_uniqueness_key(candidate)
        if not question_key or question_key in used_prompt_keys or question_key in section_question_keys:
            return False

        selected.append(candidate)
        section_question_keys.add(question_key)
        return True

    for catalog_item in [*ranked_pool, *candidate_pool]:
        if len(selected) >= count:
            break

        catalog_id = int(catalog_item.id)
        if catalog_id in used_catalog_question_ids:
            continue

        content_hash = str(catalog_item.content_hash or "").strip().lower()
        if content_hash and content_hash in used_catalog_content_hashes:
            continue

        candidate = _catalog_question_to_generated_payload(catalog_item)
        if candidate is None:
            continue

        if not try_add_question(candidate):
            continue
        used_catalog_question_ids.add(catalog_id)
        if content_hash:
            used_catalog_content_hashes.add(content_hash)

    if len(selected) < count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "INSUFFICIENT_QUESTION_POOL",
                "message": (
                    f"Недостаточно валидных уникальных вопросов для секции «{subject.name_ru}»: "
                    f"доступно {len(selected)} из {count}."
                ),
            },
        )

    used_prompt_keys.update(section_question_keys)
    return selected[:count]


def _catalog_question_to_generated_payload(catalog_item: CatalogQuestion) -> GeneratedQuestionPayload | None:
    prompt = str(catalog_item.prompt or "").strip()
    if len(prompt) < 6:
        return None

    explanation_json = dict(catalog_item.explanation_json or {})
    topic_tags = [str(item).strip() for item in (catalog_item.topic_tags_json or []) if str(item).strip()]
    if not str(explanation_json.get("topic", "")).strip():
        explanation_json["topic"] = topic_tags[0] if topic_tags else "General"
    explanation_json["catalog_question_id"] = int(catalog_item.id)
    explanation_json["catalog_content_hash"] = str(catalog_item.content_hash or "").strip()
    explanation_json["catalog_source"] = str(catalog_item.source or "").strip()

    question_type = QuestionType(str(catalog_item.type.value))
    correct_answer_json = dict(catalog_item.correct_answer_json or {})

    options_payload: dict[str, Any] | None = None
    if question_type in {QuestionType.single_choice, QuestionType.multi_choice}:
        raw_options = (catalog_item.options_json or {}).get("options", [])
        normalized_options: list[dict[str, Any]] = []
        for idx, raw in enumerate(raw_options):
            if isinstance(raw, dict):
                option_text = str(raw.get("text", "")).strip()
                option_id_raw = raw.get("id")
                if isinstance(option_id_raw, int):
                    option_id = option_id_raw
                elif isinstance(option_id_raw, str) and option_id_raw.strip().isdigit():
                    option_id = int(option_id_raw.strip())
                else:
                    option_id = idx + 1
            else:
                option_text = str(raw).strip()
                option_id = idx + 1
            if not option_text:
                continue
            normalized_options.append({"id": option_id, "text": option_text})

        if len(normalized_options) < 2:
            return None
        options_payload = {"options": normalized_options}
        option_ids = {int(item["id"]) for item in normalized_options}
        correct_option_ids: list[int] = []
        for value in (correct_answer_json.get("correct_option_ids") or []):
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                continue
            if parsed in option_ids and parsed not in correct_option_ids:
                correct_option_ids.append(parsed)

        if question_type == QuestionType.single_choice and len(correct_option_ids) != 1:
            return None
        if question_type == QuestionType.multi_choice and len(correct_option_ids) < 1:
            return None
        correct_answer_json = {"correct_option_ids": correct_option_ids}
    elif question_type in {QuestionType.short_text, QuestionType.oral_answer}:
        sample_answer = str(correct_answer_json.get("sample_answer", "")).strip()
        keywords = [
            str(item).strip()
            for item in (correct_answer_json.get("keywords") or [])
            if str(item).strip()
        ]
        if not sample_answer and not keywords:
            return None
        correct_answer_json = {"sample_answer": sample_answer, "keywords": keywords}

    return GeneratedQuestionPayload(
        type=question_type,
        prompt=prompt,
        options_json=options_payload,
        correct_answer_json=correct_answer_json,
        explanation_json=explanation_json,
        tts_text=prompt,
    )


def _load_student_coverage_for_catalog_ids(
    *,
    db: DBSession,
    student_id: int,
    catalog_question_ids: list[int],
) -> dict[int, StudentQuestionCoverage]:
    if not catalog_question_ids:
        return {}
    rows = db.scalars(
        select(StudentQuestionCoverage).where(
            StudentQuestionCoverage.student_id == student_id,
            StudentQuestionCoverage.catalog_question_id.in_(catalog_question_ids),
        )
    ).all()
    return {int(row.catalog_question_id): row for row in rows}


def _exam_prompt_key(prompt: str) -> str:
    normalized = re.sub(r"\s+", " ", prompt.strip().lower())
    normalized = re.sub(r"^\s*\[[^\]]+\]\s*", "", normalized).strip()
    normalized = re.sub(r"^\s*вопрос\s*\d+\s*[:.\-]\s*", "", normalized).strip()
    normalized = re.sub(r"^\s*\d+\s*[-.)]\s*", "", normalized).strip()
    normalized = re.sub(r"\s*\((вариант|нұсқа)\s*\d+\)\s*$", "", normalized, flags=re.IGNORECASE).strip()

    normalized = re.sub(r"[.!?…]+$", "", normalized).strip()
    return normalized


def _exam_question_uniqueness_key(question: Any) -> str:
    explanation = dict(getattr(question, "explanation_json", {}) or {})
    catalog_question_id = explanation.get("catalog_question_id")
    if isinstance(catalog_question_id, int):
        return f"cq::{catalog_question_id}"
    if isinstance(catalog_question_id, str) and catalog_question_id.strip().isdigit():
        return f"cq::{catalog_question_id.strip()}"

    content_hash = str(explanation.get("catalog_content_hash", "")).strip().lower()
    if content_hash:
        return f"ch::{content_hash}"

    template_key = str(explanation.get("library_template_key", "")).strip().lower()
    if template_key:
        return f"tpl::{template_key}"

    content_key = str(explanation.get("library_content_key", "")).strip().lower()
    if content_key:
        return f"cnt::{content_key}"

    return f"pr::{_exam_prompt_key(str(getattr(question, 'prompt', '')))}"


def _decorate_exam_question(
    *,
    question: Any,
    exam_kind: str,
    section_code: str,
    section_title: str,
    section_order: int,
    section_position: int,
    global_position: int,
) -> Any:
    explanation = dict(question.explanation_json or {})
    explanation.update(
        {
            "exam_kind": exam_kind,
            "exam_section_code": section_code,
            "exam_section_title": section_title,
            "exam_section_order": section_order,
            "exam_section_position": section_position,
            "exam_global_position": global_position,
        }
    )
    return question.model_copy(update={"explanation_json": explanation})


def _extract_topic_from_question(question: Any) -> str:
    topic = str((question.explanation_json or {}).get("topic", "")).strip()
    return topic or "Общая тема"


def _extract_sample_answer_from_question(question: Any, language: PreferredLanguage) -> str:
    raw = str((question.correct_answer_json or {}).get("sample_answer", "")).strip()
    if raw:
        return raw

    options = list((question.options_json or {}).get("options", []) or [])
    correct_ids = {
        int(item)
        for item in (question.correct_answer_json or {}).get("correct_option_ids", [])
        if isinstance(item, int)
    }
    selected_texts: list[str] = []
    for option in options:
        if not isinstance(option, dict):
            continue
        option_id = option.get("id")
        if not isinstance(option_id, int) or option_id not in correct_ids:
            continue
        text = _strip_option_prefix(str(option.get("text", "")).strip())
        if text:
            selected_texts.append(text)
    if selected_texts:
        return "; ".join(selected_texts)

    return (
        f"Кратко объясните правильный ответ по теме «{_extract_topic_from_question(question)}»."
        if language == PreferredLanguage.ru
        else f"«{_extract_topic_from_question(question)}» тақырыбы бойынша дұрыс жауапты қысқаша түсіндіріңіз."
    )


def _extract_keywords_from_sample(sample: str, language: PreferredLanguage) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for token in re.findall(r"[a-zA-Zа-яА-ЯәіңғүұқөһӘІҢҒҮҰҚӨҺ0-9]+", sample.lower()):
        if len(token) < 4 or token in seen:
            continue
        seen.add(token)
        values.append(token)
        if len(values) >= 3:
            break
    fallback = "пример" if language == PreferredLanguage.ru else "мысал"
    if fallback not in seen:
        values.append(fallback)
    return values[:4]


def _convert_question_to_short_text(*, question: Any, language: PreferredLanguage) -> Any:
    if question.type == QuestionType.short_text:
        return question

    prompt = str(question.prompt or "").strip()
    if language == PreferredLanguage.ru and "напишите" not in prompt.lower():
        prompt = f"{prompt} Напишите краткий ответ своими словами."
    if language == PreferredLanguage.kz and "жазыңыз" not in prompt.lower():
        prompt = f"{prompt} Өз сөзіңізбен қысқа жауап жазыңыз."

    sample_answer = _extract_sample_answer_from_question(question, language)
    keywords = _extract_keywords_from_sample(sample_answer, language)
    return question.model_copy(
        update={
            "type": QuestionType.short_text,
            "options_json": None,
            "prompt": prompt,
            "correct_answer_json": {"keywords": keywords, "sample_answer": sample_answer},
            "tts_text": None,
        }
    )


def _convert_question_to_oral(*, question: Any, language: PreferredLanguage) -> Any:
    if question.type == QuestionType.oral_answer:
        return question

    prompt = str(question.prompt or "").strip()
    if language == PreferredLanguage.ru and "устно" not in prompt.lower():
        prompt = f"{prompt} Ответьте устно и кратко поясните ответ."
    if language == PreferredLanguage.kz and "ауызша" not in prompt.lower():
        prompt = f"{prompt} Ауызша жауап беріп, қысқаша түсіндіріңіз."

    sample_answer = _extract_sample_answer_from_question(question, language)
    keywords = _extract_keywords_from_sample(sample_answer, language)
    return question.model_copy(
        update={
            "type": QuestionType.oral_answer,
            "options_json": None,
            "prompt": prompt,
            "correct_answer_json": {
                "keywords": keywords,
                "sample_answer": sample_answer,
                "expected_field": "spoken_answer_text",
            },
            "tts_text": None,
        }
    )


def _load_wrong_questions(db: DBSession, student_id: int, subject_id: int | None = None) -> list[tuple[Question, Test]]:
    query = (
        db.query(Question, Test)
        .join(Test, Test.id == Question.test_id)
        .join(Answer, Answer.question_id == Question.id)
        .filter(
            Test.student_id == student_id,
            Answer.is_correct.is_(False),
        )
        .order_by(Test.created_at.desc(), Question.id.desc())
    )
    if subject_id is not None:
        query = query.filter(Test.subject_id == subject_id)

    rows = query.all()
    output: list[tuple[Question, Test]] = []
    seen_question_ids: set[int] = set()
    for question, test in rows:
        if question.id in seen_question_ids:
            continue
        seen_question_ids.add(question.id)
        output.append((question, test))
    return output


def _get_or_create_group_custom_subject(db: DBSession) -> Subject:
    subject = db.scalar(
        select(Subject).where(
            Subject.name_ru == "Групповой тест",
            Subject.name_kz == "Топтық тест",
        )
    )
    if subject:
        return subject

    fallback = db.scalar(select(Subject).where(Subject.name_ru == "Групповой тест"))
    if fallback:
        return fallback

    subject = Subject(name_ru="Групповой тест", name_kz="Топтық тест")
    db.add(subject)
    db.flush()
    return subject


def _load_test(db: DBSession, test_id: int) -> Test:
    test = (
        db.query(Test)
        .options(
            joinedload(Test.questions).joinedload(Question.answers),
            joinedload(Test.subject),
            joinedload(Test.session),
            joinedload(Test.result),
            joinedload(Test.recommendation),
        )
        .filter(Test.id == test_id)
        .first()
    )
    if not test:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Тест не найден")
    return test


def _assert_access(db: DBSession, test: Test, user: User) -> None:
    if user.role == UserRole.teacher:
        teacher_membership_ids = db.scalars(
            select(InstitutionMembership.id).where(
                InstitutionMembership.user_id == int(user.id),
                InstitutionMembership.role == InstitutionMembershipRole.teacher,
                InstitutionMembership.status == InstitutionMembershipStatus.active,
            )
        ).all()

        assigned_teacher_of_student = db.scalar(
            select(GroupMembership.id)
            .join(Group, Group.id == GroupMembership.group_id)
            .join(GroupTeacherAssignment, GroupTeacherAssignment.group_id == Group.id)
            .where(
                GroupMembership.student_id == int(test.student_id),
                GroupTeacherAssignment.teacher_membership_id.in_(teacher_membership_ids or [-1]),
                Group.institution_id.is_not(None),
            )
            .limit(1)
        )
        if assigned_teacher_of_student:
            return

        # Transitional fallback for legacy non-institution groups created before RBAC migration.
        legacy_teacher_of_student = db.scalar(
            select(GroupMembership.id)
            .join(Group, Group.id == GroupMembership.group_id)
            .where(
                GroupMembership.student_id == int(test.student_id),
                Group.teacher_id == int(user.id),
                Group.institution_id.is_(None),
            )
            .limit(1)
        )
        if legacy_teacher_of_student:
            return

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав для доступа к этому тесту",
        )
    if test.student_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав для доступа к этому тесту")


def _build_test_response(test: Test) -> TestResponse:
    questions = [
        QuestionResponse(
            id=question.id,
            type=question.type,
            prompt=question.prompt,
            options_json=question.options_json,
            tts_text=question.tts_text,
        )
        for question in sorted(test.questions, key=lambda item: item.id)
    ]

    return TestResponse(
        id=test.id,
        student_id=test.student_id,
        subject_id=test.subject_id,
        difficulty=test.difficulty,
        language=test.language,
        mode=test.mode,
        time_limit_seconds=(test.session.time_limit_seconds if test.session else None),
        warning_limit=(test.session.warning_limit if test.session else None),
        exam_kind=(test.session.exam_kind if test.session else None),
        exam_config_json=(test.session.exam_config_json if test.session else None),
        created_at=test.created_at,
        questions=questions,
    )


def _build_question_tts_narration(*, question: Question, language: PreferredLanguage) -> str:
    base = str(question.tts_text or question.prompt or "").strip()
    base = _strip_prompt_variant_suffix(base)
    return base


def _strip_prompt_variant_suffix(text: str) -> str:
    return re.sub(r"\s*\((вариант|нұсқа)\s*\d+\)\s*$", "", text, flags=re.IGNORECASE).strip()


def _extract_option_label(text: str, option_id: int) -> str:
    match = re.match(r"^\s*([A-Z])\s*[\).:-]", text, flags=re.IGNORECASE)
    if match and match.group(1):
        return match.group(1).upper()
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    if 0 <= option_id < len(letters):
        return letters[option_id]
    return "?"


def _strip_option_prefix(text: str) -> str:
    return re.sub(r"^\s*[A-ZА-Я]\s*[\).:-]\s*", "", text, flags=re.IGNORECASE).strip()


def _normalize_warning_events(events: list[TestWarningSignal]) -> list[dict]:
    normalized: list[dict] = []
    for item in events:
        event_type = str(item.type).strip().lower().replace(" ", "_")
        if not event_type:
            continue
        normalized.append(
            {
                "type": event_type,
                "at_seconds": int(max(0, item.at_seconds)),
                "question_id": item.question_id,
                "details": dict(item.details or {}),
            }
        )
    return normalized


def _merge_warning_events(existing: list[dict], incoming: list[dict], limit: int = 200) -> list[dict]:
    merged: list[dict] = []
    seen: set[tuple[str, int, int | None]] = set()

    for source in [existing, incoming]:
        for item in source:
            event_type = str(item.get("type", "")).strip().lower()
            if not event_type:
                continue
            try:
                at_seconds = int(max(0, int(item.get("at_seconds", 0))))
            except (TypeError, ValueError):
                at_seconds = 0
            question_raw = item.get("question_id")
            try:
                question_id = int(question_raw) if question_raw is not None else None
            except (TypeError, ValueError):
                question_id = None
            signature = (event_type, at_seconds, question_id)
            if signature in seen:
                continue
            seen.add(signature)
            merged.append(
                {
                    "type": event_type,
                    "at_seconds": at_seconds,
                    "question_id": question_id,
                    "details": dict(item.get("details", {}) or {}),
                }
            )
            if len(merged) >= limit:
                return merged
    return merged


def _normalize_warning_events_json(events: list[dict] | None) -> list[TestWarningSignal]:
    normalized: list[TestWarningSignal] = []
    for item in events or []:
        try:
            normalized.append(TestWarningSignal.model_validate(item))
        except Exception:
            continue
    return normalized


def _build_result_response(result: Result, session: TestSession | None) -> ResultResponse:
    return ResultResponse(
        total_score=result.total_score,
        max_score=result.max_score,
        percent=result.percent,
        elapsed_seconds=int(session.elapsed_seconds if session else 0),
        time_limit_seconds=(session.time_limit_seconds if session else None),
        warning_count=int(session.warning_count if session else 0),
    )


def _build_feedback_from_persisted_answers(test: Test) -> tuple[list[QuestionFeedback], list[str]]:
    feedback_items: list[QuestionFeedback] = []
    weak_topic_counter: Counter[str] = Counter()

    for question in sorted(test.questions, key=lambda item: item.id):
        latest_answer = max(question.answers, key=lambda item: item.id) if question.answers else None
        student_answer = dict(latest_answer.student_answer_json) if latest_answer else {}
        score = float(latest_answer.score) if latest_answer else 0.0
        is_correct = bool(latest_answer.is_correct) if latest_answer else False
        topic = str(question.explanation_json.get("topic", "General"))
        explanation_text = str(question.explanation_json.get("correct_explanation", ""))

        if not is_correct:
            weak_topic_counter[topic] += 1

        feedback_items.append(
            QuestionFeedback(
                question_id=question.id,
                prompt=question.prompt,
                topic=topic,
                student_answer=student_answer,
                expected_hint=_build_expected_hint(question),
                is_correct=is_correct,
                score=round(score, 2),
                explanation=explanation_text,
            )
        )

    weak_topics = [topic for topic, _ in weak_topic_counter.most_common(3)]
    if weak_topics:
        defaults = ["Повторение теории", "Понимание терминов", "Применение на практике"]
        for default_topic in defaults:
            if len(weak_topics) >= 3:
                break
            if default_topic not in weak_topics:
                weak_topics.append(default_topic)
    return feedback_items, weak_topics


def _build_expected_hint(question: Question) -> dict[str, Any]:
    if question.type in {QuestionType.single_choice, QuestionType.multi_choice}:
        return {"correct_option_ids": question.correct_answer_json.get("correct_option_ids", [])}
    if question.type == QuestionType.matching:
        return {"matches": question.correct_answer_json.get("matches", {})}
    return {
        "keywords": question.correct_answer_json.get("keywords", []),
        "sample_answer": question.correct_answer_json.get("sample_answer", ""),
    }
