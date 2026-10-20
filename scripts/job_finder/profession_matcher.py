"""
Dynamic profession matcher.

Builds whitelist / blacklist title patterns from the requested role,
computes a relevance score, and logs decisions.
"""

from __future__ import annotations

import re
import logging

from job_finder.models import JobListing
from job_finder.search_terms import is_full_stack_ai_role, normalise_role

log = logging.getLogger("job_finder.matcher")

# ---------------------------------------------------------------------------
# Profession catalogue
# Each entry has:
#   "include"  – title fragments that confirm a match (any one is enough)
#   "exclude"  – title fragments that hard-exclude a job even if include hits
#   "desc_kw"  – description keywords that boost confidence
# ---------------------------------------------------------------------------
_PROFESSION_CATALOGUE: dict[str, dict] = {
    "software": {
        "include": ["software engineer", "software developer", "software development engineer",
                    "backend engineer", "backend developer", "back-end engineer", "back-end developer",
                    "front-end engineer", "front-end developer", "frontend engineer", "frontend developer",
                    "full stack engineer", "full stack developer", "full-stack engineer", "full-stack developer",
                    "fullstack engineer", "fullstack developer", "web developer", "web engineer",
                    "application developer", "applications engineer", "mobile developer", "mobile engineer",
                    "ios developer", "ios engineer", "android developer", "android engineer",
                    "python developer", "java developer", "javascript developer", "typescript developer",
                    "ruby developer", "php developer", "golang developer", "go developer",
                    "react developer", "flutter developer", "programmer", "swe"],
        "exclude": ["developer advocate", "developer relations", "sales engineer", "solutions engineer",
                    "qa engineer", "quality assurance", "in test", "sdet", "test engineer"],
        "desc_kw": ["software", "development", "programming", "backend", "frontend", "api", "coding"],
    },
    "qa": {
        "include": [
            "qa", "quality assurance", "quality engineer", "quality analyst",
            "software tester", "test engineer", "test analyst", "test lead",
            "qa automation", "automation tester", "automation qa",
            "sdet", "software development engineer in test",
            "testing engineer",
            "software engineer in test", "manual tester", "automation engineer",
        ],
        "exclude": [
            "software engineer", "backend engineer", "frontend engineer",
            "full stack engineer", "fullstack engineer", "devops engineer",
            "data engineer", "machine learning engineer", "ml engineer",
            "ai engineer", "cloud engineer", "security engineer",
            "network engineer", "mobile engineer", "ios engineer",
            "android engineer", "platform engineer", "infrastructure engineer",
            "site reliability engineer", "sre", "embedded engineer",
            "firmware engineer", "hardware engineer", "solutions engineer",
        ],
        "desc_kw": [
            "quality assurance", "qa", "software testing", "test automation",
            "automated testing", "manual testing", "test cases", "selenium",
            "cypress", "playwright", "appium", "regression testing",
            "api testing", "sdet", "test plan", "test strategy",
            "bug reporting", "defect tracking",
        ],
    },
    "react": {
        "include": [
            "react developer", "react engineer", "react.js developer",
            "reactjs developer", "frontend developer", "front-end developer",
            "front end developer", "ui developer", "react native developer",
            "react specialist",
        ],
        "exclude": [
            "backend developer", "devops", "data engineer", "ml engineer",
            "machine learning", "ios developer", "android developer",
            "python developer", "java developer", "ruby developer",
            "php developer", "node developer",
        ],
        "desc_kw": [
            "react", "reactjs", "react.js", "jsx", "redux", "next.js",
            "webpack", "frontend", "front-end", "component", "hooks",
        ],
    },
    "flutter": {
        "include": [
            "flutter developer", "flutter engineer", "mobile developer",
            "flutter/dart", "dart developer",
        ],
        "exclude": [
            "backend", "devops", "data engineer", "ml engineer",
        ],
        "desc_kw": [
            "flutter", "dart", "mobile app", "android", "ios", "widget",
        ],
    },
    "python": {
        "include": [
            "python developer", "python engineer", "python programmer",
            "backend python", "django developer", "flask developer",
            "fastapi developer",
        ],
        "exclude": [
            "data engineer", "ml engineer", "devops", "security engineer",
            "qa engineer", "frontend developer",
        ],
        "desc_kw": [
            "python", "django", "flask", "fastapi", "sqlalchemy",
            "celery", "rest api",
        ],
    },
    "devops": {
        "include": [
            "devops engineer", "devops specialist", "site reliability engineer",
            "sre", "platform engineer", "infrastructure engineer",
            "cloud engineer", "devsecops", "release engineer",
        ],
        "exclude": [
            "frontend", "backend developer", "data engineer",
            "qa engineer", "mobile developer",
        ],
        "desc_kw": [
            "devops", "ci/cd", "kubernetes", "docker", "terraform",
            "ansible", "aws", "azure", "gcp", "jenkins", "pipeline",
        ],
    },
    "ui/ux": {
        "include": [
            "ui designer", "ux designer", "ui/ux designer", "product designer",
            "user experience designer", "user interface designer",
            "interaction designer", "visual designer",
        ],
        "exclude": [
            "engineer", "developer", "devops", "backend", "frontend developer",
        ],
        "desc_kw": [
            "figma", "sketch", "wireframe", "prototype", "user research",
            "usability", "ui", "ux", "design system", "accessibility",
        ],
    },
    "product manager": {
        "include": [
            "product manager", "pm ", "senior product", "associate product manager",
            "principal product manager", "group product manager",
        ],
        "exclude": [
            "engineer", "developer", "devops", "data engineer",
        ],
        "desc_kw": [
            "product roadmap", "stakeholder", "agile", "scrum", "sprint",
            "user stories", "okr", "kpi", "go-to-market",
        ],
    },
    "business analyst": {
        "include": [
            "business analyst", "ba ", "business systems analyst",
            "functional analyst", "requirements analyst",
        ],
        "exclude": [
            "engineer", "developer", "devops",
        ],
        "desc_kw": [
            "requirements", "business process", "stakeholder", "user stories",
            "gap analysis", "jira", "confluence",
        ],
    },
}

# Score thresholds and weights (per spec)
SCORE_STRONG_TITLE   = 50
SCORE_RELATED_TITLE  = 30
SCORE_DESC_MATCH     = 20
SCORE_REMOTE_MATCH   = 30
SCORE_WRONG_PROF     = -100
SCORE_WRONG_REMOTE   = -100

MIN_SCORE_DEFAULT    = 60   # Jobs below this are rejected


def _normalise(text: str) -> str:
    """Lower-case, collapse whitespace."""
    return re.sub(r"\s+", " ", text.lower().strip())


def _get_catalogue(requested_role: str) -> dict:
    """Find the best matching catalogue entry for the requested role."""
    role = _normalise(requested_role)
    if is_full_stack_ai_role(role):
        return {"full_stack_ai": True, "include": [], "exclude": [],
                "desc_kw": ["full stack", "full-stack", "llm", "generative ai", "machine learning", "rag"]}
    if role in {"software", "software engineering", "software development", "software engineer", "software developer",
                "software engineers", "software developers", "programming", "programmer"}:
        return _PROFESSION_CATALOGUE["software"]
    if role in {"quality assurance", "quality assurance engineer", "sdet", "test engineer", "software tester",
                "software engineer in test", "manual tester", "automation tester"}:
        return _PROFESSION_CATALOGUE["qa"]
    if re.search(r"\bqa\b", role):
        return _PROFESSION_CATALOGUE["qa"]
    # Match specialised professions before the general software family
    for key, entry in _PROFESSION_CATALOGUE.items():
        if key == "software":
            continue
        if re.search(r"\b" + re.escape(key) + r"\b", role):
            return entry
    if "software" in role:
        return _PROFESSION_CATALOGUE["software"]
    # Fallback: require the role phrase rather than generic words like engineer
    words = role.split()
    return {
        "include": [role],
        "exclude": [],
        "desc_kw": words,
    }


def _title_score(title_lower: str, catalogue: dict) -> tuple[int, str]:
    """
    Return (score, reason_string).
    Strong match → SCORE_STRONG_TITLE
    Related match → SCORE_RELATED_TITLE
    Excluded → SCORE_WRONG_PROF (hard reject)
    No match → SCORE_WRONG_PROF (hard reject)
    """
    # Check exclusions first
    for excl in catalogue["exclude"]:
        if excl == "software engineer" and re.search(r"\bsoftware engineer in test\b", title_lower):
            continue
        pattern = r"\b" + re.escape(excl) + r"\b"
        if re.search(pattern, title_lower):
            return SCORE_WRONG_PROF, f"Excluded keyword in title: '{excl}'"

    # Check inclusions
    for inc in sorted(catalogue["include"], key=lambda phrase: len(phrase.split()), reverse=True):
        pattern = r"\b" + re.escape(inc) + r"\b"
        if re.search(pattern, title_lower):
            # Strong if the full include phrase is multi-word and matches well
            if len(inc.split()) >= 2:
                return SCORE_STRONG_TITLE, f"Strong title match: '{inc}'"
            return SCORE_RELATED_TITLE, f"Related title match: '{inc}'"

    return SCORE_WRONG_PROF, "Title does not match requested role"


def _full_stack_ai_title_score(job):
    """Recognise compound roles without admitting generic software/AI jobs."""
    title = normalise_role(job.title)
    context = normalise_role(f"{job.description} {job.tags}")
    if re.search(r"\b(?:qa|sdet|quality assurance|sales|solutions|recruiter|advocate|marketing|support|manager|director)\b", title):
        return SCORE_WRONG_PROF, "Excluded keyword in title: not an engineering/development role for this search"
    engineering_title = re.search(r"\b(?:engineer|developer|programmer|swe)\b", title)
    full_stack_title = "full stack" in title
    full_stack = full_stack_title or "full stack" in context
    ai_title = re.search(r"\b(?:ai|artificial intelligence|genai|ml|llms?|machine learning)\b", title)
    ai_work = re.search(
        r"\b(?:artificial intelligence|generative ai|genai|machine learning|llms?|large language models?|"
        r"retrieval augmented generation|rag|ai(?: (?:powered|driven|native|enabled))? "
        r"(?:products?|features?|applications?|systems?|models?|integrations?|platforms?|agents?))\b", context)
    if not engineering_title or not full_stack or not (ai_title or ai_work) or not (full_stack_title or ai_title):
        return SCORE_WRONG_PROF, "Title does not match requested role: full-stack engineering and AI evidence are both required"
    strong = full_stack_title and ai_title
    return (SCORE_STRONG_TITLE if strong else SCORE_RELATED_TITLE,
            "Full-stack engineering and AI evidence matched in the title or role details")


def _desc_score(description_lower: str, catalogue: dict) -> tuple[int, str]:
    matched = [kw for kw in catalogue["desc_kw"] if kw in description_lower]
    if len(matched) >= 2:
        return SCORE_DESC_MATCH, f"Description keywords matched: {matched[:3]}"
    if len(matched) == 1:
        return SCORE_DESC_MATCH // 2, f"Weak description match: {matched}"
    return 0, "No description keywords matched"


def _remote_score(job: JobListing, requested_workplace: str) -> tuple[int, str]:
    """
    Only accept "remote" classification from job.remote field (set by
    classify_work_type in linkedin.py) or the location field.
    No guessing from description.
    """
    if requested_workplace.lower() != "remote":
        return 0, "Workplace filter not active"

    remote_field = job.remote.lower().strip()
    location_lower = job.location.lower().strip()

    # Accepted values from the structured field
    accepted = {"remote", "fully remote"}
    accepted_prefixes = ("remote", "remote -", "remote –")

    if remote_field in accepted:
        return SCORE_REMOTE_MATCH, f"Workplace field = '{job.remote}'"
    for prefix in accepted_prefixes:
        if remote_field.startswith(prefix):
            return SCORE_REMOTE_MATCH, f"Workplace field starts with '{prefix}'"

    # Explicit classification takes precedence over a location mentioning remote.
    if remote_field in {"hybrid", "on-site", "onsite", "in-office"}:
        return SCORE_WRONG_REMOTE, f"Workplace is {job.remote}"

    # Location field explicit remote signals (very conservative)
    if location_lower.startswith("remote"):
        return SCORE_REMOTE_MATCH, f"Location field = '{job.location}'"

    # Otherwise hard reject when remote was requested
    if remote_field in ("hybrid", "on-site", "onsite", "in-office", "unknown", ""):
        return SCORE_WRONG_REMOTE, f"Workplace is '{job.remote}' — not remote"
    return SCORE_WRONG_REMOTE, "Workplace could not be confirmed as remote"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_job(
    job: JobListing,
    requested_role: str,
    requested_workplace: str = "remote",
    *,
    verbose: bool = False,
) -> tuple[int, str, bool]:
    """
    Compute a relevance score for *job* given the *requested_role* and
    *requested_workplace*.

    Returns:
        (score, reason, accepted)
        accepted = True  → job should be written to CSV
        accepted = False → job should be rejected
    """
    catalogue = _get_catalogue(requested_role)
    title_lower = _normalise(job.title)
    desc_lower  = _normalise(job.description or "")

    total = 0
    reasons: list[str] = []

    # --- Title (hard gate) ------------------------------------------------
    t_score, t_reason = _full_stack_ai_title_score(job) if catalogue.get("full_stack_ai") else _title_score(title_lower, catalogue)
    total += t_score
    reasons.append(t_reason)
    if t_score == SCORE_WRONG_PROF:
        reason = " | ".join(reasons)
        _log_decision(job, total, reason, accepted=False, verbose=verbose)
        return total, reason, False

    # --- Description (soft boost) ----------------------------------------
    d_score, d_reason = _desc_score(desc_lower, catalogue)
    total += d_score
    reasons.append(d_reason)

    # --- Workplace (hard gate) -------------------------------------------
    r_score, r_reason = _remote_score(job, requested_workplace)
    total += r_score
    reasons.append(r_reason)
    if r_score == SCORE_WRONG_REMOTE:
        reason = " | ".join(reasons)
        _log_decision(job, total, reason, accepted=False, verbose=verbose)
        return total, reason, False

    reason = " | ".join(reasons)
    min_score = MIN_SCORE_DEFAULT if requested_workplace.lower() == "remote" else SCORE_RELATED_TITLE
    accepted = total >= min_score
    _log_decision(job, total, reason, accepted=accepted, verbose=verbose)
    return total, reason, accepted


def _log_decision(job: JobListing, score: int, reason: str, *, accepted: bool, verbose: bool = False) -> None:
    status = "ACCEPTED" if accepted else "REJECTED"
    msg = (
        f"\n  Job: {job.title}\n"
        f"  Company: {job.company}\n"
        f"  Workplace: {job.remote}\n"
        f"  Score: {score}\n"
        f"  Result: {status}\n"
        f"  Reason: {reason}"
    )
    if accepted:
        log.info(msg)
    else:
        log.debug(msg)
    if verbose:
        try:
            print(msg)
        except UnicodeEncodeError:
            print(msg.encode("ascii", errors="replace").decode("ascii"))
