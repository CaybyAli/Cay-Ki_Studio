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
TAIL = .25      # breath after the last word, then the next shot
TALK_TAIL_MAX = .35  # extra silence a lip-sync shot may get; the model moves mouths in silence
MARGIN = .1     # stay clear of the next lip-sync window after frame rounding
SNAP = .3       # a shot this little over a window limit is tightened instead of paying a window
MIN_PAUSE = .06
TALK_SEGMENT_SECONDS = 15   # studio_quality_policy.TALK_SEGMENT: longer talking shots are split

def rendered_windows(seconds, fps=FPS):
    """Windows the lip-sync model really computes for one talking shot (split over 15 s)."""
    from studio_quality_policy import scene_segments
    return sum(talk_windows(x) for x in scene_segments(seconds, fps, True))

def talk_windows(seconds):
    """Lip-sync windows for one prompt: 81 frames first, then 72 new frames each.
    Frame count as in render_studio.audio_graph."""
    frames=4*math.ceil(seconds*TALK_FPS/4-1e-9)+1
    return 1+max(0,math.ceil((frames-81)/72))

def window_capacity(windows):
    return (80+72*(max(1,windows)-1))/TALK_FPS

def talk_window_seconds(seconds):
    """Seconds the lip-sync model computes anyway for this shot (3.2, 6.08, 8.96 …)."""
    return window_capacity(talk_windows(seconds))

def talk_plan(group):
    """Natural length of a speaking shot and the pauses it uses.

    No pause after the last line (TAIL covers the breath). If the shot ends just
    over a lip-sync window limit, pauses, head and tail shrink so it fits: a
    window costs ~3.4 min on Cay's PC (0.16.1 paid 5 windows for 3 s of silence)."""
    durations=[float(x['duration']) for x in group]
    pauses=[float(x.get('pause_after',.18)) for x in group[:-1]]+[0.]
    head,tail=HEAD,TAIL
    natural=head+sum(durations)+sum(pauses)+tail
    # Frame rounding can add up to MARGIN: decide with it, so 8.93 s is not
    # rounded to 8.96 s and charged a fourth window.
    windows=talk_windows(natural+MARGIN)
    limit=window_capacity(windows-1)-MARGIN if windows>1 else 0
    if natural>window_capacity(windows)-MARGIN:limit=window_capacity(windows)-MARGIN
    if limit:
        slack=sum(max(0,p-MIN_PAUSE) for p in pauses)+(head-.04)+(tail-.12)
        if natural-limit<=SNAP and natural-slack<=limit:
            need=natural-limit;scale=need/slack if slack else 0
            pauses=[p-max(0,p-MIN_PAUSE)*scale for p in pauses];head-=(head-.04)*scale;tail-=(tail-.12)*scale
            natural=head+sum(durations)+sum(pauses)+tail
    return {'seconds':max(1.4,natural),'head':head,'pauses':pauses,'tail':tail}

def fill_target(base, talking, target, weights):
    """Reach the minimum length without dead air in lip-sync shots.

    1) Speaking shots get at most TALK_TAIL_MAX more, never across a window limit.
    2) Silent action shots take the rest (Wan motion, mouths closed).
    3) Only without any silent shot: speaking shots up to their window limit,
       then by speech share (old behaviour, last resort).
    """
    times=list(base);missing=float(target)-sum(times)
    order=[i for i,t in enumerate(talking) if t]
    for i in order:
        if missing<=0:break
        if times[i]>=TALK_SEGMENT_SECONDS-MARGIN:continue
        free=max(0.,min(TALK_TAIL_MAX,talk_window_seconds(times[i])-times[i]-MARGIN))
        take=min(free,missing);times[i]+=take;missing-=take
    silent=[i for i,t in enumerate(talking) if not t]
    if missing>0 and silent:
        share=[max(.01,float(weights[i])) for i in silent]
        for i,w in zip(silent,share):times[i]+=missing*w/sum(share)
        missing=0
    if missing>0:
        for i in sorted(order,key=lambda i:talk_window_seconds(times[i])-times[i],reverse=True):
            if missing<=0:break
            # Over 15 s a shot is rendered as several prompts; single-prompt capacity does not apply.
            if times[i]>=TALK_SEGMENT_SECONDS-MARGIN:continue
            free=max(0.,min(talk_window_seconds(times[i]),TALK_SEGMENT_SECONDS)-times[i]-MARGIN)
            take=min(free,missing);times[i]+=take;missing-=take
    if missing>0:
        pool=order or list(range(len(times)))
        share=[max(.01,float(weights[i])) for i in pool]
        for i,w in zip(pool,share):times[i]+=missing*w/sum(share)
    return times

def audio_layout(episodes, lines, minimum_seconds=None, fps=FPS):
    """Speech starts on the cut; extra time becomes action, never a pause before the words."""
    reports=[]
    for ei,episode in enumerate(episodes):
        scenes=episode['scenes'];groups=[];base=[];plans=[]
        for si,scene in enumerate(scenes):
            group=sorted([line for line in lines if line['episode']==ei and line['scene']==si],key=lambda x:x.get('turn',0))
            groups.append(group)
            plan=talk_plan(group) if group else None;plans.append(plan)
            base.append(plan['seconds'] if group else max(2.5,float(scene.get('seconds',4))))
        target=float(minimum_seconds if minimum_seconds is not None else episode.get('minimum_seconds',0))
        rich=episode.get('dialogue_mode')=='rich' and any(groups)
        if rich:
            base=[seconds if group else 2.5 for seconds,group in zip(base,groups)]
        weights=[scene.get('seconds',4) if not group else sum(float(l['duration']) for l in group) for scene,group in zip(scenes,groups)]
        planned=fill_target(base,[bool(g) for g in groups],target,weights)
        # Whole frames; rounding only ever adds, the minimum stays met.
        times=distribute_frames(planned,target,weights,fps)
        cursor=0.;speech=0.;intervals=[]
        for scene,group,seconds,natural,plan in zip(scenes,groups,times,base,plans):
            spare=max(0,seconds-natural)
            # Older plain scripts keep a small reaction beat between lines.
            reaction=0. if rich else min(.35,spare/max(1,len(group))) if group else 0.
            local=plan['head'] if plan else HEAD
            for line,pause in zip(group,plan['pauses'] if plan else []):
                line['offset']=round(local,4);line['timeline_start']=round(cursor+local,4)
                duration=float(line['duration']);intervals.append((cursor+local,cursor+local+duration));speech+=duration
                local+=duration+pause+reaction
            scene.update(render_seconds=seconds,timeline_start=round(cursor,4),action_seconds=round(max(0,seconds-(sum(x['duration'] for x in group))),2))
            cursor+=seconds
        previous=0.;longest=0.
        for start,end in intervals:longest=max(longest,start-previous);previous=end
        reports.append({'seconds':round(cursor,2),'speech_seconds':round(speech,2),
            'speech_share':round(speech/cursor,3) if cursor else 0,
            'longest_speech_gap':round(max(longest,cursor-previous),2),'target_seconds':target,
            'minimum_met':cursor+1e-7>=target,'timing_policy':POLICY,'fps':fps,
            'talk_windows':sum(rendered_windows(t,fps) for t,g in zip(times,groups) if g),
            'silent_shots':sum(1 for g in groups if not g),'layout':17})
    return reports

# ---------------------------------------------------------------------------
# 0.16 layout, unchanged. Projects that already have a 0.16 sound version keep
# it on every re-mix or re-voice: a new layout changes every shot length and
# line offset, so every finished lip-sync window would be rendered again.
V16_HEAD = .08
V16_TAIL = .15
V16_FREE_CAP = 1.0

def v16_window_seconds(seconds):
    return (80+72*(talk_windows(seconds)-1))/TALK_FPS

def fill_target_v16(base, talking, target, weights):
    """Reach the minimum length without dead air.

    1) Seconds the lip-sync model computes anyway (rest of its last window),
       at most V16_FREE_CAP per shot. 2) Silent action scenes. 3) Only if none
       exist, speaking scenes by their speech share.
    """
    times=list(base);missing=float(target)-sum(times)
    for i in sorted([i for i,t in enumerate(talking) if t],key=lambda i:v16_window_seconds(times[i])-times[i],reverse=True):
        if missing<=0:break
        free=max(0.,min(V16_FREE_CAP,v16_window_seconds(times[i])-times[i]-MARGIN))
        take=min(free,missing);times[i]+=take;missing-=take
    if missing>0:
        silent=[i for i,t in enumerate(talking) if not t]
        pool=silent or list(range(len(times)))
        share=[max(.01,float(weights[i])) for i in pool]
        for i,w in zip(pool,share):times[i]+=missing*w/sum(share)
    return times

def audio_layout_v16(episodes, lines, minimum_seconds=None, fps=FPS):
    """Speech starts on the cut; extra time becomes action, never a pause before the words."""
    reports=[]
    for ei,episode in enumerate(episodes):
        scenes=episode['scenes'];groups=[];base=[]
        for si,scene in enumerate(scenes):
            group=sorted([line for line in lines if line['episode']==ei and line['scene']==si],key=lambda x:x.get('turn',0))
            groups.append(group)
            base.append(max(1.8,V16_HEAD+sum(float(x['duration'])+float(x.get('pause_after',.18)) for x in group)+V16_TAIL) if group else max(2.5,float(scene.get('seconds',4))))
        target=float(minimum_seconds if minimum_seconds is not None else episode.get('minimum_seconds',0))
        rich=episode.get('dialogue_mode')=='rich' and any(groups)
        if rich:
            base=[seconds if group else 2.5 for seconds,group in zip(base,groups)]
        weights=[scene.get('seconds',4) if not group else sum(float(l['duration']) for l in group) for scene,group in zip(scenes,groups)]
        planned=fill_target_v16(base,[bool(g) for g in groups],target,weights)
        # Whole frames; rounding only ever adds, the minimum stays met.
        times=distribute_frames(planned,target,weights,fps)
        cursor=0.;speech=0.;intervals=[]
        for scene,group,seconds,natural in zip(scenes,groups,times,base):
            spare=max(0,seconds-natural)
            # Older plain scripts keep a small reaction beat between lines.
            reaction=0. if rich else min(.35,spare/max(1,len(group))) if group else 0.
            local=V16_HEAD
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
            'minimum_met':cursor+1e-7>=target,'timing_policy':POLICY,'layout':16,'fps':fps,
            'talk_windows':sum(talk_windows(t) for t,g in zip(times,groups) if g)})
    return reports
