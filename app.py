from flask import Flask, render_template, request, send_file, jsonify, send_from_directory
import os
import json
import uuid
import random
import zipfile
import logging
from io import BytesIO
from datetime import datetime, timedelta
import threading
import time
from core.downloader import download_video
from core.transcriber import transcribe
from core.clip_detector import detect_clips
from video_processing import (
    generate_clips,
    add_captions_and_edit,
)
from core.video_editor import _dim_cache

logger = logging.getLogger(__name__)

OUTPUTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")
HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "history.json")

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = "uploads/"

_batch_queue = []
_batch_lock = threading.Lock()

try:
    with open("musicas_virais.json", "r", encoding="utf-8") as f:
        viral_tracks = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    viral_tracks = [
        "Música Padrão 1 - Artista Genérico",
        "Música Padrão 2 - Artista Genérico",
    ]


def suggest_music(theme=None):
    """Sugere uma música da lista de faixas virais carregada do JSON."""
    return random.choice(viral_tracks)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/process", methods=["POST"])
def process():
    input_type = request.form.get("input_type")
    video_path = None

    if input_type == "url":
        url = request.form.get("url")
        try:
            video_path = download_video(url, app.config["UPLOAD_FOLDER"])
        except Exception as e:
            print(f"Erro ao baixar vídeo do YouTube: {e}")
            return jsonify({"error": "Erro ao baixar o vídeo do YouTube. A URL pode ser inválida ou o vídeo pode ter restrições."})
    elif input_type == "file":
        file = request.files["file"]
        if file and file.filename:
            filename = f"{uuid.uuid4()}.mp4"
            video_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            file.save(video_path)
        else:
            return jsonify({"error": "Nenhum arquivo selecionado para upload."})

    if not video_path or not os.path.exists(video_path):
        return jsonify({"error": "Vídeo inválido ou erro no download."})

    whisper_model = request.form.get("whisper_model", "tiny")
    subtitle_style = request.form.get("subtitle_style", "tiktok")
    clip_duration = float(request.form.get("clip_duration", "30"))
    crop_position = request.form.get("crop_position", "center")
    zoom_factor = float(request.form.get("zoom_factor", "1.0"))
    output_width = int(request.form.get("output_width", "1080"))
    output_height = int(request.form.get("output_height", "1920"))

    crop_params = _parse_crop_position(crop_position, zoom_factor)

    try:
        transcription = transcribe(video_path, model_size=whisper_model)
        segments = detect_clips(
            transcription, video_path, num_clips=5,
            clip_duration=clip_duration,
        )

        auto_crop = crop_params.pop("auto_crop", False)
        if auto_crop:
            from core.face_tracker import detect_faces_in_clip, face_to_crop_params
            for seg in segments:
                face_info = detect_faces_in_clip(video_path, seg["start"], seg["end"])
                crop_adjusted = face_to_crop_params(face_info)
                seg["_crop_params"] = crop_adjusted
            segments = _apply_auto_crop(segments, crop_params)

        clips = generate_clips(
            video_path, segments, app.config["UPLOAD_FOLDER"],
            transcription=transcription, subtitle_style=subtitle_style,
            out_w=output_width, out_h=output_height,
            **crop_params,
        )

        for clip in clips:
            clip["segments"] = transcription.get("segments", [])
    except Exception as e:
        print(f"Erro ao processar vídeo: {e}")
        if os.path.exists(video_path):
            os.remove(video_path)
        return jsonify({"error": f"Erro ao processar o vídeo: {e}"})

    if os.path.exists(video_path):
        os.remove(video_path)

    _dim_cache.pop(video_path, None)

    return jsonify({"clips": clips})


def _parse_crop_position(position: str, zoom: float) -> dict:
    """Converte posição predefinida em parâmetros de crop."""
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
    """Aplica crop automático baseado na detecção de faces."""
    for seg in segments:
        crop = seg.pop("_crop_params", {})
        seg["x_offset"] = crop.get("x_offset", base_params.get("x_offset", 0.5))
        seg["y_offset"] = crop.get("y_offset", base_params.get("y_offset", 0.5))
    return segments


@app.route("/edit", methods=["POST"])
def edit():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Requisição inválida: esperado JSON."}), 400
    clip_path = data.get("clip_path")
    text = data.get("text", "Texto viral!")

    if not clip_path or not os.path.exists(clip_path):
        return jsonify({"error": "O clipe original não foi encontrado."}), 404

    try:
        edited_path = add_captions_and_edit(clip_path, text)
    except Exception as e:
        print(f"Erro ao editar vídeo: {e}")
        return jsonify({"error": f"Erro ao aplicar a edição no clipe: {e}"}), 500

    return jsonify({"edited_path": edited_path})


@app.route("/suggest_music", methods=["POST"])
def suggest_music_route():
    data = request.get_json() or {}
    theme = data.get("theme")
    music = suggest_music(theme)
    return jsonify({"music": music})


@app.route("/uploads/<path:filename>")
def serve_clip(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


@app.route("/download/<path:filename>")
def download(filename):
    return send_file(os.path.join(app.config["UPLOAD_FOLDER"], filename), as_attachment=True)


@app.route("/download-all", methods=["POST"])
def download_all():
    """Baixa múltiplos clips como um arquivo .zip."""
    data = request.get_json()
    paths = data.get("paths", [])
    if not paths:
        return jsonify({"error": "Nenhum clip selecionado."}), 400

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in paths:
            filename = os.path.basename(p)
            if "/" in filename or "\\" in filename or ".." in filename:
                continue
            full_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            if os.path.exists(full_path) and os.path.isfile(full_path):
                zf.write(full_path, filename)
    buf.seek(0)
    return send_file(
        buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name="clips.zip",
    )


@app.route("/export-subtitles", methods=["POST"])
def export_subtitles():
    """Exporta legendas de um clip como .srt ou .vtt."""
    data = request.get_json()
    clip_path = data.get("clip_path")
    fmt = data.get("format", "srt")

    if fmt not in ("srt", "vtt"):
        return jsonify({"error": "Formato inválido. Use 'srt' ou 'vtt'."}), 400

    if not clip_path:
        return jsonify({"error": "clip_path obrigatório."}), 400

    segments = data.get("segments")

    if not segments:
        filename = os.path.basename(clip_path)
        stem = os.path.splitext(filename)[0]
        json_path = os.path.join(OUTPUTS_DIR, f"{stem}_transcription.json")
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    transcription = json.load(f)
                segments = transcription.get("segments", [])
            except (json.JSONDecodeError, IOError):
                pass

    if not segments:
        return jsonify({"error": "Transcrição não encontrada."}), 404

    out_filename = f"{os.path.splitext(os.path.basename(clip_path))[0]}.{fmt}"
    out_path = os.path.join(app.config["UPLOAD_FOLDER"], out_filename)

    from core.subtitle_export import export_srt, export_vtt
    if fmt == "vtt":
        export_vtt(segments, out_path)
    else:
        export_srt(segments, out_path)

    return send_file(out_path, as_attachment=True, download_name=out_filename)


@app.route("/batch/add", methods=["POST"])
def batch_add():
    """Adiciona um vídeo à fila de processamento em lote."""
    input_type = request.form.get("input_type", "url")
    video_source = request.form.get("url") or request.form.get("file")

    if not video_source:
        return jsonify({"error": "Nenhum vídeo especificado."}), 400

    item = {
        "id": str(uuid.uuid4()),
        "source": video_source,
        "input_type": input_type,
        "status": "pending",
        "progress": 0,
        "clips": [],
        "error": None,
    }

    with _batch_lock:
        _batch_queue.append(item)

    return jsonify({"id": item["id"], "status": "pending"})


@app.route("/batch/status")
def batch_status():
    """Retorna status da fila de processamento em lote."""
    with _batch_lock:
        return jsonify({"queue": _batch_queue})


@app.route("/batch/process", methods=["POST"])
def batch_process():
    """Processa todos os vídeos pendentes na fila."""
    whisper_model = request.form.get("whisper_model", "tiny")
    subtitle_style = request.form.get("subtitle_style", "tiktok")
    clip_duration = float(request.form.get("clip_duration", "30"))
    crop_position = request.form.get("crop_position", "center")
    zoom_factor = float(request.form.get("zoom_factor", "1.0"))
    output_width = int(request.form.get("output_width", "1080"))
    output_height = int(request.form.get("output_height", "1920"))

    def process_batch():
        with _batch_lock:
            pending = [item for item in _batch_queue if item["status"] == "pending"]

        for item in pending:
            item["status"] = "processing"
            try:
                video_path = _resolve_video_source(item["source"], item["input_type"])
                transcription = transcribe(video_path, model_size=whisper_model)
                segments = detect_clips(transcription, video_path, num_clips=5, clip_duration=clip_duration)
                crop_params = _parse_crop_position(crop_position, zoom_factor)
                crop_params.pop("auto_crop", None)
                clips = generate_clips(
                    video_path, segments, app.config["UPLOAD_FOLDER"],
                    transcription=transcription, subtitle_style=subtitle_style,
                    out_w=output_width, out_h=output_height, **crop_params,
                )
                item["clips"] = clips
                item["status"] = "done"
                item["progress"] = 100
                if os.path.exists(video_path) and item["input_type"] == "url":
                    os.remove(video_path)
            except Exception as e:
                item["status"] = "error"
                item["error"] = str(e)

    threading.Thread(target=process_batch, daemon=True).start()
    return jsonify({"message": "Processamento em lote iniciado."})


def _resolve_video_source(source: str, input_type: str) -> str:
    """Resolve vídeo de entrada para batch."""
    if input_type == "url":
        return download_video(source, app.config["UPLOAD_FOLDER"])
    elif input_type == "file":
        filename = f"{uuid.uuid4()}.mp4"
        path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        if os.path.exists(source):
            import shutil
            shutil.copy2(source, path)
        return path
    raise ValueError(f"Tipo de entrada inválido: {input_type}")


@app.route("/history")
def get_history():
    """Retorna histórico de projetos."""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return jsonify(json.load(f))
        except (json.JSONDecodeError, IOError):
            return jsonify([])
    return jsonify([])


@app.route("/history", methods=["POST"])
def save_to_history():
    """Salva um projeto no histórico."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Dados inválidos."}), 400

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

    return jsonify({"ok": True})


if __name__ == "__main__":
    if not os.path.exists(app.config["UPLOAD_FOLDER"]):
        os.makedirs(app.config["UPLOAD_FOLDER"])

    def cleanup_uploads(max_age_hours=24, min_age_minutes=10):
        """Remove uploads mais antigos que X horas, mas não arquivos muito recentes."""
        while True:
            time.sleep(3600)
            try:
                cutoff = datetime.now() - timedelta(hours=max_age_hours)
                min_cutoff = datetime.now() - timedelta(minutes=min_age_minutes)
                for f in os.listdir(app.config["UPLOAD_FOLDER"]):
                    path = os.path.join(app.config["UPLOAD_FOLDER"], f)
                    if os.path.isfile(path):
                        mtime = datetime.fromtimestamp(os.path.getmtime(path))
                        if mtime < cutoff and mtime < min_cutoff:
                            os.remove(path)
                            logger.info("Upload limpo: %s", f)
            except Exception as e:
                logger.warning("Erro na limpeza: %s", e)

    threading.Thread(target=cleanup_uploads, daemon=True).start()

    app.run(debug=True)
