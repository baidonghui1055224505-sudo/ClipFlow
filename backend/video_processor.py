from __future__ import annotations
import shutil
import subprocess
import uuid
from pathlib import Path

TEMP_DIR = Path(__file__).parent.parent / "temp"
TEMP_DIR.mkdir(exist_ok=True)

# Find ffmpeg — try PATH first, then common locations per platform
import platform
_FFMPEG = shutil.which("ffmpeg")
if not _FFMPEG:
    if platform.system() == "Windows":
        _FFMPEG = shutil.which("ffmpeg.exe") or r"C:\ffmpeg\bin\ffmpeg.exe"
    else:
        _FFMPEG = "/usr/local/bin/ffmpeg"
if not _FFMPEG or not Path(_FFMPEG).exists():
    _FFMPEG = "ffmpeg"  # fall back to hoping it's in PATH


def _run_ffmpeg(args: list[str], description: str) -> None:
    cmd = [_FFMPEG, "-y", "-v", "error"] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg {description} failed: {result.stderr}")


def extract_audio(video_path: str | Path) -> str:
    """Extract audio from video as 16kHz mono WAV for Whisper."""
    audio_path = str(TEMP_DIR / f"audio_{uuid.uuid4().hex[:8]}.wav")
    _run_ffmpeg(
        ["-i", str(video_path), "-vn", "-acodec", "pcm_s16le",
         "-ar", "16000", "-ac", "1", audio_path],
        "audio extraction",
    )
    return audio_path


def cut_segments(video_path: str | Path, segments: list[dict], output_dir: str | Path) -> list[str]:
    """Cut video segments by timestamp pairs. Returns list of clip paths.

    Re-encodes with ultrafast preset for frame-accurate cuts (avoids keyframe
    snapping that causes repeating frames with stream copy).
    """
    clips = []
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for i, seg in enumerate(segments):
        start = seg["start"]
        end = seg["end"]
        duration = end - start
        # Fast seek to nearest keyframe before start, then precise trim.
        # This avoids decoding from the beginning while still producing
        # frame-accurate cuts (unlike stream copy which snaps to keyframes).
        rough_seek = max(0, int(start))
        trim_offset = start - rough_seek
        clip_path = str(output_dir / f"clip_{i:04d}.mp4")
        _run_ffmpeg(
            ["-ss", str(rough_seek), "-i", str(video_path),
             "-ss", str(trim_offset), "-t", str(duration),
             "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
             "-c:a", "aac", "-b:a", "128k",
             "-pix_fmt", "yuv420p", clip_path],
            f"cut segment {i} ({start:.1f}s - {end:.1f}s)",
        )
        clips.append(clip_path)

    return clips


def concat_clips(clip_paths: list[str], output_path: str | Path) -> str:
    """Concatenate multiple video clips into one output file."""
    concat_list = TEMP_DIR / f"concat_{uuid.uuid4().hex[:8]}.txt"
    with open(concat_list, "w") as f:
        for p in clip_paths:
            f.write(f"file '{Path(p).resolve()}'\n")

    output_path = str(output_path)
    _run_ffmpeg(
        ["-f", "concat", "-safe", "0", "-i", str(concat_list),
         "-c", "copy", output_path],
        "concat",
    )
    concat_list.unlink(missing_ok=True)
    return output_path


def export_srt(segments: list[dict]) -> str:
    """Convert transcript segments to SRT subtitle format."""
    lines = []
    for i, seg in enumerate(segments, 1):
        start_ts = _srt_time(seg["start"])
        end_ts = _srt_time(seg["end"])
        text = seg.get("speaker", "") and f'{seg["speaker"]}: {seg["text"]}' or seg["text"]
        lines.append(f"{i}\n{start_ts} --> {end_ts}\n{text}\n")
    return "\n".join(lines)


def _srt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def burn_subtitles(video_path: str | Path, segments: list[dict], output_path: str | Path) -> str:
    """Burn subtitles into video using FFmpeg subtitles filter.

    Timestamps are recalculated relative to the concatenated video:
    segments are assumed to be placed sequentially starting at 00:00.
    """
    # Recalculate timestamps for the concatenated video
    adjusted = []
    offset = 0.0
    for seg in segments:
        dur = seg["end"] - seg["start"]
        adjusted.append({**seg, "start": round(offset, 2), "end": round(offset + dur, 2)})
        offset += dur

    srt_path = str(TEMP_DIR / f"subs_{uuid.uuid4().hex[:8]}.srt")
    with open(srt_path, "w") as f:
        f.write(export_srt(adjusted))

    # Escape path for FFmpeg subtitles filter: handle Windows drive letter colon
    escaped = srt_path.replace("\\", "/").replace(":", "\\:")
    output_path = str(output_path)
    _run_ffmpeg(
        ["-i", str(video_path), "-vf",
         f"subtitles={escaped}:force_style='FontSize=24,PrimaryColour=&HFFFFFF,OutlineColour=&H000000,Outline=2'",
         "-c:a", "copy", output_path],
        "burn subtitles",
    )
    Path(srt_path).unlink(missing_ok=True)
    return output_path
