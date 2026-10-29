import copy

import pytest
from pydantic import ValidationError

from linescope.models import Document, Extraction, Review
from linescope.verifier import verify


def codes(report):
    return {f.code for f in report.findings}


def test_happy_path_has_resolvable_anchors(parsed, checked):
    document, extraction = parsed
    report = verify(document, extraction, checked)
    assert report.verdict == "CHECKS_PASSED"
    assert report.calculations[-1]["expected"] == "4500.00"
    for path, anchor in report.anchors.items():
        page = next(p for p in document.pages if p.number == anchor["page"])
        assert page.text[anchor["start"]:anchor["end"]]
    assert len(report.document_sha256) == 64


def test_human_confirmation_is_not_inferred(parsed):
    report = verify(*parsed, Review())
    assert report.verdict == "NEEDS_REVIEW"
    assert {"COVERAGE_UNCONFIRMED", "PRICING_SCOPE_UNCONFIRMED"} <= codes(report)


def test_grounded_source_can_still_have_wrong_total(case, checked):
    case["document"]["pages"][0]["text"] = case["document"]["pages"][0]["text"].replace("4500.00", "4200.00")
    case["extraction"]["total"] = {"value": "4200.00", "evidence": {"page": 1, "quote": "合计 4200.00"}}
    report = verify(Document.model_validate(case["document"]), Extraction.model_validate(case["extraction"]), checked)
    assert report.verdict == "BLOCKED"
    assert "TOTAL_MISMATCH" in codes(report)
    assert report.calculations[-1]["delta"] == "-300.00"


def test_same_page_other_row_is_not_valid_evidence(case, checked):
    case["extraction"]["items"][0]["quantity"] = {
        "value": "2", "evidence": {"page": 1, "quote": "数量 2"}}
    report = verify(Document.model_validate(case["document"]), Extraction.model_validate(case["extraction"]), checked)
    assert "OUTSIDE_ITEM_SCOPE" in codes(report)
    assert report.verdict == "BLOCKED"


@pytest.mark.parametrize("mutation,expected", [
    (lambda x: x["items"][0]["quantity"].update(value=None), "MISSING_VALUE"),
    (lambda x: x["items"][0]["quantity"].update(evidence=None), "MISSING_EVIDENCE"),
    (lambda x: x["total"]["evidence"].update(page=2), "PAGE_NOT_FOUND"),
    (lambda x: x["total"]["evidence"].update(quote="合计 4501.00"), "QUOTE_NOT_FOUND"),
    (lambda x: x["total"].update(value="4200.00"), "VALUE_NOT_SUPPORTED"),
    (lambda x: x["total"]["evidence"].update(quote="数量 3 | 单价 1200.00"), "AMBIGUOUS_NUMBER"),
    (lambda x: x["items"][0]["name"].update(value="不存在的设备"), "VALUE_NOT_SUPPORTED"),
    (lambda x: x.update(notes=["possible discount"]), "EXTRACTION_NOTES"),
])
def test_untrusted_candidates_are_not_cleared(case, checked, mutation, expected):
    mutation(case["extraction"])
    report = verify(Document.model_validate(case["document"]), Extraction.model_validate(case["extraction"]), checked)
    assert expected in codes(report)
    assert report.verdict != "CHECKS_PASSED"


def test_repeated_evidence_needs_context(case, checked):
    case["document"]["pages"][0]["text"] += "\n合计 4500.00"
    report = verify(Document.model_validate(case["document"]), Extraction.model_validate(case["extraction"]), checked)
    assert "AMBIGUOUS_EVIDENCE" in codes(report)
    assert report.verdict == "NEEDS_REVIEW"


def test_overlapping_item_scope_is_blocked(case, checked):
    duplicate = copy.deepcopy(case["extraction"]["items"][0])
    duplicate["item_id"] = "duplicate"
    case["extraction"]["items"].append(duplicate)
    report = verify(Document.model_validate(case["document"]), Extraction.model_validate(case["extraction"]), checked)
    assert "OVERLAPPING_ITEMS" in codes(report)


@pytest.mark.parametrize("value", [1.2, 2, "NaN", "Infinity", "-1", "1e4", "1000000000", "1.00001"])
def test_unsafe_decimal_inputs_rejected(case, value):
    case["extraction"]["total"]["value"] = value
    with pytest.raises(ValidationError):
        Extraction.model_validate(case["extraction"])


def test_decimal_arithmetic_is_exact(checked):
    def number(value, quote):
        return {"value": value, "evidence": {"page": 1, "quote": quote}}
    document = Document(pages=[{"number": 1, "text": "币种 CNY\n线缆 数量 3 单价 0.10 金额 0.30\n合计 0.30"}])
    extraction = Extraction.model_validate({
        "currency": {"value": "CNY", "evidence": {"page": 1, "quote": "币种 CNY"}},
        "items": [{"item_id": "1", "scope": {"page": 1, "quote": "线缆 数量 3 单价 0.10 金额 0.30"},
                   "name": {"value": "线缆", "evidence": {"page": 1, "quote": "线缆"}},
                   "quantity": number("3", "数量 3"), "unit_price": number("0.10", "单价 0.10"),
                   "amount": number("0.30", "金额 0.30")}],
        "total": number("0.30", "合计 0.30"), "notes": []})
    report = verify(document, extraction, checked)
    assert report.verdict == "CHECKS_PASSED"


def test_duplicate_page_ids_rejected():
    with pytest.raises(ValidationError):
        Document(pages=[{"number": 1, "text": "a"}, {"number": 1, "text": "b"}])


def test_cannot_confirm_without_note():
    with pytest.raises(ValidationError):
        Review(coverage_confirmed=True)


def test_partial_number_substring_is_rejected(case, checked):
    case["extraction"]["items"][0]["unit_price"] = {
        "value": "1200", "evidence": {"page": 1, "quote": "单价 1200"}}
    report = verify(Document.model_validate(case["document"]), Extraction.model_validate(case["extraction"]), checked)
    assert "PARTIAL_NUMBER" in codes(report)


def test_item_amount_cannot_be_used_as_document_total(case, checked):
    case["extraction"]["total"] = case["extraction"]["items"][0]["amount"]
    report = verify(Document.model_validate(case["document"]), Extraction.model_validate(case["extraction"]), checked)
    assert "TOTAL_IN_ITEM_SCOPE" in codes(report)


def test_inconsistent_line_cannot_hide_behind_total(case, checked):
    case["document"]["pages"][0]["text"] = case["document"]["pages"][0]["text"].replace("3600.00", "3500.00").replace("4500.00", "4400.00")
    case["extraction"]["items"][0]["scope"]["quote"] = case["extraction"]["items"][0]["scope"]["quote"].replace("3600.00", "3500.00")
    case["extraction"]["items"][0]["amount"] = {"value": "3500.00", "evidence": {"page": 1, "quote": "金额 3500.00"}}
    case["extraction"]["total"] = {"value": "4400.00", "evidence": {"page": 1, "quote": "合计 4400.00"}}
    report = verify(Document.model_validate(case["document"]), Extraction.model_validate(case["extraction"]), checked)
    assert "LINE_AMOUNT_MISMATCH" in codes(report)
    assert "TOTAL_MISMATCH" not in codes(report)
    assert report.verdict == "BLOCKED"


def test_unsupported_precision_stays_review_needed(case, checked):
    case["document"]["pages"][0]["text"] = case["document"]["pages"][0]["text"].replace("1200.00", "1200.005")
    case["extraction"]["items"][0]["scope"]["quote"] = case["extraction"]["items"][0]["scope"]["quote"].replace("1200.00", "1200.005")
    case["extraction"]["items"][0]["unit_price"] = {"value": "1200.005", "evidence": {"page": 1, "quote": "单价 1200.005"}}
    report = verify(Document.model_validate(case["document"]), Extraction.model_validate(case["extraction"]), checked)
    assert report.verdict == "NEEDS_REVIEW"
    assert "UNSUPPORTED_PRECISION" in codes(report)


def test_unsupported_currency_not_cleared(case, checked):
    case["document"]["pages"][0]["text"] = case["document"]["pages"][0]["text"].replace("CNY", "USD")
    case["extraction"]["currency"] = {"value": "USD", "evidence": {"page": 1, "quote": "币种 USD"}}
    report = verify(Document.model_validate(case["document"]), Extraction.model_validate(case["extraction"]), checked)
    assert report.verdict == "NEEDS_REVIEW"
    assert "UNSUPPORTED_CURRENCY" in codes(report)
