"""
core/auto_zoom.py — Zoom automático baseado em energia de áudio.

Detecta momentos de alta energia para aplicar zoom automaticamente.
"""

import numpy as np
import logging

logger = logging.getLogger(__name__)


def detect_zoom_moments(
    video_path: str,
    threshold: float = 0.7,
    min_duration: float = 2.0,
    max_duration: float = 5.0,
) -> list[dict]:
    """
    Detecta momentos de alta energia para zoom automático.

    Parameters
    ----------
    video_path : str
        Caminho do vídeo.
    threshold : float
        Limiar de energia (0.0 a 1.0). Momentos acima deste limiar recebem zoom.
    min_duration : float
        Duração mínima do zoom em segundos.
    max_duration : float
        Duração máxima do zoom em segundos.

    Returns
    -------
    list[dict]
        Lista de momentos: [{"start": float, "end": float, "energy": float}]
    """
    from core.clip_detector import _calc_audio_energy, _segment_energy

    rms, sr, hop_length = _calc_audio_energy(video_path)
    if rms is None:
        return []

    duration = len(rms) * hop_length / sr
    window = 3.0
    step = 0.5

    moments = []
    t = 0.0
    while t + window <= duration:
        energy = _segment_energy(rms, sr, hop_length, t, t + window)
        if energy >= threshold:
            moments.append({
                "start": round(t, 2),
                "end": round(min(t + window, duration), 2),
                "energy": round(energy, 3),
            })
        t += step

    moments = _merge_close_moments(moments, min_duration, max_duration)

    logger.info(
        "Zoom automático: %d momentos detectados (threshold=%.2f)",
        len(moments), threshold,
    )

    return moments


def boost_zoom_for_range(
    moments: list[dict],
    start: float,
    end: float,
    base_zoom: float = 1.0,
    boost: float = 1.3,
) -> float:
    """
    Retorna o zoom a aplicar em [start, end]: se algum momento de alta
    energia se sobrepõe ao intervalo, eleva o zoom para pelo menos `boost`.
    """
    zoom = base_zoom
    for m in moments:
        if m["start"] < end and m["end"] > start:
            zoom = max(zoom, boost)
    return zoom


def _merge_close_moments(
    moments: list[dict],
    min_duration: float,
    max_duration: float,
) -> list[dict]:
    """Mescla momentos próximos e limita duração."""
    if not moments:
        return moments

    merged = [moments[0]]
    for m in moments[1:]:
        last = merged[-1]
        if m["start"] - last["end"] < 1.0:
            last["end"] = min(m["end"], last["start"] + max_duration)
            last["energy"] = max(last["energy"], m["energy"])
        else:
            merged.append(m)

    result = []
    for m in merged:
        dur = m["end"] - m["start"]
        if dur < min_duration:
            m["end"] = m["start"] + min_duration
        elif dur > max_duration:
            m["end"] = m["start"] + max_duration
        result.append(m)

    return result
