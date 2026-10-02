"""
app.py — Backend FastAPI do ViralClipMaker (backend único).

Rotas:
    GET  /                    UI (Alpine.js)
    POST /process             Processa vídeo e retorna clips (JSON)
    POST /process-stream      Idem, com progresso em tempo real via SSE
    POST /edit                Edita clip com caption + efeito P&B
    POST /suggest_music       Sugestão de música viral
    GET  /uploads/{filename}  Serve clip gerado
    GET  /download/{filename} Download de um clip
    POST /download-all        Download .zip com vários clips
    POST /export-subtitles    Exporta legendas do clip (.srt/.vtt)
    POST /batch/add           Adiciona vídeo à fila batch
    GET  /batch/status        Status da fila
    POST /batch/process       Processa a fila (background thread)
    GET|POST /history         Histórico local de projetos
"""

import os
import json
import uuid
import random
import zipfile
import logging
import time
import threading
from io import BytesIO
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core.downloader import download_video, resolve_video_source
from core.transcriber import transcribe
from core.clip_detector import detect_clips
from core.pipeline import parse_crop_position
from core.subtitle_export import export_srt, export_vtt
from core.history import load_history, append_history
from video_processing import generate_clips, add_captions_and_edit
from core.video_editor import _dim_cache

logger = logging.getLogger(__name__)

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUTS_DIR = os.path.join(ROOT_DIR, "outputs")
UPLOAD_FOLDER = os.path.join(ROOT_DIR, "uploads")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUTS_DIR, exist_ok=True)

app = FastAPI(title="ViralClipMaker")
app.mount("/static", StaticFiles(directory=os.path.join(ROOT_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(ROOT_DIR, "templates"))

_batch_queue: list[dict] = []
_batch_lock = threading.Lock()

try:
    with open(os.path.join(ROOT_DIR, "musicas_virais.json"), "r", encoding="utf-8") as f:
        viral_tracks = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    viral_tracks = ["Música Padrão 1", "Música Padrão 2"]


# ── Helpers ─────────────────────────────────────────────────────────────

async def _save_upload(file: UploadFile) -> str:
    """Salva upload em disco via stream (não carrega o arquivo inteiro em RAM)."""
    video_path = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4()}.mp4")
    with open(video_path, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            f.write(chunk)
    return video_path


def _safe_upload_path(filename: str) -> str | None:
    """Valida filename e retorna path em uploads/, ou None se inseguro/ausente."""
    if not filename or os.path.basename(filename) != filename or ".." in filename:
        return None
    path = os.path.join(UPLOAD_FOLDER, filename)
    return path if os.path.isfile(path) else None


def _process_pipeline(
    video_path: str,
    *,
    whisper_model: str,
    subtitle_style: str,
    clip_duration: float,
    crop_params: dict,
    output_width: int,
    output_height: int,
    auto_zoom: bool,
) -> list[dict]:
    """Pipeline completo: transcrição → seleção → (auto-crop) → geração de clips."""
    transcription = transcribe(video_path, model_size=whisper_model)
    segments = detect_clips(
        transcription, video_path, num_clips=5, clip_duration=clip_duration
    )

    params = dict(crop_params)
    if params.pop("auto_crop", False):
        from core.face_tracker import (
            detect_faces_in_clip,
            face_to_crop_params,
            apply_auto_crop,
        )
        for seg in segments:
            face_info = detect_faces_in_clip(video_path, seg["start"], seg["end"])
            seg["_crop_params"] = face_to_crop_params(face_info)
        segments = apply_auto_crop(segments, params)

    clips = generate_clips(
        video_path, segments, UPLOAD_FOLDER,
        transcription=transcription, subtitle_style=subtitle_style,
        out_w=output_width, out_h=output_height,
        auto_zoom=auto_zoom, **params,
    )

    # Sidecar de transcrição por clip (fallback do /export-subtitles)
    for clip in clips:
        stem = os.path.splitext(os.path.basename(clip["path"]))[0]
        try:
            with open(
                os.path.join(OUTPUTS_DIR, f"{stem}_transcription.json"),
                "w", encoding="utf-8",
            ) as f:
                json.dump({"segments": clip.get("segments", [])}, f, ensure_ascii=False)
        except IOError:
            logger.warning("Falha ao gravar sidecar de transcrição de %s", stem)

    return clips


def _cleanup_input(video_path: str | None) -> None:
    """Remove o vídeo de entrada temporário e seu cache de dimensões."""
    if not video_path:
        return
    if os.path.exists(video_path):
        os.remove(video_path)
    _dim_cache.pop(video_path, None)


# ── Pages ────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/uploads/{filename}")
async def serve_clip(filename: str):
    path = _safe_upload_path(filename)
    if not path:
        return JSONResponse({"error": "Arquivo não encontrado."}, status_code=404)
    return FileResponse(path)


@app.get("/download/{filename}")
async def download(filename: str):
    path = _safe_upload_path(filename)
    if not path:
        return JSONResponse({"error": "Arquivo não encontrado."}, status_code=404)
    return FileResponse(path, media_type="application/octet-stream", filename=filename)


# ── Process ─────────────────────────────────────────────────────────────

async def _resolve_input(input_type: str, url: Optional[str], file: Optional[UploadFile]) -> str | None:
    if input_type == "url" and url:
        return download_video(url, UPLOAD_FOLDER)
    if input_type == "file" and file:
        return await _save_upload(file)
    return None


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
    auto_zoom: bool = Form(False),
):
    video_path = None
    try:
        video_path = await _resolve_input(input_type, url, file)
    except Exception as e:
        return JSONResponse({"error": f"Erro ao obter o vídeo: {e}"})

    if not video_path or not os.path.exists(video_path):
        return JSONResponse({"error": "Vídeo inválido."})

    try:
        clips = _process_pipeline(
            video_path,
            whisper_model=whisper_model,
            subtitle_style=subtitle_style,
            clip_duration=clip_duration,
            crop_params=parse_crop_position(crop_position, zoom_factor),
            output_width=output_width,
            output_height=output_height,
            auto_zoom=auto_zoom,
        )
    except Exception as e:
        _cleanup_input(video_path)
        return JSONResponse({"error": f"Erro ao processar: {e}"})

    _cleanup_input(video_path)
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
    auto_zoom: bool = Form(False),
):
    """Processa vídeo com progresso em tempo real via SSE."""

    def sse(payload: dict) -> str:
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    async def event_generator():
        video_path = None

        yield sse({"step": "download", "progress": 5, "message": "Preparando..."})

        try:
            if input_type == "url":
                yield sse({"step": "download", "progress": 10, "message": "Baixando vídeo..."})
                video_path = await _resolve_input("url", url, None)
            else:
                yield sse({"step": "download", "progress": 10, "message": "Enviando arquivo..."})
                video_path = await _resolve_input("file", None, file)
        except Exception as e:
            yield sse({"error": f"Erro ao obter o vídeo: {e}"})
            return

        if not video_path or not os.path.exists(video_path):
            yield sse({"error": "Vídeo inválido."})
            return

        yield sse({"step": "transcribe", "progress": 20, "message": "Transcrevendo áudio..."})

        try:
            yield sse({"step": "analyze", "progress": 60, "message": "Analisando momentos..."})
            yield sse({"step": "generate", "progress": 70, "message": "Gerando cortes..."})
            clips = _process_pipeline(
                video_path,
                whisper_model=whisper_model,
                subtitle_style=subtitle_style,
                clip_duration=clip_duration,
                crop_params=parse_crop_position(crop_position, zoom_factor),
                output_width=output_width,
                output_height=output_height,
                auto_zoom=auto_zoom,
            )
        except Exception as e:
            _cleanup_input(video_path)
            yield sse({"error": f"Erro ao processar: {e}"})
            return

        _cleanup_input(video_path)
        yield sse({"step": "done", "progress": 100, "message": "Concluído!", "clips": clips})

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ── Edit ─────────────────────────────────────────────────────────────────

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


# ── Music ────────────────────────────────────────────────────────────────

@app.post("/suggest_music")
async def suggest_music(request: Request):
    await request.body()  # aceita qualquer payload (compat)
    return {"music": random.choice(viral_tracks)}


# ── Download All ─────────────────────────────────────────────────────────

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
            full_path = _safe_upload_path(filename)
            if full_path:
                zf.write(full_path, filename)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=clips.zip"},
    )


# ── Export Subtitles ─────────────────────────────────────────────────────

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
        # Fallback: sidecar gravado durante a geração do clip
        stem = os.path.splitext(os.path.basename(clip_path))[0]
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

    if fmt == "vtt":
        export_vtt(segments, out_path)
    else:
        export_srt(segments, out_path)

    return FileResponse(out_path, filename=out_filename)


# ── Batch ────────────────────────────────────────────────────────────────

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
        # Mantém no máximo 20 itens finalizados na fila
        finished = [i for i in _batch_queue if i["status"] in ("done", "error")]
        for old in finished[:-20]:
            _batch_queue.remove(old)

    return {"id": item["id"], "status": "pending"}


@app.get("/batch/status")
async def batch_status():
    with _batch_lock:
        return {"queue": _batch_queue}


@app.post("/batch/process")
async def batch_process(request: Request):
    data = await request.json() if request.headers.get("content-type") == "application/json" else {}

    whisper_model = data.get("whisper_model", "tiny")
    subtitle_style = data.get("subtitle_style", "tiktok")
    clip_duration = float(data.get("clip_duration", 30))
    crop_params = parse_crop_position(
        data.get("crop_position", "center"),
        float(data.get("zoom_factor", 1.0)),
    )
    output_width = int(data.get("output_width", 1080))
    output_height = int(data.get("output_height", 1920))

    def process_batch():
        with _batch_lock:
            pending = [item for item in _batch_queue if item["status"] == "pending"]

        for item in pending:
            item["status"] = "processing"
            video_path = None
            try:
                video_path = resolve_video_source(item["source"], item["input_type"], UPLOAD_FOLDER)
                item["clips"] = _process_pipeline(
                    video_path,
                    whisper_model=whisper_model,
                    subtitle_style=subtitle_style,
                    clip_duration=clip_duration,
                    crop_params=crop_params,
                    output_width=output_width,
                    output_height=output_height,
                    auto_zoom=False,
                )
                item["status"] = "done"
                item["progress"] = 100
            except Exception as e:
                item["status"] = "error"
                item["error"] = str(e)
            finally:
                _cleanup_input(video_path)

    threading.Thread(target=process_batch, daemon=True).start()
    return {"message": "Processamento em lote iniciado."}


# ── History ──────────────────────────────────────────────────────────────

@app.get("/history")
async def get_history():
    return load_history()


@app.post("/history")
async def save_to_history(request: Request):
    data = await request.json()
    if not data:
        return JSONResponse({"error": "Dados inválidos."}, status_code=400)
    append_history(data)
    return {"ok": True}


# ── Startup ──────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    def cleanup_uploads(max_age_hours=24):
        """Remove arquivos de uploads/ com mais de X horas."""
        while True:
            time.sleep(3600)
            try:
                cutoff = datetime.now() - timedelta(hours=max_age_hours)
                for f in os.listdir(UPLOAD_FOLDER):
                    path = os.path.join(UPLOAD_FOLDER, f)
                    if os.path.isfile(path):
                        mtime = datetime.fromtimestamp(os.path.getmtime(path))
                        if mtime < cutoff:
                            os.remove(path)
                            logger.info("Upload limpo: %s", f)
            except Exception as e:
                logger.warning("Erro na limpeza de uploads: %s", e)

    threading.Thread(target=cleanup_uploads, daemon=True).start()
