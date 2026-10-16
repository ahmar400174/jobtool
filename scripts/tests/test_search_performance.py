"""Regression checks for concurrent search and complete platform accounting."""
import json
import sys
from pathlib import Path
from threading import Barrier, Event, Lock
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from job_finder.aggregator import fetch_all
from job_finder.models import JobListing
from job_finder.report import save_search_report
from job_finder.source_catalog import SOURCES
from job_finder.sources.linkedin import fetch_linkedin
from job_finder.sources.jobicy import fetch_jobicy


def settings_for(*keys):
    return {"sources": {key: {"enabled": key in keys} for key, _, _ in SOURCES},
            "performance": {"source_workers": 2}}


def test_sources_overlap_and_progress_reports_each_completion():
    barrier = Barrier(2)
    events = []
    def fetch(key, search, cfg):
        barrier.wait(timeout=3)  # A serial implementation breaks this barrier.
        return []
    with patch("job_finder.aggregator.fetch_public", side_effect=fetch):
        _, counts = fetch_all(settings_for("wellfound", "arc"), events.append)
    assert not counts.errors
    assert {e["source"] for e in events} == {"Wellfound", "Arc"}
    assert [e["completed"] for e in events] == [1, 2]
    assert all(e["total"] == 2 for e in events)
    assert counts.statuses["LinkedIn"] == "disabled"


def test_all_default_platforms_attempted_even_when_one_fails():
    attempted = []
    lock = Lock()
    def fetch(key, search, cfg):
        with lock:
            attempted.append(key)
        if key == "arc":
            raise RuntimeError("HTTP 403")
        if key == "remotive":
            cfg.setdefault("_warnings", []).append("Recent feed only")
        return []
    with patch("job_finder.aggregator._fetch_source", side_effect=fetch):
        _, counts = fetch_all({})
    assert sorted(attempted) == sorted(key for key, _, _ in SOURCES)
    assert len(counts) == len(counts.statuses) == len(SOURCES) == 13
    assert counts.errors == {"Arc": "HTTP 403"}
    assert counts.statuses["Arc"] == "failed"
    assert counts.statuses["Remotive"] == "partial"
    assert all(s != "pending" for s in counts.statuses.values())


def test_warning_state_does_not_leak_between_searches():
    settings = settings_for("himalayas")
    def fetch(key, search, cfg):
        cfg.setdefault("_warnings", []).append("Page limit")
        return []
    with patch("job_finder.aggregator.fetch_public", side_effect=fetch):
        for _ in range(2):
            _, counts = fetch_all(settings)
            assert counts.warnings["Himalayas"] == ["Page limit"]
    assert "_warnings" not in settings["sources"]["himalayas"]


def test_duplicate_choice_is_stable_when_platforms_finish_in_reverse_order():
    later_source_done = Event()
    def fetch(key, search, cfg):
        if key == "wellfound":
            assert later_source_done.wait(timeout=3)
        else:
            later_source_done.set()
        return [JobListing(title="QA Engineer", company="Acme", location="Worldwide", remote="Remote",
                           posted="2026-09-01", url=f"https://example.com/{key}",
                           source="Wellfound" if key == "wellfound" else "Wellfound Remote Jobs")]
    with patch("job_finder.aggregator.fetch_public", side_effect=fetch):
        jobs, counts = fetch_all(settings_for("wellfound", "wellfound_remote"))
    assert len(jobs) == 1
    assert jobs[0].source == "Wellfound"
    assert counts.filters["Wellfound Remote Jobs"]["duplicates"] == 1


def card(job_id, posted="2026-09-01"):
    return f'''<li><div data-entity-urn="urn:li:jobPosting:{job_id}">
        <h3 class="base-search-card__title">QA Engineer</h3>
        <h4 class="base-search-card__subtitle">Acme {job_id}</h4>
        <span class="job-search-card__location">United States</span>
        <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/{job_id}">Apply</a>
        <time datetime="{posted}"></time></div></li>'''


def response(html):
    return type("Response", (), {"status_code": 200, "text": html})()


def test_linkedin_details_overlap_without_skipping_verification():
    barrier = Barrier(2)
    def detail(job_id):
        barrier.wait(timeout=3)
        return "This position is fully remote. Selenium testing."
    html = card("12345678") + card("12345679") + card("12345678") + card("12345680", "2025-01-01")
    with patch("job_finder.sources.linkedin.requests.get", return_value=response(html)), \
            patch("job_finder.sources.linkedin._fetch_job_description", side_effect=detail) as fetch:
        jobs = fetch_linkedin(["QA Engineer"], "Worldwide", max_pages=1, detail_delay=0,
                              detail_workers=2, start_date="2026-09-01", end_date="2026-09-30")
    assert fetch.call_count == 2
    assert len(jobs) == 3
    assert [j.remote for j in jobs[:2]] == ["Remote", "Remote"]
    assert jobs[-1].description == ""


def test_linkedin_detail_requests_keep_spacing():
    current = [0.0]
    starts = []
    def sleep(seconds):
        current[0] += seconds
    def detail(job_id):
        starts.append(current[0])
        return "Fully remote"
    with patch("job_finder.sources.linkedin.requests.get", return_value=response(card("12345678") + card("12345679"))), \
            patch("job_finder.sources.linkedin.time.monotonic", side_effect=lambda: current[0]), \
            patch("job_finder.sources.linkedin.time.sleep", side_effect=sleep), \
            patch("job_finder.sources.linkedin._fetch_job_description", side_effect=detail):
        fetch_linkedin(["QA Engineer"], "Worldwide", max_pages=1, detail_delay=0.6, detail_workers=1)
    assert starts == [0.0, 0.6]


def test_linkedin_old_page_ends_query_and_missing_details_warn():
    warnings = []
    pages = [response(card("12345678")), response(card("12345679", "2025-01-01"))]
    with patch("job_finder.sources.linkedin.requests.get", side_effect=pages) as get, \
            patch("job_finder.sources.linkedin._fetch_job_description", return_value="") as detail:
        fetch_linkedin(["QA Engineer"], "Worldwide", max_pages=15, delay=0, detail_delay=0,
                       start_date="2026-09-01", warnings=warnings)
    assert get.call_count == 2
    assert detail.call_count == 1
    assert any("Descriptions unavailable" in w for w in warnings)


def test_remoteok_does_not_sleep_between_feed_records():
    from job_finder.sources.remoteok import fetch_remoteok
    response = type("Response", (), {"raise_for_status": lambda self: None,
        "json": lambda self: [{"legal": "terms"}] + [
            {"position": "QA Engineer", "url": f"https://example.com/{i}"} for i in range(100)]})()
    with patch("job_finder.sources.remoteok.requests.get", return_value=response), \
            patch("time.sleep", side_effect=AssertionError("Unnecessary processing delay")):
        assert len(fetch_remoteok()) == 100


def test_jobicy_failures_are_not_reported_as_successful_empty_search():
    import requests
    with patch("job_finder.sources.jobicy.requests.get", side_effect=requests.Timeout("timed out")), \
            patch("job_finder.sources.jobicy.time.sleep"):
        with pytest.raises(RuntimeError, match="Jobicy queries failed"):
            fetch_jobicy(["qa"])


def test_jobicy_keeps_successful_queries_and_warns_about_failures():
    import requests
    good = type("Response", (), {"status_code": 200, "json": lambda self: {"jobs": []}})()
    warnings = []
    with patch("job_finder.sources.jobicy.requests.get", side_effect=[requests.Timeout("timed out"), good]), \
            patch("job_finder.sources.jobicy.time.sleep"):
        assert fetch_jobicy(["qa", "sdet"], warnings=warnings) == []
    assert "results are partial" in warnings[0]


def test_jobicy_expands_invalid_two_character_qa_keyword():
    good = type("Response", (), {"status_code": 200, "json": lambda self: {"jobs": []}})()
    with patch("job_finder.sources.jobicy.requests.get", return_value=good) as get, \
            patch("job_finder.sources.jobicy.time.sleep"):
        fetch_jobicy(["qa"])
    assert get.call_args.kwargs["params"]["tag"] == "quality assurance"


def test_report_accounts_for_disabled_failed_and_partial_platforms(tmp_path):
    def fetch(key, search, cfg):
        if key == "arc":
            raise RuntimeError("Sign-in required")
        cfg.setdefault("_warnings", []).append("Public page only")
        return []
    settings = settings_for("wellfound", "arc")
    settings["output"] = {"directory": str(tmp_path)}
    with patch("job_finder.aggregator.fetch_public", side_effect=fetch):
        jobs, counts = fetch_all(settings)
    report = json.loads(save_search_report(settings, jobs, counts).read_text())
    assert report["source_statuses"]["Wellfound"] == "partial"
    assert report["source_statuses"]["Arc"] == "failed"
    assert report["source_statuses"]["LinkedIn"] == "disabled"
    assert set(report["source_seconds"]) == {"Wellfound", "Arc"}
    assert report["unique_matches"] == 0


def test_gui_saves_report_for_empty_search_before_notifying_user(tmp_path):
    from gui import JobFinderApp
    app = JobFinderApp.__new__(JobFinderApp)
    callbacks = []
    app._ui = callbacks.append
    app._on_empty = lambda: None
    settings = settings_for()
    settings["output"] = {"directory": str(tmp_path)}
    with patch("job_finder.config.load_settings", return_value=settings):
        app._run_fetch()
    assert (tmp_path / "latest_search_report.json").exists()
    assert callbacks[-1] == app._on_empty


def test_filter_decisions_do_not_print_unicode_job_titles(capsys):
    from job_finder.filters import apply_filters
    jobs = [JobListing(title="QA Engineer 日本", company="Acme", location="Remote", remote="Remote",
                       posted="2025-01-01", url="https://example.com/1", source="LinkedIn")]
    assert not apply_filters(jobs, {"search": {"start_date": "2026-09-01"}})
    assert "日本" not in capsys.readouterr().out
