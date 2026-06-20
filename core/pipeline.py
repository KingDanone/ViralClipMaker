"""
core/pipeline.py — Pipeline unificado de processamento de clips.

Substitui: MoviePy subclip + reframe_9_16 + burn_subtitles
Por: um único comando FFmpeg por clip.

Redução: 3 encodes/clip → 1 encode/clip (~3-4x mais rápido).
"""

import os
import subprocess
import logging
from core.runtime import get_ffmpeg_path
from core.video_editor import probe_dimensions, _METHODS

logger = logging.getLogger(__name__)


def export_clip(
    video_path: str,
    start: float,
    end: float,
    output_path: str,
    ass_path: str | None = None,
    *,
    method: str = "crop",
    out_w: int = 1080,
    out_h: int = 1920,
    x_offset: float | None = None,
    y_offset: float | None = None,
    zoom_factor: float = 1.0,
) -> str:
    """
    Extrai, reframe e opcionalmente legenda um clip em um único passo FFmpeg.

    Parameters
    ----------
    video_path : str
        Caminho do vídeo original.
    start, end : float
        Timestamps em segundos.
    output_path : str
        Caminho do arquivo de saída.
    ass_path : str | None
        Caminho do arquivo .ass para legendas. Se None, sem legendas.
    method : str
        Método de reframe: "crop", "letterbox", "blur".
    out_w, out_h : int
        Dimensões de saída.
    x_offset : float | None
        Offset horizontal do crop (0.0 = esquerda, 0.5 = centro, 1.0 = direita).
        None = centro (padrão).
    y_offset : float | None
        Offset vertical do crop (0.0 = topo, 0.5 = centro, 1.0 = baixo).
        None = centro (padrão).
    zoom_factor : float
        Fator de zoom (1.0 = sem zoom, 1.5 = 50% zoom). Padrão: 1.0.

    Returns
    -------
    str
        Caminho do arquivo gerado.
    """
    ffmpeg = get_ffmpeg_path()
    duration = end - start

    in_w, in_h = probe_dimensions(video_path)

    filter_str = _build_filter_chain(
        in_w, in_h, out_w, out_h,
        method=method,
        x_offset=x_offset,
        y_offset=y_offset,
        zoom_factor=zoom_factor,
    )

    if ass_path and os.path.exists(ass_path):
        filter_str = f"{filter_str},ass={ass_path}"

    cmd = [
        ffmpeg,
        "-ss", f"{start:.3f}",
        "-t", f"{duration:.3f}",
        "-i", video_path,
        "-vf", filter_str,
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "aac", "-b:a", "128k",
        "-y", output_path,
    ]

    logger.debug("Pipeline FFmpeg: %s", " ".join(cmd))
    subprocess.run(cmd, check=True, capture_output=True)
    logger.info(
        "Clip exportado: %s (%.1fs-%.1fs, %s, zoom=%.1fx)",
        output_path, start, end, method, zoom_factor,
    )

    return output_path


def _build_filter_chain(
    in_w: int,
    in_h: int,
    out_w: int,
    out_h: int,
    *,
    method: str = "crop",
    x_offset: float | None = None,
    y_offset: float | None = None,
    zoom_factor: float = 1.0,
) -> str:
    """
    Constrói a filter chain FFmpeg para crop + scale.

    Suporta offset customizado e zoom para crop editável.
    """
    if method not in _METHODS:
        method = "crop"

    if method == "crop":
        return _build_crop_filter(
            in_w, in_h, out_w, out_h,
            x_offset=x_offset,
            y_offset=y_offset,
            zoom_factor=zoom_factor,
        )

    return _METHODS[method](in_w, in_h, out_w, out_h)


def _build_crop_filter(
    in_w: int,
    in_h: int,
    out_w: int,
    out_h: int,
    *,
    x_offset: float | None = None,
    y_offset: float | None = None,
    zoom_factor: float = 1.0,
) -> str:
    """
    Constrói filtro de crop com suporte a offset e zoom.

    x_offset: 0.0 = esquerda, 0.5 = centro, 1.0 = direita
    y_offset: 0.0 = topo, 0.5 = centro, 1.0 = baixo
    zoom_factor: 1.0 = sem zoom, 1.5 = 50% zoom
    """
    target_ratio = out_w / out_h
    input_ratio = in_w / in_h

    if abs(input_ratio - target_ratio) < 0.01 and zoom_factor <= 1.0:
        return f"scale={out_w}:{out_h}"

    if input_ratio > target_ratio:
        crop_w = int(in_h * target_ratio)
        crop_h = in_h
    else:
        crop_w = in_w
        crop_h = int(in_w / target_ratio)

    if zoom_factor > 1.0:
        crop_w = int(crop_w / zoom_factor)
        crop_h = int(crop_h / zoom_factor)

    crop_w = min(crop_w, in_w)
    crop_h = min(crop_h, in_h)

    if x_offset is None:
        x = (in_w - crop_w) // 2
    else:
        max_x = in_w - crop_w
        x = int(max_x * max(0.0, min(1.0, x_offset)))

    if y_offset is None:
        y = (in_h - crop_h) // 2
    else:
        max_y = in_h - crop_h
        y = int(max_y * max(0.0, min(1.0, y_offset)))

    return f"crop={crop_w}:{crop_h}:{x}:{y},scale={out_w}:{out_h}"
