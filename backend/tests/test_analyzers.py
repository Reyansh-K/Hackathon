from exhibit_a.analyzers import parse_chat


def test_parses_android_and_ios_exports(tmp_path):
    android = tmp_path / "a.txt"
    android.write_text("04/10/2026, 09:15 - Arjun Rao: Paid.\ncontinued line\n04/10/2026, 09:16 - System notice without sender\n")
    ios = tmp_path / "i.txt"
    ios.write_text("[05/10/26, 10:14:27 AM] Kabir Fabrics: Done.\n[05/10/26, 7:30:03 PM] Arjun Rao: Sent.\n")
    a = parse_chat(android)
    assert a[0].timestamp == "2026-10-04T09:15:00" and a[0].sender == "Arjun Rao"
    assert a[0].text == "Paid.\ncontinued line"
    assert a[1].sender is None
    i = parse_chat(ios)
    assert [m.timestamp for m in i] == ["2026-10-05T10:14:27", "2026-10-05T19:30:03"]
    assert [m.id for m in i] == ["msg-0001", "msg-0002"]


def signals_for(case, file_name):
    exhibit_id = next(e["id"] for e in case.exhibits if e["file_name"] == file_name)
    return {f.signal for f in case.load_findings() if f.exhibit_id == exhibit_id}


def test_every_planted_signal_is_found(demo_case):
    found = {f.signal for f in demo_case.load_findings()}
    expected = {
        "editing-software",
        "modified-after-capture",
        "double-compression",
        "compression-inconsistency",
        "unusual-amount-for-payee",
        "pass-through",
        "structuring",
        "round-trip-cycle",
        "instruction-to-automated-reviewer",
        "deleted-message",
    }
    assert expected <= found


def test_genuine_receipt_is_clean(demo_case):
    assert signals_for(demo_case, "receipt_from_supplier.jpg") == set()


def test_forged_regions_cover_the_edited_amounts(demo_case):
    regions = [f.data for f in demo_case.load_findings() if f.signal == "compression-inconsistency"]
    assert len(regions) == 2
    for region, (x, y) in zip(sorted(regions, key=lambda r: r["y"]), [(640, 560), (640, 660)]):
        assert region["x"] <= x < region["x"] + region["w"]
        assert region["y"] <= y < region["y"] + region["h"]


def test_structuring_names_the_four_transfers(demo_case):
    finding = next(f for f in demo_case.load_findings() if f.signal == "structuring")
    assert len(finding.data["txn_ids"]) == 4
    assert "ACC-7731 -> ACC-ARJ" in finding.detail
