'use strict';
labels.audio_mixing='Ton wird gemischt';labels.finishing='Schnitt & Export';
let sourceInfo=null,performanceLoading=false;
const systemForm=form,systemTop=topRun,systemDialog=dialog;
function sourceMarkup(text){
 const matches=[...text.matchAll(/^[ \t]*(?:#{1,6}[ \t]*)?(?:\*\*|__)?(?:Folge|Episode)[ \t]+(\d{1,2})\b[^\r\n]*/gim)];
 const numbers=matches.map(x=>Number(x[1]));const valid=numbers.every((n,i)=>n===i+1)&&numbers.length<=12;
 sourceInfo={count:matches.length,valid};
 return `<span>${text.length.toLocaleString('de-DE')} / 100.000 Zeichen</span>${matches.length?`<strong>${matches.length} Folgen erkannt</strong>${!valid?'<span class="source-warning">Nummerierung prüfen: fortlaufend ab Folge 1.</span>':matches.length!==state.draft.episodes?`<button type="button" class="small" data-action="source-count">${matches.length} Folgen übernehmen</button>`:'<span>✓ Folgenzahl passt</span>'}`:'<span>Grobe Idee oder vollständiges Drehbuch einfügen.</span>'}`;
}
form=function(){return transformMarkup(systemForm(),root=>{
 const input=root.querySelector('#idea');input.insertAdjacentHTML('afterend',`<div class="source-tools"><label class="source-upload" for="source-file">Drehbuch importieren <span>TXT / Markdown</span><input id="source-file" type="file" accept=".txt,.md,.markdown,text/plain,text/markdown"></label><div id="source-summary" class="source-summary" role="status">${sourceMarkup(state.draft.idea)}</div></div>`);
})};
topRun=function(d,stage){
 let html=systemTop(d,stage);const detected=d.source?.episodes?.length;
 html+=`<div class="source-project"><span>${detected?`${detected} Originalfolgen übernommen · `:''}${d.episodes.length} / ${d.idea.episodes} Drehbücher geplant</span><a href="/api/factory/${d.id}/source" download>Originaltext ↓</a><button class="small ghost" data-action="performance">Leistung & Laufzeiten</button>${d.state==='done'?'<button class="small" data-action="reopen-output">Ton & Export bearbeiten</button>':''}</div>`;
 if(d.cpu_jobs?.length)html+=`<div class="cpu-jobs">${d.cpu_jobs.filter(j=>!j.kind.startsWith('prepare:')||j.status==='running').map(j=>`<span class="tag">CPU · Folge ${j.episode+1} · ${j.kind==='mix'?'Tonmischung':j.kind.startsWith('prepare:')?'Abschnitt vorbereiten':'Export'} · ${esc({queued:'wartet',running:'läuft',failed:'Fehler'}[j.status]||j.status)}</span>`).join('')}</div>`;
 return html;
};
dialog=function(html){systemDialog(html);if(html.includes('Dein lokales Studio'))$('#dialog').insertAdjacentHTML('beforeend','<hr class="divider"><button data-action="performance">Leistung & Laufzeiten ansehen</button>')};
document.addEventListener('input',event=>{if(event.target.id==='idea'&&$('#source-summary'))$('#source-summary').innerHTML=sourceMarkup(event.target.value)});
document.addEventListener('change',async event=>{
 if(event.target.id==='episodes'&&$('#source-summary'))$('#source-summary').innerHTML=sourceMarkup(state.draft.idea);
 if(event.target.id!=='source-file')return;
 const file=event.target.files[0];if(!file)return;
 try{
  if(file.size>2*1024**2)throw Error('Die Textdatei darf höchstens 2 MB groß sein.');
  const text=new TextDecoder('utf-8',{fatal:true}).decode(await file.arrayBuffer());
  if(text.length>100000)throw Error('Das Drehbuch enthält mehr als 100.000 Zeichen. Bitte in mehrere Projekte aufteilen; es wurde nichts gekürzt.');
  if(text.includes('\0')||text.trim().length<12)throw Error('Bitte eine lesbare TXT- oder Markdown-Datei in UTF-8 auswählen.');
  state.draft.idea=text;saveIdea();render();toast('Originaltext vollständig übernommen. Erkannte Folgenzahl prüfen.');
 }catch(error){toast(error.message)}
});
function formatSeconds(seconds){return seconds>=60?(seconds/60).toFixed(1)+' min':seconds.toFixed(1)+' s'}
async function refreshPerformance(){
 if(!$('#performance-body')||performanceLoading)return;performanceLoading=true;
 try{
  const project=state.page==='run'?state.rid:state.page==='remix-run'?remixState.job?.id:null;
  const [data,status]=await Promise.all([api('/api/system/performance'+(project?'?project='+encodeURIComponent(project):'')),api('/api/status')]);
  if(!$('#performance-body'))return;
  const sys=data.system||{},mem=sys.memory||{},gpu=status.system?.gpu||status.gpu||{};
  const gb=value=>value==null?'—':(value/1024**3).toFixed(1)+' GB';
  $('#performance-body').innerHTML=memorySummary(sys,gpu)+`<div class="performance-grid"><article><small>Grafikkarte</small><strong>${gpu.utilization==null?'—':gpu.utilization+' %'}</strong><span>${esc(gpu.name||'Werte werden abgefragt')}</span><span>${gpu.used_mib==null?'':(gpu.used_mib/1024).toFixed(1)+' / '+(gpu.total_mib/1024).toFixed(1)+' GB VRAM'}</span></article><article><small>Prozessor · WSL/Linux</small><strong>${sys.cpu_percent==null?'—':sys.cpu_percent+' %'}</strong><span>${sys.cpu_options?.threads||'—'} Encoderthreads · ${sys.cpu_options?.filter_threads||'—'} Filterthreads</span></article><article><small>Verfügbarer RAM · WSL/Linux</small><strong>${gb(mem.available)}</strong><span>Von ${gb(mem.total)} in WSL</span></article><article><small>Auslagerung · WSL/Linux</small><strong>${gb(mem.swap_used)}</strong><span>${sys.swap_pages_in_per_second??'—'} Seiten/s gelesen · ${sys.swap_pages_out_per_second??'—'} geschrieben</span></article></div><p class="muted">Windows-Speicher ist darin nicht vollständig enthalten. Ein niedriger freier Wert während des Renderns allein beweist keinen Engpass.</p><div class="cpu-jobs">${[...(sys.cpu_active||[]),...(sys.cpu_waiting||[])].map(j=>`<span class="tag">CPU · ${esc(j.stage)}${j.reason?' · '+esc(j.reason):''}</span>`).join('')||'<span>Aktuell keine CPU-Nachbearbeitung.</span>'}</div><div class="performance-table"><table><thead><tr><th>Arbeitsschritt</th><th>Ressource</th><th>Aufrufe</th><th>Gemessene Zeit</th></tr></thead><tbody>${data.stages.map(s=>`<tr><td>${esc(s.stage)}${s.status==='partial'?' · Teilantwort':s.status==='interrupted'?' · unterbrochen':''}</td><td>${s.resource==='cache'?'Wiederverwendet':esc(s.resource)}</td><td>${s.calls}</td><td>${formatSeconds(s.seconds||0)}</td></tr>`).join('')||'<tr><td colspan="4">Messwerte entstehen beim nächsten Auftrag.</td></tr>'}</tbody></table></div><p class="muted">${esc(data.note)}</p>`;
 }catch(error){if($('#performance-body'))$('#performance-body').textContent=error.message}
 finally{performanceLoading=false}
}
document.addEventListener('click',async event=>{
 const button=event.target.closest('[data-action]');const action=button?.dataset.action;
 if(!['source-count','performance','reopen-output'].includes(action))return;
 event.preventDefault();event.stopImmediatePropagation();
 if(action==='source-count'&&sourceInfo?.valid){state.draft.episodes=sourceInfo.count;saveIdea();render();return}
 if(action==='performance'){dialog('<div class="dialog-head"><h2>Leistung & Laufzeiten</h2><button class="small ghost" data-action="close">Schließen</button></div><p>Animation auf der GPU, Nachbearbeitung auf der CPU. Messwerte werden während der Arbeit aktualisiert.</p><div id="performance-body" role="status">Werte werden geladen …</div>');await refreshPerformance();return}
 if(action==='reopen-output'){
  if(state.busy)return;state.busy=true;button.disabled=true;
  try{state.run=await post('/api/factory/'+state.rid+'/reopen-output',{revision:state.run.revision});render();toast('Ton und Export können bearbeitet werden. Die bisherige Filmfassung bleibt gespeichert.')}catch(error){toast(error.message)}finally{state.busy=false;if(button.isConnected)button.disabled=false}
 }
},true);
setInterval(refreshPerformance,5000);
