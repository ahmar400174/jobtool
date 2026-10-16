"""Detect remote, hybrid, or on-site from job listing text."""

from __future__ import annotations

import re

from job_finder.models import JobListing

_ONSITE_PHRASES = (
    "on-site",
    "onsite",
    "on site",
    "in-office",
    "in office",
    "in-person",
    "in person",
    "office-based",
    "office based",
    "on premises",
    "on-premises",
    "must work from our office",
    "must work from the office",
    "report to our office",
    "report to the office",
    "work from our office",
    "work from the office",
    "relocation required",
    "relocate to",
    "commute to",
    "commuting distance",
    "workplace type: on-site",
    "workplace type: onsite",
    "workplace type: in-office",
)

# Checked before any positive "remote" match (description may say "no remote work")
_NOT_REMOTE_PHRASES = (
    "not remote",
    "not a remote",
    "this is not a remote",
    "no remote work",
    "no remote option",
    "no opportunity for remote",
    "not eligible for remote",
    "without remote",
    "cannot work remotely",
    "can't work remotely",
    "no work from home",
    "not work from home",
    "in-office role",
    "in office role",
    "on-site role",
    "onsite role",
    "non-remote",
    "non remote",
    "remote is not available",
    "remote work is not available",
    "remote not permitted",
)

_HYBRID_PHRASES = (
    "hybrid role",
    "hybrid position",
    "hybrid work",
    "hybrid schedule",
    "hybrid model",
    "hybrid environment",
    "hybrid setup",
    "hybrid arrangement",
    "hybrid working",
    "hybrid policy",
    "hybrid mode",
    "flexible hybrid",
    "days/week in office",
    "days in office",
    "days per week in office",
    "days a week in the office",
    "days/week in the office",
    "partially remote",
    "partial remote",
    "split between remote and office",
    "workplace type: hybrid",
    "workplace: hybrid",
)

_REMOTE_PHRASES = (
    "fully remote",
    "100% remote",
    "100 percent remote",
    "remote-first",
    "remote first",
    "work from home",
    "work-from-home",
    "work from anywhere",
    "remote position",
    "remote role",
    "remote opportunity",
    "telecommute",
    "telecommuting",
    "distributed team",
    "anywhere in the world",
    "global remote",
    "workplace type: remote",
)

_REMOTE_BOARDS = ("Jobicy", "RemoteOK", "Remotive")


def _blob(job: JobListing) -> str:
    return f"{job.title} {job.location} {job.remote} {job.description} {job.tags}".lower()


def _looks_like_city_state(location: str) -> bool:
    loc = location.strip()
    if not loc:
        return False
    if re.search(r",\s*[A-Za-z]{2}\b", loc):
        return True
    return bool(re.search(r"\barea\b", loc, re.I))


def _is_remote_negated(blob: str) -> bool:
    if any(p in blob for p in _NOT_REMOTE_PHRASES):
        return True
    if re.search(r"\bno\b[^.]{0,40}\bremote\b", blob):
        return True
    if re.search(r"\bnot\b[^.]{0,40}\bremote\b", blob):
        return True
    return False


def _location_is_remote(location: str) -> bool:
    loc = location.lower().strip()
    if not loc:
        return False
    if "remote" in loc:
        return True
    return loc in {"work from home", "wfh", "anywhere"}


def classify_work_type(job: JobListing) -> str:
    """Use workplace metadata and employment requirements, not technology names."""
    field = job.remote.lower().strip()
    structured = f"{job.title} {job.location} {job.remote}".lower()
    description = job.description.lower()
    if field in {"hybrid", "on-site", "onsite", "in-office"}:
        return "hybrid" if field == "hybrid" else "onsite"

    # A negative must refer to the job, not an unrelated sentence containing 'not'.
    if any(phrase in structured + " " + description for phrase in _NOT_REMOTE_PHRASES):
        return "onsite"

    hybrid_job = r"\bhybrid\s+(?:role|position|work(?:ing)?|schedule|arrangement|policy|setup)\b"
    office_days = r"\b\d+\s*days?\s*(?:(?:a|per|/)\s*week\s*)?(?:in|at)\s+(?:the\s+)?office\b"
    office_days_after = r"\b(?:in|at)\s+(?:the\s+)?office\s+\d+\s*days?\b"
    if (re.search(r"\bhybrid\b", structured) or re.search(hybrid_job, description)
            or re.search(office_days, description) or re.search(office_days_after, description)
            or "partially remote" in description or "partial remote" in description):
        return "hybrid"

    # 'On-premises software' and 'hybrid cloud' are not office requirements.
    onsite_job = r"\b(?:on[- ]?site|in[- ]office|in[- ]person|office[- ]based)\s+(?:role|position|job|work(?:ing)?|schedule)\b"
    requirements = r"\b(?:must|required to|will|expected to)\s+(?:work|report|commute|be present|attend)\b[^.]{0,70}\b(?:office|on[- ]?site|in[- ]person)\b"
    onsite_matches = list(re.finditer(onsite_job, description))
    onsite_matches = [m for m in onsite_matches if not re.search(r"\b(?:no|not|without|zero)\s+(?:any\s+)?$", description[max(0, m.start()-20):m.start()])]
    if (re.search(r"\b(?:on[- ]?site|in[- ]office|in[- ]person)\b", structured)
            or onsite_matches or re.search(requirements, description)
            or any(p in description for p in ("work from our office", "work from the office", "relocation required", "commuting distance"))):
        return "onsite"

    if field in {"remote", "fully remote", "yes"}:
        return "remote"
    if _location_is_remote(job.location) or re.search(r"\bremote\b", job.title.lower()):
        return "remote"
    if any(p in description for p in _REMOTE_PHRASES):
        return "remote"
    if job.source in _REMOTE_BOARDS:
        return "remote"
    # A city address alone doesn't prove that office attendance is required.
    return "unknown"


def work_type_label(work_type: str) -> str:
    return {
        "remote": "Remote",
        "hybrid": "Hybrid",
        "onsite": "On-site",
        "unknown": "Unknown",
    }.get(work_type, "Unknown")


def is_fully_remote(job: JobListing, *, include_hybrid: bool = False) -> bool:
    work_type = classify_work_type(job)
    if work_type == "remote":
        return True
    if include_hybrid and work_type == "hybrid":
        return True
    return False
