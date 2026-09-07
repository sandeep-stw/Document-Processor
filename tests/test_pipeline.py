from src.document_extractor import RegexInvoiceExtractor
from src.email_ingestor import EmailAttachment, IncomingEmail
from src.pipeline import DocumentPipeline, ProcessingStatus
from src.settings import Settings
from src.vendor_store import Vendor, VendorStore

INVOICE_TEXT = b"""\
Invoice Number: INV-1001
Invoice Date: 2026-09-01
Total: USD 100.00
"""


class FakeBCClient:
    def __init__(self, existing=None, fail=False):
        self.existing = existing
        self.fail = fail
        self.created = []
        self.attached = []

    def find_purchase_invoice_by_number(self, number):
        if self.fail:
            raise RuntimeError("boom")
        return self.existing

    def create_purchase_invoice(self, vendor_no, document, external_number=""):
        from src.business_central import PurchaseInvoiceResult

        self.created.append((vendor_no, document))
        return PurchaseInvoiceResult(id="bc-1", number=document.invoice_number, status="Draft", raw={})

    def attach_document(self, invoice_id, filename, content):
        self.attached.append((invoice_id, filename))


def _settings():
    return Settings(
        mailbox="ap@example.com",
        vendor_store_path="unused",
        bc_base_url="https://api.businesscentral.dynamics.com",
        bc_environment="production",
        bc_company="CRONUS",
        bc_tenant_id="t",
        bc_client_id="c",
    )


def _store():
    return VendorStore(
        [
            Vendor(
                name="Contoso",
                vendor_no="V00010",
                email_addresses=("invoices@contoso.example.com",),
                email_domains=("contoso.example.com",),
                currency_code="USD",
            )
        ]
    )


def _email(sender, with_attachment=True, body=""):
    attachments = []
    if with_attachment:
        attachments.append(
            EmailAttachment("invoice.pdf", "application/pdf", INVOICE_TEXT)
        )
    return IncomingEmail(sender=sender, subject="Invoice", body_text=body, attachments=attachments)


def _pipeline(bc):
    return DocumentPipeline(_settings(), _store(), RegexInvoiceExtractor(), bc)


def test_processes_known_vendor_and_creates_invoice():
    bc = FakeBCClient()
    result = _pipeline(bc).process_email(_email("Billing <invoices@contoso.example.com>"))
    assert result.status == ProcessingStatus.PROCESSED
    assert result.vendor_no == "V00010"
    assert result.invoice_number == "INV-1001"
    assert result.bc_invoice_id == "bc-1"
    assert bc.created[0][0] == "V00010"
    assert bc.attached == [("bc-1", "invoice.pdf")]


def test_skips_unknown_vendor():
    bc = FakeBCClient()
    result = _pipeline(bc).process_email(_email("random@stranger.example.com"))
    assert result.status == ProcessingStatus.SKIPPED_UNKNOWN_VENDOR
    assert bc.created == []


def test_skips_when_no_supported_attachment_and_no_body():
    bc = FakeBCClient()
    msg = _email("invoices@contoso.example.com", with_attachment=False)
    msg.attachments.append(EmailAttachment("notes.txt", "text/plain", b"hi"))
    result = _pipeline(bc).process_email(msg)
    assert result.status == ProcessingStatus.SKIPPED_NO_ATTACHMENT


def test_falls_back_to_body_text_when_no_attachment():
    bc = FakeBCClient()
    result = _pipeline(bc).process_email(
        _email("invoices@contoso.example.com", with_attachment=False, body=INVOICE_TEXT.decode())
    )
    assert result.status == ProcessingStatus.PROCESSED


def test_existing_invoice_is_not_duplicated():
    bc = FakeBCClient(existing={"id": "bc-existing", "number": "INV-1001"})
    result = _pipeline(bc).process_email(_email("invoices@contoso.example.com"))
    assert result.status == ProcessingStatus.PROCESSED
    assert result.bc_invoice_id == "bc-existing"
    assert bc.created == []


def test_bc_failure_is_reported():
    bc = FakeBCClient(fail=True)
    result = _pipeline(bc).process_email(_email("invoices@contoso.example.com"))
    assert result.status == ProcessingStatus.BC_UPDATE_FAILED
    assert result.errors


def test_missing_invoice_number_is_extraction_failure():
    bc = FakeBCClient()
    msg = IncomingEmail(
        sender="invoices@contoso.example.com",
        subject="Hi",
        body_text="no invoice data here",
        attachments=[],
    )
    result = _pipeline(bc).process_email(msg)
    assert result.status == ProcessingStatus.EXTRACTION_FAILED
