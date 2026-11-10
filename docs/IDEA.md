# Exhibit A: the idea

## One line

An AI forensics copilot that seals evidence, catches forgeries and money trails, and writes reports in which every sentence is backed by an exact quote from sealed evidence.

## 30 second pitch

Digital evidence shows up in almost every investigation now, and faking it takes one phone app. AI could help examiners keep up, but an AI that invents a single detail is dangerous in a case. Exhibit A is built around one rule: **cite or stay silent**. It seals every file into a tamper-evident chain of custody, runs forensic analyzers that see edits the eye cannot, and lets Claude draft the report. Then plain code checks every quote against the sealed evidence. Anything the AI cannot prove never reaches the examiner, and even the AI's own calls are logged as part of the record.

## Who it is for

| User | Pain today | What Exhibit A gives them |
|---|---|---|
| Forensic examiners (labs, police cyber cells) | Piles of chats, photos and statements to read by hand | A cited first draft, plus signals they can confirm in minutes |
| Fraud investigators and auditors | Forged receipts and layered transfers are slow to untangle | Image forensics and money trail patterns in one place |
| Lawyers on either side | Hard to check what an analysis rests on | Every claim links to an exact quote and a verifiable seal |
| Forensics students and teachers | Few realistic practice cases, privacy limits on real ones | Case Academy: synthetic cases with planted clues and an answer key |

## Why the AI is essential, and why it is not trusted blindly

Cross-referencing two chats, a bank ledger and a pair of receipts into one timeline is slow reading work, and that is exactly what a large model is good at. A model alone cannot be trusted with evidence, and rules alone cannot explain a case. Exhibit A splits the job:

- **Deterministic analyzers** produce hard, repeatable signals (an EXIF tag, a pasted region, a transfer pattern).
- **Claude** reads everything, links it, and explains it in plain language with citations.
- **Plain code** checks every citation before a human sees the result.

## The demo story (video outline, about 3 minutes)

| Time | Beat |
|---|---|
| 0:00 | Hook: two receipts side by side. "One of these is fake. Can you tell?" |
| 0:20 | The problem in three lines: evidence volume, easy forgery, AI that guesses |
| 0:45 | Seal: drop in five exhibits, watch the hashes and the ledger appear |
| 1:15 | Analyze: the ghost heatmap lights up the two edited digits; the money graph shows the loop and the four transfers just under 10,000 |
| 1:50 | Reason: Claude's report. Hover a claim and the quoted words highlight in the evidence. Open the quarantine panel to show a claim that was removed and why. Show the "note for any AI tool" message reported instead of obeyed |
| 2:30 | Prove: flip one bit in the bank file live, verification turns red |
| 2:50 | Responsible AI, who this helps, what is next |

## How it maps to the judging criteria

The Devpost overview and the official rules list slightly different rubrics, so the project is built to score on both.

| Criterion (rules page) | Weight | What earns it |
|---|---|---|
| Innovation and Originality | 25% | Cite-or-silence grounding, the AI logged as a witness on the chain of custody, JPEG ghost heatmaps that find edits the eye cannot |
| Technical Implementation | 25% | Hash-chained ledger with Merkle inclusion proofs, three analyzers, structured outputs with vision, 31 automated tests and CI |
| Real World Impact | 20% | Evidence backlogs, cheap forgeries, small business fraud; a training mode for students |
| AI Integration and Responsible Use | 15% | AI does the reading, code does the checking; verdict blocking, prompt injection detection, synthetic data, human sign-off |
| User Experience and Presentation | 15% | Story-driven demo case, one-command setup, clear web app (in progress) |

| Criterion (overview page) | Points | Same evidence as above |
|---|---|---|
| Innovation and Creativity | 30 | Innovation row |
| Technical Execution and Complexity | 30 | Technical row |
| Design and User Experience | 20 | Web app plus demo flow |
| Presentation and Impact | 20 | Video, README, live deployment |

## Risks and how we handle them

| Risk | Plan |
|---|---|
| The live AI call fails during judging | Demo video, analyzers-only mode that needs no key, and a saved report in the demo case |
| Judges are new to forensics | Plain-language findings, each with a "how this can be wrong" note, and a story-based demo |
| Scope creep before the deadline | Roadmap with clear cut lines; the core engine is already done |
