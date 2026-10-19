const STORAGE_KEY = 'jobfinder.linkedin.v1';
export const FRESH_MS = 10 * 60 * 1000;
export const MAX_AGE_MS = 24 * 60 * 60 * 1000;

function searchKey(search) {
  return JSON.stringify({ role: search.role.trim().toLowerCase().replace(/\s+/g, ' '), country: search.country,
    start_date: search.start_date, end_date: search.end_date, remote_only: search.remote_only,
    exclude_pakistan: search.exclude_pakistan, include_undated: search.include_undated });
}

const object = value => value && typeof value === 'object' && !Array.isArray(value);

function valid(result) {
  return object(result) && Array.isArray(result.jobs) && object(result.fetched)
    && object(result.source_statuses) && object(result.errors) && object(result.warnings);
}

export function readLinkedInCache(search, now = Date.now(), storage) {
  try {
    storage ??= globalThis.localStorage;
    const entry = JSON.parse(storage.getItem(STORAGE_KEY));
    if (!entry || entry.key !== searchKey(search) || !valid(entry.result)) return null;
    const age = now - entry.storedAt;
    if (!Number.isFinite(age) || age < 0 || age > MAX_AGE_MS) return null;
    return { ...entry, age };
  } catch { return null; }
}

export function saveLinkedInCache(search, result, now = Date.now(), storage) {
  if (!valid(result) || result.errors.LinkedIn || !['ok', 'partial'].includes(result.source_statuses.LinkedIn)) return false;
  if (result.retry_after_seconds && !result.jobs.length) return false;
  try {
    storage ??= globalThis.localStorage;
    const storedAt = result.cache_info?.cached ? Date.parse(result.cache_info.fetched_at) : now;
    if (!Number.isFinite(storedAt) || now - storedAt > MAX_AGE_MS || storedAt > now) return false;
    storage.setItem(STORAGE_KEY, JSON.stringify({ key: searchKey(search), storedAt, result }));
    return true;
  } catch { return false; }
}

export function cachedLinkedInResult(entry, reason) {
  const result = structuredClone(entry.result);
  const fetchedAt = new Date(entry.storedAt).toISOString();
  result.cache_info = { cached: true, fetched_at: fetchedAt, age_seconds: Math.floor(entry.age / 1000) };
  result.source_statuses.LinkedIn = 'partial';
  (result.warnings.LinkedIn ||= []).push(`${reason} Showing LinkedIn results fetched at ${fetchedAt}.`);
  return result;
}
