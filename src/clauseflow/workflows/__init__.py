"""Workflows package for ClauseFlow."""

from clauseflow.workflows.states import (
    APPROVAL_STATES,
    ALLOWED_APPROVAL_TRANSITIONS,
    ALLOWED_REVIEW_TRANSITIONS,
    REVIEW_STATES,
    TERMINAL_APPROVAL_STATES,
    TERMINAL_REVIEW_STATES,
    can_transition_approval_request,
    can_transition_review_run,
    validate_approval_request_transition,
    validate_review_run_transition,
)
from clauseflow.workflows.transitions import (
    advance_approval_request,
    advance_review_run,
)

__all__ = [
    "ALLOWED_APPROVAL_TRANSITIONS",
    "ALLOWED_REVIEW_TRANSITIONS",
    "APPROVAL_STATES",
    "REVIEW_STATES",
    "TERMINAL_APPROVAL_STATES",
    "TERMINAL_REVIEW_STATES",
    "advance_approval_request",
    "advance_review_run",
    "can_transition_approval_request",
    "can_transition_review_run",
    "validate_approval_request_transition",
    "validate_review_run_transition",
]

