"""Q0 experiment orchestration: corpus, partition, candidates, calibrate, evaluate, reproducibility."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .hashing import sha256_file, sha256_json
from .q0_corpus import materialize_q0_corpus
from .partition import (
    build_partition,
    write_partition,
    load_partition,
    candidate_partition,
)
from .transforms import generate_candidates_for_source
from .ground_truth import GroundTruthRecord, write_ground_truth, load_ground_truth
from .visual.frame_hash import extract as visual_extract, score_pair as visual_score
from .audio.fingerprint import extract as audio_extract, score_pair as audio_score
from .alignment.temporal import (
    align_frame_hashes,
    temporal_iou,
    start_end_error,
    fragmentation_error,
    false_continuous,
    padding_inflation,
)
from .retrieval.index import SimpleIndex
from .calibration import (
    ScoreSample,
    build_threshold_profile,
    write_threshold_profile,
    score_distributions,
)
from .evidence.artifacts import store_artifact
from .metrics.classification import binary_counts, rates
from .metrics.resources import measure
from .metrics.temporal import summarize_temporal


ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"
CORPUS = ROOT / "corpus"
CONFIGS = ROOT / "configs"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def q0_prepare_corpus() -> Dict[str, Any]:
    sources, negatives = materialize_q0_corpus(CORPUS)
    return {
        "n_sources": len(sources),
        "n_negatives": len(negatives),
        "source_ids": [s.asset_id for s in sources],
        "negative_ids": [n.asset_id for n in negatives],
    }


def q0_build_partition() -> str:
    sources = json.loads((CORPUS / "sources_manifest.json").read_text())
    negatives = json.loads((CORPUS / "negatives_manifest.json").read_text())
    pm = build_partition(
        [s["asset_id"] for s in sources],
        [n["asset_id"] for n in negatives],
        calibration_source_frac=0.5,
        calibration_negative_frac=0.5,
    )
    path = RESULTS / "q0" / "partition-manifest.json"
    digest = write_partition(pm, path)
    return digest


def q0_generate_candidates() -> Dict[str, Any]:
    cfg = yaml.safe_load((CONFIGS / "transforms-q0.yaml").read_text())
    tmap = cfg["transforms"]
    chains = [[tmap[name] for name in chain if name in tmap] for chain in cfg["chains"]]
    lengths_default = cfg.get("length_policy", {}).get("default", [3, 5, 10])

    sources = json.loads((CORPUS / "sources_manifest.json").read_text())
    negatives = json.loads((CORPUS / "negatives_manifest.json").read_text())
    out_dir = RESULTS / "q0" / "candidates"
    out_dir.mkdir(parents=True, exist_ok=True)

    all_recs: List[GroundTruthRecord] = []
    next_id = 1
    for src in sources:
        src_dict = {
            "asset_id": src["asset_id"],
            "path": src["path"],
            "duration_s": src["duration_s"],
        }
        recs = generate_candidates_for_source(
            src_dict, out_dir, chains, [float(x) for x in lengths_default], id_start=next_id
        )
        all_recs.extend(recs)
        next_id = max((int(r.candidate_id[1:]) for r in all_recs), default=0) + 1

    # pure negatives as non-derivative candidates (one per negative, full clip)
    for neg in negatives:
        cid = f"C{next_id:04d}"
        next_id += 1
        all_recs.append(
            GroundTruthRecord(
                candidate_id=cid,
                source_id=neg["asset_id"],  # partition uses negative id
                is_derivative=False,
                source_intervals_ms=[],
                candidate_intervals_ms=[],
                visual_ancestry=False,
                audio_ancestry=False,
                transcript_ancestry=False,
                transformations=["none"],
                candidate_sha256=neg["sha256"],
                candidate_path=neg["path"],
                clip_length_s=neg["duration_s"],
            )
        )

    gt_path = RESULTS / "q0" / "ground-truth.json"
    write_ground_truth(all_recs, gt_path)
    tmani = [
        {
            "candidate_id": r.candidate_id,
            "source_id": r.source_id,
            "is_derivative": r.is_derivative,
            "transformations": r.transformations,
            "sha256": r.candidate_sha256,
            "path": r.candidate_path,
            "clip_length_s": r.clip_length_s,
            "status": (r.extra or {}).get("status", "ok"),
        }
        for r in all_recs
    ]
    tpath = RESULTS / "q0" / "transformation-manifest.json"
    tpath.write_text(json.dumps(tmani, indent=2, sort_keys=True) + "\n")
    return {"n_candidates": len(all_recs), "n_failed": sum(1 for r in all_recs if (r.extra or {}).get("status") == "failed")}


def q0_run_matching(run_tag: str = "q0") -> str:
    """Extract fingerprints, retrieve, align; write results.jsonl. Returns run_id."""
    gt = load_ground_truth(RESULTS / "q0" / "ground-truth.json")
    sources = json.loads((CORPUS / "sources_manifest.json").read_text())
    pm = load_partition(RESULTS / "q0" / "partition-manifest.json")

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    run_dir = RESULTS / "q0" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    art_root = run_dir / "artifacts"
    art_root.mkdir(exist_ok=True)

    index = SimpleIndex()
    source_arts: Dict[str, Any] = {}
    with measure() as res_idx:
        for src in sources:
            v = visual_extract(Path(src["path"]), sample_fps=1.0, max_frames=16)
            a = audio_extract(Path(src["path"]), work_dir=run_dir / "audio_tmp")
            store_artifact(art_root / "fingerprints", v)
            store_artifact(art_root / "fingerprints", a)
            index.add(src["asset_id"], v, a)
            source_arts[src["asset_id"]] = {"visual": v, "audio": a}

    results_path = run_dir / "results.jsonl"
    retrieval_path = run_dir / "retrieval-topk.jsonl"
    n_ok = n_fail = 0
    with results_path.open("w") as fh, retrieval_path.open("w") as rh, measure() as res_run:
        for rec in gt:
            part = candidate_partition(rec.source_id, rec.is_derivative, pm)
            if (rec.extra or {}).get("status") == "failed" or not rec.candidate_sha256:
                row = {
                    "candidate_id": rec.candidate_id,
                    "partition": part,
                    "is_derivative": rec.is_derivative,
                    "true_source_id": rec.source_id if rec.is_derivative else None,
                    "status": "failed",
                    "visual": {"score": None, "status": "not_evaluated"},
                    "audio": {"score": None, "status": "not_evaluated"},
                }
                fh.write(json.dumps(row, sort_keys=True) + "\n")
                n_fail += 1
                continue

            cand_path = Path(rec.candidate_path)
            try:
                v_art = visual_extract(cand_path, sample_fps=1.0, max_frames=16)
                a_art = audio_extract(cand_path, work_dir=run_dir / "audio_tmp")
            except Exception as e:
                row = {
                    "candidate_id": rec.candidate_id,
                    "partition": part,
                    "is_derivative": rec.is_derivative,
                    "true_source_id": rec.source_id if rec.is_derivative else None,
                    "status": "failed",
                    "error": str(e),
                    "visual": {"score": None, "status": "not_evaluated"},
                    "audio": {"score": None, "status": "not_evaluated"},
                }
                fh.write(json.dumps(row, sort_keys=True) + "\n")
                n_fail += 1
                continue

            v_hash = store_artifact(art_root / "fingerprints", v_art)
            a_hash = store_artifact(art_root / "fingerprints", a_art)

            ranked_v = index.retrieve(v_art, a_art, k=5, modality="visual")
            ranked_a = index.retrieve(v_art, a_art, k=5, modality="audio")

            # ambiguity: margin between top-1 and top-2 visual
            margin_v = None
            if len(ranked_v) >= 2:
                margin_v = ranked_v[0][1] - ranked_v[1][1]
            disposition = "single"
            if margin_v is not None and margin_v < 0.08 and len(ranked_v) >= 2:
                disposition = "AMBIGUOUS"

            rh.write(json.dumps({
                "candidate_id": rec.candidate_id,
                "retrieval_visual": ranked_v,
                "retrieval_audio": ranked_a,
                "margin_visual": margin_v,
                "disposition": disposition,
            }, sort_keys=True) + "\n")

            # pairwise vs true parent (derivatives) and top hits
            targets = set()
            if rec.is_derivative and rec.source_id:
                targets.add(rec.source_id)
            for aid, _ in ranked_v[:3]:
                targets.add(aid)
            for aid, _ in ranked_a[:3]:
                targets.add(aid)

            pairwise: Dict[str, Any] = {}
            for aid in targets:
                if aid not in source_arts:
                    continue
                sa = source_arts[aid]
                vs = visual_score(v_art, sa["visual"])
                aus = audio_score(a_art, sa["audio"])
                aln = align_frame_hashes(
                    v_art.get("frame_hashes") or [],
                    sa["visual"].get("frame_hashes") or [],
                    sample_fps=float(v_art.get("sample_fps") or 1.5),
                )
                store_artifact(art_root / "alignments", {
                    "candidate_id": rec.candidate_id,
                    "source_id": aid,
                    **{k: v for k, v in aln.items() if k != "matched_pairs"},
                    "n_matched_pairs": len(aln.get("matched_pairs") or []),
                    "artifact_sha256": None,
                })

                iou = se = frag_err = fc = pad = None
                if rec.is_derivative and aid == rec.source_id and aln.get("source_intervals_s"):
                    truth_s = [[a / 1000.0, b / 1000.0] for a, b in rec.source_intervals_ms]
                    iou = temporal_iou(aln["source_intervals_s"], truth_s)
                    se = start_end_error(aln["source_intervals_s"], truth_s)
                    frag_err = fragmentation_error(
                        aln.get("n_fragments_claimed") or 0,
                        len(rec.source_intervals_ms),
                    )
                    fc = false_continuous(
                        aln.get("n_fragments_claimed") or 0,
                        len(rec.source_intervals_ms),
                    )
                    pad = padding_inflation(aln["source_intervals_s"], truth_s)

                pairwise[aid] = {
                    "visual": vs,
                    "audio": aus,
                    "alignment": {
                        k: v for k, v in aln.items() if k != "matched_pairs"
                    },
                    "temporal_iou": iou,
                    "start_error_s": (se or {}).get("start_error_s"),
                    "end_error_s": (se or {}).get("end_error_s"),
                    "fragmentation_error": frag_err,
                    "false_continuous": fc,
                    "padding_inflation": pad,
                }

            # scores vs true parent for calibration/eval
            true_v = true_a = None
            if rec.is_derivative and rec.source_id and rec.source_id in pairwise:
                true_v = pairwise[rec.source_id]["visual"].get("score")
                true_a = pairwise[rec.source_id]["audio"].get("score")
            elif not rec.is_derivative:
                # best score against any source as negative score
                best_v = best_a = None
                for pw in pairwise.values():
                    sc = (pw.get("visual") or {}).get("score")
                    if sc is not None:
                        best_v = sc if best_v is None else max(best_v, sc)
                    sca = (pw.get("audio") or {}).get("score")
                    if sca is not None:
                        best_a = sca if best_a is None else max(best_a, sca)
                true_v, true_a = best_v, best_a

            row = {
                "candidate_id": rec.candidate_id,
                "partition": part,
                "is_derivative": rec.is_derivative,
                "true_source_id": rec.source_id if rec.is_derivative else None,
                "clip_length_s": rec.clip_length_s,
                "transformations": rec.transformations,
                "visual_ancestry": rec.visual_ancestry,
                "audio_ancestry": rec.audio_ancestry,
                "status": "ok",
                "disposition": disposition,
                "margin_visual": margin_v,
                "visual_artifact_sha256": v_hash,
                "audio_artifact_sha256": a_hash,
                "score_visual_vs_true": true_v,
                "score_audio_vs_true": true_a,
                "visual_status": "ok" if true_v is not None else "not_evaluated",
                "audio_status": "ok" if true_a is not None else "not_evaluated",
                "retrieval_visual_top1": ranked_v[0][0] if ranked_v else None,
                "pairwise": pairwise,
            }
            fh.write(json.dumps(row, sort_keys=True) + "\n")
            n_ok += 1

    meta = {
        "run_id": run_id,
        "tag": run_tag,
        "started_finished": _utc(),
        "n_ok": n_ok,
        "n_failed": n_fail,
        "index_wall_s": res_idx.get("wall_s"),
        "run_wall_s": res_run.get("wall_s"),
        "max_rss_kb": res_run.get("max_rss_kb"),
        "n_sources_indexed": len(sources),
    }
    (run_dir / "run_meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    return run_id


def q0_calibrate(run_id: str) -> str:
    """Build threshold profile from calibration partition only. Returns profile sha256."""
    run_dir = RESULTS / "q0" / "runs" / run_id
    rows = [json.loads(l) for l in (run_dir / "results.jsonl").read_text().splitlines() if l.strip()]

    samples_v: List[ScoreSample] = []
    samples_a: List[ScoreSample] = []
    for r in rows:
        if r.get("partition") != "calibration":
            continue
        if r.get("status") != "ok":
            continue
        # visual
        sv = r.get("score_visual_vs_true")
        if sv is not None and r.get("visual_status") == "ok":
            is_pos = bool(r.get("is_derivative") and r.get("visual_ancestry"))
            if not r.get("is_derivative"):
                is_pos = False
            samples_v.append(ScoreSample(r["candidate_id"], float(sv), is_pos, "visual"))
        # audio
        sa = r.get("score_audio_vs_true")
        if sa is not None and r.get("audio_status") == "ok":
            is_pos = bool(r.get("is_derivative") and r.get("audio_ancestry"))
            if not r.get("is_derivative"):
                is_pos = False
            samples_a.append(ScoreSample(r["candidate_id"], float(sa), is_pos, "audio"))

    profile = build_threshold_profile(
        {"visual": samples_v, "audio": samples_a},
        rule="max_tpr_at_fpr_le_0.20",
    )
    path = run_dir / "threshold-profile.json"
    digest = write_threshold_profile(profile, path)

    # score distributions artifact
    dist = {
        "visual": score_distributions(samples_v),
        "audio": score_distributions(samples_a),
        "n_visual_samples": len(samples_v),
        "n_audio_samples": len(samples_a),
    }
    (run_dir / "score-distributions.json").write_text(json.dumps(dist, indent=2, sort_keys=True) + "\n")
    return digest


def q0_evaluate(run_id: str) -> Dict[str, Any]:
    """Apply frozen threshold profile to evaluation partition only."""
    run_dir = RESULTS / "q0" / "runs" / run_id
    profile = json.loads((run_dir / "threshold-profile.json").read_text())
    thr_v = (profile.get("modalities") or {}).get("visual", {}).get("threshold")
    thr_a = (profile.get("modalities") or {}).get("audio", {}).get("threshold")

    rows = [json.loads(l) for l in (run_dir / "results.jsonl").read_text().splitlines() if l.strip()]
    ytv: List[bool] = []
    ypv: List[bool] = []
    yta: List[bool] = []
    ypa: List[bool] = []
    temporal_rows: List[Dict[str, Any]] = []
    ambiguous = 0
    failed = 0
    recall_at = {1: 0, 5: 0}
    n_der = 0

    for r in rows:
        if r.get("status") != "ok":
            failed += 1
            continue
        if r.get("disposition") == "AMBIGUOUS":
            ambiguous += 1
        if r.get("partition") != "evaluation":
            continue

        is_der = bool(r.get("is_derivative"))
        vis_anc = bool(r.get("visual_ancestry"))
        aud_anc = bool(r.get("audio_ancestry"))
        sv = r.get("score_visual_vs_true")
        sa = r.get("score_audio_vs_true")

        # visual classification (only when score present)
        if sv is not None and thr_v is not None:
            ytv.append(is_der and vis_anc)
            ypv.append(sv >= thr_v)
        # audio
        if sa is not None and thr_a is not None:
            yta.append(is_der and aud_anc)
            ypa.append(sa >= thr_a)

        if is_der:
            n_der += 1
            top1 = r.get("retrieval_visual_top1")
            if top1 == r.get("true_source_id"):
                recall_at[1] += 1
            # approximate recall@5 from pairwise keys
            if r.get("true_source_id") in (r.get("pairwise") or {}):
                recall_at[5] += 1

            # temporal from true parent pairwise
            pw = (r.get("pairwise") or {}).get(r.get("true_source_id") or "", {})
            temporal_rows.append({
                "iou": pw.get("temporal_iou"),
                "start_error_s": pw.get("start_error_s"),
                "end_error_s": pw.get("end_error_s"),
                "false_continuous": pw.get("false_continuous"),
                "fragmentation_error": pw.get("fragmentation_error"),
                "padding_inflation": pw.get("padding_inflation"),
            })

    metrics = {
        "run_id": run_id,
        "profile_sha256": profile.get("profile_sha256"),
        "thresholds": {"visual": thr_v, "audio": thr_a},
        "selection_rule": profile.get("selection_rule"),
        "evaluation_visual": rates(*binary_counts(ytv, ypv)) if ytv else {},
        "evaluation_audio": rates(*binary_counts(yta, ypa)) if yta else {},
        "temporal": summarize_temporal(temporal_rows),
        "retrieval_recall_at_1": (recall_at[1] / n_der) if n_der else None,
        "retrieval_recall_at_5": (recall_at[5] / n_der) if n_der else None,
        "n_evaluation_scored_visual": len(ytv),
        "n_evaluation_scored_audio": len(yta),
        "n_ambiguous_all_partitions": ambiguous,
        "n_failed": failed,
        "n_derivative_eval_approx": n_der,
    }
    (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n")
    return metrics


def q0_reproducibility(run_id_a: str, run_id_b: str) -> Dict[str, Any]:
    """Compare two runs on same config."""
    def load_scores(rid: str) -> Dict[str, Dict[str, Any]]:
        path = RESULTS / "q0" / "runs" / rid / "results.jsonl"
        out = {}
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            out[r["candidate_id"]] = {
                "score_visual_vs_true": r.get("score_visual_vs_true"),
                "score_audio_vs_true": r.get("score_audio_vs_true"),
                "visual_artifact_sha256": r.get("visual_artifact_sha256"),
                "status": r.get("status"),
                "disposition": r.get("disposition"),
            }
        return out

    a = load_scores(run_id_a)
    b = load_scores(run_id_b)
    ids = sorted(set(a) | set(b))
    same_ids = set(a) == set(b)
    n = 0
    n_score_match = 0
    n_hash_match = 0
    n_status_match = 0
    max_v_diff = 0.0
    for cid in ids:
        if cid not in a or cid not in b:
            continue
        n += 1
        if a[cid]["status"] == b[cid]["status"]:
            n_status_match += 1
        if a[cid]["visual_artifact_sha256"] and a[cid]["visual_artifact_sha256"] == b[cid]["visual_artifact_sha256"]:
            n_hash_match += 1
        sa, sb = a[cid]["score_visual_vs_true"], b[cid]["score_visual_vs_true"]
        if sa is not None and sb is not None:
            diff = abs(sa - sb)
            max_v_diff = max(max_v_diff, diff)
            if diff < 1e-9:
                n_score_match += 1
        elif sa is None and sb is None:
            n_score_match += 1

    if same_ids and n_hash_match == n and n_score_match == n:
        klass = "BIT_DETERMINISTIC"
    elif max_v_diff < 1e-3 and n_status_match == n:
        klass = "TOLERANCE_REPRODUCIBLE"
    else:
        klass = "UNSTABLE"

    report = {
        "run_a": run_id_a,
        "run_b": run_id_b,
        "same_candidate_ids": same_ids,
        "n_compared": n,
        "n_status_match": n_status_match,
        "n_artifact_hash_match": n_hash_match,
        "n_score_exact_match": n_score_match,
        "max_visual_score_diff": max_v_diff,
        "classification": klass,
    }
    out = RESULTS / "q0" / "reproducibility.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report
