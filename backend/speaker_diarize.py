from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

_pipeline = None


def preload_pipeline():
    """Preload pyannote pipeline at startup."""
    global _pipeline
    if _pipeline is None:
        import sys
        print("[pyannote] Loading speaker-diarization-3.1...", file=sys.stderr, flush=True)
        _pipeline = _get_pipeline()
        print("[pyannote] Pipeline loaded.", file=sys.stderr, flush=True)
    return _pipeline


def _get_pipeline():
    global _pipeline
    if _pipeline is None:
        from pyannote.audio import Pipeline
        token = os.environ.get("HF_TOKEN", "")
        _pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=token,
        )
    return _pipeline


def diarize(audio_path: str) -> list[dict]:
    """Run speaker diarization on audio. Returns speaker segments."""
    pipeline = _get_pipeline()
    output = pipeline(audio_path)

    segments = []
    for turn, _, speaker in output.itertracks(yield_label=True):
        segments.append({
            "start": round(turn.start, 2),
            "end": round(turn.end, 2),
            "speaker": speaker,
        })
    return segments


def merge_asr_diarization(asr_segments: list[dict], diarize_segments: list[dict]) -> list[dict]:
    """Assign speaker labels to ASR segments based on time overlap."""
    result = []
    for seg in asr_segments:
        mid = (seg["start"] + seg["end"]) / 2
        speaker = ""
        best_overlap = 0

        for d in diarize_segments:
            overlap_start = max(seg["start"], d["start"])
            overlap_end = min(seg["end"], d["end"])
            overlap = overlap_end - overlap_start
            if overlap > best_overlap:
                best_overlap = overlap
                speaker = d["speaker"]

        result.append({**seg, "speaker": speaker})
    return result
