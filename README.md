# Document-Processor

Customer document processing for Microsoft Dynamics 365 Business Central:
receive documents from **selected vendors** by email, extract the data with AI,
and **update the purchase document (PC) in Business Central** — automatically.

Built with **Outlook** (shared mailbox), **Power Automate** (orchestration),
**Copilot Studio** (document processing / AI Builder), **Power Apps**
(vendor store) and the **Business Central v2.0 API**. A Python pipeline
mirrors the low-code logic so it can be tested and run anywhere.

## Architecture

```
Vendor email ─▶ Outlook shared mailbox ─▶ Power Automate flow
                                             │
              unknown vendor ──▶ Quarantine  │ vendor store (Power Apps / Dataverse)
                                             ▼
                              Copilot Studio document processing
                                             │  invoice no, dates, amounts, lines
                                             ▼
                        Business Central purchaseInvoices (create + attach)
                                             ▼
                                 Teams / email notification
```

Details: [docs/architecture.md](docs/architecture.md) ·
Setup: [docs/setup-guide.md](docs/setup-guide.md)

## Repository layout

| Path                            | Purpose |
|---------------------------------|---------|
| `config/vendors.json`           | Vendor allow-list (sender → BC vendor no.); mirrors the Power Apps vendor store |
| `config/settings.json`          | Mailbox, Business Central environment/company, endpoint settings |
| `config/power-automate-flow.json` | Power Automate flow definition template |
| `src/`                          | Processing pipeline (stdlib-only Python) |
| `src/email_ingestor.py`         | Parse vendor emails (`.eml`) with attachments |
| `src/vendor_store.py`           | Vendor allow-list matching (address / domain) |
| `src/document_extractor.py`     | Copilot Studio extractor + deterministic fallback |
| `src/business_central.py`       | Business Central v2.0 API client (OAuth + purchaseInvoices) |
| `src/pipeline.py`               | Orchestration: vendor check → extract → update BC |
| `src/main.py`                   | CLI entry point |
| `tests/`                        | pytest suite for all of the above |
| `docs/`                         | Architecture and setup guide |

## Quick start

```bash
pip install -r requirements-dev.txt

# Process one vendor email without touching Business Central
python -m src.main --eml path/to/message.eml --dry-run

# Run the test suite
pytest
```

A real run needs the Business Central app secret in the environment
(see the [setup guide](docs/setup-guide.md#6-run-the-python-pipeline-locally)):

```bash
export BC_CLIENT_SECRET="<from Key Vault>"
python -m src.main --eml path/to/message.eml
```

## How a document flows through the code

1. `parse_eml` reads the message and its attachments.
2. `VendorStore.find_by_sender` checks the sender against the allow-list —
   unknown vendors are skipped (`skipped_unknown_vendor`).
3. `get_extractor` picks the Copilot Studio endpoint when configured,
   otherwise the regex fallback extractor.
4. `BusinessCentralClient` looks up the invoice by number (idempotency),
   creates the `purchaseInvoices` record plus lines when missing, and
   attaches the original document.
5. `ProcessingResult` reports `processed` / `skipped_*` / `*_failed`.
