from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from io import BytesIO
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.core.deps import CurrentUser, DBSession, require_role
from app.models import (
    Answer,
    DifficultyLevel,
    GroupMembership,
    PreferredLanguage,
    Question,
    QuestionType,
    Recommendation,
    Result,
    Subject,
    Test,
    TeacherAuthoredTest,
    TeacherAuthoredTestGroup,
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
    QuestionResponse,
    RecommendationResponse,
    ResultResponse,
    TestWarningSignal,
    SubmitTestRequest,
    SubmitTestResponse,
    TestResponse,
    TestResultDetailsResponse,
)
from app.services.cache import cache
from app.services.ai import RecommendationPayload, ai_service
from app.services.evaluation import evaluate_answers
from app.services.tts import TTSProviderUnavailableError, TTSServiceError, tts_service

router = APIRouter(prefix="/tests", tags=["tests"])


def _invalidate_student_dashboard_cache(student_id: int) -> None:
    cache.delete_many(
        f"student:{student_id}:history:v1",
        f"student:{student_id}:progress:v1",
        f"student:{student_id}:dashboard:v1",
    )


@router.post("/generate", response_model=TestResponse)
def generate_test(
    payload: GenerateTestRequest,
    db: DBSession,
    current_user: User = Depends(require_role(UserRole.student)),
) -> TestResponse:
    subject = db.get(Subject, payload.subject_id)
    if not subject:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Предмет не найден")

    focus_topics = _collect_student_focus_topics(
        db=db,
        student_id=current_user.id,
        subject_id=payload.subject_id,
    )
    used_library_question_ids = _collect_used_library_question_ids(
        db=db,
        student_id=current_user.id,
        subject_id=payload.subject_id,
        difficulty=payload.difficulty,
        language=payload.language,
        mode=payload.mode,
    )

    generated = ai_service.generate_test(
        subject=subject,
        difficulty=payload.difficulty,
        language=payload.language,
        mode=payload.mode,
        num_questions=payload.num_questions,
        user_id=current_user.id,
        focus_topics=focus_topics,
        used_library_question_ids=used_library_question_ids,
    )

    test = Test(
        student_id=current_user.id,
        subject_id=payload.subject_id,
        difficulty=payload.difficulty,
        language=payload.language,
        mode=payload.mode,
    )
    db.add(test)
    db.flush()
    db.add(
        TestSession(
            test_id=test.id,
            time_limit_seconds=(payload.time_limit_minutes * 60) if payload.time_limit_minutes else None,
        )
    )

    for generated_question in generated.questions:
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


@router.post("/generate-from-custom/{custom_test_id}", response_model=TestResponse)
def generate_test_from_custom_template(
    custom_test_id: int,
    db: DBSession,
    current_user: User = Depends(require_role(UserRole.student)),
) -> TestResponse:
    membership = db.scalar(
        select(GroupMembership).where(GroupMembership.student_id == current_user.id)
    )
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Вы не состоите в группе. Доступ к групповым тестам закрыт.",
        )

    custom_test = db.scalar(
        select(TeacherAuthoredTest)
        .options(joinedload(TeacherAuthoredTest.questions))
        .join(TeacherAuthoredTestGroup, TeacherAuthoredTestGroup.test_id == TeacherAuthoredTest.id)
        .where(
            TeacherAuthoredTest.id == custom_test_id,
            TeacherAuthoredTestGroup.group_id == membership.group_id,
        )
    )
    if not custom_test:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Групповой тест не найден")
    if not custom_test.questions:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="В выбранном тесте нет вопросов")

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
            time_limit_seconds=max(60, int(custom_test.time_limit_seconds)),
            warning_limit=max(0, int(custom_test.warning_limit)),
            exam_kind="group_custom",
            exam_config_json={
                "title": custom_test.title,
                "custom_test_id": custom_test.id,
                "group_id": membership.group_id,
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
                options_json=(source.options_json if normalized_type == QuestionType.single_choice else None),
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

    used_library_ids: set[str] = set()
    used_library_template_keys: set[str] = set()
    used_prompt_keys: set[str] = set()
    generated_questions: list[Any] = []
    global_index = 0

    for section_index, section in enumerate(sections, start=1):
        section_questions = _collect_exam_section_questions(
            subject=section["subject"],
            language=payload.language,
            mode=section["mode"],
            count=section["count"],
            base_seed=f"ent::{current_user.id}::{section['subject'].id}::{section['code']}",
            difficulty_order=section["difficulty_order"],
            used_library_ids=used_library_ids,
            used_library_template_keys=used_library_template_keys,
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

    used_library_ids: set[str] = set()
    used_library_template_keys: set[str] = set()
    used_prompt_keys: set[str] = set()
    generated_questions: list[Any] = []
    global_index = 0

    for section_index, section in enumerate(sections, start=1):
        section_questions = _collect_exam_section_questions(
            subject=english_subject,
            language=payload.language,
            mode=section["mode"],
            count=section["count"],
            base_seed=f"ielts::{current_user.id}::{section['code']}",
            difficulty_order=section["difficulty_order"],
            used_library_ids=used_library_ids,
            used_library_template_keys=used_library_template_keys,
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
    db.add(TestSession(test_id=test.id, time_limit_seconds=None))

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
            options_json=source_question.options_json if normalized_type != QuestionType.short_text else None,
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
    _assert_access(test, current_user)
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
    _assert_access(test, current_user)

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

    if test.result:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Тест уже отправлен")

    answers_by_question_id = {item.question_id: item.student_answer_json for item in payload.answers}
    evaluation = evaluate_answers(test.questions, answers_by_question_id)

    now = datetime.now(timezone.utc)
    telemetry = payload.telemetry
    if telemetry and telemetry.elapsed_seconds is not None:
        elapsed_seconds = int(max(0, telemetry.elapsed_seconds))
    else:
        elapsed_seconds = int(max(0, (now - test.created_at).total_seconds()))

    session = test.session or TestSession(test_id=test.id, started_at=test.created_at)
    if not test.session:
        db.add(session)

    normalized_warnings = _normalize_warning_events(list(telemetry.warnings if telemetry else []))
    if session.time_limit_seconds is not None and elapsed_seconds > session.time_limit_seconds:
        normalized_warnings.append(
            {
                "type": "time_limit_exceeded",
                "at_seconds": elapsed_seconds,
                "question_id": None,
                "details": {
                    "limit_seconds": int(session.time_limit_seconds),
                    "elapsed_seconds": elapsed_seconds,
                },
            }
        )
    merged_warning_events = _merge_warning_events(session.warning_events_json or [], normalized_warnings)
    session.warning_events_json = merged_warning_events
    session.warning_count = len(merged_warning_events)
    session.elapsed_seconds = max(int(session.elapsed_seconds or 0), elapsed_seconds)
    session.submitted_at = now

    feedback_map = {item.question_id: item for item in evaluation.feedback}
    for question in test.questions:
        student_answer = answers_by_question_id.get(question.id, {})
        feedback = feedback_map[question.id]
        db.add(
            Answer(
                question_id=question.id,
                student_answer_json=student_answer,
                is_correct=feedback.is_correct,
                score=feedback.score,
            )
        )

    result_total_score = float(evaluation.total_score)
    result_max_score = float(evaluation.max_score)
    if session.exam_kind == "ent":
        result_max_score = 140.0
        if evaluation.max_score > 0:
            result_total_score = round((evaluation.total_score / evaluation.max_score) * result_max_score, 2)
        else:
            result_total_score = 0.0

    percent = round((result_total_score / result_max_score) * 100, 2) if result_max_score else 0.0
    result = Result(
        test_id=test.id,
        total_score=result_total_score,
        max_score=result_max_score,
        percent=percent,
    )
    db.add(result)

    recommendation_payload, recommendation_weak_topics = _build_personalized_recommendation(
        test=test,
        percent=percent,
        warning_count=session.warning_count,
        weak_topics=evaluation.weak_topics,
    )
    recommendation = Recommendation(
        test_id=test.id,
        weak_topics_json=recommendation_weak_topics,
        advice_text=recommendation_payload.advice_text,
        generated_tasks_json=recommendation_payload.generated_tasks,
    )
    db.add(recommendation)

    db.commit()
    _invalidate_student_dashboard_cache(current_user.id)

    return SubmitTestResponse(
        test_id=test.id,
        result=_build_result_response(result=result, session=session),
        integrity_warnings=[TestWarningSignal.model_validate(item) for item in merged_warning_events],
        feedback=evaluation.feedback,
        recommendation=RecommendationResponse(
            weak_topics=recommendation_weak_topics,
            advice_text=recommendation_payload.advice_text,
            generated_tasks=recommendation_payload.generated_tasks,
        ),
    )


@router.get("/{test_id}/result", response_model=TestResultDetailsResponse)
def get_test_result(test_id: int, db: DBSession, current_user: CurrentUser) -> TestResultDetailsResponse:
    test = _load_test(db, test_id)
    _assert_access(test, current_user)

    if not test.result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Результат не найден")

    answers_map = {}
    for question in test.questions:
        if question.answers:
            answers_map[question.id] = question.answers[-1].student_answer_json

    evaluation = evaluate_answers(test.questions, answers_map)
    recommendation = test.recommendation
    session = test.session
    warning_events = _normalize_warning_events_json(session.warning_events_json if session else [])
    return TestResultDetailsResponse(
        test_id=test.id,
        submitted_at=test.result.created_at,
        result=_build_result_response(result=test.result, session=session),
        integrity_warnings=warning_events,
        feedback=evaluation.feedback,
        recommendation=RecommendationResponse(
            weak_topics=list(recommendation.weak_topics_json if recommendation else evaluation.weak_topics),
            advice_text=(recommendation.advice_text if recommendation else ""),
            generated_tasks=list(recommendation.generated_tasks_json if recommendation else []),
        ),
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
    generated, weak_topics = _build_personalized_recommendation(
        test=test,
        percent=percent,
        warning_count=warning_count,
        weak_topics=current_weak_topics,
    )

    test.recommendation.weak_topics_json = weak_topics
    test.recommendation.advice_text = generated.advice_text
    test.recommendation.generated_tasks_json = generated.generated_tasks
    db.commit()
    _invalidate_student_dashboard_cache(current_user.id)

    return RecommendationResponse(
        weak_topics=weak_topics,
        advice_text=generated.advice_text,
        generated_tasks=generated.generated_tasks,
    )


def _build_personalized_recommendation(
    *,
    test: Test,
    percent: float,
    warning_count: int,
    weak_topics: list[str],
) -> tuple[RecommendationPayload, list[str]]:
    clean_topics = [str(topic).strip() for topic in weak_topics if str(topic).strip()]
    exam_kind = str(test.session.exam_kind or "").strip().lower() if test.session else ""

    if exam_kind in {"ent", "ielts"}:
        return _build_exam_recommendation(
            exam_kind=exam_kind,
            language=test.language,
            percent=percent,
            warning_count=warning_count,
            weak_topics=clean_topics,
        )

    subject_name = test.subject.name_ru if test.language == PreferredLanguage.ru else test.subject.name_kz

    if percent >= 99.9 and warning_count == 0:
        if test.language == PreferredLanguage.kz:
            advice = (
                "Керемет нәтиже! Тестті өте сенімді әрі адал орындадыңыз. "
                "Келесі қадам ретінде деңгейді көтеріп немесе сұрақ санын көбейтіп көріңіз."
            )
            tasks = [
                {"topic": "Күрделілік", "task": f"«{subject_name}» пәнінен келесі тестті hard деңгейінде өтіңіз.", "difficulty": "hard"},
                {"topic": "Көлем", "task": "Келесі тестте 20-25 сұрақ таңдап, нәтиженің тұрақтылығын тексеріңіз.", "difficulty": "medium"},
                {"topic": "Жылдамдық", "task": "Жауап сапасын сақтай отырып, әр сұраққа кететін уақытты азайтыңыз.", "difficulty": "medium"},
                {"topic": "Тереңдету", "task": "Қиынырақ тақырыптар бойынша қысқа ашық сұрақтарға жауап беріңіз.", "difficulty": "hard"},
                {"topic": "Тұрақтылық", "task": "Жоғары нәтижені қатарынан 2-3 тестте қайталап көріңіз.", "difficulty": "adaptive"},
            ]
        else:
            advice = (
                "Отличный результат! Вы проходите тест уверенно и честно. "
                "Попробуйте повысить сложность или увеличить количество вопросов."
            )
            tasks = [
                {"topic": "Усложнение", "task": f"Пройдите следующий тест по предмету «{subject_name}» на сложном уровне.", "difficulty": "hard"},
                {"topic": "Объём", "task": "Выберите 20-25 вопросов в следующей попытке и проверьте стабильность результата.", "difficulty": "medium"},
                {"topic": "Скорость", "task": "Сократите среднее время на один вопрос без потери точности.", "difficulty": "medium"},
                {"topic": "Глубина", "task": "Добавьте открытые вопросы и объясняйте ход решения полным ответом.", "difficulty": "hard"},
                {"topic": "Стабильность", "task": "Повторите такой же результат минимум в 2-3 тестах подряд.", "difficulty": "adaptive"},
            ]
        return RecommendationPayload(advice_text=advice, generated_tasks=tasks), []

    if percent >= 90 and warning_count > 0:
        if test.language == PreferredLanguage.kz:
            advice = (
                f"Нәтиже жоғары ({round(percent, 1)}%), бірақ тестте {warning_count} ескерту тіркелді. "
                "Оқу тиімді болуы үшін келесі тестті адал форматта, сыртқы көмексіз өтіп көріңіз."
            )
            tasks = [
                {"topic": "Адал режим", "task": "Келесі тест кезінде басқа қойындыларға ауыспай орындаңыз.", "difficulty": "adaptive"},
                {"topic": "Өзіндік жауап", "task": "Мәтіндік сұрақтарға дайын мәтін қоймай, өз сөзіңізбен жауап беріңіз.", "difficulty": "adaptive"},
                {"topic": "Бақылау", "task": "Тест аяқталған соң 2 сұрақ бойынша шешім логикасын қысқаша жазып шығыңыз.", "difficulty": "medium"},
                {"topic": "Қайталау", "task": "Сіз қате жауап берген тақырыптарды жеке-жеке қайталаңыз.", "difficulty": "medium"},
                {"topic": "Тұрақтылық", "task": "Ескертусіз жоғары нәтижені 2 рет қатарынан көрсетуге тырысыңыз.", "difficulty": "adaptive"},
            ]
        else:
            advice = (
                f"Результат высокий ({round(percent, 1)}%), но зафиксированы предупреждения ({warning_count}). "
                "Для эффективного обучения попробуйте пройти следующий тест честно, без переключений вкладок и вставки готовых ответов."
            )
            tasks = [
                {"topic": "Честный режим", "task": "Пройдите следующий тест без перехода на другие вкладки.", "difficulty": "adaptive"},
                {"topic": "Самостоятельный ответ", "task": "На открытые вопросы отвечайте своими словами, без вставки текста.", "difficulty": "adaptive"},
                {"topic": "Контроль понимания", "task": "После теста письменно объясните ход решения двух вопросов.", "difficulty": "medium"},
                {"topic": "Повторение ошибок", "task": "Отработайте темы вопросов, где были ошибки по баллам.", "difficulty": "medium"},
                {"topic": "Стабильность", "task": "Покажите высокий результат без предупреждений в двух попытках подряд.", "difficulty": "adaptive"},
            ]
        return RecommendationPayload(advice_text=advice, generated_tasks=tasks), clean_topics

    generated = ai_service.generate_recommendation(
        subject=test.subject,
        language=test.language,
        weak_topics=clean_topics,
    )
    return generated, clean_topics


def _default_exam_topics(exam_kind: str, language: PreferredLanguage) -> list[str]:
    if exam_kind == "ent":
        if language == PreferredLanguage.kz:
            return ["Қазақстан тарихы", "Математикалық сауаттылық", "Оқу сауаттылығы"]
        return ["История Казахстана", "Математическая грамотность", "Грамотность чтения"]

    if language == PreferredLanguage.kz:
        return ["Listening", "Reading", "Writing", "Speaking"]
    return ["Listening", "Reading", "Writing", "Speaking"]


def _build_exam_recommendation(
    *,
    exam_kind: str,
    language: PreferredLanguage,
    percent: float,
    warning_count: int,
    weak_topics: list[str],
) -> tuple[RecommendationPayload, list[str]]:
    exam_label = "ЕНТ" if exam_kind == "ent" else "IELTS"
    base_topics = _default_exam_topics(exam_kind, language)
    normalized_topics: list[str] = []
    seen_topics: set[str] = set()
    for topic in [*weak_topics, *base_topics]:
        value = str(topic).strip()
        key = value.lower()
        if not value or key in seen_topics:
            continue
        seen_topics.add(key)
        normalized_topics.append(value)
        if len(normalized_topics) >= 5:
            break
    if not normalized_topics:
        normalized_topics = base_topics[:3]

    focus_topics = normalized_topics[:3]

    if language == PreferredLanguage.kz:
        if percent >= 99.9 and warning_count == 0:
            advice = (
                f"Керемет! Сіз {exam_label} форматындағы сынақ тестін өте жоғары және адал нәтижемен аяқтадыңыз. "
                "Келесі қадам ретінде уақытты азайтып, тұрақтылықты сақтап көріңіз."
            )
        elif warning_count > 0 and percent >= 90:
            advice = (
                f"Нәтиже жоғары ({round(percent, 1)}%), бірақ {exam_label} тестінде {warning_count} ескерту тіркелді. "
                "Нәтижеңізді шынайы бағалау үшін келесі талпынысты сыртқы көмексіз, адал форматта өтіңіз."
            )
        elif percent >= 85:
            advice = (
                f"{exam_label} бойынша нәтиже жақсы ({round(percent, 1)}%). "
                f"Енді мына тақырыптарға назар аударыңыз: {', '.join(focus_topics)}."
            )
        else:
            advice = (
                f"{exam_label} сынағында нәтижені көтеру үшін әлсіз тақырыптарды жүйелі қайталаңыз: "
                f"{', '.join(focus_topics)}."
            )

        tasks = []
        for topic in focus_topics:
            if exam_kind == "ent":
                task_text = f"«{topic}» бойынша 10 тапсырманы уақытпен орындап, әр қатені қысқаша талдаңыз."
            else:
                task_text = f"«{topic}» бөліміне 20-25 минуттық шағын жаттығу жасап, кейін өз қателеріңізді тексеріңіз."
            tasks.append({"topic": topic, "task": task_text, "difficulty": "adaptive"})

        tasks.append(
            {
                "topic": "Тайм-менеджмент",
                "task": "Келесі тестте әр бөлімге уақытты алдын ала бөліп, соңғы 10 минутты тексеруге қалдырыңыз.",
                "difficulty": "medium",
            }
        )
        tasks.append(
            {
                "topic": "Адал формат",
                "task": "Келесі талпынысты ескертусіз өтуге тырысыңыз: басқа қойындыларға ауыспаңыз және дайын мәтін қоймаңыз.",
                "difficulty": "adaptive",
            }
        )
        return RecommendationPayload(advice_text=advice, generated_tasks=tasks[:5]), focus_topics

    if percent >= 99.9 and warning_count == 0:
        advice = (
            f"Отличный результат! Вы прошли пробный {exam_label} на очень высоком уровне и без предупреждений. "
            "Попробуйте следующий прогон с тем же качеством и более строгим таймингом."
        )
    elif warning_count > 0 and percent >= 90:
        advice = (
            f"Результат высокий ({round(percent, 1)}%), но в режиме {exam_label} зафиксированы предупреждения ({warning_count}). "
            "Чтобы прогресс был честным и устойчивым, пройдите следующую попытку без переключений вкладок и вставки готовых ответов."
        )
    elif percent >= 85:
        advice = (
            f"Хороший уровень по формату {exam_label} ({round(percent, 1)}%). "
            f"Для уверенного роста доработайте темы: {', '.join(focus_topics)}."
        )
    else:
        advice = (
            f"Чтобы улучшить результат по {exam_label}, сфокусируйтесь на слабых зонах: "
            f"{', '.join(focus_topics)}."
        )

    tasks = []
    for topic in focus_topics:
        if exam_kind == "ent":
            task_text = f"По теме «{topic}» решите 10 заданий формата ЕНТ в ограниченное время и разберите ошибки."
        else:
            task_text = f"По части «{topic}» сделайте 20-25 минут целевой практики IELTS и проверьте точность ответов."
        tasks.append({"topic": topic, "task": task_text, "difficulty": "adaptive"})

    tasks.append(
        {
            "topic": "Тайм-менеджмент",
            "task": "В следующем тесте заранее распределите время по блокам и оставьте 10 минут на финальную проверку.",
            "difficulty": "medium",
        }
    )
    tasks.append(
        {
            "topic": "Честный режим",
            "task": "Постарайтесь пройти следующую попытку без предупреждений: без переключений вкладок и вставки готового текста.",
            "difficulty": "adaptive",
        }
    )
    return RecommendationPayload(advice_text=advice, generated_tasks=tasks[:5]), focus_topics


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
    subject: Subject,
    language: PreferredLanguage,
    mode: TestMode,
    count: int,
    base_seed: str,
    difficulty_order: list[DifficultyLevel],
    used_library_ids: set[str],
    used_library_template_keys: set[str],
    used_prompt_keys: set[str],
) -> list[Any]:
    selected: list[Any] = []
    section_question_keys: set[str] = set()

    def try_add_question(candidate: Any) -> bool:
        question_key = _exam_question_uniqueness_key(candidate)
        if not question_key or question_key in used_prompt_keys or question_key in section_question_keys:
            return False

        selected.append(candidate)
        section_question_keys.add(question_key)

        explanation = dict(candidate.explanation_json or {})
        library_id = str(explanation.get("library_question_id", "")).strip()
        if library_id:
            used_library_ids.add(library_id)
        template_key = str(explanation.get("library_template_key", "")).strip().lower()
        if template_key:
            used_library_template_keys.add(template_key)
        return True

    for attempt in range(5):
        if len(selected) >= count:
            break

        remaining = count - len(selected)
        request_size = min(240, max(remaining * 3, remaining + 8))
        batch = ai_service.generate_library_only_questions(
            subject=subject,
            language=language,
            mode=mode,
            num_questions=request_size,
            seed=f"{base_seed}::library::{attempt}",
            difficulty_order=difficulty_order,
            used_library_question_ids=used_library_ids,
            used_library_content_keys=used_library_template_keys,
        )
        if not batch:
            break

        added_in_batch = 0
        for question in batch:
            if try_add_question(question):
                added_in_batch += 1
                if len(selected) >= count:
                    break

        if added_in_batch == 0 and attempt >= 1:
            break

    if len(selected) < count:
        for fallback_attempt in range(8):
            if len(selected) >= count:
                break
            remaining = count - len(selected)
            fallback_payload = ai_service._generate_non_library_test(  # noqa: SLF001
                subject=subject,
                difficulty=(difficulty_order[0] if difficulty_order else DifficultyLevel.medium),
                language=language,
                mode=mode,
                num_questions=max(remaining * 3, remaining + 6),
                seed=f"{base_seed}::mock-fallback::{fallback_attempt}",
                focus_topics=[],
            )
            added = 0
            for question in fallback_payload.questions:
                if try_add_question(question):
                    added += 1
                    if len(selected) >= count:
                        break
            if added == 0 and fallback_attempt >= 2:
                break

    if len(selected) < count:
        for filler_attempt in range(16):
            if len(selected) >= count:
                break
            remaining = count - len(selected)
            filler_batch = ai_service.generate_library_only_questions(
                subject=subject,
                language=language,
                mode=mode,
                num_questions=max(remaining * 2, remaining + 4),
                seed=f"{base_seed}::library-filler::{filler_attempt}",
                difficulty_order=difficulty_order,
                used_library_question_ids=used_library_ids,
                used_library_content_keys=used_library_template_keys,
            )
            if not filler_batch:
                break

            added = 0
            for question in filler_batch:
                if try_add_question(question):
                    added += 1
                    if len(selected) >= count:
                        break
            if added == 0 and filler_attempt >= 3:
                break

    if len(selected) < count:
        remaining = count - len(selected)
        final_payload = ai_service._generate_non_library_test(  # noqa: SLF001
            subject=subject,
            difficulty=(difficulty_order[0] if difficulty_order else DifficultyLevel.medium),
            language=language,
            mode=mode,
            num_questions=max(remaining * 4, remaining + 10),
            seed=f"{base_seed}::deep-topup",
            focus_topics=[],
        )
        for question in final_payload.questions:
            if try_add_question(question):
                if len(selected) >= count:
                    break

    if len(selected) < count:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Недостаточно уникальных вопросов для секции «{subject.name_ru}».",
        )

    used_prompt_keys.update(section_question_keys)
    return selected[:count]


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


def _collect_student_focus_topics(db: DBSession, student_id: int, subject_id: int, limit: int = 5) -> list[str]:
    topic_counter: Counter[str] = Counter()

    weak_topics_rows = db.scalars(
        select(Recommendation.weak_topics_json)
        .join(Test, Recommendation.test_id == Test.id)
        .where(Test.student_id == student_id, Test.subject_id == subject_id)
    ).all()
    for topics in weak_topics_rows:
        for topic in topics:
            value = str(topic).strip()
            if value:
                topic_counter[value] += 1

    wrong_topic_rows = db.scalars(
        select(Question.explanation_json)
        .join(Test, Question.test_id == Test.id)
        .join(Answer, Answer.question_id == Question.id)
        .where(
            Test.student_id == student_id,
            Test.subject_id == subject_id,
            Answer.is_correct.is_(False),
        )
    ).all()
    for explanation in wrong_topic_rows:
        topic = str((explanation or {}).get("topic", "")).strip()
        if topic:
            topic_counter[topic] += 1

    return [topic for topic, _ in topic_counter.most_common(limit)]


def _collect_used_library_question_ids(
    *,
    db: DBSession,
    student_id: int,
    subject_id: int,
    difficulty: DifficultyLevel,
    language: PreferredLanguage,
    mode: TestMode,
) -> set[str]:
    explanation_rows = db.scalars(
        select(Question.explanation_json)
        .join(Test, Question.test_id == Test.id)
        .join(Result, Result.test_id == Test.id)
        .where(
            Test.student_id == student_id,
            Test.subject_id == subject_id,
            Test.difficulty == difficulty,
            Test.language == language,
            Test.mode == mode,
        )
    ).all()

    used_ids: set[str] = set()
    for explanation in explanation_rows:
        value = str((explanation or {}).get("library_question_id", "")).strip()
        if value:
            used_ids.add(value)
    return used_ids


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


def _assert_access(test: Test, user: User) -> None:
    if user.role == UserRole.teacher:
        return
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
