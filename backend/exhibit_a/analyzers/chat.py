"""Chat export parsing (WhatsApp style, Android and iOS formats) and signals.

Every message gets a stable ID (msg-0001, msg-0002, ...) so the AI report can
cite the exact message it relies on, and the grounding check can confirm the
quoted words really are in that message.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from .base import Finding

_ANDROID = re.compile(
    r"^(?P<date>\d{1,2}/\d{1,2}/\d{2,4}),\s(?P<time>\d{1,2}:\d{2}(?:\s?[AaPp][Mm])?)\s-\s(?P<rest>.*)$"
)
_IOS = re.compile(
    r"^\[(?P<date>\d{1,2}/\d{1,2}/\d{2,4}),\s(?P<time>\d{1,2}:\d{2}(?::\d{2})?(?:\s?[AaPp][Mm])?)\]\s(?P<rest>.*)$"
)
_DELETED = re.compile(r"^(this message was deleted|you deleted this message)\.?$", re.I)
_EDITED = "<this message was edited>"
_MEDIA = re.compile(r"<media omitted>|<attached: [^>]+>|image omitted", re.I)
_INJECTION = re.compile(
    r"(ignore (all |any |the )?(previous |prior )?(instructions|transactions|evidence)"
    r"|note (for|to) (any|the) (ai|bot|assistant|tool)"
    r"|(any|the) ai (tool|system|assistant|model) (checking|reviewing|reading)"
    r"|system prompt|report no issues|disregard (the|all|previous))",
    re.I,
)


@dataclass
class Message:
    id: str
    timestamp: str | None
    sender: str | None
    text: str
    line: int

    def as_text(self) -> str:
        who = self.sender or "SYSTEM"
        return f"{who}: {self.text}"

    def to_dict(self) -> dict:
        return asdict(self)


def _clean(line: str) -> str:
    return line.replace("‎", "").replace(" ", " ").replace(" ", " ").rstrip("\r\n")


def _to_iso(date: str, time: str, dayfirst: bool) -> str | None:
    first, second, year = date.split("/")
    day, month = (first, second) if dayfirst else (second, first)
    year_number = int(year) + 2000 if len(year) == 2 else int(year)
    time = time.strip().upper().replace(" ", "")
    for pattern in ("%I:%M:%S%p", "%I:%M%p", "%H:%M:%S", "%H:%M"):
        try:
            clock = datetime.strptime(time, pattern)
            return datetime(year_number, int(month), int(day), clock.hour, clock.minute, clock.second).isoformat()
        except ValueError:
            continue
    return None


def parse_chat(path: str | Path, dayfirst: bool = True) -> list[Message]:
    messages: list[Message] = []
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    for number, raw in enumerate(text.splitlines(), start=1):
        line = _clean(raw)
        if not line.strip():
            continue
        match = _ANDROID.match(line) or _IOS.match(line)
        if not match:
            if messages:
                messages[-1].text += "\n" + line
            continue
        rest = match.group("rest")
        sender, body = (rest.split(": ", 1) + [""])[:2] if ": " in rest else (None, rest)
        messages.append(
            Message(
                id=f"msg-{len(messages) + 1:04d}",
                timestamp=_to_iso(match.group("date"), match.group("time"), dayfirst),
                sender=sender.strip() if sender else None,
                text=body.strip(),
                line=number,
            )
        )
    return messages


def analyze_chat(path: str | Path, exhibit_id: str) -> tuple[list[Message], list[Finding]]:
    messages = parse_chat(path)
    findings: list[Finding] = []
    for message in messages:
        body = message.text.strip()
        if _DELETED.match(body):
            findings.append(
                Finding(
                    exhibit_id=exhibit_id,
                    analyzer="chat",
                    signal="deleted-message",
                    title="A message was deleted",
                    detail=f"{message.sender or 'Someone'} deleted a message at {message.timestamp}.",
                    locator=message.id,
                    confidence="low",
                    limitations="Deleting messages is common and usually innocent. The deleted content may be recoverable from the device.",
                )
            )
        if _EDITED in body.lower():
            findings.append(
                Finding(
                    exhibit_id=exhibit_id,
                    analyzer="chat",
                    signal="edited-message",
                    title="A message was edited after sending",
                    detail=f"{message.sender or 'Someone'} edited a message sent at {message.timestamp}.",
                    locator=message.id,
                    confidence="low",
                    limitations="The export only keeps the final text, not the original.",
                )
            )
        if message.sender and _INJECTION.search(body):
            findings.append(
                Finding(
                    exhibit_id=exhibit_id,
                    analyzer="chat",
                    signal="instruction-to-automated-reviewer",
                    title="Message tries to instruct an automated reviewer",
                    detail=(
                        f"{message.sender} wrote text aimed at AI or automated tools: \"{body[:160]}\". "
                        "Exhibit A treats evidence as data and never follows instructions found inside it."
                    ),
                    locator=message.id,
                    confidence="medium",
                    limitations="Could be a joke or sarcasm. It is reported because it targets the analysis itself.",
                )
            )
    return messages, findings


def has_media_reference(message: Message) -> bool:
    return bool(_MEDIA.search(message.text))
