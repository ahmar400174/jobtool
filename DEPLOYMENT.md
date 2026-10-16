# Firebase website + free Python server

The desktop application still works. The web application reuses its Python
search/filter/export code through `scripts/web_server.py`.

## Run locally

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-web.txt
.\.venv\Scripts\python.exe scripts/web_server.py
```

Open http://127.0.0.1:8765. The UI uses the local API automatically.

## Deploy with no card (Back4app Containers Free)

The repository contains a production `Dockerfile`. Create a container app on
Back4app, connect `ahmar400174/jobtool`, select branch `main`, and choose **Free**.
The free plan includes 0.25 CPU, 256 MB RAM, and 100 GB transfer, with no credit
card required according to its current published pricing:
https://www.back4app.com/pricing/container-as-a-service.

Use port **7860**, the repository root as the build context, and `Dockerfile`.
Set `ALLOWED_ORIGINS` to
`https://jobs-tool.web.app,https://jobs-tool.firebaseapp.com`.
After deployment, verify `/api/health` on the assigned HTTPS URL, then put that
exact URL into the production branch of `API_BASE_URL` in `web/config.js`.

The production API URL is deliberately blank until a backend exists. This keeps
the UI from sending requests to an unverified or unowned server domain.

## Alternative: Render Free

Render requested card verification in this account even with the Free instance
selected. The service was not created. If you complete that verification yourself,
the following configuration is ready to deploy without selecting a paid plan.

Push the project to GitHub, then create a Render Web Service from that repository.
Use the settings in `render.yaml`, or import it as a Render Blueprint:

| Setting | Value |
| --- | --- |
| Runtime | Python 3 |
| Instance | **Free** |
| Build command | `pip install -r requirements-web.txt` |
| Start command | `gunicorn --chdir scripts web_server:app --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 120` |
| Health check | `/api/health` |
| `PYTHON_VERSION` | `3.13.5` |
| `ALLOWED_ORIGINS` | `https://jobs-tool.web.app,https://jobs-tool.firebaseapp.com` |

Use exactly **one worker**: searches are held in memory within that process.
The server permits one search at a time and retains up to 20 results for up to
one hour. Downloads are isolated per search and never overwrite desktop exports.
Restarts and free-instance spin-down discard results; download your workbook
before leaving. No database, disk subscription, or paid Firebase Functions is used.

After deployment, check `https://YOUR-SERVICE.onrender.com/api/health`, then put
the service's exact HTTPS URL in `web/config.js` as `API_BASE_URL`.
Do not assume the desired service name is available.

## Deploy the website (Firebase Hosting)

The Firebase web configuration is included in `web/config.js`. This public client
configuration is not an administrator credential. Sign in using the Firebase CLI:

```powershell
npx firebase-tools login
npx firebase-tools deploy --only hosting --project jobs-tool
```

Only the `web/` directory is published, at https://jobs-tool.web.app.
Firebase's static Hosting service is used; no paid backend is provisioned there.

## Verify

```powershell
.\.venv\Scripts\python.exe -m pytest scripts/tests -q
node --check web/app.js
node --check web/config.js
```

On the deployed page, run a search and check platform completion, job links,
coverage warnings, and the Excel download. Public boards may block cloud IPs;
individual source failures appear in the results instead of stopping other boards.
The web search caps LinkedIn/Himalayas at 3 pages, other HTML boards at 2 pages,
and HN at 100 comments per thread across at most 2 threads to fit the free server.

Render's free service sleeps after 15 minutes without requests and may take about
a minute to wake. Its free instance hours and network/build quotas still apply.
See https://render.com/docs/free and https://firebase.google.com/docs/hosting/usage-quotas-pricing.
