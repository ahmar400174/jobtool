#!/usr/bin/env python3
"""Search job platforms and export matching listings to Excel."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from job_finder.aggregator import fetch_all
from job_finder.config import load_settings
from job_finder.export import export_excel
from job_finder.report import save_search_report, summary_lines
from job_finder.source_catalog import SOURCES


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(
        description="Search job platforms concurrently and export matches to Excel",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Open the Excel file after export (Windows)",
    )
    parser.add_argument("--all-sources", action="store_true", help="Check every supported platform for this run")
    args = parser.parse_args()

    settings = load_settings()
    if args.all_sources:
        for key, _, _ in SOURCES:
            settings.setdefault("sources", {}).setdefault(key, {})["enabled"] = True
    search = settings.get("search", {})
    print("\n  Job Finder - Concurrent multi-platform search")
    print(f"  Roles: {', '.join(search.get('keywords') or ['QA Engineer'])}")
    print(f"  Location: {search.get('location', 'United States')}")
    print(f"  Date window: {search.get('start_date', 'any')} to {search.get('end_date', 'any')}\n")

    def progress(event):
        print(f"  [{event['completed']}/{event['total']}] {event['source']}: "
              f"{event['count']} jobs, {event['status']}, {event['seconds']:.1f}s", flush=True)

    jobs, source_counts = fetch_all(settings, on_progress=progress)
    report_path = save_search_report(settings, jobs, source_counts)
    print(f"\n  Search took {source_counts.elapsed_seconds:.1f}s; {len(jobs)} unique matches")
    for line in summary_lines(source_counts):
        print(f"  {line}")
    print(f"  Search report: {report_path}\n")

    for name, error in getattr(source_counts, "errors", {}).items():
        print(f"  WARNING: {name} failed: {error}")

    if not jobs:
        print("  No jobs matched. Try adjusting config/settings.yaml")
        return 1

    try:
        path = export_excel(jobs, settings)
    except Exception as exc:
        save_search_report(settings, jobs, source_counts, export_error=str(exc))
        print(f"  Found {len(jobs)} jobs, but Excel export failed: {exc}")
        return 1
    save_search_report(settings, jobs, source_counts, excel_path=path)
    print(f"  Excel saved and verified: {len(jobs)} job rows in {path}\n")

    if args.open:
        import os

        os.startfile(path)  # type: ignore[attr-defined]

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
