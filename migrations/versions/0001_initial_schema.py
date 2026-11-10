"""Initial relational schema for ClauseFlow.

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-11-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. organizations
    op.create_table(
        "organizations",
        sa.Column("org_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("org_id", name="pk_organizations"),
    )

    # 2. teams
    op.create_table(
        "teams",
        sa.Column("team_id", sa.Text(), nullable=False),
        sa.Column("org_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.org_id"], name="fk_teams_org_id", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("team_id", name="pk_teams"),
    )
    op.create_index("ix_teams_org_id", "teams", ["org_id"])

    # 3. users
    op.create_table(
        "users",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", sa.Text(), nullable=False),
        sa.Column("username", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("team_id", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("role IN ('analyst', 'legal_reviewer', 'policy_admin')", name="ck_users_role"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.org_id"], name="fk_users_org_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.team_id"], name="fk_users_team_id", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("user_id", name="pk_users"),
        sa.UniqueConstraint("org_id", "username", name="uq_users_org_username"),
    )
    op.create_index("ix_users_org_id", "users", ["org_id"])
    op.create_index("ix_users_team_id", "users", ["team_id"])

    # 4. contracts
    op.create_table(
        "contracts",
        sa.Column("contract_id", sa.Text(), nullable=False),
        sa.Column("org_id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("source_type IN ('cuad', 'upload')", name="ck_contracts_source_type"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.org_id"], name="fk_contracts_org_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.user_id"], name="fk_contracts_uploaded_by", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("contract_id", name="pk_contracts"),
    )
    op.create_index("ix_contracts_org_id", "contracts", ["org_id"])

    # 5. document_versions
    op.create_table(
        "document_versions",
        sa.Column("document_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("contract_id", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.Text(), nullable=True),
        sa.Column("local_path", sa.Text(), nullable=True),
        sa.Column("ingestion_status", sa.Text(), server_default="not_started", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_document_versions_version_positive"),
        sa.CheckConstraint("ingestion_status IN ('not_started', 'processing', 'ready', 'failed')", name="ck_document_versions_ingestion_status"),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.contract_id"], name="fk_document_versions_contract_id", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("document_version_id", name="pk_document_versions"),
        sa.UniqueConstraint("contract_id", "version", name="uq_document_versions_contract_version"),
    )
    op.create_index("ix_document_versions_contract_id", "document_versions", ["contract_id"])

    # 6. team_contract_access
    op.create_table(
        "team_contract_access",
        sa.Column("team_id", sa.Text(), nullable=False),
        sa.Column("contract_id", sa.Text(), nullable=False),
        sa.Column("permission", sa.Text(), server_default="read", nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("permission = 'read'", name="ck_team_contract_permission_read"),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.contract_id"], name="fk_team_contract_access_contract_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.team_id"], name="fk_team_contract_access_team_id", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("team_id", "contract_id", name="pk_team_contract_access"),
    )

    # 7. user_contract_access
    op.create_table(
        "user_contract_access",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("contract_id", sa.Text(), nullable=False),
        sa.Column("permission", sa.Text(), server_default="read", nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("permission = 'read'", name="ck_user_contract_permission_read"),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.contract_id"], name="fk_user_contract_access_contract_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], name="fk_user_contract_access_user_id", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "contract_id", name="pk_user_contract_access"),
    )

    # 8. policy_versions
    op.create_table(
        "policy_versions",
        sa.Column("policy_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", sa.Text(), nullable=False),
        sa.Column("policy_id", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("content_sha256", sa.Text(), nullable=False),
        sa.Column("source_yaml", sa.Text(), nullable=False),
        sa.Column("published_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_policy_versions_version_positive"),
        sa.CheckConstraint("status IN ('draft', 'published', 'archived')", name="ck_policy_versions_status"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.org_id"], name="fk_policy_versions_org_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["published_by"], ["users.user_id"], name="fk_policy_versions_published_by", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("policy_version_id", name="pk_policy_versions"),
        sa.UniqueConstraint("org_id", "policy_id", "version", name="uq_policy_versions_org_policy_version"),
    )
    op.create_index("ix_policy_versions_org_id", "policy_versions", ["org_id"])

    # 9. policy_rules
    op.create_table(
        "policy_rules",
        sa.Column("rule_record_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rule_id", sa.Text(), nullable=False),
        sa.Column("business_area", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("approver_role", sa.Text(), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("conditions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("unknown_handling", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["policy_version_id"], ["policy_versions.policy_version_id"], name="fk_policy_rules_policy_version_id", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("rule_record_id", name="pk_policy_rules"),
        sa.UniqueConstraint("policy_version_id", "rule_id", name="uq_policy_rules_version_rule_id"),
    )
    op.create_index("ix_policy_rules_policy_version_id", "policy_rules", ["policy_version_id"])

    # 10. chunks
    op.create_table(
        "chunks",
        sa.Column("chunk_id", sa.Text(), nullable=False),
        sa.Column("document_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.Text(), nullable=False),
        sa.Column("section_hint", sa.Text(), nullable=True),
        sa.Column("indexed_model_version", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("char_start >= 0", name="ck_chunks_char_start_non_negative"),
        sa.CheckConstraint("char_end > char_start", name="ck_chunks_char_end_greater"),
        sa.ForeignKeyConstraint(["document_version_id"], ["document_versions.document_version_id"], name="fk_chunks_document_version_id", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("chunk_id", name="pk_chunks"),
    )
    op.create_index("ix_chunks_document_version_id", "chunks", ["document_version_id"])

    # 11. review_runs
    op.create_table(
        "review_runs",
        sa.Column("review_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("contract_id", sa.Text(), nullable=False),
        sa.Column("document_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("model_version", sa.Text(), nullable=True),
        sa.Column("prompt_version", sa.Text(), nullable=True),
        sa.Column("index_version", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('created', 'ingesting', 'retrieving', 'extracting', 'evaluating', 'report_ready', 'failed')", name="ck_review_runs_status"),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.contract_id"], name="fk_review_runs_contract_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_version_id"], ["document_versions.document_version_id"], name="fk_review_runs_document_version_id", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["policy_version_id"], ["policy_versions.policy_version_id"], name="fk_review_runs_policy_version_id", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["requested_by"], ["users.user_id"], name="fk_review_runs_requested_by", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("review_run_id", name="pk_review_runs"),
    )
    op.create_index("ix_review_runs_contract_id", "review_runs", ["contract_id"])
    op.create_index("ix_review_runs_policy_version_id", "review_runs", ["policy_version_id"])
    op.create_index("ix_review_runs_requested_by", "review_runs", ["requested_by"])

    # 12. findings
    op.create_table(
        "findings",
        sa.Column("finding_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("review_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rule_id", sa.Text(), nullable=False),
        sa.Column("clause_category", sa.Text(), nullable=False),
        sa.Column("finding_status", sa.Text(), nullable=False),
        sa.Column("extracted_facts", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("evidence_refs", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("finding_status IN ('compliant', 'potential_exception', 'needs_review', 'not_found', 'not_applicable')", name="ck_findings_finding_status"),
        sa.ForeignKeyConstraint(["review_run_id"], ["review_runs.review_run_id"], name="fk_findings_review_run_id", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("finding_id", name="pk_findings"),
    )
    op.create_index("ix_findings_review_run_id", "findings", ["review_run_id"])

    # 13. approval_requests
    op.create_table(
        "approval_requests",
        sa.Column("approval_request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("review_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assigned_reviewer", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("review_comment", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("state IN ('draft', 'pending_confirmation', 'pending_legal', 'approved', 'rejected', 'changes_requested')", name="ck_approval_requests_state"),
        sa.CheckConstraint(
            "(state IN ('approved', 'rejected', 'changes_requested') AND decided_at IS NOT NULL) OR "
            "(state NOT IN ('approved', 'rejected', 'changes_requested') AND decided_at IS NULL)",
            name="ck_approval_requests_decided_at",
        ),
        sa.ForeignKeyConstraint(["assigned_reviewer"], ["users.user_id"], name="fk_approval_requests_assigned_reviewer", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["requested_by"], ["users.user_id"], name="fk_approval_requests_requested_by", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["review_run_id"], ["review_runs.review_run_id"], name="fk_approval_requests_review_run_id", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("approval_request_id", name="pk_approval_requests"),
        sa.UniqueConstraint("review_run_id", "idempotency_key", name="uq_approval_requests_run_idempotency"),
    )
    op.create_index("ix_approval_requests_review_run_id", "approval_requests", ["review_run_id"])

    # 14. audit_events
    op.create_table(
        "audit_events",
        sa.Column("audit_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("object_type", sa.Text(), nullable=False),
        sa.Column("object_id", sa.Text(), nullable=False),
        sa.Column("result", sa.Text(), nullable=False),
        sa.Column("reason_code", sa.Text(), nullable=True),
        sa.Column("request_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("result IN ('allowed', 'denied', 'success', 'failed')", name="ck_audit_events_result"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.user_id"], name="fk_audit_events_actor_user_id", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("audit_event_id", name="pk_audit_events"),
    )

    # 15. model_runs
    op.create_table(
        "model_runs",
        sa.Column("model_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("review_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("model_id", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["review_run_id"], ["review_runs.review_run_id"], name="fk_model_runs_review_run_id", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("model_run_id", name="pk_model_runs"),
    )


def downgrade() -> None:
    # Drop in reverse dependency order
    op.drop_table("model_runs")
    op.drop_table("audit_events")
    op.drop_table("approval_requests")
    op.drop_table("findings")
    op.drop_table("review_runs")
    op.drop_table("chunks")
    op.drop_table("policy_rules")
    op.drop_table("policy_versions")
    op.drop_table("user_contract_access")
    op.drop_table("team_contract_access")
    op.drop_table("document_versions")
    op.drop_table("contracts")
    op.drop_table("users")
    op.drop_table("teams")
    op.drop_table("organizations")

