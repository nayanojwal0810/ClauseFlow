"""Tests for company policy playbook loader, synthetic decision cases, and access fixtures."""

from __future__ import annotations

import json
from pathlib import Path
import pytest
import yaml

from clauseflow.policy.playbook import EXPECTED_RULE_IDS, load_playbook

PLAYBOOK_PATH = Path("policies/company_playbook_v1.yaml")
DEV_CASES_PATH = Path("tests/fixtures/policy_cases_development.jsonl")
ACCEPTANCE_CASES_PATH = Path("tests/fixtures/policy_cases_acceptance.jsonl")
ACCESS_FIXTURES_PATH = Path("tests/fixtures/access_fixtures.json")
MANIFEST_PATH = Path("configs/contract_splits.json")

VALID_STATUSES = {
    "COMPLIANT",
    "POTENTIAL_EXCEPTION",
    "NEEDS_REVIEW",
    "NOT_FOUND",
    "NOT_APPLICABLE",
}

EXPECTED_CASE_MATRIX = {
    # Development - Renewal
    "REN-D-01": "COMPLIANT",
    "REN-D-02": "COMPLIANT",
    "REN-D-03": "POTENTIAL_EXCEPTION",
    "REN-D-04": "POTENTIAL_EXCEPTION",
    "REN-D-05": "POTENTIAL_EXCEPTION",
    "REN-D-06": "COMPLIANT",
    "REN-D-07": "NEEDS_REVIEW",
    "REN-D-08": "NEEDS_REVIEW",
    "REN-D-09": "NEEDS_REVIEW",
    "REN-D-10": "NOT_FOUND",
    "REN-D-11": "NOT_APPLICABLE",
    "REN-D-12": "NEEDS_REVIEW",
    # Development - Termination
    "TERM-D-01": "COMPLIANT",
    "TERM-D-02": "COMPLIANT",
    "TERM-D-03": "POTENTIAL_EXCEPTION",
    "TERM-D-04": "POTENTIAL_EXCEPTION",
    "TERM-D-05": "NEEDS_REVIEW",
    "TERM-D-06": "NOT_FOUND",
    "TERM-D-07": "NEEDS_REVIEW",
    "TERM-D-08": "NEEDS_REVIEW",
    "TERM-D-09": "COMPLIANT",
    "TERM-D-10": "POTENTIAL_EXCEPTION",
    "TERM-D-11": "NEEDS_REVIEW",
    "TERM-D-12": "COMPLIANT",
    # Development - Liability
    "LIAB-D-01": "COMPLIANT",
    "LIAB-D-02": "COMPLIANT",
    "LIAB-D-03": "POTENTIAL_EXCEPTION",
    "LIAB-D-04": "POTENTIAL_EXCEPTION",
    "LIAB-D-05": "COMPLIANT",
    "LIAB-D-06": "NEEDS_REVIEW",
    "LIAB-D-07": "NOT_FOUND",
    "LIAB-D-08": "NEEDS_REVIEW",
    "LIAB-D-09": "POTENTIAL_EXCEPTION",
    "LIAB-D-10": "NEEDS_REVIEW",
    "LIAB-D-11": "COMPLIANT",
    "LIAB-D-12": "NEEDS_REVIEW",
    # Acceptance - Renewal
    "REN-A-01": "POTENTIAL_EXCEPTION",
    "REN-A-02": "COMPLIANT",
    "REN-A-03": "NOT_FOUND",
    "REN-A-04": "NEEDS_REVIEW",
    # Acceptance - Termination
    "TERM-A-01": "POTENTIAL_EXCEPTION",
    "TERM-A-02": "COMPLIANT",
    "TERM-A-03": "NOT_FOUND",
    "TERM-A-04": "NEEDS_REVIEW",
    # Acceptance - Liability
    "LIAB-A-01": "POTENTIAL_EXCEPTION",
    "LIAB-A-02": "COMPLIANT",
    "LIAB-A-03": "NOT_FOUND",
    "LIAB-A-04": "NEEDS_REVIEW",
}


def _read_jsonl(path: Path) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def test_playbook_load_valid_and_schema():
    """Verify company playbook loads correctly and adheres to schema."""
    playbook = load_playbook(PLAYBOOK_PATH)

    assert playbook["policy_id"] == "org_demo_vendor_contracts"
    assert playbook["org_id"] == "org_demo"
    assert playbook["version"] == 1
    assert playbook["status"] == "published"
    assert "not legal advice" in playbook["disclaimer"].lower()

    rules = playbook["rules"]
    assert len(rules) == 3
    rule_ids = {r["rule_id"] for r in rules}
    assert rule_ids == EXPECTED_RULE_IDS

    for r in rules:
        assert r["version"] == 1
        assert r["status"] == "published"
        assert r["approver_role"] == "legal_reviewer"
        assert isinstance(r["source_text"], str) and len(r["source_text"]) > 20
        assert isinstance(r["conditions"], dict) and len(r["conditions"]) > 0
        assert r["unknown_handling"]


def test_playbook_loader_error_handling(tmp_path: Path):
    """Verify playbook loader rejects missing files, invalid YAML, and structural issues."""
    # Missing file
    with pytest.raises(FileNotFoundError, match="not found"):
        load_playbook(tmp_path / "nonexistent.yaml")

    # Malformed YAML
    malformed_yaml = tmp_path / "malformed.yaml"
    malformed_yaml.write_text("policy_id: [unclosed list", encoding="utf-8")
    with pytest.raises(ValueError, match="Malformed YAML"):
        load_playbook(malformed_yaml)

    # Missing required top-level field
    incomplete_yaml = tmp_path / "incomplete.yaml"
    incomplete_yaml.write_text("policy_id: test\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing required top-level fields"):
        load_playbook(incomplete_yaml)

    # Duplicate rule IDs
    dup_rules_yaml = tmp_path / "dup_rules.yaml"
    valid_data = yaml.safe_load(PLAYBOOK_PATH.read_text(encoding="utf-8"))
    dup_data = dict(valid_data)
    dup_data["rules"] = [valid_data["rules"][0], valid_data["rules"][0], valid_data["rules"][1]]
    dup_rules_yaml.write_text(yaml.dump(dup_data), encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate rule_id"):
        load_playbook(dup_rules_yaml)

    # Invalid approver role
    bad_role_yaml = tmp_path / "bad_role.yaml"
    bad_role_data = dict(valid_data)
    bad_role_data["rules"] = [dict(r) for r in valid_data["rules"]]
    bad_role_data["rules"][0]["approver_role"] = "anyone"
    bad_role_yaml.write_text(yaml.dump(bad_role_data), encoding="utf-8")
    with pytest.raises(ValueError, match="approver_role must be 'legal_reviewer'"):
        load_playbook(bad_role_yaml)


def test_policy_cases_counts_and_schema():
    """Verify exact case counts, unique IDs, schema, and nonblank fields."""
    dev_cases = _read_jsonl(DEV_CASES_PATH)
    acceptance_cases = _read_jsonl(ACCEPTANCE_CASES_PATH)

    assert len(dev_cases) == 36, f"Expected 36 dev cases, found {len(dev_cases)}"
    assert len(acceptance_cases) == 12, f"Expected 12 acceptance cases, found {len(acceptance_cases)}"

    all_cases = dev_cases + acceptance_cases
    assert len(all_cases) == 48

    # Unique case IDs
    all_case_ids = [c["case_id"] for c in all_cases]
    assert len(all_case_ids) == len(set(all_case_ids)), "Duplicate case_id found"

    # Per-rule counts
    for rule_id in EXPECTED_RULE_IDS:
        rule_dev = [c for c in dev_cases if c["rule_id"] == rule_id]
        rule_acc = [c for c in acceptance_cases if c["rule_id"] == rule_id]
        assert len(rule_dev) == 12, f"Expected 12 dev cases for {rule_id}, got {len(rule_dev)}"
        assert len(rule_acc) == 4, f"Expected 4 acceptance cases for {rule_id}, got {len(rule_acc)}"

    required_keys = {
        "case_id",
        "rule_id",
        "source_type",
        "policy_version",
        "snippet",
        "extracted_facts",
        "expected_status",
        "expected_reason",
        "explanation",
    }

    for case in all_cases:
        missing = required_keys - set(case.keys())
        assert not missing, f"Case {case.get('case_id')} missing keys: {missing}"
        assert case["source_type"] == "synthetic"
        assert case["policy_version"] == 1
        assert case["expected_status"] in VALID_STATUSES
        assert isinstance(case["snippet"], str) and case["snippet"].strip()
        assert isinstance(case["expected_reason"], str) and case["expected_reason"].strip()
        assert isinstance(case["explanation"], str) and case["explanation"].strip()
        assert isinstance(case["extracted_facts"], dict)


def test_policy_cases_matrix_integrity_and_semantics():
    """Verify mandatory case matrix matches and semantic consistency holds."""
    dev_cases = _read_jsonl(DEV_CASES_PATH)
    acceptance_cases = _read_jsonl(ACCEPTANCE_CASES_PATH)
    all_cases = dev_cases + acceptance_cases

    for case in all_cases:
        cid = case["case_id"]
        assert cid in EXPECTED_CASE_MATRIX, f"Unexpected case ID {cid}"
        expected_st = EXPECTED_CASE_MATRIX[cid]
        assert case["expected_status"] == expected_st, (
            f"Case {cid} expected status {expected_st}, got {case['expected_status']}"
        )

        facts = case["extracted_facts"]
        status = case["expected_status"]

        # Semantic integrity checks
        if status == "NOT_FOUND":
            assert facts.get("evidence_found") is False, (
                f"Case {cid} with NOT_FOUND status must have evidence_found=False"
            )
            # Must not secretly state a discovered clause
            assert facts.get("company_notice_days") is None
            assert facts.get("company_right") is None
            assert facts.get("company_cap") is None

        if status in ("COMPLIANT", "POTENTIAL_EXCEPTION"):
            assert facts.get("evidence_found") is True, (
                f"Case {cid} with status {status} must have evidence_found=True"
            )
            # Party must not be unclear in definite compliant/exception cases
            assert facts.get("party_clear") is not False
            assert facts.get("notice_party") != "unclear"


def test_access_fixtures_validation():
    """Verify access fixtures use existing development contracts and enforce authorization rules."""
    with open(ACCESS_FIXTURES_PATH, "r", encoding="utf-8") as f:
        access_data = json.load(f)

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    # 1. Check org and teams
    assert access_data["org_id"] == "org_demo"
    team_ids = {t["team_id"] for t in access_data["teams"]}
    assert team_ids == {"procurement_a", "procurement_b"}

    # 2. Check users
    user_names = {u["username"] for u in access_data["users"]}
    assert user_names == {"analyst_alice", "analyst_bob", "legal_reviewer", "policy_admin"}

    # 3. Check contracts belong to development manifest
    manifest_dev_contracts = [c for c in manifest["contracts"] if c["split"] == "development"]
    sorted_dev_ids = [c["contract_id"] for c in sorted(manifest_dev_contracts, key=lambda x: x["contract_id"])]
    expected_first_6 = sorted_dev_ids[:6]

    fixture_contract_ids = [c["contract_id"] for c in access_data["contract_allocations"]]
    assert len(fixture_contract_ids) == 6
    assert fixture_contract_ids == expected_first_6

    # 4. Check team allocations (3 to procurement_a, 3 to procurement_b)
    team_a_contracts = [c["contract_id"] for c in access_data["contract_allocations"] if c["team_id"] == "procurement_a"]
    team_b_contracts = [c["contract_id"] for c in access_data["contract_allocations"] if c["team_id"] == "procurement_b"]
    assert len(team_a_contracts) == 3
    assert len(team_b_contracts) == 3

    # 5. Check action examples
    examples = access_data["action_examples"]
    assert len(examples) >= 8

    # Check cross-team denial
    cross_team_denied = [
        ex for ex in examples
        if ex["action"] == "read_contract"
        and ex["expected_allowed"] is False
        and "cross_team" in ex["reason"]
    ]
    assert len(cross_team_denied) >= 1

    # Check admin contract-read denial
    admin_denied = [
        ex for ex in examples
        if ex["actor"] == "policy_admin"
        and ex["action"] == "read_contract"
        and ex["expected_allowed"] is False
    ]
    assert len(admin_denied) >= 1

    # Check analyst policy-publish denial
    analyst_publish_denied = [
        ex for ex in examples
        if ex["actor"].startswith("analyst_")
        and ex["action"] == "publish_policy"
        and ex["expected_allowed"] is False
    ]
    assert len(analyst_publish_denied) >= 1

    # Check legal review allowed
    legal_allowed = [
        ex for ex in examples
        if ex["actor"] == "legal_reviewer"
        and ex["action"] == "read_contract"
        and ex["expected_allowed"] is True
    ]
    assert len(legal_allowed) >= 1

    # Check analyst self-approval denial
    analyst_approval_denied = [
        ex for ex in examples
        if ex["actor"].startswith("analyst_")
        and ex["action"] == "approve_exception"
        and ex["expected_allowed"] is False
    ]
    assert len(analyst_approval_denied) >= 1
