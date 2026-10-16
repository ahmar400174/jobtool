# Job Finder

The browser version uses Firebase Hosting and a Python backend on Vercel Hobby.
See [DEPLOYMENT.md](DEPLOYMENT.md) for setup, free-hosting limits, and local web
development. The desktop application below remains available.

Run `setup.bat` once, then `start.bat` to open the desktop app. Choose a role,
country, date range and sources, then search. Matches are deduplicated and
exported to Excel. `fetch_jobs.bat` runs the same search from the saved YAML.

All **13 supported platforms are enabled** in the saved configuration. Searches
run across eight platforms concurrently, with live completion counts in the GUI
and CLI. LinkedIn descriptions use four workers with the existing global request
spacing, preserving remote-work verification. Remote OK processes its feed
without per-record sleeps, and public-board workers reuse HTTP connections.
The GUI's **Select all platforms** button re-enables every platform. The CLI's
`--all-sources` option checks them all for one run without changing saved settings.
This checks every supported platform; it cannot guarantee access to every job
board on the internet or every listing behind sign-in.

The country dropdown includes **Worldwide** first, followed by countries in
alphabetical order. Worldwide removes geographic restrictions from source
queries and includes country-specific listings from across the world; it does
not mean every listing accepts applicants from every country. Other selected
filters, such as Remote only and Exclude Pakistan, still apply.

## Platforms

| Platform | Fetch method | Coverage / access |
| --- | --- | --- |
| LinkedIn Jobs | Public guest search and details | Role and location search, bounded by `max_pages` |
| Remote OK | Public JSON API | Current feed; filtering happens locally |
| Remotive | Public JSON API | Current feed; filtering happens locally |
| Jobicy | Public JSON API | Role tag and geography search |
| Himalayas | Public JSON search API | Role/country search, `max_pages` defaults to 3 |
| We Work Remotely | Public RSS | Recent feed, links and source attribution preserved |
| Startup.jobs | Public RSS | Latest 50 listings from the last 14 days; remote feed selected when requested |
| Wellfound | Public embedded listing data | Listings on the public landing page, not the complete signed-in database |
| Wellfound Remote Jobs | Public embedded listing data | Remote landing-page listings; deduplicated against Wellfound |
| Y Combinator | Public listing cards | Listings on the public jobs page; dates are unavailable on these cards |
| Arc | Public embedded listing data | Listings present on the public remote jobs page |
| AI Jobs | Public listing cards at aijobs.ai | Public jobs page; exact posting dates unavailable |
| Hacker News: Who Is Hiring? | Official HN Firebase API | Latest 2 hiring threads, first 300 top-level comments each; recognizes explicit roles near the start of a comment |

No authentication, anti-bot bypass, browser automation, paid services or API
keys are included.

Public HTML layouts can change. Landing-page adapters offer limited coverage and
may produce no matches for a narrow role. Country is sent to LinkedIn, Jobicy and
Himalayas; it is not a universal geographic filter for other feeds. Listings with
missing dates are excluded unless `search.include_undated` is enabled. The saved
date range is set in the GUI or `config/settings.yaml`.

## Configuration and checks

`config/settings.yaml` controls enabled sources, output and search preferences.
New sources appear as checkboxes in the scrollable GUI. The existing sources are
retained, including Jobicy. `performance.source_workers` controls platform
concurrency (1–16; default 8). `sources.linkedin.detail_workers` controls description
workers (1–8; default 4); `detail_delay_seconds` spaces request starts globally.
The saved LinkedIn settings now space search requests by 2 seconds and description
requests by 1.5 seconds. HTTP 429 searches retry at most twice, using `Retry-After`
when supplied or 5/10-second backoff. A server wait longer than
`max_retry_wait_seconds` (default 60) stops this platform instead of retrying early.
Persistent rate limits preserve fetched cards, stop further LinkedIn queries and
description checks, and start an in-process cooldown of at least five minutes.
Other platforms continue. This improves recovery but cannot guarantee public
LinkedIn access.
Jobicy expands the QA alias to `quality assurance`, because its API rejects
two-character keyword filters. Its current feed has a limited publication window;
see [Jobicy's API documentation](https://jobicy.com/jobs-rss-feed).

Each GUI/CLI search writes `output/latest_search_report.json`, including searches
with no matches. It records every platform as `ok`, `partial`, `failed`, or
`disabled`, with timings, raw counts, filtering reasons and coverage warnings.
Feed/page limits are shown explicitly. A failed platform does not stop others.
Per-job decision logs use Python logging instead of printing hundreds of records.

Excel export cleans invalid control characters in fetched text and verifies that
the saved job-row count equals the filtered match count before publishing the
workbook. A failed export preserves the previous file. If Excel has the configured
filename open, a fresh timestamped filename is saved; use **Open Excel** in the app
to open that exact result. The completion log displays the verified count and
full path. `latest_search_report.json` also records export status, filename and
verified row count separately from search matches. Descriptions stay in their
cells, with compact row heights so more jobs are visible; select a cell or expand
its row to read the complete exported description.

Run the offline tests with:

```powershell
.\.venv\Scripts\python.exe -m pytest scripts/tests -q
```

`pytest` is needed only for development and is not a runtime dependency.
Run the bounded live source check with:

```powershell
.\.venv\Scripts\python.exe scripts/probe_sources.py
```

The connectivity check attempts all 13 adapters, caps pagination at one page,
and HN at 15 comments. It writes
`output/latest_source_check.json` and exits nonzero if a platform fails. Its record
counts are before final filtering and are not total platform coverage or a
benchmark of a full search with your saved page limits.

Primary integration references: [Himalayas API](https://himalayas.app/api),
[We Work Remotely RSS](https://weworkremotely.com/remote-job-rss-feed),
[Startup.jobs feeds](https://startup.jobs/api), and
[Hacker News API](https://github.com/HackerNews/API).
