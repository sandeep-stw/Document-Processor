"""Minimal Business Central v2.0 API client (stdlib only).

Handles OAuth client-credentials tokens against Microsoft Entra ID and
purchase invoice operations needed to update PCs (purchase documents)
from extracted vendor invoices.
"""

from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from .document_extractor import ExtractedDocument
from .settings import Settings

BC_SCOPE = "https://api.businesscentral.dynamics.com/.default"


class BusinessCentralError(RuntimeError):
    """Raised when the Business Central API returns an error."""


@dataclass
class PurchaseInvoiceResult:
    id: str
    number: str
    status: str
    raw: dict


class BusinessCentralClient:
    def __init__(self, settings: Settings, access_token: str | None = None, timeout: int = 60):
        self._settings = settings
        self._timeout = timeout
        self._token = access_token or ""
        self._token_expiry = 0.0

    # -- auth -------------------------------------------------------------

    def _acquire_token(self) -> str:
        if self._token and time.time() < self._token_expiry - 60:
            return self._token
        secret = self._settings.resolve_secret(self._settings.bc_client_secret_env)
        body = urllib.parse.urlencode(
            {
                "grant_type": "client_credentials",
                "client_id": self._settings.bc_client_id,
                "client_secret": secret,
                "scope": BC_SCOPE,
            }
        ).encode("utf-8")
        url = (
            f"https://login.microsoftonline.com/{self._settings.bc_tenant_id}"
            "/oauth2/v2.0/token"
        )
        request = urllib.request.Request(url, data=body, method="POST")
        with urllib.request.urlopen(request, timeout=self._timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        self._token = payload["access_token"]
        self._token_expiry = time.time() + int(payload.get("expires_in", 3600))
        return self._token

    # -- http helpers -----------------------------------------------------

    def _request(self, method: str, path: str, body: dict | None = None) -> Any:
        url = f"{self._settings.bc_api_url}/companies({self._settings.bc_company})/{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("Authorization", "Bearer " + self._acquire_token())
        request.add_header("Accept", "application/json")
        if data is not None:
            request.add_header("Content-Type", "application/json")
            request.add_header("If-Match", "*")
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise BusinessCentralError(
                f"Business Central {method} {path} failed with {exc.code}: {detail}"
            ) from exc

    # -- purchase invoices -------------------------------------------------

    def find_purchase_invoice_by_number(self, number: str) -> dict | None:
        escaped = number.replace("'", "''")
        path = f"purchaseInvoices?$filter=number eq '{escaped}'"
        result = self._request("GET", path)
        values = result.get("value", []) if isinstance(result, dict) else []
        return values[0] if values else None

    def create_purchase_invoice(
        self, vendor_no: str, document: ExtractedDocument, external_number: str = ""
    ) -> PurchaseInvoiceResult:
        payload = document.to_bc_payload(vendor_no)
        if not payload.get("number"):
            payload["number"] = external_number or document.invoice_number
        created = self._request("POST", "purchaseInvoices", payload)
        invoice_id = created.get("id", "")
        for line in document.lines:
            self._request(
                "POST",
                f"purchaseInvoices({invoice_id})/purchaseInvoiceLines",
                {
                    "lineType": "Item",
                    "description": line.description,
                    "quantity": float(line.quantity),
                    "unitCost": float(line.unit_cost),
                },
            )
        return PurchaseInvoiceResult(
            id=invoice_id,
            number=created.get("number", payload["number"]),
            status=created.get("status", "Draft"),
            raw=created,
        )

    def post_purchase_invoice(self, invoice_id: str) -> None:
        self._request("POST", f"purchaseInvoices({invoice_id})/Microsoft.NAV.post")

    def attach_document(self, invoice_id: str, filename: str, content: bytes) -> None:
        """Attach the original vendor document to the invoice (best effort)."""
        body = {
            "fileName": filename,
            "attachmentContent": base64.b64encode(content).decode("ascii"),
        }
        try:
            self._request("POST", f"purchaseInvoices({invoice_id})/attachments", body)
        except BusinessCentralError:
            # Attachments are informational; do not fail the whole run.
            pass
