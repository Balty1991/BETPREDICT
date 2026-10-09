import json
from datetime import datetime, timezone

import pytest
import requests

from betpredict.ingest.bsd_client import endpoint_key, is_paid_only, normalize_path
from betpredict.ingest.errors import (
    BSDAuthError, BSDBadRequest, BSDError, BudgetExceeded, EndpointNotEntitled, PaidEndpointBlocked, QuotaExhausted,
)
from betpredict.ingest.quota import PRIORITY_HIGH, QuotaTracker, parse_ratelimit

from .conftest import FakeResp


def test_paths_and_paid_detection():
    assert normalize_path("/api/v2/events/12/odds") == "events/12/odds/"
    assert normalize_path("https://sports.bzzoiro.com/api/v2/odds/best/?x=1") == "odds/best/"
    assert endpoint_key("events/123/odds/comparison/") == "events/{id}/odds/comparison/"
    assert is_paid_only("odds/best/")
    assert is_paid_only("/api/v2/events/55/odds/comparison/")
    assert is_paid_only("odds/", {"bookmaker_slug": "pinnacle"})
    assert not is_paid_only("odds/", {"market": "1x2"})
    assert not is_paid_only("events/55/odds/")


def test_api_key_only_from_env_and_sent_as_token_header(make_client):
    client, session = make_client({"events/": [FakeResp(200, {"results": []})]})
    client.get("events/")
    assert session.calls[0]["headers"]["Authorization"] == "Token secret-test-key-123"
    assert "secret-test-key-123" not in repr(client)


def test_no_key_means_no_auth_header(make_client):
    client, session = make_client({"events/": [FakeResp(200, {})]}, env={"BSD_API_KEY": ""})
    assert not client.has_key
    client.get("events/")
    assert "Authorization" not in session.calls[0]["headers"]


def test_paid_endpoints_blocked_locally_on_free(make_client):
    client, session = make_client({"odds/best/": [FakeResp(200, {})]})
    with pytest.raises(PaidEndpointBlocked):
        client.get("odds/best/", {"market": "1x2"})
    with pytest.raises(PaidEndpointBlocked):
        client.get("events/9/odds/comparison/")
    assert session.calls == []  # zero cereri consumate
    assert client.quota.state.local_count == 0
    assert client.stats["blocked_paid"] == 2


def test_paid_endpoints_allowed_on_unlimited(make_client):
    client, session = make_client({"odds/best/": [FakeResp(200, {"results": [1]})]}, env={"BSD_PLAN": "unlimited"})
    assert client.get("odds/best/", {"market": "1x2"}) == {"results": [1]}
    assert len(session.calls) == 1


def test_rate_limited_429_is_retried_after_retry_after(make_client):
    client, session = make_client({"events/": [
        FakeResp(429, {"code": "rate_limited"}, {"Retry-After": "1"}),
        FakeResp(200, {"ok": True}),
    ]})
    assert client.get("events/") == {"ok": True}
    assert client._sleeps == [1.0]
    assert len(session.calls) == 2
    assert client.quota.state.local_count == 2  # ambele cereri contează în buget


def test_taster_exhausted_stops_everything(make_client):
    client, session = make_client({"events/": [
        FakeResp(429, {"code": "taster_exhausted"}, {"Retry-After": "3600", "RateLimit": '"football";r=0;t=3600'}),
    ]})
    with pytest.raises(QuotaExhausted):
        client.get("events/")
    assert client.quota.state.exhausted
    with pytest.raises(BudgetExceeded):
        client.get("events/", priority=PRIORITY_HIGH)
    assert len(session.calls) == 1


def test_server_errors_retry_with_backoff_then_fail(make_client):
    client, session = make_client({"events/": [FakeResp(503, {"detail": "down"})]})
    with pytest.raises(BSDError) as e:
        client.get("events/")
    assert e.value.status == 503
    assert len(session.calls) == client.settings.max_retries + 1
    assert len(client._sleeps) == client.settings.max_retries


def test_network_error_then_success(make_client):
    client, session = make_client({"events/": [requests.ConnectionError("boom"), FakeResp(200, {"ok": 1})]})
    assert client.get("events/") == {"ok": 1}


def test_403_not_entitled_is_remembered(make_client):
    client, session = make_client({"odds/value/": [FakeResp(403, {"code": "bookmakers_not_entitled"})]})
    with pytest.raises(EndpointNotEntitled):
        client.get("odds/value/")
    with pytest.raises(EndpointNotEntitled):
        client.get("odds/value/")
    assert len(session.calls) == 1
    assert client.quota.state.not_entitled == {"odds/value/": "bookmakers_not_entitled"}


def test_404_returns_none_400_and_401_raise(make_client):
    client, _ = make_client({
        "events/1/": [FakeResp(404, {})],
        "events/": [FakeResp(400, {"detail": "Unknown query parameter(s): league"})],
        "leagues/": [FakeResp(401, {})],
    })
    assert client.get("events/1/") is None
    with pytest.raises(BSDBadRequest):
        client.get("events/", {"league": 1})
    with pytest.raises(BSDAuthError):
        client.get("leagues/")


def test_ratelimit_headers_update_remaining_and_reserve_blocks(make_client):
    client, session = make_client({"events/": [
        FakeResp(200, {}, {"RateLimit": '"football";r=501;t=100', "RateLimit-Policy": '"football";q=7500;w=86400'}),
    ]})
    client.get("events/")
    assert client.quota.state.server_remaining == 501
    assert client.quota.state.server_quota == 7500
    # rămân 501, rezerva normală e 500 → o cerere normală ar coborî la 500: permisă o dată
    client.quota.state.server_remaining = 500
    with pytest.raises(BudgetExceeded):
        client.get("events/")
    client.get("events/", priority=PRIORITY_HIGH)  # decontarea poate intra în rezervă


def test_max_requests_per_run(make_client):
    client, session = make_client({"events/": [FakeResp(200, {})]}, settings_kwargs={"max_requests_per_run": 2})
    client.get("events/")
    client.get("events/")
    with pytest.raises(BudgetExceeded):
        client.get("events/")
    assert len(session.calls) == 2


def test_pagination_follows_next(make_client):
    client, session = make_client({
        "events/": [FakeResp(200, {"count": 3, "next": "https://sports.bzzoiro.com/api/v2/events/?limit=2&offset=2",
                                   "results": [{"id": 1}, {"id": 2}]})],
        "events/?limit=2&offset=2": [FakeResp(200, {"count": 3, "next": None, "results": [{"id": 3}]})],
    })
    assert [r["id"] for r in client.paginate("events/", {"date_from": "2026-10-09"}, page_size=2)] == [1, 2, 3]
    assert session.calls[0]["params"] == {"date_from": "2026-10-09", "limit": 2}
    assert session.calls[1]["params"] is None


def test_external_next_url_refused(make_client):
    client, _ = make_client({"events/": [FakeResp(200, {"next": "https://evil.example/steal", "results": []})]})
    with pytest.raises(BSDError):
        list(client.paginate("events/"))


def test_disk_cache_avoids_spending_quota(make_client):
    client, session = make_client({"leagues/": [FakeResp(200, {"results": [{"id": 17}]})]})
    a = client.get("leagues/", cache_ttl=3600)
    b = client.get("leagues/", cache_ttl=3600)
    assert a == b
    assert len(session.calls) == 1
    assert client.stats["cache_hits"] == 1


def test_quota_persists_and_rolls_over_utc_day(tmp_path):
    day1 = datetime(2026, 10, 9, 23, 0, tzinfo=timezone.utc)
    q = QuotaTracker(tmp_path / "q.json", daily_quota=7500, reserve=500, clock=lambda: day1)
    q.record_request("events/")
    q.save()
    again = QuotaTracker(tmp_path / "q.json", daily_quota=7500, reserve=500, clock=lambda: day1)
    assert again.state.local_count == 1
    assert json.loads((tmp_path / "q.json").read_text())["effective_remaining"] == 7499
    day2 = datetime(2026, 10, 10, 0, 1, tzinfo=timezone.utc)
    rolled = QuotaTracker(tmp_path / "q.json", daily_quota=7500, reserve=500, clock=lambda: day2)
    assert rolled.state.local_count == 0


def test_parse_ratelimit():
    assert parse_ratelimit('"football";r=7213;t=52800') == {"r": 7213, "t": 52800}
    assert parse_ratelimit("") == {}


def test_paid_plan_without_headers_is_unlimited(tmp_path):
    q = QuotaTracker(None, daily_quota=0, reserve=500)
    assert q.effective_remaining() is None
    assert q.check(10_000) is None
