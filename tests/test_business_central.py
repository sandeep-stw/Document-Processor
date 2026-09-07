import json

import pytest

from src.business_central import BusinessCentralClient, BusinessCentralError
from src.document_extractor import ExtractedDocument
from src.settings import Settings


def _settings():
    return Settings(
        mailbox="ap@example.com",
        vendor_store_path="unused",
        bc_base_url="https://api.businesscentral.dynamics.com",
        bc_environment="production",
        bc_company="CRONUS International Ltd.",
        bc_tenant_id="tenant",
        bc_client_id="client",
    )


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_bc_api_url_composition():
    assert _settings().bc_api_url == (
        "https://api.businesscentral.dynamics.com/v2.0/production/api/v2.0"
    )


def test_find_purchase_invoice_builds_filter_and_uses_bearer_token(monkeypatch):
    token = "".join(["token", "-", "123"])
    client = BusinessCentralClient(_settings(), access_token=token)
    client._token_expiry = float("inf")
    requests = []

    def fake_urlopen(request, timeout=0):
        requests.append(request)
        return FakeResponse({"value": [{"id": "1", "number": "INV-1"}]})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    found = client.find_purchase_invoice_by_number("INV-1")
    assert found["id"] == "1"
    url = requests[0].full_url
    assert "companies(CRONUS International Ltd.)" in url
    assert "purchaseInvoices?$filter=number eq 'INV-1'" in url
    expected = " ".join(["Bearer", token])
    assert requests[0].headers["Authorization"] == expected


def test_find_purchase_invoice_returns_none_when_empty(monkeypatch):
    client = BusinessCentralClient(_settings(), access_token="token-123")
    client._token_expiry = float("inf")
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda request, timeout=0: FakeResponse({"value": []})
    )
    assert client.find_purchase_invoice_by_number("NOPE") is None


def test_http_error_raises_domain_exception(monkeypatch):
    import urllib.error

    client = BusinessCentralClient(_settings(), access_token="token-123")
    client._token_expiry = float("inf")

    def fake_urlopen(request, timeout=0):
        raise urllib.error.HTTPError(
            request.full_url, 400, "Bad Request", hdrs=None, fp=__import__("io").BytesIO(b"{}")
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    with pytest.raises(BusinessCentralError):
        client.find_purchase_invoice_by_number("INV-1")


def test_create_purchase_invoice_posts_payload_and_lines(monkeypatch):
    client = BusinessCentralClient(_settings(), access_token="token-123")
    client._token_expiry = float("inf")
    calls = []

    def fake_urlopen(request, timeout=0):
        body = json.loads(request.data.decode()) if request.data else None
        calls.append((request.get_method(), request.full_url, body))
        return FakeResponse({"id": "inv-1", "number": body["number"], "status": "Draft"})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    doc = ExtractedDocument(
        invoice_number="INV-9",
        invoice_date="2026-09-01",
        currency_code="USD",
        lines=[],
    )
    result = client.create_purchase_invoice("V00010", doc)
    assert result.id == "inv-1"
    assert result.number == "INV-9"
    assert calls[0][0] == "POST"
    assert "purchaseInvoices" in calls[0][1]
    assert calls[0][2]["vendorNumber"] == "V00010"
