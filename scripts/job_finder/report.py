"""Persist per-source coverage and rejection counts for troubleshooting."""
import json
from datetime import datetime
from pathlib import Path
from job_finder.config import project_root


def save_search_report(settings, jobs, counts, *, excel_path=None, export_error=None):
    directory = project_root() / settings.get("output", {}).get("directory", "output")
    directory.mkdir(parents=True, exist_ok=True)
    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "search": settings.get("search", {}),
        "unique_matches": len(jobs),
        "dated_matches": sum(bool(job.posted) for job in jobs),
        "undated_matches": sum(not job.posted for job in jobs),
        "fetched": dict(counts),
        "source_statuses": counts.statuses,
        "source_seconds": counts.durations,
        "elapsed_seconds": counts.elapsed_seconds,
        "filter_counts": counts.filters,
        "errors": counts.errors,
        "coverage_warnings": counts.warnings,
        "excel_export": {
            "status": "failed" if export_error else "saved" if excel_path else "pending" if jobs else "no_matches",
            "path": str(excel_path.resolve()) if excel_path else None,
            "expected_rows": len(jobs),
            "verified_rows": len(jobs) if excel_path else None,
            "error": export_error,
        },
    }
    path = directory / "latest_search_report.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def summary_lines(counts):
    for source, raw in counts.items():
        stats = counts.filters.get(source, {})
        rejected = ", ".join(f"{reason} {stats[reason]}" for reason in
            ("date_range", "undated", "role", "workplace", "pakistan", "us_company", "duplicates") if stats.get(reason))
        yield f"{source}: fetched {raw}, kept {stats.get('unique', 0)}" + (f"; excluded: {rejected}" if rejected else "")
    for source, warnings in counts.warnings.items():
        for warning in dict.fromkeys(warnings):
            yield f"{source} coverage: {warning}"
