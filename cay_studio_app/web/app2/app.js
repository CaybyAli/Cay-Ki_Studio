'use strict';
/* Cay Studio 0.14 – one script for the whole studio (replaces 15 layered scripts).
   Rules: one next step per screen, no inline styles or scripts (strict CSP),
   polling never re-renders while Cay types or plays audio/video. */

const S = { token: '', version: '', page: 'new', rid: null, run: null, progress: null, runs: null, docs: {}, speed: null,
  draft: null, busy: false, episode: 0, sig: '', health: null, deferred: false,
  library: null, libQuery: '', libLook: 'all', pick: null };
const $ = (q, root = document) => root.querySelector(q);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const hex = () => Array.from(crypto.getRandomValues(new Uint8Array(16)), b => b.toString(16).padStart(2, '0')).join('');
const PLAY = '<svg viewBox="0 0 12 12" aria-hidden="true"><path d="M3 1.5v9l7.5-4.5z" fill="currentColor"/></svg>';
const PAUSE = '<svg viewBox="0 0 12 12" aria-hidden="true"><path d="M2.5 1.5h2.5v9H2.5zm4.5 0h2.5v9H7z" fill="currentColor"/></svg>';

/* ---------- data ---------- */
function defaults() {
  return { request_key: hex(), idea: '', title: '', episodes: 1, duration: 60, look: 'auto', characters: 'invent', participants: [],
    examples: [], music: null, fps: 25, quality: 'fast', smooth: true, speech_engine: 'auto', lip_sync: 'audio', autopilot: true, cast_check: true };
}
function loadDraft() {
  try { const saved = JSON.parse(localStorage.getItem('cay-draft') || 'null'); if (saved && saved.request_key) return { ...defaults(), ...saved }; } catch (e) { /* private mode */ }
  return defaults();
}
function saveDraft() { try { localStorage.setItem('cay-draft', JSON.stringify(S.draft)); } catch (e) { /* ignore */ } }

async function api(path, { method = 'GET', body, raw } = {}) {
  const headers = {};
  let payload;
  if (method !== 'GET') headers['X-Cay-Token'] = S.token;
  if (raw) payload = raw;
  else if (body !== undefined) { headers['Content-Type'] = 'application/json'; payload = JSON.stringify(body); }
  const response = await fetch(path, { method, headers, body: payload });
  const text = await response.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch (e) { data = null; }
  if (!response.ok) {
    const detail = data && data.detail;
    throw new Error(typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map(x => x.msg).join('; ') : `Anfrage fehlgeschlagen (${response.status}).`);
  }
  return data;
}
const post = (path, body = {}) => api(path, { method: 'POST', body });
const put = (path, body) => api(path, { method: 'PUT', body });

function toast(text) {
  const el = $('#toast'); el.textContent = text; el.classList.add('show');
  clearTimeout(toast.timer); toast.timer = setTimeout(() => el.classList.remove('show'), 4200);
}

/* ---------- vocabulary ---------- */
const STEPS = ['Drehbuch', 'Bilder', 'Ton', 'Animation', 'Fertig'];
const STAGE = { planning: 0, correcting: 1, pictures: 1, cast_review: 1, image_review: 1, voicing: 2, audio_mixing: 2, voice_review: 2, rendering: 3, sample_review: 3, finishing: 3, done: 4 };
const WORKING = new Set(['planning', 'correcting', 'pictures', 'voicing', 'audio_mixing', 'rendering', 'finishing']);
const REVIEW = new Set(['cast_review', 'image_review', 'voice_review', 'sample_review']);
const LOOKS = [['auto', 'Automatisch'], ['film', 'Film'], ['cartoon', 'Cartoon'], ['clay', 'Knete'], ['paper', 'Papier']];
const QUALITY = { draft: 'Entwurf', fast: 'Standard', balanced: 'Ausgewogen (alt)', high: 'Hoch (alt)' };
const PRESETS = [['young_woman', 'Junge Frau'], ['woman', 'Frau'], ['young_man', 'Junger Mann'], ['man', 'Mann'], ['child_girl', 'Mädchen'], ['child_boy', 'Junge'], ['grandma', 'Oma'], ['grandpa', 'Opa'], ['creature', 'Fantasiefigur']];
// Measured on Cay's RTX 4090 (14.10.2026, 0.16.1): 88 min animation for 60 s at Standard = 88 s per film second.
// 0.17 guides only the first of four lip-sync steps (8 -> 5 transformer passes): [Hochrechnung] ~60-70 % of that.
// Entwurf (480x832) is not measured yet: [Hochrechnung] 1.6-1.8x faster per window.
const SECONDS_PER_FILM_SECOND = { fast: [55, 95], draft: [32, 60] };

function status(d) {
  if (d.deleted) return ['stop', 'Im Papierkorb'];
  if (d.state === 'done') return ['done', 'Fertig'];
  if (d.state === 'blocked') return ['stop', 'Angehalten'];
  if (d.paused) return ['', 'Pausiert'];
  if (d.state === 'cast_review' || d.waiting || (REVIEW.has(d.state) && !d.autopilot)) return ['you', 'Wartet auf dich'];
  if (d.queue > 0 && !d.busy) return ['', d.queue === 1 ? 'Als Nächstes dran' : `In der Warteschlange, Platz ${d.queue + 1}`];
  return ['run', 'Läuft'];
}
function duration(seconds) {
  if (seconds == null || !isFinite(seconds)) return '–';
  const m = Math.round(seconds / 60);
  if (seconds < 90) return `${Math.max(1, Math.round(seconds))} s`;
  if (m < 90) return `${m} min`;
  const h = Math.floor(m / 60), rest = m % 60;
  return rest ? `${h} h ${rest} min` : `${h} h`;
}
function estimate(draft) {
  // Prefer what this PC measured for finished films; else the 14.10. measurement.
  const total = draft.duration * draft.episodes, measured = S.speed && S.speed[draft.quality];
  const [low, high] = measured ? [measured.low, measured.high] : SECONDS_PER_FILM_SECOND[draft.quality] || SECONDS_PER_FILM_SECOND.fast;
  const basis = measured ? `gemessen an ${measured.films} fertigen ${measured.films === 1 ? 'Film' : 'Filmen'} in dieser Qualität` : 'Hochrechnung aus deiner Messung vom 14.10. mit der Beschleunigung aus 0.17';
  return `Rechenzeit ungefähr ${low === high ? duration(total * low) : `${duration(total * low)} bis ${duration(total * high)}`}, ${basis}`;
}

/* ---------- shell ---------- */
function route() {
  const hash = decodeURIComponent(location.hash.slice(1));
  if (hash.startsWith('p=')) { S.page = 'project'; if (S.rid !== hash.slice(2)) { S.rid = hash.slice(2); S.run = null; S.progress = null; S.clock = null; S.sig = ''; S.episode = 0; } }
  else S.page = ['projects', 'library'].includes(hash) ? hash : 'new';
}
function render() {
  document.querySelectorAll('[data-nav]').forEach(b => b.setAttribute('aria-current', (b.dataset.nav === S.page || (S.page === 'project' && b.dataset.nav === 'projects')) ? 'page' : 'false'));
  const main = $('#main');
  main.innerHTML = S.page === 'project' ? projectView() : S.page === 'projects' ? projectsView() : S.page === 'library' ? libraryView() : composeView();
  S.deferred = false;
  if (S.page === 'new') updateCompose();
  if (S.page === 'project') paintProgress();
}
async function load() {
  render();
  try {
    if (S.page === 'project') await refreshRun(true);
    else if (S.page === 'projects') await refreshRuns();
    else if (S.page === 'library') { await refreshLibrary(); render(); }
  } catch (e) { toast(e.message); }
}
function busyUI() {
  const active = document.activeElement;
  const typing = active && $('#main').contains(active) && /^(TEXTAREA|INPUT|SELECT)$/.test(active.tagName);
  const playing = [...document.querySelectorAll('#main audio, #main video')].some(m => !m.paused);
  return typing || playing || $('#sheet').open;
}

/* ---------- compose a new film ---------- */
function seg(name, options, value) {
  return `<div class="segmented" role="group" aria-label="${esc(name)}">${options.map(([v, label]) => `<button type="button" data-set="${esc(name)}" data-value="${esc(v)}" aria-pressed="${String(v) === String(value)}">${esc(label)}</button>`).join('')}</div>`;
}
function composeView() {
  const d = S.draft;
  return `<section class="compose">
    <div>
      <h1 class="display">Was soll passieren?</h1>
      <p class="lede">Ein, zwei Sätze reichen. Das Studio schreibt Drehbuch und Dialoge, gestaltet die Figuren, spricht und animiert.</p>
      <label class="sr" for="idea">Deine Idee</label>
      <textarea id="idea" class="idea-input" data-field="idea" placeholder="Zwei Kollegen streiten um den letzten Keks. Am Ende hat ihn die Praktikantin längst gegessen.">${esc(d.idea)}</textarea>
      <div class="idea-line"></div>
      <div class="choices">
        <div class="choice"><span>Länge pro Film</span>${seg('duration', [[15, '15 s'], [30, '30 s'], [60, '60 s'], [90, '90 s']], d.duration)}</div>
        <div class="choice"><span>Folgen</span>${seg('episodes', [[1, 'Einzelfilm'], [3, '3'], [6, '6'], [12, '12']], d.episodes)}
          <p class="hint" id="series-hint"></p></div>
        <div class="choice"><span>Look</span>${seg('look', LOOKS, d.look)}</div>
        <div class="choice"><span>Qualität</span>${seg('quality', [['draft', 'Entwurf'], ['fast', 'Standard']], d.quality)}
          <p class="hint" id="quality-hint"></p></div>
        <div class="choice"><span>Autopilot</span><label class="switch"><input type="checkbox" data-field="autopilot" ${d.autopilot ? 'checked' : ''}><span id="autopilot-text"></span></label></div>
        <div class="choice"><span>Figurencheck</span><label class="switch"><input type="checkbox" data-field="cast_check" ${d.cast_check !== false ? 'checked' : ''}><span>Figuren vorher zeigen</span></label>
          <p class="hint">Ein kurzer Blick auf die Figuren, bevor Szenen und Animation entstehen. Danach läuft alles allein.</p></div>
      </div>
      <details class="more"><summary>Figuren, Look-Vorlagen und Musik</summary>${extrasView()}</details>
      <div class="compose-foot"><p class="muted small" id="estimate"></p><button class="button" data-action="create" id="create">Film starten</button></div>
    </div>
    <aside class="frame preview-frame" id="preview" aria-hidden="true">
      <div class="preview-part" id="preview-part"></div>
      <div class="preview-length"><div><strong id="preview-seconds"></strong><span id="preview-scenes"></span></div></div>
      <div class="preview-caption">Hier stehen später deine Untertitel.</div>
    </aside>
  </section>`;
}
function extrasView() {
  const d = S.draft;
  const thumbs = d.examples.map((id, i) => `<div class="thumb"><img src="/api/factory/assets/${esc(id)}" alt="Vorlage ${i + 1}"><button class="thumb-remove" data-action="remove-example" data-index="${i}" aria-label="Vorlage ${i + 1} entfernen">×</button></div>`).join('');
  const add = d.examples.length < 4 ? `<label class="thumb add"><span>Bild hinzufügen</span><input type="file" accept="image/*" multiple data-upload="example"></label>` : '';
  const people = d.participants.map((p, i) => `<div class="person">
      <label class="thumb small ${p.image ? '' : 'add'}" title="Bild genau dieser Figur">${p.image ? `<img src="/api/factory/assets/${esc(p.image)}" alt="">` : '<span>Bild</span>'}<input type="file" accept="image/*" data-upload="image" data-index="${i}"></label>
      <div class="person-fields">
        <input class="input" aria-label="Name" placeholder="Name" data-person="${i}" data-key="name" value="${esc(p.name)}" maxlength="60">
        <input class="input" aria-label="Aussehen und Art" placeholder="Aussehen, Alter, Art" data-person="${i}" data-key="traits" value="${esc(p.traits)}" maxlength="1500">
        <div class="person-tools">
          ${p.library_label ? `<span class="chip accent" title="Bild und Stimme aus deiner Bibliothek">${esc(p.library_label)}</span>` : ''}
          ${p.voice ? `<span class="voice-note"><button type="button" class="play" data-action="play" data-src="/api/factory/assets/${esc(p.voice)}" aria-label="Stimme von ${esc(p.name || 'Figur')} anhören">${PLAY}</button>${p.library_id && p.voice_from_library ? 'Stimme aus deinen Figuren' : 'Eigene Stimme'}</span>` : ''}
          <label class="file-pill">${p.voice ? 'Andere Aufnahme' : 'Eigene Stimme (optional)'}<input type="file" accept="audio/*" data-upload="voice" data-index="${i}"></label>
          ${p.image && !(p.library_id && p.image_mode === 'exact') ? `<label class="switch compact"><input type="checkbox" data-person-exact="${i}" ${p.image_mode === 'exact' ? 'checked' : ''}><span>Gesichtsausdruck aus dem Bild übernehmen</span></label>` : ''}
        </div>
      </div>
      <button class="icon-remove" data-action="remove-person" data-index="${i}" aria-label="Figur entfernen">×</button></div>`).join('');
  return `<section class="group"><h3 class="group-title">Look-Vorlagen</h3>
      <p class="hint">Bis zu vier Bilder, die zeigen, wie dein Film aussehen soll, zum Beispiel Knete-Optik, Farben oder Licht. Das Studio übernimmt den Stil, nicht die Figuren daraus.</p>
      <div class="thumbs">${thumbs}${add}</div></section>
    <section class="group"><h3 class="group-title">Figuren</h3>
      ${seg('characters', [['invent', 'Studio erfindet'], ['provided', 'Nur meine Figuren'], ['none', 'Ohne Figuren']], d.characters)}
      <p class="hint">Eigene Figuren mit Bild sehen in jeder Szene und Folge gleich aus. Den Gesichtsausdruck bestimmt jede Szene selbst.</p>
      <div class="people">${people}</div>
      <div class="actions"><button class="button quiet small" data-action="lib-pick-compose">Aus deinen Figuren wählen</button><button class="button quiet small" data-action="add-person">Figur hinzufügen</button></div></section>
    <section class="group"><h3 class="group-title">Titel und Musik</h3>
      <label class="field"><span>Titel (optional)</span><input class="input" data-field="title" value="${esc(d.title)}" maxlength="100" placeholder="Wird sonst aus der Idee gebildet"></label>
      <label class="file-pill ${d.music ? 'set' : ''}">${d.music ? 'Eigene Musik gewählt' : 'Eigene Musik hochladen'}<input type="file" accept="audio/*" data-upload="music"></label>
      <p class="hint">Ohne eigene Musik bleibt die Musik aus.</p></section>`;
}
function refreshExtras() {
  const box = $('details.more'); if (!box) return;
  box.innerHTML = '<summary>Figuren, Look-Vorlagen und Musik</summary>' + extrasView(); box.open = true;
}
async function asPng(file) {
  // The studio stores PNG; convert JPG/WebP/AVIF in the browser and keep it within 2048 px.
  if (!file.type.startsWith('image/')) throw new Error('Bitte ein Bild wählen: JPG, PNG oder WebP.');
  let bitmap;
  try { bitmap = await createImageBitmap(file); } catch (e) { throw new Error(`${file.name}: Dieses Bildformat kann der Browser nicht lesen. Bitte JPG, PNG oder WebP wählen.`); }
  const scale = Math.min(1, 2048 / Math.max(bitmap.width, bitmap.height));
  if (file.type === 'image/png' && scale === 1 && file.size < 18e6) return file;
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(bitmap.width * scale); canvas.height = Math.round(bitmap.height * scale);
  canvas.getContext('2d').drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'));
  return new File([blob], file.name.replace(/\.[^.]+$/, '') + '.png', { type: 'image/png' });
}
function updateCompose() {
  const d = S.draft;
  document.querySelectorAll('[data-set]').forEach(b => b.setAttribute('aria-pressed', String(String(d[b.dataset.set]) === b.dataset.value)));
  const scenes = Math.max(3, Math.min(15, Math.ceil(d.duration / 6)));
  $('#preview-seconds').textContent = `${d.duration} s`;
  $('#preview-scenes').textContent = d.episodes > 1 ? `${d.episodes} Folgen mit je ${scenes} Szenen` : `${scenes} Szenen`;
  $('#preview-part').textContent = d.episodes > 1 ? `Teil 1/${d.episodes}` : '';
  $('#preview-part').hidden = d.episodes < 2;
  $('#preview').dataset.look = d.look;
  $('#series-hint').textContent = d.episodes > 1 ? 'Jede Folge endet mit einem offenen Ende, die nächste knüpft daran an.' : '';
  $('#quality-hint').textContent = d.quality === 'draft' ? 'Etwa doppelt so schnell, etwas weniger scharf. Gut zum Ausprobieren.' : 'Die Qualität deines letzten Films.';
  $('#autopilot-text').textContent = d.autopilot ? 'Ohne Zwischenstopps fertigstellen' : 'Bilder, Ton und Probe selbst freigeben';
  $('#estimate').textContent = estimate(d) + '.';
  $('#create').textContent = d.episodes > 1 ? `Serie mit ${d.episodes} Folgen starten` : 'Film starten';
}
async function createFilm() {
  const d = S.draft;
  if (d.idea.trim().length < 12) { toast('Beschreib deine Idee in mindestens einem kurzen Satz.'); $('#idea').focus(); return; }
  const body = { ...d, idea: d.idea.trim(), title: d.title.trim(),
    participants: d.characters === 'none' ? [] : d.participants.filter(p => p.name.trim()).map(p => ({ name: p.name.trim(), traits: p.traits || '', image: p.image || null,
      voice: p.voice || null, voice_text: p.voice_text || '', image_mode: p.image_mode === 'exact' ? 'exact' : 'neutral',
      library_id: p.library_id || null, voice_design: p.voice_from_library && p.voice_design ? p.voice_design : null,
      library_image: p.library_image || null, library_voice: p.voice_from_library ? p.library_voice || p.library_id || null : null,
      image_look: p.library_image ? p.image_look || null : null })) };
  if (d.characters === 'provided' && !body.participants.length) { toast('Für „Nur meine Figuren“ mindestens eine Figur mit Namen eintragen.'); return; }
  const run = await post('/api/factory', body);
  S.draft = defaults(); saveDraft();
  toast(body.episodes > 1 ? 'Serie angelegt. Das Drehbuch entsteht.' : 'Film angelegt. Das Drehbuch entsteht.');
  location.hash = 'p=' + run.id;
}
async function upload(kind, file) {
  if (!file) return null;
  if (kind === 'image') file = await asPng(file);
  const result = await api(`/api/factory/assets?kind=${kind}&name=${encodeURIComponent(file.name)}`, { method: 'POST', raw: file });
  return result.id;
}

/* ---------- projects ---------- */
function frameFor(rid, doc, extra = '') {
  const pic = doc && thumbnail(doc);
  return `<div class="frame">${pic ? `<img src="/api/factory/${esc(rid)}/picture/${esc(pic)}" alt="" loading="lazy">` : `<span class="frame-title">${esc(doc ? doc.title : '')}</span>`}${extra}</div>`;
}
function thumbnail(doc) {
  for (const ep of doc.episodes || []) for (const sc of ep.scenes || []) {
    if (sc.selected) return sc.selected;
    if (sc.active_variants && sc.active_variants[0]) return sc.active_variants[0].id;
  }
  return null;
}
/* Measured compute time: base seconds plus a live count while the project is on the GPU. */
function clockSeconds(c) {
  if (!c) return 0;
  const since = c.since ? Date.parse(c.since) : NaN;
  return (c.seconds || 0) + (isNaN(since) ? 0 : Math.max(0, (Date.now() - since) / 1000));
}
function clockText(seconds) {
  const s = Math.round(seconds), h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), r = s % 60;
  return h ? `${h}:${String(m).padStart(2, '0')}:${String(r).padStart(2, '0')}` : `${m}:${String(r).padStart(2, '0')}`;
}
function clockTag(c, done) {
  if (!c || (!c.seconds && !c.since)) return '';
  const live = c.since ? ` data-clock="${esc(JSON.stringify(c))}"` : '';
  return `<span class="clock${c.since ? ' live' : ''}"${live} title="Gemessene Rechenzeit (ohne Wartezeit auf deine Freigaben)">${done ? 'Rechenzeit ' : '⏱ '}<b>${clockText(clockSeconds(c))}</b></span>`;
}
function tickClocks() {
  document.querySelectorAll('[data-clock]').forEach(el => {
    try { const b = el.querySelector('b'); if (b) b.textContent = clockText(clockSeconds(JSON.parse(el.dataset.clock))); } catch (e) { /* ignore */ }
  });
}
function projectsView() {
  if (!S.runs) return '<p class="muted">Projekte werden geladen …</p>';
  const head = `<div class="page-head"><h1 class="title">Projekte</h1><a class="button" href="#new">Neuer Film</a></div>`;
  if (!S.runs.length) return head + `<div class="empty"><h2 class="headline">Noch kein Projekt.</h2><p class="muted">Beschreib eine Idee, das Studio macht daraus einen Hochkantfilm für TikTok und Shorts.</p><a class="button" href="#new">Ersten Film starten</a></div>`;
  const order = { you: 0, stop: 1, run: 2, '': 3, done: 4 };
  const runs = [...S.runs].sort((a, b) => order[status(a)[0]] - order[status(b)[0]] || String(b.updated).localeCompare(String(a.updated)));
  return head + `<div class="grid">${runs.map(r => {
    const [cls, label] = status(r);
    const doc = S.docs[r.id] && S.docs[r.id].doc;
    const badge = r.episodes > 1 ? `<span class="frame-badge">${r.finished}/${r.episodes} Folgen</span>` : '';
    return `<a class="tile" href="#p=${esc(r.id)}">${frameFor(r.id, doc, badge)}<span class="tile-title">${esc(r.title)}</span><span class="status ${cls}">${esc(label)}</span>${clockTag(r.clock, r.state === 'done')}</a>`;
  }).join('')}</div>`;
}
async function refreshRuns() {
  const list = await api('/api/factory');
  await Promise.all(list.runs.map(async r => {
    const cached = S.docs[r.id];
    if (!cached || cached.updated !== r.updated) {
      try { S.docs[r.id] = { updated: r.updated, doc: await api('/api/factory/' + r.id) }; } catch (e) { /* listed but gone */ }
    }
    const doc = S.docs[r.id] && S.docs[r.id].doc;
    r.autopilot = !!(doc && doc.idea && doc.idea.autopilot);
    r.waiting = !!(doc && doc.autopilot_stopped && doc.autopilot_stopped.state === doc.state);
    r.deleted = false;
  }));
  const changed = JSON.stringify(list.runs) !== JSON.stringify(S.runs);
  S.runs = list.runs;
  if (changed && S.page === 'projects' && !busyUI()) render();
}

/* ---------- one project ---------- */
function stageOf(d) { return d.state === 'blocked' ? STAGE[d.resume_state] ?? 0 : STAGE[d.state] ?? 0; }
function stepsView(d) {
  const now = stageOf(d);
  return `<ol class="steps" aria-label="Ablauf">${STEPS.map((s, i) => `<li class="${i < now || d.state === 'done' ? 'done' : i === now ? 'now' : ''}">${esc(s)}</li>`).join('')}</ol>`;
}
function settingsLine(d) {
  const i = d.idea, parts = [`${i.duration} Sekunden`, i.episodes > 1 ? `${i.episodes} Folgen` : 'Einzelfilm', `Qualität ${QUALITY[i.quality] || i.quality}`];
  return parts.join(', ') + '.';
}
function projectView() {
  const d = S.run;
  if (!d) return '<p class="muted">Projekt wird geladen …</p>';
  return `<div class="project-head">
      <a class="back" href="#projects">Alle Projekte</a>
      <h1 class="title">${esc(d.title)}</h1>
      <p class="muted">${esc(settingsLine(d))} <span id="clock-slot">${clockTag(S.clock, d.state === 'done')}</span></p>
      ${stepsView(d)}
    </div>
    ${nextView(d)}
    ${sectionsView(d)}`;
}
function autopilotSwitch(d) {
  return `<label class="switch"><input type="checkbox" data-action="autopilot" ${d.idea.autopilot ? 'checked' : ''}><span>Autopilot${d.idea.autopilot ? ': ohne Zwischenstopps' : ''}</span></label>`;
}
function nextView(d) {
  const pause = d.paused ? '<button class="button" data-action="resume">Fortsetzen</button>' : '<button class="button quiet" data-action="pause">Pausieren</button>';
  if (d.deleted) return `<section class="next wait"><h2 class="headline">Im Papierkorb.</h2><p>Dateien bleiben erhalten.</p><div class="actions"><button class="button" data-action="restore">Wiederherstellen</button></div></section>`;
  if (d.state === 'blocked') return blockedView(d);
  if (d.state === 'done') return `<section class="next"><h2 class="headline">${d.idea.episodes > 1 ? 'Deine Serie ist fertig.' : 'Dein Film ist fertig.'}</h2>
      <p>Unten ansehen, herunterladen und mit der fertigen Beschreibung hochladen.</p>
      <div class="actions"><button class="button quiet" data-action="reopen-output">Ton noch einmal bearbeiten</button><button class="button quiet" data-action="new-edition">Neue Fassung planen</button></div></section>`;
  if (d.state === 'cast_review') {
    return `<section class="next wait"><h2 class="headline">Prüf deine Figuren.</h2>
      <p>So sieht jede Figur in allen Szenen aus. Passt eine nicht, tippe auf sie: eine aus deinen Figuren nehmen, neu gestalten oder ein eigenes Bild hochladen. Danach entstehen die Szenen${d.idea.autopilot ? ' und der Autopilot macht ohne weitere Stopps fertig' : ''}.</p>
      <div class="actions"><button class="button" data-action="cast-approve">Figuren passen, weiter</button></div></section>`;
  }
  if (d.state === 'image_review') {
    const scenes = d.episodes.flatMap(e => e.scenes), chosen = scenes.filter(s => s.selected).length;
    return `<section class="next wait"><h2 class="headline">Wähle pro Szene ein Bild.</h2>
      <p>${chosen} von ${scenes.length} Szenen gewählt. Mit dem Autopilot nimmt das Studio überall das erste Bild und macht ohne weitere Stopps fertig.</p>
      <div class="actions"><button class="button" data-action="approve-images" ${chosen < scenes.length ? 'disabled' : ''}>Bilder übernehmen</button>${autopilotSwitch(d)}</div></section>`;
  }
  if (d.state === 'voice_review') return `<section class="next wait"><h2 class="headline">Hör dir den Ton an.</h2>
      <p>Jede Zeile wurde einzeln auf hörbare Sprache geprüft. Passt alles, startet die Animation.</p>
      <div class="actions"><button class="button" data-action="approve-voices">Ton freigeben und animieren</button>${autopilotSwitch(d)}</div></section>`;
  if (d.state === 'sample_review') return `<section class="next wait"><h2 class="headline">Prüf die kurze Probe.</h2>
      <p>Mundbewegung, Stimme und Figur. Danach rechnet das Studio den Rest ohne Unterbrechung.</p>
      <div class="sample"><video class="frame" controls playsinline preload="metadata" src="/api/factory/${esc(d.id)}/sample#t=0.1"></video></div>
      <div class="actions"><button class="button" data-action="approve-sample">Passt, weiterrechnen</button><button class="button quiet" data-action="reject-sample">Zurück zum Ton</button></div></section>`;
  if (d.state === 'rendering' || d.state === 'finishing') return `<section class="next"><h2 class="headline">${d.idea.episodes > 1 ? 'Deine Serie entsteht.' : 'Dein Film entsteht.'}</h2>
      <p class="muted">${esc(d.phase || '')}</p><div id="progress-slot"></div>
      <div class="actions">${pause}<button class="link" data-action="abort-step">Aktuellen Abschnitt abbrechen</button></div></section>`;
  return `<section class="next"><h2 class="headline">Das Studio arbeitet.</h2><p class="muted">${esc(d.phase || '')}</p>
      <div class="actions">${pause}${autopilotSwitch(d)}</div></section>`;
}
function blockedView(d) {
  const error = d.error || '', silent = error.includes('DIALOG FEHLT'), speech = error.includes('SPRACHPRÜFUNG');
  const title = silent ? 'Das Drehbuch hat keinen Dialog.' : speech ? 'Einige Sätze sind nicht hörbar.' : d.uncertain ? 'Ein Abschnitt ist nicht mehr auffindbar.' : 'Die Produktion ist angehalten.';
  const text = silent ? 'So entstünde ein stummer Film. Es wurde noch keine Animation gerechnet.'
    : speech ? 'Unten steht, welche Folge, Szene und Figur betroffen ist. Fortsetzen spricht nur diese Sätze neu ein.'
    : d.uncertain ? 'Meist nach einem Neustart. Der Abschnitt wird neu gerechnet, fertige Abschnitte bleiben.'
    : 'Die Ursache steht unten. Fertige Bilder, Stimmen und Abschnitte bleiben gespeichert.';
  const actions = [];
  if (silent && d.resume_state === 'voicing') actions.push('<button class="button" data-action="new-edition">Neue Fassung planen</button>');
  else if (d.uncertain && d.resume_state === 'rendering') actions.push('<button class="button" data-action="abort-fast">Abschnitt neu starten</button>');
  else actions.push(`<button class="button" data-action="resume">${d.resume_state === 'planning' ? 'Neu planen' : 'Fortsetzen'}</button>`);
  if ((d.previews || []).length && ['rendering', 'finishing'].includes(d.resume_state) && !d.uncertain) actions.push('<button class="button quiet" data-action="reopen-voices">Ton bearbeiten</button>');
  actions.push(`<a class="link" href="/api/factory/${esc(d.id)}/diagnostics/download" download>Fehlerbericht speichern</a>`);
  return `<section class="next alert"><h2 class="headline">${title}</h2><p>${text}</p><pre class="error-text">${esc(error)}</pre><div class="actions">${actions.join('')}</div></section>`;
}
function episodeTabs(d) {
  if (d.episodes.length < 2) return '';
  S.episode = Math.min(S.episode, d.episodes.length - 1);
  return `<div class="segmented episode-tabs" role="group" aria-label="Folge">${d.episodes.map((e, i) => `<button data-action="episode" data-index="${i}" aria-pressed="${i === S.episode}">Folge ${i + 1}</button>`).join('')}</div>`;
}
function linesOf(scene) {
  return (scene.dialogues && scene.dialogues.length) ? scene.dialogues : scene.dialogue ? [{ speaker: scene.speaker, text: scene.dialogue, emotion: scene.emotion || 'Natürlich', pause_after: 0.18 }] : [];
}
function sectionsView(d) {
  if (!d.episodes || !d.episodes.length) return '';
  if (d.state === 'done') return filmsSection(d);
  const cast = showsCast(d) ? castPanel(d) : '';
  if (['image_review', 'pictures', 'cast_review'].includes(d.state)) return cast + scenesSection(d, d.state !== 'cast_review');
  if (d.state === 'voice_review') return cast + soundSection(d) + scenesSection(d, false);
  return cast + scenesSection(d, false);
}
/* Casting in a running project: who plays whom, where image and voice come from, and what
   may change right now. One tap on a figure opens everything that is possible for it. */
const CAST_STATES = new Set(['cast_review', 'pictures', 'image_review', 'voicing', 'audio_mixing', 'voice_review']);
function showsCast(d) {
  return !!(d.plan && (d.plan.cast || []).length) && (CAST_STATES.has(d.state) || (d.state === 'blocked' && ['pictures', 'voicing', 'audio_mixing'].includes(d.resume_state)));
}
function participantOf(d, name) { return (d.idea.participants || []).find(x => x.name === name) || {}; }
/* A project document from before 0.18 has no image_mode: its uploads were used exactly as they are. */
function imageMode(e) { return e.image ? (e.image_mode || 'exact') : null; }
function libraryFigure(id) { return id ? (S.library || []).find(f => f.id === id) : null; }
function nameKey(s) { return String(s || '').normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, ''); }
function lookRank(f, look) { return f.look === look ? 2 : (f.look === 'auto' || look === 'auto') ? 1 : 0; }
/* Library figures whose film name is this figure's name, best look first; none once a figure is cast from the library. */
function suggestionsFor(d, name) {
  const e = participantOf(d, name);
  if (e.library_id || e.library_image || e.library_voice) return [];
  return (S.library || []).filter(f => nameKey(f.name) === nameKey(name)).sort((a, b) => lookRank(b, d.idea.look) - lookRank(a, d.idea.look));
}
/* Parts of a library figure this project can take now or later (kept until the next safe point). */
function usableParts(d, f) { const w = d.cast_windows || {}; return ['image', 'voice'].filter(part => f[part] && ['now', 'later'].includes(w[part])); }
function laterText(d) {
  return { pictures: 'sobald das aktuelle Bild fertig ist', voicing: 'sobald die laufenden Stimmen fertig sind', audio_mixing: 'sobald der Ton gemischt ist' }[d.state] || 'in wenigen Sekunden';
}
function scenesWith(d, name) { return d.episodes.flatMap(e => e.scenes).filter(s => (s.cast || []).includes(name)).length; }
function linesOfFigure(d, name) { return d.episodes.flatMap(e => e.scenes).flatMap(s => linesOf(s)).filter(l => l.speaker === name).length; }
function partsText(parts) { return parts.length === 2 ? 'Bild und Stimme' : parts[0] === 'image' ? 'Bild' : 'Stimme'; }
function imageSource(d, p) {
  const e = participantOf(d, p.name), lib = libraryFigure(e.library_image);
  if (e.library_image) return lib ? lib.label : 'Aus deinen Figuren';
  if (e.image) return imageMode(e) === 'exact' ? 'Dein Bild, genau so' : 'Dein Bild, neutral nachgezeichnet';
  return p.original ? 'Original' : 'Vom Studio gestaltet';
}
function voiceSource(d, p) {
  const e = participantOf(d, p.name), lib = libraryFigure(e.library_voice);
  if (e.library_voice) return lib ? lib.label : 'Aus deinen Figuren';
  if (e.voice) return 'Deine Aufnahme';
  return (d.voice_profiles || {})[p.name] ? 'Vom Studio gestaltet' : 'Entsteht mit dem Ton';
}
/* The reference voice itself: a chosen recording first (a designed profile may be outdated after a change). */
function voiceUrl(d, p) {
  const e = participantOf(d, p.name);
  if (e.voice) return `/api/factory/assets/${encodeURIComponent(e.voice)}`;
  return (d.voice_profiles || {})[p.name] ? `/api/factory/${encodeURIComponent(d.id)}/voice-profile/${encodeURIComponent(p.name)}` : '';
}
function castPicture(d, name) {
  const cast = d.plan.cast, i = cast.findIndex(p => p.name === name), refs = d.cast_refs || {};
  // Cache key from the reference itself: an own upload changes the file, not design_round.
  return refs[name] ? `<img src="/api/factory/${esc(d.id)}/cast-image/${i}?v=${encodeURIComponent(String(refs[name]).slice(-48))}-${cast[i].design_round || 0}" alt="" loading="lazy">`
    : `<div class="frame-empty">${['pictures', 'cast_review'].includes(d.state) ? 'entsteht' : ''}</div>`;
}
function pendingFor(d, name) {
  const mine = (d.pending_cast || []).filter(x => x.name === name);
  return mine.length ? { label: mine[0].label || 'deine Figur', parts: mine.map(x => x.part).sort() } : null;
}
function castIntro(d) {
  const w = d.cast_windows || {};
  if (w.image === 'now') return 'Tippe auf eine Figur, um Bild oder Stimme zu tauschen. Ein neues Bild zeichnet nur die Szenen dieser Figur neu.';
  if (w.image === 'later') return 'Die Figuren entstehen gerade. Tippe auf eine, um ihr ein Profil aus deinen Figuren zu geben. Es wird übernommen, sobald das aktuelle Bild fertig ist.';
  if (['now', 'later'].includes(w.voice)) return 'Die Bilder stehen fest. Stimmen lassen sich bis zur Animation tauschen: tippe auf eine Figur.';
  return 'So spielen deine Figuren in diesem Film.';
}
function castPanel(d) {
  const items = d.plan.cast.map(p => {
    const pend = pendingFor(d, p.name), sug = !pend && suggestionsFor(d, p.name)[0], parts = sug ? usableParts(d, sug) : [];
    const url = voiceUrl(d, p);
    const suggestion = sug && parts.length ? `<button class="role-suggest" data-action="lib-suggest" data-name="${esc(p.name)}" data-id="${esc(sug.id)}">
        <span class="mini">${sug.image ? `<img src="/api/factory/assets/${esc(sug.image)}" alt="">` : initials(sug)}</span><span>${parts.length === 2 ? `<b>${esc(sug.label)}</b> verwenden` : `${parts[0] === 'image' ? 'Bild' : 'Stimme'} von <b>${esc(sug.label)}</b>`}</span></button>` : '';
    return `<article class="role">
      <button class="role-hit" data-action="figure-menu" data-name="${esc(p.name)}" aria-label="${esc(p.name)}: Bild und Stimme ändern">
        <span class="figure-pic">${castPicture(d, p.name)}<span class="role-edit" aria-hidden="true">Ändern</span></span>
        <span class="role-name">${esc(p.name)}</span></button>
      <dl class="role-src"><dt>Bild</dt><dd>${esc(imageSource(d, p))}</dd>
        <dt>Stimme</dt><dd>${url ? `<button class="play" data-action="play" data-src="${esc(url)}" aria-label="Stimme von ${esc(p.name)} anhören">${PLAY}</button>` : ''}<span>${esc(voiceSource(d, p))}</span></dd></dl>
      ${pend ? `<p class="role-pending">Vorgemerkt: ${esc(partsText(pend.parts))} von „${esc(pend.label)}“</p>` : ''}${suggestion}</article>`;
  }).join('');
  return `<section class="cast" aria-labelledby="cast-title"><div class="cast-head"><h3 class="label" id="cast-title">Besetzung</h3><p class="muted small">${esc(castIntro(d))}</p></div>
    <div class="cast-row">${items}</div></section>`;
}
function checkLine(d, ep, ei) {
  // Automatic checks in one line: script size, speech share, lip-sync windows.
  const parts = [], st = ep.screenplay_stats, t = (d.timing || [])[ei];
  if (st) parts.push(`${st.words} Wörter`, `${st.shots} Einstellungen`, `${st.actions} stumme Aktionen`);
  if (t) parts.push(`Sprachanteil ${Math.round((t.speech_share || 0) * 100)} %`, `längste Pause ${String(t.longest_speech_gap ?? '–').replace('.', ',')} s`, `${t.talk_windows ?? '–'} Rechenblöcke`);
  const warn = (ep.warnings || []).filter(w => !w.startsWith('Wenig Dialog')).slice(0, 2);
  if (!parts.length && !warn.length) return '';
  return `<p class="muted small check-line">${esc(parts.join(' · '))}</p>${warn.map(w => `<p class="small warn-line">${esc(w)}</p>`).join('')}`;
}
function spineCard(ep) {
  const sp = ep.spine;
  if (!sp) return '';
  return `<div class="spine"><h3 class="label">Ziel des Films</h3><p>${esc(sp.logline)}</p>
    <dl><dt>Haken</dt><dd>${esc(sp.hook)}</dd><dt>Wendung</dt><dd>${esc(sp.twist)}</dd><dt>Pointe</dt><dd>${esc(sp.payoff)}</dd></dl></div>`;
}
function scenesSection(d, choose) {
  const ep = d.episodes[S.episode] || d.episodes[0], ei = d.episodes.indexOf(ep);
  const editable = ['image_review', 'voice_review'].includes(d.state);
  return `<section class="section"><h2 class="title">${d.episodes.length > 1 ? esc(ep.title) : 'Drehbuch'}</h2>${episodeTabs(d)}
    ${checkLine(d, ep, ei)}${spineCard(ep)}
    <div class="scenes ${choose ? '' : 'compact'}">${ep.scenes.map((sc, si) => {
      const variants = sc.active_variants || [];
      const pickable = d.state === 'image_review';
      const pictures = choose && variants.length ? `<div class="variants">${variants.map(v => `<button class="variant" data-action="choose" data-episode="${ei}" data-scene="${si}" data-step="${esc(v.id)}" aria-pressed="${sc.selected === v.id}" aria-label="Bild wählen" ${pickable ? '' : 'disabled'}><div class="frame"><img src="/api/factory/${esc(d.id)}/picture/${esc(v.id)}" alt="" loading="lazy"></div></button>`).join('')}</div>`
        : sc.selected ? `<div class="frame"><img src="/api/factory/${esc(d.id)}/picture/${esc(sc.selected)}" alt="" loading="lazy"></div>`
        : `<div class="frame"><div class="frame-empty">${choose ? 'Bilder entstehen' : ''}</div></div>`;
      const lines = linesOf(sc).map(l => `<p class="line"><b>${esc(l.speaker)}:</b> ${esc(l.text)}</p>`).join('') || '<p class="muted small">Ohne Dialog</p>';
      const tools = editable ? `<div class="actions">${d.state === 'image_review' ? `<button class="button quiet small" data-action="revise" data-episode="${ei}" data-scene="${si}">Neue Bilder</button>` : ''}<button class="button quiet small" data-action="edit-lines" data-episode="${ei}" data-scene="${si}">Text ändern</button></div>` : '';
      return `<article class="scene">${pictures}<div class="scene-text"><h3>${si + 1}. ${esc(sc.title)}</h3><p>${esc(sc.action)}</p>${lines}${tools}</div></article>`;
    }).join('')}</div>
    ${choose && d.state === 'image_review' ? `<div class="dock"><span>${d.episodes.flatMap(e => e.scenes).filter(s => s.selected).length} von ${d.episodes.flatMap(e => e.scenes).length} gewählt</span><button class="button" data-action="approve-images" ${d.episodes.flatMap(e => e.scenes).every(s => s.selected) ? '' : 'disabled'}>Bilder übernehmen</button></div>` : ''}
  </section>`;
}
function soundSection(d) {
  const ei = Math.min(S.episode, d.episodes.length - 1), t = (d.timing || [])[ei] || {};
  const music = (d.mix && d.mix.music_mode) || 'off';
  const cast = (d.plan && d.plan.cast) || [];
  const lines = (d.lines || []).map((l, index) => ({ ...l, index })).filter(l => l.episode === ei);
  return `<section class="section"><h2 class="title">Ton</h2>${episodeTabs(d)}
    <div class="mix"><audio controls preload="metadata" src="/api/factory/${esc(d.id)}/mix/${ei}"></audio>
      <p class="small muted">${t.seconds ? `${t.seconds.toFixed(1)} s, davon ${(t.speech_seconds || 0).toFixed(1)} s Sprache. Längste Pause ${(t.longest_speech_gap || 0).toFixed(1)} s.` : ''}</p>
      <div class="actions"><span class="small muted">Musik</span>${seg('music', [['off', 'Aus'], ['auto', 'Einfach'], ...(d.idea.music ? [['uploaded', 'Eigene']] : [])], music).replaceAll('data-set=', 'data-mix=')}
        <button class="button quiet small" data-action="more-dialogue">Dialoge ergänzen</button><button class="button quiet small" data-action="rebuild-audio">Ton neu erzeugen</button></div></div>
    <h3 class="headline section">Stimmen</h3>
    <div class="voices">${cast.map(p => `<div class="voice"><div class="actions"><button class="play" data-action="play" data-src="/api/factory/${esc(d.id)}/voice-profile/${encodeURIComponent(p.name)}" aria-label="Stimme von ${esc(p.name)} anhören">${PLAY}</button><span class="speaker">${esc(p.name)}</span></div>
        <select class="input" data-voice="${esc(p.name)}" aria-label="Stimmtyp von ${esc(p.name)}">${PRESETS.map(([v, l]) => `<option value="${v}" ${p.voice_preset === v ? 'selected' : ''}>${l}</option>`).join('')}</select>
        <div class="actions"><button class="button quiet small" data-action="new-voice" data-name="${esc(p.name)}">Andere Stimme</button></div></div>`).join('')}</div>
    <h3 class="headline section">Sätze</h3>
    <div class="lines">${lines.map(l => `<div class="line-row"><button class="play" data-action="play" data-src="/api/factory/${esc(d.id)}/audio/${l.index}" aria-label="Satz anhören">${PLAY}</button><span class="speaker">${esc(l.speaker)}</span><span class="line-text">${esc(l.text)}</span><span class="small muted">${(l.duration || 0).toFixed(1)} s</span></div>`).join('') || '<p class="muted small">In dieser Folge spricht niemand.</p>'}</div>
  </section>`;
}
function captionBox(d, ep, ei) {
  const total = d.idea.episodes, s = ep.social;
  const caption = (total > 1 ? `Teil ${ei + 1}/${total}: ` : '') + s.caption;
  const tags = (s.hashtags || []).map(h => '#' + h).join(' ');
  return `<div class="caption-box"><span>${esc(caption)}</span><span class="tags">${esc(tags)}</span><span><button class="link" data-action="copy" data-text="${esc(caption + '\n\n' + tags)}">Beschreibung kopieren</button></span></div>`;
}
function filmsSection(d) {
  return `<section class="section"><h2 class="title">${d.idea.episodes > 1 ? 'Deine Folgen' : 'Dein Film'}</h2><div class="grid">${(d.exports || []).map((x, i) => {
    const ep = d.episodes[x.episode] || {};
    return `<div class="film"><video class="frame" controls playsinline preload="metadata" src="/api/factory/${esc(d.id)}/export/${i}#t=0.1"></video>
      <span class="tile-title">${d.idea.episodes > 1 ? `Folge ${x.episode + 1}: ` : ''}${esc(ep.title || d.title)}</span>
      ${ep.social ? captionBox(d, ep, x.episode) : ''}
      <a class="button quiet small" href="/api/factory/${esc(d.id)}/export/${i}?download=true" download>Herunterladen</a></div>`;
  }).join('')}</div></section>`;
}
async function refreshRun(force) {
  if (!S.rid) return;
  const d = await api('/api/factory/' + S.rid);
  d.autopilot = d.idea && d.idea.autopilot;
  S.clock = await api(`/api/factory/${S.rid}/clock`).catch(() => S.clock);
  const slot = $('#clock-slot'); if (slot) slot.innerHTML = clockTag(S.clock, d.state === 'done');
  const sig = d.revision + JSON.stringify([d.pending_cast || [], d.cast_windows || {}]);
  const changed = sig !== S.sig;
  S.run = d; S.sig = sig;
  if (force || ((changed || S.deferred) && !busyUI())) render(); else if (changed) S.deferred = true;
  if (['rendering', 'finishing'].includes(d.state)) await refreshProgress();
}
async function refreshProgress() {
  try { S.progress = await api(`/api/factory/${S.rid}/progress`); } catch (e) { S.progress = null; }
  paintProgress();
}
function paintProgress() {
  const slot = $('#progress-slot'), p = S.progress, d = S.run;
  if (!slot || !p || !d) return;
  const a = p.active, detail = (a && a.detail) || {}, node = detail.progress;
  const stuck = a && p.last_progress && Date.now() / 1000 - p.last_progress > 600 && d.state === 'rendering';
  const g = p.gpu || {};
  const eta = p.eta ? `${duration(p.eta.low)} bis ${duration(p.eta.high)}` : '–';
  slot.innerHTML = `<div class="facts">
      <div class="fact"><strong>${p.done} von ${p.total}</strong><span>Abschnitte animiert</span></div>
      <div class="fact"><strong>${esc(eta)}</strong><span>${p.eta ? 'Restzeit Animation' : 'Restzeit nach drei fertigen Abschnitten'}</span></div>
      <div class="fact"><strong>${g.utilization == null ? '–' : esc(g.utilization) + ' %'}</strong><span>Grafikkarte ausgelastet</span></div>
    </div>
    <progress class="meter" max="${Math.max(1, p.total)}" value="${p.done}" aria-label="Gesamtfortschritt"></progress>
    ${a ? `<p class="small muted">${esc(detail.label || 'Animation')}${a.scene != null ? `, Folge ${a.episode + 1}, Szene ${a.scene + 1}` : ''}${node ? `: Schritt ${node.value} von ${node.max}` : ''}</p>
      ${node ? `<progress class="meter" max="${node.max}" value="${node.value}" aria-label="Aktueller Abschnitt"></progress>` : ''}` : ''}
    ${stuck ? `<div class="stall"><p><b>Dieser Abschnitt hängt wahrscheinlich.</b> Seit ${esc(duration(Date.now() / 1000 - p.last_progress))} kein neuer Rechenschritt${g.total_mib ? `, Grafikspeicher ${(g.used_mib / 1024).toFixed(1)} von ${(g.total_mib / 1024).toFixed(0)} GB` : ''}.</p>
      <div class="actions"><button class="button small" data-action="abort-fast">Abschnitt neu starten</button></div></div>` : ''}`;
}

/* ---------- figure library ---------- */
/* Cay's casting archive: figures with image and voice, reusable in every film.
   Used in three places with one picker: the library page, a new film, a running project. */
const LOOK_NAMES = { auto: 'Jeder Look', clay: 'Knete', cartoon: 'Cartoon', film: 'Film', paper: 'Papier' };
async function refreshLibrary() {
  const r = await api('/api/library');
  S.library = r.figures || [];
  return S.library;
}
function waveform(peaks) {
  if (!peaks || !peaks.length) return '';
  const bar = 3, gap = 2;
  return `<svg class="wave" viewBox="0 0 ${peaks.length * (bar + gap) - gap} 24" preserveAspectRatio="none" aria-hidden="true">${peaks.map((p, i) => {
    const h = Math.max(2, Math.round(p * 22));
    return `<rect x="${i * (bar + gap)}" y="${(24 - h) / 2}" width="${bar}" height="${h}" rx="1.5"></rect>`;
  }).join('')}</svg>`;
}
function initials(f) { return esc(String(f.label || f.name || '?').split(/\s+/).map(w => w[0]).join('').slice(0, 2).toUpperCase()); }
function portrait(f, withVoice = true) {
  const img = f.image ? `<img src="/api/factory/assets/${esc(f.image)}" alt="" loading="lazy">` : `<span class="portrait-empty" aria-hidden="true">${initials(f)}</span>`;
  const voice = !withVoice ? '' : f.voice
    ? `<div class="voice-strip"><button class="play" data-action="play" data-src="/api/factory/assets/${esc(f.voice)}" aria-label="Stimme von ${esc(f.label)} anhören">${PLAY}</button>${waveform(f.voice_peaks)}</div>`
    : '<div class="voice-strip none"><span>Ohne Stimme</span></div>';
  // The voice strip sits beside the image layer, above the card's click area, so ▶ plays instead of opening.
  return `<div class="portrait-wrap"><div class="portrait">${img}</div>${voice}</div>`;
}
function libraryMatches(f) {
  const q = S.libQuery.trim().toLowerCase();
  return (S.libLook === 'all' || f.look === S.libLook || f.look === 'auto') && (!q || `${f.label} ${f.name} ${f.traits}`.toLowerCase().includes(q));
}
function libraryFilters(id) {
  const looks = [['all', 'Alle'], ['clay', 'Knete'], ['cartoon', 'Cartoon'], ['film', 'Film'], ['paper', 'Papier']];
  return `<div class="filters"><input class="input search" type="search" placeholder="Figur suchen" aria-label="Figur suchen" value="${esc(S.libQuery)}" data-libq="${id}">
    <div class="segmented" role="group" aria-label="Look">${looks.map(([v, l]) => `<button type="button" data-liblook="${v}" data-target="${id}" aria-pressed="${S.libLook === v}">${l}</button>`).join('')}</div></div>`;
}
function libraryCards() {
  const list = (S.library || []).filter(libraryMatches);
  if (!list.length) return `<p class="muted cards-empty">Keine Figur passt zu dieser Suche.</p>`;
  return list.map(f => `<article class="card">
      ${portrait(f)}
      <h3 class="card-title"><button class="card-open" data-action="lib-edit" data-id="${esc(f.id)}">${esc(f.label)}</button></h3>
      <p class="card-meta"><span class="chip">${esc(LOOK_NAMES[f.look] || 'Jeder Look')}</span><span class="small muted">${f.name !== f.label ? `heißt im Film ${esc(f.name)}` : ''}${f.uses ? `${f.name !== f.label ? ', ' : ''}in ${f.uses} ${f.uses === 1 ? 'Film' : 'Filmen'}` : ''}</span></p>
    </article>`).join('');
}
function libraryView() {
  const head = `<div class="page-head"><div class="page-intro"><h1 class="title">Deine Figuren</h1><p class="muted">Bild und Stimme einmal festlegen und in jedem Film wiederverwenden.</p></div><button class="button" data-action="lib-new">Neue Figur</button></div>`;
  if (!S.library) return head + '<p class="muted">Figuren werden geladen …</p>';
  if (!S.library.length) return head + `<div class="empty"><h2 class="headline">Noch keine Figuren.</h2>
      <p class="muted">Nimm eine Figur aus einem Projekt auf: bei der Figurenprüfung unter „In deine Figuren aufnehmen“. Oder lege hier eine mit Bild und Stimme an.</p>
      <button class="button" data-action="lib-new">Figur anlegen</button></div>`;
  return head + libraryFilters('lib-cards') + `<div class="cards" id="lib-cards">${libraryCards()}</div>`;
}
function looksRadio(value) {
  return `<div class="segmented" role="radiogroup" aria-label="Look">${Object.entries(LOOK_NAMES).map(([v, l]) => `<label><input type="radio" name="look" value="${v}" ${v === value ? 'checked' : ''}><span>${l}</span></label>`).join('')}</div>`;
}
function libraryEditor(f) {
  const x = f || { name: '', label: '', look: (S.draft && S.draft.look !== 'auto' && S.draft.look) || 'auto', traits: '', image: null, image_mode: 'neutral', voice: null, voice_text: '' };
  const source = f && f.source && f.source.title ? `<p class="small muted">Aufgenommen aus „${esc(f.source.title)}“.</p>` : '';
  openSheet(`<div class="sheet-head"><h2 class="headline">${f ? esc(f.label) : 'Neue Figur'}</h2><button class="button quiet small" data-action="close">Abbrechen</button></div>
    <form id="lib-form" class="lib-form" data-id="${f ? esc(f.id) : ''}">
      <div class="lib-top">
        <label class="lib-photo ${x.image ? '' : 'add'}" aria-label="Bild der Figur wählen">${x.image ? `<img src="/api/factory/assets/${esc(x.image)}" alt="">` : '<span>Bild wählen</span>'}<input type="file" accept="image/*" data-upload="lib-image"></label>
        <div class="lib-fields">
          <label class="field"><span>Profilname</span><input class="input" name="label" required maxlength="80" value="${esc(x.label)}" placeholder="Patrick Knete"></label>
          <label class="field"><span>Name im Film</span><input class="input" name="name" required maxlength="60" value="${esc(x.name)}" placeholder="Patrick"></label>
        </div>
      </div>
      <div class="field"><span>Look</span>${looksRadio(x.look)}</div>
      <input type="hidden" name="image" value="${esc(x.image || '')}">
      <label class="switch"><input type="checkbox" name="exact" ${x.image_mode === 'exact' ? 'checked' : ''}><span>Gesichtsausdruck aus dem Bild übernehmen</span></label>
      <p class="small muted lib-note">Ausgeschaltet zeichnet das Studio die Figur einmal mit neutralem Gesicht, und jede Szene bestimmt den Ausdruck. Eingeschaltet wird das Bild genau so verwendet, richtig für fertige Figurenblätter.</p>
      <label class="field"><span>Aussehen und Art</span><textarea class="textarea" name="traits" maxlength="1500" placeholder="Rosa Seestern, grüne Shorts, verträumt">${esc(x.traits)}</textarea></label>
      <div class="field"><span>Stimme</span>
        <div class="lib-voice" id="lib-voice">${x.voice ? `<button type="button" class="play" data-action="play" data-src="/api/factory/assets/${esc(x.voice)}" aria-label="Stimme anhören">${PLAY}</button>${waveform(x.voice_peaks)}` : '<span class="muted small">Noch keine Stimme. Ohne Stimme gestaltet das Studio eine passende.</span>'}</div>
        <input type="hidden" name="voice" value="${esc(x.voice || '')}">
        <div class="actions"><label class="file-pill">${x.voice ? 'Andere Aufnahme wählen' : 'Aufnahme wählen'}<input type="file" accept="audio/*" data-upload="lib-voice"></label>${x.voice ? '<button type="button" class="button quiet small" data-action="lib-voice-clear">Stimme entfernen</button>' : ''}</div>
      </div>
      <label class="field"><span>Was wird in der Aufnahme gesagt? (optional, macht die Stimme genauer)</span><input class="input" name="voice_text" maxlength="2500" value="${esc(x.voice_text || '')}"></label>
      ${source}
      <div class="sheet-foot">${f ? `<button type="button" class="button danger" data-action="lib-delete" data-id="${esc(f.id)}">Aus deinen Figuren entfernen</button>` : '<span></span>'}<button class="button" type="submit">${f ? 'Änderungen sichern' : 'Figur sichern'}</button></div>
    </form>`);
}
function readLibraryForm(form) {
  const v = name => (form.elements[name] && form.elements[name].value || '').trim();
  const fig = (S.library || []).find(f => f.id === form.dataset.id) || {};
  return { name: v('name'), label: v('label'), look: (form.querySelector('input[name="look"]:checked') || {}).value || 'auto', traits: v('traits'),
    image: v('image') || null, image_mode: form.elements.exact.checked ? 'exact' : 'neutral', voice: v('voice') || null, voice_text: v('voice_text'),
    voice_design: v('voice') && v('voice') === fig.voice ? fig.voice_design || null : null, voice_preset: fig.voice_preset || '', original: fig.original || '' };
}
/* Picker: one sheet for a new film (several figures) and for one figure of a running project. */
function pickerSheet() {
  const p = S.pick, d = S.run, list = (S.library || []);
  const title = p.mode === 'project' ? `Figur für ${esc(p.name)}` : 'Aus deinen Figuren wählen';
  const intro = p.mode === 'project' ? `Bild und Stimme kommen aus deiner Bibliothek. Im Drehbuch heißt die Figur weiter ${esc(p.name)}.` : 'Gewählte Figuren spielen mit ihrem Bild und ihrer Stimme in deinem Film mit.';
  if (!list.length) {
    openSheet(`<div class="sheet-head"><h2 class="headline">${title}</h2><button class="button quiet small" data-action="close">Schließen</button></div>
      <div class="empty compact"><h3 class="headline">Noch keine Figuren.</h3><p class="muted">Nimm Figuren aus einem Projekt auf oder lege sie im Bereich „Figuren“ an.</p><a class="button quiet" href="#library" data-action="close">Zu deinen Figuren</a></div>`);
    return;
  }
  openSheet(`<div class="sheet-head"><h2 class="headline">${title}</h2><button class="button quiet small" data-action="close">Abbrechen</button></div>
    <p class="muted">${intro}</p>${libraryFilters('pick-grid')}
    <div class="pick-grid" id="pick-grid">${pickItems()}</div>
    <div class="sheet-foot pick-foot" id="pick-foot">${pickFoot()}</div>`);
}
function pickItems() {
  const p = S.pick, d = S.run;
  const look = p.mode === 'project' ? d.idea.look : S.draft.look;
  const fits = f => p.mode === 'project' && nameKey(f.name) === nameKey(p.name);
  // A figure with the same film name comes first: "Patrick" in the film, "Patrick Knete" in the library.
  const list = (S.library || []).filter(libraryMatches).sort((a, b) => (fits(b) - fits(a)) || (lookRank(b, look) - lookRank(a, look)));
  return list.map(f => {
    const chosen = p.mode === 'project' ? p.selected === f.id : p.selected.has(f.id);
    const other = look && look !== 'auto' && f.look !== 'auto' && f.look !== look;
    return `<div class="pick-item"><button type="button" class="pick" data-action="lib-choose" data-id="${esc(f.id)}" aria-pressed="${chosen}">
        ${portrait(f, false)}<span class="pick-title">${esc(f.label)}</span><span class="small muted">${fits(f) ? `Passt zu ${esc(p.name)}. ` : ''}${esc(LOOK_NAMES[f.look] || '')}${other && f.image ? `, wird im Look ${p.mode === 'project' ? 'dieses' : 'deines'} Films nachgezeichnet` : ''}</span></button>
        ${f.voice ? `<button type="button" class="play pick-play" data-action="play" data-src="/api/factory/assets/${esc(f.voice)}" aria-label="Stimme von ${esc(f.label)} anhören">${PLAY}</button>` : ''}</div>`;
  }).join('') || '<p class="muted">Keine Figur passt zu dieser Suche.</p>';
}
function pickFoot() {
  const p = S.pick;
  if (p.mode === 'compose') {
    const n = p.selected.size;
    return `<span class="small muted">${n ? `${n} gewählt` : 'Tippe auf Figuren, um sie zu wählen.'}</span><button class="button" data-action="lib-add-compose" ${n ? '' : 'disabled'}>${n === 1 ? 'Figur übernehmen' : `${n || ''} Figuren übernehmen`.trim()}</button>`;
  }
  const d = S.run, f = (S.library || []).find(x => x.id === p.selected), w = d.cast_windows || {};
  if (!f) return '<span class="small muted">Wähle eine Figur.</span><button class="button" disabled>Übernehmen</button>';
  const scenes = scenesWith(d, p.name), lines = linesOfFigure(d, p.name);
  const option = (part, title, has, effect) => {
    const win = w[part], ok = has && ['now', 'later'].includes(win);
    const why = !has ? `Diese Figur hat ${part === 'image' ? 'kein Bild' : 'keine Stimme'}.` : !ok ? win || '' : win === 'later' ? `Wird vorgemerkt und übernommen, ${laterText(d)}. ${effect}` : effect;
    return `<label class="check"><input type="checkbox" id="pick-${part}" ${ok ? 'checked' : 'disabled'}><span><b>${title}</b><span class="small muted">${esc(why)}</span></span></label>`;
  };
  const later = ['image', 'voice'].some(part => f[part] && w[part] === 'later');
  const ok = ['image', 'voice'].some(part => f[part] && ['now', 'later'].includes(w[part]));
  return `<div class="pick-options">
      ${option('image', 'Bild übernehmen', !!f.image, `${scenes} ${scenes === 1 ? 'Szene wird' : 'Szenen werden'} neu gezeichnet.`)}
      ${option('voice', 'Stimme übernehmen', !!f.voice, `${lines} ${lines === 1 ? 'Satz wird' : 'Sätze werden'} neu eingesprochen.`)}
    </div><button class="button" data-action="lib-apply" ${ok ? '' : 'disabled'}>Für ${esc(p.name)} ${later ? 'vormerken' : 'übernehmen'}</button>`;
}
function figureSheet(name) {
  const d = S.run, p = d.plan.cast.find(x => x.name === name), e = participantOf(d, name), w = d.cast_windows || {};
  const refs = d.cast_refs || {}, scenes = scenesWith(d, name), pend = pendingFor(d, name), url = voiceUrl(d, p);
  const usable = ['image', 'voice'].filter(part => ['now', 'later'].includes(w[part]));
  const row = (attrs, title, text, disabled) => `<button class="menu-row" ${attrs} ${disabled ? 'disabled' : ''}><b>${title}</b><span>${text}</span></button>`;
  const library = usable.length ? `<div class="menu-section"><p class="menu-title">Aus deinen Figuren</p>
      ${suggestionsFor(d, name).slice(0, 3).filter(f => usableParts(d, f).length).map(f => `<button class="menu-row with-pic" data-action="lib-suggest" data-name="${esc(name)}" data-id="${esc(f.id)}">
        <span class="mini">${f.image ? `<img src="/api/factory/assets/${esc(f.image)}" alt="">` : initials(f)}</span><b>${esc(f.label)} verwenden</b>
        <span>${esc(partsText(usableParts(d, f)))}${usableParts(d, f).some(part => w[part] === 'later') ? `, wird übernommen, ${esc(laterText(d))}` : ''}.</span></button>`).join('')}
      ${row(`data-action="lib-pick-project" data-name="${esc(name)}"`, 'Aus deinen Figuren wählen', `Bild und Stimme aus deiner Bibliothek. Im Drehbuch heißt die Figur weiter ${esc(name)}.`)}</div>` : '';
  const ownImage = e.image && !e.library_image;
  const image = w.image === 'now' ? `<div class="menu-section"><p class="menu-title">Bild</p>
      ${imageMode(e) !== 'exact' ? row(`data-action="cast-redo" data-name="${esc(name)}"`, 'Neu gestalten', `Das Studio zeichnet ${esc(name)} noch einmal.`) : ''}
      <label class="menu-row"><b>Eigenes Bild hochladen</b><span>Mit neutralem Gesicht übernommen, jede Szene bestimmt den Ausdruck.</span><input type="file" accept="image/*" data-upload="cast" data-name="${esc(name)}"></label>
      ${e.image ? (imageMode(e) === 'exact'
        ? row(`data-action="cast-mode" data-name="${esc(name)}" data-mode="neutral"`, 'Gesicht neutral nachzeichnen', `${ownImage ? 'Dein Bild' : 'Das Bild'} wird einmal mit neutralem Gesicht gezeichnet, damit ${esc(name)} in jeder Szene passend schaut.`)
        : row(`data-action="cast-mode" data-name="${esc(name)}" data-mode="exact"`, 'Bild genau so verwenden', 'Richtig für fertige Figurenblätter. Der Gesichtsausdruck aus dem Bild bleibt dann in allen Szenen.')) : ''}</div>`
    : `<div class="menu-section"><p class="menu-title">Bild</p><p class="menu-note">${esc(w.image === 'later' ? `Figuren aus deiner Bibliothek kannst du schon jetzt vormerken. Zum Neu-Gestalten oder für ein eigenes Bild das Projekt kurz pausieren.` : w.image || '')}</p></div>`;
  const voice = w.voice === 'now' ? `<div class="menu-section"><p class="menu-title">Stimme</p>
      ${row(`data-action="figure-voice-new" data-name="${esc(name)}"`, 'Andere Stimme gestalten', `Das Studio gestaltet eine neue Stimme für ${esc(name)}. Die Sätze werden neu eingesprochen.`)}
      <label class="menu-row"><b>Eigene Aufnahme hochladen</b><span>Eine Sprachaufnahme dieser Figur, 5 bis 20 Sekunden.</span><input type="file" accept="audio/*" data-upload="cast-voice" data-name="${esc(name)}"></label></div>`
    : `<div class="menu-section"><p class="menu-title">Stimme</p><p class="menu-note">${esc(w.voice === 'later' ? `Eigene Aufnahmen und neue Stimmen gehen, ${laterText(d)}. Figuren aus deiner Bibliothek kannst du schon jetzt vormerken.` : w.voice || '')}</p></div>`;
  const keep = refs[name] || e.voice || (d.voice_profiles || {})[name]
    ? `<div class="menu-section">${row(`data-action="lib-save" data-name="${esc(name)}"`, 'In deine Figuren aufnehmen', 'Bild und Stimme für andere Filme sichern. An diesem Film ändert sich nichts.')}</div>` : '';
  openSheet(`<div class="sheet-head"><h2 class="headline">${esc(name)}</h2><button class="button quiet small" data-action="close">Fertig</button></div>
    ${pend ? `<div class="notice"><span>Vorgemerkt: ${esc(partsText(pend.parts))} von „${esc(pend.label)}“. Wird übernommen, ${esc(laterText(d))}.</span><button class="button quiet small" data-action="cast-cancel" data-name="${esc(name)}">Vormerkung aufheben</button></div>` : ''}
    <div class="figure-sheet"><div class="figure-side"><div class="figure-pic">${castPicture(d, name)}</div>
        <dl class="role-src"><dt>Bild</dt><dd>${esc(imageSource(d, p))}</dd><dt>Stimme</dt><dd>${url ? `<button class="play" data-action="play" data-src="${esc(url)}" aria-label="Stimme von ${esc(name)} anhören">${PLAY}</button>` : ''}<span>${esc(voiceSource(d, p))}</span></dd></dl>
        <p class="small muted">In ${scenes} ${scenes === 1 ? 'Szene' : 'Szenen'} zu sehen.</p></div>
      <div class="menu">${library}${image}${voice}${keep}</div></div>`);
}
function saveToLibrarySheet(name) {
  const d = S.run, look = LOOK_NAMES[d.idea.look];
  openSheet(`<div class="sheet-head"><h2 class="headline">${esc(name)} aufnehmen</h2><button class="button quiet small" data-action="close">Abbrechen</button></div>
    <p class="muted">Bild und Stimme aus diesem Projekt kommen in deine Figuren und lassen sich in jedem Film wiederverwenden.</p>
    <form id="lib-save-form" data-name="${esc(name)}"><label class="field"><span>Profilname</span><input class="input" name="label" required maxlength="80" value="${esc(look && d.idea.look !== 'auto' ? `${name} ${look}` : name)}"></label>
      <div class="sheet-foot"><span></span><button class="button" type="submit">In deine Figuren aufnehmen</button></div></form>`);
}

/* ---------- sheets ---------- */
function openSheet(html) { const sheet = $('#sheet'); sheet.innerHTML = `<div class="sheet-body">${html}</div>`; if (!sheet.open) sheet.showModal(); }
function closeSheet() { const sheet = $('#sheet'); if (sheet.open) sheet.close(); }
async function settingsSheet() {
  openSheet(`<div class="sheet-head"><h2 class="headline">Einrichtung</h2><button class="button quiet small" data-action="close">Fertig</button></div><p class="muted">Bereitschaft wird geprüft …</p>`);
  const [check, voices, animation, boost, notify] = await Promise.all([api('/api/factory/check').catch(e => ({ error: e.message })),
    api('/api/factory/voice-studio/status').catch(() => null), api('/api/factory/render-studio/status').catch(() => null), api('/api/factory/turbo').catch(() => null),
    api('/api/notify').catch(() => null)]);
  const rows = (check.checks || []).map(c => `<div class="check-row"><span class="dot ${c.ready ? '' : 'bad'}"></span><div><b>${esc(c.name)}</b><div class="small muted">${esc(c.detail)}</div></div></div>`).join('');
  const anim = (animation && animation.checks || []).map(c => `<div class="check-row"><span class="dot ${c.ready ? '' : 'bad'}"></span><div><b>${esc(c.name)}</b><div class="small muted">${esc(c.detail)}</div></div></div>`).join('');
  openSheet(`<div class="sheet-head"><h2 class="headline">Einrichtung</h2><button class="button quiet small" data-action="close">Fertig</button></div>
    <div>${rows || `<p class="muted">${esc(check.error || 'Keine Angaben.')}</p>`}</div>
    <h3 class="headline">Stimmen</h3><p class="small muted">${esc(voices ? voices.message : 'Status nicht lesbar.')}${voices && voices.dialogue_ready ? ' Qwen-Dialogmodell bereit.' : ''}</p>
    ${voices && voices.state !== 'ready' ? '<div class="actions"><button class="button quiet small" data-action="setup-voices">Stimmen einrichten</button></div>' : ''}
    ${voices && voices.state === 'ready' && !voices.dialogue_ready ? '<div class="actions"><button class="button quiet small" data-action="upgrade-voices">Dialogmodell ergänzen</button></div>' : ''}
    <h3 class="headline">Turbo</h3>
    <p class="small muted">Schnellere Rechenart der Grafikkarte für Sprechszenen, kostenlos. Erwartet etwa 1,5- bis 2-fach schneller, auf deinem PC noch nicht gemessen. Schlägt ein Abschnitt fehl, schaltet sich Turbo selbst ab.</p>
    <p class="small">${esc(boost ? boost.message : 'Status nicht lesbar.')}${boost && boost.error ? ' ' + esc(boost.error) : ''}</p>
    <div class="actions">${boost && ['missing', 'off'].includes(boost.state) ? '<button class="button quiet small" data-action="turbo-setup">Turbo einrichten</button>' : ''}${boost && ['active', 'restart'].includes(boost.state) ? '<button class="button quiet small" data-action="turbo-off">Turbo ausschalten</button>' : ''}</div>
    <h3 class="headline">Animation</h3><div>${anim}</div>
    ${animation && animation.message ? `<p class="small muted">${esc(animation.message)}</p>` : ''}
    ${animation && animation.checks && animation.checks.some(c => !c.ready) ? '<div class="actions"><button class="button quiet small" data-action="setup-animation">Fehlende Animationsteile einrichten</button></div>' : ''}
    <h3 class="headline">Benachrichtigungen</h3>
    <p class="small muted">${esc(notify ? notifySummary(notify) : 'Status nicht lesbar.')}</p>
    <div class="actions"><button class="button quiet small" data-action="notify">${notify && notifyChannels(notify).length ? 'Ändern' : 'Einrichten'}</button></div>
    <h3 class="headline">Weitere Werkzeuge</h3>
    <p><a href="/classic#remix">Figurentausch</a> öffnet sich in der bisherigen Ansicht. <a href="/classic">Bisherige Oberfläche</a></p>
    <p class="small muted">Cay Studio ${esc(S.version)}. Alles läuft lokal, ohne Abo und ohne kostenpflichtige Dienste.</p>`);
}
/* ---------- notifications (0.18): opt-in, every channel says what leaves the PC ---------- */
/* "Am PC": this browser shows the server's event feed while a studio tab is open. Nothing leaves the PC.
   The server decides what counts (autopilot rules, dedupe); this tab only remembers what it has shown. */
const NOTE = { seq: null, busy: false, error: null, token: '', consent: { telegram: false, ntfy: false } };
function pcNotify() {
  if (!('Notification' in window)) return 'unsupported';
  if (Notification.permission === 'denied') return 'denied';
  let on = false;
  try { on = localStorage.getItem('cay-notify-pc') === 'on'; } catch (e) { /* private mode: off */ }
  return on && Notification.permission === 'granted' ? 'on' : 'off';
}
function setPcNotify(on) { try { localStorage.setItem('cay-notify-pc', on ? 'on' : 'off'); } catch (e) { /* ignore */ } }
function shownBefore(key) {
  try {
    const seen = JSON.parse(localStorage.getItem('cay-notify-seen') || '[]');
    if (seen.includes(key)) return true;
    seen.push(key); localStorage.setItem('cay-notify-seen', JSON.stringify(seen.slice(-200)));
  } catch (e) { /* without storage the tag still keeps one message per event */ }
  return false;
}
function showPc(title, body, tag, rid) {
  try {
    const note = new Notification(title, { body, tag, lang: 'de' });
    note.onclick = () => { window.focus(); if (rid) location.hash = 'p=' + rid; note.close(); };
    return true;
  } catch (e) { return false; }
}
async function notifyPoll() {
  if (pcNotify() !== 'on') { NOTE.seq = null; return; }
  if (NOTE.busy) return;
  NOTE.busy = true;
  try {
    const feed = await api('/api/notify/feed' + (NOTE.seq === null ? '' : '?after=' + NOTE.seq));
    if (NOTE.seq !== null) for (const e of feed.events) if (!shownBefore(e.key)) showPc(e.title, e.body, e.key, e.run_id);
    NOTE.seq = feed.latest;
  } catch (e) { /* next tick */ } finally { NOTE.busy = false; }
}
function notifyChannels(n) {
  return [n.telegram.state === 'connected' && 'Telegram', n.ntfy.state === 'on' && 'ntfy', pcNotify() === 'on' && 'Am PC'].filter(Boolean);
}
function notifySummary(n) {
  const on = notifyChannels(n);
  if (!on.length) return 'Aus. Auf Wunsch sagt dir das Studio Bescheid, wenn ein Film fertig ist oder du gebraucht wirst.';
  const failed = ['telegram', 'ntfy'].filter(c => n[c].last && !n[c].last.ok).map(c => (c === 'telegram' ? 'Telegram' : 'ntfy'));
  return `An: ${on.join(', ')}.` + (failed.length ? ` Letzte Nachricht über ${failed.join(' und ')} fehlgeschlagen.` : '');
}
function when(iso) {
  const t = new Date(iso);
  return isNaN(t) ? '' : t.toLocaleString('de-DE', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
}
function notifyLast(c) {
  if (c.pending) return `<p class="small notify-last wait">${c.pending === 1 ? 'Eine Nachricht wartet' : `${c.pending} Nachrichten warten`} auf einen neuen Versuch.${c.last && !c.last.ok ? ' ' + esc(c.last.text) : ''}</p>`;
  if (!c.last) return '';
  return `<p class="small notify-last ${c.last.ok ? 'ok' : 'bad'}">${c.last.ok ? 'Zuletzt' : 'Fehlgeschlagen'} am ${esc(when(c.last.at))}: ${esc(c.last.text)}</p>`;
}
function notifySwitch(key, label, checked, hint) {
  return `<div class="notify-option"><label class="switch"><input type="checkbox" data-notify="${key}" ${checked ? 'checked' : ''}><span>${esc(label)}</span></label>${hint ? `<p class="small muted">${esc(hint)}</p>` : ''}</div>`;
}
function notifyError(channel) {
  return NOTE.error && NOTE.error.channel === channel ? `<p class="notify-error" role="alert" tabindex="-1">${esc(NOTE.error.text)}</p>` : '';
}
function chip(on, text) { return `<span class="chip${on ? ' on' : ''}">${esc(text)}</span>`; }
function pcBlock() {
  const pc = pcNotify();
  const body = pc === 'unsupported' ? '<p class="small">Dieser Browser kann keine Meldungen anzeigen. Nimm Telegram oder ntfy.</p>'
    : pc === 'denied' ? '<p class="small">Im Browser blockiert. Erlaube Benachrichtigungen für das Studio in den Website-Einstellungen (Symbol links neben der Adresse) und lade die Seite neu.</p>'
    : pc === 'on' ? '<div class="actions"><button class="button quiet small" data-action="pc-test">Probe anzeigen</button><button class="button danger small" data-action="pc-off">Ausschalten</button></div>'
    : '<div class="actions"><button class="button small" data-action="pc-on">Am PC einschalten</button></div>';
  return `<section class="notify-channel" aria-labelledby="nc-pc"><div class="notify-top"><h3 class="group-title" id="nc-pc">Am PC</h3>${chip(pc === 'on', pc === 'on' ? 'An' : 'Aus')}</div>
    <p class="small muted">Eine Meldung am Bildschirm, solange ein Studio-Fenster offen ist. Dabei verlassen keine Daten den PC.</p>${body}${notifyError('pc')}</section>`;
}
function telegramBlock(t) {
  let body;
  if (t.state === 'off') {
    body = `<div class="notify-disclosure"><b>Was an Telegram geht</b><ul>
        <li>Projekttitel, Status und eine kurze Fehlermeldung, auf Wunsch ein Vorschaubild und der fertige Film.</li>
        <li>Telegram speichert die Nachrichten auf seinen Servern. Sie sind nicht Ende-zu-Ende verschlüsselt.</li>
        <li>Der Bot-Schlüssel bleibt auf deinem PC. Wer ihn hat, kann deinen Bot steuern. @BotFather stellt dir jederzeit einen neuen aus.</li></ul></div>
      <ol class="notify-steps"><li>In Telegram <b>@BotFather</b> öffnen, <b>/newbot</b> senden und einen Namen wählen. Er schickt dir einen Schlüssel.</li>
        <li><label class="field"><span>Schlüssel hier einfügen</span><input class="input notify-token" id="tg-token" value="${esc(NOTE.token)}" autocomplete="off" spellcheck="false" placeholder="123456789:AA…"></label></li></ol>
      <label class="check"><input type="checkbox" id="tg-consent" ${NOTE.consent.telegram ? 'checked' : ''}><span>Einverstanden: Diese Angaben dürfen an Telegram gehen.</span></label>
      <div class="actions"><button class="button small" data-action="tg-token">Bot prüfen</button></div>`;
  } else if (t.state === 'token') {
    body = `<p>Bot gefunden: <b>${esc(t.bot.name)}</b> (@${esc(t.bot.username)})</p>
      <ol class="notify-steps" start="3"><li>Öffne <a href="${esc(t.bot.link)}" target="_blank" rel="noopener noreferrer">${esc(t.bot.link.replace('https://', ''))}</a> oder suche in Telegram nach <b>@${esc(t.bot.username)}</b> und tippe auf <b>Start</b>.</li>
        <li>Dann hier auf „Verbindung prüfen“.</li></ol>
      <div class="actions"><button class="button small" data-action="tg-connect">Verbindung prüfen</button><button class="button danger small" data-action="notify-off" data-channel="telegram">Abbrechen</button></div>`;
  } else {
    body = `<p>Verbunden mit <b>${esc(t.chat.name)}</b> über <b>@${esc(t.bot.username)}</b>.</p>
      ${notifySwitch('telegram_preview', 'Vorschaubild mitsenden', t.preview)}
      ${notifySwitch('telegram_film', 'Fertigen Film mitsenden', t.film, 'Nur bis 49\u00a0MB, das schafft Telegram. Ein Film von 60\u00a0Sekunden hat etwa 20\u00a0MB.')}
      ${notifyLast(t)}
      <div class="actions"><button class="button quiet small" data-action="notify-test" data-channel="telegram">Testnachricht senden</button><button class="button danger small" data-action="notify-off" data-channel="telegram">Trennen</button></div>`;
  }
  const label = t.state === 'connected' ? 'Verbunden' : t.state === 'token' ? 'Noch nicht fertig' : 'Aus';
  return `<section class="notify-channel" aria-labelledby="nc-tg"><div class="notify-top"><h3 class="group-title" id="nc-tg">Telegram</h3>${chip(t.state === 'connected', label)}</div>
    <p class="small muted">Aufs Handy, mit Vorschaubild. Kostenlos, ohne Abo. Empfohlen.</p>${body}${notifyError('telegram')}</section>`;
}
function ntfyBlock(n) {
  let body;
  if (n.state === 'off') {
    body = `<div class="notify-disclosure"><b>Was an ntfy.sh geht</b><ul>
        <li>Projekttitel, Status und eine kurze Fehlermeldung, auf Wunsch ein Vorschaubild.</li>
        <li>Wer den Namen deines Themas kennt, kann mitlesen. Das Studio wählt einen langen Zufallsnamen. Gib ihn nicht weiter.</li>
        <li>Nicht Ende-zu-Ende verschlüsselt. Kostenlos bis 250 Nachrichten am Tag.</li></ul></div>
      <label class="check"><input type="checkbox" id="ntfy-consent" ${NOTE.consent.ntfy ? 'checked' : ''}><span>Einverstanden: Diese Angaben dürfen an ntfy.sh gehen.</span></label>
      <div class="actions"><button class="button small" data-action="ntfy-on">ntfy einschalten</button></div>`;
  } else {
    body = `<ol class="notify-steps"><li>Die kostenlose App <b>ntfy</b> installieren (Android oder iPhone).</li><li>In der App auf <b>+</b> tippen und dieses Thema eintragen:</li></ol>
      <div class="notify-topic"><code>${esc(n.topic)}</code><button class="button quiet small" data-action="notify-copy" data-text="${esc(n.topic)}">Kopieren</button></div>
      <p class="small muted">Oder im Browser öffnen: <a href="${esc(n.url)}" target="_blank" rel="noopener noreferrer">${esc(n.url.replace('https://', ''))}</a></p>
      ${notifySwitch('ntfy_preview', 'Vorschaubild mitsenden', n.preview)}
      ${notifyLast(n)}
      <div class="actions"><button class="button quiet small" data-action="notify-test" data-channel="ntfy">Testnachricht senden</button><button class="button danger small" data-action="notify-off" data-channel="ntfy">Trennen</button></div>`;
  }
  return `<section class="notify-channel" aria-labelledby="nc-ntfy"><div class="notify-top"><h3 class="group-title" id="nc-ntfy">ntfy</h3>${chip(n.state === 'on', n.state === 'on' ? 'An' : 'Aus')}</div>
    <p class="small muted">Aufs Handy, ohne Konto und ohne Telefonnummer.</p>${body}${notifyError('ntfy')}</section>`;
}
function notifyHtml(n) {
  return `<div class="sheet-head"><div class="notify-head"><button class="link small" data-action="settings">‹ Einrichtung</button><h2 class="headline">Benachrichtigungen</h2></div><button class="button quiet small" data-action="close">Fertig</button></div>
    <p class="muted notify-lede">Das Studio sagt dir Bescheid, wenn ein Film fertig ist, wenn du dran bist oder wenn etwas angehalten hat.${notifyChannels(n).length ? '' : ' Alles bleibt aus, bis du es hier einschaltest.'}</p>
    <section class="notify-when" aria-labelledby="nc-when"><h3 class="group-title" id="nc-when">Wann</h3>
      ${notifySwitch('done', 'Film fertig', n.events.done)}
      ${notifySwitch('turn', 'Du bist dran', n.events.turn, 'Wenn eine Freigabe auf dich wartet. Mit Autopilot nur, wenn er nicht allein weiterkommt.')}
      ${notifySwitch('blocked', 'Angehalten', n.events.blocked, 'Wenn ein Projekt wegen eines Fehlers stehen bleibt.')}
      ${notifySwitch('link', 'Link zum Projekt mitsenden', n.link, 'Der Link öffnet das Projekt nur am PC, nicht am Handy.')}</section>
    ${pcBlock()}${telegramBlock(n.telegram)}${ntfyBlock(n.ntfy)}
    <p class="small muted notify-whatsapp">WhatsApp gibt es hier nicht: Meta verlangt für jede Nachricht, die das Studio von sich aus schickt, eine Gebühr, und die kostenlosen Umwege laufen über inoffizielle Fremdanbieter – Telegram funktioniert ähnlich und ist kostenlos.</p>`;
}
function notifyRender(n, focus) {
  const before = $('#sheet .sheet-body'), top = before ? before.scrollTop : 0;
  S.notify = n; openSheet(notifyHtml(n));
  const body = $('#sheet .sheet-body'); if (body) body.scrollTop = top;
  const target = (focus && $(focus)) || $('#sheet .notify-error');
  if (target) target.focus({ preventScroll: false });
}
async function notifySheet() {
  NOTE.error = null;
  openSheet(`<div class="sheet-head"><h2 class="headline">Benachrichtigungen</h2><button class="button quiet small" data-action="close">Fertig</button></div><p class="muted">Wird geladen …</p>`);
  try { notifyRender(await api('/api/notify')); } catch (e) { openSheet(`<div class="sheet-head"><h2 class="headline">Benachrichtigungen</h2><button class="button quiet small" data-action="close">Fertig</button></div><p class="notify-error" role="alert">${esc(e.message)}</p>`); }
}
/* One step of a channel setup: errors stay next to the channel they belong to. */
async function notifyStep(channel, fn, focus) {
  try { const n = await fn(); NOTE.error = null; notifyRender(n || await api('/api/notify'), focus); return true; } catch (e) {
    NOTE.error = { channel, text: e.message }; notifyRender(S.notify || await api('/api/notify').catch(() => S.notify)); return false;
  }
}
function linesSheet(ei, si) {
  const sc = S.run.episodes[ei].scenes[si], lines = linesOf(sc);
  const row = (l, i) => `<div class="person"><select class="input" data-line="${i}" data-key="speaker" aria-label="Sprecher">${sc.cast.map(n => `<option ${n === l.speaker ? 'selected' : ''}>${esc(n)}</option>`).join('')}</select>
    <input class="input" data-line="${i}" data-key="text" value="${esc(l.text)}" maxlength="240" aria-label="Satz">
    <input type="hidden" data-line="${i}" data-key="emotion" value="${esc(l.emotion || 'Natürlich')}"><input type="hidden" data-line="${i}" data-key="pause_after" value="${l.pause_after ?? 0.18}"><button class="button danger small" data-action="drop-line" data-index="${i}">Entfernen</button></div>`;
  openSheet(`<div class="sheet-head"><h2 class="headline">Szene ${si + 1}: Text</h2><button class="button quiet small" data-action="close">Abbrechen</button></div>
    <form id="lines-form" data-episode="${ei}" data-scene="${si}">${lines.map(row).join('')}
    ${sc.cast.length ? '<div class="actions"><button type="button" class="button quiet small" data-action="add-line">Satz hinzufügen</button></div>' : '<p class="muted">In dieser Szene ist niemand im Bild.</p>'}
    <p class="small muted">Danach entsteht der Ton neu. Bilder bleiben.</p>
    <div class="actions"><button class="button" type="submit">Speichern</button></div></form>`);
}
function readLines(form) {
  const rows = {};
  form.querySelectorAll('[data-line]').forEach(el => { (rows[el.dataset.line] ||= {})[el.dataset.key] = el.value.trim(); });
  // Delivery and pause travel with each line: saving must not turn 'schreiend' into 'Natürlich'.
  const pause = v => (v === undefined || v === '' || !isFinite(+v)) ? 0.18 : +v;
  return Object.values(rows).filter(l => l.text).map(l => ({ speaker: l.speaker, text: l.text, emotion: l.emotion || 'Natürlich', pause_after: pause(l.pause_after) }));
}

/* Library figure -> figure of this project; the answer says whether it is applied or kept for later. */
async function castProfile(name, f, image, voice) {
  const d = await post(`/api/factory/${S.rid}/cast/profile`, { name, library_id: f.id, image, voice });
  const kept = (d.pending_cast || []).some(x => x.name === name && x.library_id === f.id);
  closeSheet(); await refreshRun(true);
  const what = image && voice ? 'Bild und Stimme' : image ? 'das Bild' : 'die Stimme';
  toast(kept ? `Vorgemerkt: ${name} bekommt ${what} von „${f.label}“, ${laterText(S.run)}.` : `${name} bekommt ${what} von „${f.label}“.`);
}
/* ---------- actions ---------- */
const audioPlayer = new Audio();
const actions = {
  async create() { await createFilm(); },
  'add-person'() { S.draft.participants.push({ name: '', traits: '', image: null, voice: null }); saveDraft(); refreshExtras(); },
  'remove-person'(b) { S.draft.participants.splice(+b.dataset.index, 1); saveDraft(); refreshExtras(); },
  'remove-example'(b) { S.draft.examples.splice(+b.dataset.index, 1); saveDraft(); refreshExtras(); },
  theme() {
    const root = document.documentElement, dark = (root.dataset.theme || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')) === 'dark';
    root.dataset.theme = dark ? 'light' : 'dark'; try { localStorage.setItem('cay-theme', root.dataset.theme); } catch (e) { /* ignore */ }
  },
  async settings() { await settingsSheet(); },
  async notify() { await notifySheet(); },
  async 'pc-on'() {
    if (!('Notification' in window)) return;
    const answer = await Notification.requestPermission();
    if (answer !== 'granted') {
      NOTE.error = { channel: 'pc', text: answer === 'denied' ? 'Der Browser hat Meldungen blockiert. Erlaube sie in den Website-Einstellungen (Symbol links neben der Adresse) und lade die Seite neu.'
        : 'Ohne deine Erlaubnis im Browser geht es nicht. Bitte noch einmal tippen und „Zulassen“ wählen.' };
      notifyRender(S.notify); return;
    }
    setPcNotify(true); NOTE.seq = null; NOTE.error = null; await notifyPoll();
    showPc('Cay Studio', 'So sieht eine Meldung am PC aus.', 'cay-studio-probe', null);
    notifyRender(S.notify, '[data-action="pc-test"]');
  },
  'pc-off'() { setPcNotify(false); NOTE.seq = null; NOTE.error = null; notifyRender(S.notify, '[data-action="pc-on"]'); },
  'pc-test'() { if (!showPc('Cay Studio', 'So sieht eine Meldung am PC aus.', 'cay-studio-probe', null)) toast('Der Browser hat die Meldung nicht angezeigt.'); },
  async 'tg-token'() {
    NOTE.token = ($('#tg-token') || {}).value?.trim() || ''; NOTE.consent.telegram = !!($('#tg-consent') || {}).checked;
    if (!NOTE.token) { NOTE.error = { channel: 'telegram', text: 'Bitte zuerst den Schlüssel aus der Nachricht von @BotFather einfügen.' }; notifyRender(S.notify, '#tg-token'); return; }
    if (!NOTE.consent.telegram) { NOTE.error = { channel: 'telegram', text: 'Bitte zuerst den Haken bei „Einverstanden“ setzen.' }; notifyRender(S.notify, '#tg-consent'); return; }
    if (await notifyStep('telegram', () => post('/api/notify/telegram/token', { token: NOTE.token, consent: true }), '[data-action="tg-connect"]')) NOTE.token = '';
  },
  async 'tg-connect'() {
    if (await notifyStep('telegram', () => post('/api/notify/telegram/connect'), '[data-action="notify-test"][data-channel="telegram"]')) toast('Verbunden. Schick dir zur Probe eine Testnachricht.');
  },
  async 'ntfy-on'() {
    NOTE.consent.ntfy = !!($('#ntfy-consent') || {}).checked;
    if (!NOTE.consent.ntfy) { NOTE.error = { channel: 'ntfy', text: 'Bitte zuerst den Haken bei „Einverstanden“ setzen.' }; notifyRender(S.notify, '#ntfy-consent'); return; }
    if (await notifyStep('ntfy', () => post('/api/notify/ntfy/enable', { consent: true }), '[data-action="notify-copy"]')) toast('ntfy ist an. Trag jetzt das Thema in der App ein.');
  },
  async 'notify-test'(b) {
    const channel = b.dataset.channel;
    if (await notifyStep(channel, () => post('/api/notify/test', { channel }), `[data-action="notify-test"][data-channel="${channel}"]`)) toast('Testnachricht gesendet. Sie sollte gleich auf dem Handy erscheinen.');
  },
  async 'notify-off'(b) {
    const channel = b.dataset.channel, telegram = channel === 'telegram';
    if (!confirm(telegram ? 'Telegram trennen? Der Bot-Schlüssel wird auf diesem PC gelöscht.' : 'ntfy trennen? Das Thema wird gelöscht. Schaltest du ntfy wieder ein, gibt es ein neues.')) return;
    NOTE.consent[channel] = false;
    if (await notifyStep(channel, () => api('/api/notify/' + channel, { method: 'DELETE' }))) toast(telegram ? 'Getrennt. Den Bot selbst löschst du bei @BotFather mit /deletebot.' : 'ntfy ist aus.');
  },
  async 'notify-copy'(b) {
    try { await navigator.clipboard.writeText(b.dataset.text); toast('Thema kopiert.'); } catch (e) { toast('Kopieren nicht möglich. Bitte das Thema abschreiben.'); }
  },
  close() { closeSheet(); },
  async 'setup-voices'() { await post('/api/factory/voice-studio/setup'); toast('Stimmen werden eingerichtet. Das dauert einige Minuten.'); closeSheet(); },
  async 'upgrade-voices'() { await post('/api/factory/voice-studio/upgrade'); toast('Dialogmodell wird ergänzt.'); closeSheet(); },
  async 'turbo-setup'() { await post('/api/factory/turbo/setup'); toast('Turbo wird eingerichtet und geprüft. Danach einmal den PC neu starten.'); closeSheet(); },
  async 'turbo-off'() { await post('/api/factory/turbo/off'); toast('Turbo ist aus.'); closeSheet(); },
  async 'setup-animation'() { await post('/api/factory/render-studio/setup'); toast('Animationsteile werden eingerichtet.'); closeSheet(); },
  async pause() { await post(`/api/factory/${S.rid}/pause`); toast('Pausiert, sobald der aktuelle Schritt fertig ist.'); },
  async resume() { await post(`/api/factory/${S.rid}/resume`); toast('Geht weiter.'); },
  async restore() { await post(`/api/factory/${S.rid}/restore`); toast('Wiederhergestellt. Mit „Fortsetzen“ geht es weiter.'); },
  async autopilot(b) { await post(`/api/factory/${S.rid}/autopilot`, { enabled: b.checked }); toast(b.checked ? 'Autopilot an: der Rest läuft ohne Zwischenstopps.' : 'Autopilot aus.'); },
  async 'abort-step'() { if (confirm('Aktuellen Abschnitt abbrechen und pausieren? Fertige Abschnitte bleiben erhalten.')) { await post(`/api/factory/${S.rid}/abort-step`, { fast: false }); toast('Abgebrochen und pausiert.'); } },
  async 'abort-fast'() { if (confirm('Abschnitt neu starten? Fertige Bilder, Stimmen und Abschnitte bleiben erhalten.')) { await post(`/api/factory/${S.rid}/abort-step`, { fast: true }); toast('Der Abschnitt wird neu gerechnet.'); } },
  async choose(b) { await post(`/api/factory/${S.rid}/choose`, { episode: +b.dataset.episode, scene: +b.dataset.scene, step_id: b.dataset.step }); },
  async revise(b) {
    openSheet(`<div class="sheet-head"><h2 class="headline">Neue Bilder für Szene ${+b.dataset.scene + 1}</h2><button class="button quiet small" data-action="close">Abbrechen</button></div>
      <form id="revise-form" data-episode="${b.dataset.episode}" data-scene="${b.dataset.scene}"><label class="field"><span>Was soll anders sein? (optional)</span><textarea class="textarea" name="note" maxlength="700" placeholder="Zum Beispiel: beide Arme sichtbar, Figur steht näher an der Tür"></textarea></label>
      <div class="actions"><button class="button" type="submit">Zwei neue Bilder erzeugen</button></div></form>`);
  },
  async 'cast-approve'() { await post(`/api/factory/${S.rid}/cast/approve`); toast('Figuren übernommen. Die Szenenbilder entstehen.'); },
  async 'cast-redo'(b) {
    if (!confirm(`${b.dataset.name} neu gestalten? Alle Szenen mit ${b.dataset.name} bekommen neue Bilder.`)) return;
    await post(`/api/factory/${S.rid}/cast/redo`, { name: b.dataset.name });
    closeSheet(); toast(`${b.dataset.name} wird neu gestaltet.`);
  },
  'edit-lines'(b) { linesSheet(+b.dataset.episode, +b.dataset.scene); },
  'add-line'() { const form = $('#lines-form'), sc = S.run.episodes[+form.dataset.episode].scenes[+form.dataset.scene]; const lines = readLines(form); lines.push({ speaker: sc.cast[0], text: '' }); linesSheetFrom(form, lines); },
  'drop-line'(b) { const form = $('#lines-form'), lines = readLines(form); lines.splice(+b.dataset.index, 1); linesSheetFrom(form, lines); },
  async 'approve-images'() { await post(`/api/factory/${S.rid}/approve-images`, { revision: S.run.revision }); toast('Bilder übernommen. Die Stimmen entstehen.'); },
  async 'approve-voices'() { await post(`/api/factory/${S.rid}/approve-voices`, { revision: S.run.revision }); toast('Ton freigegeben. Die Animation beginnt.'); },
  async 'approve-sample'() { await post(`/api/factory/${S.rid}/approve-sample`, { revision: S.run.revision }); toast('Probe übernommen.'); },
  async 'reject-sample'() { await post(`/api/factory/${S.rid}/reject-sample`, { revision: S.run.revision }); },
  async 'rebuild-audio'() { await post(`/api/factory/${S.rid}/rebuild-audio`); toast('Der Ton wird neu erzeugt.'); },
  async 'more-dialogue'() {
    await post(`/api/factory/${S.rid}/correction`, { request_key: hex(), revision: S.run.revision, kind: 'dialogue', episode: S.episode,
      message: 'Ergänze Reaktionen, Widerspruch und Entscheidungen, damit weniger Pausen entstehen. Bestehende Sätze behalten.' });
    toast('Dialoge werden ergänzt. Danach entsteht neuer Ton.');
  },
  async 'new-voice'(b) {
    const select = document.querySelector(`[data-voice="${CSS.escape(b.dataset.name)}"]`);
    await post(`/api/factory/${S.rid}/voice-settings`, { name: b.dataset.name, voice_preset: select.value, voice_description: '', new_variant: true });
    toast(`Neue Stimme für ${b.dataset.name} wird gestaltet.`);
  },
  async 'reopen-voices'() { await post(`/api/factory/${S.rid}/reopen-voices`, { revision: S.run.revision }); },
  async 'reopen-output'() { await post(`/api/factory/${S.rid}/reopen-output`, { revision: S.run.revision }); },
  async 'new-edition'() { const run = await post(`/api/factory/${S.rid}/new-edition`); toast('Neue Fassung angelegt.'); location.hash = 'p=' + run.id; },
  episode(b) { S.episode = +b.dataset.index; render(); },
  async copy(b) { try { await navigator.clipboard.writeText(b.dataset.text); toast('Beschreibung kopiert.'); } catch (e) { toast('Kopieren nicht möglich. Text bitte markieren.'); } },
  'lib-new'() { libraryEditor(null); },
  'lib-edit'(b) { libraryEditor((S.library || []).find(f => f.id === b.dataset.id)); },
  async 'lib-delete'(b) {
    const f = (S.library || []).find(x => x.id === b.dataset.id);
    if (!f || !confirm(`„${f.label}“ aus deinen Figuren entfernen? Filme, die die Figur schon nutzen, bleiben unverändert.`)) return;
    await api(`/api/library/${f.id}`, { method: 'DELETE' });
    await refreshLibrary(); closeSheet(); render(); toast(`„${f.label}“ entfernt.`);
  },
  'lib-voice-clear'() {
    const form = $('#lib-form'); form.elements.voice.value = '';
    $('#lib-voice').innerHTML = '<span class="muted small">Ohne Stimme. Das Studio gestaltet eine passende.</span>';
  },
  async 'lib-pick-compose'() { await refreshLibrary(); S.libQuery = ''; S.libLook = 'all'; S.pick = { mode: 'compose', selected: new Set() }; pickerSheet(); },
  async 'lib-pick-project'(b) { await refreshLibrary(); S.libQuery = ''; S.libLook = 'all'; S.pick = { mode: 'project', name: b.dataset.name, selected: null }; pickerSheet(); },
  'lib-choose'(b) {
    const p = S.pick, id = b.dataset.id;
    if (p.mode === 'project') p.selected = p.selected === id ? null : id;
    else if (p.selected.has(id)) p.selected.delete(id); else p.selected.add(id);
    document.querySelectorAll('#pick-grid .pick').forEach(x => x.setAttribute('aria-pressed', String(p.mode === 'project' ? p.selected === x.dataset.id : p.selected.has(x.dataset.id))));
    $('#pick-foot').innerHTML = pickFoot();
  },
  'lib-add-compose'() {
    const chosen = (S.library || []).filter(f => S.pick.selected.has(f.id));
    for (const f of chosen) {
      const entry = { name: f.name, traits: f.traits || '', image: f.image || null, image_mode: f.image_mode || 'neutral', voice: f.voice || null,
        voice_text: f.voice_text || '', voice_design: f.voice_design || null, voice_from_library: !!f.voice, library_id: f.id, library_label: f.label,
        library_image: f.image ? f.id : null, library_voice: f.voice ? f.id : null, image_look: f.image ? f.look : null };
      const at = S.draft.participants.findIndex(x => x.name.trim().toLowerCase() === f.name.toLowerCase());
      if (at >= 0) S.draft.participants[at] = entry; else S.draft.participants.push(entry);
    }
    if (S.draft.characters === 'none') S.draft.characters = 'invent';
    saveDraft(); closeSheet(); refreshExtras(); updateCompose();
    toast(chosen.length === 1 ? `${chosen[0].label} spielt mit.` : `${chosen.length} Figuren spielen mit.`);
  },
  async 'lib-apply'() {
    const p = S.pick, f = (S.library || []).find(x => x.id === p.selected);
    const image = !!($('#pick-image') && $('#pick-image').checked), voice = !!($('#pick-voice') && $('#pick-voice').checked);
    if (!image && !voice) { toast('Wähle Bild, Stimme oder beides.'); return; }
    await castProfile(p.name, f, image, voice);
  },
  async 'lib-save'(b) { saveToLibrarySheet(b.dataset.name); },
  'figure-menu'(b) { figureSheet(b.dataset.name); },
  async 'lib-suggest'(b) {
    const d = S.run, f = (S.library || []).find(x => x.id === b.dataset.id), name = b.dataset.name;
    if (!f) return;
    const parts = usableParts(d, f), scenes = scenesWith(d, name);
    if (parts.includes('image') && d.state === 'image_review' && d.cast_windows.image === 'now'
        && !confirm(`„${f.label}“ für ${name} verwenden? ${scenes} ${scenes === 1 ? 'Szene wird' : 'Szenen werden'} neu gezeichnet, deine Bildwahl dort entfällt.`)) return;
    await castProfile(name, f, parts.includes('image'), parts.includes('voice'));
  },
  async 'cast-cancel'(b) {
    await api(`/api/factory/${S.rid}/cast/pending/${encodeURIComponent(b.dataset.name)}`, { method: 'DELETE' });
    closeSheet(); await refreshRun(true); toast('Vormerkung aufgehoben.');
  },
  async 'cast-mode'(b) {
    const e = participantOf(S.run, b.dataset.name), scenes = scenesWith(S.run, b.dataset.name);
    if (S.run.state === 'image_review' && !confirm(`${scenes} ${scenes === 1 ? 'Szene wird' : 'Szenen werden'} mit ${b.dataset.name} neu gezeichnet. Weiter?`)) return;
    await post(`/api/factory/${S.rid}/cast/image`, { name: b.dataset.name, asset_id: e.image, image_mode: b.dataset.mode });
    closeSheet(); await refreshRun(true);
    toast(b.dataset.mode === 'exact' ? `${b.dataset.name} nutzt das Bild jetzt genau so.` : `${b.dataset.name} wird mit neutralem Gesicht nachgezeichnet.`);
  },
  async 'figure-voice-new'(b) {
    const p = S.run.plan.cast.find(x => x.name === b.dataset.name);
    await post(`/api/factory/${S.rid}/voice-settings`, { name: p.name, voice_preset: p.voice_preset || 'man', voice_description: p.voice_description || '', new_variant: true });
    closeSheet(); await refreshRun(true); toast(`Neue Stimme für ${p.name} wird gestaltet.`);
  },
  play(b) {
    const same = audioPlayer.dataset.src === b.dataset.src && !audioPlayer.paused;
    document.querySelectorAll('.play').forEach(x => { x.innerHTML = PLAY; });
    audioPlayer.pause();
    if (same) return;
    audioPlayer.src = b.dataset.src; audioPlayer.dataset.src = b.dataset.src; audioPlayer.play().catch(() => toast('Datei noch nicht verfügbar.'));
    b.innerHTML = PAUSE; audioPlayer.onended = () => { b.innerHTML = PLAY; };
  },
};
function linesSheetFrom(form, lines) {
  const ei = +form.dataset.episode, si = +form.dataset.scene, sc = S.run.episodes[ei].scenes[si];
  const original = sc.dialogues; sc.dialogues = lines.map(l => ({ ...l, text: l.text.trim() || '' })); linesSheet(ei, si); sc.dialogues = original;
}
const NEEDS_REFRESH = new Set(['cast-approve', 'cast-redo', 'pause', 'resume', 'restore', 'autopilot', 'abort-step', 'abort-fast', 'choose', 'approve-images', 'approve-voices', 'approve-sample', 'reject-sample', 'rebuild-audio', 'more-dialogue', 'new-voice', 'reopen-voices', 'reopen-output']);

document.addEventListener('click', async event => {
  const nav = event.target.closest('[data-nav]');
  if (nav) { location.hash = nav.dataset.nav; return; }
  const libLink = event.target.closest('a[href="#library"][data-action="close"]');
  if (libLink) { closeSheet(); return; }
  const set = event.target.closest('[data-set]');
  if (set && S.page === 'new') { const v = set.dataset.value; S.draft[set.dataset.set] = /^\d+$/.test(v) ? +v : v; saveDraft(); updateCompose(); return; }
  const look = event.target.closest('[data-liblook]');
  if (look) {
    S.libLook = look.dataset.liblook;
    look.parentElement.querySelectorAll('[data-liblook]').forEach(x => x.setAttribute('aria-pressed', String(x === look)));
    const grid = $('#' + look.dataset.target); if (grid) grid.innerHTML = look.dataset.target === 'pick-grid' ? pickItems() : libraryCards();
    return;
  }
  const mixButton = event.target.closest('[data-mix]');
  if (mixButton) {
    const mix = S.run.mix || {};
    await guarded(mixButton, async () => {
      await post(`/api/factory/${S.rid}/mix-settings`, { music_mode: mixButton.dataset.value, music_level: mix.music_level ?? 0.7, effects_level: mix.effects_level ?? 0.65, ambience_level: mix.ambience_level ?? 0.6 });
      toast('Musik geändert. Der Ton wird neu gemischt.'); await refreshRun(true);
    });
    return;
  }
  const b = event.target.closest('[data-action]');
  if (!b || b.tagName === 'INPUT') return;
  const name = b.dataset.action;
  if (!actions[name]) return;
  event.preventDefault();
  await guarded(b, async () => { await actions[name](b); if (NEEDS_REFRESH.has(name)) await refreshRun(true); });
});
document.addEventListener('change', async event => {
  const el = event.target;
  if (el.matches('input[data-action="autopilot"]')) { await guarded(el, async () => { await actions.autopilot(el); await refreshRun(true); }); return; }
  if (el.matches('[data-notify]')) {
    await guarded(el, async () => {
      try { S.notify = await put('/api/notify', { [el.dataset.notify]: el.checked }); } catch (e) { el.checked = !el.checked; throw e; }
    });
    return;
  }
  if (el.matches('[data-field="autopilot"]')) { S.draft.autopilot = el.checked; saveDraft(); updateCompose(); return; }
  if (el.matches('[data-field="cast_check"]')) { S.draft.cast_check = el.checked; saveDraft(); return; }
  if (el.matches('[data-person-exact]')) { S.draft.participants[+el.dataset.personExact].image_mode = el.checked ? 'exact' : 'neutral'; saveDraft(); return; }
  if (el.matches('[data-upload="lib-image"], [data-upload="lib-voice"]')) {
    const form = $('#lib-form'), file = el.files[0];
    await guarded(el, async () => {
      if (el.dataset.upload === 'lib-image') {
        const id = await upload('image', file); form.elements.image.value = id;
        const box = el.closest('.lib-photo'); box.classList.remove('add');
        box.querySelector('img, span') && box.querySelector('img, span').remove(); box.insertAdjacentHTML('afterbegin', `<img src="/api/factory/assets/${esc(id)}" alt="">`);
      } else {
        const id = await upload('voice', file); form.elements.voice.value = id;
        $('#lib-voice').innerHTML = `<button type="button" class="play" data-action="play" data-src="/api/factory/assets/${esc(id)}" aria-label="Stimme anhören">${PLAY}</button><span class="small muted">Neue Aufnahme, ${esc(file.name)}</span>`;
      }
    });
    el.value = '';
    return;
  }
  if (el.matches('[data-upload]')) {
    const kind = el.dataset.upload, files = [...el.files];
    await guarded(el, async () => {
      if (kind === 'cast-voice') {
        const id = await upload('voice', files[0]);
        await post(`/api/factory/${S.rid}/voice-reference`, { name: el.dataset.name, asset_id: id, voice_text: '' });
        closeSheet(); toast(`Deine Aufnahme für ${el.dataset.name} wird verwendet. Die Sätze werden neu eingesprochen.`); await refreshRun(true); return;
      }
      if (kind === 'cast') {
        const png = await upload('image', files[0]);
        await post(`/api/factory/${S.rid}/cast/image`, { name: el.dataset.name, asset_id: png });
        closeSheet(); toast(`Dein Bild für ${el.dataset.name} wird verwendet.`); await refreshRun(true); return;
      }
      if (kind === 'example') {
        for (const file of files.slice(0, 4 - S.draft.examples.length)) S.draft.examples.push(await upload('image', file));
        toast(files.length > 1 ? 'Vorlagen übernommen.' : 'Vorlage übernommen.');
      } else {
        const id = await upload(kind, files[0]);
        if (kind === 'music') S.draft.music = id;
        else {
          // Cay's own file replaces the library's for this part; the profile chip stays for the other part.
          const person = S.draft.participants[+el.dataset.index]; person[kind] = id;
          if (kind === 'image') { person.library_image = null; person.image_look = null; }
          if (kind === 'voice') { person.library_voice = null; person.voice_from_library = false; person.voice_design = null; person.voice_text = ''; }
          if (!person.library_image && !person.voice_from_library) { person.library_id = null; person.library_label = ''; }
        }
        toast('Datei übernommen.');
      }
      saveDraft(); refreshExtras();
    });
  }
});
document.addEventListener('input', event => {
  const el = event.target;
  if (el.dataset.libq) { S.libQuery = el.value; const grid = $('#' + el.dataset.libq); if (grid) grid.innerHTML = el.dataset.libq === 'pick-grid' ? pickItems() : libraryCards(); return; }
  if (el.dataset.field && !['autopilot', 'cast_check'].includes(el.dataset.field)) { S.draft[el.dataset.field] = el.value; saveDraft(); }
  if (el.dataset.person) { S.draft.participants[+el.dataset.person][el.dataset.key] = el.value; saveDraft(); }
});
document.addEventListener('submit', async event => {
  const form = event.target; event.preventDefault();
  if (form.id === 'lib-form' || form.id === 'lib-save-form') {
    await guarded(form.querySelector('[type=submit]'), async () => {
      if (form.id === 'lib-form') {
        const body = readLibraryForm(form);
        if (!body.image && !body.voice) { toast('Wähle ein Bild, eine Aufnahme oder beides.'); return; }
        await (form.dataset.id ? put(`/api/library/${form.dataset.id}`, body) : post('/api/library', body));
        toast(form.dataset.id ? 'Änderungen gesichert.' : `„${body.label}“ ist jetzt in deinen Figuren.`);
      } else {
        const label = form.elements.label.value.trim();
        await post('/api/library/from-project', { project: S.rid, name: form.dataset.name, label });
        toast(`„${label}“ ist jetzt in deinen Figuren.`);
      }
      await refreshLibrary(); closeSheet(); render();
    });
    return;
  }
  const ei = +form.dataset.episode, si = +form.dataset.scene;
  await guarded(form.querySelector('[type=submit]'), async () => {
    if (form.id === 'revise-form') {
      await post(`/api/factory/${S.rid}/revise`, { episode: ei, scene: si, note: form.note.value.trim() });
      toast('Zwei neue Bilder werden erzeugt.');
    } else if (form.id === 'lines-form') {
      const sc = S.run.episodes[ei].scenes[si];
      await put(`/api/factory/${S.rid}/dialogues`, { episode: ei, scene: si, action: sc.action, dialogues: readLines(form) });
      toast('Gespeichert. Der Ton entsteht neu.');
    }
    closeSheet(); await refreshRun(true);
  });
});
async function guarded(el, fn) {
  if (S.busy) return;
  S.busy = true; if (el) el.disabled = true;
  try { await fn(); } catch (e) { toast(e.message); } finally { S.busy = false; if (el && el.isConnected) el.disabled = false; }
}

/* ---------- polling ---------- */
async function tick() {
  notifyPoll();
  try {
    if (S.page === 'project' && S.rid) {
      const before = S.run && S.run.state;
      if (!S.run || WORKING.has(S.run.state) || (REVIEW.has(S.run.state) && S.run.idea.autopilot) || S.deferred || before === 'blocked') await refreshRun(false);
    } else if (S.page === 'projects') await refreshRuns();
  } catch (e) { /* next tick */ }
}
async function health() {
  try {
    const s = await api('/api/status'), ok = s.system.comfy.online && s.system.ollama.online, el = $('#health');
    el.className = 'health ' + (ok ? 'ok' : 'bad');
    el.title = ok ? 'ComfyUI und Planung erreichbar' : `Nicht erreichbar: ${[!s.system.comfy.online && 'ComfyUI', !s.system.ollama.online && 'Planung'].filter(Boolean).join(', ')}`;
  } catch (e) { $('#health').className = 'health bad'; }
}

async function start() {
  try { const theme = localStorage.getItem('cay-theme'); if (theme) document.documentElement.dataset.theme = theme; } catch (e) { /* ignore */ }
  S.draft = loadDraft();
  const boot = await api('/api/bootstrap');
  S.token = boot.csrf; S.version = boot.version; $('#version').textContent = 'Cay Studio ' + boot.version;
  S.speed = await api('/api/factory/speed').catch(() => null);
  await refreshLibrary().catch(() => { S.library = []; });
  route(); await load(); health(); notifyPoll();
  window.addEventListener('hashchange', () => { route(); load(); });
  setInterval(tick, 2500); setInterval(health, 15000); setInterval(tickClocks, 1000);
}
start().catch(e => { $('#main').innerHTML = `<div class="empty"><h2 class="headline">Das Studio antwortet nicht.</h2><p class="muted">${esc(e.message)} Cay_Studio_Starten.cmd erneut öffnen.</p></div>`; });
