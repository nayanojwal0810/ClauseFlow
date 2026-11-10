"""Focused unit tests for CUAD contract preparation and split pipeline."""

from __future__ import annotations

import json
from pathlib import Path
import zipfile
import pytest

from clauseflow.data.prepare import (
    CATEGORY_CANONICAL_MAP,
    SELECTED_CATEGORIES,
    compute_file_sha256,
    generate_contract_id,
    normalize_title,
    prepare_dataset,
    split_training_contracts,
)


def create_mock_cuad_archive(zip_path: Path, contracts_data: list[dict]) -> Path:
    """Create a minimal artificial CUAD zip archive with CUAD_v1.json."""
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": "v1", "data": contracts_data}
    with zipfile.ZipFile(zip_path, "w") as z:
        z.writestr("CUAD_v1/CUAD_v1.json", json.dumps(payload))
    return zip_path


def create_mock_splits_archive(
    zip_path: Path, train_titles: list[str], test_titles: list[str]
) -> Path:
    """Create a minimal artificial publisher splits zip archive."""
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    train_payload = {"data": [{"title": t} for t in train_titles]}
    test_payload = {"data": [{"title": t} for t in test_titles]}
    with zipfile.ZipFile(zip_path, "w") as z:
        z.writestr("train_separate_questions.json", json.dumps(train_payload))
        z.writestr("test.json", json.dumps(test_payload))
    return zip_path


def build_contract_fixture(
    title: str,
    context: str | None = None,
    qas: list[dict] | None = None,
) -> dict:
    """Build a minimal contract dictionary for testing."""
    if context is None:
        context = f"This is a sample agreement context specifically for {title}."
    if qas is None:
        qas = []
        for cat in SELECTED_CATEGORIES:
            qas.append({
                "id": f"{title}__{cat}",
                "question": f'Highlight the parts related to "{cat}".',
                "is_impossible": False,
                "answers": [{"text": "agreement", "answer_start": context.find("agreement")}],
            })
    return {
        "title": title,
        "paragraphs": [
            {
                "context": context,
                "qas": qas,
            }
        ],
    }


def test_stable_title_normalization_and_contract_ids():
    """Verify whitespace normalization and deterministic contract ID hashing."""
    t1 = "  Alpha   Corp   Agreement  "
    t2 = "Alpha Corp Agreement"
    t3 = "Alpha\tCorp\nAgreement"

    assert normalize_title(t1) == "Alpha Corp Agreement"
    assert normalize_title(t2) == "Alpha Corp Agreement"
    assert normalize_title(t3) == "Alpha Corp Agreement"

    id1 = generate_contract_id(t1)
    id2 = generate_contract_id(t2)
    id3 = generate_contract_id(t3)

    assert id1 == id2 == id3
    assert id1.startswith("cuad_")
    assert len(id1) == 21  # 'cuad_' (5) + 16 hex chars

    # Different titles must produce distinct contract IDs
    id_diff = generate_contract_id("Beta Corp Agreement")
    assert id1 != id_diff


@pytest.mark.parametrize(
    "total_train,val_count,seed",
    [
        (10, 3, 42),
        (20, 5, 42),
        (408, 80, 42),
    ],
)
def test_deterministic_split_logic(total_train: int, val_count: int, seed: int):
    """Verify deterministic split counts, zero overlap, and reproducible selection."""
    mock_train = [
        {"contract_id": f"cuad_{i:04d}", "title": f"Contract_{i:04d}"}
        for i in range(total_train)
    ]

    dev_1, val_1 = split_training_contracts(mock_train, val_count=val_count, seed=seed)
    dev_2, val_2 = split_training_contracts(mock_train, val_count=val_count, seed=seed)

    assert len(val_1) == val_count
    assert len(dev_1) == total_train - val_count

    # Exactly idempotent across runs
    assert [c["contract_id"] for c in dev_1] == [c["contract_id"] for c in dev_2]
    assert [c["contract_id"] for c in val_1] == [c["contract_id"] for c in val_2]

    # No overlap
    dev_ids = {c["contract_id"] for c in dev_1}
    val_ids = {c["contract_id"] for c in val_1}
    assert dev_ids.isdisjoint(val_ids)
    assert dev_ids | val_ids == {c["contract_id"] for c in mock_train}


def test_train_test_overlap_detection(tmp_path: Path):
    """Reject archives where official train and test splits overlap."""
    titles = ["Contract_A", "Contract_B", "Contract_C"]
    full_zip = create_mock_cuad_archive(
        tmp_path / "full.zip", [build_contract_fixture(t) for t in titles]
    )
    # Contract_B appears in BOTH train and test
    split_zip = create_mock_splits_archive(
        tmp_path / "split.zip",
        train_titles=["Contract_A", "Contract_B"],
        test_titles=["Contract_B", "Contract_C"],
    )

    with pytest.raises(ValueError, match="Publisher train and test splits overlap"):
        prepare_dataset(
            archive_path=full_zip,
            split_archive_path=split_zip,
            output_dir=tmp_path / "out",
            manifest_path=tmp_path / "manifest.json",
            expected_full_count=3,
            expected_train_count=None,
            expected_test_count=None,
            val_count=1,
        )


def test_missing_contract_in_splits(tmp_path: Path):
    """Reject archives when source contracts are missing from publisher splits."""
    titles = ["Contract_A", "Contract_B", "Contract_C"]
    full_zip = create_mock_cuad_archive(
        tmp_path / "full.zip", [build_contract_fixture(t) for t in titles]
    )
    # Contract_C is missing from both train and test
    split_zip = create_mock_splits_archive(
        tmp_path / "split.zip",
        train_titles=["Contract_A"],
        test_titles=["Contract_B"],
    )

    with pytest.raises(ValueError, match="not found in either publisher train or test split"):
        prepare_dataset(
            archive_path=full_zip,
            split_archive_path=split_zip,
            output_dir=tmp_path / "out",
            manifest_path=tmp_path / "manifest.json",
            expected_full_count=3,
            expected_train_count=None,
            expected_test_count=None,
            val_count=1,
        )


def test_duplicate_title_or_id_collision(tmp_path: Path):
    """Reject full archive with duplicate or colliding contract titles."""
    contracts = [
        build_contract_fixture("Contract_A"),
        build_contract_fixture("  Contract_A  "),  # duplicate after normalization
    ]
    full_zip = create_mock_cuad_archive(tmp_path / "full.zip", contracts)
    split_zip = create_mock_splits_archive(
        tmp_path / "split.zip",
        train_titles=["Contract_A"],
        test_titles=[],
    )

    with pytest.raises(ValueError, match="Duplicate contract title detected"):
        prepare_dataset(
            archive_path=full_zip,
            split_archive_path=split_zip,
            output_dir=tmp_path / "out",
            manifest_path=tmp_path / "manifest.json",
            expected_full_count=2,
            expected_train_count=None,
            expected_test_count=None,
            val_count=0,
        )


def test_text_and_offset_preservation_including_no_answer(tmp_path: Path):
    """Verify exact preservation of paragraph context, offsets, and negative cases."""
    ctx_1 = "Contract 1 context: Termination for Convenience is permitted with 30 days notice."
    ctx_2 = "Contract 2 context: Termination for Convenience is permitted with 60 days notice and Uncapped Liability applies."
    ctx_3 = "Contract 3 context: Termination for Convenience is permitted with 90 days notice and Uncapped Liability applies."
    ctx_test = "Contract Test context: Termination for Convenience is permitted with 120 days notice."

    def make_qas(ctx: str, prefix: str, include_uncapped_positive: bool = True):
        start_pos = ctx.find("Termination for Convenience")
        uncapped_start = ctx.find("Uncapped Liability")
        qas = [
            {
                "id": f"{prefix}__Termination For Convenience",
                "question": 'Highlight the parts related to "Termination For Convenience".',
                "is_impossible": False,
                "answers": [{"text": "Termination for Convenience", "answer_start": start_pos}],
            },
        ]
        if include_uncapped_positive and uncapped_start != -1:
            qas.append({
                "id": f"{prefix}__Uncapped Liability",
                "question": 'Highlight the parts related to "Uncapped Liability".',
                "is_impossible": False,
                "answers": [{"text": "Uncapped Liability", "answer_start": uncapped_start}],
            })
        else:
            qas.append({
                "id": f"{prefix}__Uncapped Liability",
                "question": 'Highlight the parts related to "Uncapped Liability".',
                "is_impossible": True,
                "answers": [],
            })

        for cat in ["Notice Period To Terminate Renewal", "Renewal Term", "Cap On Liability"]:
            qas.append({
                "id": f"{prefix}__{cat}",
                "question": f'Highlight the parts related to "{cat}".',
                "is_impossible": False,
                "answers": [{"text": "Termination", "answer_start": start_pos}],
            })
        return qas

    # Contract 1 has no-answer for Uncapped Liability
    c1 = {"title": "Contract_1", "paragraphs": [{"context": ctx_1, "qas": make_qas(ctx_1, "Contract_1", include_uncapped_positive=False)}]}
    # Contracts 2 and 3 have positive answer for Uncapped Liability
    c2 = {"title": "Contract_2", "paragraphs": [{"context": ctx_2, "qas": make_qas(ctx_2, "Contract_2", include_uncapped_positive=True)}]}
    c3 = {"title": "Contract_3", "paragraphs": [{"context": ctx_3, "qas": make_qas(ctx_3, "Contract_3", include_uncapped_positive=True)}]}
    c_test = {"title": "Contract_Test", "paragraphs": [{"context": ctx_test, "qas": make_qas(ctx_test, "Contract_Test", include_uncapped_positive=False)}]}

    full_zip = create_mock_cuad_archive(tmp_path / "full.zip", [c1, c2, c3, c_test])
    split_zip = create_mock_splits_archive(
        tmp_path / "split.zip",
        train_titles=["Contract_1", "Contract_2", "Contract_3"],
        test_titles=["Contract_Test"],
    )

    out_dir = tmp_path / "out"
    manifest = tmp_path / "manifest.json"

    prepare_dataset(
        archive_path=full_zip,
        split_archive_path=split_zip,
        output_dir=out_dir,
        manifest_path=manifest,
        expected_full_count=4,
        expected_train_count=3,
        expected_test_count=1,
        val_count=1,
    )

    # Check contracts.jsonl
    contracts_file = out_dir / "contracts.jsonl"
    assert contracts_file.exists()
    contracts = [json.loads(line) for line in contracts_file.read_text(encoding="utf-8").splitlines()]
    assert len(contracts) == 4
    for c in contracts:
        assert len(c["paragraphs"][0]["context"]) > 0

    # Check annotations across dev and val
    dev_anno_file = out_dir / "development_annotations.jsonl"
    val_anno_file = out_dir / "validation_annotations.jsonl"
    assert dev_anno_file.exists()
    assert val_anno_file.exists()
    dev_annos = [json.loads(line) for line in dev_anno_file.read_text(encoding="utf-8").splitlines()]
    val_annos = [json.loads(line) for line in val_anno_file.read_text(encoding="utf-8").splitlines()]
    all_train_annos = dev_annos + val_annos

    # Locate positive annotation
    term_annos = [a for a in all_train_annos if a["category"] == "Termination For Convenience"]
    assert len(term_annos) == 3
    for a in term_annos:
        assert a["is_impossible"] is False
        assert a["answers"][0]["text"] == "Termination for Convenience"

    # Locate negative annotation from Contract_1
    c1_uncapped = [a for a in all_train_annos if a["category"] == "Uncapped Liability" and "Contract_1" in a["qa_id"]]
    assert len(c1_uncapped) == 1
    assert c1_uncapped[0]["is_impossible"] is True
    assert c1_uncapped[0]["answers"] == []


def test_missing_archive_and_missing_member_failure(tmp_path: Path):
    """Verify clear failures when archive file or required member is missing."""
    missing_zip = tmp_path / "nonexistent.zip"
    dummy_zip = tmp_path / "empty.zip"
    with zipfile.ZipFile(dummy_zip, "w") as z:
        z.writestr("irrelevant.txt", "hello")

    with pytest.raises(FileNotFoundError, match="Full CUAD archive not found"):
        prepare_dataset(
            archive_path=missing_zip,
            split_archive_path=dummy_zip,
            output_dir=tmp_path / "out",
            manifest_path=tmp_path / "manifest.json",
        )

    with pytest.raises(FileNotFoundError, match="Could not find member with basename 'CUAD_v1.json'"):
        prepare_dataset(
            archive_path=dummy_zip,
            split_archive_path=dummy_zip,
            output_dir=tmp_path / "out",
            manifest_path=tmp_path / "manifest.json",
        )


def test_manifest_idempotency_and_conflict_detection(tmp_path: Path):
    """Verify that rerun produces identical manifest, and conflicting manifest raises error."""
    titles = [f"Contract_{i:02d}" for i in range(4)]
    full_zip = create_mock_cuad_archive(
        tmp_path / "full.zip", [build_contract_fixture(t) for t in titles]
    )
    split_zip = create_mock_splits_archive(
        tmp_path / "split.zip",
        train_titles=titles[:3],
        test_titles=titles[3:],
    )

    out_dir = tmp_path / "out"
    manifest_path = tmp_path / "configs" / "contract_splits.json"

    # Run 1
    prepare_dataset(
        archive_path=full_zip,
        split_archive_path=split_zip,
        output_dir=out_dir,
        manifest_path=manifest_path,
        expected_full_count=4,
        expected_train_count=3,
        expected_test_count=1,
        val_count=1,
    )
    content_run_1 = manifest_path.read_text(encoding="utf-8")

    # Run 2 with identical inputs - must succeed and remain byte-for-byte identical
    prepare_dataset(
        archive_path=full_zip,
        split_archive_path=split_zip,
        output_dir=out_dir,
        manifest_path=manifest_path,
        expected_full_count=4,
        expected_train_count=3,
        expected_test_count=1,
        val_count=1,
    )
    content_run_2 = manifest_path.read_text(encoding="utf-8")
    assert content_run_1 == content_run_2

    # Manually tamper with manifest on disk
    tampered = json.loads(content_run_1)
    tampered["counts"]["development"] = 9999
    manifest_path.write_text(json.dumps(tampered), encoding="utf-8")

    # Run 3 should fail due to conflict
    with pytest.raises(ValueError, match="conflicts with newly generated split manifest"):
        prepare_dataset(
            archive_path=full_zip,
            split_archive_path=split_zip,
            output_dir=out_dir,
            manifest_path=manifest_path,
            expected_full_count=4,
            expected_train_count=3,
            expected_test_count=1,
            val_count=1,
        )


def test_cross_split_duplicate_text_detection(tmp_path: Path):
    """Detect and fail when identical document text appears across split boundaries."""
    shared_text = "Standard identical master terms between Alpha and Beta."
    c_train = build_contract_fixture("Contract_Train", context=shared_text)
    c_test = build_contract_fixture("Contract_Test", context=shared_text)

    full_zip = create_mock_cuad_archive(tmp_path / "full.zip", [c_train, c_test])
    split_zip = create_mock_splits_archive(
        tmp_path / "split.zip",
        train_titles=["Contract_Train"],
        test_titles=["Contract_Test"],
    )

    with pytest.raises(RuntimeError, match="Exact cross-split duplicate contracts detected"):
        prepare_dataset(
            archive_path=full_zip,
            split_archive_path=split_zip,
            output_dir=tmp_path / "out",
            manifest_path=tmp_path / "manifest.json",
            expected_full_count=2,
            expected_train_count=1,
            expected_test_count=1,
            val_count=0,
        )
