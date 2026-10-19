"""Repeated searches reduce public requests without mixing filters or hiding age."""
from copy import deepcopy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from job_finder.linkedin_cache import LinkedInResultCache, LinkedInSearchBusy


def settings(role="engineer"):
    return {"search": {"keywords": [role], "start_date": "2026-10-01", "end_date": "2026-10-19"},
            "sources": {"linkedin": {"enabled": True, "max_pages": 1}}}


def result(jobs=None, error=None):
    return {"jobs": jobs if jobs is not None else [{"title": "Engineer"}],
            "fetched": {"LinkedIn": 1}, "source_statuses": {"LinkedIn": "failed" if error else "ok"},
            "errors": {"LinkedIn": error} if error else {}, "warnings": {}}


def test_repeated_query_reuses_results_and_keeps_original_snapshot():
    cache = LinkedInResultCache()
    first = cache.run(settings(), result)
    first["jobs"].clear()
    reused = cache.run(settings(), lambda: pytest.fail("Fetched a recent query again"))
    assert reused["jobs"] == [{"title": "Engineer"}]
    assert reused["cache_info"]["cached"]
    assert reused["cache_info"]["fetched_at"] == first["cache_info"]["fetched_at"]
    assert "fetched at" in reused["warnings"]["LinkedIn"][0]


@pytest.mark.parametrize("change", ["role", "date", "location", "remote"])
def test_changed_filters_require_a_new_search(change):
    cache = LinkedInResultCache()
    cache.run(settings(), result)
    other = deepcopy(settings())
    if change == "role": other["search"]["keywords"] = ["designer"]
    if change == "date": other["search"]["start_date"] = "2026-10-18"
    if change == "location": other["search"]["location"] = "Canada"
    if change == "remote": other["search"]["remote_only"] = False
    fresh = cache.run(other, lambda: result(jobs=[]))
    assert fresh["jobs"] == []
    assert not fresh["cache_info"]["cached"]


def test_rate_limit_reuses_stale_results_with_age_and_retry():
    now = [0]
    cache = LinkedInResultCache(clock=lambda: now[0])
    cache.run(settings(), result)
    now[0] = 601
    limited = cache.run(settings(), lambda: result([], "HTTP 429: Wait at least 420 seconds"))
    assert limited["jobs"]
    assert limited["errors"]["LinkedIn"].startswith("HTTP 429")
    assert limited["cache_info"]["age_seconds"] == 601
    assert limited["retry_after_seconds"] == 420
    now[0] = 86401
    expired = cache.run(settings(), lambda: result([], "HTTP 429"))
    assert expired["jobs"] == []
    assert "cache_info" not in expired


def test_successful_empty_search_replaces_stale_jobs_and_failures_are_not_cached():
    now = [0]
    cache = LinkedInResultCache(clock=lambda: now[0])
    cache.run(settings(), lambda: result([], "network unavailable"))
    assert cache.run(settings(), result)["jobs"]
    now[0] = 601
    cache.run(settings(), lambda: result([]))
    assert cache.run(settings(), lambda: pytest.fail("Fetched cached empty results"))["jobs"] == []


def test_detail_rate_limit_does_not_replace_saved_jobs_with_empty_filtered_results():
    now = [0]
    cache = LinkedInResultCache(clock=lambda: now[0])
    cache.run(settings(), result)
    now[0] = 601
    partial = result([])
    partial["source_statuses"]["LinkedIn"] = "partial"
    partial["warnings"]["LinkedIn"] = ["HTTP 429. Wait at least 300 seconds. Stopped description checks"]
    reused = cache.run(settings(), lambda: partial)
    assert reused["jobs"]
    assert reused["cache_info"]["age_seconds"] == 601
    assert reused["retry_after_seconds"] == 300
    assert any("Stopped description checks" in warning for warning in reused["warnings"]["LinkedIn"])


def test_concurrent_searches_are_rejected_or_use_the_matching_cache():
    now = [0]
    cache = LinkedInResultCache(clock=lambda: now[0])
    cache.run(settings(), result)
    now[0] = 601
    cache.request_lock.acquire()
    try:
        with pytest.raises(LinkedInSearchBusy):
            cache.run(settings("designer"), lambda: pytest.fail("Concurrent fetch"))
        assert cache.run(settings(), lambda: pytest.fail("Concurrent fetch"))["cache_info"]["cached"]
    finally:
        cache.request_lock.release()


def test_fetch_exception_releases_request_lock():
    cache = LinkedInResultCache()
    def fail(): raise RuntimeError("network failure")
    with pytest.raises(RuntimeError): cache.run(settings(), fail)
    assert cache.run(settings(), result)["jobs"]
