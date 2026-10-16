"""Public APIs, RSS feeds and server-rendered job board listings.

No authentication or challenge bypass. Missing listing data is an error,
not an empty successful search.
"""
from __future__ import annotations

import json
import re
import time
import threading
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlencode

import requests
from bs4 import BeautifulSoup

from job_finder.models import JobListing
from job_finder.countries import is_worldwide
from job_finder.search_terms import query_terms

HEADERS = {"User-Agent": "JobFinder/2.0 (personal job search)", "Accept": "*/*"}
_connections = threading.local()


def get(url, **kwargs):
    # Each worker keeps its own connection pool for pagination and HN comments.
    if not hasattr(_connections, "session"):
        _connections.session = requests.Session()
    response = _connections.session.get(url, headers=HEADERS, timeout=(10, 30), **kwargs)
    response.raise_for_status()
    return response


def text(value):
    return BeautifulSoup(str(value or ""), "html.parser").get_text(" ", strip=True)


def date(value):
    if not value:
        return ""
    if isinstance(value, (float, int)):
        return datetime.fromtimestamp(value, timezone.utc).strftime("%Y-%m-%d")
    value = str(value)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except ValueError:
        try:
            return parsedate_to_datetime(value).strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            return ""


def record(source, title, company, location, remote, posted, url, description="", salary="", tags=""):
    return JobListing(text(title), text(company) or "Unknown", text(location), remote,
                      date(posted), url, source, text(description), str(salary or ""), text(tags))


def fetch_rss(source, url, *, remote=False):
    root = ET.fromstring(get(url).content)
    jobs = []
    for item in root.findall("./channel/item"):
        title = item.findtext("title", "")
        if source == "We Work Remotely":
            company, sep, title_part = title.partition(": ")
            title = title_part if sep else title
            company = company if sep else "Unknown"
            location = item.findtext("region", "") or item.findtext("country", "") or "Remote"
        else:
            title, sep, company = title.rpartition(" at ")
            if not sep:
                title, company = item.findtext("title", ""), "Unknown"
            # Startup.jobs puts the location on the last description line.
            location = item.findtext("description", "").strip().split("\n")[-1].split(" · ")[0]
        url = item.findtext("link", "")
        if title and url:
            jobs.append(record(source, title, company, location, "Remote" if remote else "Unknown",
                               item.findtext("pubDate"), url, item.findtext("description"),
                               tags=", ".join(n.text or "" for n in item.findall("category"))))
    return jobs


def fetch_himalayas(search, cfg):
    jobs, seen = [], set()
    max_pages = int(cfg.get("max_pages", 25))
    for keyword in query_terms(search.get("keywords")):
        exhausted = False
        for page in range(1, max_pages + 1):
            params = {"q": keyword, "page": page, "sort": "recent"}
            location = search.get("location", "")
            if not is_worldwide(location):
                params["country"] = location
            payload = get("https://himalayas.app/jobs/api/search", params=params).json()
            items = payload.get("jobs")
            if not isinstance(items, list):
                raise ValueError("Himalayas returned an unexpected response")
            added = 0
            for item in items:
                url = item.get("guid") or item.get("applicationLink")
                if not url or url in seen:
                    continue
                seen.add(url)
                added += 1
                salary = f"{item.get('currency') or ''} {item.get('minSalary') or ''}-{item.get('maxSalary') or ''}".strip(" -")
                jobs.append(record("Himalayas", item.get("title"), item.get("companyName"),
                                   ", ".join(item.get("locationRestrictions") or ["Worldwide"]),
                                   "Remote", item.get("pubDate"), url, item.get("description"), salary,
                                   ", ".join(item.get("categories") or [])))
            if not added:
                exhausted = True
                break
            # Stop only after the complete page falls before the requested
            # window; featured older jobs on a newer page must not stop paging.
            dated = [date(item.get("pubDate")) for item in items]
            if dated and all(dated) and max(dated) < search.get("start_date", "1970-01-01"):
                exhausted = True
                break
            if page * int(payload.get("limit") or 20) >= int(payload.get("totalCount") or 10**9):
                exhausted = True
                break
            time.sleep(float(cfg.get("delay_seconds", 0.5)))
        if not exhausted:
            cfg.setdefault("_warnings", []).append(f"Himalayas reached {max_pages} pages for '{keyword}'; search coverage is partial")
    return jobs


def next_props(html):
    script = BeautifulSoup(html, "html.parser").select_one("script#__NEXT_DATA__")
    if not script:
        raise ValueError("Public listing data unavailable; the site may require sign-in or have changed")
    return json.loads(script.get_text())["props"]["pageProps"]


def parse_wellfound(html, remote_only=False):
    data = next_props(html).get("apolloState", {}).get("data", {})
    companies_by_job = {}
    for company in data.values():
        if isinstance(company, dict) and company.get("__typename") == "StartupResult":
            for ref in company.get("highlightedJobListings", []):
                companies_by_job[ref.get("__ref")] = company
    jobs = []
    for ref, item in data.items():
        if not isinstance(item, dict) or item.get("__typename") not in {"JobListing", "JobListingSearchResult"}:
            continue
        company = data.get((item.get("startup") or {}).get("__ref"), {}) or companies_by_job.get(ref, {})
        remote = bool(item.get("remote"))
        if remote_only and not remote:
            continue
        locations = item.get("acceptedRemoteLocationNames") if remote else item.get("locationNames")
        locations = locations or item.get("locationNames") or []
        jobs.append(record("Wellfound Remote Jobs" if remote_only else "Wellfound", item.get("title"),
                           company.get("name"), ", ".join(locations), "Remote" if remote else "Unknown",
                           item.get("liveStartAt"), f"https://wellfound.com/jobs/{item['id']}-{item.get('slug', '')}",
                           description=item.get("description", ""), salary=item.get("compensation")))
    if not jobs:
        raise ValueError("No public Wellfound listings available on this page")
    return jobs


def parse_arc(html):
    props = next_props(html)
    jobs = []
    for item in props.get("arcJobs", []) + props.get("externalJobs", []):
        url = f"https://arc.dev/remote-jobs/details/{item['urlString']}-{item['randomKey']}"
        jobs.append(record("Arc", item.get("title"), (item.get("company") or {}).get("name"),
                           ", ".join(item.get("requiredCountries") or ["Worldwide"]), "Remote", item.get("postedAt"), url,
                           tags=", ".join(c.get("name", "") for c in item.get("categories", []))))
    if not jobs:
        raise ValueError("Arc public listing data unavailable")
    return jobs


def parse_yc(html):
    soup = BeautifulSoup(html, "html.parser")
    jobs, seen = [], set()
    for link in soup.select('a[href*="/companies/"][href*="/jobs/"]'):
        url = urljoin("https://www.ycombinator.com", link["href"])
        if url in seen:
            continue
        seen.add(url)
        container = link.parent.parent
        company_link = container.select_one('a[href*="/companies/"]:not([href*="/jobs/"]) span.font-bold')
        company = company_link.get_text(" ", strip=True) if company_link else "Unknown"
        metadata = link.find_next_sibling("div")
        parts = metadata.select("div") if metadata else []
        location = parts[-1].get_text(" ", strip=True) if parts else ""
        jobs.append(record("Y Combinator", link.get_text(), company, location, "Unknown", "", url))
    if not jobs:
        raise ValueError("Y Combinator public listing data unavailable")
    return jobs


def parse_ai_jobs(html):
    soup = BeautifulSoup(html, "html.parser")
    jobs = []
    for card in soup.select('a.jobcardStyle1[href*="/job/"]'):
        title = card.select_one('div[class*="tw-text-lg"]')
        company = card.select_one(".tw-card-title")
        location = card.select_one(".tw-location")
        if not title:
            continue
        remote = "Remote" if any(s.get_text(strip=True) == "Remote" for s in card.select("span")) else "Unknown"
        jobs.append(record("AI Jobs", title.get_text(), company.get_text() if company else "Unknown",
                           location.get_text() if location else "", remote, "", card["href"]))
    if not jobs:
        raise ValueError("AI Jobs public listing data unavailable")
    return jobs


def parse_jsonld(html, source, base_url):
    """Parse genuine JobPosting records; never treat category links as jobs."""
    jobs = []
    def walk(node):
        if isinstance(node, list):
            for child in node:
                walk(child)
        elif isinstance(node, dict):
            kinds = node.get("@type", [])
            if kinds == "JobPosting" or isinstance(kinds, list) and "JobPosting" in kinds:
                company = node.get("hiringOrganization") or {}
                locations = node.get("jobLocation") or []
                if isinstance(locations, dict):
                    locations = [locations]
                loc = []
                for entry in locations:
                    address = entry.get("address") or {}
                    if isinstance(address, str):
                        loc.append(address)
                    else:
                        loc.extend(str(address[k]) for k in ["addressLocality", "addressRegion", "addressCountry"] if address.get(k))
                remote = "Remote" if node.get("jobLocationType") == "TELECOMMUTE" else "Unknown"
                url = node.get("url")
                if node.get("title") and url:
                    jobs.append(record(source, node["title"], company.get("name"), ", ".join(loc), remote,
                                       node.get("datePosted"), urljoin(base_url, url), node.get("description")))
            for child in node.values():
                if isinstance(child, (dict, list)):
                    walk(child)
    for script in BeautifulSoup(html, "html.parser").select('script[type="application/ld+json"]'):
        try:
            walk(json.loads(script.get_text()))
        except json.JSONDecodeError:
            continue
    return jobs


def fetch_hn(search, cfg):
    """Read actual monthly Who Is Hiring threads and their top-level comments."""
    base = "https://hacker-news.firebaseio.com/v0/"
    def item(item_id):
        return get(f"{base}item/{item_id}.json").json() or {}
    profile = get(base + "user/whoishiring.json").json()
    ids = profile.get("submitted", [])[:int(cfg.get("story_scan_limit", 20))]
    with ThreadPoolExecutor(max_workers=6) as pool:
        stories = list(pool.map(item, ids))
    threads = sorted((s for s in stories if s.get("title", "").startswith("Ask HN: Who is hiring?")),
                     key=lambda s: s.get("time", 0), reverse=True)
    # Use threads whose month overlaps the requested window, not always only
    # this month and last month.
    selected = []
    for story in threads:
        month = date(story.get("time"))[:7]
        if search.get("start_date", "1970-01-01")[:7] <= month <= search.get("end_date", "2099-12-31")[:7]:
            selected.append(story)
    threads = selected[:int(cfg.get("months", 12))]
    if not threads:
        cfg.setdefault("_warnings", []).append("No Who Is Hiring thread found for this date window in the scanned story history")
        return []
    jobs = []
    from job_finder.profession_matcher import _get_catalogue, _title_score, _normalise
    catalogues = [_get_catalogue(role) for role in search.get("keywords") or ["QA Engineer"]]
    for thread in threads:
        with ThreadPoolExecutor(max_workers=6) as pool:
            comment_ids = thread.get("kids", [])
            max_comments = int(cfg.get("max_comments", 1000))
            comments = list(pool.map(item, comment_ids[:max_comments]))
        if len(comment_ids) > max_comments:
            cfg.setdefault("_warnings", []).append(f"HN scanned {max_comments} of {len(comment_ids)} comments; coverage is partial")
        for comment in comments:
            if comment.get("deleted") or comment.get("dead") or not comment.get("text"):
                continue
            soup = BeautifulSoup(comment["text"], "html.parser")
            lines = [line.strip() for line in soup.get_text("\n", strip=True).splitlines() if line.strip()]
            header = lines[0] if lines else ""
            # Only explicit role text from the posting; preserve the original title.
            title = next((line for line in lines if any(_title_score(_normalise(line), cat)[0] > 0 for cat in catalogues)), None)
            if not title:
                continue
            jobs.append(record("Hacker News: Who Is Hiring?", title[:300], header.split("|")[0][:100],
                               " | ".join(header.split("|")[1:])[:300], "Unknown", comment.get("time"),
                               f"https://news.ycombinator.com/item?id={comment['id']}", soup.get_text(" ", strip=True)))
    return jobs


def fetch_paged(url, parser, cfg):
    jobs, seen_urls, seen_pages = [], set(), set()
    max_pages = int(cfg.get("max_pages", 10))
    for page in range(max_pages):
        if url in seen_pages:
            break
        seen_pages.add(url)
        response = get(url)
        page_jobs = parser(response.text)
        added = 0
        for job in page_jobs:
            if job.url not in seen_urls:
                seen_urls.add(job.url)
                jobs.append(job)
                added += 1
        soup = BeautifulSoup(response.text, "html.parser")
        next_link = soup.select_one('a[rel="next"][href]') or next((a for a in soup.select("a[href]")
                    if a.get_text(" ", strip=True).lower() in {"next", "next page", "next →", "next ›"}
                    or (a.get("aria-label") or "").lower() in {"next", "next page"}), None)
        if not next_link or not added:
            cfg.setdefault("_warnings", []).append(f"Public listing coverage: {len(seen_pages)} page(s), {len(jobs)} records; full platform history is unavailable")
            break
        if page + 1 == max_pages:
            cfg.setdefault("_warnings", []).append(f"Reached {max_pages} pages; more public pages exist")
            break
        url = urljoin(response.url, next_link["href"])
        time.sleep(float(cfg.get("delay_seconds", 0.5)))
    return jobs


def fetch_public(key, search, cfg):
    if key == "himalayas":
        return fetch_himalayas(search, cfg)
    if key == "weworkremotely":
        cfg.setdefault("_warnings", []).append("RSS feed covers recent listings only, not full historical search")
        return fetch_rss("We Work Remotely", "https://weworkremotely.com/remote-jobs.rss", remote=True)
    if key == "startupjobs":
        params = {}
        if search.get("remote_only", True):
            params["workplace"] = "remote"
        from job_finder.profession_matcher import _get_catalogue, _PROFESSION_CATALOGUE
        role = (search.get("keywords") or ["QA Engineer"])[0]
        if _get_catalogue(role) is _PROFESSION_CATALOGUE["software"]:
            params["role"] = "engineering"
        url = "https://startup.jobs/feeds/jobs" + ("?" + urlencode(params) if params else "")
        cfg.setdefault("_warnings", []).append("RSS is capped at 50 recent jobs within the last 14 days; older searches may return no dated matches")
        return fetch_rss("Startup.jobs", url, remote=search.get("remote_only", True))
    if key == "hackernews":
        return fetch_hn(search, cfg)
    pages = {"wellfound": ("https://wellfound.com/jobs", parse_wellfound),
             "wellfound_remote": ("https://wellfound.com/remote", lambda html: parse_wellfound(html, True)),
             "ycombinator": ("https://www.ycombinator.com/jobs", parse_yc),
             "arc": ("https://arc.dev/remote-jobs", parse_arc),
             "aijobs": ("https://aijobs.ai/jobs", parse_ai_jobs)}
    if key in pages:
        url, parser = pages[key]
        if key in {"arc", "aijobs"}:
            terms = query_terms(search.get("keywords"))
            url += "?" + urlencode({"search" if key == "arc" else "keyword": terms[0]})
        return fetch_paged(url, parser, cfg)
    raise ValueError(f"Unsupported job source: {key}")
