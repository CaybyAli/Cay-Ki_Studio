"""Bounded CPU work, measured stages and local Linux/WSL telemetry."""
import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import shutil
import subprocess
import time


from studio_resources_options import cpu_options


def memory_info():
    try:
        fields={line.split(':')[0]:int(line.split()[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines() if len(line.split())>=2 and line.split()[1].isdigit()}
        return {'scope':'WSL/Linux','total':fields.get('MemTotal'), 'available':fields.get('MemAvailable'),
                'swap_total':fields.get('SwapTotal'),'swap_used':fields.get('SwapTotal',0)-fields.get('SwapFree',0)}
    except OSError:return {'scope':'WSL/Linux'}


def windows_memory_info():
    """Read-only host counters; never edit WSL settings or terminate processes."""
    try:
        if 'microsoft' not in Path('/proc/sys/kernel/osrelease').read_text().lower():return {}
        binary=shutil.which('powershell.exe')
        if not binary:return {}
        command='$m=Get-CimInstance Win32_OperatingSystem; @{total=[double]$m.TotalVisibleMemorySize*1024; available=[double]$m.FreePhysicalMemory*1024} | ConvertTo-Json -Compress'
        result=subprocess.run([binary,'-NoProfile','-NonInteractive','-Command',command],capture_output=True,text=True,timeout=5)
        data=json.loads(result.stdout.lstrip('\ufeff'))
        return {'scope':'Windows',**{k:float(data[k]) for k in ('total','available')}}
    except (OSError,ValueError,KeyError,subprocess.TimeoutExpired):return {}


def memory_advice(snapshot):
    messages=[]
    for key,label in [('memory','WSL'),('host_memory','Windows')]:
        m=snapshot.get(key) or {};available=m.get('available');total=m.get('total')
        if available is not None and total and (available<3*1024**3 or available/total<.06):
            messages.append(f'{label}: nur {available/1024**3:.1f} GB RAM frei. Nicht benötigte Programme schließen; keine zweite Produktion starten.')
    if snapshot.get('swap_pages_in_per_second',0)+snapshot.get('swap_pages_out_per_second',0)>256:
        messages.append('WSL lagert gerade aktiv Speicher aus. Das kann die GPU ausbremsen.')
    return messages


class Resources:
    def __init__(self,g):
        self.g=g;self.options=cpu_options();self.slots=asyncio.Semaphore(self.options['workers'])
        self.active={};self.waiting={};self.previous=None;self.latest={};self.host_memory={};self.host_read_at=0

    def init(self):
        self.g['execute']('CREATE TABLE IF NOT EXISTS performance_stages(id INTEGER PRIMARY KEY AUTOINCREMENT,project TEXT,stage TEXT,resource TEXT,started TEXT,seconds REAL,status TEXT,detail TEXT)')

    def note(self,project,stage,resource,seconds,status='done',detail=None):
        self.g['execute']('INSERT INTO performance_stages(project,stage,resource,started,seconds,status,detail) VALUES(?,?,?,?,?,?,?)',
            (project,stage,resource,self.g['now'](),seconds,status,json.dumps(detail or {},ensure_ascii=False)))

    @asynccontextmanager
    async def measure(self,project,stage,resource):
        start=time.monotonic();status='done'
        try:yield
        except BaseException:status='interrupted';raise
        finally:self.note(project,stage,resource,time.monotonic()-start,status)

    async def cpu(self,project,stage,fn,*args):
        task_id=f'{project}:{stage}:{time.monotonic_ns()}'
        self.waiting[task_id]={'project':project,'stage':stage,'resource':'CPU'}
        try:
            async with self.slots:
                # Never prefetch heavy finishing jobs into an already crowded host.
                while memory_info().get('available',8*1024**3)<2*1024**3:
                    self.waiting[task_id]['reason']='Wartet auf freien Arbeitsspeicher'
                    await asyncio.sleep(2)
                self.active[task_id]=self.waiting.pop(task_id)
                async with self.measure(project,stage,'CPU'):
                    task=asyncio.create_task(asyncio.to_thread(fn,*args))
                    try:return await asyncio.shield(task)
                    except asyncio.CancelledError:
                        # A Python thread cannot be killed. Hold the slot until its
                        # file writes complete, including during server shutdown.
                        await task
                        raise
        finally:self.waiting.pop(task_id,None);self.active.pop(task_id,None)

    def sample(self):
        if time.monotonic()-self.host_read_at>20:
            self.host_memory=windows_memory_info();self.host_read_at=time.monotonic()
        value={'memory':memory_info(),'cpu_options':self.options,
               'host_memory':self.host_memory,'cpu_active':list(self.active.values()),'cpu_waiting':list(self.waiting.values())}
        try:
            cpu=[int(x) for x in Path('/proc/stat').read_text().splitlines()[0].split()[1:9]]
            vm={row.split()[0]:int(row.split()[1]) for row in Path('/proc/vmstat').read_text().splitlines()}
            point=(time.monotonic(),sum(cpu),cpu[3]+cpu[4],vm.get('pswpin',0),vm.get('pswpout',0))
            if self.previous:
                old=self.previous;total=point[1]-old[1]
                value['cpu_percent']=round(100*(1-(point[2]-old[2])/total),1) if total else 0
                value['swap_pages_in_per_second']=round((point[3]-old[3])/max(.001,point[0]-old[0]),1)
                value['swap_pages_out_per_second']=round((point[4]-old[4])/max(.001,point[0]-old[0]),1)
            self.previous=point
        except (OSError,ValueError,IndexError):pass
        value['work_cache']=str(self.g['RUNTIME']/'cache/finishing')
        value['warnings']=memory_advice(value)
        self.latest=value
        return value

    def summary(self,project=None):
        condition=' WHERE project=?' if project else ''
        args=(project,) if project else ()
        stages=self.g['rows']('SELECT stage,resource,status,COUNT(*) AS calls,ROUND(SUM(seconds),2) AS seconds FROM performance_stages'+condition+' GROUP BY stage,resource,status',args)
        return {'system':self.latest,'stages':stages,'note':'Zeitmessungen dieses Studios. CPU und GPU können überlappen; Stufenzeiten sind keine addierbare Gesamtdauer.'}

    def log_sample(self,snapshot):
        # Small bounded trace, independent from source media and project artifacts.
        folder=self.g['RUNTIME']/'logs';folder.mkdir(parents=True,exist_ok=True)
        path=folder/'performance.jsonl'
        try:
            if path.exists() and path.stat().st_size>8*1024**2:
                os.replace(path,path.with_suffix('.previous.jsonl'))
            with path.open('a') as f:f.write(json.dumps({'at':self.g['now'](),'resources':snapshot,'gpu':self.g.get('STATUS',{}).get('gpu',{})})+'\n')
        except OSError:pass

    def workspace(self,project,episode):
        base=self.g['RUNTIME']/'cache/finishing';base.mkdir(parents=True,exist_ok=True)
        # Only disposable completed workspaces are eligible for eviction.
        if shutil.disk_usage(base).free<8*1024**3:
            for marker in sorted(base.glob('*/*/.completed'),key=lambda p:p.stat().st_mtime):
                if marker.parent.parent.name==project:continue
                shutil.rmtree(marker.parent)
                if shutil.disk_usage(base).free>=12*1024**3:break
        if shutil.disk_usage(base).free<3*1024**3:
            raise RuntimeError('Zu wenig Platz im Linux-Arbeitscache. Mindestens 3 GB freigeben; fertige Projektdateien bleiben erhalten.')
        path=base/project/f'Folge_{episode+1:02}'
        path.mkdir(parents=True,exist_ok=True);(path/'.completed').unlink(missing_ok=True)
        return path
