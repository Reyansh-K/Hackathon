"""Tamper-evident chain of custody.

Every action on a case becomes one ledger entry: sealing a file, running an
analyzer, calling an AI model, an examiner approving a finding. Each entry
stores the hash of the entry before it, so editing, deleting or reordering any
past entry breaks verification from that point on. Sealed files are
fingerprinted with SHA-256, so changing a single byte of an exhibit is caught
the next time the case is verified.

The ledger also exposes a Merkle root over all entry hashes (RFC 6962 style,
with leaf and node prefixes) plus inclusion proofs, so one entry can be proven
to belong to a case without handing over the rest of the case.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

GENESIS_HASH = "0" * 64
_CHUNK = 1 << 20


def canonical_json(obj: Any) -> bytes:
    """Deterministic JSON bytes: sorted keys, no extra whitespace, UTF-8."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class Entry:
    index: int
    timestamp: str
    actor: str
    action: str
    exhibit_id: str | None
    payload: dict
    prev_hash: str
    entry_hash: str

    def body(self) -> dict:
        data = asdict(self)
        data.pop("entry_hash")
        return data


def compute_entry_hash(body: dict) -> str:
    return sha256_bytes(canonical_json(body))


@dataclass
class VerifyReport:
    ok: bool
    entries_checked: int
    exhibits_checked: int = 0
    problems: list[str] = field(default_factory=list)
    first_bad_index: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class CustodyLedger:
    """Append-only, hash-chained log stored as JSON Lines."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else None
        self.entries: list[Entry] = []
        if self.path and self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    self.entries.append(Entry(**json.loads(line)))

    @property
    def head(self) -> str:
        return self.entries[-1].entry_hash if self.entries else GENESIS_HASH

    def append(
        self,
        actor: str,
        action: str,
        exhibit_id: str | None = None,
        payload: dict | None = None,
        timestamp: str | None = None,
    ) -> Entry:
        body = {
            "index": len(self.entries),
            "timestamp": timestamp or utc_now(),
            "actor": actor,
            "action": action,
            "exhibit_id": exhibit_id,
            "payload": payload or {},
            "prev_hash": self.head,
        }
        entry = Entry(**body, entry_hash=compute_entry_hash(body))
        self.entries.append(entry)
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")
        return entry

    def seal_file(self, path: str | Path, exhibit_id: str, actor: str, kind: str) -> Entry:
        file_path = Path(path)
        return self.append(
            actor,
            "SEAL",
            exhibit_id,
            {
                "file_name": file_path.name,
                "kind": kind,
                "size_bytes": file_path.stat().st_size,
                "sha256": sha256_file(file_path),
            },
        )

    def sealed_exhibits(self) -> dict[str, dict]:
        return {e.exhibit_id: e.payload for e in self.entries if e.action == "SEAL" and e.exhibit_id}

    def verify(self, exhibit_files: dict[str, Path] | None = None) -> VerifyReport:
        """Re-check every link in the chain, and optionally every sealed file."""
        problems: list[str] = []
        first_bad: int | None = None
        expected_prev = GENESIS_HASH
        for position, entry in enumerate(self.entries):
            entry_problems = []
            if entry.index != position:
                entry_problems.append(
                    f"entry {position}: index says {entry.index}, so entries were removed or reordered"
                )
            if entry.prev_hash != expected_prev:
                entry_problems.append(f"entry {position}: does not link to the entry before it (chain broken)")
            if compute_entry_hash(entry.body()) != entry.entry_hash:
                entry_problems.append(f"entry {position}: contents changed after it was written")
            if entry_problems and first_bad is None:
                first_bad = position
            problems.extend(entry_problems)
            expected_prev = entry.entry_hash

        exhibits_checked = 0
        if exhibit_files is not None:
            sealed = self.sealed_exhibits()
            for exhibit_id, seal in sealed.items():
                path = exhibit_files.get(exhibit_id)
                if path is None or not Path(path).exists():
                    problems.append(f"{exhibit_id}: sealed file is missing")
                    continue
                exhibits_checked += 1
                actual = sha256_file(path)
                if actual != seal["sha256"]:
                    problems.append(
                        f"{exhibit_id}: SHA-256 mismatch, the file changed after sealing "
                        f"(sealed {seal['sha256'][:12]}..., now {actual[:12]}...)"
                    )
            for exhibit_id in exhibit_files:
                if exhibit_id not in sealed:
                    problems.append(f"{exhibit_id}: file was never sealed into the ledger")

        return VerifyReport(
            ok=not problems,
            entries_checked=len(self.entries),
            exhibits_checked=exhibits_checked,
            problems=problems,
            first_bad_index=first_bad,
        )

    def merkle_root(self) -> str:
        return merkle_root(e.entry_hash for e in self.entries)

    def inclusion_proof(self, index: int) -> list[dict]:
        return merkle_proof([e.entry_hash for e in self.entries], index)


# Merkle tree (RFC 6962 style: 0x00 prefix for leaves, 0x01 for inner nodes,
# an odd node is promoted unchanged instead of being duplicated).

def _leaf(hex_hash: str) -> bytes:
    return hashlib.sha256(b"\x00" + bytes.fromhex(hex_hash)).digest()


def _node(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(b"\x01" + left + right).digest()


def merkle_root(hashes: Iterable[str]) -> str:
    level = [_leaf(h) for h in hashes]
    if not level:
        return GENESIS_HASH
    while len(level) > 1:
        nxt = [_node(level[i], level[i + 1]) for i in range(0, len(level) - 1, 2)]
        if len(level) % 2:
            nxt.append(level[-1])
        level = nxt
    return level[0].hex()


def merkle_proof(hashes: list[str], index: int) -> list[dict]:
    """Sibling path from leaf `index` up to the root."""
    if not 0 <= index < len(hashes):
        raise IndexError("leaf index out of range")
    level = [_leaf(h) for h in hashes]
    proof: list[dict] = []
    position = index
    while len(level) > 1:
        sibling = position ^ 1
        if sibling < len(level):
            proof.append({"side": "left" if sibling < position else "right", "hash": level[sibling].hex()})
        nxt = [_node(level[i], level[i + 1]) for i in range(0, len(level) - 1, 2)]
        if len(level) % 2:
            nxt.append(level[-1])
        level = nxt
        position //= 2
    return proof


def verify_merkle_proof(leaf_hash: str, proof: list[dict], root: str) -> bool:
    current = _leaf(leaf_hash)
    for step in proof:
        sibling = bytes.fromhex(step["hash"])
        current = _node(sibling, current) if step["side"] == "left" else _node(current, sibling)
    return current.hex() == root
