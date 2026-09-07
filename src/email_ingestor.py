"""Email ingestion helpers.

Production ingestion is handled by the Power Automate trigger "When a new
email arrives (V3)" on the shared vendor mailbox, which forwards the message
payload to this pipeline. For local runs and tests we parse standard ``.eml``
files (RFC 822) with the stdlib :mod:`email` package.
"""

from __future__ import annotations

import email
import email.policy
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class EmailAttachment:
    filename: str
    content_type: str
    content: bytes

    @property
    def extension(self) -> str:
        return Path(self.filename).suffix.lower()


@dataclass
class IncomingEmail:
    sender: str
    subject: str
    message_id: str = ""
    body_text: str = ""
    attachments: list[EmailAttachment] = field(default_factory=list)


def parse_eml(path: str | Path) -> IncomingEmail:
    """Parse an .eml file into an :class:`IncomingEmail`."""
    with open(path, "rb") as handle:
        message = email.message_from_bytes(handle.read(), policy=email.policy.default)

    body_text = ""
    attachments: list[EmailAttachment] = []
    for part in message.walk():
        if part.is_multipart():
            continue
        filename = part.get_filename()
        disposition = part.get_content_disposition()
        if filename or disposition == "attachment":
            attachments.append(
                EmailAttachment(
                    filename=filename or "attachment.bin",
                    content_type=part.get_content_type(),
                    content=part.get_payload(decode=True) or b"",
                )
            )
        elif part.get_content_type() == "text/plain" and not body_text:
            body_text = part.get_content()

    return IncomingEmail(
        sender=message.get("From", ""),
        subject=message.get("Subject", ""),
        message_id=message.get("Message-ID", ""),
        body_text=body_text,
        attachments=attachments,
    )
