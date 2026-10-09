"""One frame-based timing policy from script estimate to approved audio and export."""
import math

FPS = 25
POLICY = 3

def scene_lines(scene):
    return scene.get('dialogues') or ([{'speaker':scene.get('speaker',''), 'text':scene['dialogue'],
        'pause_after':.18}] if scene.get('dialogue') else [])

def distribute_frames(base, minimum, weights, fps=FPS):
    if fps not in (25,30):raise ValueError('25 oder 30 FPS wählen.')
    frames=[max(1,math.ceil(float(seconds)*fps-1e-8)) for seconds in base]
    missing=max(0,math.ceil(float(minimum)*fps-1e-8)-sum(frames))
    if missing and frames:
        weights=[max(.01,float(w)) for w in weights]
        shares=[missing*w/sum(weights) for w in weights]
        extra=[math.floor(v) for v in shares]
        for i in sorted(range(len(extra)),key=lambda i:shares[i]-extra[i],reverse=True)[:missing-sum(extra)]:extra[i]+=1
        frames=[n+a for n,a in zip(frames,extra)]
    return [n/fps for n in frames]

def plan_seconds(episode, minimum, fps=FPS):
    """Long dialogue scenes get their own budget; no words are cut or sped up."""
    scenes=episode['scenes'];base=[]
    for scene in scenes:
        lines=scene_lines(scene)
        words=sum(len(line['text'].split()) for line in lines)
        base.append(max(3.,words/2.25+sum(float(x.get('pause_after',.18)) for x in lines)+.7) if lines else 4.)
    times=distribute_frames(base,minimum,base,fps)
    for scene,seconds in zip(scenes,times):scene['seconds']=seconds
    episode['minimum_seconds']=minimum
    episode['estimated_seconds']=round(sum(times),2)
    return times

def audio_layout(episodes, lines, minimum_seconds=None, fps=FPS):
    """Schedule measured speech, retain natural pauses, fill target with moving action."""
    reports=[]
    for ei,episode in enumerate(episodes):
        scenes=episode['scenes'];groups=[];base=[]
        for si,scene in enumerate(scenes):
            group=sorted([line for line in lines if line['episode']==ei and line['scene']==si],key=lambda x:x.get('turn',0))
            groups.append(group)
            base.append(max(2.5,.12+sum(float(x['duration'])+float(x.get('pause_after',.18)) for x in group)+.22) if group else max(2.5,float(scene.get('seconds',4))))
        target=float(minimum_seconds if minimum_seconds is not None else episode.get('minimum_seconds',0))
        rich=episode.get('dialogue_mode')=='rich' and any(groups)
        if rich:
            base=[seconds if group else 2.5 for seconds,group in zip(base,groups)]
        weights=[sum(float(l['duration']) for l in group) if group else .01 for group in groups] if rich else [scene.get('seconds',4) for scene in scenes]
        times=distribute_frames(base,target,weights,fps)
        cursor=0.;speech=0.;intervals=[]
        for scene,group,seconds,natural in zip(scenes,groups,times,base):
            spare=max(0,seconds-natural)
            # Small reaction beats inside a conversation, then actual animated action.
            reaction=0. if rich else min(.35,spare/max(1,len(group))) if group else 0.
            local=.12+spare/2 if rich and group else .12
            for line in group:
                line['offset']=round(local,4);line['timeline_start']=round(cursor+local,4)
                duration=float(line['duration']);intervals.append((cursor+local,cursor+local+duration));speech+=duration
                local+=duration+float(line.get('pause_after',.18))+reaction
            scene.update(render_seconds=seconds,timeline_start=round(cursor,4),action_seconds=round(max(0,seconds-(sum(x['duration'] for x in group))),2))
            cursor+=seconds
        previous=0.;longest=0.
        for start,end in intervals:longest=max(longest,start-previous);previous=end
        reports.append({'seconds':round(cursor,2),'speech_seconds':round(speech,2),
            'speech_share':round(speech/cursor,3) if cursor else 0,
            'longest_speech_gap':round(max(longest,cursor-previous),2),'target_seconds':target,
            'minimum_met':cursor+1e-7>=target,'timing_policy':POLICY,'fps':fps})
    return reports
