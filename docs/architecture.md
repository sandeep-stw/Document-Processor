# Solution Architecture

## Goal

Receive documents (invoices, credit memos) from **selected vendors** by email,
extract the data automatically, and **update the purchase document (PC) in
Microsoft Dynamics 365 Business Central** — without manual data entry.

## End-to-end flow

```
 Vendor                                Your tenant
 ┌────────┐   email + PDF     ┌──────────────────────────────────────────────────┐
 │ Vendor │ ────────────────▶ │ 1. Outlook shared mailbox (vendor-invoices@…)    │
 └────────┘                   │                                                  │
                              │ 2. Power Automate flow (orchestration)           │
                              │    • trigger: When a new email arrives (V3)      │
                              │    • look up sender in the Vendor Store          │
                              │    • unknown vendor → quarantine + notify        │
                              │                                                  │
                              │ 3. Copilot Studio document processing            │
                              │    (AI Builder invoice / custom model)           │
                              │    • invoice number, dates, amounts, lines       │
                              │                                                  │
                              │ 4. Power Apps "Vendor Store" (Dataverse table)   │
                              │    • allow-list: sender domain → BC vendor no.   │
                              │    • maintained by the AP team in a canvas app   │
                              │                                                  │
                              │ 5. Business Central v2.0 API                     │
                              │    • create/update purchaseInvoices              │
                              │    • add purchaseInvoiceLines                    │
                              │    • attach the original document                │
                              │                                                  │
                              │ 6. Notify (Teams/email) + error handling         │
                              └──────────────────────────────────────────────────┘
```

## Component responsibilities

| Component            | Role                                                              | Where defined |
|----------------------|-------------------------------------------------------------------|---------------|
| Outlook / Exchange   | Shared mailbox that receives vendor documents                     | `config/settings.json` (`mailbox`) |
| Power Automate       | Orchestrates trigger → vendor check → extraction → BC update      | `config/power-automate-flow.json` |
| Copilot Studio       | Document processing model that extracts invoice fields            | `src/document_extractor.py` (`CopilotStudioExtractor`) |
| Power Apps           | Canvas app over the Dataverse vendor store table                  | `config/vendors.json` (local mirror) |
| Business Central     | System of record; purchase invoices created/updated via v2.0 API  | `src/business_central.py` |
| Python pipeline      | Reference implementation of the same steps (testable, CI-friendly)| `src/pipeline.py` |

## Why a Python pipeline alongside the low-code flow?

The Power Platform components are configured, not compiled. The Python package
in `src/` implements the identical decision logic so it can be:

* **unit-tested** (`tests/`) and run in CI,
* used to **replay `.eml` files** locally during development,
* deployed later as an Azure Function behind the same Power Automate flow if
  you outgrow pure low-code.

## Data flow contract

1. **Trigger payload** — Power Automate sends `From`, `Subject`, attachments.
2. **Vendor match** — sender address/domain must exist in the vendor store,
   otherwise the message is skipped/quarantined (`skipped_unknown_vendor`).
3. **Extraction result** — `ExtractedDocument` (invoice number, dates,
   currency, total, lines) with a confidence score.
4. **BC upsert** — `GET purchaseInvoices?$filter=number eq '…'`; create when
   missing (idempotency), add lines, attach the source document.
5. **Outcome** — `ProcessingResult` status is logged and surfaced to Teams.

## Failure handling

| Failure                          | Behavior |
|----------------------------------|----------|
| Unknown/inactive vendor          | Skip; move message to Quarantine; result `skipped_unknown_vendor` |
| No supported attachment          | Skip with `skipped_no_attachment` |
| Extraction error / no invoice no.| `extraction_failed`; notify AP for manual entry |
| Business Central error           | `bc_update_failed`; retry policy on the flow; notify AP |

## Security notes

* Only senders on the vendor allow-list are processed (address + domain match).
* Secrets are never stored in the repo: `config/settings.json` references the
  **name** of an environment variable (e.g. `BC_CLIENT_SECRET`); values come
  from Azure Key Vault or Power Platform environment variables.
* Business Central access uses OAuth client credentials (Microsoft Entra ID
  app registration) scoped to the BC API — see `docs/setup-guide.md`.
