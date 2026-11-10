from exhibit_a.grounding import EvidenceIndex, validate_report


def index():
    idx = EvidenceIndex()
    idx.add("EX-001", "msg-0003", "[2026-10-03T18:05:51] Arjun Rao: Keep your 4,500 and send the rest to the account no. I gave you, ending 7731.")
    idx.add("EX-002", "txn:T0028", 'T0028 2026-10-04T10:58 ACC-BIZ -> ACC-SUP 45000.00 "Invoice KF-2291"')
    idx.images.add("EX-003")
    return idx


def cite(exhibit_id, locator, quote):
    return {"exhibit_id": exhibit_id, "locator": locator, "quote": quote}


def claim(cid, statement, *citations):
    return {"id": cid, "statement": statement, "kind": "observation", "confidence": "high", "citations": list(citations), "alternatives": []}


def statuses(report):
    return {c["id"]: c["status"] for c in validate_report(report, index())["claims"]}


def test_exact_quote_is_verified_and_whitespace_case_insensitive():
    report = {"claims": [claim("C1", "Arjun asked for the rest to go to 7731.", cite("EX-001", "msg-0003", "send the rest to the   ACCOUNT no."))]}
    assert statuses(report) == {"C1": "verified"}


def test_hallucinated_citations_are_quarantined():
    report = {
        "claims": [
            claim("C1", "Misquote.", cite("EX-001", "msg-0003", "send everything to 7731")),
            claim("C2", "Invented locator.", cite("EX-001", "msg-0099", "anything")),
            claim("C3", "Invented exhibit.", cite("EX-404", "msg-0003", "send the rest")),
            claim("C4", "No citations at all."),
            claim("C5", "Empty quote.", cite("EX-002", "txn:T0028", "  ")),
            claim("C6", "One good, one bad.", cite("EX-002", "txn:T0028", "45000.00"), cite("EX-002", "txn:T9999", "1")),
        ]
    }
    assert set(statuses(report).values()) == {"unsupported"}


def test_visual_claims_need_examiner_confirmation():
    report = {"claims": [claim("C1", "The receipt total reads 45,000.00.", cite("EX-003", "image", "Total reads 45,000.00"))]}
    assert statuses(report) == {"C1": "needs_visual_check"}
    region = {"claims": [claim("C1", "Region shows digits.", cite("EX-003", "region:624,544,224,64", "digits"))]}
    assert statuses(region) == {"C1": "needs_visual_check"}


def test_verdict_language_is_out_of_scope():
    report = {"claims": [claim("C1", "Arjun is guilty of fraud.", cite("EX-002", "txn:T0028", "45000.00"))]}
    assert statuses(report) == {"C1": "out_of_scope"}


def test_summary_sentences_must_rest_on_kept_claims():
    report = {
        "summary": "The shop paid 45,000 to the supplier [C1]. The rest went to 7731 [C2]. Something uncited happened.",
        "claims": [
            claim("C1", "Payment.", cite("EX-002", "txn:T0028", "ACC-BIZ -> ACC-SUP 45000.00")),
            claim("C2", "Bad quote.", cite("EX-001", "msg-0003", "wire it all")),
        ],
    }
    summary = validate_report(report, index())["summary"]
    assert [s["kept"] for s in summary] == [True, False, False]


def test_timeline_events_are_checked_too():
    report = {"claims": [], "timeline": [{"when": "2026-10-04", "event": "Payment", "citations": [cite("EX-002", "txn:T0028", "Invoice KF-2291")]}]}
    assert validate_report(report, index())["timeline"][0]["status"] == "verified"
