"""Cite-or-silence: the check that sits between the AI and the examiner.

The AI may only say things it can point to. Every claim in a report must cite
an exhibit, a locator inside it (msg-0012, txn:T0047, exif:Software,
finding:F-003) and an exact quote. This module resolves each citation against
the sealed evidence and re-reads the quoted words. A claim with a missing,
invented or misquoted citation is quarantined and never reaches the report
body. Visual claims about images cannot be string-matched, so they are marked
for the examiner to confirm by eye.

The check is plain code, not another model, so it cannot be talked out of
its job.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

VERIFIED = "verified"
NEEDS_VISUAL_CHECK = "needs_visual_check"
UNSUPPORTED = "unsupported"
OUT_OF_SCOPE = "out_of_scope"

_VISUAL_LOCATOR = re.compile(r"^(image|region:\d+,\d+,\d+,\d+)$")
_CLAIM_REF = re.compile(r"\bC\d+\b")
_BRACKETS = re.compile(r"\[([^\]]+)\]")
# The AI reports evidence. It never decides guilt or intent.
_VERDICT_LANGUAGE = re.compile(
    r"\b(is|are|was|were) guilty\b|\bguilty of\b|\bcommitted (the |a |an )?(crime|fraud|offen[cs]e|theft)\b"
    r"|\bis a (criminal|thief|fraudster|liar)\b|\bdefinitely (stole|lied|embezzled)\b"
    r"|\bproves? (beyond (any|reasonable) doubt|guilt)\b",
    re.I,
)
_QUOTE_FOLD = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "₹": "INR "})


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.translate(_QUOTE_FOLD)).strip().casefold()


@dataclass
class EvidenceIndex:
    """Everything a citation is allowed to point at."""

    texts: dict[str, dict[str, str]] = field(default_factory=dict)
    images: set[str] = field(default_factory=set)

    def add(self, exhibit_id: str, locator: str, text: str) -> None:
        self.texts.setdefault(exhibit_id, {})[locator] = text

    def known_exhibit(self, exhibit_id: str) -> bool:
        return exhibit_id in self.texts or exhibit_id in self.images

    def resolve(self, exhibit_id: str, locator: str) -> str | None:
        return self.texts.get(exhibit_id, {}).get(locator)


def check_citation(citation: dict, index: EvidenceIndex) -> tuple[str, str | None]:
    exhibit_id = str(citation.get("exhibit_id", "")).strip()
    locator = str(citation.get("locator", "")).strip()
    quote = str(citation.get("quote", ""))
    if not index.known_exhibit(exhibit_id):
        return UNSUPPORTED, f"cites unknown exhibit '{exhibit_id}'"
    if exhibit_id in index.images and _VISUAL_LOCATOR.match(locator):
        return NEEDS_VISUAL_CHECK, None
    text = index.resolve(exhibit_id, locator)
    if text is None:
        return UNSUPPORTED, f"locator '{locator}' does not exist in {exhibit_id}"
    if not quote.strip():
        return UNSUPPORTED, f"no quote given for {exhibit_id} {locator}"
    if normalize(quote) not in normalize(text):
        return UNSUPPORTED, f"quote not found at {exhibit_id} {locator}"
    return VERIFIED, None


def check_cited_item(statement: str, citations: list[dict], index: EvidenceIndex) -> tuple[str, list[str]]:
    if not citations:
        return UNSUPPORTED, ["no citations"]
    statuses, problems = [], []
    for citation in citations:
        status, problem = check_citation(citation, index)
        statuses.append(status)
        if problem:
            problems.append(problem)
    if UNSUPPORTED in statuses:
        return UNSUPPORTED, problems
    if _VERDICT_LANGUAGE.search(statement):
        return OUT_OF_SCOPE, ["states guilt or intent; Exhibit A only reports what the evidence shows"]
    if NEEDS_VISUAL_CHECK in statuses:
        return NEEDS_VISUAL_CHECK, ["visual observation: examiner must confirm against the image"]
    return VERIFIED, []


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]


def validate_report(report: dict, index: EvidenceIndex) -> dict:
    """Return the report with a status on every claim, event and summary sentence."""
    claims_out = []
    kept_ids: set[str] = set()
    for claim in report.get("claims", []):
        status, problems = check_cited_item(claim.get("statement", ""), claim.get("citations", []), index)
        claims_out.append({**claim, "status": status, "problems": problems})
        if status in (VERIFIED, NEEDS_VISUAL_CHECK):
            kept_ids.add(str(claim.get("id")))

    timeline_out = []
    for event in report.get("timeline", []):
        status, problems = check_cited_item(event.get("event", ""), event.get("citations", []), index)
        timeline_out.append({**event, "status": status, "problems": problems})

    summary_out = []
    for sentence in _split_sentences(report.get("summary", "")):
        refs = {ref for group in _BRACKETS.findall(sentence) for ref in _CLAIM_REF.findall(group)}
        if not refs:
            summary_out.append({"sentence": sentence, "kept": False, "reason": "does not reference any claim"})
        elif not refs <= kept_ids:
            missing = sorted(refs - kept_ids)
            summary_out.append({"sentence": sentence, "kept": False, "reason": f"relies on quarantined or unknown claims {missing}"})
        elif _VERDICT_LANGUAGE.search(sentence):
            summary_out.append({"sentence": sentence, "kept": False, "reason": "states guilt or intent"})
        else:
            summary_out.append({"sentence": sentence, "kept": True, "reason": ""})

    def count(status: str) -> int:
        return sum(1 for claim in claims_out if claim["status"] == status)

    return {
        "summary": summary_out,
        "claims": claims_out,
        "timeline": timeline_out,
        "limitations": report.get("limitations", []),
        "open_questions": report.get("open_questions", []),
        "stats": {
            "claims_total": len(claims_out),
            VERIFIED: count(VERIFIED),
            NEEDS_VISUAL_CHECK: count(NEEDS_VISUAL_CHECK),
            UNSUPPORTED: count(UNSUPPORTED),
            OUT_OF_SCOPE: count(OUT_OF_SCOPE),
        },
    }
