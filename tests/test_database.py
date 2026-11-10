"""Tests for database models, metadata, migrations, constraints, and seed logic."""

from __future__ import annotations

import json
from pathlib import Path
import pytest
from sqlalchemy import inspect, select
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from clauseflow.db.database import get_db_url, get_engine
from clauseflow.db.models import (
    ApprovalRequest,
    AuditEvent,
    Base,
    Contract,
    DocumentVersion,
    Organization,
    PolicyRule,
    PolicyVersion,
    ReviewRun,
    Team,
    TeamContractAccess,
    User,
    UserContractAccess,
)
from clauseflow.db.seed import seed_demo_data
from clauseflow.workflows.transitions import advance_approval_request, advance_review_run

EXPECTED_TABLES = {
    "organizations",
    "teams",
    "users",
    "contracts",
    "document_versions",
    "team_contract_access",
    "user_contract_access",
    "policy_versions",
    "policy_rules",
    "chunks",
    "review_runs",
    "findings",
    "approval_requests",
    "audit_events",
    "model_runs",
}


def test_models_metadata_has_all_15_tables():
    """Verify that SQLAlchemy metadata defines all 15 required tables."""
    table_names = set(Base.metadata.tables.keys())
    assert table_names == EXPECTED_TABLES, f"Missing or extra tables: {EXPECTED_TABLES.symmetric_difference(table_names)}"
    assert len(table_names) == 15


def test_database_url_requires_password(monkeypatch):
    """Verify that get_db_url fails clearly when password is not provided."""
    monkeypatch.delenv("CF_DB_PASSWORD", raising=False)
    with pytest.raises(ValueError, match="Database password is required"):
        get_db_url(password=None)

    url = get_db_url(password="secret_pass_123", user="test_user", host="127.0.0.1", port=5433, name="test_db")
    assert url.drivername == "postgresql+psycopg"
    assert url.username == "test_user"
    assert url.host == "127.0.0.1"
    assert url.port == 5433
    assert url.database == "test_db"


@pytest.fixture(scope="module")
def db_engine():
    """Fixture providing a connected SQLAlchemy engine or skipping if DB unavailable."""
    try:
        engine = get_engine(connect_args={"connect_timeout": 2})
        with engine.connect() as conn:
            pass
        return engine
    except Exception as exc:
        pytest.skip(f"PostgreSQL database not available ({exc}). Skipping DB integration tests.")


@pytest.fixture
def db_session(db_engine):
    """Fixture providing a transactional session isolated with rollback."""
    with Session(db_engine) as session:
        yield session
        session.rollback()


def test_db_foreign_key_constraint_enforcement(db_session):
    """Verify that PostgreSQL rejects rows violating foreign key constraints."""
    bad_team = Team(team_id="orphan_team", org_id="nonexistent_org", name="Orphan")
    db_session.add(bad_team)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_db_unique_constraint_enforcement(db_session):
    """Verify that PostgreSQL rejects duplicate rows on unique constraints."""
    repo_root = Path(__file__).resolve().parent.parent
    seed_demo_data(db_session, repo_root)

    dup_org = Organization(org_id="org_demo", name="Duplicate Demo Org")
    db_session.add(dup_org)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_db_seed_idempotence_and_contract_verification(db_session):
    """Verify database seed produces correct counts and is strictly idempotent."""
    repo_root = Path(__file__).resolve().parent.parent
    summary1 = seed_demo_data(db_session, repo_root)

    assert summary1["organizations"] == 1
    assert summary1["teams"] == 2
    assert summary1["users"] == 4
    assert summary1["contracts"] == 6
    assert summary1["document_versions"] == 6
    assert summary1["team_grants"] == 6
    assert summary1["user_grants"] == 6
    assert summary1["policy_versions"] == 1
    assert summary1["policy_rules"] == 3

    # Verify contracts match manifest development split
    with open(repo_root / "configs" / "contract_splits.json", "r", encoding="utf-8") as f:
        manifest = json.load(f)
    sorted_first_6 = [
        c["contract_id"]
        for c in sorted([c for c in manifest["contracts"] if c["split"] == "development"], key=lambda x: x["contract_id"])[:6]
    ]

    db_contracts = db_session.execute(select(Contract.contract_id).order_by(Contract.contract_id)).scalars().all()
    assert list(db_contracts) == sorted_first_6

    # Verify second seed run produces identical counts without duplicates
    summary2 = seed_demo_data(db_session, repo_root)
    assert summary1 == summary2


def test_db_transitions_and_audit_event_creation(db_session):
    """Verify state transitions and audit event logging in PostgreSQL."""
    repo_root = Path(__file__).resolve().parent.parent
    seed_demo_data(db_session, repo_root)

    alice = db_session.execute(select(User).where(User.username == "analyst_alice")).scalar_one()
    legal_rev = db_session.execute(select(User).where(User.username == "legal_reviewer")).scalar_one()
    c1 = db_session.execute(select(Contract).order_by(Contract.contract_id)).scalars().first()
    pv = db_session.execute(select(PolicyVersion)).scalar_one()

    import uuid
    run = ReviewRun(
        review_run_id=uuid.uuid4(),
        contract_id=c1.contract_id,
        requested_by=alice.user_id,
        policy_version_id=pv.policy_version_id,
        status="created",
    )
    db_session.add(run)
    db_session.flush()

    # Advance review run
    advance_review_run(db_session, run.review_run_id, "ingesting", actor_user_id=alice.user_id)
    assert run.status == "ingesting"

    # Create approval request
    app_req = ApprovalRequest(
        approval_request_id=uuid.uuid4(),
        review_run_id=run.review_run_id,
        requested_by=alice.user_id,
        assigned_reviewer=legal_rev.user_id,
        state="draft",
        idempotency_key="key_test_1",
    )
    db_session.add(app_req)
    db_session.flush()

    advance_approval_request(db_session, app_req.approval_request_id, "pending_confirmation", actor_user_id=alice.user_id)
    advance_approval_request(db_session, app_req.approval_request_id, "pending_legal", actor_user_id=alice.user_id)

    # Unauthorized analyst attempting approval decision from pending_legal
    with pytest.raises(ValueError, match="only 'legal_reviewer' may decide legal approval requests"):
        advance_approval_request(db_session, app_req.approval_request_id, "approved", actor_user_id=alice.user_id)

    # Authorized legal reviewer approving
    advance_approval_request(db_session, app_req.approval_request_id, "approved", actor_user_id=legal_rev.user_id, comment="LGTM")
    assert app_req.state == "approved"
    assert app_req.decided_at is not None

    # Check audit events were emitted
    audit_events = db_session.execute(select(AuditEvent)).scalars().all()
    assert len(audit_events) >= 3
