"""Fetch jobs from Jobicy public API."""

from __future__ import annotations

import time
from typing import Any

import requests

from job_finder.models import JobListing
from job_finder.countries import is_worldwide

API_URL = "https://jobicy.com/api/v2/remote-jobs"


def fetch_jobicy(
    tags: list[str] | None = None,
    *,
    geo: str = "usa",
    count: int = 200,
    warnings: list | None = None,
) -> list[JobListing]:
    tags = tags or ["qa", "sdet", "quality", "test-automation", "software-testing"]
    headers = {"User-Agent": "QA-Job-Finder/1.0 (personal job search tool)"}
    jobs: list[JobListing] = []
    seen_ids: set[str] = set()
    failures = []
    succeeded = 0

    for tag in tags:
        # The API rejects two-character keywords, including the common QA alias.
        if tag.strip().lower() == "qa":
            tag = "quality assurance"
        params: dict[str, Any] = {"count": min(count, 200), "tag": tag}
        if not is_worldwide(geo):
            params["geo"] = geo
        try:
            resp = requests.get(API_URL, params=params, headers=headers, timeout=45)
            if resp.status_code != 200:
                resp.raise_for_status()
                raise ValueError(f"Unexpected HTTP {resp.status_code}")
            payload = resp.json()
            items = payload.get("jobs") if isinstance(payload, dict) else []
            if not isinstance(items, list):
                raise ValueError("Jobicy returned an unexpected response")
            if not isinstance(payload, dict) or "jobs" not in payload:
                raise ValueError("Jobicy response is missing job data")
            succeeded += 1

            for item in items:
                if not isinstance(item, dict):
                    continue
                job_id = str(item.get("id") or item.get("url") or "")
                if not job_id or job_id in seen_ids:
                    continue
                seen_ids.add(job_id)

                title = str(item.get("jobTitle") or "").strip()
                if not title:
                    continue

                salary = ""
                smin = item.get("salaryMin")
                smax = item.get("salaryMax")
                cur = item.get("salaryCurrency") or ""
                if smin or smax:
                    salary = f"{cur} {smin or ''}-{smax or ''}".strip()

                jobs.append(
                    JobListing(
                        title=title,
                        company=str(item.get("companyName") or "Unknown").strip(),
                        location=str(item.get("jobGeo") or "USA").strip(),
                        remote="Unknown",
                        posted=str(item.get("pubDate") or "")[:10],
                        url=str(item.get("url") or ""),
                        source="Jobicy",
                        description=str(item.get("jobDescription") or "")[:500],
                        salary=salary,
                        tags=f"{item.get('jobIndustry', '')}, {item.get('jobType', '')}".strip(", "),
                    )
                )
        except (requests.RequestException, ValueError) as exc:
            failures.append(f"'{tag}': {exc}")
        time.sleep(0.5)

    if failures:
        message = "Jobicy queries failed: " + "; ".join(failures)
        if not succeeded:
            raise RuntimeError(message)
        if warnings is not None:
            warnings.append(message + "; results are partial")
    return jobs
