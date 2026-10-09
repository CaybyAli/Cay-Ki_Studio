import os

def cpu_options():
    available=len(os.sched_getaffinity(0)) if hasattr(os,'sched_getaffinity') else (os.cpu_count() or 4)
    def setting(name,default,maximum):
        try:return max(1,min(maximum,int(os.environ.get(name,default))))
        except ValueError:return default
    workers=setting('CAY_CPU_WORKERS',1,2)
    return {'workers':workers,'threads':setting('CAY_FFMPEG_THREADS',max(2,min(12,available//2)),max(2,available-2)),
            'filter_threads':setting('CAY_FILTER_THREADS',min(4,max(1,available//4)),8),
            'logical_cpus':available}


