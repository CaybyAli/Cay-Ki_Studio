'use strict';
// Patch changed DOM nodes; keep media playback, focus, open panels and scroll position.
function domKey(node){
 if(node.nodeType!==1)return null;
 if(node.id)return 'id:'+node.id;
 if(node.dataset.liveKey)return 'key:'+node.dataset.liveKey;
 if(['IMG','AUDIO','VIDEO','SOURCE'].includes(node.tagName))return node.tagName+':'+node.getAttribute('src');
 return null;
}
function prepareKeys(root){
 const scope=state.page+':'+(state.rid||remixState?.job?.id||'')+':'+state.episode;
 for(const selector of ['.scene','.audio-card','.person','.episode-card'])root.querySelectorAll(selector).forEach((n,i)=>n.dataset.liveKey=scope+selector+i);
}
function patchNode(old,next){
 if(old.nodeType!==next.nodeType||old.nodeName!==next.nodeName){old.replaceWith(next);return}
 if(old.nodeType!==1){if(old.nodeValue!==next.nodeValue)old.nodeValue=next.nodeValue;return}
 const focused=document.activeElement===old,dirty=old.dataset.liveDirty==='true';
 for(const a of [...old.attributes])if(!next.hasAttribute(a.name)&&!['open','data-live-dirty'].includes(a.name))old.removeAttribute(a.name);
 for(const a of next.attributes){if((a.name==='value'||a.name==='checked')&&(focused||dirty))continue;if(old.getAttribute(a.name)!==a.value)old.setAttribute(a.name,a.value)}
 if(['AUDIO','VIDEO','IMG','INPUT'].includes(old.tagName))return;
 if(['TEXTAREA','SELECT'].includes(old.tagName)&&(focused||dirty))return;
 patchChildren(old,next);
}
function patchChildren(old,next){
 const keyed=new Map([...old.childNodes].map(n=>[domKey(n),n]).filter(([k])=>k));
 let cursor=old.firstChild;
 for(const wanted of [...next.childNodes]){
  const key=domKey(wanted);let match=key?keyed.get(key):cursor;
  if(match&&(!key&&domKey(match)||match.nodeType!==wanted.nodeType||match.nodeName!==wanted.nodeName))match=null;
  if(match){if(match!==cursor)old.insertBefore(match,cursor);patchNode(match,wanted);cursor=match.nextSibling;keyed.delete(key)}
  else{old.insertBefore(wanted,cursor)}
 }
 while(cursor){const after=cursor.nextSibling;cursor.remove();cursor=after}
}
function updateMain(html){
 const root=document.querySelector('#main'),next=document.createElement('template');next.innerHTML=html;prepareKeys(next.content);
 const context=state.page+':'+(state.page==='run'?state.rid:state.page==='remix-run'?remixState.job?.id:'');
 if(root.dataset.context!==context){root.replaceChildren(next.content);root.dataset.context=context;return}
 patchChildren(root,next.content);
}
document.addEventListener('input',e=>{if(e.target.matches('#main input:not([type=file]),#main textarea,#main select'))e.target.dataset.liveDirty='true'});
