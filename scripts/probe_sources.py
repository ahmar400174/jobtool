"""Bounded live check of ALL adapters; does not export jobs or change settings."""
import json
import sys
from datetime import date, timedelta
from job_finder.aggregator import fetch_all
from job_finder.config import project_root
from job_finder.source_catalog import SOURCES


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    today = date.today()
    settings = {
        "search": {"keywords": ["QA Engineer"], "location": "Worldwide", "remote_only": True,
                   "start_date": (today - timedelta(days=30)).isoformat(), "end_date": today.isoformat()},
        "sources": {key: {"enabled": True, "max_pages": 1, "max_details": 3,
                          "story_scan_limit": 8, "months": 1, "max_comments": 15}
                    for key, _, _ in SOURCES},
        "performance": {"source_workers": 8},
    }
    def progress(event):
        print(f"[{event['completed']}/{event['total']}] {event['source']}: {event['count']} public records, "
              f"{event['status']}, {event['seconds']:.1f}s", flush=True)
        if event["error"]:
            print(f"  {event['error']}", flush=True)
    _, counts = fetch_all(settings, on_progress=progress)
    report = {"checked_at": today.isoformat(), "elapsed_seconds": counts.elapsed_seconds,
              "fetched": dict(counts), "statuses": counts.statuses,
              "source_seconds": counts.durations, "errors": counts.errors,
              "coverage_warnings": counts.warnings}
    path = project_root() / "output" / "latest_source_check.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nChecked {len(counts)} platforms in {counts.elapsed_seconds:.1f}s. Report: {path}")
    return 0 if not counts.errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
