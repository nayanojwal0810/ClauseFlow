"""Company contract policy playbook loader and validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Set
import yaml

EXPECTED_RULE_IDS: Set[str] = {"P-REN-01", "P-TERM-01", "P-LIAB-01"}
REQUIRED_TOP_LEVEL_KEYS: Set[str] = {
    "policy_id",
    "org_id",
    "version",
    "status",
    "effective_date",
    "title",
    "disclaimer",
    "rules",
}
REQUIRED_RULE_KEYS: Set[str] = {
    "rule_id",
    "business_area",
    "version",
    "status",
    "applies_to",
    "rationale",
    "source_text",
    "severity",
    "approver_role",
    "conditions",
    "unknown_handling",
}


def load_playbook(path: Path | str) -> Dict[str, Any]:
    """Load and structurally validate a company policy playbook YAML file.
    
    Rejects missing files, malformed YAML, non-dictionary content, missing required
    top-level fields, unexpected/duplicate rule IDs, malformed version/status,
    missing rule text, or missing unknown handling.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Policy playbook file not found: {file_path}")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        raise ValueError(f"Malformed YAML in playbook file {file_path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"Playbook content in {file_path} must be a dictionary, got {type(data).__name__}.")

    missing_top_keys = REQUIRED_TOP_LEVEL_KEYS - set(data.keys())
    if missing_top_keys:
        raise ValueError(f"Playbook is missing required top-level fields: {sorted(missing_top_keys)}")

    if not isinstance(data["version"], int) or data["version"] < 1:
        raise ValueError(f"Playbook version must be a positive integer, got: {data.get('version')}")

    if not isinstance(data["status"], str) or not data["status"].strip():
        raise ValueError(f"Playbook status must be a non-empty string, got: {data.get('status')}")

    rules = data.get("rules")
    if not isinstance(rules, list) or len(rules) != len(EXPECTED_RULE_IDS):
        raise ValueError(
            f"Playbook rules must be a list of exactly {len(EXPECTED_RULE_IDS)} rules, found {len(rules) if isinstance(rules, list) else type(rules).__name__}."
        )

    seen_rule_ids: Set[str] = set()
    for idx, rule in enumerate(rules):
        if not isinstance(rule, dict):
            raise ValueError(f"Rule at index {idx} must be a dictionary, got {type(rule).__name__}.")

        missing_rule_keys = REQUIRED_RULE_KEYS - set(rule.keys())
        if missing_rule_keys:
            raise ValueError(f"Rule at index {idx} is missing required fields: {sorted(missing_rule_keys)}")

        rule_id = rule.get("rule_id")
        if not isinstance(rule_id, str) or not rule_id.strip():
            raise ValueError(f"Rule at index {idx} has an invalid rule_id: {rule_id}")

        if rule_id not in EXPECTED_RULE_IDS:
            raise ValueError(f"Unexpected rule_id '{rule_id}'. Expected one of {sorted(EXPECTED_RULE_IDS)}")

        if rule_id in seen_rule_ids:
            raise ValueError(f"Duplicate rule_id '{rule_id}' detected in playbook.")
        seen_rule_ids.add(rule_id)

        if not isinstance(rule.get("version"), int) or rule["version"] < 1:
            raise ValueError(f"Rule '{rule_id}' version must be a positive integer.")

        if not isinstance(rule.get("status"), str) or not rule["status"].strip():
            raise ValueError(f"Rule '{rule_id}' status must be a non-empty string.")

        source_text = rule.get("source_text")
        if not isinstance(source_text, str) or not source_text.strip():
            raise ValueError(f"Rule '{rule_id}' is missing required plain-English source_text.")

        approver_role = rule.get("approver_role")
        if approver_role != "legal_reviewer":
            raise ValueError(f"Rule '{rule_id}' approver_role must be 'legal_reviewer', got: '{approver_role}'")

        conditions = rule.get("conditions")
        if not isinstance(conditions, dict) or not conditions:
            raise ValueError(f"Rule '{rule_id}' conditions must be a non-empty dictionary.")

        unknown_handling = rule.get("unknown_handling")
        if not unknown_handling:
            raise ValueError(f"Rule '{rule_id}' is missing required unknown_handling specification.")

    if seen_rule_ids != EXPECTED_RULE_IDS:
        missing_rules = EXPECTED_RULE_IDS - seen_rule_ids
        raise ValueError(f"Playbook is missing expected rules: {sorted(missing_rules)}")

    return data
