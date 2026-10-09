'use strict';
// Focus each screen on the next useful action. Diagnostics stay expandable.
let animationPolling=false;
let voiceReadAt=0,voiceReading=false,voiceSnapshot=null;
const twelveVoicePanel=voiceStudioPanel;
function voiceSummary(r){return r?.dialogue_ready?'Qwen-Dialoge sind eingerichtet.':r?.state==='running'?'Stimmen werden eingerichtet. Diese Anzeige aktualisiert sich automatisch.':r?.message||'Stimmenstatus wird geprüft …'}
voiceStudioPanel=function(){return transformMarkup(twelveVoicePanel(),root=>{
 const text=root.querySelector('.voice-setup-status');if(text)text.textContent=voiceSummary(voiceSnapshot);
 const button=root.querySelector('[data-action=upgrade-voices]');if(button&&voiceSnapshot?.dialogue_ready){button.disabled=true;button.textContent='Qwen-Dialoge bereit'}
})};
voiceStatus=async function(){
 if(voiceReading)return;voiceReading=true;
 try{const r=await api('/api/factory/voice-studio/status');voiceSnapshot=r;voiceReadAt=Date.now();state.voiceSetupRunning=r.state==='running';
 document.querySelectorAll('.voice-setup-status').forEach(el=>el.textContent=voiceSummary(r));
 document.querySelectorAll('[data-action=upgrade-voices]').forEach(b=>{b.disabled=state.voiceSetupRunning||r.dialogue_ready;b.textContent=r.dialogue_ready?'Qwen-Dialoge bereit':state.voiceSetupRunning?'Wird eingerichtet …':'Qwen-Dialoge einrichten'});
 }finally{voiceReading=false}
};
setInterval(()=>{if(!document.hidden&&$('.voice-setup-status')&&Date.now()-voiceReadAt>15000)voiceStatus().catch(()=>{voiceReadAt=Date.now()})},1500);
function animationPanel(s){
 const ready=s.checks?.length&&s.checks.every(c=>c.ready);
 const title=s.running?'Einrichtung läuft':ready?'Animation ist bereit':s.state==='restart_required'?'Einrichtung abgeschlossen':'Animation vorbereiten';
 const next=s.running?'Der PC lädt und installiert die benötigten Komponenten. Du kannst dieses Fenster schließen; der PC muss eingeschaltet bleiben.':ready?'Wähle für den ersten Film „Schnell“ und prüfe anschließend die kurze Produktionsprobe.':s.state==='restart_required'?'Pausiere laufende Produktionen. Starte danach den PC neu und öffne Cay Studio mit der Startdatei.':'Einmal auf „Fehlende Komponenten einrichten“ klicken. Vorhandene Modelle bleiben erhalten.';
 return `<section id="animation-panel"><div class="dialog-head"><h2>${title}</h2><button class="small ghost" data-action="close">Schließen</button></div><p class="next-step" role="status">${next}</p>${s.running?'<div class="setup-working"><span class="live-dot"></span>Die Anzeige aktualisiert sich automatisch.</div>':''}<div class="setup-checklist">${(s.checks||[]).map(c=>`<div class="check-row"><strong>${c.ready?'✓':'○'} ${esc(c.name)}</strong>${c.ready?'':`<details><summary>Details</summary><p>${esc(c.detail)}</p></details>`}</div>`).join('')}</div>${s.error?`<p class="note">${esc(s.error)}</p>`:''}${s.message?`<p>${esc(s.message)}</p>`:''}<div class="row"><button class="small ghost" data-action="render-studio">Erneut prüfen</button>${!ready&&s.state!=='restart_required'?`<button class="primary" data-action="render-setup" ${s.running?'disabled':''}>${s.running?'Wird eingerichtet …':'Fehlende Komponenten einrichten'}</button>`:''}</div>${!ready&&!s.running?'<p class="muted">Für eine vollständige Ersteinrichtung bitte 60 GB frei halten. Keine Abo- oder API-Gebühren.</p>':''}${s.log?`<details id="animation-log" class="setup-log"><summary>Installationsprotokoll</summary><pre>${esc(s.log)}</pre></details>`:''}</section>`;
}
renderStudio=async function(){
 const s=await api('/api/factory/render-studio/status');
 const current=$('#animation-panel');
 if(current){const template=document.createElement('template');template.innerHTML=animationPanel(s);patchNode(current,template.content.firstElementChild)}
 else dialog(animationPanel(s));
};
setInterval(async()=>{
 if(animationPolling||!$('#dialog')?.open||!$('#animation-panel')||document.hidden)return;
 animationPolling=true;try{await renderStudio()}catch(error){const p=$('#animation-panel .next-step');if(p)p.textContent='Verbindung kurz unterbrochen. Die gespeicherte Einrichtung wird beim nächsten Abruf erneut geprüft.'}finally{animationPolling=false}
},4000);

const repairBaseRun=runView;
runView=function(){
 const d=state.run;
 if(d?.state==='blocked'&&d.resume_state==='planning'&&/KI-Planung|Handlung|Anschluss|payoff|beat=/.test(d.error||''))
  return topRun(d,0)+`<section class="repair-card"><p class="section-kicker">Dein nächster Schritt</p><h2>Die Planung kann fortgesetzt werden.</h2><p>Die automatische Szenenkorrektur wurde verbessert. Starte sie hier erneut; deine Idee und die gespeicherte Planung bleiben erhalten.</p><button class="primary" data-action="resume">Planung fortsetzen</button><details><summary>Technische Details</summary><p>${esc(d.error)}</p></details></section>`;
 return repairBaseRun();
};
const nextBaseForm=form;
form=function(){return transformMarkup(nextBaseForm(),root=>{
 const row=root.querySelector('.start-row');
 if(row)row.insertAdjacentHTML('beforebegin','<aside class="next-step compact"><strong>Zum ersten Film</strong><span>Idee eingeben → Bilder und Ton prüfen → kurze Produktionsprobe freigeben.</span><button type="button" class="small ghost" data-action="render-studio">Einrichtung prüfen</button></aside>');
})};

const twelveRemixSetup=remixSetup;
remixSetup=function(){const s=remixState.status;return transformMarkup(twelveRemixSetup(),root=>{
 const text=root.querySelector('.remix-setup>div>p');
 if(text&&!s?.message)text.textContent='Das Update ergänzt eine lokale Figurenprüfung (rund 0,8 GB). Bei bereits eingerichtetem Figurenstudio 3 GB frei halten; für eine komplette Ersteinrichtung 32 GB. Keine laufenden Gebühren.';
 const button=root.querySelector('[data-action=remix-setup]');if(button)button.textContent='Figurenstudio ergänzen';
})};
const twelveRemixList=remixList;
remixList=function(){return twelveRemixList().replaceAll('>quality_review<','>Figur prüfen<').replaceAll('>result_review<','>Ergebnis prüfen<').replaceAll('>awaiting_setup<','>Einrichtung ergänzen<')};
const twelveRemixRun=remixRun;
remixRun=function(){
 const d=remixState.job;if(!d)return twelveRemixRun();
 const top=`<div class="project-title"><div><p class="eyebrow">FIGURENTAUSCH</p><h1>${esc(d.title)}</h1></div><button class="small ghost" data-nav="remix">Alle Bearbeitungen</button></div>`;
 if(d.state==='mask_review'){
  const targets=d.request.targets?.length?d.request.targets:[d.request];
  return top+`<section class="next-step"><strong>Ist es überall dieselbe Ersatzfigur?</strong><p>Prüfe die Figurenbilder von Anfang bis Ende. Diese Bilder führen anschließend die Animation.</p></section>`+targets.map((t,i)=>{
   const work=d.request.targets?.length?d.target_work?.[i]:d,q=d.request.targets?.length?'?target='+i:'?';
   return `<section class="target-review"><h2>Punkt ${i+1} → Bild ${i+1}</h2><div class="identity-strip">${(work?.identity_anchors||[]).map(a=>`<figure><img loading="lazy" src="/api/remix/${d.id}/preview/keyframe${q}&frame=${a.frame}" alt="Figur ${i+1} bei ${a.seconds.toFixed(2)} Sekunden"><figcaption>${a.seconds.toFixed(2)} s</figcaption></figure>`).join('')}</div><details class="mask-details"><summary>Markierung über den Verlauf prüfen</summary><video controls playsinline preload="none" src="/api/remix/${d.id}/preview/mask${q}"></video></details></section>`;
  }).join('')+`<div class="bottom-action"><button class="ghost" data-action="remix-copy">Auswahl ändern</button><button class="primary" data-action="remix-approve">Figurenbilder passen · Animieren</button></div>`;
 }
 if(d.state==='quality_review'){
  const index=d.quality_target,work=index===undefined?d:d.target_work?.[index],issue=work?.quality_issue,q=index===undefined?'':'?target='+index;
  const times=issue?.report?.suspect_seconds||[];
  return top+`<section class="repair-card"><p class="section-kicker">Qualitätskontrolle</p><h2>Die Ersatzfigur verändert sich möglicherweise.</h2><p>Der betroffene Abschnitt wurde einmal automatisch wiederholt. Die weitere Produktion wartet, damit kein offensichtlich misslungener Film als fertig erscheint.</p>${times.length?`<p>Auffällig bei: ${times.slice(0,8).map(t=>t.toFixed(2)+' s').join(' · ')} im gewählten Ausschnitt.</p>`:''}<video class="quality-preview" controls playsinline preload="metadata" src="/api/remix/${d.id}/preview/quality${q}"></video><div class="row"><button class="primary" data-remix-review="retry-quality">Diesen Abschnitt neu versuchen</button><button class="ghost" data-action="remix-copy">Figur oder Auswahl ändern</button></div><p class="muted">Die automatische Prüfung ist eine Hilfe und kann sich irren. Sie bewertet keine perfekte Gesichtsidentität.</p></section>`;
 }
 if(d.state==='result_review'){
  const work=d.target_work||[d];const warnings=work.flatMap(w=>{const r=w.final_composite_check||w.final_identity_check;return r?.status==='review'?r.suspect_seconds:[]});
  return top+`<section class="sample-check"><p class="section-kicker">Letzter Schritt</p><h2>Bleibt deine Figur bis zum Schluss erhalten?</h2><p>Sieh dir den ganzen Clip an. Prüfe besonders Gesicht, Fell, schnelle Bewegungen und Übergänge.</p>${warnings.length?`<p class="note">Die automatische Prüfung sieht mögliche Abweichungen bei ${[...new Set(warnings)].slice(0,8).map(t=>t.toFixed(2)+' s').join(', ')}. Bitte genau ansehen.</p>`:''}<video controls playsinline preload="metadata" src="/api/remix/${d.id}/preview/export"></video><div class="row"><button class="primary" data-remix-review="approve-result">Video passt · Als fertig speichern</button><button class="ghost" data-action="remix-copy">Figur oder Auswahl ändern</button></div></section>`;
 }
 if(['tracking','rendering','finishing'].includes(d.state)){
  const list=d.target_work||[d],total=list.reduce((n,w)=>n+Math.ceil((w.tracking?.frames||d.request.seconds*16)/32),0),done=list.reduce((n,w)=>n+(w.clips?.length||0),0);
  return transformMarkup(twelveRemixRun(),root=>{const p=root.querySelector('.status-panel');if(p)p.insertAdjacentHTML('beforeend',`<div class="remix-meter"><span>${done} von ${total} Abschnitten geprüft</span><progress max="${Math.max(total,1)}" value="${done}"></progress><small>Figurenbilder → Animation → Figurenprüfung → Deine Freigabe</small></div>`)});
 }
 return twelveRemixRun();
};
document.addEventListener('click',async e=>{
 const b=e.target.closest('[data-remix-review]');if(!b)return;e.preventDefault();e.stopImmediatePropagation();if(remixState.busy)return;
 remixState.busy=true;b.disabled=true;
 try{remixState.job=await post('/api/remix/'+remixState.job.id+'/'+b.dataset.remixReview,{revision:remixState.job.revision});remixState.signature=remixState.job.revision;render()}catch(error){toast(error.message)}finally{remixState.busy=false;if(b.isConnected)b.disabled=false}
},true);
