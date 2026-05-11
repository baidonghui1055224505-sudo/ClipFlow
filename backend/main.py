import json
import uuid
import shutil
import re
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from transcriber import transcribe, preload_model
from video_processor import extract_audio, cut_segments, concat_clips, export_srt, burn_subtitles, TEMP_DIR
from ai_selector import select_segments

# Optional dependency: speaker diarization (requires pyannote.audio + torch)
try:
    from speaker_diarize import preload_pipeline
    _HAS_DIARIZE = True
except ImportError:
    _HAS_DIARIZE = False
    def preload_pipeline(): pass

# Optional dependency: platform video download (requires yt-dlp)
try:
    import yt_dlp
    _HAS_YTDLP = True
except ImportError:
    _HAS_YTDLP = False

UPLOAD_DIR = TEMP_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR = TEMP_DIR / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

app = FastAPI()


@app.on_event("startup")
def startup():
    """Preload ML models so the first request doesn't wait for downloads."""
    import sys
    import os
    try:
        preload_model()
    except Exception as e:
        print(f"[startup] Whisper preload failed: {e}", file=sys.stderr, flush=True)

    if _HAS_DIARIZE and os.environ.get("HF_TOKEN"):
        try:
            preload_pipeline()
        except Exception as e:
            print(f"[startup] Pyannote preload failed: {e}", file=sys.stderr, flush=True)
    elif not _HAS_DIARIZE:
        print("[startup] pyannote not installed, speaker diarization disabled", file=sys.stderr, flush=True)
    else:
        print("[startup] HF_TOKEN not set, skipping pyannote preload", file=sys.stderr, flush=True)


# Session state
sessions: dict[str, dict] = {}


@app.post("/api/upload")
async def upload_video(file: UploadFile = File(...)):
    video_id = uuid.uuid4().hex[:12]
    ext = Path(file.filename).suffix or ".mp4"
    video_path = UPLOAD_DIR / f"{video_id}{ext}"
    with open(video_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    sessions[video_id] = {
        "video_path": str(video_path),
        "transcript": None,
        "status": "uploaded",
    }
    return {"video_id": video_id, "filename": file.filename}


@app.post("/api/upload-url")
async def upload_video_url(req: dict):
    """Download a video from a URL and register it as a session."""
    url = req.get("url", "").strip()
    if not url:
        return JSONResponse({"error": "URL is required"}, 400)

    # Validate URL
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return JSONResponse({"error": "Invalid URL scheme"}, 400)

    # Determine filename from URL or use default
    path_part = parsed.path or "/video"
    ext = Path(path_part).suffix or ".mp4"
    # Sanitize extension
    if len(ext) > 6 or not re.match(r'^\.\w{2,5}$', ext):
        ext = ".mp4"
    video_id = uuid.uuid4().hex[:12]
    video_path = UPLOAD_DIR / f"{video_id}{ext}"

    # Detect platform URLs that need yt-dlp
    hostname = parsed.hostname or ""
    is_platform = any(kw in hostname for kw in [
        "bilibili.com", "youtube.com", "youtu.be",
        "vimeo.com", "tiktok.com", "douyin.com",
        "ixigua.com", "weibo.com",
    ])

    try:
        if is_platform:
            if not _HAS_YTDLP:
                return JSONResponse({"error": "Downloading from this platform requires yt-dlp. Run: pip install yt-dlp"}, 400)
            print(f"[upload-url] Downloading platform video {url} with yt-dlp ...", flush=True)
            ydl_opts = {
                "outtmpl": str(video_path),
                "format": "bestvideo+bestaudio/best",
                "quiet": True,
                "no_warnings": True,
                "merge_output_format": "mp4",
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            file_size = video_path.stat().st_size
            print(f"[upload-url] Downloaded {file_size} bytes", flush=True)
        else:
            print(f"[upload-url] Downloading direct URL {url} ...", flush=True)
            urllib.request.urlretrieve(url, str(video_path))
            file_size = video_path.stat().st_size
            print(f"[upload-url] Downloaded {file_size} bytes", flush=True)

        if file_size < 1024:
            video_path.unlink(missing_ok=True)
            return JSONResponse({"error": "Downloaded file is empty or too small"}, 400)

        # Validate the downloaded file is actually a video
        header = video_path.read_bytes()[:12]
        if header[:4] == b"<htm" or header[:4] == b"<!DO":
            video_path.unlink(missing_ok=True)
            return JSONResponse({"error": "Downloaded file is not a video (got HTML). The URL may require a video platform downloader."}, 400)
    except Exception as e:
        video_path.unlink(missing_ok=True)
        return JSONResponse({"error": f"Download failed: {str(e)}"}, 400)

    filename = Path(parsed.path).name or f"video{ext}"
    sessions[video_id] = {
        "video_path": str(video_path),
        "transcript": None,
        "status": "uploaded",
    }
    return {"video_id": video_id, "filename": filename}


@app.get("/api/video/{video_id}")
async def serve_video(video_id: str):
    """Serve an uploaded video file for playback."""
    session = sessions.get(video_id)
    if not session:
        return JSONResponse({"error": "Session not found"}, 404)
    video_path = session.get("video_path", "")
    if not video_path or not Path(video_path).exists():
        return JSONResponse({"error": "Video file not found"}, 404)
    return FileResponse(video_path, media_type="video/mp4")


@app.post("/api/transcribe/{video_id}")
async def transcribe_video(video_id: str, body: dict = None):
    session = sessions.get(video_id)
    if not session:
        return JSONResponse({"error": "Session not found"}, 404)

    enable_diarization = body.get("diarization", False) if body else False
    model_size = body.get("model", "tiny") if body else "tiny"
    audio_path = extract_audio(session["video_path"])
    result = transcribe(audio_path, enable_diarization=enable_diarization, model_size=model_size)
    Path(audio_path).unlink(missing_ok=True)

    session["transcript"] = result
    session["status"] = "transcribed"
    return result


@app.post("/api/rename-speakers")
def rename_speakers(req: dict):
    video_id = req["video_id"]
    renames: dict = req.get("renames", {})

    session = sessions.get(video_id)
    if not session:
        return JSONResponse({"error": "Session not found"}, 404)

    session["speaker_renames"] = renames
    return {"ok": True}


@app.get("/api/transcript/{video_id}")
def get_transcript(video_id: str):
    session = sessions.get(video_id)
    if not session:
        return JSONResponse({"error": "Session not found"}, 404)
    if not session.get("transcript"):
        return JSONResponse({"error": "Not yet transcribed"}, 400)
    return session["transcript"]


@app.post("/api/select-segments")
def ai_select_segments(req: dict):
    video_id = req["video_id"]
    instruction: str = req["instruction"]
    reset: bool = req.get("reset", False)

    session = sessions.get(video_id)
    if not session or not session.get("transcript"):
        return JSONResponse({"error": "Session not found or not transcribed"}, 400)

    # Manage conversation history
    if reset or "chat_history" not in session:
        session["chat_history"] = []

    segments = session["transcript"]["segments"]
    try:
        history = session["chat_history"].copy()
        ids, reasoning = select_segments(segments, instruction, history)

        # Store this round in history
        session["chat_history"].append({"role": "user", "content": instruction})
        session["chat_history"].append({
            "role": "assistant",
            "content": json.dumps({"ids": ids, "reasoning": reasoning})
        })

        return {
            "segment_ids": ids,
            "total": len(segments),
            "selected": len(ids),
            "reasoning": reasoning,
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, 500)


@app.post("/api/export")
def export_video(req: dict):
    video_id = req["video_id"]
    segment_ids: list[int] = req["segment_ids"]

    session = sessions.get(video_id)
    if not session or not session.get("transcript"):
        return JSONResponse({"error": "Session not found or not transcribed"}, 400)

    all_segments = session["transcript"]["segments"]
    selected = [all_segments[i] for i in segment_ids if i < len(all_segments)]
    if not selected:
        return JSONResponse({"error": "No segments selected"}, 400)

    work_dir = TEMP_DIR / f"export_{video_id}"
    work_dir.mkdir(exist_ok=True)

    clips = cut_segments(session["video_path"], selected, work_dir)
    output_path = str(OUTPUT_DIR / f"output_{video_id}.mp4")
    concat_clips(clips, output_path)

    return FileResponse(output_path, media_type="video/mp4",
                        filename=f"edited_{video_id}.mp4")


@app.get("/api/export-srt/{video_id}")
def export_srt_endpoint(video_id: str):
    session = sessions.get(video_id)
    if not session or not session.get("transcript"):
        return JSONResponse({"error": "Session not found or not transcribed"}, 400)

    segments = session["transcript"]["segments"]
    # Apply speaker renames if any
    renames = session.get("speaker_renames", {})
    for seg in segments:
        spk = seg.get("speaker", "")
        if spk and spk in renames:
            seg = {**seg, "speaker": renames[spk]}

    srt_content = export_srt(segments)
    srt_path = OUTPUT_DIR / f"subs_{video_id}.srt"
    srt_path.write_text(srt_content)
    return FileResponse(str(srt_path), media_type="text/plain",
                        filename=f"subtitles_{video_id}.srt")


@app.post("/api/export-burn")
def export_burn(req: dict):
    video_id = req["video_id"]
    segment_ids: list[int] = req["segment_ids"]

    session = sessions.get(video_id)
    if not session or not session.get("transcript"):
        return JSONResponse({"error": "Session not found or not transcribed"}, 400)

    all_segments = session["transcript"]["segments"]
    selected = [all_segments[i] for i in segment_ids if i < len(all_segments)]
    if not selected:
        return JSONResponse({"error": "No segments selected"}, 400)

    # Apply speaker renames
    renames = session.get("speaker_renames", {})
    for seg in selected:
        spk = seg.get("speaker", "")
        if spk and spk in renames:
            seg["speaker"] = renames[spk]

    work_dir = TEMP_DIR / f"burn_{video_id}"
    work_dir.mkdir(exist_ok=True)
    clips = cut_segments(session["video_path"], selected, work_dir)
    concat_path = str(work_dir / "concat.mp4")
    concat_clips(clips, concat_path)
    output_path = str(OUTPUT_DIR / f"burned_{video_id}.mp4")
    burn_subtitles(concat_path, selected, output_path)

    return FileResponse(output_path, media_type="video/mp4",
                        filename=f"subtitled_{video_id}.mp4")


app.mount("/", StaticFiles(directory=Path(__file__).parent.parent / "frontend", html=True))
