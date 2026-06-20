"""
core/face_tracker.py — Camera tracking via MediaPipe face detection.

Detecta faces em frames do vídeo e calcula posição média para ajustar o crop.
Roda em CPU, ~30fps com MediaPipe.
"""

import subprocess
import logging
import numpy as np

logger = logging.getLogger(__name__)


def detect_faces_in_clip(
    video_path: str,
    start: float,
    end: float,
    max_frames: int = 30,
) -> dict:
    """
    Detecta faces em um clip e retorna a posição média.

    Parameters
    ----------
    video_path : str
        Caminho do vídeo.
    start, end : float
        Timestamps em segundos.
    max_frames : int
        Máximo de frames a analisar (para performance).

    Returns
    -------
    dict com:
        has_faces : bool
        face_x : float (0.0 = esquerda, 1.0 = direita)
        face_y : float (0.0 = topo, 1.0 = baixo)
        confidence : float (0.0 a 1.0)
    """
    try:
        import mediapipe as mp
    except ImportError:
        logger.warning("MediaPipe não instalado — camera tracking desabilitado")
        return {"has_faces": False, "face_x": 0.5, "face_y": 0.5, "confidence": 0.0}

    frames = _extract_frames(video_path, start, end, max_frames)
    if not frames:
        return {"has_faces": False, "face_x": 0.5, "face_y": 0.5, "confidence": 0.0}

    mp_face = mp.solutions.face_detection
    face_positions = []

    with mp_face.FaceDetection(
        model_selection=0,
        min_detection_confidence=0.5,
    ) as face_detection:
        for frame in frames:
            results = face_detection.process(frame)
            if results.detections:
                for detection in results.detections:
                    bbox = detection.location_data.relative_bounding_box
                    cx = bbox.xmin + bbox.width / 2
                    cy = bbox.ymin + bbox.height / 2
                    confidence = detection.score[0]
                    if confidence > 0.5:
                        face_positions.append((cx, cy, confidence))

    if not face_positions:
        return {"has_faces": False, "face_x": 0.5, "face_y": 0.5, "confidence": 0.0}

    xs = [p[0] for p in face_positions]
    ys = [p[1] for p in face_positions]
    confs = [p[2] for p in face_positions]

    avg_x = float(np.mean(xs))
    avg_y = float(np.mean(ys))
    avg_conf = float(np.mean(confs))

    logger.info(
        "Face detectada: x=%.2f, y=%.2f, conf=%.2f (%d faces em %d frames)",
        avg_x, avg_y, avg_conf, len(face_positions), len(frames),
    )

    return {
        "has_faces": True,
        "face_x": avg_x,
        "face_y": avg_y,
        "confidence": avg_conf,
    }


def face_to_crop_params(face_info: dict) -> dict:
    """
    Converte informação de face em parâmetros de crop.

    Se face está à esquerda (x < 0.4), crop na esquerda.
    Se face está à direita (x > 0.6), crop na direita.
    Caso contrário, centro.
    """
    if not face_info.get("has_faces"):
        return {"x_offset": 0.5, "y_offset": 0.5}

    fx = face_info["face_x"]

    if fx < 0.4:
        x_offset = 0.0  # Esquerda
    elif fx > 0.6:
        x_offset = 1.0  # Direita
    else:
        x_offset = 0.5  # Centro

    return {
        "x_offset": x_offset,
        "y_offset": 0.5,
    }


def _extract_frames(
    video_path: str,
    start: float,
    end: float,
    max_frames: int = 30,
) -> list:
    """Extrai frames do vídeo via FFmpeg pipe como numpy arrays RGB."""
    from core.runtime import get_ffmpeg_path

    ffmpeg = get_ffmpeg_path()
    duration = end - start
    interval = duration / max_frames

    frames = []
    for i in range(max_frames):
        t = start + i * interval
        cmd = [
            ffmpeg,
            "-ss", f"{t:.3f}",
            "-i", video_path,
            "-frames:v", "1",
            "-vf", "scale=320:240",
            "-f", "rawvideo",
            "-pix_fmt", "rgb24",
            "-v", "error",
            "-",
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=5)
            if proc.returncode == 0 and len(proc.stdout) > 0:
                expected_size = 320 * 240 * 3
                if len(proc.stdout) >= expected_size:
                    frame = np.frombuffer(proc.stdout[:expected_size], dtype=np.uint8).reshape(240, 320, 3)
                    frames.append(frame)
        except (subprocess.TimeoutExpired, Exception):
            continue

    return frames
