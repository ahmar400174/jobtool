"""Bounded caching and request coalescing for LinkedIn web searches.

This cache is per Python process. Browser caching covers a user's repeated
searches even when a serverless request reaches a different process.
"""
from collections import OrderedDict
from copy import deepcopy
from datetime import datetime, timezone
import json
import re
from threading import Lock
from time import monotonic


class LinkedInSearchBusy(RuntimeError):
    pass


class LinkedInResultCache:
    fresh_seconds = 600
    stale_seconds = 86400

    def __init__(self, clock=monotonic):
        self.clock = clock
        self.entries = OrderedDict()
        self.lock = Lock()
        self.request_lock = Lock()

    def clear(self):
        with self.lock:
            self.entries.clear()

    def _cached(self, key):
        with self.lock:
            entry = self.entries.get(key)
            if entry is None:
                return None
            age = self.clock() - entry["created"]
            if age < 0 or age > self.stale_seconds:
                del self.entries[key]
                return None
            self.entries.move_to_end(key)
            return deepcopy(entry), int(age)

    @staticmethod
    def _reuse(cached, reason):
        entry, age = cached
        result = entry["result"]
        result["cache_info"] = {"cached": True, "fetched_at": entry["fetched_at"], "age_seconds": age}
        result.setdefault("warnings", {}).setdefault("LinkedIn", []).append(
            f"{reason} Showing LinkedIn results fetched at {entry['fetched_at']} ({age // 60} minutes ago)."
        )
        result["source_statuses"]["LinkedIn"] = "partial"
        return result

    def run(self, settings, fetch):
        key = json.dumps({"search": settings["search"], "linkedin": settings["sources"]["linkedin"]}, sort_keys=True)
        cached = self._cached(key)
        if cached and cached[1] < self.fresh_seconds:
            return self._reuse(cached, "Reused a recent search to reduce repeated LinkedIn requests.")
        if not self.request_lock.acquire(blocking=False):
            if cached:
                return self._reuse(cached, "Another LinkedIn search is running on this server.")
            raise LinkedInSearchBusy("A LinkedIn search is already running on this server. Retry in 10 seconds.")
        try:
            result = fetch()
            error = result.get("errors", {}).get("LinkedIn", "")
            messages = " ".join([error, *result.get("warnings", {}).get("LinkedIn", [])])
            if "429" in messages or "cooling down" in messages.lower():
                match = re.search(r"at least (\d+) seconds", messages)
                retry = int(match.group(1)) if match else 300
                if cached and not result.get("jobs"):
                    live_warnings = result.get("warnings", {}).get("LinkedIn", [])
                    result = self._reuse(cached, "LinkedIn temporarily rate-limited the live request.")
                    result["warnings"]["LinkedIn"].extend(live_warnings)
                    if error:
                        result.setdefault("errors", {})["LinkedIn"] = error
                result["retry_after_seconds"] = retry
                return result
            if not error and result.get("source_statuses", {}).get("LinkedIn") in {"ok", "partial"}:
                fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
                result["cache_info"] = {"cached": False, "fetched_at": fetched_at, "age_seconds": 0}
                with self.lock:
                    self.entries[key] = {"created": self.clock(), "fetched_at": fetched_at, "result": deepcopy(result)}
                    self.entries.move_to_end(key)
                    while len(self.entries) > 16:
                        self.entries.popitem(last=False)
            return result
        finally:
            self.request_lock.release()
