"""CLI entry point.

Usage:
    python -m src.main --eml path/to/message.eml
    python -m src.main --eml path/to/message.eml --dry-run --verbose
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict

from .business_central import BusinessCentralClient
from .document_extractor import get_extractor
from .email_ingestor import parse_eml
from .pipeline import DocumentPipeline
from .settings import load_settings
from .vendor_store import VendorStore


class _DryRunBCClient(BusinessCentralClient):
    """Business Central client stub that records calls without network I/O."""

    def __init__(self):  # type: ignore[super-init-not-called]
        self.calls: list[tuple[str, tuple, dict]] = []

    def _record(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))

    def find_purchase_invoice_by_number(self, number):  # noqa: D102
        self._record("find_purchase_invoice_by_number", number)
        return None

    def create_purchase_invoice(self, vendor_no, document, external_number=""):  # noqa: D102
        self._record("create_purchase_invoice", vendor_no, document, external_number)
        from .business_central import PurchaseInvoiceResult

        return PurchaseInvoiceResult(
            id="DRY-RUN", number=document.invoice_number, status="Draft", raw={}
        )

    def post_purchase_invoice(self, invoice_id):  # noqa: D102
        self._record("post_purchase_invoice", invoice_id)

    def attach_document(self, invoice_id, filename, content):  # noqa: D102
        self._record("attach_document", invoice_id, filename, content)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="document-processor",
        description="Process vendor documents received by email and update Business Central.",
    )
    parser.add_argument("--eml", required=False, help="Path to an .eml file to process.")
    parser.add_argument(
        "--settings", default=None, help="Path to settings.json (default: config/settings.json)."
    )
    parser.add_argument(
        "--vendors", default=None, help="Path to vendors.json vendor store override."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the full pipeline but skip Business Central writes.",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    settings = load_settings(args.settings)
    store = VendorStore.load(args.vendors or settings.vendor_store_path)
    extractor = get_extractor(settings.copilot_studio_endpoint)
    bc_client: BusinessCentralClient = (
        _DryRunBCClient()
        if args.dry_run
        else BusinessCentralClient(settings, access_token="")  # token fetched lazily
    )
    pipeline = DocumentPipeline(settings, store, extractor, bc_client)

    if not args.eml:
        build_parser().error("--eml is required (Power Automate calls this per message)")

    message = parse_eml(args.eml)
    result = pipeline.process_email(message)
    print(json.dumps(asdict(result), indent=2, default=str))
    return 0 if result.status.value == "processed" else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
