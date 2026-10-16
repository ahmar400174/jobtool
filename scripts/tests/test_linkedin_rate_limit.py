"""Bounded retries and rate-limit stops use no live network requests."""
import sys
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from unittest.mock import patch

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from job_finder.sources import linkedin
from test_search_performance import card


def response(status=200, html="", retry_after=None):
    result = requests.Response()
    result.status_code = status
    result._content = html.encode()
    result.url = linkedin.SEARCH_URL
    if retry_after is not None:
        result.headers["Retry-After"] = retry_after
    return result


@pytest.fixture(autouse=True)
def fresh_cooldown(monkeypatch):
    monkeypatch.setattr(linkedin, "_cooldown_until", 0)


def test_429_retries_after_server_delay_then_keeps_jobs():
    warnings = []
    with patch.object(linkedin.requests, "get", side_effect=[response(429, retry_after="7"), response(html=card("12345678"))]) as get, \
            patch.object(linkedin.time, "sleep") as sleep:
        jobs = linkedin.fetch_linkedin(["QA Engineer"], "Worldwide", max_pages=1, fetch_details=False, warnings=warnings)
    assert len(jobs) == 1
    assert get.call_count == 2
    sleep.assert_called_once_with(7.0)
    assert any("waiting 7s" in warning for warning in warnings)


def test_persistent_429_has_bounded_backoff_and_blocks_next_search():
    with patch.object(linkedin.requests, "get", return_value=response(429)) as get, \
            patch.object(linkedin.time, "sleep") as sleep:
        with pytest.raises(linkedin.LinkedInRateLimitError, match="HTTP 429"):
            linkedin.fetch_linkedin(["QA Engineer", "SDET"], "Worldwide")
        assert get.call_count == 3
        assert [call.args[0] for call in sleep.call_args_list] == [5.0, 10.0]
        with pytest.raises(linkedin.LinkedInRateLimitError, match="cooling down"):
            linkedin.fetch_linkedin(["QA Engineer"], "Worldwide")
        assert get.call_count == 3


def test_long_retry_after_stops_without_waiting_or_early_retry():
    with patch.object(linkedin.requests, "get", return_value=response(429, retry_after="3600")) as get, \
            patch.object(linkedin.time, "sleep") as sleep:
        with pytest.raises(linkedin.LinkedInRateLimitError, match="3600 seconds"):
            linkedin.fetch_linkedin(["QA Engineer"], "Worldwide")
    assert get.call_count == 1
    sleep.assert_not_called()


def test_retry_after_http_date_and_invalid_header():
    retry_at = datetime.now(timezone.utc) + timedelta(seconds=30)
    assert 28 <= linkedin._retry_after(response(429, retry_after=format_datetime(retry_at)), 5) <= 30
    assert linkedin._retry_after(response(429, retry_after="nonsense"), 5) == 5


def test_search_429_keeps_existing_jobs_and_skips_other_keywords_and_details():
    warnings = []
    with patch.object(linkedin.requests, "get", side_effect=[response(html=card("12345678")), response(429)]) as get, \
            patch.object(linkedin, "_fetch_job_description") as detail:
        jobs = linkedin.fetch_linkedin(["QA Engineer", "SDET"], "Worldwide", max_pages=3, delay=0,
                                       max_retries=0, warnings=warnings)
    assert len(jobs) == 1
    assert get.call_count == 2
    detail.assert_not_called()
    assert any("Keeping 1 fetched listings" in warning for warning in warnings)
    assert any("Description checks skipped" in warning for warning in warnings)


def test_details_stop_after_429_and_keep_card_metadata():
    html = "".join(card(str(12345678 + i)) for i in range(5))
    warnings = []
    with patch.object(linkedin.requests, "get", side_effect=[response(html=html), response(429)]) as get:
        jobs = linkedin.fetch_linkedin(["QA Engineer"], "Worldwide", max_pages=1, detail_delay=0,
                                       detail_workers=1, warnings=warnings)
    assert len(jobs) == 5
    assert get.call_count == 2
    assert any("Stopped description checks" in warning for warning in warnings)


def test_keyword_boundaries_keep_request_spacing():
    with patch.object(linkedin.requests, "get", return_value=response()) as get, \
            patch.object(linkedin.time, "sleep") as sleep:
        linkedin.fetch_linkedin(["QA Engineer", "SDET"], "Worldwide", delay=2)
    assert get.call_count == 2
    sleep.assert_called_once_with(2)
