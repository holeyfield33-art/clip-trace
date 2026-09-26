"""Simple in-memory retrieval index for Stage 1."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from ..visual.frame_hash import score_pair as visual_score
from ..audio.fingerprint import score_pair as audio_score


class SimpleIndex:
    """Holds source artifacts and returns ranked candidates by modality score."""

    def __init__(self) -> None:
        self.sources: Dict[str, Dict[str, Any]] = {}  # asset_id -> {visual, audio}

    def add(self, asset_id: str, visual_art: Dict[str, Any], audio_art: Dict[str, Any]) -> None:
        self.sources[asset_id] = {"visual": visual_art, "audio": audio_art}

    def retrieve(
        self,
        candidate_visual: Dict[str, Any],
        candidate_audio: Dict[str, Any],
        k: int = 10,
        modality: str = "visual",
    ) -> List[Tuple[str, float]]:
        scores: List[Tuple[str, float]] = []
        for asset_id, arts in self.sources.items():
            if modality == "visual":
                r = visual_score(candidate_visual, arts["visual"])
            elif modality == "audio":
                r = audio_score(candidate_audio, arts["audio"])
            else:
                r = {"score": None, "status": "not_evaluated"}
            sc = r.get("score")
            if sc is None:
                continue
            scores.append((asset_id, float(sc)))
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:k]
