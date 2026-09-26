"""Three-way E1 runner. Evaluation is guarded by frozen code/data/config hashes."""
import concurrent.futures
import json
import time
from datetime import datetime,timezone
from pathlib import Path
import psutil
from .e1_common import ROOT,OUT,load,dump,verify,sha,artifact
from .e1_features import METHODS,CONFIG,FPCALC,extract,match

PRINCIPAL=['corpus-manifest.json','partition-manifest.json','transformation-manifest.json','ground-truth.json']

def code_hashes():
    return {str(p.relative_to(ROOT)):sha(p) for p in sorted([*(ROOT/'src/cliptrace_e1').rglob('*.py'),*(ROOT/'tools').glob('e1_*.py')])}

def assert_partition_integrity(corpus,partition):
    groups={};seen=set()
    for a in corpus['assets']:
        aid=a['asset_id']
        if aid in seen: raise ValueError('Duplicate identity')
        seen.add(aid)
        if partition['assignments'].get(aid)!=a['partition']: raise ValueError('Partition mismatch')
        groups.setdefault(a['identity_group'],set()).add(a['partition'])
    if any(len(x)!=1 for x in groups.values()): raise ValueError('Original-work identity leakage')
    for component in partition['common_content_components']:
        if len({partition['assignments'][a] for a in component})!=1: raise ValueError('Common-content leakage')
    if seen!=set(partition['assignments']): raise ValueError('Partition coverage mismatch')

def evaluation_guard():
    p=verify(OUT/'frozen-evaluation-profile.json')
    for name,digest in p['manifest_sha256'].items():
        verify(OUT/name)
        if sha(OUT/name)!=digest: raise ValueError('Frozen manifest changed: '+name)
    if code_hashes()!=p['code_sha256']: raise ValueError('Frozen implementation changed; evaluation cannot proceed')
    if CONFIG!=p['feature_configuration']: raise ValueError('Frozen feature config changed')
    if sha(OUT/'environment.json')!=p['environment_sha256']: raise ValueError('Frozen environment record changed')
    if FPCALC is not None and sha(FPCALC)!=p['fpcalc_sha256']: raise ValueError('Frozen fpcalc changed')
    return p

def read_rows(path):
    p=Path(path)
    return [json.loads(l) for l in p.read_text(encoding='utf-8').splitlines() if l.strip()] if p.exists() else []

def registry_for(partition,refresh=False):
    if partition=='evaluation': evaluation_guard()
    sources=[a for a in verify(OUT/'corpus-manifest.json')['assets'] if a['role']=='source' and a['partition']==partition]
    registry={};records={}
    for a in sources:
        if sha(a['path'])!=a['sha256']: raise ValueError('Source media changed')
        obj,timing=extract(a['path'],OUT/'audio_tmp'/('repeat' if refresh else 'main'))
        h=artifact(obj);registry[a['asset_id']]=obj;records[a['asset_id']]=dict(artifact_sha256=h,**timing)
    return registry,records

def score_one(row,registry):
    base={k:row[k] for k in ['candidate_id','identity','partition','category','role','length_s','transform','family','severity',
          'visual_ancestry','audio_ancestry','expected_parent','expected_ambiguity']}
    base['candidate_media_sha256']=row.get('sha256')
    if row['status']!='evaluated':
        return base|dict(status=row['status'],reason=row.get('reason',row.get('error')),methods={m:dict(status=row['status'],score=None,retrieval=[],pairs=[]) for m in METHODS})
    start=time.perf_counter()
    try:
        if sha(row['path'])!=row['sha256']: raise ValueError('Candidate media changed')
        feature,resources=extract(row['path'])
        h=artifact(feature)
        # No source identity, category, transform, ancestry label or GT interval passed to match().
        methods=match(feature,registry)
        for method,r in methods.items():
            for pair in r['pairs']:
                pair['alignment_artifact_sha256']=artifact(dict(method=method,**pair))
        return base|dict(status='evaluated',feature_artifact_sha256=h,methods=methods,observed_duration_s=feature['duration_s'],
                         resources=resources|dict(total_wall_s=time.perf_counter()-start,rss_bytes=psutil.Process().memory_info().rss))
    except MemoryError:
        return base|dict(status='resource_exhausted',methods={m:dict(status='resource_exhausted',score=None,retrieval=[],pairs=[]) for m in METHODS})
    except Exception as e:
        return base|dict(status='failed',error=str(e),methods={m:dict(status='failed',score=None,retrieval=[],pairs=[]) for m in METHODS})

def score_partition(partition):
    if partition not in ['development','calibration','evaluation']: raise ValueError(partition)
    if partition=='evaluation': evaluation_guard()
    corpus=verify(OUT/'corpus-manifest.json');pm=verify(OUT/'partition-manifest.json')
    assert_partition_integrity(corpus,pm)
    manifest=verify(OUT/'transformation-manifest.json')
    expected=[r for r in manifest['candidates'] if r['partition']==partition]
    profile_hash=sha(OUT/'frozen-evaluation-profile.json') if partition=='evaluation' else None
    state_path=OUT/(partition+'-run-state.json')
    # Non-evaluation scoring may consume completed generation journal entries while other
    # identities are still being rendered. The immutable design binds labels, and final
    # ground truth/media hashes are reconciled before calibration can freeze anything.
    bound_manifests=PRINCIPAL if partition=='evaluation' else PRINCIPAL[:-1]
    signature=dict(code_sha256=code_hashes(),manifests={n:sha(OUT/n) for n in bound_manifests},profile_sha256=profile_hash)
    if state_path.exists():
        old=verify(state_path)
        if old['signature']!=signature: raise ValueError('Cannot resume run after code/data changes; use a new pre-evaluation run')
    else: dump(state_path,dict(signature=signature,started_at=datetime.now(timezone.utc).isoformat()),immutable=True)
    path=OUT/(partition+'-results.jsonl');rows=read_rows(path);seen={r['candidate_id'] for r in rows}
    if len(rows)!=len(seen): raise ValueError('Duplicate result IDs')
    if len(seen)==len(expected): return rows
    registry,source_records=registry_for(partition)
    dump(OUT/(partition+'-source-artifacts.json'),source_records)
    t=time.perf_counter()
    with path.open('a',encoding='utf-8') as f,concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        pending={};submitted=set(seen);finished_generation=None
        while len(rows)<len(expected):
            if (OUT/'ground-truth.json').exists():
                if finished_generation is None:
                    finished_generation={r['candidate_id']:r for r in verify(OUT/'ground-truth.json')['records']}
                generated=finished_generation
            else:
                journal=(OUT/'generation-results.jsonl').read_text(encoding='utf-8')
                complete_lines=journal.split('\n')[:-1]
                generated={r['candidate_id']:r for r in map(json.loads,complete_lines) if r['partition']==partition}
            for spec in expected:
                cid=spec['candidate_id']
                if cid in submitted or cid not in generated or len(pending)>=4: continue
                row=generated[cid]
                for key in ['identity','partition','length_s','transform','visual_ancestry','audio_ancestry','expected_parent']:
                    if row[key]!=spec[key]: raise ValueError('Generated record diverges from immutable design')
                pending[ex.submit(score_one,row,registry)]=cid;submitted.add(cid)
            if not pending:
                if finished_generation is not None: raise ValueError('Final ground truth missing expected candidates')
                time.sleep(1);continue
            ready,_=concurrent.futures.wait(pending,timeout=1,return_when=concurrent.futures.FIRST_COMPLETED)
            for future in ready:
                pending.pop(future);r=future.result();rows.append(r)
                f.write(json.dumps(r,sort_keys=True,allow_nan=False)+'\n');f.flush()
                if len(rows)%20==0: print(partition,len(rows),'/',len(expected),'wall_s',round(time.perf_counter()-t),flush=True)
    path.with_name(path.name+'.sha256').write_text(sha(path)+'\n')
    assert {r['candidate_id'] for r in rows}=={r['candidate_id'] for r in expected}
    return rows

def positive(row,method):
    if method=='F-fusion': return row['visual_ancestry'] or row['audio_ancestry']
    return row['visual_ancestry'] if method.startswith('V-') else row['audio_ancestry']

def fusion_row(row,visual,audio,weight):
    v={p['parent']:p.get('score') for p in row['methods'][visual].get('pairs',[])}
    a={p['parent']:p.get('score') for p in row['methods'][audio].get('pairs',[])}
    pairs=[dict(parent=sid,score=weight*v[sid]+(1-weight)*a[sid]) for sid in sorted(set(v)&set(a)) if v[sid] is not None and a[sid] is not None]
    pairs.sort(key=lambda x:(-x['score'],x['parent']))
    top=pairs[0] if pairs else {}
    score=top.get('score');margin=score-pairs[1]['score'] if len(pairs)>1 else None
    return row|dict(methods={'F-fusion':dict(score=score,margin=margin,top_parent=top.get('parent'),status='evaluated' if pairs else 'not_evaluated',pairs=pairs)})

def calibrate_fusion(rows,visual,audio,ops):
    if not visual or not audio:
        return dict(status='not_evaluated',reason='Both constituent modalities must have qualified calibration operating points before fitting a combined routing rule.')
    duration=max(ops[visual]['minimum_duration_s'],ops[audio]['minimum_duration_s'])
    identities=sorted({r['identity'] for r in rows});trials=[]
    def select(rs):
        points=curve(rs,'F-fusion',duration)
        ok=[p for p in points if p['fpr'] is not None and p['tpr'] is not None and p['fpr']<=.015 and p['tpr']>=.7 and p['negative_available_denominator']==p['negative_expected_denominator']]
        return max(ok,key=lambda p:(p['tpr'],-p['fpr'],p['threshold'])) if ok else None
    for weight in [.25,.5,.75]:
        fr=[fusion_row(r,visual,audio,weight) for r in rows];held=[]
        for identity in identities:
            fitted=select([r for r in fr if r['identity']!=identity])
            op=dict(threshold=fitted['threshold'],minimum_duration_s=duration) if fitted else None
            for r in fr:
                if r['identity']==identity and r['length_s']>=duration:
                    held.append((r,decision(r,'F-fusion',op)))
        pos=sum(positive(r,'F-fusion') for r,d in held);neg=sum(not positive(r,'F-fusion') for r,d in held)
        tp=sum(positive(r,'F-fusion') and d['state']=='supported' and d['parent']==r['expected_parent'] for r,d in held)
        fp=sum(not positive(r,'F-fusion') and d['state']=='supported' for r,d in held)
        fitted=select(fr)
        trials.append(dict(visual_weight=weight,held_out_tp=tp,held_out_positive=pos,held_out_fp=fp,held_out_negative=neg,
                           qualified=bool(fitted and pos and neg and tp/pos>=.7 and fp/neg<=.015),full_calibration_fit=fitted))
    dump(OUT/'fusion-calibration.json',dict(trials=trials,validation='Leave one complete identity out; weight grid restricted before evaluation.'),immutable=True)
    valid=[t for t in trials if t['qualified']]
    if not valid: return dict(status='not_evaluated',reason='No convex fusion passed identity-held-out calibration gates.',trials=trials)
    chosen=max(valid,key=lambda t:(t['held_out_tp']/t['held_out_positive'],-t['held_out_fp']/t['held_out_negative']))
    return dict(status='evaluated',visual=visual,audio=audio,visual_weight=chosen['visual_weight'],
                threshold=chosen['full_calibration_fit']['threshold'],minimum_duration_s=duration,
                trials=trials,claim_semantics='Routing evidence only; does not replace separate C3/C4 support states.')

def decision(row,method,op):
    r=row['methods'][method];score=r.get('score')
    if row['status']!='evaluated' or r['status']!='evaluated' or score is None:
        return dict(state='insufficient',parent=None,processing_state=r['status'],reason='unavailable_evidence')
    if op is None or op.get('threshold') is None:
        return dict(state='insufficient',parent=None,processing_state='evaluated',reason='no_qualified_operating_point')
    if row.get('observed_duration_s',row['length_s'])<op['minimum_duration_s'] or score<op['threshold']:
        return dict(state='insufficient',parent=None,processing_state='evaluated',reason='duration_or_score')
    if r.get('margin') is not None and r['margin']<CONFIG['ambiguity_margin']:
        return dict(state='AMBIGUOUS',parent=None,processing_state='evaluated',reason='competing_registered_parents')
    return dict(state='supported',parent=r.get('top_parent'),processing_state='evaluated',reason='qualified_score_and_margin')

def curve(rows,method,min_duration):
    eligible=[r for r in rows if r['length_s']>=min_duration and (not method.startswith('V-') or not positive(r,method) or r['severity']!='harsh')]
    # Failed positives remain in the sensitivity denominator; unavailable negatives reported separately.
    pos=[r for r in eligible if positive(r,method)];neg=[r for r in eligible if not positive(r,method)]
    scores=sorted({float(r['methods'][method]['score']) for r in eligible if r['methods'][method].get('score') is not None})
    thresholds=[-0.000001,*scores,1.000001]
    rows_out=[]
    for threshold in thresholds:
        op=dict(threshold=threshold,minimum_duration_s=min_duration)
        ds=[(r,decision(r,method,op)) for r in eligible]
        tp=sum(positive(r,method) and d['state']=='supported' and d['parent']==r['expected_parent'] for r,d in ds)
        fp=sum(not positive(r,method) and d['state']=='supported' for r,d in ds)
        nneg=sum(not positive(r,method) and d['processing_state']=='evaluated' for r,d in ds)
        rows_out.append(dict(threshold=threshold,minimum_duration_s=min_duration,tp_correct_parent=tp,fp=fp,
            positive_denominator=len(pos),negative_available_denominator=nneg,negative_expected_denominator=len(neg),
            tpr=tp/len(pos) if pos else None,fpr=fp/nneg if nneg else None,
            wrong_parent=sum(positive(r,method) and d['state']=='supported' and d['parent']!=r['expected_parent'] for r,d in ds),
            ambiguous=sum(d['state']=='AMBIGUOUS' for r,d in ds)))
    return rows_out

def calibrate():
    if (OUT/'frozen-evaluation-profile.json').exists(): raise ValueError('Profile already frozen')
    if (OUT/'corpus-revision-plan.json').exists() and not (OUT/'corpus-revision-results.json').exists():
        raise ValueError('Pre-evaluation corpus revision is not complete')
    if verify(OUT/'calibration-run-state.json')['signature']['code_sha256']!=code_hashes():
        raise ValueError('Implementation changed after calibration; profile cannot be frozen from stale scores')
    rows=read_rows(OUT/'calibration-results.jsonl')
    expected=[r for r in verify(OUT/'transformation-manifest.json')['candidates'] if r['partition']=='calibration']
    if {r['candidate_id'] for r in rows}!={r['candidate_id'] for r in expected}: raise ValueError('Incomplete calibration')
    if any(r['partition']!='calibration' for r in rows): raise ValueError('Calibration contains another partition')
    truth={r['candidate_id']:r for r in verify(OUT/'ground-truth.json')['records']}
    for part in ['development','calibration']:
        prior=read_rows(OUT/(part+'-results.jsonl'))
        if {r['candidate_id'] for r in prior}!={cid for cid,g in truth.items() if g['partition']==part}: raise ValueError('Incomplete pre-evaluation partition')
        for r in prior:
            g=truth[r['candidate_id']]
            for key in ['identity','partition','length_s','transform','visual_ancestry','audio_ancestry','expected_parent']:
                if r[key]!=g[key]: raise ValueError('Result label / final ground-truth mismatch')
            if r.get('candidate_media_sha256')!=g.get('sha256'): raise ValueError('Scored media / final ground-truth hash mismatch')
    curves={};ops={};summaries={}
    for method in METHODS:
        curves[method]={str(d):curve(rows,method,d) for d in [1,2,3,5,10,15,30]}
        target_tpr=.7 if method.startswith('V-') else .75;target_fpr=.02 if method.startswith('V-') else .015
        qualifying=[]
        for duration in [5,10,15,30]:
            points=[x for x in curves[method][str(duration)] if x['tpr'] is not None and x['fpr'] is not None and x['tpr']>=target_tpr and x['fpr']<=target_fpr and x['negative_available_denominator']==x['negative_expected_denominator']]
            if points:
                qualifying.append(max(points,key=lambda x:(x['tpr'],-x['fpr'],x['threshold'])))
        chosen=min(qualifying,key=lambda x:x['minimum_duration_s']) if qualifying else None
        ops[method]=dict(threshold=chosen['threshold'],minimum_duration_s=chosen['minimum_duration_s']) if chosen else None
        summaries[method]=dict(selection=chosen,eligible_final=method not in ['V-A','A-baseline'],
                               conclusion='qualified_on_calibration' if chosen else 'NO OPERATING POINT SATISFIES REQUIRED FPR/TPR TRADEOFF')
    dump(OUT/'calibration-curves.json',dict(curves=curves,selection=summaries,
        rule='Correct-parent TPR maximized at FPR gate, smallest passing duration >=5; negatives must have complete scoring. Only visual qualification excludes harsh positives; audio includes all waveform-preserving transformations.'),immutable=True)
    eligible=[m for m in ['V-B','V-C'] if ops[m]]
    visual=max(eligible,key=lambda m:(summaries[m]['selection']['tpr'],-summaries[m]['selection']['fpr'])) if eligible else None
    audio='A-chromaprint' if ops['A-chromaprint'] else None
    fusion=calibrate_fusion(rows,visual,audio,ops)
    environment=verify(OUT/'environment.json');environment['source_tree_sha256']=code_hashes()
    dump(OUT/'environment.json',environment)
    profile=dict(version='E1.1',frozen_at=datetime.now(timezone.utc).isoformat(),
        manifest_sha256={n:sha(OUT/n) for n in PRINCIPAL},code_sha256=code_hashes(),
        calibration_results_sha256=sha(OUT/'calibration-results.jsonl'),calibration_curves_sha256=sha(OUT/'calibration-curves.json'),
        feature_configuration=CONFIG,algorithms=METHODS,
        algorithm_versions={'V-A':'Q0 frame_phash v1 unchanged','V-B':'E1 temporal XOR/appearance blocks v1',
                            'V-C':'E1 ORB geometric correspondence v1','A-baseline':'Q0 chromaprint_basic v1 unchanged',
                            'A-chromaprint':'Chromaprint fpcalc 1.6.1 algorithm 2 + raw Hamming sequence v1'},
        fpcalc_sha256=sha(FPCALC) if FPCALC else None,operating_points=ops,selected_visual=visual,selected_audio=audio,
        ambiguity_policy=dict(margin=.05,conflicting_modal_parent='AMBIGUOUS',common_content='competing registered evidence abstains; no first-registration preference'),
        fusion=dict(modes=['visual_only','audio_only','visual_OR_audio','visual_AND_audio'],
                    calibrated=fusion),environment_sha256=sha(OUT/'environment.json'),
        optional_candidates={'V-D':dict(status='resource_exhausted',reason='Deferred under local experiment implementation/CPU budget after measured feature pipeline cost; no pretrained embedding runtime benchmark or semantic-bleed qualification performed. Hardware infeasibility is not established.')},
        minimum_duration_tested=[1,2,3,5,10,15,30],
        temporal_gate=dict(mean_iou=.7,mean_start_error_s=1.,mean_end_error_s=1.,false_continuous_rate=.05,correct_parent_alignment_coverage=.7),
        reproducibility_tolerances=dict(score_abs=1e-6,alignment_s=.001,timestamp_s=.001),
        q0_preserved=dict(visual_tpr=.9,visual_fpr=.75,audio='collapsed',mean_iou=.55,start_error_s=.89,end_error_s=3.2,false_continuous_rate=0))
    dump(OUT/'frozen-evaluation-profile.json',profile,immutable=True)
    print('FROZEN',sha(OUT/'frozen-evaluation-profile.json'),'visual',visual,'audio',audio,flush=True)
    return profile

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['development','calibration','freeze','evaluation'])
    args=parser.parse_args()
    if args.stage=='freeze': calibrate()
    else: score_partition(args.stage)
