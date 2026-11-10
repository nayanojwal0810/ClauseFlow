"""Review and approval workflow state definitions and transition rules."""

from __future__ import annotations

from typing import Dict, Optional, Set

# Review Run States
REVIEW_STATE_CREATED = "created"
REVIEW_STATE_INGESTING = "ingesting"
REVIEW_STATE_RETRIEVING = "retrieving"
REVIEW_STATE_EXTRACTING = "extracting"
REVIEW_STATE_EVALUATING = "evaluating"
REVIEW_STATE_REPORT_READY = "report_ready"
REVIEW_STATE_FAILED = "failed"

REVIEW_STATES: Set[str] = {
    REVIEW_STATE_CREATED,
    REVIEW_STATE_INGESTING,
    REVIEW_STATE_RETRIEVING,
    REVIEW_STATE_EXTRACTING,
    REVIEW_STATE_EVALUATING,
    REVIEW_STATE_REPORT_READY,
    REVIEW_STATE_FAILED,
}

TERMINAL_REVIEW_STATES: Set[str] = {
    REVIEW_STATE_REPORT_READY,
    REVIEW_STATE_FAILED,
}

# Normal sequential advancement for review runs
ALLOWED_REVIEW_TRANSITIONS: Dict[str, Set[str]] = {
    REVIEW_STATE_CREATED: {REVIEW_STATE_INGESTING, REVIEW_STATE_FAILED},
    REVIEW_STATE_INGESTING: {REVIEW_STATE_RETRIEVING, REVIEW_STATE_FAILED},
    REVIEW_STATE_RETRIEVING: {REVIEW_STATE_EXTRACTING, REVIEW_STATE_FAILED},
    REVIEW_STATE_EXTRACTING: {REVIEW_STATE_EVALUATING, REVIEW_STATE_FAILED},
    REVIEW_STATE_EVALUATING: {REVIEW_STATE_REPORT_READY, REVIEW_STATE_FAILED},
    REVIEW_STATE_REPORT_READY: set(),
    REVIEW_STATE_FAILED: set(),
}

# Approval Request States
APPROVAL_STATE_DRAFT = "draft"
APPROVAL_STATE_PENDING_CONFIRMATION = "pending_confirmation"
APPROVAL_STATE_PENDING_LEGAL = "pending_legal"
APPROVAL_STATE_APPROVED = "approved"
APPROVAL_STATE_REJECTED = "rejected"
APPROVAL_STATE_CHANGES_REQUESTED = "changes_requested"

APPROVAL_STATES: Set[str] = {
    APPROVAL_STATE_DRAFT,
    APPROVAL_STATE_PENDING_CONFIRMATION,
    APPROVAL_STATE_PENDING_LEGAL,
    APPROVAL_STATE_APPROVED,
    APPROVAL_STATE_REJECTED,
    APPROVAL_STATE_CHANGES_REQUESTED,
}

TERMINAL_APPROVAL_STATES: Set[str] = {
    APPROVAL_STATE_APPROVED,
    APPROVAL_STATE_REJECTED,
    APPROVAL_STATE_CHANGES_REQUESTED,
}

ALLOWED_APPROVAL_TRANSITIONS: Dict[str, Set[str]] = {
    APPROVAL_STATE_DRAFT: {APPROVAL_STATE_PENDING_CONFIRMATION},
    APPROVAL_STATE_PENDING_CONFIRMATION: {APPROVAL_STATE_PENDING_LEGAL},
    APPROVAL_STATE_PENDING_LEGAL: {
        APPROVAL_STATE_APPROVED,
        APPROVAL_STATE_REJECTED,
        APPROVAL_STATE_CHANGES_REQUESTED,
    },
    APPROVAL_STATE_APPROVED: set(),
    APPROVAL_STATE_REJECTED: set(),
    APPROVAL_STATE_CHANGES_REQUESTED: set(),
}


def can_transition_review_run(
    current_status: str,
    next_status: str,
    error_code: Optional[str] = None,
) -> bool:
    """Check if a transition between review run statuses is permissible."""
    if current_status not in REVIEW_STATES or next_status not in REVIEW_STATES:
        return False
    if next_status not in ALLOWED_REVIEW_TRANSITIONS.get(current_status, set()):
        return False
    if next_status == REVIEW_STATE_FAILED and not (error_code and error_code.strip()):
        return False
    return True


def validate_review_run_transition(
    current_status: str,
    next_status: str,
    error_code: Optional[str] = None,
) -> None:
    """Validate review run transition; raise ValueError on disallowed transition."""
    if current_status not in REVIEW_STATES:
        raise ValueError(f"Unknown current review status: '{current_status}'")
    if next_status not in REVIEW_STATES:
        raise ValueError(f"Unknown target review status: '{next_status}'")
    if current_status in TERMINAL_REVIEW_STATES:
        raise ValueError(
            f"Cannot advance terminal review run status '{current_status}' to '{next_status}'. A fresh review run is required."
        )
    allowed = ALLOWED_REVIEW_TRANSITIONS.get(current_status, set())
    if next_status not in allowed:
        raise ValueError(
            f"Invalid review run transition from '{current_status}' to '{next_status}'. Allowed targets: {sorted(allowed)}"
        )
    if next_status == REVIEW_STATE_FAILED and not (error_code and error_code.strip()):
        raise ValueError("Transitioning to 'failed' requires a non-empty error_code.")


def can_transition_approval_request(current_state: str, next_state: str) -> bool:
    """Check if a transition between approval request states is permissible."""
    if current_state not in APPROVAL_STATES or next_state not in APPROVAL_STATES:
        return False
    return next_state in ALLOWED_APPROVAL_TRANSITIONS.get(current_state, set())


def validate_approval_request_transition(current_state: str, next_state: str) -> None:
    """Validate approval request transition; raise ValueError on disallowed transition."""
    if current_state not in APPROVAL_STATES:
        raise ValueError(f"Unknown current approval state: '{current_state}'")
    if next_state not in APPROVAL_STATES:
        raise ValueError(f"Unknown target approval state: '{next_state}'")
    if current_state in TERMINAL_APPROVAL_STATES:
        raise ValueError(
            f"Cannot advance terminal approval state '{current_state}' to '{next_state}'. A new approval request is required."
        )
    allowed = ALLOWED_APPROVAL_TRANSITIONS.get(current_state, set())
    if next_state not in allowed:
        raise ValueError(
            f"Invalid approval transition from '{current_state}' to '{next_state}'. Allowed targets: {sorted(allowed)}"
        )

