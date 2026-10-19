import test from 'node:test';
import assert from 'node:assert/strict';
import { readLinkedInCache, saveLinkedInCache, cachedLinkedInResult, MAX_AGE_MS } from '../../web/linkedin-cache.js';

const search = { role: 'Engineer', country: 'Worldwide', start_date: '2026-10-01', end_date: '2026-10-19',
  remote_only: true, exclude_pakistan: true, include_undated: false, sources: ['linkedin'] };
const result = () => ({ jobs: [{ title: 'Engineer' }], fetched: { LinkedIn: 1 },
  source_statuses: { LinkedIn: 'ok' }, errors: {}, warnings: {} });
const storage = () => { const data = new Map(); return { getItem: k => data.get(k), setItem: (k, v) => data.set(k, v) }; };
const now = Date.parse('2026-10-19T12:00:00Z');

test('reuse is restricted to matching filters, independent of other selected platforms', () => {
  const store = storage();
  assert.ok(saveLinkedInCache(search, result(), now, store));
  assert.ok(readLinkedInCache({ ...search, sources: ['linkedin', 'remotive'] }, now, store));
  for (const changes of [{ role: 'Designer' }, { country: 'Canada' }, { start_date: '2026-10-18' },
    { end_date: '2026-10-18' }, { remote_only: false }, { exclude_pakistan: false }, { include_undated: true }]) {
    assert.equal(readLinkedInCache({ ...search, ...changes }, now, store), null);
  }
});

test('expired, future and corrupt browser entries cannot be used', () => {
  const store = storage(); saveLinkedInCache(search, result(), now, store);
  assert.equal(readLinkedInCache(search, now + MAX_AGE_MS + 1, store), null);
  assert.equal(readLinkedInCache(search, now - 1, store), null);
  assert.equal(readLinkedInCache(search, now, { getItem: () => '{broken' }), null);
});

test('disabled storage and quota errors do not break searches', () => {
  const blocked = { getItem() { throw Error('blocked'); }, setItem() { throw Error('quota'); } };
  assert.equal(readLinkedInCache(search, now, blocked), null);
  assert.equal(saveLinkedInCache(search, result(), now, blocked), false);
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, get() { throw Error('security'); } });
  try {
    assert.equal(readLinkedInCache(search, now), null);
    assert.equal(saveLinkedInCache(search, result(), now), false);
  } finally { delete globalThis.localStorage; }
});

test('failures preserve cache; a successful empty response replaces it', () => {
  const store = storage(); saveLinkedInCache(search, result(), now, store);
  const failed = result(); failed.errors.LinkedIn = 'HTTP 429'; failed.jobs = [];
  assert.equal(saveLinkedInCache(search, failed, now + 1000, store), false);
  const limited = result(); limited.jobs = []; limited.retry_after_seconds = 300;
  limited.source_statuses.LinkedIn = 'partial';
  assert.equal(saveLinkedInCache(search, limited, now + 1000, store), false);
  assert.equal(readLinkedInCache(search, now + 1000, store).result.jobs.length, 1);
  const empty = result(); empty.jobs = [];
  assert.ok(saveLinkedInCache(search, empty, now + 1000, store));
  assert.equal(readLinkedInCache(search, now + 1000, store).result.jobs.length, 0);
});

test('reused server results retain their original age and display a timestamp', () => {
  const store = storage(); const response = result();
  response.cache_info = { cached: true, fetched_at: new Date(now - 700000).toISOString() };
  assert.ok(saveLinkedInCache(search, response, now, store));
  const entry = readLinkedInCache(search, now, store);
  assert.equal(entry.age, 700000);
  const reused = cachedLinkedInResult(entry, 'Rate limited.');
  assert.equal(reused.cache_info.age_seconds, 700);
  assert.match(reused.warnings.LinkedIn[0], /2026-10-19T11:48:20.000Z/);
  assert.deepEqual(entry.result.warnings, {});
});
