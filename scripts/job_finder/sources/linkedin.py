"""Fetch jobs from LinkedIn public guest job search."""

from __future__ import annotations

import re
import time
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from threading import Event, Lock

import requests
from bs4 import BeautifulSoup

from job_finder.models import JobListing
from job_finder.countries import is_worldwide
from job_finder.work_type import classify_work_type as _classify_work_type, work_type_label as _work_type_label

SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
DETAIL_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
PAGE_SIZE = 10  # LinkedIn guest API returns ~10 jobs per page

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml",
}

_cooldown_lock = Lock()
_cooldown_until = 0.0


class LinkedInRateLimitError(RuntimeError):
    """The guest endpoint needs time to recover before any more requests."""


def _retry_after(response, fallback: float) -> float:
    value = getattr(response, "headers", {}).get("Retry-After", "")
    try:
        if str(value).strip().isdigit():
            return float(value)
        retry_at = parsedate_to_datetime(value)
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())
    except (TypeError, ValueError, OverflowError):
        return fallback


def _rate_limit(response, *, cooldown_seconds: float = 300) -> LinkedInRateLimitError:
    global _cooldown_until
    seconds = max(cooldown_seconds, _retry_after(response, cooldown_seconds))
    with _cooldown_lock:
        _cooldown_until = max(_cooldown_until, time.monotonic() + seconds)
    return LinkedInRateLimitError(
        f"LinkedIn rate-limited public access (HTTP 429). Wait at least {math.ceil(seconds)} seconds "
        "before searching LinkedIn again. Other platforms continue."
    )


def _search_request(params, warnings, *, max_retries, retry_backoff, max_retry_wait):
    for attempt in range(max(0, min(5, max_retries)) + 1):
        response = requests.get(SEARCH_URL, params=params, headers=HEADERS, timeout=30)
        if response.status_code != 429:
            return response
        wait = _retry_after(response, max(1.0, retry_backoff) * 2 ** attempt)
        if attempt >= max_retries or wait > max_retry_wait:
            raise _rate_limit(response)
        warnings.append(f"HTTP 429: waiting {wait:.0f}s before retrying LinkedIn search")
        time.sleep(wait)
    raise _rate_limit(response)


def _extract_job_id(card, href: str) -> str:
    root = card.select_one("[data-entity-urn]") or card
    urn = root.get("data-entity-urn", "")
    if urn and "jobPosting:" in urn:
        return urn.rsplit(":", 1)[-1]
    match = re.search(r"(\d{8,})(?:\?|$)", href)
    return match.group(1) if match else ""


def _fetch_job_description(job_id: str) -> str:
    if not job_id:
        return ""
    try:
        resp = requests.get(DETAIL_URL.format(job_id=job_id), headers=HEADERS, timeout=30)
        if resp.status_code == 429:
            raise _rate_limit(resp)
        if resp.status_code != 200:
            return ""
        soup = BeautifulSoup(resp.text, "html.parser")
        desc_el = soup.select_one(".show-more-less-html__markup")
        if desc_el:
            return desc_el.get_text(" ", strip=True)
    except requests.RequestException:
        return ""
    return ""


def _resolve_remote_label(location: str, *, api_remote_filter: bool = False) -> str:
    loc = location.lower().strip()
    if not loc:
        return "Unknown"

    if "hybrid" in loc:
        return "Hybrid"
    if any(k in loc for k in ("on-site", "onsite", "in-office", "in office", "in-person", "in person")):
        return "On-site"
    if "remote" in loc or loc in {"work from home", "wfh", "anywhere"}:
        return "Remote"

    return "Unknown"


def _parse_card(card, *, api_remote_filter: bool = False) -> tuple[JobListing | None, str]:
    title_el    = card.select_one(".base-search-card__title")
    company_el  = card.select_one(".base-search-card__subtitle")
    location_el = card.select_one(".job-search-card__location")
    link_el     = card.select_one("a.base-card__full-link") or card.select_one("a[href*='/jobs/view/']")
    time_el     = card.select_one("time")

    title    = title_el.get_text(strip=True)    if title_el    else ""
    if not title:
        return None, ""

    company  = company_el.get_text(strip=True)  if company_el  else "Unknown"
    location = location_el.get_text(strip=True) if location_el else "United States"
    posted   = time_el.get("datetime", "")[:10] if time_el     else ""
    if not posted and time_el:
        posted = time_el.get_text(strip=True)

    href = link_el.get("href", "") if link_el else ""
    if href and not href.startswith("http"):
        href = f"https://www.linkedin.com{href}"

    job_id = _extract_job_id(card, href)

    remote_label = _resolve_remote_label(location, api_remote_filter=api_remote_filter)

    job = JobListing(
        title=title,
        company=company,
        location=location,
        remote=remote_label,
        posted=posted,
        url=href,
        source="LinkedIn",
        description="",
        salary="",
        tags="",
    )
    return job, job_id


def fetch_linkedin(
    keywords: list[str],
    location: str,
    *,
    max_pages: int = 6,
    delay: float = 2.0,
    fetch_details: bool = True,
    detail_delay: float = 0.6,
    detail_workers: int = 4,
    remote_only: bool = True,
    start_date: str = "1970-01-01",
    end_date: str = "2099-12-31",
    warnings: list | None = None,
    max_retries: int = 2,
    retry_backoff: float = 5.0,
    max_retry_wait: float = 60.0,
) -> list[JobListing]:
    jobs: list[JobListing] = []
    detail_jobs: list[tuple[JobListing, str]] = []
    seen_urls: set[str] = set()
    warnings = warnings if warnings is not None else []
    with _cooldown_lock:
        remaining = _cooldown_until - time.monotonic()
    if remaining > 0:
        raise LinkedInRateLimitError(
            f"LinkedIn is cooling down after HTTP 429. Wait at least {math.ceil(remaining)} seconds. "
            "Other platforms continue."
        )
    rate_limited = False
    first_request = True

    for keyword in keywords:
        for page in range(max_pages):
            start = page * PAGE_SIZE
            params = {
                "keywords": keyword,
                "start": str(start),
                "sortBy": "DD",
            }
            if not is_worldwide(location):
                params["location"] = location
            if remote_only:
                params["f_WT"] = "2"
            if start_date != "1970-01-01":
                days = max(1, (date.today() - date.fromisoformat(start_date)).days + 1)
                params["f_TPR"] = f"r{days * 86400}"
            try:
                # Space requests across keyword boundaries as well as pages.
                if not first_request:
                    time.sleep(max(0, delay))
                first_request = False
                resp = _search_request(
                    params, warnings, max_retries=max_retries,
                    retry_backoff=retry_backoff, max_retry_wait=max_retry_wait,
                )
                if resp.status_code != 200:
                    if not jobs:
                        resp.raise_for_status()
                    warnings.append(f"Search stopped at HTTP {resp.status_code}; results are partial")
                    break
                soup = BeautifulSoup(resp.text, "html.parser")
                cards = soup.select("li") or soup.select(".base-card")
                if not cards:
                    break

                page_count = 0
                page_dates = []
                for card in cards:
                    job, job_id = _parse_card(card, api_remote_filter=True)
                    if job:
                        page_dates.append(job.posted)
                    identity = job_id or (job.url.split("?")[0] if job else "")
                    if not job or not job.url or identity in seen_urls:
                        continue
                    seen_urls.add(identity)

                    in_window = not job.posted or not re.match(r"^\d{4}-\d{2}-\d{2}$", job.posted) or start_date <= job.posted <= end_date
                    if fetch_details and job_id and in_window:
                        detail_jobs.append((job, job_id))

                    jobs.append(job)
                    page_count += 1

                if page_count == 0:
                    break
                # A complete older page can end this date-sorted query safely.
                if page_dates and all(re.match(r"^\d{4}-\d{2}-\d{2}$", d) for d in page_dates) and max(page_dates) < start_date:
                    break
            except LinkedInRateLimitError as exc:
                if not jobs:
                    raise
                warnings.append(f"{exc} Keeping {len(jobs)} fetched listings; results are partial")
                rate_limited = True
                break
            except requests.RequestException as exc:
                if not jobs:
                    raise
                warnings.append(f"Search interrupted: {exc}; results are partial")
                break

        else:
            warnings.append(f"Reached {max_pages} pages for '{keyword}'; more jobs may exist")
        if rate_limited:
            break

    # Fetch descriptions concurrently while preserving one global request-start
    # interval. More workers overlap network waits, not the platform rate limit.
    rate_lock = Lock()
    details_stopped = Event()
    next_request = 0.0
    def detail(entry):
        nonlocal next_request
        with rate_lock:
            if details_stopped.is_set():
                return False
            wait = next_request - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            if details_stopped.is_set():
                return False
            next_request = time.monotonic() + max(0, detail_delay)
        job, job_id = entry
        try:
            job.description = _fetch_job_description(job_id)
        except LinkedInRateLimitError as exc:
            with rate_lock:
                if not details_stopped.is_set():
                    warnings.append(f"{exc} Stopped description checks; results are partial")
                details_stopped.set()
            return False
        return bool(job.description)

    if rate_limited and detail_jobs:
        warnings.append("Description checks skipped after HTTP 429; remote verification is incomplete")
    elif detail_jobs:
        with ThreadPoolExecutor(max_workers=max(1, min(8, detail_workers)), thread_name_prefix="linkedin-detail") as pool:
            verified = list(pool.map(detail, detail_jobs))
        missing = len(verified) - sum(verified)
        if missing:
            warnings.append(f"Descriptions unavailable for {missing} of {len(detail_jobs)} listings; remote verification is incomplete")
    elif not fetch_details:
        warnings.append("Description checks disabled; remote verification is limited to search cards")
    for job in jobs:
        job.remote = _work_type_label(_classify_work_type(job))
    return jobs
