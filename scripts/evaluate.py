"""Evaluate explicitly synthetic verifier inputs. Never a model-accuracy benchmark."""

import copy
import json
from pathlib import Path

from linescope.models import Document, Extraction, Review
from linescope.verifier import verify

ROOT = Path(__file__).resolve().parents[1]


def cases():
    source = json.loads((ROOT / "src/linescope/demo.json").read_text(encoding="utf-8"))
    approved = Review(coverage_confirmed=True, simple_pricing_confirmed=True,
                      reviewer="synthetic-case-author", reason="Controlled fixture; not a user review")
    yield "clean", copy.deepcopy(source), approved, "CHECKS_PASSED", None
    yield "unreviewed", copy.deepcopy(source), Review(), "NEEDS_REVIEW", "COVERAGE_UNCONFIRMED"
    wrong_total = copy.deepcopy(source)
    wrong_total["document"]["pages"][0]["text"] = wrong_total["document"]["pages"][0]["text"].replace("4500.00", "4200.00")
    wrong_total["extraction"]["total"] = {"value": "4200.00", "evidence": {"page": 1, "quote": "合计 4200.00"}}
    yield "source-total-mismatch", wrong_total, approved, "BLOCKED", "TOTAL_MISMATCH"
    cross = copy.deepcopy(source)
    cross["extraction"]["items"][0]["quantity"] = {"value": "2", "evidence": {"page": 1, "quote": "数量 2"}}
    yield "same-page-wrong-item", cross, approved, "BLOCKED", "OUTSIDE_ITEM_SCOPE"
    partial = copy.deepcopy(source)
    partial["extraction"]["items"][0]["unit_price"] = {"value": "1200", "evidence": {"page": 1, "quote": "单价 1200"}}
    yield "partial-number", partial, approved, "BLOCKED", "PARTIAL_NUMBER"
    missing = copy.deepcopy(source)
    missing["extraction"]["items"][0]["amount"] = {"value": None, "evidence": None}
    yield "missing-amount", missing, approved, "NEEDS_REVIEW", "MISSING_VALUE"
    repeated = copy.deepcopy(source)
    repeated["document"]["pages"][0]["text"] += "\n合计 4500.00"
    yield "ambiguous-total", repeated, approved, "NEEDS_REVIEW", "AMBIGUOUS_EVIDENCE"
    invented = copy.deepcopy(source)
    invented["extraction"]["items"][0]["unit_price"]["value"] = "1300.00"
    yield "invented-value", invented, approved, "BLOCKED", "VALUE_NOT_SUPPORTED"


def main():
    rows = []
    for name, case, review, expected, code in cases():
        report = verify(Document.model_validate(case["document"]), Extraction.model_validate(case["extraction"]), review)
        actual_codes = sorted({f.code for f in report.findings})
        rows.append(dict(case=name, expected=expected, actual=report.verdict, expected_code=code,
                         codes=actual_codes, matched=report.verdict == expected and (code is None or code in actual_codes)))
    output = dict(dataset="8 synthetic verifier cases, manually authored candidates; no model calls",
                  verifier_version="0.1.0", matched=sum(row["matched"] for row in rows), total=len(rows),
                  cases=rows, limitation="Outcome agreement on known synthetic cases is not extraction accuracy or real-world generalization.")
    target = ROOT / "docs/evaluation.json"
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    raise SystemExit(0 if output["matched"] == output["total"] else 1)


if __name__ == "__main__":
    main()
