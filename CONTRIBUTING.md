# Contributing to Exhibit A

SLAY HACKS 2026 entry (online, Devpost: slayy-hacks.devpost.com). Build window Nov 7 to Dec 7, 2026; target submission Dec 6. Judging Dec 8 to 14; winners Dec 16.

Rules-page rubric: Innovation 25, Technical 25, Real World Impact 20, AI Integration and Responsible Use 15, UX and Presentation 15. The overview page lists a 30/30/20/20 version. See docs/IDEA.md.

## What it is

AI digital forensics copilot: seal evidence (hash-chained ledger), run analyzers (image, chat, money), have the AI draft a cited report, quarantine anything that fails the cite-or-silence check, and let a human review. Demo data is a synthetic case ("The Case of the Missing Invoice").

## Stack

- backend/: Python 3.11+, FastAPI, Pillow, NumPy, NetworkX, scikit-learn, Anthropic SDK.
- frontend/: not started. The visual style has not been chosen yet.

## Setup

```bash
cd backend
pip install -e ".[dev]"
pytest
exhibit-a demo          # add --ai with ANTHROPIC_API_KEY set
exhibit-a serve         # http://127.0.0.1:8000/docs
```

## Ground rules

- Style: no em dashes anywhere (code comments, docs, UI copy, commit messages).
- Demo and test data stays synthetic (backend/exhibit_a/synth.py). Never add real personal data.
- Every AI claim goes through grounding.py. Never bypass or weaken it to make a demo look better.
- ledger.jsonl is append-only. Never rewrite past entries.
- Keep the tests green (`pytest`) and CI passing.
- This repo is public: keep private planning notes out of it.
