"""Development-only algorithm qualification; results are never calibration observations."""
from cliptrace_e1.e1_common import OUT,load,dump,verify,artifact
from cliptrace_e1.e1_features import extract,match
from cliptrace_e1.e1_run import registry_for

registry,_=registry_for('development')
rows=load(OUT/'development-generation-pilot.json')
repairs={r['candidate_id']:r for r in load(OUT/'development-generation-pilot-repairs.json')}
rows=[repairs.get(r['candidate_id'],r) for r in rows]
rows=[r for r in rows if r['transform'] in ['trim','crop25','speed125','audio_replace','subtitles','reaction_layout','discontinuous'] and r['status']=='evaluated']
assets=verify(OUT/'corpus-manifest.json')['assets']
for a in assets:
    if a['partition']=='development' and a['role']=='negative':
        rows.append(dict(candidate_id=a['asset_id'],identity=a['asset_id'],transform='negative',path=a['path'],expected_parent=None))
results=[]
for r in rows:
    f,t=extract(r['path']);m=match(f,registry)
    result=dict(candidate_id=r['candidate_id'],identity=r['identity'],transform=r['transform'],
                expected_parent=r.get('expected_parent'),artifact_sha256=artifact(f),methods=m,resources=t)
    results.append(result)
    print(r['candidate_id'],r['transform'],{k:(round(v['score'],3) if v['score'] is not None else None,v['top_parent']) for k,v in m.items()},flush=True)
dump(OUT/'development-algorithm-pilot.json',results)
