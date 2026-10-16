"""Fetch jobs from Remotive public API."""

from __future__ import annotations

import requests

from job_finder.models import JobListing


def fetch_remotive() -> list[JobListing]:
    url = "https://remotive.com/api/remote-jobs"
    headers = {
        "User-Agent": "QA-Job-Finder/1.0 (personal job search tool)",
        "Accept": "application/json",
    }
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    items = payload.get("jobs") if isinstance(payload, dict) else []
    if not isinstance(items, list):
        return []

    jobs: list[JobListing] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        company = str(item.get("company_name") or "Unknown").strip()
        location = str(item.get("candidate_required_location") or "Remote").strip()
        category = str(item.get("category") or "")
        job_type = str(item.get("job_type") or "")
        tags = f"{category}, {job_type}".strip(", ")
        posted = str(item.get("publication_date") or "")[:10]
        job_url = str(item.get("url") or "")

        jobs.append(
            JobListing(
                title=title,
                company=company,
                location=location or "Remote",
                remote="Yes",
                posted=posted,
                url=job_url,
                source="Remotive",
                description=str(item.get("description") or "")[:500],
                salary=str(item.get("salary") or ""),
                tags=tags,
            )
        )

    return jobs
