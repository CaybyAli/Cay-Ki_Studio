"""Shared deterministic speech finishing for both local speech engines."""
import math,re,unicodedata

SPEECH_POLICY='studio08-natural-v1'

def clean_text(text):
    text=unicodedata.normalize('NFC',text).replace('\u200b','')
    return re.sub(r'\s+',' ',text).strip()

def sampling(emotion):
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

def performance_key(emotion):
    text=emotion.lower()
    for key,parts in [('angry',('wüt','wuet','zorn','aggress','angry')),('afraid',('ängst','aengst','panik','angst','erschrock','afraid')),('joy',('freud','begeister','glücklich','aufgeregt','lach','joy')),('sad',('traurig','weinen','verzweifel','sad')),('quiet',('flüster','fluester','geheim','whisper')),('firm',('bestimmt','droh','entschlossen','firm'))]:
        if any(p in text for p in parts):return key
    return 'natural'
