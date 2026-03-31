from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import joinedload, selectinload

from app.core.deps import DBSession, CurrentUser, get_active_memberships, require_institution_role
from app.models import (
    InstitutionMembership,
    InstitutionMembershipRole,
    TeacherAuthoredTest,
    TestModerationStatus,
    TestReviewRequest,
)
from app.schemas.institutional import (
    InstitutionListItemResponse,
    ReviewDecisionRequest,
    ReviewDetailsQuestionResponse,
    ReviewDetailsResponse,
    SubmitReviewRequestResponse,
    TestReviewQueueItemResponse,
)
from app.services.audit_logs import audit_log_service
from app.services.custom_tests import custom_test_duration_minutes
from app.services.notifications import notification_service

router = APIRouter(prefix="/methodist", tags=["methodist"])


def _methodist_membership_dependency():
    return Depends(require_institution_role(InstitutionMembershipRole.methodist))


def _assert_methodist_scope(*, membership: InstitutionMembership, institution_id: int) -> None:
    if int(membership.institution_id) != int(institution_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет доступа к выбранному учебному учреждению.",
        )


@router.get("/institutions", response_model=list[InstitutionListItemResponse])
def my_methodist_institutions(
    db: DBSession,
    current_user: CurrentUser,
) -> list[InstitutionListItemResponse]:
    memberships = get_active_memberships(
        db=db,
        user_id=current_user.id,
        roles={InstitutionMembershipRole.methodist},
    )
    return [
        InstitutionListItemResponse(
            id=int(membership.institution.id),
            name=str(membership.institution.name),
            role=membership.role,
            status=membership.status,
            is_primary=bool(membership.is_primary),
        )
        for membership in memberships
        if membership.institution is not None
    ]


@router.get(
    "/institutions/{institution_id}/reviews",
    response_model=list[TestReviewQueueItemResponse],
)
def list_review_queue(
    institution_id: int,
    db: DBSession,
    methodist_membership: InstitutionMembership = _methodist_membership_dependency(),
) -> list[TestReviewQueueItemResponse]:
    _assert_methodist_scope(membership=methodist_membership, institution_id=institution_id)

    rows = db.scalars(
        select(TeacherAuthoredTest)
        .options(
            joinedload(TeacherAuthoredTest.teacher),
            selectinload(TeacherAuthoredTest.questions),
        )
        .where(
            TeacherAuthoredTest.institution_id == int(institution_id),
            TeacherAuthoredTest.moderation_status.in_(
                (
                    TestModerationStatus.submitted_for_review,
                    TestModerationStatus.in_review,
                    TestModerationStatus.needs_revision,
                )
            ),
        )
        .order_by(
            TeacherAuthoredTest.submitted_for_review_at.desc().nullslast(),
            TeacherAuthoredTest.updated_at.desc(),
            TeacherAuthoredTest.id.desc(),
        )
    ).all()

    payload: list[TestReviewQueueItemResponse] = []
    for row in rows:
        teacher_name = ""
        if row.teacher is not None:
            teacher_name = (row.teacher.full_name or row.teacher.username).strip()
        payload.append(
            TestReviewQueueItemResponse(
                test_id=int(row.id),
                title=row.title,
                teacher_user_id=int(row.teacher_id),
                teacher_name=teacher_name,
                moderation_status=row.moderation_status,
                submitted_for_review_at=row.submitted_for_review_at,
                created_at=row.created_at,
                updated_at=row.updated_at,
                questions_count=len(row.questions),
            )
        )
    return payload


@router.get(
    "/institutions/{institution_id}/reviews/{test_id}",
    response_model=ReviewDetailsResponse,
)
def get_review_details(
    institution_id: int,
    test_id: int,
    db: DBSession,
    methodist_membership: InstitutionMembership = _methodist_membership_dependency(),
) -> ReviewDetailsResponse:
    _assert_methodist_scope(membership=methodist_membership, institution_id=institution_id)

    test = db.scalar(
        select(TeacherAuthoredTest)
        .options(
            joinedload(TeacherAuthoredTest.teacher),
            selectinload(TeacherAuthoredTest.questions),
        )
        .where(
            TeacherAuthoredTest.id == int(test_id),
            TeacherAuthoredTest.institution_id == int(institution_id),
        )
    )
    if test is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Тест не найден.")

    teacher_name = ""
    if test.teacher is not None:
        teacher_name = (test.teacher.full_name or test.teacher.username).strip()

    questions = [
        ReviewDetailsQuestionResponse(
            id=int(question.id),
            order_index=int(question.order_index),
            prompt=question.prompt,
            question_type=question.question_type,
        )
        for question in sorted(test.questions, key=lambda item: (int(item.order_index), int(item.id)))
    ]

    return ReviewDetailsResponse(
        test_id=int(test.id),
        institution_id=int(test.institution_id or institution_id),
        title=test.title,
        teacher_user_id=int(test.teacher_id),
        teacher_name=teacher_name,
        warning_limit=int(test.warning_limit or 0),
        duration_minutes=custom_test_duration_minutes(int(test.time_limit_seconds or 0)),
        due_date=test.due_date,
        moderation_status=test.moderation_status,
        moderation_comment=test.moderation_comment,
        current_draft_version=int(test.current_draft_version or 1),
        approved_version=test.approved_version,
        submitted_for_review_at=test.submitted_for_review_at,
        reviewed_at=test.reviewed_at,
        questions=questions,
    )


@router.post(
    "/institutions/{institution_id}/reviews/{test_id}/decision",
    response_model=SubmitReviewRequestResponse,
)
def decide_review(
    institution_id: int,
    test_id: int,
    payload: ReviewDecisionRequest,
    db: DBSession,
    methodist_membership: InstitutionMembership = _methodist_membership_dependency(),
) -> SubmitReviewRequestResponse:
    _assert_methodist_scope(membership=methodist_membership, institution_id=institution_id)

    test = db.scalar(
        select(TeacherAuthoredTest)
        .where(
            TeacherAuthoredTest.id == int(test_id),
            TeacherAuthoredTest.institution_id == int(institution_id),
        )
    )
    if test is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Тест не найден.")
    if test.moderation_status not in {
        TestModerationStatus.submitted_for_review,
        TestModerationStatus.in_review,
        TestModerationStatus.needs_revision,
    }:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Этот тест сейчас нельзя модерировать в выбранном статусе.",
        )

    status_map = {
        "approved": TestModerationStatus.approved,
        "rejected": TestModerationStatus.rejected,
        "needs_revision": TestModerationStatus.needs_revision,
    }
    next_status = status_map[payload.status]
    now = datetime.now(timezone.utc)

    review_request = db.scalar(
        select(TestReviewRequest)
        .where(
            TestReviewRequest.test_id == test.id,
            TestReviewRequest.institution_id == int(institution_id),
            TestReviewRequest.status.in_(
                (
                    TestModerationStatus.submitted_for_review,
                    TestModerationStatus.in_review,
                )
            ),
        )
        .order_by(TestReviewRequest.created_at.desc(), TestReviewRequest.id.desc())
    )
    if review_request is None:
        review_request = TestReviewRequest(
            institution_id=int(institution_id),
            test_id=test.id,
            submitted_version=int(test.current_draft_version or 1),
            status=TestModerationStatus.in_review,
            requested_by_membership_id=int(methodist_membership.id),
            reviewer_membership_id=None,
            comment=None,
            created_at=now,
            reviewed_at=None,
        )
        db.add(review_request)
        db.flush()

    review_request.status = next_status
    review_request.reviewer_membership_id = int(methodist_membership.id)
    review_request.comment = (payload.comment or "").strip() or None
    review_request.reviewed_at = now

    test.moderation_status = next_status
    test.moderation_comment = review_request.comment
    test.reviewed_at = now
    test.reviewed_by_membership_id = int(methodist_membership.id)
    if next_status == TestModerationStatus.approved:
        test.approved_version = int(test.current_draft_version or 1)

    notification_service.create(
        db=db,
        user_id=int(test.teacher_id),
        institution_id=int(institution_id),
        notification_type="test_review_decision",
        title="Решение по модерации теста",
        message=f"По тесту «{test.title}» принято решение: {next_status.value}.",
        data={
            "test_id": int(test.id),
            "status": next_status.value,
            "comment": review_request.comment,
            "review_request_id": int(review_request.id),
        },
    )

    audit_log_service.record(
        db=db,
        institution_id=int(institution_id),
        actor_user_id=int(methodist_membership.user_id),
        action="test_review_decision",
        target_type="teacher_authored_test",
        target_id=test.id,
        metadata={
            "status": next_status.value,
            "comment": review_request.comment,
            "review_request_id": int(review_request.id),
            "version": int(test.current_draft_version or 1),
        },
    )

    db.commit()
    db.refresh(test)
    return SubmitReviewRequestResponse(
        test_id=int(test.id),
        status=test.moderation_status,
        current_draft_version=int(test.current_draft_version or 1),
        submitted_for_review_at=test.submitted_for_review_at or now,
    )
