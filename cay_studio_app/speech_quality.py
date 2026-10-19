"""Shared deterministic speech finishing for both local speech engines."""
import math,re,unicodedata

SPEECH_POLICY='studio08-natural-v1'

def clean_text(text):
    text=unicodedata.normalize('NFC',text).replace('\u200b','')
    return re.sub(r'\s+',' ',text).strip()

# Chatterbox: the vendor's own "dramatic" recipe. Up to 0.16 every line ran at
# exaggeration 0.4 (below the model default 0.5), which flattened the voices.
CHATTERBOX = {'natural': (.5, .5), 'firm': (.65, .4), 'threat': (.65, .4), 'mocking': (.65, .4), 'annoyed': (.6, .45),
              'angry': (.85, .3), 'shout': (.9, .3), 'panic': (.85, .3), 'afraid': (.7, .35), 'joy': (.75, .35),
              'excited': (.85, .3), 'triumph': (.8, .3), 'surprised': (.75, .35), 'sad': (.45, .5), 'whisper': (.35, .5),
              'pleading': (.6, .4), 'confused': (.55, .45)}

def sampling(emotion,policy=17):
    if policy<17:return sampling_v16(emotion)
    exaggeration, cfg = CHATTERBOX.get(performance_key(emotion,policy), CHATTERBOX['natural'])
    return {'exaggeration':exaggeration,'cfg_weight':cfg,'temperature':.8,'top_p':.95,'repetition_penalty':1.2}

def sampling_v16(emotion):
    # Projects voiced before 0.17 keep this exact recipe (it is part of the line cache signature).
    emotion=emotion.lower()
    emphasis=.55 if any(x in emotion for x in ('wüt','ängst','begeister','erschrock','aufgeregt')) else .4
    return {'exaggeration':emphasis,'cfg_weight':.5,'temperature':.7,'top_p':.95,'repetition_penalty':1.2}

def finish_voice(data,sr,text):
    import numpy as np
    data=np.asarray(data,dtype=np.float32).reshape(-1)
    if not data.size or not np.isfinite(data).all():raise RuntimeError('Sprachmodell liefert ungültige Audiodaten.')
    peak=float(np.max(np.abs(data)))
    if peak<.001:raise RuntimeError('Sprachmodell liefert eine stumme Aufnahme.')
    if float(np.mean(np.abs(data)>=.999))>.01:raise RuntimeError('Sprachaufnahme übersteuert; neue Variante nötig.')
    # RMS windows retain quiet consonants and breath releases instead of a
    # sample threshold cutting off low-level word endings.
    hop=max(1,round(sr*.01));pad=(-len(data))%hop
    blocks=np.pad(data,(0,pad)).reshape(-1,hop)
    rms=np.sqrt(np.mean(blocks*blocks,axis=1));active=np.flatnonzero(rms>max(.00025,float(rms.max())*.008))
    if not len(active):raise RuntimeError('Keine verwertbare Stimme erkannt.')
    # A click or breath must not count as a spoken line. Short exclamations
    # previously passed because only peak and trimmed length were checked.
    words=max(1,len(text.split()))
    voiced=float(np.sum(rms>=max(.004,float(rms.max())*.08)))*.01
    if peak<.015 or voiced<.12+.07*words:
        raise RuntimeError(f'Kaum hörbare Sprache ({voiced:.2f} s Stimme für {words} Wörter). Die Zeile wird erneut eingesprochen.')
    first=max(0,int(active[0]*hop)-round(sr*.07));last=min(len(data),int((active[-1]+1)*hop)+round(sr*.16))
    data=data[first:last].copy();duration=len(data)/sr
    if not max(.15,words/6-.35)<duration<min(40,max(8,words/.7+2)):
        raise RuntimeError('Unplausible Sprechdauer. Die Zeile wird erneut eingesprochen.')
    if peak>.95:data*=.95/peak
    fade=min(round(sr*.006),len(data)//2)
    if fade:data[:fade]*=np.linspace(0,1,fade);data[-fade:]*=np.linspace(1,0,fade)
    return data,{'duration':duration,'voiced_seconds':round(voiced,2),'words_per_second':round(words/duration,2),'peak':round(float(np.max(np.abs(data))),4),'processing':SPEECH_POLICY}

# Delivery categories. The screenplay asks for one of these German words per
# line; free text from older plans is matched by stems. Up to 0.16 29 of 40
# common words ('panisch', 'schreiend', 'triumphierend' …) fell back to the
# neutral voice, so most lines sounded like calm narration.
PERFORMANCES = [
    ('shout', ('schrei', 'brüll', 'bruell', 'kreisch', 'shout', 'yell')),
    ('panic', ('panik', 'panisch', 'hektisch', 'hysterisch', 'panic')),
    ('angry', ('wüt', 'wuet', 'zorn', 'aggress', 'empört', 'empoert', 'sauer', 'angry', 'furious')),
    ('threat', ('droh', 'bedroh', 'gefährlich', 'eiskalt', 'threat', 'menac')),
    ('mocking', ('spött', 'spoett', 'höhn', 'hoehn', 'sarkas', 'ironisch', 'herablass', 'mock', 'sarcas')),
    ('annoyed', ('genervt', 'gereizt', 'ungeduld', 'annoy')),
    ('triumph', ('triumph', 'siegessicher', 'stolz', 'hämisch', 'haemisch', 'gierig', 'gloat')),
    ('excited', ('begeister', 'aufgeregt', 'euphor', 'enthusi', 'excit')),
    ('joy', ('freud', 'fröhlich', 'froehlich', 'glücklich', 'gluecklich', 'lach', 'erleichter', 'heiter', 'joy', 'happy')),
    ('surprised', ('überrasch', 'ueberrasch', 'erstaun', 'verblüfft', 'verbluefft', 'schockiert', 'entsetz', 'surpris', 'shock')),
    ('afraid', ('ängst', 'aengst', 'angst', 'furcht', 'erschrock', 'nervös', 'nervoes', 'zitter', 'afraid', 'scared')),
    ('pleading', ('fleh', 'bettel', 'bittend', 'verzweifel', 'plead')),
    ('sad', ('traurig', 'wein', 'niedergeschlagen', 'enttäusch', 'enttaeusch', 'sad')),
    ('whisper', ('flüster', 'fluester', 'geheim', 'leise', 'tuschel', 'whisper')),
    ('confused', ('verwirr', 'ratlos', 'unsicher', 'confus')),
    ('firm', ('bestimmt', 'entschlossen', 'ernst', 'befehl', 'firm')),
]

# Words that contain a stem by accident: 'neugierig' is not greedy-triumphant,
# 'beschreibend' is no shout, 'flach'/'gescheitert' contain 'lach'/'heiter'.
NOT_STEMS = re.compile(r'neugier|wissbegier|schreib|flach|scheiter')

VOICE_POLICY_NFC=19   # voice_policy from which a delivery word in decomposed Unicode (NFD, e.g. from macOS) is read

def performance_key(emotion,policy=0):
    # 0.19: 'wu\u0308tend' (NFD) fell silently to 'natural'. Only for voice_policy 19: an older project's stored
    # NFD words keep their category (references, cache signatures and picture expressions stay as they are).
    text=unicodedata.normalize('NFC',str(emotion or '')) if policy>=VOICE_POLICY_NFC else str(emotion or '')
    text=NOT_STEMS.sub('',text.lower())
    for key,parts in PERFORMANCES:
        if any(p in text for p in parts):return key
    return 'natural'

def performance_key_v16(emotion):
    # 0.16 categories, kept for projects voiced before 0.17 (selects their emotion references).
    text=str(emotion or '').lower()
    for key,parts in [('angry',('wüt','wuet','zorn','aggress','angry')),('afraid',('ängst','aengst','panik','angst','erschrock','afraid')),('joy',('freud','begeister','glücklich','aufgeregt','lach','joy')),('sad',('traurig','weinen','verzweifel','sad')),('quiet',('flüster','fluester','geheim','whisper')),('firm',('bestimmt','droh','entschlossen','firm'))]:
        if any(p in text for p in parts):return key
    return 'natural'

# Mix level per delivery in dB: shouting stands out, whispers sit lower. The
# compressor and loudnorm used to flatten these differences completely. Whispers
# only -2 dB: the music ducking ignores this gain, and the speech check blocks a
# line the music masks (a breathy take is already quiet on its own).
LEVEL_DB = {'shout': 2.5, 'angry': 1.5, 'panic': 1.5, 'excited': 1.0, 'triumph': 1.0, 'whisper': -2.0, 'sad': -1.5, 'pleading': -1.0}

def level_db(emotion):
    return LEVEL_DB.get(performance_key(emotion), 0.)

def prosody_score(data, sr):
    """How lively a take sounds: spread of pitch (semitones) and of loudness.
    Plain numpy (autocorrelation), so it runs in every speech environment.
    Used to keep the livelier of two takes for emotional lines."""
    import numpy as np
    x=np.asarray(data,dtype=np.float64).reshape(-1)
    if x.size<sr*.3:return 0.
    # Up to 1000 Hz: child and cartoon voices go above 500 Hz when shouting; a lower
    # limit made those frames jump an octave and look 'lively' by mistake.
    frame=int(sr*.04);hop=int(sr*.01);lo,hi=int(sr/1000),int(sr/70)
    frames=[x[i:i+frame] for i in range(0,len(x)-frame,hop)]
    rms=np.array([np.sqrt(np.mean(f*f)) for f in frames])
    if not rms.size or rms.max()<=0:return 0.
    voiced=rms>rms.max()*.12;pitches=[]
    for f,v in zip(frames,voiced):
        if not v:continue
        f=f-f.mean();ac=np.correlate(f,f,'full')[frame-1:]
        if ac[0]<=0 or hi>=len(ac):continue
        lag=lo+int(np.argmax(ac[lo:hi]))
        # A maximum on the edge of the search range is no pitch (half-filled frame at a pause).
        if lo<lag<hi-1 and ac[lag]/ac[0]>.45:pitches.append(sr/lag)
    spread=0.
    if len(pitches)>5:
        tones=12*np.log2(np.array(pitches)/np.median(pitches))
        # Octave errors are single-frame jumps: drop frames > 7 semitones off the local median.
        local=np.array([np.median(tones[max(0,i-2):i+3]) for i in range(len(tones))])
        tones=tones[np.abs(tones-local)<=7]
        if len(tones)>5:spread=float(np.std(tones))
    loud=20*np.log10(rms[voiced]+1e-9)
    return round(spread+.5*float(np.std(loud))/3,3)
