"""Seed database with fictional demo organization, contracts, users, and policy rules."""

from __future__ import annotations

import datetime
import hashlib
import json
from pathlib import Path
from typing import Any, Dict
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from clauseflow.db.models import (
    Contract,
    DocumentVersion,
    Organization,
    PolicyRule,
    PolicyVersion,
    Team,
    TeamContractAccess,
    User,
    UserContractAccess,
)
from clauseflow.policy.playbook import load_playbook


def seed_demo_data(session: Session, repo_root: Path) -> Dict[str, Any]:
    """Seed the database with initial demo data from repository fixtures.
    
    Idempotent: will not create duplicate entries on repeated runs.
    Fails if existing data has conflicting policy version content.
    Caller controls session transaction commit/rollback.
    """
    repo_root = Path(repo_root)
    splits_path = repo_root / "configs" / "contract_splits.json"
    access_path = repo_root / "tests" / "fixtures" / "access_fixtures.json"
    playbook_path = repo_root / "policies" / "company_playbook_v1.yaml"

    if not splits_path.exists():
        raise FileNotFoundError(f"Missing splits manifest: {splits_path}")
    if not access_path.exists():
        raise FileNotFoundError(f"Missing access fixtures: {access_path}")
    if not playbook_path.exists():
        raise FileNotFoundError(f"Missing policy playbook: {playbook_path}")

    # 1. Load splits manifest to get real titles for development contracts
    with open(splits_path, "r", encoding="utf-8") as f:
        splits_data = json.load(f)
    dev_titles = {
        c["contract_id"]: c["title"]
        for c in splits_data.get("contracts", [])
        if c.get("split") == "development"
    }

    # 2. Load access fixtures
    with open(access_path, "r", encoding="utf-8") as f:
        access_data = json.load(f)

    org_id = access_data.get("org_id", "org_demo")
    allocations = access_data.get("contract_allocations", [])
    if len(allocations) != 6:
        raise ValueError(f"Expected exactly 6 contract allocations in fixture, found {len(allocations)}")

    # Verify all allocated contracts exist in development manifest
    for alloc in allocations:
        cid = alloc["contract_id"]
        if cid not in dev_titles:
            raise ValueError(
                f"Contract '{cid}' in access fixture does not belong to the development split in {splits_path}"
            )

    # 3. Load policy playbook and compute raw bytes SHA256
    playbook = load_playbook(playbook_path)
    with open(playbook_path, "rb") as f:
        raw_yaml_bytes = f.read()
    yaml_sha256 = hashlib.sha256(raw_yaml_bytes).hexdigest()
    yaml_text = raw_yaml_bytes.decode("utf-8")

    # 4. Seed Organization
    org = session.get(Organization, org_id)
    if not org:
        org = Organization(org_id=org_id, name="Demo Organization")
        session.add(org)
        session.flush()

    # 5. Seed Teams
    seeded_teams = {}
    for team_entry in access_data.get("teams", []):
        tid = team_entry["team_id"]
        team = session.get(Team, tid)
        if not team:
            team = Team(team_id=tid, org_id=org_id, name=team_entry.get("name", tid))
            session.add(team)
            session.flush()
        seeded_teams[tid] = team

    # 6. Seed Users
    seeded_users = {}
    for user_entry in access_data.get("users", []):
        uname = user_entry["username"]
        role = user_entry["role"]
        tid = user_entry.get("team_id")
        user = session.execute(
            select(User).where(User.org_id == org_id, User.username == uname)
        ).scalar_one_or_none()
        if not user:
            user = User(
                user_id=uuid.uuid4(),
                org_id=org_id,
                username=uname,
                role=role,
                team_id=tid,
                active=True,
                password_hash=None,
            )
            session.add(user)
            session.flush()
        seeded_users[uname] = user

    # 7. Seed Contracts and Document Versions
    seeded_contracts = {}
    for alloc in allocations:
        cid = alloc["contract_id"]
        title = dev_titles[cid]
        contract = session.get(Contract, cid)
        if not contract:
            contract = Contract(
                contract_id=cid,
                org_id=org_id,
                title=title,
                source_type="cuad",
                uploaded_by=None,
            )
            session.add(contract)
            session.flush()
        seeded_contracts[cid] = contract

        # Version 1 document version
        doc_ver = session.execute(
            select(DocumentVersion).where(
                DocumentVersion.contract_id == cid,
                DocumentVersion.version == 1,
            )
        ).scalar_one_or_none()
        if not doc_ver:
            doc_ver = DocumentVersion(
                document_version_id=uuid.uuid4(),
                contract_id=cid,
                version=1,
                content_sha256=None,
                local_path=None,
                ingestion_status="not_started",
            )
            session.add(doc_ver)
            session.flush()

    # 8. Seed Team Contract Access
    team_grants_count = 0
    for alloc in allocations:
        cid = alloc["contract_id"]
        tid = alloc["team_id"]
        t_access = session.get(TeamContractAccess, (tid, cid))
        if not t_access:
            t_access = TeamContractAccess(
                team_id=tid,
                contract_id=cid,
                permission="read",
            )
            session.add(t_access)
            session.flush()
            team_grants_count += 1

    # 9. Seed User Contract Access (Explicit grants for legal_reviewer on all 6 contracts)
    legal_reviewer = seeded_users.get("legal_reviewer")
    user_grants_count = 0
    if legal_reviewer:
        for cid in seeded_contracts:
            u_access = session.get(UserContractAccess, (legal_reviewer.user_id, cid))
            if not u_access:
                u_access = UserContractAccess(
                    user_id=legal_reviewer.user_id,
                    contract_id=cid,
                    permission="read",
                )
                session.add(u_access)
                session.flush()
                user_grants_count += 1

    # 10. Seed Policy Version
    policy_id = playbook["policy_id"]
    version_num = playbook["version"]
    effective_dt = datetime.date.fromisoformat(str(playbook["effective_date"]))

    existing_pv = session.execute(
        select(PolicyVersion).where(
            PolicyVersion.org_id == org_id,
            PolicyVersion.policy_id == policy_id,
            PolicyVersion.version == version_num,
        )
    ).scalar_one_or_none()

    if existing_pv:
        if existing_pv.content_sha256 != yaml_sha256:
            raise ValueError(
                f"Policy version {version_num} for '{policy_id}' already exists with differing content hash. Cannot overwrite."
            )
        policy_version = existing_pv
    else:
        policy_version = PolicyVersion(
            policy_version_id=uuid.uuid4(),
            org_id=org_id,
            policy_id=policy_id,
            version=version_num,
            status=playbook["status"],
            effective_date=effective_dt,
            content_sha256=yaml_sha256,
            source_yaml=yaml_text,
            published_by=None,
        )
        session.add(policy_version)
        session.flush()

    # 11. Seed Policy Rules
    rules_count = 0
    for rule in playbook.get("rules", []):
        rid = rule["rule_id"]
        p_rule = session.execute(
            select(PolicyRule).where(
                PolicyRule.policy_version_id == policy_version.policy_version_id,
                PolicyRule.rule_id == rid,
            )
        ).scalar_one_or_none()

        if not p_rule:
            p_rule = PolicyRule(
                rule_record_id=uuid.uuid4(),
                policy_version_id=policy_version.policy_version_id,
                rule_id=rid,
                business_area=rule["business_area"],
                severity=rule["severity"],
                approver_role=rule["approver_role"],
                source_text=rule["source_text"],
                conditions=rule["conditions"],
                unknown_handling=rule["unknown_handling"],
            )
            session.add(p_rule)
            session.flush()
            rules_count += 1

    return {
        "organizations": 1,
        "teams": len(seeded_teams),
        "users": len(seeded_users),
        "contracts": len(seeded_contracts),
        "document_versions": len(seeded_contracts),
        "team_grants": 6,
        "user_grants": 6,
        "policy_versions": 1,
        "policy_rules": len(playbook.get("rules", [])),
    }

