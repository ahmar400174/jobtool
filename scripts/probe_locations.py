"""Quick probe: what location strings does LinkedIn actually return?"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import requests
from bs4 import BeautifulSoup

SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml",
}

params = {
    "keywords": "QA Engineer",
    "location": "United States",
    "f_WT": "2",   # Remote filter
    "start": "0",
}

resp = requests.get(SEARCH_URL, params=params, headers=HEADERS, timeout=30)
print(f"Status: {resp.status_code}")

soup = BeautifulSoup(resp.text, "html.parser")
cards = soup.select("li") or soup.select(".base-card")
print(f"Cards found: {len(cards)}\n")

for i, card in enumerate(cards[:15]):
    title_el = card.select_one(".base-search-card__title")
    loc_el   = card.select_one(".job-search-card__location")
    title = title_el.get_text(strip=True) if title_el else "(no title)"
    loc   = loc_el.get_text(strip=True)   if loc_el   else "(no location)"
    print(f"  [{i+1}] Title: {title}")
    print(f"       Location: '{loc}'")
    print()
