import { API_BASE_URL, firebaseConfig } from './config.js';

// Firebase initialization is independent from search availability.
import('https://www.gstatic.com/firebasejs/12.4.0/firebase-app.js')
  .then(({ initializeApp }) => initializeApp(firebaseConfig))
  .catch(() => console.info('Firebase SDK could not load; search is still available.'));

const $ = id => document.getElementById(id);
const base = API_BASE_URL.replace(/\/$/, '');
let currentId = null;
let currentJobs = [];
let visible = 0;
let busy = false;
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
  const response = await fetch(`${base}${path}`, { ...options, signal: AbortSignal.timeout(90000) });
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
    $('connection').textContent = 'Search server ready. Results and downloads are kept for up to one hour.';
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
      details.append(node('summary', 'Read description'), node('p', job.description.replace(/<[^>]*>/g, ' ')));
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
  $('download').href = `${base}/api/search/${currentId}/excel`;
  const warnings = Object.entries(data.warnings || {}).flatMap(([source, items]) => items.map(message => `${source}: ${message}`));
  const errors = Object.entries(data.errors || {}).map(([source, message]) => `${source}: ${message}`);
  $('coverage').hidden = false;
  $('coverage-content').replaceChildren(...[data.coverage, ...errors, ...warnings].map(message => node('p', message)));
  const allFailed = Object.values(data.source_statuses).filter(value => value !== 'disabled').every(value => value === 'failed');
  status(allFailed ? 'The selected platforms could not be reached. See platform issues below and try again later.' : data.export_error || `Search finished in ${data.elapsed_seconds.toFixed(1)} seconds.${errors.length ? ` ${errors.length} platforms could not be reached.` : ''}`, allFailed || Boolean(data.export_error));
}

async function poll(id) {
  // Briefly retry a dropped connection without starting duplicate searches.
  let failures = 0;
  for (;;) {
    let data;
    try { data = await api(`/api/search/${id}`); failures = 0; }
    catch (error) {
      if (++failures >= 3) throw error;
      status('Connection interrupted. Reconnecting to your search…');
      await new Promise(resolve => setTimeout(resolve, 4000)); continue;
    }
    renderProgress(data.progress || []);
    if (data.status === 'failed') throw new Error(data.error);
    if (data.status === 'complete') { complete(data); return; }
    status(`Searching platforms… ${(data.progress || []).length} finished. You can keep this page open while the remaining platforms respond.`);
    await new Promise(resolve => setTimeout(resolve, 2000));
  }
}

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
    const search = await api('/api/search', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
      role: $('role').value.trim(), country: $('country').value,
      start_date: $('start-date').value, end_date: $('end-date').value,
      remote_only: $('remote-only').checked, exclude_pakistan: $('exclude-pakistan').checked,
      include_undated: $('include-undated').checked, sources: selected
    }) });
    currentId = search.id;
    await poll(currentId);
  } catch (error) { status(error.message, true); $('result-count').textContent = 'Search could not finish'; }
  finally { busy = false; $('search-button').disabled = false; $('search-button').replaceChildren(document.createTextNode('Search jobs '), node('span', '↗')); }
});

connect();
