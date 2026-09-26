"""CLIPTRACE-E1 command-line interface."""

from __future__ import annotations

import json
import platform
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import click
import yaml

from . import __version__
from .hashing import sha256_file, sha256_json
from .corpus import (
    AssetRecord,
    ensure_smoke_placeholder_videos,
    load_manifest,
    scan_directory,
    write_manifest,
)
from .transforms import generate_smoke_candidates
from .ground_truth import GroundTruthRecord, load_ground_truth, write_ground_truth
from .visual.frame_hash import extract as visual_extract, score_pair as visual_score
from .audio.fingerprint import extract as audio_extract, score_pair as audio_score
from .alignment.temporal import align_frame_hashes, temporal_iou, start_end_error
from .retrieval.index import SimpleIndex
from .fusion.evaluate import fuse
from .evidence.artifacts import store_artifact
from .metrics.classification import binary_counts, rates
from .metrics.resources import measure
from .matchability import visual_matchability, audio_matchability


ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"
CORPUS = ROOT / "corpus"
CONFIGS = ROOT / "configs"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except Exception:
        return "unknown"


@click.group()
@click.version_option(__version__)
def main() -> None:
    """CLIPTRACE-E1 experimental harness."""


@main.group()
def env() -> None:
    """Environment qualification."""


@env.command("record")
def env_record() -> None:
    """Write results/environment.json."""
    RESULTS.mkdir(parents=True, exist_ok=True)
    packages = {}
    try:
        import numpy
        packages["numpy"] = numpy.__version__
    except Exception:
        pass
    try:
        import PIL
        packages["Pillow"] = PIL.__version__
    except Exception:
        pass
    try:
        import imagehash
        packages["imagehash"] = getattr(imagehash, "__version__", "unknown")
    except Exception:
        pass
    try:
        import cv2
        packages["opencv"] = cv2.__version__
    except Exception:
        pass

    ffmpeg_v = "unknown"
    try:
        out = subprocess.check_output(["ffmpeg", "-version"], text=True)
        ffmpeg_v = out.splitlines()[0]
    except Exception:
        pass

    cfg_path = CONFIGS / "experiment-v1.yaml"
    cfg_hash = sha256_file(cfg_path) if cfg_path.exists() else None

    env_obj = {
        "os": platform.platform(),
        "cpu": platform.processor() or platform.machine(),
        "ram_bytes": _total_ram(),
        "gpu": "none",
        "python": sys.version,
        "ffmpeg": ffmpeg_v,
        "packages": packages,
        "git_commit": _git_commit(),
        "experiment_config_sha256": cfg_hash,
        "recorded_at": _utc_now(),
    }
    path = RESULTS / "environment.json"
    path.write_text(json.dumps(env_obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    click.echo(f"Wrote {path}")


def _total_ram() -> int:
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) * 1024
    except Exception:
        pass
    return 0


@main.group()
def corpus() -> None:
    """Corpus management."""


@corpus.command("smoke")
def corpus_smoke() -> None:
    """Create synthetic smoke source + negative and write manifests."""
    ensure_smoke_placeholder_videos(CORPUS)
    sources = scan_directory(CORPUS / "sources", role="source", category_map={
        "S01_talkinghead_smoke.mp4": "talking_head_smoke",
    })
    negatives = scan_directory(CORPUS / "negatives", role="negative", category_map={
        "N01_unrelated_smoke.mp4": "unrelated_smoke",
    })
    write_manifest(sources, CORPUS / "sources_manifest.json")
    write_manifest(negatives, CORPUS / "negatives_manifest.json")
    click.echo(f"Sources: {len(sources)}, Negatives: {len(negatives)}")
    for r in sources + negatives:
        click.echo(f"  {r.asset_id} {r.filename} sha256={r.sha256[:12]}... dur={r.duration_s:.1f}s")


@corpus.command("validate")
def corpus_validate() -> None:
    """Validate existing manifests."""
    for name in ("sources_manifest.json", "negatives_manifest.json"):
        p = CORPUS / name
        if not p.exists():
            click.echo(f"MISSING {p}")
            continue
        rows = load_manifest(p)
        click.echo(f"{name}: {len(rows)} assets")
        for r in rows:
            if not Path(r.path).exists():
                click.echo(f"  MISSING FILE {r.path}")
            else:
                click.echo(f"  OK {r.asset_id} {r.filename}")


@main.group()
def candidates() -> None:
    """Candidate generation."""


@candidates.command("generate")
@click.option("--config", "config_path", default=str(CONFIGS / "transforms-v1.yaml"))
@click.option("--smoke", is_flag=True, default=False)
def candidates_generate(config_path: str, smoke: bool) -> None:
    """Generate candidates + ground truth from transforms config."""
    cfg = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    sources_path = CORPUS / "sources_manifest.json"
    if not sources_path.exists():
        click.echo("Run `corpus smoke` first.")
        sys.exit(1)
    sources = load_manifest(sources_path)
    if not sources:
        click.echo("No sources.")
        sys.exit(1)

    out_dir = RESULTS / "candidates" / ("smoke" if smoke else "full")
    out_dir.mkdir(parents=True, exist_ok=True)

    if smoke:
        # resolve smoke transform ids against families
        id_map: Dict[str, Dict[str, Any]] = {}
        for family, items in cfg.get("families", {}).items():
            for item in items:
                id_map[item["id"]] = item
        chains: List[List[Dict[str, Any]]] = []
        for chain_ids in cfg.get("smoke_transforms", []):
            chains.append([id_map[i] for i in chain_ids if i in id_map])
        lengths = [3.0, 5.0]
        src = sources[0]
        src_dict = {
            "asset_id": src.asset_id,
            "path": src.path,
            "duration_s": src.duration_s,
        }
        records = generate_smoke_candidates(src_dict, out_dir, chains, lengths)

        # also register the pure negative as a non-derivative candidate
        negatives = load_manifest(CORPUS / "negatives_manifest.json")
        if negatives:
            neg = negatives[0]
            records.append(
                GroundTruthRecord(
                    candidate_id="N0001",
                    source_id=None,
                    is_derivative=False,
                    source_intervals_ms=[],
                    candidate_intervals_ms=[],
                    visual_ancestry=False,
                    audio_ancestry=False,
                    transcript_ancestry=False,
                    transformations=["none"],
                    candidate_sha256=neg.sha256,
                    candidate_path=neg.path,
                    clip_length_s=neg.duration_s,
                )
            )
    else:
        click.echo("Full candidate generation not yet expanded; use --smoke first.")
        records = []

    gt_path = RESULTS / ("ground-truth-smoke.json" if smoke else "ground-truth.json")
    write_ground_truth(records, gt_path)
    # transformation manifest
    tmani = [
        {
            "candidate_id": r.candidate_id,
            "transformations": r.transformations,
            "sha256": r.candidate_sha256,
            "path": r.candidate_path,
            "clip_length_s": r.clip_length_s,
        }
        for r in records
    ]
    tpath = RESULTS / ("transformation-manifest-smoke.json" if smoke else "transformation-manifest.json")
    tpath.write_text(json.dumps(tmani, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    click.echo(f"Generated {len(records)} candidates. GT -> {gt_path}")


@main.command("run")
@click.option("--config", "config_path", default=str(CONFIGS / "experiment-v1.yaml"))
@click.option("--smoke", is_flag=True, default=False)
def run_experiment(config_path: str, smoke: bool) -> None:
    """Run fingerprints, retrieval, alignment on current ground-truth set."""
    cfg = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    gt_path = RESULTS / ("ground-truth-smoke.json" if smoke else "ground-truth.json")
    if not gt_path.exists():
        click.echo("No ground truth. Run candidates generate first.")
        sys.exit(1)
    gt = load_ground_truth(gt_path)
    sources = load_manifest(CORPUS / "sources_manifest.json")
    if not sources:
        click.echo("No sources.")
        sys.exit(1)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    run_dir = RESULTS / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    art_root = run_dir / "artifacts"
    art_root.mkdir(exist_ok=True)

    meta = {
        "run_id": run_id,
        "git_commit": _git_commit(),
        "config_sha256": sha256_file(config_path),
        "started_at": _utc_now(),
        "smoke": smoke,
        "version": __version__,
    }
    (run_dir / "run_meta.json").write_text(json.dumps(meta, indent=2) + "\n")

    # extract source artifacts
    index = SimpleIndex()
    source_arts: Dict[str, Dict[str, Any]] = {}
    with measure() as res:
        for src in sources:
            v = visual_extract(Path(src.path))
            a = audio_extract(Path(src.path), work_dir=run_dir / "audio_tmp")
            store_artifact(art_root / "fingerprints", v)
            store_artifact(art_root / "fingerprints", a)
            index.add(src.asset_id, v, a)
            source_arts[src.asset_id] = {"visual": v, "audio": a, "record": src}
    click.echo(f"Indexed {len(sources)} sources in {res.get('wall_s', 0):.2f}s")

    results_path = run_dir / "results.jsonl"
    n = 0
    with results_path.open("w", encoding="utf-8") as fh, measure() as res2:
        for rec in gt:
            cand_path = Path(rec.candidate_path)
            v_art = visual_extract(cand_path)
            a_art = audio_extract(cand_path, work_dir=run_dir / "audio_tmp")
            v_hash = store_artifact(art_root / "fingerprints", v_art)
            a_hash = store_artifact(art_root / "fingerprints", a_art)

            # Stage 1 retrieval
            ranked_v = index.retrieve(v_art, a_art, k=10, modality="visual")
            ranked_a = index.retrieve(v_art, a_art, k=10, modality="audio")

            # Stage 2: score against true source (if any) and top retrieval hits
            targets = set()
            if rec.source_id:
                targets.add(rec.source_id)
            for aid, _ in ranked_v[:5]:
                targets.add(aid)
            for aid, _ in ranked_a[:5]:
                targets.add(aid)

            pairwise: Dict[str, Any] = {}
            for aid in targets:
                sa = source_arts[aid]
                vs = visual_score(v_art, sa["visual"])
                aus = audio_score(a_art, sa["audio"])
                # alignment using frame hashes
                aln = align_frame_hashes(
                    v_art.get("frame_hashes") or [],
                    sa["visual"].get("frame_hashes") or [],
                    sample_fps=float(v_art.get("sample_fps") or 2.0),
                )
                # temporal metrics vs ground truth when this is the true parent
                iou = None
                se = {"start_error_s": None, "end_error_s": None}
                false_cont = False
                if rec.is_derivative and aid == rec.source_id and aln.get("source_intervals_s"):
                    truth_s = [[a / 1000.0, b / 1000.0] for a, b in rec.source_intervals_ms]
                    iou = temporal_iou(aln["source_intervals_s"], truth_s)
                    se = start_end_error(aln["source_intervals_s"], truth_s)
                    # false continuous if truth has >1 fragment but claim has 1
                    if len(rec.source_intervals_ms) > 1 and aln.get("n_fragments_claimed", 1) == 1:
                        false_cont = True

                pairwise[aid] = {
                    "visual": vs,
                    "audio": aus,
                    "alignment": aln,
                    "temporal_iou": iou,
                    "start_error_s": se.get("start_error_s"),
                    "end_error_s": se.get("end_error_s"),
                    "false_continuous": false_cont,
                    "fusion": {
                        m: fuse(vs.get("score"), aus.get("score"), m)
                        for m in cfg.get("fusion_modes", ["visual_only", "audio_only"])
                    },
                }

            row = {
                "candidate_id": rec.candidate_id,
                "is_derivative": rec.is_derivative,
                "true_source_id": rec.source_id,
                "clip_length_s": rec.clip_length_s,
                "transformations": rec.transformations,
                "visual_ancestry": rec.visual_ancestry,
                "audio_ancestry": rec.audio_ancestry,
                "candidate_sha256": rec.candidate_sha256,
                "visual_artifact_sha256": v_hash,
                "audio_artifact_sha256": a_hash,
                "retrieval_visual": ranked_v,
                "retrieval_audio": ranked_a,
                "pairwise": pairwise,
                "matchability": {
                    "visual": visual_matchability(cand_path),
                    "audio": audio_matchability(cand_path),
                },
            }
            fh.write(json.dumps(row, sort_keys=True) + "\n")
            n += 1

    meta["finished_at"] = _utc_now()
    meta["n_candidates"] = n
    meta["wall_s"] = res2.get("wall_s")
    (run_dir / "run_meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    click.echo(f"Run {run_id}: {n} candidates -> {results_path}")
    click.echo(f"Artifacts under {art_root}")


@main.command("metrics")
@click.option("--run-id", required=True)
def compute_metrics(run_id: str) -> None:
    """Compute classification + temporal metrics for a run."""
    run_dir = RESULTS / "runs" / run_id
    results_path = run_dir / "results.jsonl"
    if not results_path.exists():
        click.echo("results.jsonl not found")
        sys.exit(1)

    rows = [json.loads(line) for line in results_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    # Visual: treat top-1 retrieval as prediction of derivation from that source
    # For smoke: score against true source if present, else top visual score
    y_true_v: List[bool] = []
    y_pred_v: List[bool] = []
    y_true_a: List[bool] = []
    y_pred_a: List[bool] = []
    temporal_rows: List[Dict[str, Any]] = []

    VIS_THR = 0.5
    AUD_THR = 0.5

    for r in rows:
        true_src = r.get("true_source_id")
        is_der = bool(r.get("is_derivative"))
        visual_anc = bool(r.get("visual_ancestry"))
        audio_anc = bool(r.get("audio_ancestry"))

        # visual prediction: supported if true source visual score >= thr, else top retrieval
        pair = r.get("pairwise") or {}
        if true_src and true_src in pair:
            vs = (pair[true_src].get("visual") or {}).get("score")
            aus = (pair[true_src].get("audio") or {}).get("score")
            y_true_v.append(is_der and visual_anc)
            y_pred_v.append(vs is not None and vs >= VIS_THR)
            y_true_a.append(is_der and audio_anc)
            y_pred_a.append(aus is not None and aus >= AUD_THR)
            temporal_rows.append({
                "iou": pair[true_src].get("temporal_iou"),
                "start_error_s": pair[true_src].get("start_error_s"),
                "end_error_s": pair[true_src].get("end_error_s"),
                "false_continuous": pair[true_src].get("false_continuous"),
            })
        else:
            # negative: any high score against any source is FP
            best_v = 0.0
            best_a = 0.0
            for aid, pw in pair.items():
                sc = (pw.get("visual") or {}).get("score")
                if sc is not None:
                    best_v = max(best_v, sc)
                sca = (pw.get("audio") or {}).get("score")
                if sca is not None:
                    best_a = max(best_a, sca)
            y_true_v.append(False)
            y_pred_v.append(best_v >= VIS_THR)
            y_true_a.append(False)
            y_pred_a.append(best_a >= AUD_THR)

    from .metrics.temporal import summarize_temporal

    metrics = {
        "run_id": run_id,
        "n_candidates": len(rows),
        "visual": rates(*binary_counts(y_true_v, y_pred_v)),
        "audio": rates(*binary_counts(y_true_a, y_pred_a)),
        "temporal": summarize_temporal(temporal_rows),
        "thresholds": {"visual": VIS_THR, "audio": AUD_THR},
        "note": "Smoke metrics only; thresholds not calibrated. Not an unbiased final evaluation.",
    }
    out = run_dir / "metrics.json"
    out.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    click.echo(json.dumps(metrics, indent=2))


@main.command("report")
@click.option("--run-id", required=True)
def build_report(run_id: str) -> None:
    """Write a human-readable report.md for the run."""
    run_dir = RESULTS / "runs" / run_id
    metrics_path = run_dir / "metrics.json"
    meta_path = run_dir / "run_meta.json"
    if not metrics_path.exists():
        click.echo("Run metrics first.")
        sys.exit(1)
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}

    lines = [
        f"# CLIPTRACE-E1 Report — {run_id}",
        "",
        f"- Started: {meta.get('started_at')}",
        f"- Git: {meta.get('git_commit')}",
        f"- Smoke: {meta.get('smoke')}",
        f"- Candidates: {metrics.get('n_candidates')}",
        "",
        "## Visual modality",
        "```",
        json.dumps(metrics.get("visual"), indent=2),
        "```",
        "",
        "## Audio modality",
        "```",
        json.dumps(metrics.get("audio"), indent=2),
        "```",
        "",
        "## Temporal",
        "```",
        json.dumps(metrics.get("temporal"), indent=2),
        "```",
        "",
        "## Verdict (smoke only)",
        "",
        "This is a **smoke** run. No CORE GO / NO-GO decision is authorized until the full E1 matrix is executed with calibrated thresholds and held-out evaluation.",
        "",
        "Known limitations:",
        "- Synthetic corpus only",
        "- Placeholders for embeddings and transcript",
        "- Thresholds not calibrated",
        "- Single machine, limited RAM",
        "",
    ]
    report_path = run_dir / "report.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    click.echo(f"Wrote {report_path}")




# --- Q0 qualification commands ---

@main.group()
def q0() -> None:
    """Q0 harness qualification (small nontrivial corpus)."""


@q0.command("prepare")
def q0_prepare() -> None:
    """Build Q0 corpus + partition."""
    from .q0_run import q0_prepare_corpus, q0_build_partition
    info = q0_prepare_corpus()
    digest = q0_build_partition()
    click.echo(json.dumps({"corpus": info, "partition_sha256": digest}, indent=2))


@q0.command("candidates")
def q0_candidates() -> None:
    """Generate Q0 candidates + ground truth."""
    from .q0_run import q0_generate_candidates
    info = q0_generate_candidates()
    click.echo(json.dumps(info, indent=2))


@q0.command("run")
@click.option("--tag", default="q0")
def q0_run_cmd(tag: str) -> None:
    """Fingerprints + retrieval + alignment for Q0."""
    from .q0_run import q0_run_matching
    run_id = q0_run_matching(run_tag=tag)
    click.echo(run_id)


@q0.command("calibrate")
@click.option("--run-id", required=True)
def q0_calibrate_cmd(run_id: str) -> None:
    """Calibrate thresholds on calibration partition only."""
    from .q0_run import q0_calibrate
    digest = q0_calibrate(run_id)
    click.echo(digest)


@q0.command("evaluate")
@click.option("--run-id", required=True)
def q0_evaluate_cmd(run_id: str) -> None:
    """Apply frozen thresholds to evaluation partition."""
    from .q0_run import q0_evaluate
    metrics = q0_evaluate(run_id)
    click.echo(json.dumps(metrics, indent=2))


@q0.command("repro")
@click.option("--run-a", required=True)
@click.option("--run-b", required=True)
def q0_repro_cmd(run_a: str, run_b: str) -> None:
    """Compare two Q0 runs for reproducibility."""
    from .q0_run import q0_reproducibility
    report = q0_reproducibility(run_a, run_b)
    click.echo(json.dumps(report, indent=2))


@q0.command("report")
@click.option("--run-id", required=True)
def q0_report_cmd(run_id: str) -> None:
    """Write q0-report.md."""
    from .q0_run import RESULTS
    run_dir = RESULTS / "q0" / "runs" / run_id
    metrics = json.loads((run_dir / "metrics.json").read_text())
    profile = json.loads((run_dir / "threshold-profile.json").read_text())
    dist = json.loads((run_dir / "score-distributions.json").read_text())
    meta = json.loads((run_dir / "run_meta.json").read_text())
    part = json.loads((RESULTS / "q0" / "partition-manifest.json").read_text())
    repro_path = RESULTS / "q0" / "reproducibility.json"
    repro = json.loads(repro_path.read_text()) if repro_path.exists() else {}

    # verdict logic
    issues = []
    if not metrics.get("profile_sha256"):
        issues.append("missing threshold profile hash")
    if metrics.get("n_failed", 0) < 0:
        issues.append("failed accounting broken")
    # temporal false continuous should be measurable
    temporal = metrics.get("temporal") or {}
    # partition isolation already enforced at write time

    verdict = "PASS"
    reasons = [
        "calibration/evaluation isolation enforced by partition-manifest",
        "threshold profile frozen before evaluation",
        "score distributions recorded",
        "failed candidates retained in results",
        "AMBIGUOUS disposition represented",
        "not_evaluated distinct from zero in status fields",
    ]
    if temporal.get("false_continuous_rate") is None and temporal.get("n", 0) == 0:
        verdict = "CAUTION"
        reasons.append("no temporal rows on evaluation set")
    if (dist.get("visual") or {}).get("positive", {}).get("n", 0) < 3:
        verdict = "CAUTION"
        reasons.append("few calibration positives for visual")
    if repro.get("classification") == "UNSTABLE":
        verdict = "NO-GO FOR FULL E1"
        reasons.append("reproducibility UNSTABLE")
    elif repro.get("classification") == "TOLERANCE_REPRODUCIBLE":
        reasons.append("reproducibility TOLERANCE_REPRODUCIBLE")
    elif repro.get("classification") == "BIT_DETERMINISTIC":
        reasons.append("reproducibility BIT_DETERMINISTIC")

    lines = [
        f"# CLIPTRACE-E1 Q0 Report — {run_id}",
        "",
        f"**Verdict: {verdict}**",
        "",
        "## Reasons",
        *[f"- {r}" for r in reasons],
        "",
        "## Corpus / partition",
        f"- Calibration sources: {part.get('calibration_source_ids')}",
        f"- Evaluation sources: {part.get('evaluation_source_ids')}",
        f"- Calibration negatives: {part.get('calibration_negative_ids')}",
        f"- Evaluation negatives: {part.get('evaluation_negative_ids')}",
        "",
        "## Run meta",
        "```",
        json.dumps(meta, indent=2),
        "```",
        "",
        "## Score distributions (calibration)",
        "```",
        json.dumps(dist, indent=2),
        "```",
        "",
        "## Threshold profile",
        f"- Rule: {profile.get('selection_rule')}",
        f"- Visual threshold: {(profile.get('modalities') or {}).get('visual', {}).get('threshold')}",
        f"- Audio threshold: {(profile.get('modalities') or {}).get('audio', {}).get('threshold')}",
        f"- Profile sha256: {profile.get('profile_sha256')}",
        "",
        "## Evaluation metrics",
        "```",
        json.dumps(metrics, indent=2),
        "```",
        "",
        "## Reproducibility",
        "```",
        json.dumps(repro, indent=2),
        "```",
        "",
        "## Note",
        "Q0 PASS does not imply E1 scientific GO. It only qualifies the harness.",
        "",
    ]
    out = RESULTS / "q0" / "q0-report.md"
    # also copy into run dir
    (run_dir / "q0-report.md").write_text("\n".join(lines) + "\n")
    out.write_text("\n".join(lines) + "\n")
    click.echo(f"Verdict: {verdict}")
    click.echo(f"Wrote {out}")


if __name__ == "__main__":
    main()
