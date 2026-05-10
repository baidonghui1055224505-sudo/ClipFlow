from __future__ import annotations
import sys
from faster_whisper import WhisperModel

_models: dict[str, WhisperModel] = {}
_DEFAULT_MODEL = "tiny"  # tiny ~10x faster, good enough for most content


def preload_model():
    """Preload default whisper model at startup."""
    if _DEFAULT_MODEL not in _models:
        print(f"[whisper] Loading {_DEFAULT_MODEL} model (CPU/int8)...", file=sys.stderr, flush=True)
        _models[_DEFAULT_MODEL] = WhisperModel(_DEFAULT_MODEL, device="cpu", compute_type="int8")
        print("[whisper] Model loaded.", file=sys.stderr, flush=True)
    return _models[_DEFAULT_MODEL]


def get_model(size: str = _DEFAULT_MODEL) -> WhisperModel:
    if size not in _models:
        print(f"[whisper] Loading {size} model (CPU/int8)...", file=sys.stderr, flush=True)
        _models[size] = WhisperModel(size, device="cpu", compute_type="int8")
        print("[whisper] Model loaded.", file=sys.stderr, flush=True)
    return _models[size]


def transcribe(audio_path: str, enable_diarization: bool = False, model_size: str = _DEFAULT_MODEL) -> dict:
    """Transcribe audio and return segments with timestamps.

    If enable_diarization is True and HF_TOKEN is set, also perform speaker diarization.
    model_size: 'tiny' (fast) or 'medium' (accurate).
    """
    import time
    model = get_model(model_size)
    t0 = time.time()
    print(f"[transcribe] Starting Whisper ({model_size}) transcription...", file=sys.stderr, flush=True)
    segments_raw, info = model.transcribe(
        audio_path,
        beam_size=1,
        best_of=1,
        word_timestamps=False,
        vad_filter=True,
    )
    print(f"[transcribe] Whisper done in {time.time()-t0:.1f}s", file=sys.stderr, flush=True)

    language = info.language
    segments = []
    for seg in segments_raw:
        segments.append({
            "id": len(segments),
            "start": round(seg.start, 2),
            "end": round(seg.end, 2),
            "text": seg.text.strip(),
            "speaker": "",
        })

    # Speaker diarization
    if enable_diarization:
        try:
            from speaker_diarize import diarize, merge_asr_diarization
            print(f"[transcribe] Starting speaker diarization...", file=sys.stderr, flush=True)
            t1 = time.time()
            diarize_segs = diarize(audio_path)
            print(f"[transcribe] Diarization done in {time.time()-t1:.1f}s", file=sys.stderr, flush=True)
            segments = merge_asr_diarization(segments, diarize_segs)
        except Exception as e:
            import traceback
            print(f"Warning: Speaker diarization failed: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)

    return {
        "language": language,
        "segments": segments,
        "full_text": " ".join(s["text"] for s in segments),
        "has_speakers": any(s.get("speaker") for s in segments),
    }
