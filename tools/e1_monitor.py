"""Run a stage and sample descendant resources; observations are explicit lower bounds."""
import json
import subprocess
import sys
import time
from pathlib import Path
import psutil

label=sys.argv[1];command=sys.argv[2:]
out=Path('results/e1');out.mkdir(exist_ok=True,parents=True)
started=time.time();seen={};peak=0;samples=0
with (out/(label+'.log')).open('w',encoding='utf-8') as log:
    process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
    while process.poll() is None:
        try:
            root=psutil.Process(process.pid);tree=[root]+root.children(recursive=True);rss=0
            for p in tree:
                try:
                    key=(p.pid,p.create_time());cpu=p.cpu_times();seen[key]=max(seen.get(key,0),cpu.user+cpu.system);rss+=p.memory_info().rss
                except (psutil.NoSuchProcess,psutil.AccessDenied): pass
            peak=max(peak,rss);samples+=1
        except psutil.NoSuchProcess: pass
        time.sleep(.25)
data=dict(label=label,command=command,returncode=process.returncode,wall_s=time.time()-started,
          sampled_process_tree_cpu_s_lower_bound=sum(seen.values()),peak_sampled_process_tree_rss_bytes=peak,
          process_count=len(seen),samples=samples,sampling_interval_s=.25,
          limitation='Short-lived processes and final CPU between polls may be missed; CPU estimate is a lower bound, RSS is sampled.')
(out/(label+'-resources.json')).write_text(json.dumps(data,indent=2),encoding='utf-8')
sys.exit(process.returncode)
