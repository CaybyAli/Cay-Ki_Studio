"""Validated data for a guided, project-independent series production."""
from typing import Literal,Annotated
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)

class VoiceRecipe(Strict):
    """How a designed voice was made (VoiceDesign instruction and seed): a library voice keeps
    its emotional range in every new project."""
    instruction:str=Field(min_length=10,max_length=2000)
    seed:int=Field(ge=0)

class Participant(Strict):
    name:str=Field(min_length=1,max_length=60)
    traits:str=Field(default='',max_length=1500)
    image:str|None=Field(default=None,pattern=r'^[a-f0-9]{32}$')
    voice:str|None=Field(default=None,pattern=r'^[a-f0-9]{32}$')
    voice_text:str=Field(default='',max_length=2500)
    # 'neutral': the upload is redrawn once with a neutral face (a laughing photo must not make
    # the figure laugh in every scene); 'exact': the upload is the design as it is. The app sends
    # it explicitly (default neutral there); a missing value keeps the pre-0.18 meaning 'exact'
    # (new edition of an old project, classic view).
    image_mode:Literal['neutral','exact']='exact'
    library_id:str|None=Field(default=None,pattern=r'^[a-f0-9]{32}$')
    voice_design:VoiceRecipe|None=None
    # Which library profile the image and the voice come from (shown on the figure card),
    # and the look of that image: a figure from another look is redrawn in the film's look.
    library_image:str|None=Field(default=None,pattern=r'^[a-f0-9]{32}$')
    library_voice:str|None=Field(default=None,pattern=r'^[a-f0-9]{32}$')
    image_look:Literal['auto','film','cartoon','clay','paper']|None=None

class LibraryFigure(Strict):
    name:str=Field(min_length=1,max_length=60)
    label:str=Field(min_length=1,max_length=80)
    look:Literal['auto','film','cartoon','clay','paper']='auto'
    traits:str=Field(default='',max_length=1500)
    image:str|None=Field(default=None,pattern=r'^[a-f0-9]{32}$')
    image_mode:Literal['neutral','exact']='neutral'
    voice:str|None=Field(default=None,pattern=r'^[a-f0-9]{32}$')
    voice_text:str=Field(default='',max_length=2500)
    voice_design:VoiceRecipe|None=None
    voice_preset:str=Field(default='',max_length=40)
    original:str=Field(default='',max_length=300)

class LibraryFromProject(Strict):
    project:str=Field(pattern=r'^[a-f0-9]{32}$')
    name:str=Field(min_length=1,max_length=60)
    label:str=Field(min_length=1,max_length=80)

class CastProfile(Strict):
    name:str=Field(min_length=1,max_length=60)
    library_id:str=Field(pattern=r'^[a-f0-9]{32}$')
    image:bool=True
    voice:bool=True

class Idea(Strict):
    request_key:str=Field(pattern=r'^[a-f0-9]{32}$')
    idea:Annotated[str,StringConstraints(strip_whitespace=False)]=Field(min_length=12,max_length=100000)
    title:str=Field(default='',max_length=100)
    episodes:int=Field(default=1,ge=1,le=12)
    duration:int=Field(default=60,ge=15,le=90)
    look:Literal['auto','film','cartoon','clay','paper']='auto'
    characters:Literal['invent','provided','none']='invent'
    participants:list[Participant]=Field(default_factory=list,max_length=8)
    examples:list[str]=Field(default_factory=list,max_length=4)
    music:str|None=Field(default=None,pattern=r'^[a-f0-9]{32}$')
    fps:Literal[25,30]=25
    quality:Literal['draft','fast','balanced','high']='fast'
    smooth:bool=True
    speech_engine:Literal['auto','qwen','chatterbox']='auto'
    lip_sync:Literal['audio','off']='audio'
    autopilot:bool=False
    # Show the designed figures once before scene images (0.17). The new UI sends it;
    # old projects and the classic UI (no cast_review screen) leave it off.
    cast_check:bool=False

class CastPlan(Strict):
    name:str=Field(min_length=1,max_length=60)
    appearance:str=Field(min_length=5,max_length=1000)
    # Well-known figure the user asked for (e.g. SpongeBob). Empty for invented ones.
    original:str=Field(default='',max_length=200)
    personality:str=Field(min_length=3,max_length=400)
    voice:Literal['warm','deep','bright','energetic']='warm'
    voice_preset:Literal['child_boy','child_girl','young_man','young_woman','man','woman','grandpa','grandma','creature']='man'
    voice_description:str=Field(default='',max_length=600)

class Outline(Strict):
    title:str=Field(min_length=2,max_length=100)
    plot:str=Field(min_length=10,max_length=1200)
    ending:str=Field(min_length=3,max_length=400)
    pickup:str=Field(default='',max_length=400)
    cliffhanger:str=Field(default='',max_length=400)

class SocialPost(Strict):
    caption:str=Field(min_length=10,max_length=180)
    hashtags:list[str]=Field(min_length=3,max_length=6)

class SeriesPlan(Strict):
    title:str=Field(min_length=2,max_length=100)
    synopsis:str=Field(min_length=10,max_length=1800)
    style:str=Field(min_length=10,max_length=1800)
    visual:Literal['film','cartoon','clay','paper']
    mood:Literal['suspense','playful','gentle','energetic']
    cast:list[CastPlan]=Field(max_length=8)
    episodes:list[Outline]=Field(min_length=1,max_length=12)

class Choice(Strict):
    episode:int=Field(ge=0,le=11)
    scene:int=Field(ge=0,le=44)
    step_id:str=Field(pattern=r'^[a-f0-9]{32}$')

class Review(Strict):
    revision:str=Field(pattern=r'^[a-f0-9]{64}$')

class ReviseScene(Strict):
    episode:int=Field(ge=0,le=11)
    scene:int=Field(ge=0,le=44)
    note:str=Field(default='',max_length=700)

class VoiceRedo(Strict):
    index:int=Field(ge=0,le=500)
    emotion:str=Field(min_length=1,max_length=150)

class SceneText(Strict):
    episode:int=Field(ge=0,le=11)
    scene:int=Field(ge=0,le=44)
    action:str=Field(min_length=5,max_length=800)
    dialogue:str=Field(default='',max_length=300)
    speaker:str=Field(default='',max_length=60)
    emotion:str=Field(default='Natürlich',max_length=150)

class DialogLine(Strict):
    speaker:str=Field(min_length=1,max_length=60)
    text:str=Field(min_length=1,max_length=240)
    emotion:str=Field(default='Natürlich',max_length=150)
    pause_after:float=Field(default=.18,ge=0,le=1.5)
class SoundCue(Strict):
    kind:Literal['magic','impact','whoosh','footstep','door','page','bell','splash']
    position:float=Field(ge=0,le=1)
    reason:str=Field(min_length=3,max_length=160)

class Shot(Strict):
    title:str=Field(min_length=2,max_length=100)
    action:str=Field(min_length=5,max_length=800)
    location:str=Field(min_length=2,max_length=250)
    camera:str=Field(min_length=3,max_length=250)
    cast:list[str]=Field(max_length=4)
    dialogue:str=Field(default='',max_length=180)
    speaker:str=Field(default='',max_length=60)
    emotion:str=Field(default='Natürlich',max_length=150)
    continuity:str=Field(min_length=3,max_length=400)
    beat:Literal['setup','problem','attempt','turn','payoff','cliffhanger']='attempt'
    because:str=Field(default='',max_length=400)
    dialogues:list[DialogLine]=Field(default_factory=list,max_length=6)
    ambience:Literal['room','wind','forest','rain','train','none']='room'
    sound_cues:list[SoundCue]=Field(default_factory=list,max_length=4)
    motion:list[str]=Field(default_factory=list,max_length=4)
    animation_prompt:str=Field(default='',max_length=1400)
    # 0.17 screenplay shots: English picture text naming only visible figures; 'line' or 'action'.
    still:str=Field(default='',max_length=600)
    kind:Literal['line','action','scene']='scene'

class CastRedo(Strict):
    name:str=Field(min_length=1,max_length=60)

class CastImage(Strict):
    name:str=Field(min_length=1,max_length=60)
    asset_id:str=Field(pattern=r'^[a-f0-9]{32}$')
    image_mode:Literal['neutral','exact']='neutral'

class AutopilotSwitch(Strict):
    enabled:bool

class AbortStep(Strict):
    fast:bool=False

class ProductionSettings(Strict):
    revision:str=Field(pattern=r'^[a-f0-9]{64}$')
    fps:Literal[25,30]
    quality:Literal['draft','fast','balanced','high']
    smooth:bool=True
    speech_engine:Literal['auto','qwen','chatterbox']='auto'
    lip_sync:Literal['audio','off']='audio'

class EpisodePlan(Strict):
    title:str=Field(min_length=2,max_length=100)
    goal:str=Field(min_length=1,max_length=400)
    obstacle:str=Field(min_length=1,max_length=400)
    resolution:str=Field(min_length=1,max_length=400)
    scenes:list[Shot]=Field(min_length=3,max_length=30)

def repair_episode_overview(raw):
    """Recover missing presentation fields from existing actions, never rewrite a story.

    The caller must still validate the whole episode and speaker/cast constraints.
    Returned source indices tell the UI to label these as scene excerpts rather
    than pretending that an action is a semantically verified goal or obstacle.
    """
    if not isinstance(raw,dict):return raw,{}
    scenes=raw.get('scenes')
    if not isinstance(scenes,list) or not scenes:return raw,{}
    value=dict(raw);sources={}
    problem=next((i for i,s in enumerate(scenes) if isinstance(s,dict) and s.get('beat')=='problem'),len(scenes)//2)
    indices={'goal':0,'obstacle':problem,'resolution':len(scenes)-1}
    for key,index in indices.items():
        supplied=value.get(key)
        if supplied is not None and (not isinstance(supplied,str) or supplied.strip()):continue
        scene=scenes[index]
        action=scene.get('action') if isinstance(scene,dict) else None
        if not isinstance(action,str) or not action.strip():continue
        text=action.strip();value[key]=text if len(text)<=400 else text[:397].rstrip()+'…'
        sources[key]=index+1
    return value,sources

class VoiceReference(Strict):
    name:str=Field(min_length=1,max_length=60)
    asset_id:str=Field(pattern=r'^[a-f0-9]{32}$')
    voice_text:str=Field(default='',max_length=2500)

class VoiceSettings(Strict):
    name:str=Field(min_length=1,max_length=60)
    voice_preset:Literal['child_boy','child_girl','young_man','young_woman','man','woman','grandpa','grandma','creature']
    voice_description:str=Field(default='',max_length=600)
    new_variant:bool=False
class SceneDialogueEdit(Strict):
    episode:int=Field(ge=0,le=11)
    scene:int=Field(ge=0,le=44)
    action:str=Field(min_length=5,max_length=1600)
    dialogues:list[DialogLine]=Field(max_length=6)
class MixSettings(Strict):
    music_mode:Literal['auto','off','uploaded']='auto'
    music_level:float=Field(default=1,ge=0,le=2)
    effects_level:float=Field(default=1,ge=0,le=2)
    ambience_level:float=Field(default=1,ge=0,le=2)
