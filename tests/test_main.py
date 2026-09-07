import json

from src.main import main

EML = b"""\
From: Billing <invoices@contoso.example.com>
To: vendor-invoices@example.com
Subject: Invoice INV-2026-0042
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="BOUND"

--BOUND
Content-Type: text/plain; charset="utf-8"

Attached invoice.

--BOUND
Content-Type: application/pdf; name="invoice.pdf"
Content-Disposition: attachment; filename="invoice.pdf"
Content-Transfer-Encoding: base64

SW52b2ljZSBOdW1iZXI6IElOVi0yMDI2LTAwNDIKSW52b2ljZSBEYXRlOiAyMDI2LTA5LTAxClRvdGFsOiBVU0QgMTAwLjAw

--BOUND--
"""


def test_cli_dry_run_processes_sample_invoice(tmp_path, capsys):
    eml_path = tmp_path / "message.eml"
    eml_path.write_bytes(EML)

    exit_code = main(
        [
            "--eml",
            str(eml_path),
            "--dry-run",
        ]
    )
    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "processed"
    assert output["vendor_no"] == "V00010"
    assert output["invoice_number"] == "INV-2026-0042"


def test_cli_returns_nonzero_for_unknown_vendor(tmp_path, capsys):
    eml_path = tmp_path / "unknown.eml"
    eml_path.write_bytes(EML.replace(b"invoices@contoso.example.com", b"mallory@evil.example.com"))

    exit_code = main(["--eml", str(eml_path), "--dry-run"])
    assert exit_code == 1
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "skipped_unknown_vendor"
