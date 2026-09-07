"""Vendor store: the allow-list of vendors whose documents are processed.

In production the vendor store lives in Microsoft Dataverse and is maintained
through a Power Apps canvas app. This module mirrors that store from a JSON
file (``config/vendors.json``) so the pipeline can run and be tested outside
the Power Platform.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

_EMAIL_RE = re.compile(r"[^<>\s]+@[^<>\s]+")


def normalize_email(raw: str) -> str:
    """Extract a lowercase address from a display string like 'Name <a@b.com>'."""
    matches = _EMAIL_RE.findall(raw or "")
    if not matches:
        return ""
    return matches[-1].strip().lower()


@dataclass(frozen=True)
class Vendor:
    name: str
    vendor_no: str
    email_addresses: tuple[str, ...]
    email_domains: tuple[str, ...]
    default_document_type: str = "Invoice"
    currency_code: str = ""
    active: bool = True

    def matches_sender(self, sender: str) -> bool:
        address = normalize_email(sender)
        if not address:
            return False
        if address in self.email_addresses:
            return True
        domain = address.rsplit("@", 1)[-1]
        return domain in self.email_domains


class VendorStore:
    """In-memory vendor allow-list loaded from JSON."""

    def __init__(self, vendors: list[Vendor]):
        self._vendors = vendors

    def __len__(self) -> int:  # pragma: no cover - trivial
        return len(self._vendors)

    @property
    def vendors(self) -> list[Vendor]:
        return list(self._vendors)

    @classmethod
    def load(cls, path: str | Path) -> "VendorStore":
        with open(path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
        entries = raw.get("vendors", raw if isinstance(raw, list) else [])
        vendors = [
            Vendor(
                name=entry["name"],
                vendor_no=entry["vendor_no"],
                email_addresses=tuple(a.lower() for a in entry.get("email_addresses", [])),
                email_domains=tuple(d.lower() for d in entry.get("email_domains", [])),
                default_document_type=entry.get("default_document_type", "Invoice"),
                currency_code=entry.get("currency_code", ""),
                active=entry.get("active", True),
            )
            for entry in entries
        ]
        return cls(vendors)

    def find_by_sender(self, sender: str) -> Vendor | None:
        """Return the active vendor allowed to send from this address, if any."""
        for vendor in self._vendors:
            if vendor.active and vendor.matches_sender(sender):
                return vendor
        return None
