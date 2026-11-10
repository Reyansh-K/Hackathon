"""HTTP API for the Exhibit A web app.

Run:  uvicorn exhibit_a.api:app --reload
Data lives in EXHIBIT_A_DATA (default ./data/cases).
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import __version__
from .analyzers import save_heatmap
from .case import CASE_ID, EXHIBIT_ID, FINDING_ID, REVIEW_DECISIONS, Case, IntegrityError
from .reasoner import ReasonerError
from .synth import build_demo_case

DATA_DIR = Path(os.environ.get("EXHIBIT_A_DATA", "data/cases"))
MAX_UPLOAD_BYTES = 25 * 1024 * 1024

app = FastAPI(title="Exhibit A", version=__version__)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("EXHIBIT_A_CORS", "http://localhost:5173,http://127.0.0.1:5173").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


class NewCase(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    examiner: str = Field(default="examiner", min_length=1, max_length=60)


class Review(BaseModel):
    decision: str
    examiner: str = Field(min_length=1, max_length=60)
    note: str = Field(default="", max_length=500)


class ReportRequest(BaseModel):
    examiner: str = Field(default="examiner", min_length=1, max_length=60)


def _open(case_id: str) -> Case:
    # IDs are validated before they touch the filesystem (no path traversal).
    if not CASE_ID.match(case_id) or not (DATA_DIR / case_id / "case.json").exists():
        raise HTTPException(404, "case not found")
    return Case(DATA_DIR / case_id)


def _summary(case: Case) -> dict:
    verify = case.verify()
    return {
        "case_id": case.case_id,
        "title": case.title,
        "created_at": case.meta["created_at"],
        "exhibits": case.exhibits,
        "findings": [f.to_dict() for f in case.load_findings()],
        "reviews": case.reviews(),
        "report": case.load_report(),
        "custody": {"ok": verify.ok, "problems": verify.problems, "head": case.ledger.head, "merkle_root": case.ledger.merkle_root()},
    }


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "version": __version__, "ai_enabled": bool(os.environ.get("ANTHROPIC_API_KEY"))}


@app.get("/api/cases")
def list_cases() -> list[dict]:
    if not DATA_DIR.exists():
        return []
    cases = []
    for folder in sorted(DATA_DIR.iterdir()):
        if CASE_ID.match(folder.name) and (folder / "case.json").exists():
            case = Case(folder)
            cases.append({"case_id": case.case_id, "title": case.title, "exhibits": len(case.exhibits)})
    return cases


@app.post("/api/cases")
def create_case(body: NewCase) -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return _summary(Case.create(DATA_DIR, body.title, examiner=body.examiner))


@app.post("/api/demo")
def create_demo_case() -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return _summary(build_demo_case(DATA_DIR))


@app.get("/api/cases/{case_id}")
def get_case(case_id: str) -> dict:
    return _summary(_open(case_id))


@app.post("/api/cases/{case_id}/exhibits")
async def upload_exhibit(case_id: str, file: UploadFile = File(...), examiner: str = "examiner") -> dict:
    case = _open(case_id)
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "file is larger than 25 MB")
    try:
        return case.add_exhibit(data, filename=file.filename or "upload", examiner=examiner[:60])
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


@app.get("/api/cases/{case_id}/exhibits/{exhibit_id}/file")
def exhibit_file(case_id: str, exhibit_id: str) -> FileResponse:
    case = _open(case_id)
    if not EXHIBIT_ID.match(exhibit_id):
        raise HTTPException(404, "exhibit not found")
    try:
        return FileResponse(case.exhibit_path(exhibit_id))
    except KeyError as error:
        raise HTTPException(404, "exhibit not found") from error


@app.get("/api/cases/{case_id}/exhibits/{exhibit_id}/heatmap")
def exhibit_heatmap(case_id: str, exhibit_id: str) -> FileResponse:
    case = _open(case_id)
    if not EXHIBIT_ID.match(exhibit_id):
        raise HTTPException(404, "exhibit not found")
    try:
        exhibit = case.exhibit(exhibit_id)
    except KeyError as error:
        raise HTTPException(404, "exhibit not found") from error
    if exhibit["kind"] != "image":
        raise HTTPException(400, "heatmaps exist for image exhibits only")
    out = case.root / "derived" / f"{exhibit_id}_heatmap.png"
    out.parent.mkdir(exist_ok=True)
    if not out.exists() and save_heatmap(case.exhibit_path(exhibit_id), out) is None:
        raise HTTPException(400, "heatmaps need a JPEG image")
    return FileResponse(out, media_type="image/png")


@app.post("/api/cases/{case_id}/analyze")
def analyze(case_id: str) -> dict:
    case = _open(case_id)
    try:
        case.analyze()
    except IntegrityError as error:
        raise HTTPException(409, str(error)) from error
    return _summary(case)


@app.post("/api/cases/{case_id}/findings/{finding_id}/review")
def review(case_id: str, finding_id: str, body: Review) -> dict:
    case = _open(case_id)
    if not FINDING_ID.match(finding_id):
        raise HTTPException(404, "finding not found")
    if body.decision not in REVIEW_DECISIONS:
        raise HTTPException(400, f"decision must be one of {REVIEW_DECISIONS}")
    try:
        case.review(finding_id, body.decision, body.examiner, body.note)
    except KeyError as error:
        raise HTTPException(404, "finding not found") from error
    return _summary(case)


@app.post("/api/cases/{case_id}/report")
def report(case_id: str, body: ReportRequest | None = None) -> dict:
    case = _open(case_id)
    if not case.load_findings():
        raise HTTPException(400, "run the analyzers first")
    try:
        case.generate_report(examiner=(body.examiner if body else "examiner"))
    except IntegrityError as error:
        raise HTTPException(409, str(error)) from error
    except ReasonerError as error:
        raise HTTPException(502, str(error)) from error
    return _summary(case)


@app.get("/api/cases/{case_id}/custody")
def custody(case_id: str) -> dict:
    case = _open(case_id)
    verify = case.verify()
    return {
        "verify": verify.to_dict(),
        "head": case.ledger.head,
        "merkle_root": case.ledger.merkle_root(),
        "entries": [entry.__dict__ for entry in case.ledger.entries],
    }
