"""Offline contract tests for public source parsing and integration."""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from job_finder.aggregator import fetch_all
from job_finder.filters import apply_filters
from job_finder.models import JobListing
from job_finder.source_catalog import SOURCES
from job_finder.sources.public_boards import (
    fetch_himalayas, fetch_rss, parse_wellfound, parse_arc, parse_jsonld, fetch_hn,
)
from job_finder.work_type import classify_work_type
import json


class Response:
    def __init__(self, data=None, content=b""):
        self.data, self.content = data, content
    def json(self):
        return self.data


def next_page(props):
    return '<script id="__NEXT_DATA__" type="application/json">' + json.dumps({"props": {"pageProps": props}}) + '</script>'


def job(**overrides):
    values = dict(title="QA Engineer", company="Acme", location="United States", remote="Remote",
                  posted="2026-09-01", url="https://example.com/job", source="Himalayas")
    values.update(overrides)
    return JobListing(**values)


def test_wellfound_resolves_company_and_remote():
    data = {"Job:1": {"__typename": "JobListing", "id": "1", "slug": "qa-engineer", "title": "QA Engineer",
                      "remote": True, "acceptedRemoteLocationNames": ["United States"], "liveStartAt": 1788220800,
                      "startup": {"__ref": "Startup:1"}},
            "Startup:1": {"name": "Acme"}}
    parsed = parse_wellfound(next_page({"apolloState": {"data": data}}), True)
    assert parsed[0].company == "Acme"
    assert parsed[0].remote == "Remote"
    assert parsed[0].source == "Wellfound Remote Jobs"
    assert parsed[0].posted == "2026-09-01"


def test_arc_constructs_actual_detail_url():
    parsed = parse_arc(next_page({"arcJobs": [], "externalJobs": [{"title": "QA Engineer", "urlString": "acme-qa",
        "randomKey": "123", "company": {"name": "Acme"}, "requiredCountries": ["US"]}]}))
    assert parsed[0].url == "https://arc.dev/remote-jobs/details/acme-qa-123"
    assert parsed[0].location == "US"


def test_wellfound_remote_search_result_schema():
    data = {"JobListingSearchResult:1": {"__typename": "JobListingSearchResult", "id": "1", "slug": "qa",
        "title": "QA Engineer", "remote": True, "acceptedRemoteLocationNames": ["US"]},
        "StartupResult:2": {"__typename": "StartupResult", "name": "Acme",
        "highlightedJobListings": [{"__ref": "JobListingSearchResult:1"}]}}
    parsed = parse_wellfound(next_page({"apolloState": {"data": data}}), True)
    assert parsed[0].company == "Acme"
    assert parsed[0].remote == "Remote"


def test_anonymous_companies_do_not_dedupe_distinct_urls():
    assert job(company="Unknown", url="https://example.com/1").dedupe_key != job(company="Unknown", url="https://example.com/2").dedupe_key


def test_jsonld_graph_parses_job_not_categories():
    html = '<script type="application/ld+json">' + json.dumps({"@graph": [{"@type": "JobPosting",
        "title": "QA Engineer", "hiringOrganization": {"name": "Acme"}, "jobLocationType": "TELECOMMUTE",
        "url": "/jobs/1", "datePosted": "2026-09-01", "description": "<p>QA work</p>"}]}) + '</script>'
    parsed = parse_jsonld(html, "Example Board", "https://jobs.example.com")
    assert parsed[0].remote == "Remote"
    assert parsed[0].description == "QA work"
    assert parsed[0].url == "https://jobs.example.com/jobs/1"


def test_rss_preserves_source_links_and_title_company():
    content = b'<rss><channel><item><title>Acme: QA Engineer</title><region>USA</region><link>https://weworkremotely.com/1</link><pubDate>Tue, 01 Sep 2026 00:00:00 GMT</pubDate><description>Testing</description></item></channel></rss>'
    with patch("job_finder.sources.public_boards.get", return_value=Response(content=content)):
        parsed = fetch_rss("We Work Remotely", "https://example.com/feed", remote=True)
    assert parsed[0].title == "QA Engineer"
    assert parsed[0].company == "Acme"
    assert parsed[0].posted == "2026-09-01"


def test_himalayas_stops_repeated_pages_and_passes_country():
    response = Response({"jobs": [{"title": "QA Engineer", "companyName": "Acme", "guid": "https://himalayas.app/jobs/1",
                                  "locationRestrictions": ["United States"], "pubDate": 1788220800}]})
    with patch("job_finder.sources.public_boards.get", return_value=response) as get:
        result = fetch_himalayas({"keywords": ["QA Engineer"], "location": "United States"}, {"max_pages": 3, "delay_seconds": 0})
    assert len(result) == 1
    assert get.call_count == 2
    assert get.call_args.kwargs["params"]["country"] == "United States"


def test_hn_uses_monthly_thread_comments_not_job_stories():
    def get(url, **kwargs):
        if "user/" in url:
            return Response({"submitted": [1, 2]})
        data = {1: {"id": 1, "title": "Ask HN: Who is hiring? (September 2026)", "time": 1788220800, "kids": [3]},
                2: {"id": 2, "title": "Ask HN: Who wants to be hired?", "time": 1788220800},
                3: {"id": 3, "text": "Acme | Remote | QA Engineer<p>Selenium tests</p>", "time": 1788220800}}
        return Response(data[int(url.split('/')[-1].split('.')[0])])
    with patch("job_finder.sources.public_boards.get", side_effect=get):
        parsed = fetch_hn({"keywords": ["QA Engineer"]}, {"months": 1})
    assert parsed[0].company == "Acme"
    assert parsed[0].url == "https://news.ycombinator.com/item?id=3"


def test_source_failure_is_reported_separately():
    settings = {"sources": {key: {"enabled": key == "arc"} for key, _, _ in SOURCES}}
    with patch("job_finder.aggregator.fetch_public", side_effect=RuntimeError("HTTP 403")):
        jobs, counts = fetch_all(settings)
    assert not jobs
    assert counts["Arc"] == 0
    assert counts.errors["Arc"] == "HTTP 403"


def test_new_sources_deduplicate():
    settings = {"sources": {key: {"enabled": key in {"wellfound", "wellfound_remote"}} for key, _, _ in SOURCES}}
    with patch("job_finder.aggregator.fetch_public", return_value=[job()]):
        jobs, counts = fetch_all(settings)
    assert len(jobs) == 1
    assert len(counts) == 2


def test_hybrid_remote_location_rejected():
    settings = {"search": {"keywords": ["QA Engineer"], "remote_only": True}}
    assert not apply_filters([job(location="Remote - United States", description="Hybrid role. 3 days per week in office.")], settings)


def test_remote_off_keeps_exact_role_without_description():
    assert apply_filters([job(remote="Unknown")], {"search": {"keywords": ["QA Engineer"], "remote_only": False}})


def test_residency_requirement_does_not_mean_onsite():
    assert classify_work_type(job(description="Fully remote. Must reside in the United States.")) == "remote"


def test_explicit_remote_field_survives_new_board_classification():
    assert classify_work_type(job()) == "remote"


def test_gui_deferred_error_callback_captures_message():
    from gui import JobFinderApp
    app = JobFinderApp.__new__(JobFinderApp)
    callbacks, errors = [], []
    app._ui = callbacks.append
    app._on_error = errors.append
    with patch("job_finder.config.load_settings", side_effect=RuntimeError("settings unavailable")):
        app._run_fetch()
    callbacks[-1]()
    assert errors == ["settings unavailable"]


def test_linkedin_remote_filter_can_be_disabled():
    from job_finder.sources.linkedin import fetch_linkedin
    response = type("Response", (), {"status_code": 200, "text": "<html></html>"})()
    with patch("job_finder.sources.linkedin.requests.get", return_value=response) as get:
        fetch_linkedin(["QA Engineer"], "United States", remote_only=False)
    assert "f_WT" not in get.call_args.kwargs["params"]


def test_worldwide_omits_country_from_source_requests():
    from job_finder.sources.linkedin import fetch_linkedin
    from job_finder.sources.jobicy import fetch_jobicy
    response = type("Response", (), {"status_code": 200, "text": "<html></html>",
                                      "json": lambda self: {"jobs": []}})()
    with patch("job_finder.sources.linkedin.requests.get", return_value=response) as get:
        fetch_linkedin(["QA Engineer"], "Worldwide")
    assert "location" not in get.call_args.kwargs["params"]
    with patch("job_finder.sources.jobicy.requests.get", return_value=response) as get, \
            patch("job_finder.sources.jobicy.time.sleep"):
        fetch_jobicy(["qa"], geo="")
    assert "geo" not in get.call_args.kwargs["params"]
    with patch("job_finder.sources.public_boards.get", return_value=Response({"jobs": []})) as get:
        fetch_himalayas({"keywords": ["QA Engineer"], "location": "Worldwide"}, {"max_pages": 1})
    assert "country" not in get.call_args.kwargs["params"]
