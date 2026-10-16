"""Search enabled platforms concurrently, then filter and deduplicate."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from time import perf_counter
from typing import Any, Callable

from job_finder.filters import apply_filters
from job_finder.source_catalog import SOURCES
from job_finder.countries import jobicy_geo
from job_finder.search_terms import query_terms, jobicy_terms
from job_finder.sources.public_boards import fetch_public
from job_finder.models import JobListing
from job_finder.sources.jobicy import fetch_jobicy
from job_finder.sources.linkedin import fetch_linkedin
from job_finder.sources.remoteok import fetch_remoteok
from job_finder.sources.remotive import fetch_remotive


class SourceCounts(dict):
    """Compatible record counts, plus timing, failures and coverage details."""
    def __init__(self):
        super().__init__()
        self.errors = {}
        self.warnings = {}
        self.filters = {}
        self.raw_jobs = []
        self.statuses = {}
        self.durations = {}
        self.elapsed_seconds = 0.0


def _fetch_source(key, search, cfg):
    """Each worker owns its configuration and warning list."""
    if key == "remoteok":
        cfg.setdefault("_warnings", []).append("Current public feed; full historical coverage is unavailable")
        return fetch_remoteok()
    if key == "remotive":
        cfg.setdefault("_warnings", []).append("Current public feed; full historical coverage is unavailable")
        return fetch_remotive()
    if key == "jobicy":
        cfg.setdefault("_warnings", []).append("API results are limited per query; full historical coverage is unavailable")
        return fetch_jobicy(
            tags=jobicy_terms(search.get("keywords")),
            geo=jobicy_geo(search["location"]) if "location" in search else cfg.get("geo", "usa"),
            count=int(cfg.get("count", 200)),
            warnings=cfg["_warnings"],
        )
    if key == "linkedin":
        return fetch_linkedin(
            keywords=query_terms(search.get("keywords")),
            location=search.get("location", "United States"),
            max_pages=int(cfg.get("max_pages", 6)),
            delay=float(cfg.get("delay_seconds", 2)),
            fetch_details=bool(cfg.get("fetch_details", True)),
            detail_delay=float(cfg.get("detail_delay_seconds", 0.6)),
            detail_workers=int(cfg.get("detail_workers", 4)),
            remote_only=bool(search.get("remote_only", True)),
            start_date=search.get("start_date", "1970-01-01"),
            end_date=search.get("end_date", "2099-12-31"),
            warnings=cfg.setdefault("_warnings", []),
            max_retries=int(cfg.get("max_retries", 2)),
            retry_backoff=float(cfg.get("retry_backoff_seconds", 5)),
            max_retry_wait=float(cfg.get("max_retry_wait_seconds", 60)),
        )
    return fetch_public(key, search, cfg)


def _run_source(key, search, cfg):
    started = perf_counter()
    try:
        return _fetch_source(key, search, cfg), None, perf_counter() - started
    except Exception as exc:
        return [], str(exc), perf_counter() - started


def fetch_all(
    settings: dict[str, Any],
    on_progress: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[list[JobListing], SourceCounts]:
    search = settings.get("search", {})
    sources_cfg = settings.get("sources", {})
    counts = SourceCounts()
    started = perf_counter()
    enabled = []
    for key, label, default in SOURCES:
        # Preserve the existing RemoteOK result name for exports/callers.
        label = "RemoteOK" if key == "remoteok" else label
        cfg = dict(sources_cfg.get(key, {}) or {})
        cfg.pop("_warnings", None)
        counts.statuses[label] = "pending" if cfg.get("enabled", default) else "disabled"
        if counts.statuses[label] == "pending":
            enabled.append((key, label, cfg))

    workers = max(1, min(16, int(settings.get("performance", {}).get("source_workers", 8))))
    results = {}
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="job-source") as pool:
        futures = {pool.submit(_run_source, key, search, cfg): (label, cfg)
                   for key, label, cfg in enabled}
        for future in as_completed(futures):
            label, cfg = futures[future]
            jobs, error, duration = future.result()
            results[label] = jobs
            counts.durations[label] = round(duration, 3)
            warnings = cfg.get("_warnings", [])
            if warnings:
                counts.warnings[label] = warnings
            status = "failed" if error is not None else "partial" if warnings else "ok"
            counts.statuses[label] = status
            if error is not None:
                counts.errors[label] = error
            if on_progress:
                on_progress({"source": label, "status": status, "count": len(jobs),
                             "seconds": counts.durations[label], "error": error,
                             "completed": len(results), "total": len(enabled)})

    # Stable source order keeps duplicate selection independent of network speed.
    raw = []
    for _, label, _ in enabled:
        counts[label] = len(results[label])
        raw.extend(results[label])
    counts.raw_jobs = raw
    filtered = apply_filters(raw, settings, counts.filters)
    deduped = _dedupe(filtered)
    kept = {id(job) for job in deduped}
    for job in filtered:
        stats = counts.filters[job.source]
        key = "unique" if id(job) in kept else "duplicates"
        stats[key] = stats.get(key, 0) + 1
    counts.elapsed_seconds = round(perf_counter() - started, 3)
    return deduped, counts


_SOURCE_PRIORITY = {"LinkedIn": 0, "Jobicy": 1, "RemoteOK": 2, "Remotive": 3}


def _dedupe(jobs: list[JobListing]) -> list[JobListing]:
    best: dict[str, JobListing] = {}
    for job in jobs:
        key = job.dedupe_key
        existing = best.get(key)
        if existing is None:
            best[key] = job
            continue
        job_pri = _SOURCE_PRIORITY.get(job.source, 99)
        existing_pri = _SOURCE_PRIORITY.get(existing.source, 99)
        if job_pri < existing_pri:
            best[key] = job
    result = list(best.values())
    result.sort(key=lambda j: (j.source, j.posted, j.title), reverse=True)
    return result
