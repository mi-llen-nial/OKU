from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.core.deps import CurrentUser, DBSession, require_role
from app.models import (
    Answer,
    DifficultyLevel,
    PreferredLanguage,
    Question,
    QuestionType,
    Recommendation,
    Result,
    Subject,
    Test,
    TestMode,
    TestSession,
    User,
    UserRole,
)
from app.schemas.tests import (
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
from app.services.ai import ai_service
from app.services.evaluation import evaluate_answers

router = APIRouter(prefix="/tests", tags=["tests"])


@router.post("/generate", response_model=TestResponse)
def generate_test(
    payload: GenerateTestRequest,
    db: DBSession,
    current_user: User = Depends(require_role(UserRole.student)),
) -> TestResponse:
    subject = db.get(Subject, payload.subject_id)
    if not subject:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found")

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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found")

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


@router.post("/{test_id}/submit", response_model=SubmitTestResponse)
def submit_test(
    test_id: int,
    payload: SubmitTestRequest,
    db: DBSession,
    current_user: User = Depends(require_role(UserRole.student)),
) -> SubmitTestResponse:
    test = _load_test(db, test_id)
    if test.student_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot submit another student's test")

    if test.result:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Test already submitted")

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

    percent = round((evaluation.total_score / evaluation.max_score) * 100, 2) if evaluation.max_score else 0.0
    result = Result(
        test_id=test.id,
        total_score=evaluation.total_score,
        max_score=evaluation.max_score,
        percent=percent,
    )
    db.add(result)

    recommendation_payload = ai_service.generate_recommendation(
        subject=test.subject,
        language=test.language,
        weak_topics=evaluation.weak_topics,
    )
    recommendation = Recommendation(
        test_id=test.id,
        weak_topics_json=evaluation.weak_topics,
        advice_text=recommendation_payload.advice_text,
        generated_tasks_json=recommendation_payload.generated_tasks,
    )
    db.add(recommendation)

    db.commit()

    return SubmitTestResponse(
        test_id=test.id,
        result=_build_result_response(result=result, session=session),
        integrity_warnings=[TestWarningSignal.model_validate(item) for item in merged_warning_events],
        feedback=evaluation.feedback,
        recommendation=RecommendationResponse(
            weak_topics=evaluation.weak_topics,
            advice_text=recommendation_payload.advice_text,
            generated_tasks=recommendation_payload.generated_tasks,
        ),
    )


@router.get("/{test_id}/result", response_model=TestResultDetailsResponse)
def get_test_result(test_id: int, db: DBSession, current_user: CurrentUser) -> TestResultDetailsResponse:
    test = _load_test(db, test_id)
    _assert_access(test, current_user)

    if not test.result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Result not found")

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
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot update another student's test")

    if not test.recommendation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found")

    weak_topics = list(test.recommendation.weak_topics_json)
    generated = ai_service.generate_recommendation(
        subject=test.subject,
        language=test.language,
        weak_topics=weak_topics,
    )

    test.recommendation.advice_text = generated.advice_text
    test.recommendation.generated_tasks_json = generated.generated_tasks
    db.commit()

    return RecommendationResponse(
        weak_topics=weak_topics,
        advice_text=generated.advice_text,
        generated_tasks=generated.generated_tasks,
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test not found")
    return test


def _assert_access(test: Test, user: User) -> None:
    if user.role == UserRole.teacher:
        return
    if test.student_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


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
        created_at=test.created_at,
        questions=questions,
    )


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
