"""Pre-evaluation correction of an accidentally shared development/evaluation intro.

Preserve old manifests and scores. Evaluation has never been fingerprinted/scored.
No algorithms or operating thresholds are modified by this corpus correction.
"""
import concurrent.futures
import json
import shutil
import time
from pathlib import Path
from cliptrace_e1.e1_common import OUT,verify,load,dump,sha
from cliptrace_e1.e1_design import generate_one
from e1_controls import generate

assert not (OUT/'frozen-evaluation-profile.json').exists()
assert not (OUT/'evaluation-results.jsonl').exists()
archive=OUT/'revisions/intro-isolation-v1';archive.mkdir(parents=True,exist_ok=True)
for part in ['development','calibration']:
    for suffix in ['-results.jsonl','-results.jsonl.sha256','-run-state.json','-run-state.json.sha256',
                   '-source-artifacts.json','-source-artifacts.json.sha256','.log','-resources.json']:
        p=OUT/(part+suffix)
        if p.exists(): shutil.move(str(p),str(archive/p.name))
for name in ['corpus-manifest.json','partition-manifest.json','corpus-integrity.json']:
    for p in [OUT/name,OUT/(name+'.sha256')]:
        if p.exists(): shutil.copy2(p,archive/p.name)
corpus=verify(OUT/'corpus-manifest.json');before=sha(OUT/'corpus-manifest.json')
changed=['S07','N18','N21']
corpus['assets']=[generate(r)|dict(corpus_revision='evaluation_intro_v2',
    revision_reason='Independent evaluation-only polygon/title artwork replaces accidental shared development N05 intro asset.') if r['asset_id'] in changed else r for r in corpus['assets']]
corpus['version']='E1.2-pre-evaluation-intro-isolation'
dump(OUT/'corpus-manifest.json',corpus)
partition=verify(OUT/'partition-manifest.json')
partition['registry_scope']='Only registered sources in the active partition; evaluation fingerprint extraction and scoring occur after freeze. Acquisition and integrity QA precede freeze.'
dump(OUT/'partition-manifest.json',partition)
manifest=verify(OUT/'transformation-manifest.json')
affected=[r for r in manifest['candidates'] if r['identity'] in changed]
dump(OUT/'corpus-revision-plan.json',dict(reason='Detected shared generated intro artwork crossing development and evaluation.',
    affected_assets=changed,affected_candidates=[r['candidate_id'] for r in affected],
    corpus_sha256_before=before,corpus_sha256_after=sha(OUT/'corpus-manifest.json'),
    evaluation_scores_opened=False,algorithms_changed=False,thresholds_selected=False,
    count_unchanged=len(manifest['candidates']),resource_allowance_additional_cpu_hours=1,
    previous_scores='Archived and will be rerun with final corpus/profile bindings.'))
print('Revised evaluation artwork; awaiting original generation completion',flush=True)
while not (OUT/'ground-truth.json').exists(): time.sleep(2)
assert not (OUT/'frozen-evaluation-profile.json').exists()
gt=verify(OUT/'ground-truth.json');records={r['candidate_id']:r for r in gt['records']}
for name in ['ground-truth.json','ground-truth.json.sha256','generation-results.jsonl']:
    shutil.copy2(OUT/name,archive/name)
assets={a['asset_id']:a for a in corpus['assets']}
repairs=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
    futures=[ex.submit(generate_one,r,assets) for r in affected]
    for future in concurrent.futures.as_completed(futures):
        r=future.result();records[r['candidate_id']]=r;repairs.append(r)
        print('regenerated',len(repairs),'/',len(affected),r['candidate_id'],r['status'],flush=True)
gt['records']=[records[r['candidate_id']] for r in manifest['candidates']]
gt['corpus_revision']='evaluation_intro_v2'
dump(OUT/'ground-truth.json',gt)
(OUT/'generation-results.jsonl').write_text(''.join(json.dumps(r,sort_keys=True)+'\n' for r in gt['records']),encoding='utf-8')
dump(OUT/'corpus-revision-results.json',dict(replacements=repairs,all_expected_candidates=len(gt['records']),
    completed=True,manifest_candidate_ids_unchanged=True,evaluation_still_sealed=True))
print('CORPUS REVISION COMPLETE',flush=True)
