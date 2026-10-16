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
```

Live checks include a platform search, result links, coverage warnings, and
opening the downloaded Excel workbook.

Verified on 2026-10-16: 106 offline tests passed. A browser search across all
13 platforms returned 130 unique jobs in 17.6 seconds; 12 platforms completed
and LinkedIn was blocked. The Excel file downloaded from the Firebase page
opened successfully with all 130 job rows. The API health check also passed.

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
