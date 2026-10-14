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

TALK_FPS = 25
HEAD = .08      # speech starts almost on the cut
TAIL = .15      # short breath after the last word, then the next shot
FREE_CAP = 1.0  # at most this much extra action after the words of one shot
MARGIN = .1     # stay clear of the next lip-sync window after frame rounding

def talk_windows(seconds):
    """Lip-sync windows for one prompt: 81 frames first, then 72 new frames each.
    Frame count as in render_studio.audio_graph."""
    frames=4*math.ceil(seconds*TALK_FPS/4-1e-9)+1
    return 1+max(0,math.ceil((frames-81)/72))

def talk_window_seconds(seconds):
    """Seconds the lip-sync model computes anyway for this shot (3.2, 6.08, 8.96 …)."""
    return (80+72*(talk_windows(seconds)-1))/TALK_FPS

def fill_target(base, talking, target, weights):
    """Reach the minimum length without dead air.

    1) Seconds the lip-sync model computes anyway (rest of its last window),
       at most FREE_CAP per shot. 2) Silent action scenes. 3) Only if none
       exist, speaking scenes by their speech share.
    """
    times=list(base);missing=float(target)-sum(times)
    for i in sorted([i for i,t in enumerate(talking) if t],key=lambda i:talk_window_seconds(times[i])-times[i],reverse=True):
        if missing<=0:break
        free=max(0.,min(FREE_CAP,talk_window_seconds(times[i])-times[i]-MARGIN))
        take=min(free,missing);times[i]+=take;missing-=take
    if missing>0:
        silent=[i for i,t in enumerate(talking) if not t]
        pool=silent or list(range(len(times)))
        share=[max(.01,float(weights[i])) for i in pool]
        for i,w in zip(pool,share):times[i]+=missing*w/sum(share)
    return times

def audio_layout(episodes, lines, minimum_seconds=None, fps=FPS):
    """Speech starts on the cut; extra time becomes action, never a pause before the words."""
    reports=[]
    for ei,episode in enumerate(episodes):
        scenes=episode['scenes'];groups=[];base=[]
        for si,scene in enumerate(scenes):
            group=sorted([line for line in lines if line['episode']==ei and line['scene']==si],key=lambda x:x.get('turn',0))
            groups.append(group)
            base.append(max(1.8,HEAD+sum(float(x['duration'])+float(x.get('pause_after',.18)) for x in group)+TAIL) if group else max(2.5,float(scene.get('seconds',4))))
        target=float(minimum_seconds if minimum_seconds is not None else episode.get('minimum_seconds',0))
        rich=episode.get('dialogue_mode')=='rich' and any(groups)
        if rich:
            base=[seconds if group else 2.5 for seconds,group in zip(base,groups)]
        weights=[scene.get('seconds',4) if not group else sum(float(l['duration']) for l in group) for scene,group in zip(scenes,groups)]
        planned=fill_target(base,[bool(g) for g in groups],target,weights)
        # Whole frames; rounding only ever adds, the minimum stays met.
        times=distribute_frames(planned,target,weights,fps)
        cursor=0.;speech=0.;intervals=[]
        for scene,group,seconds,natural in zip(scenes,groups,times,base):
            spare=max(0,seconds-natural)
            # Older plain scripts keep a small reaction beat between lines.
            reaction=0. if rich else min(.35,spare/max(1,len(group))) if group else 0.
            local=HEAD
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
            'minimum_met':cursor+1e-7>=target,'timing_policy':POLICY,'fps':fps,
            'talk_windows':sum(talk_windows(t) for t,g in zip(times,groups) if g)})
    return reports
