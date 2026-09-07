import json

import pytest

from src.settings import Settings, load_settings


def test_load_settings_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "mailbox": "ap@example.com",
                "bc_environment": "sandbox",
                "bc_company": "CRONUS",
                "bc_tenant_id": "t",
                "bc_client_id": "c",
            }
        ),
        encoding="utf-8",
    )
    settings = load_settings(path)
    assert settings.mailbox == "ap@example.com"
    assert settings.bc_environment == "sandbox"
    assert settings.bc_base_url == "https://api.businesscentral.dynamics.com"
    assert settings.bc_client_secret_env == "BC_CLIENT_SECRET"
    assert ".pdf" in settings.required_attachment_extensions
    assert settings.bc_api_url.endswith("/v2.0/sandbox/api/v2.0")


def test_resolve_secret_requires_env_var(monkeypatch):
    settings = Settings(
        mailbox="m",
        vendor_store_path="v",
        bc_base_url="b",
        bc_environment="e",
        bc_company="c",
        bc_tenant_id="t",
        bc_client_id="c",
    )
    monkeypatch.delenv("BC_CLIENT_SECRET", raising=False)
    with pytest.raises(RuntimeError):
        settings.resolve_secret("BC_CLIENT_SECRET")
    monkeypatch.setenv("BC_CLIENT_SECRET", "s3cr3t")
    assert settings.resolve_secret("BC_CLIENT_SECRET") == "s3cr3t"
