'use strict';
const exactShots=seconds=>Math.max(3,Math.min(15,Math.ceil(seconds/6)));
budget=function(){const d=state.draft,n=exactShots(d.duration);return `${d.episodes} ${d.episodes===1?'Film':'Filme'} · ${n} Szenen je Folge · ${n*d.episodes*2} Bildvarianten. Gleiche Dauer, gleiche Szenenzahl. Erst Bilder und Ton prüfen, dann produzieren.`};
const liveRun=runView;let lastReview=null;
runView=function(){
 const d=state.run;if(!d)return liveRun();
 if(d.state==='sample_review')return topRun(d,3)+`<section class="sample-check"><p class="section-kicker">Kurze Probe vor der Serie</p><h2>Passt dieser erste Abschnitt?</h2><p>Prüfe die Mundbewegung bei Sprache und Stille, die Identität und den Stimmklang. Die restliche Produktion wartet auf deine Entscheidung.</p><video controls playsinline preload="metadata" src="/api/factory/${d.id}/sample?k=${d.sample.key}"></video><div class="row"><button class="primary" data-action="sample-approve">Passt · Produktion fortsetzen</button><button class="ghost" data-action="sample-reject">Ton / Qualität nachbessern</button></div></section>`;
 if(['image_review','voice_review'].includes(d.state)){
  const html=liveRun();lastReview={id:d.id,episode:state.episode,html};return html;
 }
 if(['pictures','correcting','voicing','audio_mixing'].includes(d.state)&&lastReview?.id===d.id&&lastReview.episode===state.episode){
  return transformMarkup(lastReview.html,root=>{root.querySelectorAll('button:not([data-action=episode])').forEach(b=>b.disabled=true);root.querySelectorAll('[data-action^=life-]').forEach(b=>b.disabled=false)})+`<div class="live-work" role="status"><span class="live-dot"></span>${esc(d.phase)} · Deine Ansicht bleibt erhalten.</div>`;
 }
 return liveRun();
};
const conciseStory=storyOverview;
storyOverview=function(ep){return `<details class="optional story-check"><summary>Handlung prüfen<span>${ep.scenes.length} Szenen${ep.story_review?' · Dramaturgie geprüft':''}</span></summary><div class="body">${conciseStory(ep)}${ep.story_review?`<p><strong>Einstieg:</strong> ${esc(ep.story_review.hook)}</p><p><strong>Einsatz:</strong> ${esc(ep.story_review.stakes)}</p><p><strong>Wendung und Schluss:</strong> ${esc(ep.story_review.payoff)}</p>${ep.story_review.problems?.length?`<p class="note">Noch prüfen: ${ep.story_review.problems.map(esc).join(' · ')}</p>`:''}`:''}</div></details>`};
const studio11Quality=qualityFields;
qualityFields=function(d,scope,remix=false){
 let html=studio11Quality(d,scope,remix);
 if(!remix){html=html.replace('<option value="high"',`<option value="fast"${selected(d.quality,'fast')}>Schnell · 4 Schritte, Zusatzgewichte</option><option value="high"`);html+=`<label for="${scope}-lip_sync">Sprechende Figuren</label><select id="${scope}-lip_sync" data-production="lip_sync" data-scope="${scope}"><option value="audio"${selected(d.lip_sync||'audio','audio')}>Mit Ton gesteuerte Mundbewegungen</option><option value="off"${selected(d.lip_sync,'off')}>Nur Bildbewegung / Off-Kommentar</option></select><p class="muted">Schnell nutzt trainierte Beschleunigungsgewichte bei 720 × 1280. Sprechbilder nutzen dabei 576 × 1024. Bewegungsdetails können sich unterscheiden. Der 1080p-Export bleibt. Zuerst eine kurze Probe prüfen.</p><button type="button" class="small ghost" data-action="render-studio">Animation einrichten / prüfen</button>`}
 return html;
};
const oldProductionValues=productionValues;
productionValues=function(d,legacy=false){return {...oldProductionValues(d,legacy),lip_sync:d.lip_sync||'audio'}};
const studio11Mix=mixPreview;
mixPreview=function(d){return studio11Mix(d).replaceAll('Mundbewegungen sind weiterhin nicht verlässlich lippensynchron.','Sprechszenen erhalten die freigegebene Sprache als Modelleingabe. Die erste kurze Probe vor der vollständigen Produktion prüfen.');};
async function renderStudio(){const s=await api('/api/factory/render-studio/status');dialog(`<div class="dialog-head"><h2>Animation</h2><button class="small ghost" data-action="close">Schließen</button></div><p>Lokale Modelle · keine API-Gebühren</p>${s.checks.map(c=>`<div class="check-row"><strong>${c.ready?'✓':'○'} ${esc(c.name)}</strong><p>${esc(c.detail)}</p></div>`).join('')}<p>Einmalig kostenlose Modelle und die fehlende WanVideo-Erweiterung ergänzen. Bitte 60 GB frei halten. Danach ComfyUI neu starten und erneut prüfen. Vorhandene Erweiterungen werden nicht automatisch überschrieben.</p>${s.error?`<p class="note">${esc(s.error)}</p>`:''}${s.message?`<p class="note">${esc(s.message)}</p>`:''}<button class="small ghost" data-action="render-studio">Prüfung aktualisieren</button> <button class="primary" data-action="render-setup" ${s.running?'disabled':''}>${s.running?'Einrichtung läuft':'Animation einrichten'}</button>${s.log?`<pre>${esc(s.log)}</pre>`:''}`)}
document.addEventListener('click',async e=>{const b=e.target.closest('[data-action]');if(!['render-studio','render-setup'].includes(b?.dataset.action))return;e.preventDefault();e.stopImmediatePropagation();b.disabled=true;try{if(b.dataset.action==='render-setup')await post('/api/factory/render-studio/setup');await renderStudio()}catch(err){toast(err.message)}finally{if(b.isConnected)b.disabled=false}},true);

labels.sample_review='Produktionsprobe prüfen';
document.addEventListener('click',async e=>{const b=e.target.closest('[data-action]');if(!['sample-approve','sample-reject'].includes(b?.dataset.action))return;e.preventDefault();e.stopImmediatePropagation();if(state.busy)return;state.busy=true;try{await post('/api/factory/'+state.rid+'/'+(b.dataset.action==='sample-approve'?'approve-sample':'reject-sample'),{revision:state.run.revision});await refreshRun()}catch(err){toast(err.message)}finally{state.busy=false}},true);

const transcriptVoices=voiceTools;
voiceTools=function(d){return transcriptVoices(d)+`<details class="optional"><summary>Text der eigenen Stimmprobe<span>Verbessert die Qwen-Stimmübernahme</span></summary><div class="body">${(d.idea.participants||[]).filter(p=>p.voice).map((p,i)=>`<label>${esc(p.name)} · genau gesprochener Text<textarea rows="3" maxlength="2500" data-voice-transcript="${esc(p.name)}">${esc(p.voice_text||'')}</textarea></label><button class="small" data-action="save-transcript" data-name="${esc(p.name)}">Stimmprobe mit Text übernehmen</button>`).join('')||'<p>Nach dem Hochladen einer eigenen Stimmprobe kannst du ihren genauen Text ergänzen.</p>'}</div></details>`};
document.addEventListener('click',async e=>{const b=e.target.closest('[data-action=save-transcript]');if(!b)return;e.preventDefault();e.stopImmediatePropagation();const p=state.run.idea.participants.find(p=>p.name===b.dataset.name),input=[...document.querySelectorAll('[data-voice-transcript]')].find(n=>n.dataset.voiceTranscript===p.name);try{await post('/api/factory/'+state.rid+'/voice-reference',{name:p.name,asset_id:p.voice,voice_text:input.value});await refreshRun();toast('Referenztext gespeichert. Neue Tonvorschau prüfen.')}catch(err){toast(err.message)}},true);
