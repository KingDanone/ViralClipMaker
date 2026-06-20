"""
app_fastapi.py — FastAPI backend com SSE para progresso em tempo real.

Substitui Flask para endpoints que precisam de streaming.
Mantém compatibilidade com a UI atual (Alpine.js).
"""

import os
import json
import uuid
import random
import zipfile
import logging
import time
from io import BytesIO
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core.downloader import download_video
from core.transcriber import transcribe
from core.clip_detector import detect_clips
from video_processing import generate_clips, add_captions_and_edit
from core.video_editor import _dim_cache

logger = logging.getLogger(__name__)

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUTS_DIR = os.path.join(ROOT_DIR, "outputs")
HISTORY_FILE = os.path.join(ROOT_DIR, "history.json")
UPLOAD_FOLDER = os.path.join(ROOT_DIR, "uploads")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = FastAPI(title="ViralClipMaker")
app.mount("/static", StaticFiles(directory=os.path.join(ROOT_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(ROOT_DIR, "templates"))

_batch_queue = []
_batch_lock = __import__("threading").Lock()

try:
    with open(os.path.join(ROOT_DIR, "musicas_virais.json"), "r", encoding="utf-8") as f:
        viral_tracks = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    viral_tracks = ["Música Padrão 1", "Música Padrão 2"]


# ── Pages ───────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/uploads/{filename}")
async def serve_clip(filename: str):
    return FileResponse(os.path.join(UPLOAD_FOLDER, filename))


@app.get("/download/{filename}")
async def download(filename: str):
    return FileResponse(
        os.path.join(UPLOAD_FOLDER, filename),
        media_type="application/octet-stream",
        filename=filename,
    )


# ── Process with SSE ────────────────────────────────────────────────────

@app.post("/process")
async def process_video(
    input_type: str = Form(...),
    url: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    whisper_model: str = Form("tiny"),
    subtitle_style: str = Form("tiktok"),
    clip_duration: float = Form(30),
    crop_position: str = Form("center"),
    zoom_factor: float = Form(1.0),
    output_width: int = Form(1080),
    output_height: int = Form(1920),
):
    video_path = None

    if input_type == "url" and url:
        try:
            video_path = download_video(url, UPLOAD_FOLDER)
        except Exception as e:
            return JSONResponse({"error": f"Erro ao baixar: {e}"})
    elif input_type == "file" and file:
        filename = f"{uuid.uuid4()}.mp4"
        video_path = os.path.join(UPLOAD_FOLDER, filename)
        content = await file.read()
        with open(video_path, "wb") as f:
            f.write(content)

    if not video_path or not os.path.exists(video_path):
        return JSONResponse({"error": "Vídeo inválido."})

    crop_params = _parse_crop_position(crop_position, zoom_factor)

    try:
        transcription = transcribe(video_path, model_size=whisper_model)
        segments = detect_clips(transcription, video_path, num_clips=5, clip_duration=clip_duration)

        auto_crop = crop_params.pop("auto_crop", False)
        if auto_crop:
            from core.face_tracker import detect_faces_in_clip, face_to_crop_params
            for seg in segments:
                face_info = detect_faces_in_clip(video_path, seg["start"], seg["end"])
                crop_adjusted = face_to_crop_params(face_info)
                seg["_crop_params"] = crop_adjusted
            segments = _apply_auto_crop(segments, crop_params)

        clips = generate_clips(
            video_path, segments, UPLOAD_FOLDER,
            transcription=transcription, subtitle_style=subtitle_style,
            out_w=output_width, out_h=output_height, **crop_params,
        )

        for clip in clips:
            clip["segments"] = transcription.get("segments", [])

    except Exception as e:
        if os.path.exists(video_path):
            os.remove(video_path)
        return JSONResponse({"error": f"Erro ao processar: {e}"})

    if os.path.exists(video_path):
        os.remove(video_path)
    _dim_cache.pop(video_path, None)

    return {"clips": clips}


@app.post("/process-stream")
async def process_stream(
    input_type: str = Form(...),
    url: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    whisper_model: str = Form("tiny"),
    subtitle_style: str = Form("tiktok"),
    clip_duration: float = Form(30),
    crop_position: str = Form("center"),
    zoom_factor: float = Form(1.0),
    output_width: int = Form(1080),
    output_height: int = Form(1920),
):
    """Processa vídeo com progresso via SSE."""
    async def event_generator():
        video_path = None

        yield f"data: {json.dumps({'step': 'download', 'progress': 5, 'message': 'Preparando...'})}\n\n"

        if input_type == "url" and url:
            yield f"data: {json.dumps({'step': 'download', 'progress': 10, 'message': 'Baixando vídeo...'})}\n\n"
            try:
                video_path = download_video(url, UPLOAD_FOLDER)
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
                return
        elif input_type == "file" and file:
            yield f"data: {json.dumps({'step': 'download', 'progress': 10, 'message': 'Salvando arquivo...'})}\n\n"
            filename = f"{uuid.uuid4()}.mp4"
            video_path = os.path.join(UPLOAD_FOLDER, filename)
            content = await file.read()
            with open(video_path, "wb") as f:
                f.write(content)

        if not video_path or not os.path.exists(video_path):
            yield f"data: {json.dumps({'error': 'Vídeo inválido.'})}\n\n"
            return

        yield f"data: {json.dumps({'step': 'transcribe', 'progress': 20, 'message': 'Transcrevendo áudio...'})}\n\n"

        crop_params = _parse_crop_position(crop_position, zoom_factor)

        try:
            transcription = transcribe(video_path, model_size=whisper_model)
            yield f"data: {json.dumps({'step': 'analyze', 'progress': 60, 'message': 'Analisando momentos...'})}\n\n"

            segments = detect_clips(transcription, video_path, num_clips=5, clip_duration=clip_duration)

            auto_crop = crop_params.pop("auto_crop", False)
            if auto_crop:
                from core.face_tracker import detect_faces_in_clip, face_to_crop_params
                for seg in segments:
                    face_info = detect_faces_in_clip(video_path, seg["start"], seg["end"])
                    crop_adjusted = face_to_crop_params(face_info)
                    seg["_crop_params"] = crop_adjusted
                segments = _apply_auto_crop(segments, crop_params)

            yield f"data: {json.dumps({'step': 'generate', 'progress': 70, 'message': 'Gerando cortes...'})}\n\n"

            clips = generate_clips(
                video_path, segments, UPLOAD_FOLDER,
                transcription=transcription, subtitle_style=subtitle_style,
                out_w=output_width, out_h=output_height, **crop_params,
            )

            for clip in clips:
                clip["segments"] = transcription.get("segments", [])

        except Exception as e:
            if os.path.exists(video_path):
                os.remove(video_path)
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            return

        if os.path.exists(video_path):
            os.remove(video_path)
        _dim_cache.pop(video_path, None)

        yield f"data: {json.dumps({'step': 'done', 'progress': 100, 'message': 'Concluído!', 'clips': clips})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ── Edit ────────────────────────────────────────────────────────────────

@app.post("/edit")
async def edit(request: Request):
    data = await request.json()
    if not data:
        return JSONResponse({"error": "JSON obrigatório."}, status_code=400)

    clip_path = data.get("clip_path")
    text = data.get("text", "Texto viral!")

    if not clip_path or not os.path.exists(clip_path):
        return JSONResponse({"error": "Clipe não encontrado."}, status_code=404)

    try:
        edited_path = add_captions_and_edit(clip_path, text)
    except Exception as e:
        return JSONResponse({"error": f"Erro ao editar: {e}"}, status_code=500)

    return {"edited_path": edited_path}


# ── Music ───────────────────────────────────────────────────────────────

@app.post("/suggest_music")
async def suggest_music(request: Request):
    data = await request.json() or {}
    return {"music": random.choice(viral_tracks)}


# ── Download All ────────────────────────────────────────────────────────

@app.post("/download-all")
async def download_all(request: Request):
    data = await request.json()
    paths = data.get("paths", [])
    if not paths:
        return JSONResponse({"error": "Nenhum clip."}, status_code=400)

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in paths:
            filename = os.path.basename(p)
            if "/" in filename or "\\" in filename or ".." in filename:
                continue
            full_path = os.path.join(UPLOAD_FOLDER, filename)
            if os.path.exists(full_path) and os.path.isfile(full_path):
                zf.write(full_path, filename)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=clips.zip"},
    )


# ── Export Subtitles ────────────────────────────────────────────────────

@app.post("/export-subtitles")
async def export_subtitles(request: Request):
    data = await request.json()
    clip_path = data.get("clip_path")
    fmt = data.get("format", "srt")
    segments = data.get("segments")

    if fmt not in ("srt", "vtt"):
        return JSONResponse({"error": "Formato inválido."}, status_code=400)

    if not clip_path:
        return JSONResponse({"error": "clip_path obrigatório."}, status_code=400)

    if not segments:
        filename = os.path.basename(clip_path)
        stem = os.path.splitext(filename)[0]
        json_path = os.path.join(OUTPUTS_DIR, f"{stem}_transcription.json")
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    segments = json.load(f).get("segments", [])
            except (json.JSONDecodeError, IOError):
                pass

    if not segments:
        return JSONResponse({"error": "Transcrição não encontrada."}, status_code=404)

    out_filename = f"{os.path.splitext(os.path.basename(clip_path))[0]}.{fmt}"
    out_path = os.path.join(UPLOAD_FOLDER, out_filename)

    from core.subtitle_export import export_srt, export_vtt
    if fmt == "vtt":
        export_vtt(segments, out_path)
    else:
        export_srt(segments, out_path)

    return FileResponse(out_path, filename=out_filename)


# ── Batch ───────────────────────────────────────────────────────────────

@app.post("/batch/add")
async def batch_add(request: Request):
    data = await request.json()
    source = data.get("source")
    input_type = data.get("input_type", "url")

    if not source:
        return JSONResponse({"error": "Source obrigatório."}, status_code=400)

    item = {
        "id": str(uuid.uuid4()),
        "source": source,
        "input_type": input_type,
        "status": "pending",
        "progress": 0,
        "clips": [],
        "error": None,
    }

    with _batch_lock:
        _batch_queue.append(item)

    return {"id": item["id"], "status": "pending"}


@app.get("/batch/status")
async def batch_status():
    with _batch_lock:
        return {"queue": _batch_queue}


@app.post("/batch/process")
async def batch_process(request: Request):
    import threading

    data = await request.json() if request.headers.get("content-type") == "application/json" else {}

    def process_batch():
        with _batch_lock:
            pending = [item for item in _batch_queue if item["status"] == "pending"]

        for item in pending:
            item["status"] = "processing"
            try:
                video_path = _resolve_video_source(item["source"], item["input_type"])
                transcription = transcribe(video_path, model_size="tiny")
                segments = detect_clips(transcription, video_path, num_clips=5)
                clips = generate_clips(video_path, segments, UPLOAD_FOLDER, transcription=transcription)
                item["clips"] = clips
                item["status"] = "done"
                item["progress"] = 100
                if os.path.exists(video_path) and item["input_type"] == "url":
                    os.remove(video_path)
            except Exception as e:
                item["status"] = "error"
                item["error"] = str(e)

    threading.Thread(target=process_batch, daemon=True).start()
    return {"message": "Processamento em lote iniciado."}


# ── History ─────────────────────────────────────────────────────────────

@app.get("/history")
async def get_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []
    return []


@app.post("/history")
async def save_to_history(request: Request):
    data = await request.json()
    if not data:
        return JSONResponse({"error": "Dados inválidos."}, status_code=400)

    data["timestamp"] = datetime.now().isoformat()

    history = []
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
        except (json.JSONDecodeError, IOError):
            history = []

    history.insert(0, data)
    history = history[:50]

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    return {"ok": True}


# ── Helpers ─────────────────────────────────────────────────────────────

def _parse_crop_position(position: str, zoom: float) -> dict:
    if position == "auto":
        return {"x_offset": None, "y_offset": None, "zoom_factor": max(1.0, min(2.0, zoom)), "auto_crop": True}

    positions = {
        "left": {"x_offset": 0.0, "y_offset": 0.5},
        "center": {"x_offset": 0.5, "y_offset": 0.5},
        "right": {"x_offset": 1.0, "y_offset": 0.5},
    }
    params = positions.get(position, positions["center"])
    params["zoom_factor"] = max(1.0, min(2.0, zoom))
    if params["zoom_factor"] <= 1.0:
        params["zoom_factor"] = 1.0
    params["auto_crop"] = False
    return params


def _apply_auto_crop(segments: list, base_params: dict) -> list:
    for seg in segments:
        crop = seg.pop("_crop_params", {})
        seg["x_offset"] = crop.get("x_offset", base_params.get("x_offset", 0.5))
        seg["y_offset"] = crop.get("y_offset", base_params.get("y_offset", 0.5))
    return segments


def _resolve_video_source(source: str, input_type: str) -> str:
    if input_type == "url":
        return download_video(source, UPLOAD_FOLDER)
    elif input_type == "file":
        filename = f"{uuid.uuid4()}.mp4"
        path = os.path.join(UPLOAD_FOLDER, filename)
        if os.path.exists(source):
            import shutil
            shutil.copy2(source, path)
        return path
    raise ValueError(f"Tipo inválido: {input_type}")


# ── Startup ─────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    import threading

    def cleanup_uploads(max_age_hours=24, min_age_minutes=10):
        while True:
            time.sleep(3600)
            try:
                cutoff = datetime.now() - timedelta(hours=max_age_hours)
                min_cutoff = datetime.now() - timedelta(minutes=min_age_minutes)
                for f in os.listdir(UPLOAD_FOLDER):
                    path = os.path.join(UPLOAD_FOLDER, f)
                    if os.path.isfile(path):
                        mtime = datetime.fromtimestamp(os.path.getmtime(path))
                        if mtime < cutoff and mtime < min_cutoff:
                            os.remove(path)
            except Exception:
                pass

    threading.Thread(target=cleanup_uploads, daemon=True).start()
