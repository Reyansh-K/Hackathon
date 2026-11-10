"""Command line for demos and judges.

  exhibit-a demo [--dir DIR] [--ai]   build the synthetic case, analyze it, verify it
  exhibit-a verify CASE_DIR           re-check every seal and every ledger link
  exhibit-a tamper CASE_DIR EX-004    flip one byte in an exhibit, then verify (demo only)
  exhibit-a report CASE_DIR           ask Claude for a grounded report (needs ANTHROPIC_API_KEY)
  exhibit-a serve                     start the API on http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .case import Case
from .reasoner import ReasonerError
from .synth import build_demo_case


def _print_findings(case: Case) -> None:
    for finding in case.load_findings():
        print(f"  {finding.id}  {finding.exhibit_id}  [{finding.confidence:<6}] {finding.signal:<34} {finding.locator}")


def _print_verify(case: Case) -> int:
    result = case.verify()
    if result.ok:
        print(f"VERIFIED: {result.entries_checked} ledger entries and {result.exhibits_checked} sealed exhibits intact.")
        print(f"  chain head  {case.ledger.head}")
        print(f"  merkle root {case.ledger.merkle_root()}")
        return 0
    print("TAMPERING DETECTED:")
    for problem in result.problems:
        print(f"  - {problem}")
    return 1


def _print_report(report: dict) -> None:
    stats = report["stats"]
    print(
        f"\nReport: {stats['verified']} verified, {stats['needs_visual_check']} need a visual check, "
        f"{stats['unsupported']} quarantined (bad citations), {stats['out_of_scope']} out of scope."
    )
    for sentence in report["summary"]:
        if sentence["kept"]:
            print(f"  {sentence['sentence']}")
    for claim in report["claims"]:
        marker = {"verified": "OK ", "needs_visual_check": "EYE", "unsupported": "XX ", "out_of_scope": "-- "}[claim["status"]]
        print(f"  [{marker}] {claim['id']} ({claim['confidence']}) {claim['statement']}")
        for problem in claim["problems"]:
            print(f"         {problem}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="exhibit-a", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo")
    demo.add_argument("--dir", default="data/cases")
    demo.add_argument("--ai", action="store_true", help="also generate the Claude report")
    verify = sub.add_parser("verify")
    verify.add_argument("case_dir")
    tamper = sub.add_parser("tamper")
    tamper.add_argument("case_dir")
    tamper.add_argument("exhibit_id")
    report = sub.add_parser("report")
    report.add_argument("case_dir")
    sub.add_parser("serve")
    args = parser.parse_args(argv)

    if args.command == "demo":
        case = build_demo_case(args.dir)
        print(f"Opened {case.case_id}: {case.title}")
        print(f"Sealed {len(case.exhibits)} exhibits. Analyzer findings:")
        _print_findings(case)
        if args.ai:
            try:
                _print_report(case.generate_report())
            except ReasonerError as error:
                print(f"AI report skipped: {error}")
        code = _print_verify(case)
        print(f"\nCase folder: {case.root}")
        return code

    if args.command == "verify":
        return _print_verify(Case(args.case_dir))

    if args.command == "tamper":
        case = Case(args.case_dir)
        path = case.exhibit_path(args.exhibit_id)
        data = bytearray(path.read_bytes())
        data[len(data) // 2] ^= 0x01
        path.write_bytes(bytes(data))
        print(f"Flipped one bit in the middle of {path.name}.")
        return _print_verify(case)

    if args.command == "report":
        case = Case(args.case_dir)
        try:
            _print_report(case.generate_report())
        except ReasonerError as error:
            print(f"Report failed: {error}")
            return 1
        return 0

    if args.command == "serve":
        import uvicorn

        uvicorn.run("exhibit_a.api:app", host="127.0.0.1", port=8000)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
