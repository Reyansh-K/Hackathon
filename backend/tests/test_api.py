import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    import exhibit_a.api as api

    monkeypatch.setattr(api, "DATA_DIR", tmp_path / "cases")
    return TestClient(api.app)


def test_demo_flow(client):
    case = client.post("/api/demo").json()
    assert case["custody"]["ok"] and len(case["exhibits"]) == 5 and case["findings"]
    case_id = case["case_id"]
    finding_id = case["findings"][0]["id"]
    reviewed = client.post(f"/api/cases/{case_id}/findings/{finding_id}/review", json={"decision": "confirmed", "examiner": "judge"}).json()
    assert reviewed["reviews"][finding_id]["decision"] == "confirmed"
    custody = client.get(f"/api/cases/{case_id}/custody").json()
    assert custody["verify"]["ok"] and custody["entries"][-1]["action"] == "REVIEW"
    heat = client.get(f"/api/cases/{case_id}/exhibits/EX-004/heatmap")
    assert heat.status_code == 200 and heat.headers["content-type"] == "image/png"


def test_upload_and_bad_input(client):
    case_id = client.post("/api/cases", json={"title": "Upload test"}).json()["case_id"]
    ok = client.post(f"/api/cases/{case_id}/exhibits", files={"file": ("../../etc/chat.txt", b"04/10/2026, 09:15 - A: hi\n")})
    assert ok.status_code == 200 and ok.json()["stored_as"] == "EX-001_chat.txt"
    assert client.post(f"/api/cases/{case_id}/exhibits", files={"file": ("x.exe", b"MZ")}).status_code == 400
    assert client.get("/api/cases/..%2F..%2Fetc").status_code == 404
    assert client.get("/api/cases/CASE-zzzzzzzz").status_code == 404
    assert client.post(f"/api/cases/{case_id}/report").status_code == 400
