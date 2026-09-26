"""Generation qualification on development identities only; not sealed scoring."""
from pathlib import Path
from cliptrace_e1.e1_common import OUT,verify,dump
from cliptrace_e1.e1_design import design,generate_one

manifest=design();assets={r['asset_id']:r for r in verify(OUT/'corpus-manifest.json')['assets']}
selected={}
for r in manifest['candidates']:
    if r['partition']=='development' and r['role']=='source':
        if r['transform'] not in selected or abs(r['length_s']-5)<abs(selected[r['transform']]['length_s']-5): selected[r['transform']]=r
results=[]
for i,(name,r) in enumerate(selected.items()):
    pilot=dict(r,candidate_id=f'P{i:05d}',path=str((OUT/'pilot'/f'P{i:05d}.mp4').resolve()))
    result=generate_one(pilot,assets);results.append(result)
    print(name,result['status'],round(result.get('wall_s',0),1),result.get('error','')[:160],flush=True)
dump(OUT/'development-generation-pilot.json',results)
