"""Environment settings for the document processing pipeline.

Settings are loaded from a JSON file (default ``config/settings.json``).
Secrets are never stored in the file; they are referenced by environment
variable name and resolved at runtime.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_SETTINGS_PATH = Path(__file__).resolve().parent.parent / "config" / "settings.json"


@dataclass(frozen=True)
class Settings:
    """Runtime settings for the pipeline."""

    mailbox: str
    vendor_store_path: str
    bc_base_url: str
    bc_environment: str
    bc_company: str
    bc_tenant_id: str
    bc_client_id: str
    bc_client_secret_env: str = "BC_CLIENT_SECRET"
    copilot_studio_endpoint: str = ""
    power_automate_webhook_env: str = "POWER_AUTOMATE_WEBHOOK_URL"
    required_attachment_extensions: tuple[str, ...] = (".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff")
    extra: dict = field(default_factory=dict)

    @property
    def bc_api_url(self) -> str:
        """Base URL of the Business Central v2.0 API for the configured environment."""
        base = self.bc_base_url.rstrip("/")
        return f"{base}/v2.0/{self.bc_environment}/api/v2.0"

    def resolve_secret(self, env_var: str) -> str:
        """Read a secret from the environment; raises if it is missing."""
        value = os.environ.get(env_var, "")
        if not value:
            raise RuntimeError(
                f"Required secret environment variable '{env_var}' is not set. "
                "Set it locally or store it in Azure Key Vault / a Power Automate "
                "environment variable in production."
            )
        return value


def load_settings(path: str | os.PathLike | None = None) -> Settings:
    """Load settings from JSON, falling back to the repo default."""
    settings_path = Path(path) if path else DEFAULT_SETTINGS_PATH
    with open(settings_path, "r", encoding="utf-8") as handle:
        raw = json.load(handle)

    known = {
        "mailbox",
        "vendor_store_path",
        "bc_base_url",
        "bc_environment",
        "bc_company",
        "bc_tenant_id",
        "bc_client_id",
        "bc_client_secret_env",
        "copilot_studio_endpoint",
        "power_automate_webhook_env",
        "required_attachment_extensions",
    }
    extra = {key: value for key, value in raw.items() if key not in known}
    extensions = raw.get("required_attachment_extensions")
    default_extensions = (".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff")
    return Settings(
        mailbox=raw.get("mailbox", ""),
        vendor_store_path=raw.get("vendor_store_path", "config/vendors.json"),
        bc_base_url=raw.get("bc_base_url", "https://api.businesscentral.dynamics.com"),
        bc_environment=raw.get("bc_environment", "production"),
        bc_company=raw.get("bc_company", ""),
        bc_tenant_id=raw.get("bc_tenant_id", ""),
        bc_client_id=raw.get("bc_client_id", ""),
        bc_client_secret_env=raw.get("bc_client_secret_env", "BC_CLIENT_SECRET"),
        copilot_studio_endpoint=raw.get("copilot_studio_endpoint", ""),
        power_automate_webhook_env=raw.get("power_automate_webhook_env", "POWER_AUTOMATE_WEBHOOK_URL"),
        required_attachment_extensions=tuple(e.lower() for e in extensions)
        if extensions
        else default_extensions,
        extra=extra,
    )
