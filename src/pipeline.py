"""Document processing pipeline.

Implements the same steps as the Power Automate flow:
receive email -> check vendor allow-list -> extract document -> update the
purchase document (PC) in Business Central -> report the outcome.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

from .business_central import BusinessCentralClient
from .document_extractor import Extractor
from .email_ingestor import IncomingEmail
from .settings import Settings
from .vendor_store import VendorStore

logger = logging.getLogger(__name__)


class ProcessingStatus(str, Enum):
    PROCESSED = "processed"
    SKIPPED_UNKNOWN_VENDOR = "skipped_unknown_vendor"
    SKIPPED_NO_ATTACHMENT = "skipped_no_attachment"
    EXTRACTION_FAILED = "extraction_failed"
    BC_UPDATE_FAILED = "bc_update_failed"


@dataclass
class ProcessingResult:
    status: ProcessingStatus
    vendor_no: str = ""
    invoice_number: str = ""
    bc_invoice_id: str = ""
    detail: str = ""
    errors: list[str] = field(default_factory=list)


class DocumentPipeline:
    def __init__(
        self,
        settings: Settings,
        vendor_store: VendorStore,
        extractor: Extractor,
        bc_client: BusinessCentralClient,
    ):
        self._settings = settings
        self._vendors = vendor_store
        self._extractor = extractor
        self._bc = bc_client

    def process_email(self, message: IncomingEmail) -> ProcessingResult:
        vendor = self._vendors.find_by_sender(message.sender)
        if vendor is None:
            logger.info("Skipping message from unknown vendor: %s", message.sender)
            return ProcessingResult(
                status=ProcessingStatus.SKIPPED_UNKNOWN_VENDOR,
                detail=f"Sender '{message.sender}' is not in the vendor store.",
            )

        attachments = [
            a
            for a in message.attachments
            if a.extension in self._settings.required_attachment_extensions
        ]
        if not attachments and not message.body_text:
            return ProcessingResult(
                status=ProcessingStatus.SKIPPED_NO_ATTACHMENT,
                vendor_no=vendor.vendor_no,
                detail="No supported attachment or body content found.",
            )

        # Prefer the first supported attachment; fall back to the body text.
        if attachments:
            content, content_type, filename = (
                attachments[0].content,
                attachments[0].content_type,
                attachments[0].filename,
            )
        else:
            content, content_type, filename = (
                message.body_text.encode("utf-8"),
                "text/plain",
                "body.txt",
            )

        try:
            document = self._extractor.extract(content, content_type)
        except Exception as exc:  # noqa: BLE001 - surface any extractor failure
            logger.exception("Extraction failed for %s", filename)
            return ProcessingResult(
                status=ProcessingStatus.EXTRACTION_FAILED,
                vendor_no=vendor.vendor_no,
                detail=f"Extraction failed: {exc}",
                errors=[str(exc)],
            )

        if not document.invoice_number:
            return ProcessingResult(
                status=ProcessingStatus.EXTRACTION_FAILED,
                vendor_no=vendor.vendor_no,
                detail="No invoice number could be extracted.",
            )

        try:
            if not document.currency_code and vendor.currency_code:
                document.currency_code = vendor.currency_code
            existing = self._bc.find_purchase_invoice_by_number(document.invoice_number)
            if existing:
                result = ProcessingResult(
                    status=ProcessingStatus.PROCESSED,
                    vendor_no=vendor.vendor_no,
                    invoice_number=document.invoice_number,
                    bc_invoice_id=existing.get("id", ""),
                    detail="Purchase invoice already exists in Business Central.",
                )
            else:
                created = self._bc.create_purchase_invoice(
                    vendor.vendor_no, document, external_number=message.message_id
                )
                self._bc.attach_document(created.id, filename, content)
                result = ProcessingResult(
                    status=ProcessingStatus.PROCESSED,
                    vendor_no=vendor.vendor_no,
                    invoice_number=created.number,
                    bc_invoice_id=created.id,
                    detail=f"Created purchase invoice {created.number} in Business Central.",
                )
        except Exception as exc:  # noqa: BLE001 - surface any BC failure
            logger.exception("Business Central update failed")
            return ProcessingResult(
                status=ProcessingStatus.BC_UPDATE_FAILED,
                vendor_no=vendor.vendor_no,
                invoice_number=document.invoice_number,
                detail=f"Business Central update failed: {exc}",
                errors=[str(exc)],
            )

        logger.info("Processed invoice %s for vendor %s", result.invoice_number, vendor.vendor_no)
        return result
