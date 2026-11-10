import json

import pytest

from exhibit_a.custody import CustodyLedger, merkle_proof, merkle_root, sha256_bytes, verify_merkle_proof


def make_ledger(tmp_path, n=5):
    ledger = CustodyLedger(tmp_path / "ledger.jsonl")
    for i in range(n):
        ledger.append("examiner:test", "NOTE", payload={"n": i}, timestamp=f"2026-11-10T00:00:0{i}+00:00")
    return ledger


def test_chain_links_and_verifies(tmp_path):
    ledger = make_ledger(tmp_path)
    assert ledger.entries[0].prev_hash == "0" * 64
    for before, after in zip(ledger.entries, ledger.entries[1:]):
        assert after.prev_hash == before.entry_hash
    reloaded = CustodyLedger(tmp_path / "ledger.jsonl")
    assert reloaded.verify().ok
    assert reloaded.head == ledger.head


def test_edited_entry_is_detected(tmp_path):
    make_ledger(tmp_path)
    path = tmp_path / "ledger.jsonl"
    lines = path.read_text().splitlines()
    entry = json.loads(lines[2])
    entry["payload"]["n"] = 999
    lines[2] = json.dumps(entry)
    path.write_text("\n".join(lines) + "\n")
    result = CustodyLedger(path).verify()
    assert not result.ok
    assert result.first_bad_index == 2
    assert any("contents changed" in p for p in result.problems)


def test_deleted_entry_is_detected(tmp_path):
    make_ledger(tmp_path)
    path = tmp_path / "ledger.jsonl"
    lines = path.read_text().splitlines()
    del lines[1]
    path.write_text("\n".join(lines) + "\n")
    result = CustodyLedger(path).verify()
    assert not result.ok
    assert result.first_bad_index == 1


def test_changed_file_is_detected(tmp_path):
    exhibit = tmp_path / "evidence.txt"
    exhibit.write_text("original")
    ledger = CustodyLedger(tmp_path / "ledger.jsonl")
    ledger.seal_file(exhibit, "EX-001", "examiner:test", "chat")
    assert ledger.verify({"EX-001": exhibit}).ok
    exhibit.write_text("originaL")
    result = ledger.verify({"EX-001": exhibit})
    assert not result.ok
    assert "SHA-256 mismatch" in result.problems[0]


def test_missing_and_unsealed_files_are_reported(tmp_path):
    exhibit = tmp_path / "evidence.txt"
    exhibit.write_text("original")
    ledger = CustodyLedger(tmp_path / "ledger.jsonl")
    ledger.seal_file(exhibit, "EX-001", "examiner:test", "chat")
    extra = tmp_path / "extra.txt"
    extra.write_text("never sealed")
    exhibit.unlink()
    problems = ledger.verify({"EX-001": exhibit, "EX-002": extra}).problems
    assert any("missing" in p for p in problems)
    assert any("never sealed" in p for p in problems)


@pytest.mark.parametrize("size", range(1, 10))
def test_merkle_inclusion_proofs(size):
    leaves = [sha256_bytes(str(i).encode()) for i in range(size)]
    root = merkle_root(leaves)
    for index, leaf in enumerate(leaves):
        assert verify_merkle_proof(leaf, merkle_proof(leaves, index), root)
    if size > 1:
        assert not verify_merkle_proof(leaves[0], merkle_proof(leaves, 1), root)
