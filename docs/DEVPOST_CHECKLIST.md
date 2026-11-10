# Devpost submission checklist

Deadline: **December 7, 2026**, at the time shown on the Devpost submission page. Aim to submit on **December 6**.

## Required by the rules and the requirements page

- [ ] Project name and overview
- [ ] Problem and solution: who it is for and how it helps
- [ ] AI implementation: models, APIs and frameworks, and what each one does
- [ ] Working demo link with access instructions (or a demo video if a live demo is not possible)
- [ ] Screenshots of the interface and features
- [ ] Source code link with basic documentation and setup instructions (this repo; it must stay public)
- [ ] Demo video, about 2 to 4 minutes
- [ ] Every team member listed and credited, and everyone agrees to the submission
- [ ] Limitations and external dependencies disclosed (rule 7)
- [ ] Only one submission for the project
- [ ] No API keys, passwords or personal data anywhere public (rule 13); check the repo and the video
- [ ] Open every link in a private browser window before submitting

## Draft write-up (edit into your own words)

**Name:** Exhibit A

**Tagline:** The AI forensics copilot that can prove every word it says.

**Inspiration**
Write the real reason this team picked the problem. A true, specific reason beats a polished generic one.

**What it does**
Exhibit A helps a digital forensics examiner work through chats, photos and bank records. It seals every file into a tamper-evident chain of custody, runs analyzers that catch edited images and suspicious money trails, and uses Claude to draft a case report in which every claim cites an exact quote from sealed evidence. Plain code checks each quote before anyone reads the report, quarantines anything the AI cannot back up, and blocks verdict language. Examiners confirm or reject every finding, and each decision, including each AI call, is written to the ledger. One flipped bit in any file is caught on verification.

**How we built it**
Python and FastAPI on the backend. Pillow and NumPy for EXIF checks and JPEG ghost analysis. NetworkX and scikit-learn for the money trail (cycle search, pass-through and structuring rules, Isolation Forest). Claude Opus 5.5 through the Anthropic Python SDK for the case report, using vision, structured outputs with a JSON schema, streaming and server-side refusal fallback. A SHA-256 hash chain with an RFC 6962 style Merkle tree for the chain of custody. Synthetic case generation so no real personal data is used.

**Challenges we ran into**
Our first image check was classic Error Level Analysis, and it flagged the genuine receipt just as much as the fake one, because ELA reacts to sharp text and edges. We switched to JPEG ghost analysis and divided by a low quality reference to cancel out ordinary content. After that the genuine receipt came back clean and the two edited amounts lit up exactly. Making the AI cite precisely enough for code to verify, without making the report unreadable, also took several rounds of prompt and schema design.

**Accomplishments that we're proud of**
The edited receipt looks perfect to the eye and the heatmap still finds both changed numbers. Flipping a single bit in an exhibit is caught. The AI cannot get an invented quote past the grounding check. 31 automated tests run on every push.

**What we learned**
(Fill in.)

**What's next**
See docs/ROADMAP.md: Case Academy for forensics students, public timestamp anchoring for case fingerprints, and more evidence formats.

**Built with**
python, fastapi, anthropic, claude, pillow, numpy, networkx, scikit-learn, pytest, plus the frontend stack once chosen.

## Screenshot list

1. Case dashboard with all five exhibits sealed and verification green
2. Receipt next to its ghost heatmap with the two regions boxed
3. Money graph with the loop and the four transfers highlighted
4. Report with a claim hovered and its quote highlighted in the evidence
5. Quarantine panel showing a removed claim and the reason
6. Verification turning red after one bit is flipped
