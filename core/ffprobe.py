"""
core/ffprobe.py — Leitura rápida de metadados do vídeo via FFmpeg.

Roda `ffmpeg -i <video>` SEM argumentos de saída: o FFmpeg imprime o
cabeçalho (Duration, Stream WxH) no stderr e encerra imediatamente,
sem decodificar nenhum frame. Substitui o padrão antigo
`ffmpeg -i ... -f null -`, que decodificava o vídeo inteiro só para
ler o header.
"""

import re
import subprocess
import logging

from core.runtime import get_ffmpeg_path

logger = logging.getLogger(__name__)

_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
_DIMENSIONS_RE = re.compile(r"Video:.*?[^\d](\d{2,6})x(\d{2,6})[^\d]")


def _read_header(video_path: str) -> str:
    """Retorna o stderr do FFmpeg contendo o cabeçalho do vídeo."""
    ffmpeg = get_ffmpeg_path()
    cmd = [ffmpeg, "-hide_banner", "-i", video_path]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return result.stderr or ""


def probe_duration(video_path: str) -> float:
    """
    Retorna a duração do vídeo em segundos lendo apenas o header.

    Returns 0.0 se não for possível determinar.
    """
    try:
        stderr = _read_header(video_path)
    except Exception as exc:
        logger.warning("probe_duration falhou para %s: %s", video_path, exc)
        return 0.0

    match = _DURATION_RE.search(stderr)
    if not match:
        return 0.0

    hours, minutes, seconds = (
        int(match.group(1)),
        int(match.group(2)),
        float(match.group(3)),
    )
    return hours * 3600 + minutes * 60 + seconds


def probe_video_dimensions(video_path: str) -> tuple[int, int] | None:
    """
    Retorna (largura, altura) do primeiro stream de vídeo.

    Returns None se não for possível determinar.
    """
    try:
        stderr = _read_header(video_path)
    except Exception as exc:
        logger.warning("probe_video_dimensions falhou para %s: %s", video_path, exc)
        return None

    for line in stderr.splitlines():
        if "Video:" not in line:
            continue
        match = _DIMENSIONS_RE.search(line)
        if match:
            return int(match.group(1)), int(match.group(2))
    return None
