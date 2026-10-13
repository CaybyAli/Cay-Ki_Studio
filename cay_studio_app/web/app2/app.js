'use strict';
/* Cay Studio 0.14 – one script for the whole studio (replaces 15 layered scripts).
   Rules: one next step per screen, no inline styles or scripts (strict CSP),
   polling never re-renders while Cay types or plays audio/video. */

const S = { token: '', version: '', page: 'new', rid: null, run: null, progress: null, runs: null, docs: {}, speed: null,
  draft: null, busy: false, episode: 0, sig: '', health: null, deferred: false };
const $ = (q, root = document) => root.querySelector(q);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const hex = () => Array.from(crypto.getRandomValues(new Uint8Array(16)), b => b.toString(16).padStart(2, '0')).join('');
const PLAY = '<svg viewBox="0 0 12 12" aria-hidden="true"><path d="M3 1.5v9l7.5-4.5z" fill="currentColor"/></svg>';
const PAUSE = '<svg viewBox="0 0 12 12" aria-hidden="true"><path d="M2.5 1.5h2.5v9H2.5zm4.5 0h2.5v9H7z" fill="currentColor"/></svg>';

/* ---------- data ---------- */
function defaults() {
  return { request_key: hex(), idea: '', title: '', episodes: 1, duration: 60, look: 'auto', characters: 'invent', participants: [],
    examples: [], music: null, fps: 25, quality: 'fast', smooth: true, speech_engine: 'auto', lip_sync: 'audio', autopilot: true };
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
const STAGE = { planning: 0, correcting: 1, pictures: 1, image_review: 1, voicing: 2, audio_mixing: 2, voice_review: 2, rendering: 3, sample_review: 3, finishing: 3, done: 4 };
const WORKING = new Set(['planning', 'correcting', 'pictures', 'voicing', 'audio_mixing', 'rendering', 'finishing']);
const REVIEW = new Set(['image_review', 'voice_review', 'sample_review']);
const LOOKS = [['auto', 'Automatisch'], ['film', 'Film'], ['cartoon', 'Cartoon'], ['clay', 'Knete'], ['paper', 'Papier']];
const QUALITY = { draft: 'Entwurf', fast: 'Standard', balanced: 'Ausgewogen (alt)', high: 'Hoch (alt)' };
const PRESETS = [['young_woman', 'Junge Frau'], ['woman', 'Frau'], ['young_man', 'Junger Mann'], ['man', 'Mann'], ['child_girl', 'Mädchen'], ['child_boy', 'Junge'], ['grandma', 'Oma'], ['grandpa', 'Opa'], ['creature', 'Fantasiefigur']];
// Measured on Cay's RTX 4090 (12.10.2026): 9 min fastest, 20.7 min average per 5 s piece at Standard.
const SECONDS_PER_FILM_SECOND = { fast: [105, 326], draft: [55, 170] };

function status(d) {
  if (d.deleted) return ['stop', 'Im Papierkorb'];
  if (d.state === 'done') return ['done', 'Fertig'];
  if (d.state === 'blocked') return ['stop', 'Angehalten'];
  if (d.paused) return ['', 'Pausiert'];
  if (REVIEW.has(d.state) && !d.autopilot) return ['you', 'Wartet auf dich'];
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
  // Prefer what this PC measured for finished films; else the 12.10. measurement.
  const total = draft.duration * draft.episodes, measured = S.speed && S.speed[draft.quality];
  const [low, high] = measured ? [measured.low, measured.high] : SECONDS_PER_FILM_SECOND[draft.quality] || SECONDS_PER_FILM_SECOND.fast;
  const basis = measured ? `gemessen an ${measured.films} fertigen ${measured.films === 1 ? 'Film' : 'Filmen'} in dieser Qualität` : 'Hochrechnung aus deiner Messung vom 12.10.';
  return `Rechenzeit ungefähr ${low === high ? duration(total * low) : `${duration(total * low)} bis ${duration(total * high)}`}, ${basis}`;
}

/* ---------- shell ---------- */
function route() {
  const hash = decodeURIComponent(location.hash.slice(1));
  if (hash.startsWith('p=')) { S.page = 'project'; if (S.rid !== hash.slice(2)) { S.rid = hash.slice(2); S.run = null; S.progress = null; S.sig = ''; S.episode = 0; } }
  else S.page = hash === 'projects' ? hash : 'new';
}
function render() {
  document.querySelectorAll('[data-nav]').forEach(b => b.setAttribute('aria-current', (b.dataset.nav === S.page || (S.page === 'project' && b.dataset.nav === 'projects')) ? 'page' : 'false'));
  const main = $('#main');
  main.innerHTML = S.page === 'project' ? projectView() : S.page === 'projects' ? projectsView() : composeView();
  S.deferred = false;
  if (S.page === 'new') updateCompose();
  if (S.page === 'project') paintProgress();
}
async function load() {
  render();
  try {
    if (S.page === 'project') await refreshRun(true);
    else if (S.page === 'projects') await refreshRuns();
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
        <label class="file-pill ${p.voice ? 'set' : ''}">${p.voice ? 'Eigene Stimme gewählt' : 'Eigene Stimme (optional)'}<input type="file" accept="audio/*" data-upload="voice" data-index="${i}"></label>
      </div>
      <button class="icon-remove" data-action="remove-person" data-index="${i}" aria-label="Figur entfernen">×</button></div>`).join('');
  return `<section class="group"><h3 class="group-title">Look-Vorlagen</h3>
      <p class="hint">Bis zu vier Bilder, die zeigen, wie dein Film aussehen soll, zum Beispiel Knete-Optik, Farben oder Licht. Das Studio übernimmt den Stil, nicht die Figuren daraus.</p>
      <div class="thumbs">${thumbs}${add}</div></section>
    <section class="group"><h3 class="group-title">Figuren</h3>
      ${seg('characters', [['invent', 'Studio erfindet'], ['provided', 'Nur meine Figuren'], ['none', 'Ohne Figuren']], d.characters)}
      <p class="hint">Eigene Figuren mit Bild sehen in jeder Szene und Folge gleich aus.</p>
      <div class="people">${people}</div>
      <button class="button quiet small" data-action="add-person">Figur hinzufügen</button></section>
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
    participants: d.characters === 'none' ? [] : d.participants.filter(p => p.name.trim()).map(p => ({ name: p.name.trim(), traits: p.traits || '', image: p.image || null, voice: p.voice || null, voice_text: '' })) };
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
    return `<a class="tile" href="#p=${esc(r.id)}">${frameFor(r.id, doc, badge)}<span class="tile-title">${esc(r.title)}</span><span class="status ${cls}">${esc(label)}</span></a>`;
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
      <p class="muted">${esc(settingsLine(d))}</p>
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
  return (scene.dialogues && scene.dialogues.length) ? scene.dialogues : scene.dialogue ? [{ speaker: scene.speaker, text: scene.dialogue }] : [];
}
function sectionsView(d) {
  if (!d.episodes || !d.episodes.length) return '';
  if (d.state === 'done') return filmsSection(d);
  if (['image_review', 'pictures'].includes(d.state)) return scenesSection(d, true);
  if (d.state === 'voice_review') return soundSection(d) + scenesSection(d, false);
  return scenesSection(d, false);
}
function scenesSection(d, choose) {
  const ep = d.episodes[S.episode] || d.episodes[0], ei = d.episodes.indexOf(ep);
  const editable = ['image_review', 'voice_review'].includes(d.state);
  return `<section class="section"><h2 class="title">${d.episodes.length > 1 ? esc(ep.title) : 'Drehbuch'}</h2>${episodeTabs(d)}
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
        <button class="button quiet small" data-action="new-voice" data-name="${esc(p.name)}">Andere Stimme</button></div>`).join('')}</div>
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
  const changed = d.revision !== S.sig;
  S.run = d; S.sig = d.revision;
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

/* ---------- sheets ---------- */
function openSheet(html) { const sheet = $('#sheet'); sheet.innerHTML = `<div class="sheet-body">${html}</div>`; if (!sheet.open) sheet.showModal(); }
function closeSheet() { const sheet = $('#sheet'); if (sheet.open) sheet.close(); }
async function settingsSheet() {
  openSheet(`<div class="sheet-head"><h2 class="headline">Einrichtung</h2><button class="button quiet small" data-action="close">Fertig</button></div><p class="muted">Bereitschaft wird geprüft …</p>`);
  const [check, voices, animation, boost] = await Promise.all([api('/api/factory/check').catch(e => ({ error: e.message })),
    api('/api/factory/voice-studio/status').catch(() => null), api('/api/factory/render-studio/status').catch(() => null), api('/api/factory/turbo').catch(() => null)]);
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
    <h3 class="headline">Weitere Werkzeuge</h3>
    <p><a href="/classic#remix">Figurentausch</a> öffnet sich in der bisherigen Ansicht. <a href="/classic">Bisherige Oberfläche</a></p>
    <p class="small muted">Cay Studio ${esc(S.version)}. Alles läuft lokal, ohne Abo und ohne kostenpflichtige Dienste.</p>`);
}
function linesSheet(ei, si) {
  const sc = S.run.episodes[ei].scenes[si], lines = linesOf(sc);
  const row = (l, i) => `<div class="person"><select class="input" data-line="${i}" data-key="speaker" aria-label="Sprecher">${sc.cast.map(n => `<option ${n === l.speaker ? 'selected' : ''}>${esc(n)}</option>`).join('')}</select>
    <input class="input" data-line="${i}" data-key="text" value="${esc(l.text)}" maxlength="240" aria-label="Satz"><button class="button danger small" data-action="drop-line" data-index="${i}">Entfernen</button></div>`;
  openSheet(`<div class="sheet-head"><h2 class="headline">Szene ${si + 1}: Text</h2><button class="button quiet small" data-action="close">Abbrechen</button></div>
    <form id="lines-form" data-episode="${ei}" data-scene="${si}">${lines.map(row).join('')}
    ${sc.cast.length ? '<div class="actions"><button type="button" class="button quiet small" data-action="add-line">Satz hinzufügen</button></div>' : '<p class="muted">In dieser Szene ist niemand im Bild.</p>'}
    <p class="small muted">Danach entsteht der Ton neu. Bilder bleiben.</p>
    <div class="actions"><button class="button" type="submit">Speichern</button></div></form>`);
}
function readLines(form) {
  const rows = {};
  form.querySelectorAll('[data-line]').forEach(el => { (rows[el.dataset.line] ||= {})[el.dataset.key] = el.value.trim(); });
  return Object.values(rows).filter(l => l.text).map(l => ({ speaker: l.speaker, text: l.text, emotion: 'Natürlich', pause_after: 0.18 }));
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
const NEEDS_REFRESH = new Set(['pause', 'resume', 'restore', 'autopilot', 'abort-step', 'abort-fast', 'choose', 'approve-images', 'approve-voices', 'approve-sample', 'reject-sample', 'rebuild-audio', 'more-dialogue', 'new-voice', 'reopen-voices', 'reopen-output']);

document.addEventListener('click', async event => {
  const nav = event.target.closest('[data-nav]');
  if (nav) { location.hash = nav.dataset.nav; return; }
  const set = event.target.closest('[data-set]');
  if (set && S.page === 'new') { const v = set.dataset.value; S.draft[set.dataset.set] = /^\d+$/.test(v) ? +v : v; saveDraft(); updateCompose(); return; }
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
  if (el.matches('[data-field="autopilot"]')) { S.draft.autopilot = el.checked; saveDraft(); updateCompose(); return; }
  if (el.matches('[data-upload]')) {
    const kind = el.dataset.upload, files = [...el.files];
    await guarded(el, async () => {
      if (kind === 'example') {
        for (const file of files.slice(0, 4 - S.draft.examples.length)) S.draft.examples.push(await upload('image', file));
        toast(files.length > 1 ? 'Vorlagen übernommen.' : 'Vorlage übernommen.');
      } else {
        const id = await upload(kind, files[0]);
        if (kind === 'music') S.draft.music = id; else S.draft.participants[+el.dataset.index][kind] = id;
        toast('Datei übernommen.');
      }
      saveDraft(); refreshExtras();
    });
  }
});
document.addEventListener('input', event => {
  const el = event.target;
  if (el.dataset.field && el.dataset.field !== 'autopilot') { S.draft[el.dataset.field] = el.value; saveDraft(); }
  if (el.dataset.person) { S.draft.participants[+el.dataset.person][el.dataset.key] = el.value; saveDraft(); }
});
document.addEventListener('submit', async event => {
  const form = event.target; event.preventDefault();
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
  route(); await load(); health();
  window.addEventListener('hashchange', () => { route(); load(); });
  setInterval(tick, 2500); setInterval(health, 15000);
}
start().catch(e => { $('#main').innerHTML = `<div class="empty"><h2 class="headline">Das Studio antwortet nicht.</h2><p class="muted">${esc(e.message)} Cay_Studio_Starten.cmd erneut öffnen.</p></div>`; });
