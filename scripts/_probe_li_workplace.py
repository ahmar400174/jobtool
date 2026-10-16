import json
import re
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

urls = [
    "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/4447074716",
    "https://www.linkedin.com/jobs/view/4447074716",
    "https://www.linkedin.com/jobs/search/?keywords=Senior%20Quality%20Assurance%20Automation%20Engineer%20NexTech&f_WT=1",
]

session = requests.Session()
session.headers.update(HEADERS)

# Search for the NexTech job
search = session.get(
    "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search",
    params={
        "keywords": "Senior Quality Assurance Automation Engineer NexTech",
        "location": "United States",
        "start": "0",
    },
    timeout=30,
)
print("search status", search.status_code)
soup = BeautifulSoup(search.text, "html.parser")
for a in soup.select("a.base-card__full-link")[:5]:
    print("card", a.get_text(" ", strip=True)[:80], a.get("href", "")[:120])

# Also generic QA search first card details
search2 = session.get(
    "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search",
    params={"keywords": "QA Engineer", "location": "Memphis, TN", "start": "0"},
    timeout=30,
)
soup2 = BeautifulSoup(search2.text, "html.parser")
cards = soup2.select(".job-search-card")[:3]
for card in cards:
    title = card.select_one(".base-search-card__title")
    loc = card.select_one(".job-search-card__location")
    urn = card.get("data-entity-urn", "")
    print("memphis card", title.get_text(strip=True) if title else "", "|", loc.get_text(strip=True) if loc else "", "|", urn)

job_id = None
if cards:
    urn = cards[0].get("data-entity-urn", "")
    if "jobPosting:" in urn:
        job_id = urn.rsplit(":", 1)[-1]
    print("probing job_id", job_id)

if not job_id:
    job_id = "4447074716"

for kind, url in [
    ("guest", f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"),
    ("view", f"https://www.linkedin.com/jobs/view/{job_id}"),
]:
    r = session.get(url, timeout=30)
    print("\n===", kind, r.status_code, len(r.text), "===")
    soup = BeautifulSoup(r.text, "html.parser")
    for script in soup.select('script[type="application/ld+json"]'):
        raw = script.string or script.get_text() or ""
        print("ld+json snippet", raw[:800])
        try:
            data = json.loads(raw)
        except Exception as e:
            print("json fail", e)
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if isinstance(item, dict):
                print("keys", list(item.keys())[:30])
                print("jobLocationType", item.get("jobLocationType"))
                print("employmentType", item.get("employmentType"))
                loc = item.get("jobLocation")
                print("jobLocation", str(loc)[:300])
    for pat in ["TELECOMMUTE", "jobLocationType", "workplaceTypes", "On-site", "onsite", "REMOTE"]:
        print(pat, r.text.lower().count(pat.lower()) if pat != "TELECOMMUTE" else r.text.count(pat))
