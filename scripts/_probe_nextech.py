import requests
from bs4 import BeautifulSoup
from job_finder.models import JobListing
from job_finder.work_type import classify_work_type
from job_finder.filters import apply_filters, is_remote
from job_finder.config import load_settings

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

job_id = "4457606980"
r = requests.get(
    f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}",
    headers=HEADERS,
    timeout=30,
)
soup = BeautifulSoup(r.text, "html.parser")
title = soup.select_one(".top-card-layout__title")
loc = soup.select_one(".topcard__flavor--bullet") or soup.select_one(".topcard__flavor")
desc_el = soup.select_one(".show-more-less-html__markup")
title_t = title.get_text(strip=True) if title else "Senior Quality Assurance Automation Engineer"
loc_t = loc.get_text(strip=True) if loc else "Memphis, TN"
desc_t = desc_el.get_text(" ", strip=True)[:1500] if desc_el else ""
print("title", title_t)
print("loc", loc_t)
print("desc start", desc_t[:400])
print("remote in desc", "remote" in desc_t.lower())
job = JobListing(
    title=title_t,
    company="NexTech Solutions",
    location="Memphis, TN",
    remote="Unknown",
    posted="",
    url=f"https://www.linkedin.com/jobs/view/{job_id}",
    source="LinkedIn",
    description=desc_t,
)
print("classify", classify_work_type(job))
print("is_remote", is_remote(job))
print("filtered count", len(apply_filters([job], load_settings())))
