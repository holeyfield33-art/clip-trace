"""Editorial review of derived E1 reports; never changes frozen experiment inputs."""
from collections import Counter
from pathlib import Path
import shutil
from cliptrace_e1.e1_common import OUT, load, verify, dump, sha
from cliptrace_e1.e1_run import evaluation_guard, read_rows, decision, positive

profile = evaluation_guard()
archive = OUT / 'revisions/reporting-review'
archive.mkdir(parents=True, exist_ok=True)
for name in ['report.md', 'metrics.json', 'resource-metrics.json']:
    for suffix in ['', '.sha256']:
        src = OUT / (name + suffix)
        dst = archive / src.name
        if not dst.exists():
            shutil.copy2(src, dst)

metrics = verify(OUT / 'metrics.json')
old = 'No physical capture, trained embedding or validated calibrated fusion; AI-light operations are conventional open-source filters, not generative reconstruction.'
new = 'No physical capture or trained embedding. Fusion qualified on calibration but failed to generalize adequately to evaluation; AI-light operations are conventional open-source filters, not generative reconstruction.'
metrics['limitations'] = [new if x == old else x for x in metrics['limitations']]
dump(OUT / 'metrics.json', metrics)
resources = verify(OUT / 'resource-metrics.json')
resources['cpu_time_note'] = ('Summed worker wall times are not CPU time. Monitored stages have sampled process-tree CPU lower bounds. Acquisition, pilot work, corpus revision and archived preliminary passes are not comprehensively measured; totals do not represent the whole session.')
dump(OUT / 'resource-metrics.json', resources)

text = (archive / 'report.md').read_text(encoding='utf-8')
text = text.replace(old, new)
text = text.replace('Harsh positives are reported separately and excluded only from operating-point qualification.',
                    'Only visual operating-point qualification excludes harsh positives. Audio qualification includes all waveform-preserving transformations, including harsh cases.')
rows = read_rows(OUT / 'evaluation-results.jsonl')
receipts = read_rows(OUT / 'modality-decisions.jsonl')
assets = {a['asset_id']: a for a in verify(OUT / 'corpus-manifest.json')['assets']}
temporal = verify(OUT / 'temporal-metrics.json')
lines = ['## Interpretation and reporting review', '',
    'The frozen visual candidate exceeded the sensitivity target but failed specificity: 291/351 correct parents (82.9%) and 12/48 false positives (25.0%) on its qualification subset. Chromaprint failed both targets: 222/352 correct parents (63.1%) and 3/80 false positives (3.75%). Neither modality meets its original gate. No threshold or algorithm was repaired using these results.', '',
    'The visual false positives concentrate in deliberately confusing controls:', '',
    '| Method | Negative identity/category | Claimed parent | False-positive excerpts |',
    '|---|---|---|---:|']
for method in ['V-C', 'A-chromaprint']:
    counts = Counter((r['identity'], decision(r, method, profile['operating_points'][method])['parent'])
                     for r in rows if not positive(r, method) and decision(r, method, profile['operating_points'][method])['state'] == 'supported')
    for (identity, parent), count in sorted(counts.items()):
        lines.append(f'| {method} | {identity}: {assets[identity]["category"]} | {parent} | {count} |')
lines += ['', 'Shared templates and independently drawn semantic resemblance still caused false source attribution. The fixed runner-up margin did not resolve these cases. This is a failure of the tested common-content/ambiguity policy, not evidence that the negative works derive from the claimed source.', '',
    '### Multimodal routing, all 756 evaluation candidates', '',
    'These counts include short clips, harsh transforms and unavailable evidence as abstentions. They are binary routing metrics; their truth denominators differ by modality and are not the qualification subsets above.', '',
    '| Route | TP / expected positives | FP / expected negatives |', '|---|---:|---:|']
for route in ['visual_only', 'audio_only', 'visual_OR_audio', 'visual_AND_audio', 'calibrated']:
    result = metrics['multimodal'][route]
    t, f = result['tpr'], result['fpr']
    lines.append(f'| {route} | {t["numerator"]}/{t["denominator"]} | {f["numerator"]}/{f["denominator"]} |')
lines += ['', 'Fusion did not rescue specificity. The calibrated rule produced 15/84 false positives across all durations (15/48 among the >=5-second negative excerpts). Its calibration qualification is preserved; it is not a successful evaluation result.', '',
    'For the 56 audio-replacement candidates, 28 retained C3 support with C4 insufficient; the other 28 had both modalities insufficient. None received C4 support. There were 136 modality-disagreement cases overall. C5 was not evaluated.', '',
    '### Temporal limits', '',
    'V-C mean IoU was 0.640 over all 672 visual positives, including missing/wrong-parent alignments as zero. Correct-parent boundary errors averaged 0.482 s at the start and 0.870 s at the end, conditional on 544 available alignments. Among 303 supported positives, IoU was 0.828, start error 0.373 s and end error 0.663 s. However, 1/6 supported multifragment cases was falsely continuous (16.7%, exceeding the 5% gate), and raw diagnostics showed 6/21. Alignment remains CAUTION; the aggregate boundary improvement does not establish reliable fragmented provenance.', '',
    '| V-C transform | Expected visual positives | Mean IoU, missing = 0 | Start error s | End error s | False continuous / multifragment |',
    '|---|---:|---:|---:|---:|---:|']
for transform, result in temporal['V-C']['by_transform'].items():
    fmt = lambda x: 'unavailable' if x is None else f'{x:.3f}'
    fc = result['false_continuous']
    lines.append(f'| {transform} | {result["n_expected_positive"]} | {fmt(result["mean_iou_including_missing_as_zero"])} | {fmt(result["mean_start_error_s"])} | {fmt(result["mean_end_error_s"])} | {fc["numerator"]}/{fc["denominator"]} |')
lines += ['', '### Reproducibility comparison caveat', '',
    'Both tested runtimes regenerated all 12 candidate media files with identical bytes; all 12 candidate feature artifacts and all 16 source feature artifacts matched. Recorded score, alignment-coordinate and decode-timestamp deltas were zero. The frozen reproducibility checker compares JSON list rankings against fresh tuple rankings, which makes its `ranking_equal` flag false even for equal contents. A separate serialization-normalized audit matched all 60 same-runtime method/candidate rankings (`reproducibility-ranking-audit.json`). The original TOLERANCE_REPRODUCIBLE labels and raw flags remain unchanged, with this reporting defect disclosed. This is two-runtime reproduction on one machine, not independent-machine evidence.', '',
    '### Execution and audit notes', '',
    'The two generation failures were FFmpeg interpolation timeouts (E00501 and E00572); unsupported capture cases remain explicit. The interrupted development pass caused by a transient ground-truth/checksum write race was archived and fully rerun before freezing. All 34 tests passed before the frozen run. Final integrity checks are recorded in `final-audit.json`.', '',
    'This editorial review clarifies the visual-only harsh-case exclusion, corrects a stale fusion limitation sentence, and clarifies sampled CPU accounting. Original generated reports are retained in `revisions/reporting-review/`. Frozen source code, manifests, feature configuration, thresholds, raw scores, decisions and verdicts are unchanged.', '']
text = text.replace('## Stop condition', '\n'.join(lines) + '\n## Stop condition')
(OUT / 'report.md').write_text(text, encoding='utf-8')
(OUT / 'report.md.sha256').write_text(sha(OUT / 'report.md') + '\n', encoding='ascii')
evaluation_guard()
dump(OUT / 'report-review.json', dict(scope='Derived-report editorial review only',
     frozen_profile_sha256=sha(OUT / 'frozen-evaluation-profile.json'),
     script_sha256=sha(Path(__file__)),
     corrections=['visual-only harsh-positive exclusion wording', 'stale fusion limitation', 'CPU accounting scope', 'ranking list/tuple comparison defect disclosed'],
     raw_results_and_verdicts_unchanged=True))
dump(OUT / 'principal-sha256.json', {p.name:sha(p) for p in OUT.iterdir() if p.is_file() and p.suffix in ['.json', '.jsonl', '.md', '.py'] and p.name != 'principal-sha256.json'})
print('Editorial review complete; frozen profile unchanged.')
