import subprocess
import logging

from core.runtime import get_ffmpeg_path

logger = logging.getLogger(__name__)


def _probe_aspect(video_path: str) -> tuple[int, int]:
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
                        w, h = p.split("x")[:2]
                        return int(w.strip()), int(h.strip())
                    except ValueError:
                        pass
    return 1080, 1920


def _build_filter_crop(in_w: int, in_h: int, out_w: int, out_h: int) -> str:
    target_ratio = out_w / out_h
    input_ratio = in_w / in_h

    if abs(input_ratio - target_ratio) < 0.01:
        return f"scale={out_w}:{out_h}"

    if input_ratio > target_ratio:
        crop_w = int(in_h * target_ratio)
        crop_h = in_h
        x = (in_w - crop_w) // 2
        y = 0
    else:
        crop_w = in_w
        crop_h = int(in_w / target_ratio)
        x = 0
        y = (in_h - crop_h) // 2

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

    in_w, in_h = _probe_aspect(video_path)
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
