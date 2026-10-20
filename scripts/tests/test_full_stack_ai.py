"""Compound searches accept title variants while preserving role/date gates."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from job_finder.models import JobListing
from job_finder.profession_matcher import score_job
from job_finder.search_terms import query_terms, jobicy_terms
from job_finder.filters import apply_filters


ROLE = "Full-Stack AI engineer"


def job(title, description="", posted="2026-10-15", remote="Remote"):
    return JobListing(title, "Acme", "Worldwide", remote, posted, "https://example.org/job", "LinkedIn", description)


@pytest.mark.parametrize("title,description", [
    ("Full Stack AI Engineer", ""),
    ("Fullstack AI Developer", ""),
    ("Senior AI & Full-Stack Engineer", ""),
    ("Full Stack Engineer (AI-focused)", ""),
    ("Full-Stack Applied AI Engineer", ""),
    ("Full Stack AI/ML Developer - Digital Products", ""),
    ("Full\u2011Stack AI Engineer", ""),
    ("Senior Software Engineer (Full Stack | Node.js & React | AI Focus)", ""),
    ("Full Stack Engineer", "Build generative AI applications with LLMs and RAG."),
    ("AI Engineer", "Design and implement full-stack applications, from UI to backend."),
    ("Senior Software Engineer, AI", "Own fullstack delivery of AI agents."),
])
def test_compound_role_matches_title_variants_and_relevant_details(title, description):
    assert score_job(job(title, description), ROLE)[2]


@pytest.mark.parametrize("title,description", [
    ("Full Stack Engineer", "Build payment services with React and Node.js."),
    ("AI Engineer", "Train ML models and deploy inference services."),
    ("Backend AI Engineer", "Build LLM inference APIs."),
    ("Full Stack Engineer", "Use AI coding tools and GitHub Copilot to write code."),
    ("Software Engineer", "Work for our full-stack AI platform company."),
    ("Analytics Engineer", "Our full-stack AI platform powers enterprise analytics."),
    ("AI Sales Engineer", "Build full-stack artificial intelligence demos."),
    ("Full Stack AI QA Engineer", "Test LLM applications."),
    ("Full Stack Engineer", "Maintain chair repair and email templates."),
])
def test_compound_role_rejects_missing_specialism_and_unrelated_titles(title, description):
    assert not score_job(job(title, description), ROLE)[2]


@pytest.mark.parametrize("role", [ROLE, "Fullstack AI Engineer", "Full Stack Artificial Intelligence Developer"])
def test_queries_search_title_families_but_matching_keeps_both_requirements(role):
    terms = query_terms([role])
    assert terms == ["full stack AI engineer", "full stack engineer", "AI engineer"]
    assert "software" in jobicy_terms([role])
    assert not score_job(job("Backend Engineer"), role)[2]


def test_requested_dates_are_inclusive_and_do_not_admit_undated_or_non_remote_jobs():
    candidates = [job("Full Stack AI Engineer", posted=date) for date in
                  ["2026-10-12", "2026-10-13", "2026-10-20", "2026-10-21", ""]]
    candidates.append(job("Full Stack AI Engineer", remote="Hybrid"))
    settings = {"search": {"keywords": [ROLE], "start_date": "2026-10-13", "end_date": "2026-10-20", "remote_only": True}}
    accepted = apply_filters(candidates, settings)
    assert [item.posted for item in accepted] == ["2026-10-13", "2026-10-20"]
