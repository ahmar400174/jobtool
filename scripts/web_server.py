"""HTTP interface for the existing search engine; one process on the free plan.

Searches run outside request threads so polling survives long source queries.
Results are temporary, unguessable, and isolated from desktop output files.
"""
from __future__ import annotations

import copy
import logging
import os
import secrets
import tempfile
import threading
import time
from datetime import date

from flask import Flask, jsonify, request, send_file

from job_finder.aggregator import fetch_all
from job_finder.config import load_settings, project_root
from job_finder.countries import COUNTRIES, normalize_country
from job_finder.export import export_excel
from job_finder.source_catalog import SOURCES

app = Flask(__name__, static_folder=str(project_root() / "web"), static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024
log = logging.getLogger(__name__)
ORIGINS = set(os.environ.get("ALLOWED_ORIGINS", "https://jobs-tool.web.app,https://jobs-tool.firebaseapp.com,http://localhost:8080,http://127.0.0.1:8080").split(","))
if os.environ.get("RENDER_EXTERNAL_URL"):
    ORIGINS.add(os.environ["RENDER_EXTERNAL_URL"].rstrip("/"))
_lock = threading.Lock()
_searches: dict[str, dict] = {}
_active = False
TTL_SECONDS = 3600
MAX_RESULTS = 20


@app.before_request
def check_origin():
    origin = request.headers.get("Origin")
    if origin and origin not in ORIGINS:
        return jsonify(error="This website is not allowed to use this server."), 403


@app.after_request
def response_headers(response):
    origin = request.headers.get("Origin")
    if origin in ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.vary.add("Origin")
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.errorhandler(413)
def too_large(_error):
    return jsonify(error="Search request is too large."), 413


@app.get("/")
def index():
    return app.send_static_file("index.html")


@app.get("/api/health")
def health():
    return jsonify(status="ok", service="jobs-tool-api")


@app.get("/api/config")
def configuration():
    return jsonify(countries=list(COUNTRIES), sources=[{"key": key, "label": label} for key, label, _ in SOURCES])


def search_settings(data):
    if not isinstance(data, dict):
        raise ValueError("Send a search object.")
    role = data.get("role", "")
    if not isinstance(role, str) or not 2 <= len(role.strip()) <= 120:
        raise ValueError("Enter a role between 2 and 120 characters.")
    country = data.get("country", "Worldwide")
    if not isinstance(country, str) or normalize_country(country) not in COUNTRIES:
        raise ValueError("Choose a supported country.")
    try:
        start = date.fromisoformat(data.get("start_date", ""))
        end = date.fromisoformat(data.get("end_date", ""))
    except (TypeError, ValueError):
        raise ValueError("Dates must use YYYY-MM-DD.") from None
    if start > end or (end - start).days > 366:
        raise ValueError("Choose an ordered date range of at most one year.")
    selected = data.get("sources")
    valid = {key for key, _, _ in SOURCES}
    if not isinstance(selected, list) or not selected or any(not isinstance(key, str) or key not in valid for key in selected):
        raise ValueError("Choose at least one supported platform.")
    for flag in ("remote_only", "exclude_pakistan", "include_undated"):
        if flag in data and not isinstance(data[flag], bool):
            raise ValueError(f"{flag} must be true or false.")
    settings = copy.deepcopy(load_settings())
    settings["search"] = {
        "keywords": [role.strip()], "location": normalize_country(country),
        "start_date": start.isoformat(), "end_date": end.isoformat(),
        "remote_only": data.get("remote_only", True),
        "exclude_pakistan": data.get("exclude_pakistan", True),
        "include_undated": data.get("include_undated", False),
        "include_hybrid": False, "us_company_only": False,
    }
    sources = settings.setdefault("sources", {})
    for key in valid:
        sources.setdefault(key, {})["enabled"] = key in selected
    # Keep public web searches bounded for a 512 MB free instance.
    sources["linkedin"]["max_pages"] = min(3, int(sources["linkedin"].get("max_pages", 3)))
    sources["linkedin"]["detail_workers"] = 2
    sources["himalayas"]["max_pages"] = 3
    sources["hackernews"]["max_comments"] = 100
    sources["hackernews"]["months"] = 2
    for key in valid - {"linkedin", "himalayas"}:
        sources[key]["max_pages"] = 2
    settings["performance"] = {"source_workers": 4}
    return settings


def _prune():
    now = time.monotonic()
    expired = [key for key, value in _searches.items() if value["status"] != "running" and now - value["created"] > TTL_SECONDS]
    for key in expired:
        del _searches[key]
    completed = [key for key, value in _searches.items() if value["status"] != "running"]
    for key in completed[:max(0, len(_searches) - MAX_RESULTS + 1)]:
        del _searches[key]


def run_search(search_id, settings):
    global _active

    def progress(event):
        with _lock:
            _searches[search_id]["progress"].append(event)

    try:
        jobs, counts = fetch_all(settings, on_progress=progress)
        export = None
        export_error = None
        if jobs:
            try:
                with tempfile.TemporaryDirectory(prefix="jobs-tool-") as directory:
                    settings["output"] = {"directory": directory, "filename": "jobs.xlsx", "sheet_name": "Jobs"}
                    export = export_excel(jobs, settings).read_bytes()
            except Exception:
                log.exception("Excel export failed")
                export_error = "Jobs were found, but Excel export failed. You can still view the results below."
        result = {
            "status": "complete", "jobs": [job.to_row() for job in jobs],
            "count": len(jobs), "source_statuses": counts.statuses,
            "warnings": counts.warnings, "errors": counts.errors,
            "filter_counts": counts.filters, "elapsed_seconds": counts.elapsed_seconds,
            "download_available": export is not None, "export_error": export_error,
            "coverage": "Web searches check up to 3 LinkedIn/Himalayas pages, 2 other public pages, and 100 comments per HN thread (2 threads).",
        }
        with _lock:
            _searches[search_id].update(result, export=export)
    except Exception:
        log.exception("Search failed")
        with _lock:
            _searches[search_id].update(status="failed", error="The search could not finish. Please try again.")
    finally:
        with _lock:
            _active = False


@app.route("/api/search", methods=["POST", "OPTIONS"])
def start_search():
    global _active
    if request.method == "OPTIONS":
        return "", 204
    try:
        settings = search_settings(request.get_json(silent=True))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    with _lock:
        _prune()
        if _active:
            return jsonify(error="The free server is finishing another search. Please try again shortly."), 429
        _active = True
        search_id = secrets.token_urlsafe(24)
        _searches[search_id] = {"status": "running", "created": time.monotonic(), "progress": []}
    threading.Thread(target=run_search, args=(search_id, settings), daemon=True, name="web-search").start()
    return jsonify(id=search_id, status="running"), 202


@app.get("/api/search/<search_id>")
def search_status(search_id):
    with _lock:
        _prune()
        result = _searches.get(search_id)
        if result is None:
            return jsonify(error="Search expired or the server restarted. Start a new search."), 404
        return jsonify({key: value for key, value in result.items() if key not in {"created", "export"}})


@app.get("/api/search/<search_id>/excel")
def download(search_id):
    import io
    with _lock:
        _prune()
        result = _searches.get(search_id)
        export = result.get("export") if result else None
    if not export:
        return jsonify(error="No workbook is available. Run a search first."), 404
    return send_file(io.BytesIO(export), as_attachment=True, download_name="job-finder-results.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8765"))
    ORIGINS.update({f"http://127.0.0.1:{port}", f"http://localhost:{port}"})
    app.run(host="127.0.0.1", port=port)
