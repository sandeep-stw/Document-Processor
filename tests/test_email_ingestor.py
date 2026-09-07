from src.email_ingestor import parse_eml

EML = b"""\
From: Billing <invoices@contoso.example.com>
To: vendor-invoices@example.com
Subject: Invoice INV-1001
Message-ID: <abc123@contoso.example.com>
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="BOUND"

--BOUND
Content-Type: text/plain; charset="utf-8"

Please find attached our invoice.

--BOUND
Content-Type: application/pdf; name="invoice.pdf"
Content-Disposition: attachment; filename="invoice.pdf"
Content-Transfer-Encoding: base64

SW52b2ljZSBOdW1iZXI6IElOVi0xMDAx

--BOUND--
"""


def test_parse_eml_extracts_headers_body_and_attachment(tmp_path):
    eml_path = tmp_path / "message.eml"
    eml_path.write_bytes(EML)
    message = parse_eml(eml_path)
    assert message.sender == "Billing <invoices@contoso.example.com>"
    assert message.subject == "Invoice INV-1001"
    assert message.message_id == "<abc123@contoso.example.com>"
    assert "Please find attached" in message.body_text
    assert len(message.attachments) == 1
    attachment = message.attachments[0]
    assert attachment.filename == "invoice.pdf"
    assert attachment.extension == ".pdf"
    assert attachment.content == b"Invoice Number: INV-1001"
