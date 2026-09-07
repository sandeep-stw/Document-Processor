# Setup Guide

Step-by-step setup of the vendor document processing solution.
Estimated effort: 1–2 days including sandbox testing.

## Prerequisites

* Microsoft 365 with Exchange Online (for the shared mailbox)
* Power Automate + Copilot Studio licenses (per-user or per-flow)
* Power Apps license (for the vendor store canvas app)
* Business Central online with a sandbox environment for testing
* Entra ID permission to register an application

## 1. Outlook — shared vendor mailbox

1. In the Microsoft 365 admin center create a **shared mailbox**, e.g.
   `vendor-invoices@yourcompany.com`.
2. Give the service account used by Power Automate **Full Access** and
   **Send As** permissions.
3. Create mailbox folders: `Processed`, `Quarantine`, `Failed`.
4. Tell your selected vendors to send invoices to this address (PDF or image).

## 2. Power Apps — vendor store

1. In the Power Apps maker portal, create a Dataverse table, e.g.
   `cr123_vendor` with columns:
   `name`, `emailaddress`, `emaildomain`, `bc_vendornumber`,
   `currencycode`, `active`.
2. Build a **canvas app** on that table so the AP team can maintain the
   allow-list (add/deactivate vendors).
3. Keep `config/vendors.json` in this repo in sync as the local mirror used
   by the Python pipeline.

## 3. Copilot Studio — document processing

1. Open Copilot Studio → **Document processing** (AI Builder).
2. Either:
   * use the prebuilt **Invoice processing** model, or
   * train a **custom document model** on 5–15 samples per vendor layout
     (fields: invoice number, invoice date, due date, PO number, currency,
     total, line items).
3. Publish the model and copy its invocation endpoint/ID into
   `config/settings.json` (`copilot_studio_endpoint`) or the flow action
   (`<copilot-studio-document-model-id>` in `config/power-automate-flow.json`).

## 4. Business Central — API access

1. In Entra ID, register an application (client credentials):
   * API permissions → Dynamics 365 Business Central →
     `API.ReadWrite.All` (application) + `Automation.ReadWrite.All` if you
     plan to post invoices via automation APIs.
   * Grant admin consent, then create a client secret.
2. In Business Central:
   * **Microsoft Entra Applications** page → add the app, assign permission
     set `D365 BUS FULL ACCESS` (or a least-privilege custom set).
3. Record in `config/settings.json`:
   * `bc_environment` (e.g. `sandbox`, `production`)
   * `bc_company` (exact company name, e.g. `CRONUS International Ltd.`)
   * `bc_tenant_id`, `bc_client_id`
4. Store the client secret in the `BC_CLIENT_SECRET` environment variable
   (locally) or a Power Platform environment variable / Key Vault reference
   (in the flow). **Never commit the secret.**

## 5. Power Automate — orchestration flow

1. Create an automated cloud flow with trigger
   **When a new email arrives (V3)** on the shared mailbox
   (`Only with attachments = Yes`, `Include attachments = Yes`).
2. Add the actions from `config/power-automate-flow.json`:
   1. **List rows** (Dataverse) — find the vendor by sender domain.
   2. **Condition** — unknown sender → move mail to `Quarantine`, terminate.
   3. **Copilot Studio document processing** — extract invoice fields.
   4. **Business Central → Create record** (`purchaseInvoices`) with the
      extracted fields and `bc_vendornumber`.
   5. Add **purchase invoice lines** and **attach** the original file.
   6. **Post a Teams message** to the AP channel on success.
3. Configure **run-after** error handling on the BC action to email AP on
   failure and move the message to `Failed`.
4. Test with a sandbox environment before switching `bc_environment` to
   `production`.

## 6. Run the Python pipeline locally

```bash
pip install -r requirements-dev.txt   # test tooling only; runtime is stdlib-only

# process one email end-to-end without touching Business Central
python -m src.main --eml samples/vendor-invoice.eml --dry-run --verbose

# run the tests
pytest
```

Environment variables for a real (non-dry-run) run:

| Variable                   | Purpose                              |
|----------------------------|--------------------------------------|
| `BC_CLIENT_SECRET`         | Client secret of the BC app registration |
| `POWER_AUTOMATE_WEBHOOK_URL` | Optional callback to the flow      |

## 7. Go-live checklist

- [ ] Vendors loaded into the Power Apps vendor store and marked active
- [ ] Document model published with acceptable confidence on real samples
- [ ] Flow tested end-to-end in the sandbox company
- [ ] Error notifications verified (send a bad invoice)
- [ ] `bc_environment` switched to `production`
- [ ] Mailbox rules monitored for the first week
