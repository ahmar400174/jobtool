# Firebase Hosting + Vercel Hobby

The website uses Firebase Hosting in project `jobs-tool`. The Python backend
uses Vercel Hobby's Flask support. No paid Firebase Functions, database, or
persistent disk is required. The desktop app still works.

## Local development

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-web.txt
.\.venv\Scripts\python.exe scripts/web_server.py
```

Open http://127.0.0.1:8765. The UI uses the local API automatically.

## Free local LinkedIn connector

If LinkedIn blocks cloud requests, run `start_linkedin_connector.bat` on the
same computer as the browser. On https://jobs-tool.web.app click **Check connector**
under **LinkedIn connection**. A successful check enables **Use this computer for
LinkedIn**. Allow the browser's local/loopback network permission if prompted.
Keep the connector running and search normally; other platforms, merging and
Excel export continue using Vercel. No LinkedIn secret, token or login is needed.
Close the connector or press Ctrl+C to stop it. It must be restarted after reboot.

The connector binds only `127.0.0.1:8765`, allows the Firebase origins, validates
the Host header, and serves only health checks and LinkedIn source requests.
It uses the same filters and limits as the cloud API. Caches distinguish cloud
and local searches, so switching to local does not reuse an empty cloud result.
An existing local web server on port 8765 must be stopped before starting it.
Local requests can also be rate-limited by LinkedIn; this uses the user's
connection and does not bypass LinkedIn's restrictions.

## Deploy the backend

The deployed backend is https://jobtool1.vercel.app on **Vercel Hobby**.
Vercel cloned the source into `ahmar400174/jobtool1` during import; that repository
drives automatic backend deployments. The original workspace source is also
maintained at `ahmar400174/jobtool`.

For a new deployment, import the repository into Vercel using the **Hobby** plan.
Framework: **Flask**. Root directory: repository root. No custom build command.
`app.py` exposes the WSGI app. `vercel.json` configures a 300-second maximum
function duration. Set this production environment variable:

```text
ALLOWED_ORIGINS=https://jobs-tool.web.app,https://jobs-tool.firebaseapp.com
```

Verify `/api/health` and `/api/config` on the assigned production HTTPS URL.
Put that exact URL into `API_BASE_URL` in `web/config.js`; never guess the host.

The browser calls `/api/source` for each selected platform, with up to three
requests in parallel. Each request finishes its work before responding.
`/api/merge` removes cross-platform duplicates with the original source priority.
`/api/export` returns a verified Excel workbook from the displayed records.
Results stay in the browser until the page closes or another search starts.
LinkedIn also keeps the most recent matching search in browser local storage:
it is reused for 10 minutes to reduce repeated requests. If a live request fails,
the same search's results can be shown for up to 24 hours, with their original
fetch time and the failure displayed. Changed filters require a new search.
The API keeps a bounded cache and prevents concurrent LinkedIn fetches within
each Python process; these safeguards are not shared across Vercel instances.
The browser cache continues working across serverless cold starts.
The legacy background-search API is disabled on Vercel.

## Deploy the frontend

```powershell
npx firebase-tools deploy --only hosting --project jobs-tool --account ahmar400174@gmail.com
```

Only `web/` is published at https://jobs-tool.web.app. Firebase client
configuration is public SDK configuration, not a deployment credential.
The production API URL is configured as `https://jobtool1.vercel.app`.

## Verification and coverage

```powershell
.\.venv\Scripts\python.exe -m pytest scripts/tests -q
node --check web/app.js
node --check web/config.js
node --test scripts/tests/test_linkedin_browser_cache.mjs
```

Live checks include a platform search, result links, coverage warnings, and
opening the downloaded Excel workbook.

Verified on 2026-10-16: 106 offline tests passed. A browser search across all
13 platforms returned 130 unique jobs in 17.6 seconds; 12 platforms completed
and LinkedIn was blocked. The Excel file downloaded from the Firebase page
opened successfully with all 130 job rows. The API health check also passed.

On 2026-10-19 the production API successfully fetched 10 LinkedIn cards and
returned one job matching the date and remote filters in 14.4 seconds. The
earlier HTTP 429 was temporary; public access can still be rate-limited.
Caching reduces repeat requests but does not grant access when LinkedIn blocks
a cloud IP. The UI includes a direct LinkedIn search link when results are cached
or unavailable. LinkedIn identity/sign-in tokens do not grant job-search access.
The cache and connector update passed 121 Python tests and five browser-cache unit tests.
The connector fetched 10 LinkedIn cards and returned one matching remote job;
subsequent description checks were rate-limited, and partial coverage was reported.

For free hosting, each platform returns up to 100 matches and 240 KB of text.
Descriptions are excerpts of up to 2000 characters; original listings are linked.
Queries check up to one LinkedIn page per keyword, two Himalayas/public pages,
and 30 comments in one HN thread. Feed adapters retain their normal coverage.
Source failures are reported independently. Public boards can block cloud IPs.
Hobby quotas apply: https://vercel.com/docs/plans/hobby.

## Alternative configurations

`Dockerfile` runs on port 7860. `render.yaml` provides Render Free settings.
These hosts were not provisioned: Render requested card verification, Hugging
Face Docker Spaces required a paid plan, and Back4app's free URL expires after
one hour. No paid plans were selected.
