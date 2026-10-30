"""AI Engineer searches should include common title variations."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from job_finder.models import JobListing
from job_finder.profession_matcher import score_job
from job_finder.search_terms import query_terms


def job(title):
    return JobListing(title=title, company="Example", location="Remote", remote="Remote",
                      posted="2026-10-29", url="https://example.com/job", source="Remotive")


def test_ai_engineer_search_covers_title_variations():
    assert "applied AI engineer" in query_terms(["AI Engineer"])
    for title in (
        "AI Engineer", "Senior Software Engineer II Applied AI",
        "AI Experience Engineer (Conversational AI)",
        "AI Developer Experience Engineer", "Software Engineer, AI Coding Tasks",
        "Principal Applied AI Engineer - Entity Agents", "AI Harness Engineer",
    ):
        assert score_job(job(title), "AI Engineer", "remote")[2], title


def test_ai_engineer_search_excludes_non_engineering_titles():
    for title in ("AI Product Manager", "AI Recruiter", "Sales Engineer - AI"):
        assert not score_job(job(title), "AI Engineer", "remote")[2], title
