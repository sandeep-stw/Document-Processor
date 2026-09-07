from decimal import Decimal

from src.document_extractor import RegexInvoiceExtractor, get_extractor, CopilotStudioExtractor

SAMPLE_INVOICE = b"""\
Contoso Office Supplies
123 Market Street

Invoice Number: INV-2026-0042
Invoice Date: 2026-09-01
Due Date: 30 Sep 2026
Purchase Order #: PO-7788

Items:
Office chairs 2 x USD 150.00
Desk lamps 5 x USD 25.50

Subtotal: USD 427.50
Grand Total: USD 449.00
"""


def test_regex_extractor_parses_header_fields():
    doc = RegexInvoiceExtractor().extract(SAMPLE_INVOICE)
    assert doc.invoice_number == "INV-2026-0042"
    assert doc.invoice_date == "2026-09-01"
    assert doc.due_date == "2026-09-30"
    assert doc.purchase_order_number == "PO-7788"
    assert doc.total_amount == Decimal("449.00")
    assert doc.currency_code == "USD"
    assert doc.confidence == 1.0


def test_regex_extractor_parses_lines():
    doc = RegexInvoiceExtractor().extract(SAMPLE_INVOICE)
    assert len(doc.lines) == 2
    assert doc.lines[0].description == "Office chairs"
    assert doc.lines[0].quantity == Decimal("2")
    assert doc.lines[0].unit_cost == Decimal("150.00")


def test_regex_extractor_handles_missing_fields_gracefully():
    doc = RegexInvoiceExtractor().extract(b"Hello, here is our newsletter.")
    assert doc.invoice_number == ""
    assert doc.total_amount == Decimal("0")
    assert doc.confidence < 1.0


def test_to_bc_payload_includes_vendor_and_optional_fields():
    doc = RegexInvoiceExtractor().extract(SAMPLE_INVOICE)
    payload = doc.to_bc_payload("V00010")
    assert payload["number"] == "INV-2026-0042"
    assert payload["vendorNumber"] == "V00010"
    assert payload["invoiceDate"] == "2026-09-01"
    assert payload["currencyCode"] == "USD"
    assert payload["purchaseOrderNumber"] == "PO-7788"


def test_get_extractor_returns_copilot_when_endpoint_configured():
    extractor = get_extractor("https://example.com/model")
    assert isinstance(extractor, CopilotStudioExtractor)
    assert isinstance(get_extractor(""), RegexInvoiceExtractor)
