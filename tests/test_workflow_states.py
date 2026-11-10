"""Unit tests for review and approval workflow states and transitions."""

from __future__ import annotations

import pytest

from clauseflow.workflows.states import (
    APPROVAL_STATE_APPROVED,
    APPROVAL_STATE_CHANGES_REQUESTED,
    APPROVAL_STATE_DRAFT,
    APPROVAL_STATE_PENDING_CONFIRMATION,
    APPROVAL_STATE_PENDING_LEGAL,
    APPROVAL_STATE_REJECTED,
    APPROVAL_STATES,
    REVIEW_STATE_CREATED,
    REVIEW_STATE_EVALUATING,
    REVIEW_STATE_EXTRACTING,
    REVIEW_STATE_FAILED,
    REVIEW_STATE_INGESTING,
    REVIEW_STATE_REPORT_READY,
    REVIEW_STATE_RETRIEVING,
    REVIEW_STATES,
    TERMINAL_APPROVAL_STATES,
    TERMINAL_REVIEW_STATES,
    can_transition_approval_request,
    can_transition_review_run,
    validate_approval_request_transition,
    validate_review_run_transition,
)


def test_review_run_sequential_progression():
    """Verify normal step-by-step review run pipeline transitions."""
    pipeline = [
        REVIEW_STATE_CREATED,
        REVIEW_STATE_INGESTING,
        REVIEW_STATE_RETRIEVING,
        REVIEW_STATE_EXTRACTING,
        REVIEW_STATE_EVALUATING,
        REVIEW_STATE_REPORT_READY,
    ]

    for i in range(len(pipeline) - 1):
        curr, nxt = pipeline[i], pipeline[i + 1]
        assert can_transition_review_run(curr, nxt) is True
        validate_review_run_transition(curr, nxt)


def test_review_run_failure_transitions():
    """Verify that any non-terminal state can transition to failed with an error_code."""
    non_terminal_states = [
        REVIEW_STATE_CREATED,
        REVIEW_STATE_INGESTING,
        REVIEW_STATE_RETRIEVING,
        REVIEW_STATE_EXTRACTING,
        REVIEW_STATE_EVALUATING,
    ]

    for st in non_terminal_states:
        # Valid with error_code
        assert can_transition_review_run(st, REVIEW_STATE_FAILED, error_code="ERR_TIMEOUT") is True
        validate_review_run_transition(st, REVIEW_STATE_FAILED, error_code="ERR_TIMEOUT")

        # Invalid without error_code
        assert can_transition_review_run(st, REVIEW_STATE_FAILED, error_code=None) is False
        assert can_transition_review_run(st, REVIEW_STATE_FAILED, error_code="") is False
        with pytest.raises(ValueError, match="requires a non-empty error_code"):
            validate_review_run_transition(st, REVIEW_STATE_FAILED, error_code=None)
        with pytest.raises(ValueError, match="requires a non-empty error_code"):
            validate_review_run_transition(st, REVIEW_STATE_FAILED, error_code="   ")


def test_review_run_terminal_states_cannot_transition():
    """Verify terminal review run states (report_ready, failed) cannot advance."""
    for term in TERMINAL_REVIEW_STATES:
        for target in REVIEW_STATES:
            assert can_transition_review_run(term, target) is False
            with pytest.raises(ValueError, match="Cannot advance terminal review run status"):
                validate_review_run_transition(term, target)


def test_review_run_disallowed_and_unknown_transitions():
    """Verify skip, backward, and unknown status transitions are rejected."""
    # Skips
    assert can_transition_review_run(REVIEW_STATE_CREATED, REVIEW_STATE_EXTRACTING) is False
    with pytest.raises(ValueError, match="Invalid review run transition"):
        validate_review_run_transition(REVIEW_STATE_CREATED, REVIEW_STATE_EXTRACTING)

    assert can_transition_review_run(REVIEW_STATE_RETRIEVING, REVIEW_STATE_REPORT_READY) is False
    with pytest.raises(ValueError, match="Invalid review run transition"):
        validate_review_run_transition(REVIEW_STATE_RETRIEVING, REVIEW_STATE_REPORT_READY)

    # Backwards
    assert can_transition_review_run(REVIEW_STATE_EXTRACTING, REVIEW_STATE_CREATED) is False
    with pytest.raises(ValueError, match="Invalid review run transition"):
        validate_review_run_transition(REVIEW_STATE_EXTRACTING, REVIEW_STATE_CREATED)

    # Unknown
    with pytest.raises(ValueError, match="Unknown current review status"):
        validate_review_run_transition("bogus_status", REVIEW_STATE_INGESTING)
    with pytest.raises(ValueError, match="Unknown target review status"):
        validate_review_run_transition(REVIEW_STATE_CREATED, "bogus_status")


def test_approval_request_valid_progression():
    """Verify draft -> pending_confirmation -> pending_legal -> decision."""
    # Draft to pending_confirmation
    assert can_transition_approval_request(APPROVAL_STATE_DRAFT, APPROVAL_STATE_PENDING_CONFIRMATION) is True
    validate_approval_request_transition(APPROVAL_STATE_DRAFT, APPROVAL_STATE_PENDING_CONFIRMATION)

    # Pending_confirmation to pending_legal
    assert can_transition_approval_request(APPROVAL_STATE_PENDING_CONFIRMATION, APPROVAL_STATE_PENDING_LEGAL) is True
    validate_approval_request_transition(APPROVAL_STATE_PENDING_CONFIRMATION, APPROVAL_STATE_PENDING_LEGAL)

    # Legal decisions from pending_legal
    decisions = [
        APPROVAL_STATE_APPROVED,
        APPROVAL_STATE_REJECTED,
        APPROVAL_STATE_CHANGES_REQUESTED,
    ]
    for dec in decisions:
        assert can_transition_approval_request(APPROVAL_STATE_PENDING_LEGAL, dec) is True
        validate_approval_request_transition(APPROVAL_STATE_PENDING_LEGAL, dec)


def test_approval_request_terminal_states_cannot_transition():
    """Verify terminal approval states (approved, rejected, changes_requested) cannot advance."""
    for term in TERMINAL_APPROVAL_STATES:
        for target in APPROVAL_STATES:
            assert can_transition_approval_request(term, target) is False
            with pytest.raises(ValueError, match="Cannot advance terminal approval state"):
                validate_approval_request_transition(term, target)


def test_approval_request_disallowed_and_unknown_transitions():
    """Verify skip, backward, and unknown state transitions are rejected."""
    # Skips
    assert can_transition_approval_request(APPROVAL_STATE_DRAFT, APPROVAL_STATE_PENDING_LEGAL) is False
    with pytest.raises(ValueError, match="Invalid approval transition"):
        validate_approval_request_transition(APPROVAL_STATE_DRAFT, APPROVAL_STATE_PENDING_LEGAL)

    assert can_transition_approval_request(APPROVAL_STATE_DRAFT, APPROVAL_STATE_APPROVED) is False
    with pytest.raises(ValueError, match="Invalid approval transition"):
        validate_approval_request_transition(APPROVAL_STATE_DRAFT, APPROVAL_STATE_APPROVED)

    # Backwards
    assert can_transition_approval_request(APPROVAL_STATE_PENDING_LEGAL, APPROVAL_STATE_DRAFT) is False
    with pytest.raises(ValueError, match="Invalid approval transition"):
        validate_approval_request_transition(APPROVAL_STATE_PENDING_LEGAL, APPROVAL_STATE_DRAFT)

    # Unknown
    with pytest.raises(ValueError, match="Unknown current approval state"):
        validate_approval_request_transition("unknown_state", APPROVAL_STATE_PENDING_CONFIRMATION)
    with pytest.raises(ValueError, match="Unknown target approval state"):
        validate_approval_request_transition(APPROVAL_STATE_DRAFT, "unknown_state")

