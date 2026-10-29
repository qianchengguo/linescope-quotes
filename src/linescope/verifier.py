"""Deterministic evidence checks. Presence does not prove semantic correctness."""

import hashlib
import re
from decimal import ROUND_HALF_UP, Decimal

from .models import CheckReport, Document, Evidence, Extraction, Finding, Review

# Whole tokens prevent 12 from being accepted inside 112 or 12.50.
NUMBER = re.compile(r"(?<![0-9A-Za-z_.,+-])[0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?(?![0-9A-Za-z_.,])")
CENT = Decimal("0.01")


def document_hash(document: Document) -> str:
    return hashlib.sha256(document.model_dump_json().encode("utf-8")).hexdigest()


def verify(document: Document, extraction: Extraction, review: Review) -> CheckReport:
    pages = {p.number: p.text for p in document.pages}
    findings: list[Finding] = []
    anchors: dict[str, dict[str, int]] = {}
    calculations: list[dict[str, str]] = []

    def issue(code, path, message, severity="blocked"):
        findings.append(Finding(code=code, severity=severity, path=path, message=message))

    def locate(evidence: Evidence | None, path: str, scope=None):
        if evidence is None:
            issue("MISSING_EVIDENCE", path, "缺少来源证据", "review")
            return None
        text = pages.get(evidence.page)
        if text is None:
            issue("PAGE_NOT_FOUND", path, "来源页不存在")
            return None
        if scope is not None:
            if evidence.page != scope[0]:
                issue("OUTSIDE_ITEM_SCOPE", path, "证据属于其他页的明细")
                return None
            low, high = scope[1], scope[2]
        else:
            low, high = 0, len(text)
        # Lookahead also detects overlapping duplicate quotations.
        hits = [m.start() + low for m in re.finditer(
            "(?=" + re.escape(evidence.quote) + ")", text[low:high]
        )]
        if not hits:
            code = "OUTSIDE_ITEM_SCOPE" if scope else "QUOTE_NOT_FOUND"
            issue(code, path, "原文中找不到该引用，或引用不在当前明细范围")
            return None
        if len(hits) != 1:
            issue("AMBIGUOUS_EVIDENCE", path, "引用出现多次，请提供更长的上下文", "review")
            return None
        start = hits[0]
        anchor = (evidence.page, start, start + len(evidence.quote))
        anchors[path] = dict(page=anchor[0], start=anchor[1], end=anchor[2])
        return anchor

    def field_ok(field, path, scope=None):
        if field.value is None:
            issue("MISSING_VALUE", path, "字段未抽取，禁止将其当作零或自动补全", "review")
            return False
        anchor = locate(field.evidence, path, scope)
        if anchor is None:
            return False
        quote = field.evidence.quote
        if isinstance(field.value, Decimal):
            tokens = list(NUMBER.finditer(quote))
            values = [Decimal(m.group().replace(",", "")) for m in tokens]
            if len(values) != 1:
                issue("AMBIGUOUS_NUMBER", path, "引用须包含且仅包含一个完整数值", "review")
                return False
            if values[0] != field.value:
                issue("VALUE_NOT_SUPPORTED", path, "抽取数值与引用中的数值不同")
                return False
            token = tokens[0]
            source_tokens = {(m.start(), m.end()) for m in NUMBER.finditer(pages[anchor[0]])}
            if (anchor[1] + token.start(), anchor[1] + token.end()) not in source_tokens:
                issue("PARTIAL_NUMBER", path, "引用截断了原文的完整数值")
                return False
        elif field.value not in quote:
            issue("VALUE_NOT_SUPPORTED", path, "抽取文本不在引用中")
            return False
        return True

    currency_ok = field_ok(extraction.currency, "currency")
    if currency_ok and extraction.currency.value not in {"CNY", "人民币"}:
        issue("UNSUPPORTED_CURRENCY", "currency", "MVP仅支持单币种人民币", "review")

    all_items_ok = True
    amounts: list[Decimal] = []
    scopes = []
    for idx, item in enumerate(extraction.items):
        prefix = f"items.{idx}"
        scope = locate(item.scope, prefix + ".scope")
        if scope is None:
            all_items_ok = False
            continue
        if any(scope[0] == old[0] and scope[1] < old[2] and old[1] < scope[2] for old in scopes):
            issue("OVERLAPPING_ITEMS", prefix + ".scope", "明细范围重叠或重复使用同一行")
            all_items_ok = False
        scopes.append(scope)
        ok = field_ok(item.name, prefix + ".name", scope)
        for key in ("quantity", "unit_price", "amount"):
            ok = field_ok(getattr(item, key), prefix + "." + key, scope) and ok
        if item.quantity.value is not None and item.quantity.value <= 0:
            issue("INVALID_QUANTITY", prefix + ".quantity", "数量必须大于零", "review")
            ok = False
        for key in ("unit_price", "amount"):
            value = getattr(item, key).value
            if value is not None and value != value.quantize(CENT):
                issue("UNSUPPORTED_PRECISION", prefix + "." + key, "金额或单价超过两位小数", "review")
                ok = False
        if ok:
            expected = (item.quantity.value * item.unit_price.value).quantize(CENT, rounding=ROUND_HALF_UP)
            actual = item.amount.value
            calculations.append(dict(path=prefix, expected=str(expected), actual=str(actual),
                                     delta=str(actual - expected)))
            if expected != actual:
                issue("LINE_AMOUNT_MISMATCH", prefix + ".amount", f"数量×单价={expected}，原文金额={actual}")
            amounts.append(actual)
        else:
            all_items_ok = False

    total_ok = field_ok(extraction.total, "total")
    total_anchor = anchors.get("total")
    if total_anchor and any(total_anchor["page"] == s[0] and total_anchor["start"] < s[2]
                            and s[1] < total_anchor["end"] for s in scopes):
        issue("TOTAL_IN_ITEM_SCOPE", "total", "总额引用落在明细行内，不能当作报价总额")
        total_ok = False
    if extraction.total.value is not None and extraction.total.value != extraction.total.value.quantize(CENT):
        issue("UNSUPPORTED_PRECISION", "total", "总额超过两位小数", "review")
        total_ok = False
    if all_items_ok and total_ok:
        expected = sum(amounts, Decimal("0.00"))
        actual = extraction.total.value
        calculations.append(dict(path="total", expected=str(expected), actual=str(actual),
                                 delta=str(actual - expected)))
        if expected != actual:
            issue("TOTAL_MISMATCH", "total", f"明细金额合计={expected}，原文总额={actual}")
    if not review.coverage_confirmed:
        issue("COVERAGE_UNCONFIRMED", "review", "需人工对照原文确认没有漏行、错行", "review")
    if not review.simple_pricing_confirmed:
        issue("PRICING_SCOPE_UNCONFIRMED", "review", "需确认无税费、折扣、运费、多币种等额外计算", "review")
    if extraction.notes:
        issue("EXTRACTION_NOTES", "notes", "抽取包含待解释事项，请先人工复核", "review")
    verdict = "BLOCKED" if any(f.severity == "blocked" for f in findings) else (
        "NEEDS_REVIEW" if findings else "CHECKS_PASSED"
    )
    return CheckReport(document_sha256=document_hash(document), verdict=verdict,
                       findings=findings, anchors=anchors, calculations=calculations)
