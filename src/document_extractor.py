"""Document extraction.

In the managed solution this step is performed by a Copilot Studio document
processing model (AI Builder invoice/custom model). This module provides the
contract (:class:`ExtractedDocument`) plus a deterministic regex-based
extractor used for local development, tests, and as a fallback when the
Copilot Studio endpoint is unavailable.
"""

from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Protocol

_CURRENCY_CODES = ("USD", "EUR", "GBP", "INR", "AUD", "CAD", "JPY", "AED", "SGD")

_LABELS = {
    "invoice_number": [
        r"invoice\s*(?:no\.?|number|#|id)",
        r"inv(?:oice)?[-\s]*(?:no\.?|#)",
        r"document\s*(?:no\.?|number)",
    ],
    "purchase_order": [
        r"purchase\s*order\s*(?:no\.?|number|#)?",
        r"\bp\.?\s?o\.?\s*(?:no\.?|number|#)",
        r"order\s*reference",
    ],
    "invoice_date": [
        r"invoice\s*date",
        r"document\s*date",
        r"date\s*of\s*invoice",
    ],
    "due_date": [r"due\s*date", r"payment\s*due"],
    "total": [
        r"grand\s*total\s*(?:amount|due|payable)?",
        r"amount\s*due",
        r"balance\s*due",
        r"invoice\s*total",
        r"total\s*(?:amount|due|payable)",
    ],
}

_AMOUNT_RE = r"([A-Z]{3})?\s*[$€£₹]?\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)"
_DATE_PATTERNS = [
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), "ymd"),
    (re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b"), "mdy"),
    (re.compile(r"\b(\d{1,2})-(\d{1,2})-(\d{4})\b"), "dmy"),
    (
        re.compile(
            r"\b(\d{1,2})\s+"
            r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*"
            r"\s*,?\s+(\d{4})\b",
            re.IGNORECASE,
        ),
        "dMonthY",
    ),
]

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


@dataclass
class DocumentLine:
    description: str
    quantity: Decimal = Decimal("1")
    unit_cost: Decimal = Decimal("0")


@dataclass
class ExtractedDocument:
    """Structured data extracted from a vendor document."""

    invoice_number: str = ""
    purchase_order_number: str = ""
    invoice_date: str = ""
    due_date: str = ""
    currency_code: str = ""
    total_amount: Decimal = Decimal("0")
    lines: list[DocumentLine] = field(default_factory=list)
    raw_text: str = ""
    confidence: float = 0.0

    def to_bc_payload(self, vendor_no: str) -> dict:
        """Build the Business Central purchaseInvoices POST body."""
        payload: dict = {"number": self.invoice_number, "vendorNumber": vendor_no}
        if self.invoice_date:
            payload["invoiceDate"] = self.invoice_date
        if self.due_date:
            payload["dueDate"] = self.due_date
        if self.purchase_order_number:
            payload["vendorInvoiceNumber"] = self.invoice_number
            payload["purchaseOrderNumber"] = self.purchase_order_number
        if self.currency_code:
            payload["currencyCode"] = self.currency_code
        return payload


def _parse_amount(value: str) -> Decimal:
    try:
        return Decimal(value.replace(",", "")).quantize(Decimal("0.01"))
    except InvalidOperation:
        return Decimal("0")


def _parse_date(text: str) -> str:
    for pattern, kind in _DATE_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        try:
            if kind == "ymd":
                parsed = date(int(match[1]), int(match[2]), int(match[3]))
            elif kind == "mdy":
                parsed = date(int(match[3]), int(match[1]), int(match[2]))
            elif kind == "dmy":
                parsed = date(int(match[3]), int(match[2]), int(match[1]))
            else:  # dMonthY
                parsed = date(int(match[3]), _MONTHS[match[2][:3].lower()], int(match[1]))
            return parsed.isoformat()
        except (ValueError, KeyError):
            continue
    return ""


def _find_labeled_value(text: str, labels: list[str]) -> str:
    for label in labels:
        match = re.search(label + r"\s*[:\-]?\s*(.+)", text, re.IGNORECASE)
        if match:
            return match.group(1).strip().splitlines()[0].strip()
    return ""


class RegexInvoiceExtractor:
    """Deterministic fallback extractor for plain-text invoice content."""

    def extract(self, content: bytes, content_type: str = "text/plain") -> ExtractedDocument:
        text = content.decode("utf-8", errors="replace")
        doc = ExtractedDocument(raw_text=text)
        hits = 0

        invoice_number = _find_labeled_value(text, _LABELS["invoice_number"])
        if invoice_number:
            doc.invoice_number = invoice_number.split()[0]
            hits += 1

        po = _find_labeled_value(text, _LABELS["purchase_order"])
        if po:
            doc.purchase_order_number = po.split()[0]
            hits += 1

        for key, attr in (("invoice_date", "invoice_date"), ("due_date", "due_date")):
            value = _find_labeled_value(text, _LABELS[key])
            parsed = _parse_date(value) if value else ""
            if parsed:
                setattr(doc, attr, parsed)
                hits += 1

        total_label = _find_labeled_value(text, _LABELS["total"])
        if total_label:
            amount_match = re.search(_AMOUNT_RE, total_label)
            if amount_match:
                code, digits = amount_match.group(1), amount_match.group(2)
                doc.total_amount = _parse_amount(digits)
                if code in _CURRENCY_CODES:
                    doc.currency_code = code
                hits += 1

        if not doc.currency_code:
            for code in _CURRENCY_CODES:
                if re.search(rf"\b{code}\b", text):
                    doc.currency_code = code
                    break

        doc.lines = self._extract_lines(text)
        doc.confidence = round(hits / 5.0, 2)
        return doc

    @staticmethod
    def _extract_lines(text: str) -> list[DocumentLine]:
        """Parse simple 'description qty x price' table rows."""
        lines: list[DocumentLine] = []
        row_re = re.compile(
            rf"^\s*(?P<desc>.+?)\s+(?P<qty>\d+(?:\.\d+)?)\s*[x@]\s*{_AMOUNT_RE}\s*$",
            re.IGNORECASE,
        )
        for raw_line in text.splitlines():
            match = row_re.match(raw_line)
            if match:
                lines.append(
                    DocumentLine(
                        description=match["desc"].strip(),
                        quantity=Decimal(match["qty"]),
                        unit_cost=_parse_amount(match.group(4)),
                    )
                )
        return lines


class CopilotStudioExtractor:
    """Calls a Copilot Studio / AI Builder document processing endpoint.

    The endpoint must accept ``{"content_base64": ..., "content_type": ...}``
    and return the extracted fields as JSON.
    """

    def __init__(self, endpoint: str, timeout: int = 60):
        if not endpoint:
            raise ValueError("Copilot Studio endpoint is required")
        self._endpoint = endpoint
        self._timeout = timeout

    def extract(self, content: bytes, content_type: str = "application/pdf") -> ExtractedDocument:
        import base64

        body = json.dumps(
            {
                "content_base64": base64.b64encode(content).decode("ascii"),
                "content_type": content_type,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            self._endpoint, data=body, headers={"Content-Type": "application/json"}, method="POST"
        )
        with urllib.request.urlopen(request, timeout=self._timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))

        return ExtractedDocument(
            invoice_number=payload.get("invoice_number", ""),
            purchase_order_number=payload.get("purchase_order_number", ""),
            invoice_date=payload.get("invoice_date", ""),
            due_date=payload.get("due_date", ""),
            currency_code=payload.get("currency_code", ""),
            total_amount=_parse_amount(str(payload.get("total_amount", "0"))),
            lines=[
                DocumentLine(
                    description=line.get("description", ""),
                    quantity=Decimal(str(line.get("quantity", 1))),
                    unit_cost=_parse_amount(str(line.get("unit_cost", 0))),
                )
                for line in payload.get("lines", [])
            ],
            confidence=float(payload.get("confidence", 0.0)),
        )


def get_extractor(endpoint: str = "") -> "Extractor":
    """Return the Copilot Studio extractor when configured, else the fallback."""
    if endpoint:
        return CopilotStudioExtractor(endpoint)
    return RegexInvoiceExtractor()


class Extractor(Protocol):  # pragma: no cover - typing only
    def extract(self, content: bytes, content_type: str = ...) -> ExtractedDocument: ...
