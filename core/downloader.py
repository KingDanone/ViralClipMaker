import os
import uuid
import logging

import yt_dlp

from core.runtime import get_ffmpeg_path, get_node_path, patch_env_path

logger = logging.getLogger(__name__)


def download_video(url: str, output_dir: str) -> str:
    """Download a YouTube video to output_dir and return the local path."""
    filename_template = os.path.join(output_dir, f"{uuid.uuid4()}.mp4")

    node_path = get_node_path()
    node_bin_dir = os.path.dirname(node_path)
    if node_bin_dir not in os.environ.get("PATH", ""):
        os.environ["PATH"] = node_bin_dir + os.pathsep + os.environ.get("PATH", "")

    ffmpeg_path = get_ffmpeg_path()

    patch_env_path()

    ydl_opts = {
        "format": "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": filename_template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "merge_output_format": "mp4",
        "ffmpeg_location": ffmpeg_path,
        "js_runtimes": {"node": {}},
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
