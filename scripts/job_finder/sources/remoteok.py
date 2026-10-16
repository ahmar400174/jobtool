"""Fetch jobs from RemoteOK public API."""

from __future__ import annotations

import requests

from job_finder.models import JobListing


def fetch_remoteok() -> list[JobListing]:
    url = "https://remoteok.com/api"
    headers = {
        "User-Agent": "QA-Job-Finder/1.0 (personal job search tool)",
        "Accept": "application/json",
    }
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list) or len(data) < 2:
        return []

    jobs: list[JobListing] = []
    for item in data[1:]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("position") or item.get("title") or "").strip()
        if not title:
            continue
        company = str(item.get("company") or "Unknown").strip()
        location = str(item.get("location") or "Remote").strip()
        tags = item.get("tags") or []
        tag_str = ", ".join(str(t) for t in tags) if isinstance(tags, list) else str(tags)
        posted = ""
        if item.get("date"):
            posted = str(item["date"])[:10]
        job_url = str(item.get("url") or item.get("apply_url") or "")
        if job_url and not job_url.startswith("http"):
            job_url = f"https://remoteok.com{job_url}"

        jobs.append(
            JobListing(
                title=title,
                company=company,
                location=location or "Remote",
                remote="Unknown",
                posted=posted,
                url=job_url,
                source="RemoteOK",
                description=str(item.get("description") or "")[:500],
                salary=str(item.get("salary") or ""),
                tags=tag_str,
            )
        )
    return jobs
