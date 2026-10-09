"""Preserve the exception, not just the final 1,500 characters of a traceback."""
import json

def report(status,graph=None,prompt_id=None):
    graph=graph or {};events=[]
    for item in status.get('messages',[]):
        if isinstance(item,(list,tuple)) and len(item)>=2 and item[0] in ('execution_error','execution_interrupted') and isinstance(item[1],dict):events.append(item[1])
    event=events[-1] if events else {};node_id=str(event.get('node_id',''))
    trace=event.get('traceback',[])
    if isinstance(trace,str):trace=[trace]
    return {'prompt_id':prompt_id or event.get('prompt_id'),'node_id':node_id,
            'node_type':event.get('node_type') or graph.get(node_id,{}).get('class_type'),
            'exception_type':event.get('exception_type',''),
            'exception_message':event.get('exception_message',''),
            'traceback':trace,'status':status,
            'models':[{k:n.get('inputs',{}).get(k) for k in ('clip_name','type','device','unet_name','vae_name') if k in n.get('inputs',{})}|{'node_id':key,'node_type':n.get('class_type')} for key,n in graph.items() if n.get('class_type') in ('CLIPLoader','UNETLoader','VAELoader')]}

def summary(detail):
    message=str(detail.get('exception_message') or '').strip();kind=detail.get('exception_type') or 'Ausführung fehlgeschlagen'
    node=detail.get('node_type') or detail.get('node_id') or 'Workflow'
    if not message:
        trace=detail.get('traceback') or []
        message=str(trace[-1]).strip() if trace else 'ComfyUI hat keine genaue Ausnahme geliefert. Gespeicherten Diagnosebericht öffnen.'
    return f'ComfyUI · {node} · {kind}: {message[:1200]}'
