/* Apply before styles/paint. Never depend on storage being available. */
(()=>{
  let preference='system';try{preference=localStorage.getItem('cay.studio.theme')||'system'}catch{}
  const system=matchMedia('(prefers-color-scheme: dark)');
  function apply(){const dark=preference==='dark'||(preference==='system'&&system.matches);document.documentElement.dataset.theme=dark?'dark':'light';document.documentElement.style.colorScheme=dark?'dark':'light';const b=document.querySelector('[data-action="theme"]');if(b){b.textContent=dark?'☀':'☾';b.setAttribute('aria-label',dark?'Hellen Modus aktivieren':'Dunklen Modus aktivieren');b.title=b.getAttribute('aria-label')}}
  window.cayTheme={get:()=>preference,set(value){preference=['system','light','dark'].includes(value)?value:'system';try{localStorage.setItem('cay.studio.theme',preference)}catch{}apply()}};
  apply();system.addEventListener('change',apply);document.addEventListener('DOMContentLoaded',apply);
  document.addEventListener('click',event=>{if(!event.target.closest('[data-action="theme"]'))return;event.stopImmediatePropagation();window.cayTheme.set(document.documentElement.dataset.theme==='dark'?'light':'dark')},true);
  document.addEventListener('change',event=>{if(event.target.id==='theme-choice')window.cayTheme.set(event.target.value)});
})();
