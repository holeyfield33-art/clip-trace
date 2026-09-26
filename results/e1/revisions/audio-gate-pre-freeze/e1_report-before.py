"""E1 scientific accounting; report generation never modifies matcher settings."""
import collections
import json
import math
import statistics
import time
from datetime import datetime,timezone
from pathlib import Path
from scipy.stats import beta
from .e1_common import ROOT,OUT,load,dump,verify,sha,artifact
from .e1_run import read_rows,decision,positive,evaluation_guard,registry_for,score_one,fusion_row
from .e1_features import METHODS,extract,match
from .alignment.temporal import temporal_iou,start_end_error,padding_inflation

def interval(k,n):
    if not n: return None
    return [float(beta.ppf(.025,k,n-k+1)) if k else 0.,float(beta.ppf(.975,k+1,n-k)) if k<n else 1.]

def ratio(k,n): return dict(numerator=k,denominator=n,rate=k/n if n else None,binomial_95_ci=interval(k,n))

def summarize(rows,method,op):
    pairs=[(r,decision(r,method,op)) for r in rows]
    counts=collections.Counter();states=collections.Counter();identity_negative={}
    for r,d in pairs:
        truth=positive(r,method);available=d['processing_state']=='evaluated';supported=d['state']=='supported'
        counts['positive_expected' if truth else 'negative_expected']+=1
        states[d['processing_state']]+=1
        counts['ambiguous']+=d['state']=='AMBIGUOUS'
        if truth:
            counts['correct_parent']+=supported and d['parent']==r['expected_parent']
            counts['wrong_parent']+=supported and d['parent']!=r['expected_parent']
            counts['ambiguous_parent']+=d['state']=='AMBIGUOUS'
        if not available:
            counts['unavailable_positive' if truth else 'unavailable_negative']+=1
            continue
        counts[('tp' if supported else 'fn') if truth else ('fp' if supported else 'tn')]+=1
        if not truth:
            identity_negative.setdefault(r['identity'],[]).append(supported)
    tp,fp,tn,fn=[counts[k] for k in ['tp','fp','tn','fn']]
    precision=tp/(tp+fp) if tp+fp else None;recall=tp/(tp+fn) if tp+fn else None
    # Recall@K comes only from the recorded Stage-1 ranking, never pairwise keys or injected truth.
    derivatives=[r for r in rows if positive(r,method)]
    retrieval={str(k):ratio(sum(r['expected_parent'] in [x[0] for x in r['methods'][method].get('retrieval',[])[:k]] for r in derivatives),len(derivatives)) for k in [1,5,10]}
    margins=[r['methods'][method]['margin'] for r in rows if r['methods'][method].get('margin') is not None]
    return dict(n_expected=len(rows),processing_states=dict(states),counts=dict(counts),operating_point=op,
        tpr_available=ratio(tp,tp+fn),tpr_all_expected_lower_bound=ratio(tp,counts['positive_expected']),fpr_available=ratio(fp,fp+tn),
        correct_parent=ratio(counts['correct_parent'],counts['positive_expected']),wrong_parent=ratio(counts['wrong_parent'],counts['positive_expected']),
        ambiguous_parent=ratio(counts['ambiguous_parent'],counts['positive_expected']),
        negative_identity_any_false_positive=ratio(sum(any(v) for v in identity_negative.values()),len(identity_negative)),
        precision=precision,recall=recall,f1=2*precision*recall/(precision+recall) if precision is not None and recall is not None and precision+recall else None,
        retrieval_recall= retrieval,mean_runnerup_margin=statistics.mean(margins) if margins else None,
        uncertainty_note='Candidate-level binomial intervals are descriptive only: derivatives/excerpts share identity and are dependent. Identity-any-FP is a different, conservative event rate. 4/8-source registries make recall@5/@10 easy.')

def merge_intervals(intervals,gap=0.):
    out=[]
    for a,b in sorted(intervals):
        if out and a-out[-1][1]<=gap: out[-1][1]=max(b,out[-1][1])
        else: out.append([a,b])
    return out

def temporal_rows(rows,truth,method,op):
    result=[]
    for r in rows:
        if not r['visual_ancestry']: continue
        pred=r['methods'][method];d=decision(r,method,op)
        top=next((p for p in pred.get('pairs',[]) if p['parent']==pred.get('top_parent')),None)
        gt=truth[r['candidate_id']];true=merge_intervals(gt['source_intervals_s'])
        claimed=[b['source'] for b in top.get('blocks',[])] if top else []
        correct=pred.get('top_parent')==r['expected_parent']
        valid=bool(correct and claimed)
        err=start_end_error(claimed,true) if valid else dict(start_error_s=None,end_error_s=None)
        # Tiny frame-deletion holes are measured in IoU; continuity errors concern gaps >=0.5s.
        true_fragments=len(merge_intervals(true,.5));claimed_fragments=len(merge_intervals(claimed,.5))
        fc=valid and true_fragments>1 and claimed_fragments==1
        result.append(dict(candidate_id=r['candidate_id'],transform=r['transform'],length_s=r['length_s'],category=r['category'],severity=r['severity'],
            supported=d['state']=='supported',correct_parent_alignment=valid,iou=temporal_iou(claimed,true) if valid else 0.,
            **err,fragmentation_error=abs(claimed_fragments-true_fragments) if correct else None,
            false_continuous=bool(fc),true_multifragment=true_fragments>1,
            padding_inflation=padding_inflation(merge_intervals(claimed),true) if valid else None,
            claimed=claimed,truth=true,blocks=top.get('blocks',[]) if top else []))
    return result

def temporal_summary(rows):
    def avg(key):
        vals=[r[key] for r in rows if r.get(key) is not None]
        return statistics.mean(vals) if vals else None
    multi=[r for r in rows if r['true_multifragment']]
    return dict(n_expected_positive=len(rows),correct_parent_alignment_coverage=ratio(sum(r['correct_parent_alignment'] for r in rows),len(rows)),
        mean_iou_including_missing_as_zero=avg('iou'),mean_start_error_s=avg('start_error_s'),mean_end_error_s=avg('end_error_s'),
        boundary_error_denominator=sum(r['start_error_s'] is not None for r in rows),
        fragmentation_error=avg('fragmentation_error'),padding_inflation=avg('padding_inflation'),
        false_continuous=ratio(sum(r['false_continuous'] for r in multi),len(multi)),
        note='Boundary errors conditional on correct-parent alignment; absent/wrong-parent intervals contribute zero IoU. Multi-fragment denominator includes missing alignments; see coverage.')

def multimodal(rows,profile):
    vm=profile['selected_visual'];am=profile['selected_audio'];ops=profile['operating_points'];out=[]
    absent=dict(state='insufficient',parent=None,processing_state='not_evaluated',reason='no_selected_qualified_candidate')
    for r in rows:
        v=decision(r,vm,ops[vm]) if vm else absent;a=decision(r,am,ops[am]) if am else absent
        vs=v['state']=='supported';aus=a['state']=='supported';conflict=vs and aus and v['parent']!=a['parent']
        either='AMBIGUOUS' if conflict else 'supported' if vs or aus else 'AMBIGUOUS' if 'AMBIGUOUS' in [v['state'],a['state']] else 'insufficient'
        both='AMBIGUOUS' if conflict else 'supported' if vs and aus else 'insufficient'
        fitted=profile['fusion']['calibrated']
        calibrated=decision(fusion_row(r,fitted['visual'],fitted['audio'],fitted['visual_weight']),'F-fusion',fitted) if fitted['status']=='evaluated' else absent
        out.append(dict(candidate_id=r['candidate_id'],C3=v,C4=a,C5=dict(state='not_evaluated',reason='No transcript matcher; semantic reconstruction control has known identical script.'),
            disagreement=conflict or vs!=aus,visual_only=v['state'],audio_only=a['state'],visual_OR_audio=either,visual_AND_audio=both,
            or_parent=None if conflict else v['parent'] if vs else a['parent'] if aus else None,
            and_parent=v['parent'] if both=='supported' else None,calibrated_routing=calibrated))
    metrics={}
    for mode in ['visual_only','audio_only','visual_OR_audio','visual_AND_audio']:
        tp=fp=tn=fn=0
        for r,m in zip(rows,out):
            truth=(r['visual_ancestry'] if mode=='visual_only' else r['audio_ancestry'] if mode=='audio_only' else
                   r['visual_ancestry'] or r['audio_ancestry'] if mode=='visual_OR_audio' else r['visual_ancestry'] and r['audio_ancestry'])
            yes=m[mode]=='supported'
            tp+=truth and yes;fp+=not truth and yes;tn+=not truth and not yes;fn+=truth and not yes
        metrics[mode]=dict(tp=tp,fp=fp,tn=tn,fn=fn,tpr=ratio(tp,tp+fn),fpr=ratio(fp,fp+tn),
                           note='Routing states include unavailable/no-qualified modalities as abstentions; modality processing counts remain separate.')
    metrics['calibrated']=profile['fusion']['calibrated']
    if metrics['calibrated']['status']=='evaluated':
        truth=[r['visual_ancestry'] or r['audio_ancestry'] for r in rows]
        yes=[m['calibrated_routing']['state']=='supported' for m in out]
        metrics['calibrated']=metrics['calibrated']|dict(tpr=ratio(sum(t and y for t,y in zip(truth,yes)),sum(truth)),
            fpr=ratio(sum(not t and y for t,y in zip(truth,yes)),sum(not t for t in truth)))
    metrics['disagreement_count']=sum(r['disagreement'] for r in out)
    metrics['audio_replacement_cases']=[m for r,m in zip(rows,out) if r['transform']=='audio_replace']
    return out,metrics

def reproducibility(cross_runtime=False):
    profile=evaluation_guard();gt=verify(OUT/'ground-truth.json')['records'];details=[];source_details=[]
    from .e1_design import generate_one
    assets={r['asset_id']:r for r in verify(OUT/'corpus-manifest.json')['assets']}
    # Representative fixed rule: each partition's first source at 5s trim/crop/speed and first negative 5s.
    for partition in ['development','calibration','evaluation']:
        main={r['candidate_id']:r for r in read_rows(OUT/(partition+'-results.jsonl'))}
        available=[r for r in gt if r['partition']==partition and r['status']=='evaluated']
        source=min(r['identity'] for r in available if r['role']=='source')
        negative=min(r['identity'] for r in available if r['role']=='negative')
        subset=[r for r in available if r['length_s']==5 and ((r['identity']==source and r['transform'] in ['trim','crop25','speed125']) or r['identity']==negative)]
        registry,source_rec=registry_for(partition,refresh=True)
        prior=verify(OUT/(partition+'-source-artifacts.json'))
        for sid,r in source_rec.items(): source_details.append(dict(identity=sid,artifact_equal=prior[sid]['artifact_sha256']==r['artifact_sha256']))
        for r in subset:
            regeneration=generate_one(r|dict(path=str((OUT/'repro-candidates'/('cross' if cross_runtime else 'same')/(r['candidate_id']+'.mp4')).resolve())),assets)
            repeated=score_one(regeneration,registry);original=main[r['candidate_id']]
            by_method={}
            for m in METHODS:
                aa=original['methods'][m];bb=repeated['methods'][m]
                sa,sb=aa.get('score'),bb.get('score')
                score_delta=abs(sa-sb) if sa is not None and sb is not None else 0. if sa is sb else None
                align_a=[p.get('blocks',[]) for p in aa.get('pairs',[])];align_b=[p.get('blocks',[]) for p in bb.get('pairs',[])]
                coords_a=[float(x) for blocks in align_a for b in blocks for iv in [b['source'],b['candidate']] for x in iv]
                coords_b=[float(x) for blocks in align_b for b in blocks for iv in [b['source'],b['candidate']] for x in iv]
                delta=max([abs(x-y) for x,y in zip(coords_a,coords_b)] or [0.]) if len(coords_a)==len(coords_b) else None
                by_method[m]=dict(score_delta=score_delta,alignment_delta_s=delta,alignment_artifacts_equal=align_a==align_b,
                                  ranking_equal=aa.get('retrieval')==bb.get('retrieval'),status_equal=aa.get('status')==bb.get('status'))
            ha=original.get('feature_artifact_sha256');hb=repeated.get('feature_artifact_sha256')
            fa=load(OUT/'artifacts'/ha[:2]/(ha+'.json')) if ha else {}
            fb=load(OUT/'artifacts'/hb[:2]/(hb+'.json')) if hb else {}
            tsa=fa.get('decode_pts_s',[]);tsb=fb.get('decode_pts_s',[])
            tsdelta=max([abs(x-y) for x,y in zip(tsa,tsb)] or [0.]) if len(tsa)==len(tsb) else None
            # A further focused extraction is independent of the full repeat matching pass.
            focused,_=extract(r['path'],OUT/'audio_tmp/focused');hc=artifact(focused)
            details.append(dict(candidate_id=r['candidate_id'],partition=partition,feature_artifact_original=ha,
                feature_artifact_repeat=hb,feature_artifact_focused=hc,artifact_equal=bool(ha and ha==hb==hc),
                decode_timestamp_delta_s=tsdelta,methods=by_method,regeneration_status=regeneration['status'],
                original_media_sha256=r.get('sha256'),regenerated_media_sha256=regeneration.get('sha256'),
                media_bytes_equal=r.get('sha256')==regeneration.get('sha256')))
            print('reproduced',r['candidate_id'],flush=True)
    classification={}
    for m in METHODS:
        exact=bool(details) and all(d['artifact_equal'] and d['decode_timestamp_delta_s']==0 and d['methods'][m]['score_delta']==0 and
             d['methods'][m]['alignment_artifacts_equal'] and d['methods'][m]['ranking_equal'] and d['methods'][m]['status_equal'] for d in details) and all(d['artifact_equal'] for d in source_details)
        tol=bool(details) and all(d['decode_timestamp_delta_s'] is not None and d['decode_timestamp_delta_s']<=.001 and
              d['methods'][m]['score_delta'] is not None and d['methods'][m]['score_delta']<=1e-6 and d['methods'][m]['alignment_delta_s'] is not None and
              d['methods'][m]['alignment_delta_s']<=.001 and d['methods'][m]['status_equal'] for d in details)
        classification[m]='BIT_DETERMINISTIC' if exact else 'TOLERANCE_REPRODUCIBLE' if tol else 'UNSTABLE'
    import platform,importlib.metadata
    report=dict(scope='Media transformation regenerated; all source features re-extracted; extraction/retrieval/verification repeated on representative subset; additional focused artifact extraction.',
        classifications=classification,sources=source_details,candidates=details,
        runtime=dict(python=platform.python_version(),packages={x:importlib.metadata.version(x) for x in ['numpy','Pillow','opencv-python-headless','scipy']}),
        environment_differences='second Python runtime on same machine' if cross_runtime else 'same runtime and machine; fresh decoders and feature extraction',
        second_runtime=dict(status='not_evaluated',reason='Python 3.11 is installed but separate dependency/runtime qualification is not part of completed repeated subset; not independent machine reproduction.'))
    dump(OUT/('reproducibility-cross-runtime.json' if cross_runtime else 'reproducibility.json'),report)
    return report

def report():
    profile=evaluation_guard();rows=read_rows(OUT/'evaluation-results.jsonl');gt=verify(OUT/'ground-truth.json')['records'];truth={r['candidate_id']:r for r in gt}
    expected=[r for r in gt if r['partition']=='evaluation']
    assert len(rows)==len(expected) and {r['candidate_id'] for r in rows}=={r['candidate_id'] for r in expected}
    methods={};temporal={};distributions={}
    for m in METHODS:
        op=profile['operating_points'][m]
        gate_rows=[r for r in rows if r['length_s']>=(op['minimum_duration_s'] if op else 5) and (not positive(r,m) or r['severity']!='harsh')]
        methods[m]=dict(all=summarize(rows,m,op),qualification_subset=summarize(gate_rows,m,op),breakdowns={})
        for field in ['transform','length_s','category','severity']:
            methods[m]['breakdowns'][field]={str(value):summarize([r for r in rows if r[field]==value],m,op) for value in sorted({r[field] for r in rows})}
        distributions[m]={p:[dict(candidate_id=r['candidate_id'],identity=r['identity'],score=r['methods'][m].get('score'),
                    positive=positive(r,m),status=r['methods'][m]['status'],length_s=r['length_s'],transform=r['transform'])
                    for r in read_rows(OUT/(p+'-results.jsonl'))] for p in ['development','calibration','evaluation']}
        if m.startswith('V-'):
            tr=temporal_rows(rows,truth,m,op)
            temporal[m]=dict(all=temporal_summary(tr),supported=temporal_summary([r for r in tr if r['supported']]),
               by_transform={name:temporal_summary([r for r in tr if r['transform']==name]) for name in sorted({r['transform'] for r in tr})},rows=tr)
    multimodal_rows,fusion=multimodal(rows,profile)
    receipts=OUT/'modality-decisions.jsonl';receipts.write_text(''.join(json.dumps(r,sort_keys=True)+'\n' for r in multimodal_rows),encoding='utf-8')
    receipts.with_name(receipts.name+'.sha256').write_text(sha(receipts)+'\n')
    topk=OUT/'retrieval-topk.jsonl'
    topk.write_text(''.join(json.dumps(dict(candidate_id=r['candidate_id'],partition=r['partition'],method=m,
        ranking=r['methods'][m].get('retrieval',[]),score_margin=r['methods'][m].get('margin')),sort_keys=True)+'\n'
        for part in ['development','calibration','evaluation'] for r in read_rows(OUT/(part+'-results.jsonl')) for m in METHODS),encoding='utf-8')
    topk.with_name(topk.name+'.sha256').write_text(sha(topk)+'\n')
    dump(OUT/'score-distributions.json',distributions);dump(OUT/'temporal-metrics.json',temporal)
    repro=verify(OUT/'reproducibility.json')
    if (OUT/'reproducibility-cross-runtime.json').exists():
        cross=verify(OUT/'reproducibility-cross-runtime.json')
        ranking={'BIT_DETERMINISTIC':0,'TOLERANCE_REPRODUCIBLE':1,'UNSTABLE':2}
        repro['same_runtime_classifications']=dict(repro['classifications'])
        repro['classifications']={m:max([repro['classifications'][m],cross['classifications'][m]],key=lambda x:ranking[x]) for m in METHODS}
        repro['second_runtime']=dict(status='evaluated',runtime=cross['runtime'],classifications=cross['classifications'],
                                     artifact='reproducibility-cross-runtime.json',scope='Different Python/NumPy runtime, same Windows machine and FFmpeg/fpcalc binaries.')
        dump(OUT/'reproducibility.json',repro)
    verdicts={}
    for modality,prefix,candidates,target_tpr,target_fpr in [('visual','VISUAL',['V-B','V-C'],.7,.02),('audio','AUDIO',['A-chromaprint'],.75,.015)]:
        passed=[]
        for m in candidates:
            x=methods[m]['qualification_subset'];t=x['correct_parent']['rate'];f=x['fpr_available']['rate']
            if profile['operating_points'][m] and t is not None and f is not None and t>=target_tpr and f<=target_fpr: passed.append(m)
        verdicts[modality]=prefix+'-GO' if passed else prefix+'-NO-GO'
    selected=profile['selected_visual'];al=temporal[selected]['all'] if selected else None;gate=profile['temporal_gate']
    issued=temporal[selected]['supported'] if selected else None
    alignment_good=bool(al and al['mean_iou_including_missing_as_zero']>=gate['mean_iou'] and
        issued['mean_start_error_s'] is not None and issued['mean_start_error_s']<=gate['mean_start_error_s'] and
        issued['mean_end_error_s'] is not None and issued['mean_end_error_s']<=gate['mean_end_error_s'] and
        al['correct_parent_alignment_coverage']['rate']>=gate['correct_parent_alignment_coverage'] and
        issued['false_continuous']['rate'] is not None and issued['false_continuous']['rate']<=gate['false_continuous_rate'])
    verdicts['alignment']='ALIGNMENT-GO' if alignment_good else 'CAUTION'
    if issued and issued['false_continuous']['rate'] is not None and issued['false_continuous']['rate']>.2: verdicts['alignment']='ALIGNMENT-NO-GO'
    verdicts['reproducibility']='REPRODUCIBILITY-GO' if all(v!='UNSTABLE' for v in repro['classifications'].values()) else 'REPRODUCIBILITY-NO-GO'
    if (verdicts['visual']=='VISUAL-NO-GO' and verdicts['audio']=='AUDIO-NO-GO') or verdicts['alignment']=='ALIGNMENT-NO-GO': overall='CORE NO-GO'
    elif alignment_good and ('VISUAL-GO'==verdicts['visual'] or 'AUDIO-GO'==verdicts['audio']): overall='CORE GO'
    else: overall='CAUTION'
    # Strong GO requires demonstrated multimodal improvement, not assumed from the OR rule.
    if overall=='CORE GO' and verdicts['visual']=='VISUAL-GO' and verdicts['audio']=='AUDIO-GO':
        best=max(fusion['visual_only']['tpr']['rate'] or 0,fusion['audio_only']['tpr']['rate'] or 0)
        if (fusion['visual_OR_audio']['tpr']['rate'] or 0)>best and (fusion['visual_OR_audio']['fpr']['rate'] or 0)<=.02: overall='STRONG GO'
    states=collections.Counter(r['status'] for r in gt);evaluated_states=collections.Counter(r['status'] for r in rows)
    metrics=dict(version='E1.1',profile_sha256=sha(OUT/'frozen-evaluation-profile.json'),verdicts=verdicts,overall=overall,
       denominator_reconciliation=dict(manifest=len(gt),generation=dict(states),evaluation_expected=len(expected),evaluation_results=len(rows),evaluation_states=dict(evaluated_states)),
       methods=methods,multimodal=fusion,limitations=['Only 8 evaluation registered sources and 12 independent negative identities; sparse category strata.',
          'Negative duration excerpts are correlated; confidence intervals do not create additional independent examples.',
          'No physical capture, trained embedding or validated calibrated fusion; AI-light operations are conventional open-source filters, not generative reconstruction.',
          'Same-script new-speaker and independently drawn semantic reconstruction controls do not exhaust modern AI reconstruction.',
          'No ownership, authorization, infringement or product-readiness claims.'])
    dump(OUT/'metrics.json',metrics)
    all_rows=[r for p in ['development','calibration','evaluation'] for r in read_rows(OUT/(p+'-results.jsonl'))]
    resources=dict(checkpoint=verify(OUT/'resource-checkpoint.json'),generation_wall_s_summed=sum(r.get('wall_s',0) for r in gt),
       candidate_matching_wall_s_summed=sum(r.get('resources',{}).get('total_wall_s',0) for r in all_rows),
       peak_python_rss_bytes=max([r.get('resources',{}).get('rss_bytes',0) for r in all_rows] or [0]),
       cpu_time_note='Summed worker wall times are not CPU time; subprocess CPU accounting unavailable for this run.',
       artifact_count=sum(1 for _ in (OUT/'artifacts').rglob('*.json')),
       artifact_bytes=sum(p.stat().st_size for p in (OUT/'artifacts').rglob('*.json')),
       candidates_bytes=sum(r.get('size_bytes',0) for r in gt),
       process_tree_samples={p.stem:load(p) for p in OUT.glob('*-resources.json')})
    dump(OUT/'resource-metrics.json',resources)
    write_markdown(metrics,temporal,repro,profile,resources)
    dump(OUT/'principal-sha256.json',{p.name:sha(p) for p in OUT.iterdir() if p.is_file() and p.suffix in ['.json','.jsonl','.md'] and p.name!='principal-sha256.json'})
    print('E1 COMPLETE',overall,flush=True)

def fmt(x): return 'not evaluated' if x is None else f'{x:.3f}'

def write_markdown(metrics,temporal,repro,profile,resources):
    lines=['# CLIPTRACE-E1 scientific report','',f'**Overall verdict: {metrics["overall"]}.**','',
       'This is a finite-corpus derivation experiment, not a production implementation or ownership determination. No evaluation repair/tuning was performed after the frozen profile.','',
       '## Independent verdicts','']
    lines += [f'- {k}: **{v}**' for k,v in metrics['verdicts'].items()]
    lines += ['', '## Preserved Q0 evidence','',
       'Authorized baseline `aeefc29f066a558322ab08dd477a5ad0ec04b56e`; smoke `765509294925929cc7144af9d4ba036d3652c2b9`. Q0 pHash TPR 0.90 / FPR 0.75 remains a failed sole-MVP control. The collapsed basic audio adapter remains an ineligible final C4 control. Q0 IoU ~0.55, start error ~0.89 s, end error ~3.2 s, false-continuous 0 are not E1 success evidence.','',
       '## Design and sealing','',
       '16 source identities / 24 negative identities; development 4/6, calibration 4/6, evaluation 8/12. Common-content components remain inside a partition. Each partition has its own registry. The 1,512-row fractional manifest specifies the sampled interactions and all seven requested lengths. All generation and scoring states are retained.', '',
       f'Frozen profile SHA-256: `{sha(OUT/"frozen-evaluation-profile.json")}`.',
       f'Partition SHA-256: `{sha(OUT/"partition-manifest.json")}`.',
       'Code and principal data hashes are checked before evaluation and report generation. Stage 2 sees only Stage-1 retrieved parents, with no true-parent injection. With only 4 or 8 registered sources, recall@10 cannot demonstrate retrieval scalability.', '',
       'A pre-evaluation identity audit found an accidentally shared generated intro between development and evaluation. The evaluation-only artwork was independently replaced in S07/N18/N21 and all 98 affected variants regenerated. Preliminary development/calibration passes were archived and rerun. No evaluation fingerprints or scores had been opened. Revision plans, old manifests and replacement outcomes are retained under `revisions/` and `corpus-revision-*.json`.', '',
       '## Calibration-selected operating points','',
       '| Candidate | Threshold | Minimum duration | Role |','|---|---:|---:|---|']
    for m in METHODS:
        op=profile['operating_points'][m]
        lines.append(f'| {m} | {fmt(op["threshold"]) if op else "NO OPERATING POINT"} | {str(op["minimum_duration_s"])+" s" if op else "—"} | {"control only" if m in ["V-A","A-baseline"] else "candidate"} |')
    calibration=verify(OUT/'calibration-curves.json')
    lines += ['', 'Best calibration correct-parent TPR attainable at the required FPR bound for the original >=5 s subset (including candidates that failed the TPR gate):','',
              '| Candidate | Correct parent / positives | FP / negatives | Threshold |','|---|---:|---:|---:|']
    for m in METHODS:
        bound=.02 if m.startswith('V-') else .015
        points=[p for p in calibration['curves'][m]['5'] if p['fpr'] is not None and p['fpr']<=bound and p['tpr'] is not None]
        best=max(points,key=lambda p:(p['tpr'],-p['fpr'],p['threshold'])) if points else None
        lines.append(f'| {m} | {str(best["tp_correct_parent"])+"/"+str(best["positive_denominator"]) if best else "unavailable"} | {str(best["fp"])+"/"+str(best["negative_available_denominator"]) if best else "unavailable"} | {fmt(best["threshold"]) if best else "—"} |')
    lines += ['', 'Thresholds use calibration only: correct-parent TPR >=70% at <=2% FPR for visual, >=75% at <=1.5% FPR for audio. Harsh positives are reported separately and excluded only from operating-point qualification. Duration selection tests 5, 10, 15 and 30 s; 1/2/3 s remain diagnostic. Complete threshold curves are retained. A null operating point abstains; its zeros are not proof of successful specificity.', '',
       '## Sealed evaluation: qualification subsets','',
       '| Candidate | Correct parent / positive | Wrong parent / positive | FP / available negatives | Ambiguous / positive |','|---|---:|---:|---:|---:|']
    for m in METHODS:
        x=metrics['methods'][m]['qualification_subset']
        def cell(k):
            q=x[k];return f'{q["numerator"]}/{q["denominator"]} ({fmt(q["rate"])})'
        lines.append(f'| {m} | {cell("correct_parent")} | {cell("wrong_parent")} | {cell("fpr_available")} | {cell("ambiguous_parent")} |')
    lines += ['', 'Exact numerators, denominators, binomial intervals, identity-level any-FP rates, processing availability and retrieval@1/5/10 are in `metrics.json`. Candidate-level intervals are descriptive because transformed observations are correlated. Twelve evaluation negative identities cannot establish a population FPR of 1.5–2% precisely. Breakdowns by transform, duration, category and severity are included; pooled means do not substitute for them.', '',
       '## Duration-specific decisions','',
       'All transforms are included here, including harsh and unsupported cases. Null operating points abstain at every duration; this is not evidence that their raw scores separate positives and negatives.','']
    for m in METHODS:
        lines += [f'### {m}','', '| Seconds | Correct parent / expected positives | FP / scored negatives | Ambiguous positives | Unavailable positives |',
                  '|---:|---:|---:|---:|---:|']
        for duration in [1,2,3,5,10,15,30]:
            q=metrics['methods'][m]['breakdowns']['length_s'][str(duration)]
            c=q['correct_parent'];f=q['fpr_available'];a=q['ambiguous_parent']
            lines.append(f'| {duration} | {c["numerator"]}/{c["denominator"]} | {f["numerator"]}/{f["denominator"]} | {a["numerator"]} | {q["counts"].get("unavailable_positive",0)} |')
        lines.append('')
    lines += [
       '## Temporal evidence','',
       '| Method | IoU (missing = 0) | Start error s | End error s | Correct-parent alignment coverage | False continuous / multifragment |','|---|---:|---:|---:|---:|---:|']
    for m,t in temporal.items():
        q=t['all'];c=q['correct_parent_alignment_coverage'];f=q['false_continuous']
        lines.append(f'| {m} | {fmt(q["mean_iou_including_missing_as_zero"])} | {fmt(q["mean_start_error_s"])} | {fmt(q["mean_end_error_s"])} | {c["numerator"]}/{c["denominator"]} | {f["numerator"]}/{f["denominator"]} |')
    lines += ['', 'Boundary errors are conditional on correct-parent alignment; missing and wrong-parent alignments score zero IoU. Fragmentation, padding, supported-only results and transform-specific metrics are retained in `temporal-metrics.json`. Source/candidate interval pairs preserve reordered mapping. Physical screen-capture strata are unsupported, not successful zeros.', '',
       '## Modality separation and ambiguity','',
       f'Selected visual: `{profile["selected_visual"]}`. Selected audio: `{profile["selected_audio"]}`. Every evaluation candidate has separate C3/C4 decisions, C5 not evaluated, disagreement states, visual-only/audio-only/OR/AND routes in `modality-decisions.jsonl`. Audio replacement can retain C3 while losing C4. Conflicting supported parents cause AMBIGUOUS. Calibrated fusion status: `{profile["fusion"]["calibrated"]["status"]}`; the profile records its identity-held-out qualification or reason for abstention.', '',
       'Shared B-roll is deliberately inserted into two independently assembled evaluation works; the donor is an attribution negative. Shared slide/meme templates and same-script different-voice controls also test ordinary resemblance. Common-content ambiguity is an empirical policy under test; failures remain visible rather than relabeled using truth.', '',
       '## Reproducibility and resources','']
    lines += [f'- {m}: {c} (tested runtimes, representative subset).' for m,c in repro['classifications'].items()]
    lines += ['',f'Repeated {len(repro["candidates"])} complete candidate comparisons with freshly extracted registry features, plus focused extraction. Second-runtime status: `{repro["second_runtime"]["status"]}`. Artifact hashes, score deltas, alignment deltas and decode timestamps are in `reproducibility.json`. Independent second-machine reproduction is not established.', '',
       f'Pre-run estimate: {resources["checkpoint"]["estimate"]["expected_cpu_hours"]:.2f} CPU-hours (extrapolated from Q0 wall time, not measured Q0 CPU). Actual summed generation worker wall time: {resources["generation_wall_s_summed"]:.1f} s; candidate matching worker wall time: {resources["candidate_matching_wall_s_summed"]:.1f} s; peak sampled Python RSS: {resources["peak_python_rss_bytes"]/1e6:.1f} MB; artifacts: {resources["artifact_bytes"]/1e6:.1f} MB. Process-tree CPU/RAM accounting is limited; see resource metrics.', '',
       '## Denominator reconciliation','', '```json',json.dumps(metrics['denominator_reconciliation'],indent=2),'```','',
       '## Scope limits','']
    lines += ['- '+x for x in metrics['limitations']]
    lines += ['- V-D embedding is budget-deferred, not shown to be infeasible on this hardware. Semantic-bleed performance of an embedding was not evaluated.',
              '- Reaction/PIP uses a generated graphic host panel; portrait footage is a crop of real interview footage. Corpus license and provenance details accompany every asset.',
              '- Lanczos upscaling, optical-flow interpolation and denoising are conventional transformations. No claim of a neural-upscaler or generative-model benchmark is made.',
              '- Registered references are normalized to 720p. The 720p transform is a resolution control; 480p and 360p are genuine reductions. Native 1080p-to-720p robustness was not established.',
              '', '## Stop condition','', 'E1 ends here. No production matcher, dashboard, crawling or enforcement was implemented. The scientific result requires review before further engineering authorization.','']
    path=OUT/'report.md';path.write_text('\n'.join(lines),encoding='utf-8');path.with_name(path.name+'.sha256').write_text(sha(path)+'\n')

if __name__=='__main__':
    import sys
    if len(sys.argv)>1 and sys.argv[1] in ['reproduce','reproduce-cross']: reproducibility(sys.argv[1]=='reproduce-cross')
    else: report()
