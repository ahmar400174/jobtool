"""Filter jobs: profession match + remote check + date range + geography."""

from __future__ import annotations

import re
import logging
from datetime import datetime

from job_finder.models import JobListing
from job_finder.work_type import is_fully_remote, work_type_label
from job_finder.work_type import classify_work_type as _classify_work_type
from job_finder.profession_matcher import score_job

log = logging.getLogger("job_finder.filters")

# ---------------------------------------------------------------------------
# US / Pakistan geography helpers (preserved unchanged)
# ---------------------------------------------------------------------------
_US_STATE_ABBREVS = {
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga", "hi", "id", "il", "in",
    "ia", "ks", "ky", "la", "me", "md", "ma", "mi", "mn", "ms", "mo", "mt", "ne", "nv",
    "nh", "nj", "nm", "ny", "nc", "nd", "oh", "ok", "or", "pa", "ri", "sc", "sd", "tn",
    "tx", "ut", "vt", "va", "wa", "wv", "wi", "wy", "dc",
}

_NON_US_MARKERS = (
    "europe", "european union", "emea", "united kingdom", " uk", " uk,", " uk)",
    "england", "scotland", "germany", "berlin", "france", "paris", "netherlands",
    "amsterdam", "spain", "italy", "poland", "portugal", "sweden", "switzerland",
    "austria", "belgium", "ireland", "dublin", "canada", "toronto", "vancouver",
    "montreal", "india", "bangalore", "bengaluru", "mumbai", "hyderabad",
    "philippines", "singapore", "australia", "mexico", "brazil", "latin america",
    "apac", "japan", "israel", "turkey", "ukraine", "romania", "czech", "hungary",
)

_US_MARKERS = (
    "united states", "united states of america", "usa", "u.s.", "u.s.a",
    "us-only", "us only", "us-based", "u.s.-based", "usa-based", "north america",
)

_PAKISTAN_MARKERS = (
    "pakistan", "pakistani", "karachi", "lahore", "islamabad", "rawalpindi",
    "faisalabad", "peshawar", "multan", "sialkot", "gujranwala", "bahawalpur",
    "quetta", "sindh", "punjab, pakistan", "pakistan only", "based in pakistan",
    "located in pakistan", "must be in pakistan", "remote - pakistan", "remote pakistan",
)


def _has_us_state(text: str) -> bool:
    text = text.lower()
    if re.search(r",\s*(" + "|".join(_US_STATE_ABBREVS) + r")\b", text):
        return True
    for abbrev in _US_STATE_ABBREVS:
        if re.search(rf"\b{abbrev}\b", text):
            state_names = {
                "ca": "california", "ny": "new york", "tx": "texas", "wa": "washington",
                "fl": "florida", "il": "illinois", "co": "colorado", "ga": "georgia",
            }
            if abbrev in state_names and state_names[abbrev] in text:
                return True
    return False


def _has_us_marker(blob: str) -> bool:
    blob = blob.lower()
    if any(m in blob for m in _US_MARKERS):
        return True
    return _has_us_state(blob)


# ---------------------------------------------------------------------------
# Public filter helpers (preserved for backward compatibility)
# ---------------------------------------------------------------------------

def is_within_date_range(job: JobListing, start_date: str, end_date: str, *, include_undated: bool = False) -> bool:
    if not job.posted:
        return include_undated
    s_date = datetime.strptime(start_date, "%Y-%m-%d").date()
    e_date = datetime.strptime(end_date, "%Y-%m-%d").date()
    try:
        posted = datetime.strptime(job.posted[:10], "%Y-%m-%d").date()
        return s_date <= posted <= e_date
    except ValueError:
        return include_undated


def normalize_remote_label(job: JobListing) -> str:
    """Set an accurate Remote column value on the job record."""
    work_type = _classify_work_type(job)
    if work_type == "unknown" and job.source in ("Jobicy", "RemoteOK", "Remotive"):
        work_type = "remote"
    job.remote = work_type_label(work_type)
    return job.remote


def is_remote(job: JobListing, *, include_hybrid: bool = False) -> bool:
    return is_fully_remote(job, include_hybrid=include_hybrid)


def is_pakistan_job(job: JobListing) -> bool:
    """True if the listing is based in or restricted to Pakistan."""
    location = job.location.strip().lower()
    description = job.description.lower()
    if any(m in description for m in ("pakistan only", "must be in pakistan", "must reside in pakistan", "must be based in pakistan")):
        return True
    if not any(m in location for m in _PAKISTAN_MARKERS) and not re.search(r"\bpk\b", location):
        return False
    # A worldwide/multiple-country role isn't Pakistan-only just because PK is
    # one of the eligible countries. Company prose isn't a location restriction.
    if any(m in location for m in ("worldwide", "anywhere", "global")):
        return False
    parts = re.split(r"[,;|/]", location)
    remaining = [re.sub(r"\bremote\b|[()\-]", " ", part).strip() for part in parts]
    remaining = [part for part in remaining if part]
    return all(any(m in part for m in _PAKISTAN_MARKERS) or part == "pk" for part in remaining)


def is_us_based_company(job: JobListing) -> bool:
    """Company must be US-based — not just 'open to US applicants' globally."""
    location = job.location.strip()
    blob = f"{location} {job.company} {job.description[:400]} {job.tags}".lower()

    if any(m in blob for m in _NON_US_MARKERS):
        if not _has_us_marker(blob):
            return False

    if _has_us_marker(blob):
        return True

    loc_lower = location.lower()
    if job.source == "LinkedIn":
        if loc_lower in ("remote", "united states", "usa", "us"):
            return True
        if _has_us_state(location):
            return True
        return False

    if job.source == "Jobicy":
        if loc_lower in ("usa", "us", "united states", "anywhere", ""):
            return True
        if "usa" in loc_lower or "united states" in loc_lower:
            return True
        return _has_us_state(location)

    if _has_us_state(location):
        return True
    if loc_lower in ("usa", "us", "united states"):
        return True

    return False


# ---------------------------------------------------------------------------
# Legacy helper kept for backward-compat (aggregator calls it indirectly)
# ---------------------------------------------------------------------------
def is_profession_related(job: JobListing, profession_terms: list[str]) -> bool:
    """
    Lightweight check used only by non-LinkedIn sources (Jobicy, RemoteOK…).
    Checks title and tags only — description check would be too broad.
    """
    title = job.title.lower()
    tags = (job.tags or "").lower()
    for term in profession_terms:
        t = term.lower()
        if t in title or t in tags:
            return True
    return False


# ---------------------------------------------------------------------------
# Main filter pipeline
# ---------------------------------------------------------------------------

def apply_filters(jobs: list[JobListing], settings: dict, diagnostics: dict | None = None) -> list[JobListing]:
    search         = settings.get("search", {})
    requested_roles = search.get("keywords") or ["QA Engineer"]
    requested_role = ", ".join(requested_roles)
    requested_wp   = "remote" if search.get("remote_only", True) else "any"

    profession_terms = search.get("profession_terms", search.get("qa_terms", ["qa"]))
    include_hybrid   = search.get("include_hybrid", False)
    us_company_only  = search.get("us_company_only", False)
    exclude_pakistan = search.get("exclude_pakistan", True)
    start_date       = search.get("start_date", "1970-01-01")
    end_date         = search.get("end_date", "2099-12-31")
    include_undated   = search.get("include_undated", False)
    s_date = datetime.strptime(start_date, "%Y-%m-%d").date()
    e_date = datetime.strptime(end_date, "%Y-%m-%d").date()
    if s_date > e_date:
        raise ValueError("Start date must not be after end date")

    def count(job, reason):
        if diagnostics is not None:
            source = diagnostics.setdefault(job.source, {})
            source[reason] = source.get(reason, 0) + 1

    print(f"\n  [Filter] Role='{requested_role}'  Workplace='{requested_wp}'")
    print(f"  [Filter] Scoring {len(jobs)} raw jobs...\n")

    filtered: list[JobListing] = []

    for job in jobs:
        count(job, "fetched")
        # 1. Pakistan gate
        if exclude_pakistan and is_pakistan_job(job):
            count(job, "pakistan")
            log.debug("Rejected %s: Pakistan location/restriction", job.title)
            continue

        # 2. Date range
        if not is_within_date_range(job, start_date, end_date, include_undated=include_undated):
            count(job, "date_range" if re.match(r"^\d{4}-\d{2}-\d{2}$", job.posted) else "undated")
            log.debug("Rejected %s: Posted outside requested date range", job.title)
            continue

        # 3. Normalise remote label via classify_work_type
        normalize_remote_label(job)

        # 4. Strict title + remote scoring for ALL job sources
        workplace = "any" if include_hybrid and job.remote == "Hybrid" else requested_wp
        decisions = [score_job(job, role, workplace) for role in requested_roles]
        accepted = any(decision[2] for decision in decisions)
        if not accepted:
            role_mismatch = all("Title does not match" in reason or "Excluded keyword" in reason for _, reason, _ in decisions)
            count(job, "role" if role_mismatch else "workplace")
            continue

        # 5. Optional US company check if enabled
        if us_company_only and not is_us_based_company(job):
            count(job, "us_company")
            log.debug("Rejected %s: Company not US-based", job.title)
            continue

        filtered.append(job)
        count(job, "accepted")

    return filtered
