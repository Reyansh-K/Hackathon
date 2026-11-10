"""A case on disk: sealed exhibits, findings, reviews, report and the ledger.

Layout:
  <case_dir>/case.json        case metadata and the exhibit list
  <case_dir>/ledger.jsonl     chain of custody (append-only)
  <case_dir>/exhibits/        sealed copies, named EX-001_<file>
  <case_dir>/findings.json    analyzer output
  <case_dir>/report.json      grounded AI report
  <case_dir>/ai_calls/        exact AI requests (images as hashes) and replies
"""

from __future__ import annotations

import json
import re
import secrets
import shutil
from pathlib import Path

from . import __version__
from .analyzers import Finding, analyze_chat, analyze_image, analyze_transactions, parse_chat, read_exif
from .analyzers.money import load_transactions
from .custody import CustodyLedger, VerifyReport, canonical_json, sha256_bytes, sha256_file, utc_now
from .grounding import EvidenceIndex

KIND_BY_SUFFIX = {".txt": "chat", ".csv": "transactions", ".jpg": "image", ".jpeg": "image", ".png": "image"}
CASE_ID = re.compile(r"^CASE-[0-9a-f]{8}$")
EXHIBIT_ID = re.compile(r"^EX-\d{3}$")
FINDING_ID = re.compile(r"^F-\d{3}$")
REVIEW_DECISIONS = ("confirmed", "rejected", "needs-follow-up")
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


class IntegrityError(RuntimeError):
    """A sealed exhibit no longer matches its seal."""


def safe_name(filename: str) -> str:
    name = _UNSAFE.sub("_", Path(filename).name).strip("._")
    return (name or "exhibit")[:80]


class Case:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.meta = json.loads((self.root / "case.json").read_text(encoding="utf-8"))
        self.ledger = CustodyLedger(self.root / "ledger.jsonl")

    # creation and metadata -------------------------------------------------

    @classmethod
    def create(cls, base_dir: str | Path, title: str, examiner: str = "examiner", case_id: str | None = None) -> "Case":
        case_id = case_id or f"CASE-{secrets.token_hex(4)}"
        if not CASE_ID.match(case_id):
            raise ValueError("case IDs look like CASE-1a2b3c4d")
        root = Path(base_dir) / case_id
        (root / "exhibits").mkdir(parents=True, exist_ok=False)
        meta = {"case_id": case_id, "title": title, "created_at": utc_now(), "tool_version": __version__, "exhibits": []}
        (root / "case.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        case = cls(root)
        case.ledger.append(f"examiner:{examiner}", "OPEN_CASE", payload={"case_id": case_id, "title": title})
        return case

    @property
    def case_id(self) -> str:
        return self.meta["case_id"]

    @property
    def title(self) -> str:
        return self.meta["title"]

    @property
    def exhibits(self) -> list[dict]:
        return self.meta["exhibits"]

    def _save_meta(self) -> None:
        (self.root / "case.json").write_text(json.dumps(self.meta, indent=2), encoding="utf-8")

    def exhibit(self, exhibit_id: str) -> dict:
        for exhibit in self.exhibits:
            if exhibit["id"] == exhibit_id:
                return exhibit
        raise KeyError(exhibit_id)

    def exhibit_path(self, exhibit_id: str) -> Path:
        return self.root / "exhibits" / self.exhibit(exhibit_id)["stored_as"]

    # intake ----------------------------------------------------------------

    def add_exhibit(self, source: str | Path | bytes, filename: str | None = None, examiner: str = "examiner", kind: str | None = None) -> dict:
        """Copy a file into the case and seal it. The copy is hashed and, when
        the source is a file, compared with the source hash, the same
        "hash before and after acquisition" check examiners do by hand."""
        if filename is None:
            if isinstance(source, bytes):
                raise ValueError("filename is required when adding raw bytes")
            filename = Path(source).name
        name = safe_name(filename)
        kind = kind or KIND_BY_SUFFIX.get(Path(name).suffix.lower())
        if kind not in ("chat", "transactions", "image"):
            raise ValueError(f"unsupported exhibit type for '{name}' (use .txt chat exports, .csv transactions, or .jpg/.png images)")

        exhibit_id = f"EX-{len(self.exhibits) + 1:03d}"
        destination = self.root / "exhibits" / f"{exhibit_id}_{name}"
        if isinstance(source, bytes):
            destination.write_bytes(source)
            source_hash = sha256_bytes(source)
        else:
            source_hash = sha256_file(source)
            shutil.copyfile(source, destination)

        entry = self.ledger.seal_file(destination, exhibit_id, f"examiner:{examiner}", kind)
        if entry.payload["sha256"] != source_hash:
            raise IntegrityError(f"{exhibit_id}: copy does not match the source file")
        record = {
            "id": exhibit_id,
            "file_name": name,
            "kind": kind,
            "sha256": entry.payload["sha256"],
            "size_bytes": entry.payload["size_bytes"],
            "sealed_at": entry.timestamp,
            "stored_as": destination.name,
        }
        self.meta["exhibits"].append(record)
        self._save_meta()
        return record

    # analysis --------------------------------------------------------------

    def _check_seal(self, exhibit: dict) -> Path:
        path = self.exhibit_path(exhibit["id"])
        if sha256_file(path) != exhibit["sha256"]:
            raise IntegrityError(f"{exhibit['id']} changed after it was sealed. Analysis stopped.")
        return path

    def analyze(self, actor: str = "system:analyzers") -> list[Finding]:
        per_exhibit: list[tuple[dict, list[Finding]]] = []
        for exhibit in self.exhibits:
            path = self._check_seal(exhibit)
            if exhibit["kind"] == "image":
                found = analyze_image(path, exhibit["id"])
            elif exhibit["kind"] == "chat":
                _, found = analyze_chat(path, exhibit["id"])
            else:
                _, found = analyze_transactions(path, exhibit["id"])
            per_exhibit.append((exhibit, found))

        all_findings: list[Finding] = []
        for exhibit, found in per_exhibit:
            for finding in found:
                finding.id = f"F-{len(all_findings) + 1:03d}"
                all_findings.append(finding)
            self.ledger.append(
                actor,
                "ANALYZE",
                exhibit["id"],
                {
                    "tool_version": __version__,
                    "finding_ids": [f.id for f in found],
                    "findings_sha256": sha256_bytes(canonical_json([f.to_dict() for f in found])),
                },
            )
        (self.root / "findings.json").write_text(json.dumps([f.to_dict() for f in all_findings], indent=2), encoding="utf-8")
        return all_findings

    def load_findings(self) -> list[Finding]:
        path = self.root / "findings.json"
        if not path.exists():
            return []
        return [Finding(**item) for item in json.loads(path.read_text(encoding="utf-8"))]

    # human review ----------------------------------------------------------

    def review(self, finding_id: str, decision: str, examiner: str, note: str = ""):
        if decision not in REVIEW_DECISIONS:
            raise ValueError(f"decision must be one of {REVIEW_DECISIONS}")
        if finding_id not in {f.id for f in self.load_findings()}:
            raise KeyError(finding_id)
        return self.ledger.append(f"examiner:{examiner}", "REVIEW", payload={"finding_id": finding_id, "decision": decision, "note": note})

    def reviews(self) -> dict[str, dict]:
        latest: dict[str, dict] = {}
        for entry in self.ledger.entries:
            if entry.action == "REVIEW":
                latest[entry.payload["finding_id"]] = {**entry.payload, "by": entry.actor, "at": entry.timestamp}
        return latest

    # AI report -------------------------------------------------------------

    def evidence_index(self) -> EvidenceIndex:
        index = EvidenceIndex()
        for exhibit in self.exhibits:
            path = self.exhibit_path(exhibit["id"])
            if exhibit["kind"] == "chat":
                for message in parse_chat(path):
                    index.add(exhibit["id"], message.id, f"[{message.timestamp}] {message.as_text()}")
            elif exhibit["kind"] == "transactions":
                for txn in load_transactions(path):
                    index.add(exhibit["id"], txn.locator, txn.as_text())
            else:
                index.images.add(exhibit["id"])
                for tag, value in read_exif(path).items():
                    index.add(exhibit["id"], f"exif:{tag}", f"{tag}: {value}")
        for finding in self.load_findings():
            index.add(finding.exhibit_id, f"finding:{finding.id}", finding.as_text())
        return index

    def generate_report(self, call_model=None, examiner: str = "examiner") -> dict:
        from .reasoner import generate_report

        for exhibit in self.exhibits:
            self._check_seal(exhibit)
        return generate_report(self, call_model=call_model, examiner=examiner)

    def save_report(self, report: dict) -> None:
        text = json.dumps(report, indent=2, ensure_ascii=False)
        (self.root / "report.json").write_text(text, encoding="utf-8")
        self.ledger.append(
            "system:grounding",
            "REPORT",
            payload={"report_sha256": sha256_bytes(text.encode("utf-8")), "stats": report.get("stats", {})},
        )

    def load_report(self) -> dict | None:
        path = self.root / "report.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    # verification ----------------------------------------------------------

    def verify(self) -> VerifyReport:
        # Re-read the ledger from disk so edits made outside this process are caught.
        files = {exhibit["id"]: self.exhibit_path(exhibit["id"]) for exhibit in self.exhibits}
        return CustodyLedger(self.root / "ledger.jsonl").verify(files)
