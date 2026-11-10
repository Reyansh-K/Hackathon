# Roadmap

Build window: November 7 to December 7, 2026. Target submission: **December 6** (one day of buffer). Judging runs December 8 to 14, winners December 16.

## Week 1: November 10 to 16 (core engine)

- [x] Chain of custody: SHA-256 seals, hash-chained ledger, Merkle root and inclusion proofs
- [x] Image analyzer: EXIF checks and JPEG ghost analysis with heatmaps
- [x] Chat analyzer: Android and iOS WhatsApp exports, deleted and edited messages, instructions aimed at AI
- [x] Money analyzer: loops, pass-through accounts, structuring, unusual amounts, Isolation Forest ranking
- [x] Cite-or-silence grounding check
- [x] Claude case reasoner (structured outputs, vision, refusal fallback, AI call logged to the ledger)
- [x] Synthetic demo case with an answer key, FastAPI server, CLI, 31 tests, CI
- [ ] Run the live Claude report on the demo case with an API key and tune the prompt
- [ ] Pick the UI style and set up the frontend

## Week 2: November 17 to 23 (web app)

- [ ] Case dashboard: exhibits, seals, finding counts, verification status
- [ ] Evidence viewer: chat view, ledger table, image view with heatmap overlay and region boxes
- [ ] Findings review queue: confirm, reject or follow up, each signed into the ledger
- [ ] Custody timeline with live verify, plus a browser-side verify page (Web Crypto SHA-256) that needs no server

## Week 3: November 24 to 30 (report and academy)

- [ ] Report view: hover a claim to highlight the quoted words in the evidence, a quarantine panel, examiner checkboxes for visual claims
- [ ] Print and PDF export of the report with the hash table
- [ ] Case Academy: students get a synthetic case, submit findings, and are scored against the answer key
- [ ] Money graph visualization (accounts as nodes, flagged paths highlighted)

## Week 4: December 1 to 7 (ship)

- [ ] Deploy the API and the web app, with analyzers-only mode when no key is set
- [ ] Record the 2 to 4 minute demo video (see docs/IDEA.md for the outline)
- [ ] Screenshots, Devpost write-up (see docs/DEVPOST_CHECKLIST.md)
- [ ] Final test run, check every link in a private browser window, submit by December 6

## Stretch goals (only if ahead of schedule)

- Anchor each case's Merkle root to a public timestamp service such as OpenTimestamps, so the case fingerprint can be proven to have existed at a given time
- Export the hash table in the shape electronic evidence certificates ask for (for example India's Bharatiya Sakshya Adhiniyam 2023, Section 63, or US Federal Rule of Evidence 902(14)); confirm the exact format with a legal expert first
- More inputs: Telegram JSON exports, PDF invoices, bank statement PDFs
- Learned graph scoring for transaction networks once labeled data exists

## Cut lines if time runs short

Keep: seal, analyze, report with citations, verify, demo video. Cut first: PDF export, Case Academy scoring, graph visualization.
