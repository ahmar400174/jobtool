import { API_BASE_URL, firebaseConfig } from './config.js';

// Firebase initialization is independent from search availability.
import('https://www.gstatic.com/firebasejs/12.4.0/firebase-app.js')
  .then(({ initializeApp }) => initializeApp(firebaseConfig))
  .catch(() => console.info('Firebase SDK could not load; search is still available.'));

const $ = id => document.getElementById(id);
const base = API_BASE_URL.replace(/\/$/, '');
let currentJobs = [];
let visible = 0;
let busy = false;
let downloading = false;
let sourceNames = new Map();
const localDate = date => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
const today = new Date();
$('end-date').value = localDate(today);
const start = new Date(today); start.setDate(start.getDate() - 30);
$('start-date').value = localDate(start);

function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}

async function api(path, options = {}) {
  const response = await fetch(`${base}${path}`, { ...options, signal: AbortSignal.timeout(310000) });
  const data = await response.json().catch(() => ({ error: 'The server is starting up. Please try again in a minute.' }));
  if (!response.ok) throw new Error(data.error || `Server returned ${response.status}. Please try again.`);
  return data;
}

function status(message, error = false) {
  $('search-status').textContent = message;
  $('search-status').className = error ? 'error' : '';
}

async function connect() {
  if (!base) {
    $('connection').textContent = 'The search server has not been deployed yet. Please finish server setup before searching.';
    return;
  }
  try {
    const config = await api('/api/config');
    sourceNames = new Map(config.sources.map(source => [source.key, source.label]));
    $('country').replaceChildren(...config.countries.map(country => {
      const option = node('option', country); option.value = country; return option;
    }));
    $('country').disabled = false;
    $('sources').replaceChildren(...config.sources.map(source => {
      const label = node('label', undefined, 'check');
      const input = document.createElement('input');
      input.type = 'checkbox'; input.name = 'source'; input.value = source.key; input.checked = true;
      label.append(input, document.createTextNode(source.label));
      return label;
    }));
    $('search-button').disabled = false;
    $('connection').textContent = 'Search server ready. Keep this page open to view and download your results.';
  } catch (error) {
    $('connection').replaceChildren(document.createTextNode(`${error.message} `));
    const retry = node('button', 'Retry connection', 'text-button'); retry.type = 'button';
    retry.style.float = 'none'; retry.style.margin = '0'; retry.addEventListener('click', connect);
    $('connection').append(retry);
  }
}

$('select-all').addEventListener('click', () => {
  document.querySelectorAll('input[name=source]').forEach(input => { input.checked = true; });
});

function renderProgress(events) {
  $('progress').replaceChildren(...events.map(event => node('span', `${event.source}: ${event.count} · ${event.status}`, `progress-item ${event.status}`)));
}

function safeUrl(value) {
  try { const url = new URL(value); return ['https:', 'http:'].includes(url.protocol) ? url.href : null; }
  catch { return null; }
}

function renderMore() {
  const next = currentJobs.slice(visible, visible + 25);
  const cards = next.map(job => {
    const card = node('article', undefined, 'job');
    const title = node('h3');
    const url = safeUrl(job.url);
    if (url) {
      const link = node('a', job.title); link.href = url; link.target = '_blank'; link.rel = 'noopener noreferrer';
      title.append(link);
    } else title.textContent = job.title;
    const meta = node('div', undefined, 'job-meta');
    for (const value of [job.location || 'Location unspecified', job.remote, job.posted || 'Date unavailable']) meta.append(node('span', value));
    card.append(node('span', job.source, 'source-label'), title, node('p', job.company, 'job-company'), meta);
    if (job.salary) card.append(node('p', job.salary, 'job-salary'));
    if (job.description) {
      const details = node('details');
      details.append(node('summary', 'Read description excerpt'), node('p', job.description.replace(/<[^>]*>/g, ' ')));
      card.append(details);
    }
    return card;
  });
  $('results').append(...cards);
  visible += next.length;
  $('load-more').hidden = visible >= currentJobs.length;
}
$('load-more').addEventListener('click', renderMore);

function complete(data) {
  currentJobs = data.jobs; visible = 0;
  $('result-count').textContent = `${data.count} unique ${data.count === 1 ? 'opportunity' : 'opportunities'}`;
  $('results').replaceChildren();
  if (data.count) renderMore();
  else {
    const empty = node('div', undefined, 'empty');
    empty.append(node('h3', 'No matches this time.'), node('p', 'Try a broader role, a wider date range, or include undated listings.'));
    $('results').append(empty);
  }
  $('download').hidden = !data.download_available;
  $('download').href = '#download';
  const warnings = Object.entries(data.warnings || {}).flatMap(([source, items]) => items.map(message => `${source}: ${message}`));
  const errors = Object.entries(data.errors || {}).map(([source, message]) => `${source}: ${message}`);
  $('coverage').hidden = false;
  $('coverage-content').replaceChildren(...[data.coverage, ...errors, ...warnings].map(message => node('p', message)));
  const allFailed = Object.values(data.source_statuses).filter(value => value !== 'disabled').every(value => value === 'failed');
  status(allFailed ? 'The selected platforms could not be reached. See platform issues below and try again later.' : data.export_error || `Search finished in ${data.elapsed_seconds.toFixed(1)} seconds.${errors.length ? ` ${errors.length} platforms could not be reached.` : ''}`, allFailed || Boolean(data.export_error));
}

async function searchPlatforms(search) {
  const started = performance.now();
  const parts = new Array(search.sources.length);
  const events = [];
  const warnings = {}, errors = {}, statuses = {};
  let next = 0;
  async function worker() {
    while (next < search.sources.length) {
      const index = next++;
      const key = search.sources[index];
      let label = sourceNames.get(key) || key;
      try {
        const result = await api('/api/source', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...search, sources: [key] }) });
        parts[index] = result.jobs;
        const active = Object.entries(result.source_statuses).find(([, value]) => value !== 'disabled');
        if (active) { label = active[0]; statuses[label] = active[1]; }
        Object.assign(warnings, result.warnings); Object.assign(errors, result.errors);
        events.push({ source: label, count: Object.values(result.fetched).reduce((sum, value) => sum + value, 0), status: active?.[1] || 'ok' });
      } catch (error) {
        parts[index] = []; errors[label] = error.message; statuses[label] = 'failed';
        events.push({ source: label, count: 0, status: 'failed' });
      }
      renderProgress(events);
      status(`Searching platforms… ${events.length} of ${search.sources.length} finished.`);
    }
  }
  await Promise.all(Array.from({ length: Math.min(3, search.sources.length) }, worker));
  const raw = parts.flat();
  status('Combining matches and removing duplicates…');
  const merged = raw.length ? await api('/api/merge', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ jobs: raw }) }) : { jobs: [], count: 0 };
  complete({ ...merged, download_available: merged.count > 0, warnings, errors, source_statuses: statuses,
    elapsed_seconds: (performance.now() - started) / 1000,
    coverage: 'Free hosting checks up to 1 LinkedIn page per query, 2 Himalayas/public pages, and 30 comments in one HN thread. Each platform returns up to 100 matches with description excerpts; original listings contain the full details.' });
}

$('download').addEventListener('click', async event => {
  event.preventDefault();
  if (downloading || !currentJobs.length) return;
  downloading = true; $('download').textContent = 'Preparing Excel…';
  try {
    const response = await fetch(`${base}/api/export`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ jobs: currentJobs }), signal: AbortSignal.timeout(90000) });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.error || 'Excel export failed. Please try again.');
    }
    const url = URL.createObjectURL(await response.blob());
    const link = node('a'); link.href = url; link.download = 'job-finder-results.xlsx';
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  } catch (error) { status(error.message, true); }
  finally { downloading = false; $('download').textContent = 'Download Excel ↓'; }
});

$('search-form').addEventListener('submit', async event => {
  event.preventDefault();
  if (busy) return;
  const selected = [...document.querySelectorAll('input[name=source]:checked')].map(input => input.value);
  if (!selected.length) { status('Choose at least one platform.', true); return; }
  if ($('start-date').value > $('end-date').value) { status('Start date must be on or before end date.', true); return; }
  busy = true; $('search-button').disabled = true; $('search-button').textContent = 'Searching…';
  $('download').hidden = true; $('load-more').hidden = true; $('coverage').hidden = true;
  $('results').replaceChildren(); $('progress').replaceChildren();
  $('result-count').textContent = 'Finding your next move…'; status('Starting your search…');
  try {
    await searchPlatforms({
      role: $('role').value.trim(), country: $('country').value,
      start_date: $('start-date').value, end_date: $('end-date').value,
      remote_only: $('remote-only').checked, exclude_pakistan: $('exclude-pakistan').checked,
      include_undated: $('include-undated').checked, sources: selected
    });
  } catch (error) { status(error.message, true); $('result-count').textContent = 'Search could not finish'; }
  finally { busy = false; $('search-button').disabled = false; $('search-button').replaceChildren(document.createTextNode('Search jobs '), node('span', '↗')); }
});

connect();
