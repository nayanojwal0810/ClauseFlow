"""CUAD v1 contract dataset preparation and split pipeline."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import re
from typing import Any, Dict, List, Optional, Set, Tuple
import zipfile

# Five selected categories for initial business scope
SELECTED_CATEGORIES = [
    "Notice Period To Terminate Renewal",
    "Renewal Term",
    "Termination For Convenience",
    "Uncapped Liability",
    "Cap On Liability",
]

# Canonical category mapping for normalization
CATEGORY_CANONICAL_MAP = {
    "notice to terminate renewal": "Notice Period To Terminate Renewal",
    "notice period to terminate renewal": "Notice Period To Terminate Renewal",
    "renewal term": "Renewal Term",
    "termination for convenience": "Termination For Convenience",
    "uncapped liability": "Uncapped Liability",
    "cap on liability": "Cap On Liability",
}


def compute_file_sha256(file_path: Path) -> str:
    """Compute the SHA-256 hash of a file reading in chunks."""
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(8 * 1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def normalize_title(title: str) -> str:
    """Normalize title whitespace and surrounding spaces for stable ID matching.
    
    Never normalizes or modifies document text or answer spans.
    """
    return " ".join(title.strip().split())


def generate_contract_id(title: str) -> str:
    """Build a deterministic, stable contract ID from normalized title."""
    normalized = normalize_title(title)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return f"cuad_{digest}"


def find_zip_member(archive: zipfile.ZipFile, target_basename: str) -> str:
    """Find a member in a ZIP archive by its basename.
    
    Rejects missing or ambiguous multiple candidates.
    """
    candidates = [
        name for name in archive.namelist()
        if Path(name).name.lower() == target_basename.lower() and not name.endswith("/")
    ]
    if not candidates:
        raise FileNotFoundError(
            f"Could not find member with basename '{target_basename}' in archive {archive.filename}."
        )
    if len(candidates) > 1:
        raise ValueError(
            f"Ambiguous multiple candidates found for '{target_basename}' in {archive.filename}: {candidates}"
        )
    return candidates[0]


def extract_category_from_qa(qa: Dict[str, Any]) -> str:
    """Extract category name from QA id or question text."""
    qa_id = qa.get("id", "")
    if "__" in qa_id:
        return qa_id.split("__", 1)[1]
    question = qa.get("question", "")
    match = re.search(r'related to "([^"]+)"', question)
    if match:
        return match.group(1)
    return ""


def write_atomic_text(target_path: Path, content: str, encoding: str = "utf-8") -> None:
    """Write text atomically via temporary file and replace."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target_path.with_name(f"{target_path.name}.tmp_{os.getpid()}")
    try:
        with open(temp_path, "w", encoding=encoding) as f:
            f.write(content)
        os.replace(temp_path, target_path)
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def split_training_contracts(
    train_contracts: List[Dict[str, Any]],
    val_count: int = 80,
    seed: int = 42,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Reproducibly split training contracts into development and validation sets.
    
    Sorts training contracts deterministically by contract_id, then uses
    Fisher-Yates shuffle with random.Random(seed) on indices to select validation contracts.
    """
    if val_count < 0 or val_count > len(train_contracts):
        raise ValueError(f"Invalid validation count {val_count} for {len(train_contracts)} training contracts.")
    
    sorted_train = sorted(train_contracts, key=lambda c: c["contract_id"])
    indices = list(range(len(sorted_train)))
    rng = random.Random(seed)
    rng.shuffle(indices)
    
    val_indices = set(indices[:val_count])
    validation = [sorted_train[i] for i in sorted(val_indices)]
    development = [sorted_train[i] for i in range(len(sorted_train)) if i not in val_indices]
    
    return development, validation


def prepare_dataset(
    archive_path: Path,
    split_archive_path: Path,
    output_dir: Path = Path("data/processed"),
    manifest_path: Path = Path("configs/contract_splits.json"),
    seed: int = 42,
    expected_full_count: int = 510,
    expected_train_count: int = 408,
    expected_test_count: int = 102,
    val_count: int = 80,
) -> Dict[str, Any]:
    """Prepare CUAD dataset, validate splits, generate local processed data and split manifest."""
    archive_path = Path(archive_path)
    split_archive_path = Path(split_archive_path)
    output_dir = Path(output_dir)
    manifest_path = Path(manifest_path)

    if not archive_path.exists():
        raise FileNotFoundError(f"Full CUAD archive not found at: {archive_path}")
    if not split_archive_path.exists():
        raise FileNotFoundError(f"Publisher split archive not found at: {split_archive_path}")

    full_sha256 = compute_file_sha256(archive_path)
    split_sha256 = compute_file_sha256(split_archive_path)
    archive_size = archive_path.stat().st_size
    split_size = split_archive_path.stat().st_size

    # 1. Read full CUAD JSON
    with zipfile.ZipFile(archive_path, "r") as z_full:
        full_json_name = find_zip_member(z_full, "CUAD_v1.json")
        with z_full.open(full_json_name) as f:
            full_data = json.load(f)

    if not isinstance(full_data, dict) or "data" not in full_data or not isinstance(full_data["data"], list):
        raise ValueError(f"Invalid full dataset JSON format in {full_json_name}: 'data' array expected.")

    raw_contracts = full_data["data"]
    total_raw_count = len(raw_contracts)

    # 2. Read official publisher split JSONs
    with zipfile.ZipFile(split_archive_path, "r") as z_split:
        train_json_name = find_zip_member(z_split, "train_separate_questions.json")
        test_json_name = find_zip_member(z_split, "test.json")
        with z_split.open(train_json_name) as f:
            train_data = json.load(f)
        with z_split.open(test_json_name) as f:
            test_data = json.load(f)

    if not isinstance(train_data, dict) or "data" not in train_data:
        raise ValueError("Invalid publisher train JSON: missing 'data' array.")
    if not isinstance(test_data, dict) or "data" not in test_data:
        raise ValueError("Invalid publisher test JSON: missing 'data' array.")

    official_train_titles = {normalize_title(d["title"]) for d in train_data["data"] if "title" in d}
    official_test_titles = {normalize_title(d["title"]) for d in test_data["data"] if "title" in d}

    # Validate official train / test disjointness
    train_test_overlap = official_train_titles.intersection(official_test_titles)
    if train_test_overlap:
        raise ValueError(f"Publisher train and test splits overlap on {len(train_test_overlap)} titles: {train_test_overlap}")

    # Validate expected counts if checking full official dataset
    if expected_full_count is not None and total_raw_count != expected_full_count:
        raise ValueError(f"Expected {expected_full_count} source contracts, found {total_raw_count}")
    if expected_train_count is not None and len(official_train_titles) != expected_train_count:
        raise ValueError(f"Expected {expected_train_count} official train contracts, found {len(official_train_titles)}")
    if expected_test_count is not None and len(official_test_titles) != expected_test_count:
        raise ValueError(f"Expected {expected_test_count} official test contracts, found {len(official_test_titles)}")

    # 3. Process each contract and check integrity
    contract_records: List[Dict[str, Any]] = []
    seen_contract_ids: Set[str] = set()
    seen_normalized_titles: Dict[str, str] = {}
    text_to_contracts: Dict[str, List[Dict[str, Any]]] = {}

    offset_mismatch_count = 0
    malformed_record_count = 0

    for item in raw_contracts:
        raw_title = item.get("title")
        if not raw_title or not isinstance(raw_title, str):
            malformed_record_count += 1
            raise ValueError(f"Contract missing valid title: {item}")

        norm_title = normalize_title(raw_title)
        if norm_title in seen_normalized_titles:
            raise ValueError(f"Duplicate contract title detected: '{raw_title}' conflicts with '{seen_normalized_titles[norm_title]}'")
        seen_normalized_titles[norm_title] = raw_title

        contract_id = generate_contract_id(raw_title)
        if contract_id in seen_contract_ids:
            raise ValueError(f"Contract ID collision detected for ID '{contract_id}' from title '{raw_title}'")
        seen_contract_ids.add(contract_id)

        # Decide split membership from publisher split
        if norm_title in official_test_titles:
            split_candidate = "final_test"
        elif norm_title in official_train_titles:
            split_candidate = "train_pool"
        else:
            raise ValueError(f"Contract title '{raw_title}' not found in either publisher train or test split.")

        paragraphs = item.get("paragraphs")
        if not isinstance(paragraphs, list) or len(paragraphs) == 0:
            malformed_record_count += 1
            raise ValueError(f"Contract '{raw_title}' has no valid paragraphs.")

        contract_paragraphs: List[Dict[str, Any]] = []
        contract_qas: List[Dict[str, Any]] = []

        full_context_parts: List[str] = []

        for p_idx, p in enumerate(paragraphs):
            ctx = p.get("context", "")
            if not isinstance(ctx, str):
                malformed_record_count += 1
                ctx = str(ctx)
            full_context_parts.append(ctx)
            contract_paragraphs.append({
                "paragraph_index": p_idx,
                "context": ctx,
            })

            for qa in p.get("qas", []):
                qa_id = qa.get("id")
                q_text = qa.get("question", "")
                is_imp = bool(qa.get("is_impossible", False))
                answers = qa.get("answers", [])
                category = extract_category_from_qa(qa)

                # Validate answer offsets against exact context
                validated_answers = []
                for ans in answers:
                    ans_text = ans.get("text", "")
                    ans_start = ans.get("answer_start")
                    if ans_start is None or not isinstance(ans_start, int):
                        malformed_record_count += 1
                        continue
                    # Check offset bounds
                    extracted = ctx[ans_start : ans_start + len(ans_text)]
                    if extracted != ans_text:
                        offset_mismatch_count += 1
                    validated_answers.append({
                        "text": ans_text,
                        "answer_start": ans_start,
                    })

                contract_qas.append({
                    "contract_id": contract_id,
                    "paragraph_index": p_idx,
                    "qa_id": qa_id,
                    "category": category,
                    "question": q_text,
                    "is_impossible": is_imp,
                    "answers": validated_answers,
                })

        # Hash normalized full text to detect exact-text duplicate contracts
        norm_full_text = " ".join("".join(full_context_parts).split())
        text_hash = hashlib.sha256(norm_full_text.encode("utf-8")).hexdigest()

        rec = {
            "contract_id": contract_id,
            "title": raw_title,
            "norm_title": norm_title,
            "split_candidate": split_candidate,
            "paragraphs": contract_paragraphs,
            "qas": contract_qas,
            "text_hash": text_hash,
        }
        contract_records.append(rec)
        text_to_contracts.setdefault(text_hash, []).append(rec)

    # 4. Check that train + test union equals all raw contracts
    source_titles = set(seen_normalized_titles.keys())
    split_union = official_train_titles | official_test_titles
    if source_titles != split_union:
        missing_in_splits = source_titles - split_union
        extra_in_splits = split_union - source_titles
        raise ValueError(
            f"Union of official splits does not match source contracts. Missing: {missing_in_splits}, Extra: {extra_in_splits}"
        )

    # 5. Split train_pool into development (328) and validation (80)
    train_pool = [c for c in contract_records if c["split_candidate"] == "train_pool"]
    final_test_pool = [c for c in contract_records if c["split_candidate"] == "final_test"]

    dev_contracts, val_contracts = split_training_contracts(train_pool, val_count=val_count, seed=seed)

    for c in dev_contracts:
        c["split"] = "development"
    for c in val_contracts:
        c["split"] = "validation"
    for c in final_test_pool:
        c["split"] = "final_test"

    # 6. Check for exact cross-split duplicate contracts
    exact_duplicate_clusters = []
    for thash, group in text_to_contracts.items():
        if len(group) > 1:
            splits_in_group = {c["split"] for c in group}
            cluster_info = {
                "text_hash": thash,
                "contract_ids": [c["contract_id"] for c in group],
                "titles": [c["title"] for c in group],
                "splits": [c["split"] for c in group],
            }
            exact_duplicate_clusters.append(cluster_info)
            if len(splits_in_group) > 1:
                raise RuntimeError(
                    f"Exact cross-split duplicate contracts detected across split boundaries: {cluster_info}"
                )

    # 7. Check label coverage for selected categories on development and validation
    def count_positive_contracts(contracts_subset: List[Dict[str, Any]]) -> Dict[str, int]:
        counts = {cat: 0 for cat in SELECTED_CATEGORIES}
        for c in contracts_subset:
            positive_cats_in_contract = set()
            for qa in c["qas"]:
                cat = qa["category"]
                canonical = CATEGORY_CANONICAL_MAP.get(cat.lower(), cat)
                if canonical in counts:
                    answers = qa.get("answers", [])
                    if answers and not qa.get("is_impossible", False):
                        positive_cats_in_contract.add(canonical)
            for cat in positive_cats_in_contract:
                counts[cat] += 1
        return counts

    dev_coverage = count_positive_contracts(dev_contracts)
    val_coverage = count_positive_contracts(val_contracts)

    # Verify every selected category has positive coverage in both dev and val
    for cat in SELECTED_CATEGORIES:
        if dev_coverage.get(cat, 0) == 0:
            raise ValueError(f"Selected category '{cat}' has 0 positive development contracts.")
        if val_coverage.get(cat, 0) == 0:
            raise ValueError(f"Selected category '{cat}' has 0 positive validation contracts.")

    # 8. Build sorted manifest
    all_final_contracts = dev_contracts + val_contracts + final_test_pool
    # Sort contracts stably by contract_id
    manifest_contracts = [
        {
            "contract_id": c["contract_id"],
            "title": c["title"],
            "split": c["split"],
        }
        for c in sorted(all_final_contracts, key=lambda x: x["contract_id"])
    ]

    splitting_rule_desc = (
        f"Deterministic Fisher-Yates shuffle with random.Random({seed}) on "
        f"alphabetically sorted training contract IDs (len={len(train_pool)}) allocating "
        f"{len(val_contracts)} to validation and {len(dev_contracts)} to development; "
        f"{len(final_test_pool)} official test contracts preserved as final_test."
    )

    manifest_data = {
        "dataset_name": "CUAD v1",
        "dataset_version": "1.0",
        "official_split_source_url": "https://raw.githubusercontent.com/The-Atticus-Project/cuad/main/data.zip",
        "full_archive_sha256": full_sha256,
        "official_split_archive_sha256": split_sha256,
        "seed": seed,
        "splitting_rule": splitting_rule_desc,
        "counts": {
            "total": len(manifest_contracts),
            "official_train": len(train_pool),
            "development": len(dev_contracts),
            "validation": len(val_contracts),
            "final_test": len(final_test_pool),
        },
        "contracts": manifest_contracts,
    }

    # Manifest idempotency and conflict check
    manifest_json_str = json.dumps(manifest_data, indent=2, sort_keys=False) + "\n"
    if manifest_path.exists():
        with open(manifest_path, "r", encoding="utf-8") as f:
            existing_manifest = json.load(f)
        if existing_manifest != manifest_data:
            raise ValueError(
                f"Existing manifest at {manifest_path} conflicts with newly generated split manifest. Rerun aborted to prevent inconsistent state."
            )

    # 9. Write local processed files atomically
    output_dir.mkdir(parents=True, exist_ok=True)
    contracts_file = output_dir / "contracts.jsonl"
    dev_anno_file = output_dir / "development_annotations.jsonl"
    val_anno_file = output_dir / "validation_annotations.jsonl"
    test_anno_file = output_dir / "final_test_annotations.jsonl"
    summary_file = output_dir / "preparation_summary.json"

    # Write contracts.jsonl (one line per contract, sorted by contract_id)
    contracts_lines = []
    for c in sorted(all_final_contracts, key=lambda x: x["contract_id"]):
        entry = {
            "contract_id": c["contract_id"],
            "title": c["title"],
            "split": c["split"],
            "paragraphs": c["paragraphs"],
        }
        contracts_lines.append(json.dumps(entry, ensure_ascii=False))
    write_atomic_text(contracts_file, "\n".join(contracts_lines) + "\n")

    # Helper to write annotations
    def write_annotations(filepath: Path, contracts_subset: List[Dict[str, Any]]) -> None:
        lines = []
        for c in sorted(contracts_subset, key=lambda x: x["contract_id"]):
            for qa in c["qas"]:
                lines.append(json.dumps(qa, ensure_ascii=False))
        write_atomic_text(filepath, "\n".join(lines) + "\n")

    write_annotations(dev_anno_file, dev_contracts)
    write_annotations(val_anno_file, val_contracts)
    write_annotations(test_anno_file, final_test_pool)

    # Write preparation_summary.json
    summary_data = {
        "dataset_name": "CUAD v1",
        "full_archive": {
            "path": str(archive_path),
            "size_bytes": archive_size,
            "sha256": full_sha256,
        },
        "official_split_archive": {
            "path": str(split_archive_path),
            "size_bytes": split_size,
            "sha256": split_sha256,
        },
        "contract_counts": {
            "total_source_contracts": len(all_final_contracts),
            "official_train_contracts": len(train_pool),
            "development_contracts": len(dev_contracts),
            "validation_contracts": len(val_contracts),
            "final_test_contracts": len(final_test_pool),
        },
        "selected_categories_positive_contract_counts": {
            "development": dev_coverage,
            "validation": val_coverage,
        },
        "duplicate_text_clusters": exact_duplicate_clusters,
        "quality_warnings": {
            "offset_mismatches": offset_mismatch_count,
            "malformed_records": malformed_record_count,
        },
    }
    write_atomic_text(summary_file, json.dumps(summary_data, indent=2) + "\n")

    # Write configs/contract_splits.json
    write_atomic_text(manifest_path, manifest_json_str)

    return {
        "full_archive_sha256": full_sha256,
        "split_archive_sha256": split_sha256,
        "counts": manifest_data["counts"],
        "selected_labels_coverage": {
            "development": dev_coverage,
            "validation": val_coverage,
        },
        "duplicate_clusters": exact_duplicate_clusters,
        "quality_warnings": summary_data["quality_warnings"],
        "output_files": {
            "contracts": str(contracts_file),
            "development_annotations": str(dev_anno_file),
            "validation_annotations": str(val_anno_file),
            "final_test_annotations": str(test_anno_file),
            "preparation_summary": str(summary_file),
            "split_manifest": str(manifest_path),
        },
    }
