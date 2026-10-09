from pathlib import Path

from betpredict.publish.site import scan_for_secrets

ROOT = Path(__file__).resolve().parents[2]


def test_frontend_never_sends_bsd_key():
    assert scan_for_secrets(ROOT / "frontend" / "src") == []


def test_bsd_api_ts_has_no_auth_header():
    src = (ROOT / "frontend" / "src" / "services" / "bsdApi.ts").read_text(encoding="utf-8")
    assert "Authorization" not in src
    assert "setApiToken" not in src
