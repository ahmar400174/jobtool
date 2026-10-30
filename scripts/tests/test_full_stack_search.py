"""Regression checks for common full-stack title variations."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from job_finder.models import JobListing
from job_finder.profession_matcher import score_job
from job_finder.search_terms import query_terms


def test_full_stack_search_expands_source_queries():
    terms = query_terms(["Full Stack Developer"])
    assert "full stack engineer" in terms
    assert "fullstack developer" in terms


def test_full_stack_search_accepts_common_title_variants():
    for title in ("Full Stack Developer", "Senior Full-Stack Engineer", "Fullstack Developer"):
        job = JobListing(title=title, company="Example", location="Remote", remote="Remote",
                         posted="2026-10-29", url="https://example.com/job", source="LinkedIn")
        assert score_job(job, "Full Stack Developer", "remote")[2], title
