from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import joinedload

from app.core.deps import CurrentUser, DBSession, require_role
from app.models import Answer, Question, Recommendation, Result, Subject, Test, User, UserRole
from app.schemas.tests import (
    GenerateTestRequest,
    QuestionResponse,
    RecommendationResponse,
    ResultResponse,
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

    generated = ai_service.generate_test(
        subject=subject,
        difficulty=payload.difficulty,
        language=payload.language,
        mode=payload.mode,
        num_questions=payload.num_questions,
        user_id=current_user.id,
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
        result=ResultResponse(
            total_score=evaluation.total_score,
            max_score=evaluation.max_score,
            percent=percent,
        ),
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
    return TestResultDetailsResponse(
        test_id=test.id,
        submitted_at=test.result.created_at,
        result=ResultResponse(
            total_score=test.result.total_score,
            max_score=test.result.max_score,
            percent=test.result.percent,
        ),
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


def _load_test(db: DBSession, test_id: int) -> Test:
    test = (
        db.query(Test)
        .options(
            joinedload(Test.questions).joinedload(Question.answers),
            joinedload(Test.subject),
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
        created_at=test.created_at,
        questions=questions,
    )
