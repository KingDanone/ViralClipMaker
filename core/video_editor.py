import re
import subprocess
import logging

from core.runtime import get_ffmpeg_path

logger = logging.getLogger(__name__)

_dim_cache: dict[str, tuple[int, int]] = {}


def probe_dimensions(video_path: str) -> tuple[int, int]:
    """Retorna (largura, altura) do vídeo. Cacheia resultado para evitar probes repetidos."""
    if video_path in _dim_cache:
        return _dim_cache[video_path]

    ffmpeg = get_ffmpeg_path()
    cmd = [
        ffmpeg, "-i", video_path,
        "-f", "null", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    stderr = result.stderr
    for line in stderr.splitlines():
        if "Stream #0:0" in line and "Video:" in line:
            parts = line.split(",")
            for p in parts:
                p = p.strip()
                if "x" in p and any(c.isdigit() for c in p):
                    try:
                        match = re.search(r'(\d{2,})x(\d{2,})', p)
                        if match:
                            w_num = int(match.group(1))
                            h_num = int(match.group(2))
                            _dim_cache[video_path] = (w_num, h_num)
                            return w_num, h_num
                    except (ValueError, AttributeError):
                        pass

    _dim_cache[video_path] = (1080, 1920)
    return 1080, 1920


_probe_aspect = probe_dimensions


def _build_filter_crop(
    in_w: int,
    in_h: int,
    out_w: int,
    out_h: int,
    *,
    x_offset: float | None = None,
    y_offset: float | None = None,
    zoom_factor: float = 1.0,
) -> str:
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


def _build_filter_letterbox(in_w: int, in_h: int, out_w: int, out_h: int) -> str:
    return (
        f"scale={out_w}:{out_h}:force_original_aspect_ratio=decrease,"
        f"pad={out_w}:{out_h}:(ow-iw)/2:(oh-ih)/2:color=black"
    )


def _build_filter_blur(in_w: int, in_h: int, out_w: int, out_h: int) -> str:
    return (
        f"split[original][blur];"
        f"[blur]scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
        f"crop={out_w}:{out_h},boxblur=20[bg];"
        f"[original]scale={out_w}:{out_h}:force_original_aspect_ratio=decrease[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2"
    )


_METHODS = {
    "crop": _build_filter_crop,
    "letterbox": _build_filter_letterbox,
    "blur": _build_filter_blur,
}


def reframe_9_16(
    video_path: str,
    output_path: str,
    *,
    method: str = "crop",
    output_width: int = 1080,
    output_height: int = 1920,
) -> str:
    if method not in _METHODS:
        method = "crop"

    in_w, in_h = probe_dimensions(video_path)
    filter_str = _METHODS[method](in_w, in_h, output_width, output_height)

    ffmpeg = get_ffmpeg_path()
    cmd = [
        ffmpeg, "-i", video_path,
        "-vf", filter_str,
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "aac", "-b:a", "128k",
        "-y", output_path,
    ]
    logger.debug("FFmpeg reframe: %s", " ".join(cmd))
    subprocess.run(cmd, check=True, capture_output=True)
    logger.info(
        "Reframe %s: %s (%s, %dx%d → %dx%d)",
        method, output_path, video_path, in_w, in_h, output_width, output_height,
    )
    return output_path
