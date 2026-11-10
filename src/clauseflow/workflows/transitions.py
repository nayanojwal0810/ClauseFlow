"""Database-backed workflow transition services for review runs and approval requests."""

from __future__ import annotations

import datetime
from typing import Optional
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from clauseflow.db.models import ApprovalRequest, AuditEvent, ReviewRun, User
from clauseflow.workflows.states import (
    APPROVAL_STATE_APPROVED,
    APPROVAL_STATE_CHANGES_REQUESTED,
    APPROVAL_STATE_PENDING_LEGAL,
    APPROVAL_STATE_REJECTED,
    REVIEW_STATE_FAILED,
    TERMINAL_APPROVAL_STATES,
    TERMINAL_REVIEW_STATES,
    validate_approval_request_transition,
    validate_review_run_transition,
)


def advance_review_run(
    session: Session,
    run_id: uuid.UUID,
    next_status: str,
    actor_user_id: Optional[uuid.UUID] = None,
    error_code: Optional[str] = None,
) -> ReviewRun:
    """Advance a review run to the next status within an active transaction.
    
    Locks the row with SELECT FOR UPDATE.
    Emits an audit_events record upon successful status change.
    Does NOT commit the transaction; caller controls session lifecycle.
    """
    stmt = (
        select(ReviewRun)
        .where(ReviewRun.review_run_id == run_id)
        .with_for_update()
    )
    run = session.execute(stmt).scalar_one_or_none()
    if not run:
        raise ValueError(f"ReviewRun not found for ID: {run_id}")

    old_status = run.status
    validate_review_run_transition(old_status, next_status, error_code=error_code)

    now = datetime.datetime.now(datetime.timezone.utc)
    run.status = next_status
    run.updated_at = now

    if next_status == REVIEW_STATE_FAILED:
        run.error_code = error_code

    if next_status in TERMINAL_REVIEW_STATES:
        run.finished_at = now

    # Emit audit event
    audit = AuditEvent(
        audit_event_id=uuid.uuid4(),
        actor_user_id=actor_user_id,
        action="advance_review_run",
        object_type="review_run",
        object_id=str(run_id),
        result="success",
        reason_code=f"{old_status}->{next_status}",
    )
    session.add(audit)

    return run


def advance_approval_request(
    session: Session,
    request_id: uuid.UUID,
    next_state: str,
    actor_user_id: Optional[uuid.UUID] = None,
    comment: Optional[str] = None,
) -> ApprovalRequest:
    """Advance an approval request to the next state within an active transaction.
    
    Locks the row with SELECT FOR UPDATE.
    Verifies reviewer qualifications for decisions from pending_legal.
    Emits an audit_events record upon successful state change.
    Does NOT commit the transaction; caller controls session lifecycle.
    """
    stmt = (
        select(ApprovalRequest)
        .where(ApprovalRequest.approval_request_id == request_id)
        .with_for_update()
    )
    req = session.execute(stmt).scalar_one_or_none()
    if not req:
        raise ValueError(f"ApprovalRequest not found for ID: {request_id}")

    old_state = req.state
    validate_approval_request_transition(old_state, next_state)

    # Transition to pending_legal forbids anonymous transition
    if next_state == APPROVAL_STATE_PENDING_LEGAL:
        if not actor_user_id:
            raise ValueError("Transition to pending_legal requires an authenticated actor_user_id.")

    # Reviewer decision from pending_legal
    if old_state == APPROVAL_STATE_PENDING_LEGAL and next_state in TERMINAL_APPROVAL_STATES:
        if not actor_user_id:
            raise ValueError("Legal reviewer decision requires an actor_user_id.")

        actor = session.get(User, actor_user_id)
        if not actor:
            raise ValueError(f"Actor user '{actor_user_id}' not found.")
        if not actor.active:
            raise ValueError(f"Actor user '{actor.username}' is not active.")
        if actor.role != "legal_reviewer":
            raise ValueError(
                f"User '{actor.username}' has role '{actor.role}'; only 'legal_reviewer' may decide legal approval requests."
            )

        if req.assigned_reviewer and req.assigned_reviewer != actor_user_id:
            raise ValueError(
                f"Approval request is assigned to reviewer '{req.assigned_reviewer}', but action was attempted by '{actor_user_id}'."
            )

        now = datetime.datetime.now(datetime.timezone.utc)
        req.decided_at = now
        req.review_comment = comment

    now = datetime.datetime.now(datetime.timezone.utc)
    req.state = next_state
    req.updated_at = now

    audit = AuditEvent(
        audit_event_id=uuid.uuid4(),
        actor_user_id=actor_user_id,
        action="advance_approval_request",
        object_type="approval_request",
        object_id=str(request_id),
        result="success",
        reason_code=f"{old_state}->{next_state}",
    )
    session.add(audit)

    return req

