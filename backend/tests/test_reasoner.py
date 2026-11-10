import json

import pytest

from exhibit_a.reasoner import FALLBACK_BETA, MODEL, ModelReply, ReasonerError, build_request


def fake_report(case):
    chat = next(e["id"] for e in case.exhibits if e["file_name"] == "chat_arjun_kabir.txt")
    bank = next(e["id"] for e in case.exhibits if e["file_name"] == "bank_transactions.csv")
    image = next(e["id"] for e in case.exhibits if e["file_name"] == "receipt_submitted.jpg")
    return {
        "summary": "Arjun asked for the excess to be sent to 7731 [C1]. The shop paid 45,000 [C2]. He is guilty [C4].",
        "claims": [
            {"id": "C1", "statement": "Arjun told Kabir to send the rest to the account ending 7731.", "kind": "observation", "confidence": "high",
             "citations": [{"exhibit_id": chat, "locator": "msg-0003", "quote": "send the rest to the account no. I gave you, ending 7731"}], "alternatives": []},
            {"id": "C2", "statement": "The shop paid 45,000 for invoice KF-2291.", "kind": "observation", "confidence": "high",
             "citations": [{"exhibit_id": bank, "locator": "txn:T0028", "quote": "45000.00"}], "alternatives": []},
            {"id": "C3", "statement": "The submitted receipt shows 45,000.00.", "kind": "observation", "confidence": "medium",
             "citations": [{"exhibit_id": image, "locator": "image", "quote": "TOTAL (INR) 45,000.00"}], "alternatives": []},
            {"id": "C4", "statement": "Arjun is guilty of fraud.", "kind": "inference", "confidence": "low",
             "citations": [{"exhibit_id": bank, "locator": "txn:T0028", "quote": "45000.00"}], "alternatives": []},
            {"id": "C5", "statement": "Kabir admitted the scheme.", "kind": "observation", "confidence": "high",
             "citations": [{"exhibit_id": chat, "locator": "msg-0006", "quote": "I admit everything"}], "alternatives": []},
        ],
        "timeline": [],
        "limitations": ["Synthetic case."],
        "open_questions": ["Who owns ACC-7731?"],
    }


def test_request_uses_schema_fallbacks_and_images(demo_case):
    request = build_request(demo_case)
    assert request["model"] == MODEL
    assert request["betas"] == [FALLBACK_BETA] and request["fallbacks"] == "default"
    assert request["output_config"]["format"]["type"] == "json_schema"
    blocks = request["messages"][0]["content"]
    assert sum(1 for b in blocks if b["type"] == "image") == 2
    packet = blocks[-1]["text"]
    assert "[msg-0003]" in packet and "[txn:T0028]" in packet and "finding:F-" in packet


def test_report_is_grounded_and_ai_call_is_on_the_record(fresh_demo_case):
    case = fresh_demo_case
    seen = {}

    def fake_call(request):
        seen["request"] = request
        return ModelReply(text=json.dumps(fake_report(case)), stop_reason="end_turn", model=MODEL, request_id="req_test", input_tokens=10, output_tokens=20)

    report = case.generate_report(call_model=fake_call)
    status = {c["id"]: c["status"] for c in report["claims"]}
    assert status == {"C1": "verified", "C2": "verified", "C3": "needs_visual_check", "C4": "out_of_scope", "C5": "unsupported"}
    assert [s["kept"] for s in report["summary"]] == [True, True, False]

    actions = [e.action for e in case.ledger.entries]
    assert actions[-2:] == ["AI_CALL", "REPORT"]
    ai_entry = case.ledger.entries[-2]
    assert ai_entry.actor == f"ai:{MODEL}" and ai_entry.payload["request_id"] == "req_test"
    logged = (case.root / "ai_calls" / "001_request.json").read_text()
    assert '"type": "sha256"' in logged and "base64" not in logged
    assert case.verify().ok


def test_refusal_is_reported_and_still_logged(fresh_demo_case):
    case = fresh_demo_case

    def refusing_call(request):
        return ModelReply(text="", stop_reason="refusal", model=MODEL, refusal_category="cyber")

    with pytest.raises(ReasonerError, match="declined"):
        case.generate_report(call_model=refusing_call)
    assert case.ledger.entries[-1].action == "AI_CALL"
    assert case.load_report() is None


def test_tampered_exhibit_blocks_the_report(fresh_demo_case):
    case = fresh_demo_case
    path = case.exhibit_path("EX-005")
    path.write_text(path.read_text().replace("45000.0", "4500.0"))
    from exhibit_a.case import IntegrityError

    with pytest.raises(IntegrityError):
        case.generate_report(call_model=lambda request: None)
    assert not case.verify().ok
