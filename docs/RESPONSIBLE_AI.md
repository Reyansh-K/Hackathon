# Responsible AI in Exhibit A

Exhibit A works with evidence, where a mistake can hurt a real person. These are the rules it is built on and the code that enforces them.

## 1. Observations, not verdicts

The AI reports what the evidence shows and how strongly. It never decides guilt, intent or legal outcome.

- The system prompt says so explicitly (`backend/exhibit_a/reasoner.py`).
- `grounding.py` blocks verdict language ("is guilty", "committed fraud") and marks such claims `out_of_scope`, even when their citations are valid.

## 2. Cite or silence

Every claim must cite an exhibit, a locator inside it and an exact quote. Plain code resolves the locator and re-reads the quote before anyone sees the report. Claims with missing, invented or misquoted citations are quarantined and shown separately with the reason. Summary sentences must name the verified claims they rest on, or they are removed. Claims about images cannot be string-matched, so they are marked for the examiner to confirm by eye.

## 3. A human makes every decision

Analyzer output is a list of signals, never conclusions. Every finding carries a plain-language limitation ("Forwarding, resizing or re-saving a photo in any app also does this"). Only an examiner can confirm or reject a finding, and each decision is signed into the chain of custody with their name and time.

## 4. The AI is on the record

Each model call is logged in the ledger like any other action: the model that answered, whether a fallback model was used, the request ID, token counts and SHA-256 hashes of the exact request and response. The request is stored with images replaced by their hashes, so anyone can later check exactly what the AI was shown and what it said.

## 5. Evidence is data, never instructions

Evidence can contain text written to manipulate automated tools. Exhibit A handles this twice: the system prompt tells the model to treat evidence as data and report such text, and the chat analyzer detects instructions aimed at AI or automated reviewers with plain code, so the attempt is flagged even if a model were fooled. The demo case includes one such message on purpose.

## 6. Privacy

- All demo and training data is synthetic. No real person, business or account appears in this repository.
- No face recognition or voice identification. People are referred to only by names or account IDs that appear in the evidence.
- The analyzers run fully offline. Only the report step sends case contents to the Anthropic API. For real casework, use an organization account with suitable data handling terms, or run in analyzers-only mode.
- Uploaded file names are sanitized and IDs are validated before touching the filesystem.

## 7. Fairness

The money analyzer looks only at transaction patterns (amounts, timing, flow), never at names, places or any personal attribute. Isolation Forest results are labeled "unusual is not suspicious" and ranked as low confidence. Thresholds are configurable because what is normal differs between businesses and countries.

## 8. Known limitations

| Component | Can be wrong when |
|---|---|
| EXIF checks | Apps strip or rewrite metadata; tags can be forged |
| JPEG ghost analysis | Images were never re-saved, were screenshotted, or were heavily recompressed by a messaging app; strong local filters also create hot regions |
| Chat parsing | Exports in other languages or date formats; only the final text of edited messages survives |
| Money patterns | Refunds, family transfers and daily limits look like suspicious patterns |
| AI report | The model can miss connections; visual claims need a human check |

## 9. Honest scope

Exhibit A is a hackathon prototype, not a certified forensic tool. Its output is a starting point for a trained examiner, not evidence on its own.
