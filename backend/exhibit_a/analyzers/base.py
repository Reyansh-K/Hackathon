"""Shared types for the deterministic analyzers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

CONFIDENCE_LEVELS = ("low", "medium", "high")


@dataclass
class Finding:
    """One machine-generated signal for the examiner to review.

    Findings are signals, not conclusions. Every finding carries a locator that
    points at the exact evidence it came from, and a plain-language limitation
    so the examiner knows how it can be wrong.
    """

    exhibit_id: str
    analyzer: str
    signal: str
    title: str
    detail: str
    locator: str
    confidence: str
    limitations: str = ""
    data: dict = field(default_factory=dict)
    id: str = ""

    def __post_init__(self) -> None:
        if self.confidence not in CONFIDENCE_LEVELS:
            raise ValueError(f"confidence must be one of {CONFIDENCE_LEVELS}")

    def to_dict(self) -> dict:
        return asdict(self)

    def as_text(self) -> str:
        return f"{self.title}. {self.detail}"
