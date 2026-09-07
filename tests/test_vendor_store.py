import json

from src.vendor_store import Vendor, VendorStore, normalize_email


def _write_store(tmp_path, vendors):
    path = tmp_path / "vendors.json"
    path.write_text(json.dumps({"vendors": vendors}), encoding="utf-8")
    return path


def test_normalize_email_extracts_address_from_display_name():
    assert normalize_email("Jane Doe <Jane.Doe@Example.COM>") == "jane.doe@example.com"
    assert normalize_email("plain@example.com") == "plain@example.com"
    assert normalize_email("not-an-email") == ""
    assert normalize_email("") == ""


def test_vendor_matches_by_exact_address_and_domain():
    vendor = Vendor(
        name="Contoso",
        vendor_no="V1",
        email_addresses=("ap@contoso.example.com",),
        email_domains=("contoso.example.com",),
    )
    assert vendor.matches_sender("AP <ap@contoso.example.com>")
    assert vendor.matches_sender("billing@contoso.example.com")
    assert not vendor.matches_sender("someone@other.example.com")
    assert not vendor.matches_sender("no-email-here")


def test_store_finds_active_vendor_only(tmp_path):
    path = _write_store(
        tmp_path,
        [
            {
                "name": "Active Co",
                "vendor_no": "V1",
                "email_addresses": [],
                "email_domains": ["active.example.com"],
                "active": True,
            },
            {
                "name": "Inactive Co",
                "vendor_no": "V2",
                "email_addresses": [],
                "email_domains": ["inactive.example.com"],
                "active": False,
            },
        ],
    )
    store = VendorStore.load(path)
    assert len(store) == 2
    found = store.find_by_sender("billing@active.example.com")
    assert found is not None and found.vendor_no == "V1"
    assert store.find_by_sender("billing@inactive.example.com") is None
    assert store.find_by_sender("billing@unknown.example.com") is None


def test_store_defaults_document_type_and_currency(tmp_path):
    path = _write_store(
        tmp_path,
        [
            {
                "name": "Minimal",
                "vendor_no": "V9",
                "email_addresses": ["a@minimal.example.com"],
                "email_domains": [],
            }
        ],
    )
    store = VendorStore.load(path)
    vendor = store.find_by_sender("a@minimal.example.com")
    assert vendor.default_document_type == "Invoice"
    assert vendor.currency_code == ""
    assert vendor.active is True
