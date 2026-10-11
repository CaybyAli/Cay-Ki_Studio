'use strict';
labels.blocked='Fehler · angehalten';
labels.sample_review='Produktionsprobe freigeben';
const thirteenRun=runView,thirteenMix=mixPreview,thirteenProduction=productionMarkup;
function memorySummary(sys={},gpu={}){
 const gb=n=>Number.isFinite(n)?(n/1024**3).toFixed(1)+' GB':'—';
 const mem=sys.memory||{},host=sys.host_memory||{};
 return `<section class="resource-summary" aria-label="Aktuelle Auslastung"><div class="resource-readings"><span><small>GPU · Rechenauslastung</small><strong>${gpu.utilization==null?'—':esc(gpu.utilization)+' %'}</strong></span><span><small>CPU · WSL</small><strong>${sys.cpu_percent==null?'—':esc(sys.cpu_percent)+' %'}</strong></span><span><small>RAM frei · Windows</small><strong>${gb(host.available)}</strong></span><span><small>RAM frei · WSL</small><strong>${gb(mem.available)}</strong></span></div>${(sys.warnings||[]).map(s=>`<p class="memory-warning" role="status">${esc(s)}</p>`).join('')}<p class="muted">CPU und GPU arbeiten je nach Schritt unterschiedlich stark. Beide müssen nicht gleichzeitig bei 100 % liegen.${host.total?'':' Windows-Werte sind noch nicht verfügbar.'}</p>${(sys.cpu_waiting||[]).filter(x=>x.reason).map(x=>`<p class="memory-warning">${esc(x.stage)}: ${esc(x.reason)}</p>`).join('')}</section>`;
}
productionMarkup=function(p,d){return thirteenProduction(p,d)+memorySummary(p.resources,p.gpu)};
runView=function(){
 const d=state.run;let html=thirteenRun();
 if(!d||d.deleted)return html;
 if(d.state==='blocked'&&['planning','voicing','rendering','finishing','audio_mixing'].includes(d.resume_state)){
  const sampler=/WanVideoSampler|NoneType|CayWanVideoSampler/.test(d.error||''),speech=/SPRACHPRÜFUNG/.test(d.error||''),silent=/DIALOG FEHLT/.test(d.error||'');
  html=transformMarkup(html,root=>{
   const oldError=root.querySelector('.error');
   root.querySelector('[data-action=upgrade-voices]')?.closest('.note')?.remove();
   root.querySelector('[data-action=setup-voices]')?.closest('.note')?.remove();
   root.querySelectorAll('[data-action=diagnosis]').forEach(el=>el.remove());
   const panel=document.createElement('section');panel.className='repair-card render-repair';
   panel.innerHTML=`<p class="section-kicker">DEIN NÄCHSTER SCHRITT</p><h2>Die Produktion wurde angehalten.</h2><p>${silent?'Das Drehbuch enthält keine gesprochenen Dialoge. So entstünde ein stummer Film. Es wurde noch keine Rechenzeit für Animation verbraucht.':speech?'Einige Dialogbeiträge sind stumm oder nicht hörbar. Darunter steht, welche Folge, Szene und Figur betroffen ist. „Produktion fortsetzen“ spricht nur diese Beiträge neu ein; danach die neue Tonvorschau anhören.':sampler?'Nach dem Update den PC einmal neu starten und Cay Studio öffnen. Danach hier auf „Produktion fortsetzen“ klicken.':'Der Fehler steht hier direkt unter dem Hinweis. Behebe die genannte Ursache und setze die Produktion fort.'}</p><pre class="visible-error">${esc(d.error||d.phase||'Noch keine Fehlerdetails verfügbar.')}</pre><div class="repair-actions">${silent&&d.resume_state==='voicing'?'<button class="primary" data-action="new-edition">Neue Fassung planen</button>':`<button class="primary" data-action="resume">${d.resume_state==='planning'?'Folge neu planen':'Produktion fortsetzen'}</button>`}${d.previews?.length?'<button class="ghost" data-action="reopen-voices">Dialoge & Ton bearbeiten</button>':''}<a href="/api/factory/${d.id}/diagnostics/download" download>Fehlerbericht speichern ↓</a></div><p class="muted">Fertige Abschnitte bleiben gespeichert. Falls derselbe Fehler wiederkommt, den Fehlerbericht mitgeben.</p>`;
   const before=root.querySelector('.production-center');if(oldError)oldError.replaceWith(panel);else if(before)before.before(panel);else root.prepend(panel);
  });
 }
 return html;
};
mixPreview=function(d){
 const t=d.timing?.[state.episode],seconds=t?.seconds||0,share=Math.max(0,Math.min(1,t?.speech_share||0));
 const hasSpeech=d.plan?.cast?.length&&d.idea.characters!=='none';
 return thirteenMix(d)+`<section class="dialogue-summary"><div><h3>Dialoge & Sprechpausen</h3>${t?`<p><strong>${(seconds*share).toFixed(1)} s Sprache</strong> · ${(seconds*(1-share)).toFixed(1)} s Sprechpausen · längste Pause ${(t.longest_speech_gap||0).toFixed(1)} s</p>`:'<p>Nach der Tonerzeugung erscheint hier die gemessene Aufteilung.</p>'}${hasSpeech&&t&&(share<.8||t.longest_speech_gap>3.5)?'<p class="memory-warning">Diese Folge enthält längere Sprechpausen. Lass passende Reaktionen ergänzen und höre die neue Mischung an.</p>':''}<p class="muted">Ergänzt nur die ausgewählte Folge. Szenenbilder und vorhandene Dialoge bleiben erhalten. Neue Sprache braucht anschließend eine neue Produktionsfreigabe.</p></div>${hasSpeech?'<button class="small" data-action="correction-dialogue">Dialoge ergänzen</button>':''}</section>`;
};
document.addEventListener('click',async event=>{
 const b=event.target.closest('[data-action="reopen-voices"]');if(!b)return;
 event.preventDefault();event.stopImmediatePropagation();if(state.busy)return;state.busy=true;b.disabled=true;
 try{const rid=state.rid,epoch=state.navigationEpoch;await post('/api/factory/'+rid+'/reopen-voices',{revision:state.run.revision});if(epoch===state.navigationEpoch&&state.rid===rid){await refreshRun();toast('Tonvorschau geöffnet. Bei Bedarf auf „Dialoge ergänzen“ klicken.')}}catch(e){toast(e.message)}finally{state.busy=false;if(b.isConnected)b.disabled=false}
},true);
