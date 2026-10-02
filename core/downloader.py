import os
import shutil
import uuid
import logging

import yt_dlp

from core.runtime import get_ffmpeg_path, patch_env_path

logger = logging.getLogger(__name__)


def download_video(url: str, output_dir: str) -> str:
    """Download a YouTube video to output_dir and return the local path."""
    filename_template = os.path.join(output_dir, f"{uuid.uuid4()}.mp4")

    ffmpeg_path = get_ffmpeg_path()
    # Garante que ffmpeg/node ficam visíveis no PATH para o yt-dlp
    # (necessário para o runtime JS do yt-dlp-ejs e para o merge de streams).
    patch_env_path()

    ydl_opts = {
        "format": "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": filename_template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "merge_output_format": "mp4",
        "ffmpeg_location": ffmpeg_path,
        "ignoreconfig": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            ydl.download([url])
        except Exception as exc:
            raise RuntimeError(f"Falha no download do yt-dlp: {exc}") from exc

    if not os.path.exists(filename_template) or os.path.getsize(filename_template) == 0:
        if os.path.exists(filename_template):
            os.remove(filename_template)
        raise RuntimeError(
            "O download resultou em um arquivo vazio ou inexistente. "
            "Verifique a URL."
        )

    logger.info("Vídeo baixado: %s", filename_template)
    return filename_template


def resolve_video_source(source: str, input_type: str, output_dir: str) -> str:
    """
    Resolve uma origem de vídeo (URL ou path local) para um arquivo
    dentro de `output_dir`. URLs são baixadas; arquivos locais são copiados.
    """
    if input_type == "url":
        return download_video(source, output_dir)

    if input_type == "file":
        if not os.path.exists(source):
            raise FileNotFoundError(f"Arquivo não encontrado: {source}")
        filename = f"{uuid.uuid4()}.mp4"
        path = os.path.join(output_dir, filename)
        shutil.copy2(source, path)
        return path

    raise ValueError(f"Tipo de entrada inválido: {input_type}")
