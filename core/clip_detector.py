import re
import logging

import numpy as np
import librosa

from textblob import TextBlob

logger = logging.getLogger(__name__)

# Padrões de hooks virais (inglês e português)
_HOOK_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        # Perguntas
        r"você (sabia|viu|conhece|ja ouviu)",
        r"(what|why|how|did you|have you|do you|are you)",
        r"você (sabia|viu|conhece|já ouviu)",
        # Intensifiers
    r"(never|always|everyone|nobody|impossible|in[cC]r[ií]vel|amei|odeio|perfeito)",
        r"(you won't believe|you need to see|wait till|watch this)",
        r"(você não vai acreditar|você precisa ver|olha isso|espera até)",
        # Superlativos
        r"(the (best|worst|biggest|most|only))",
        r"(o (melhor|pior|maior|único))",
        r"(this is (crazy|insane|amazing|unreal|wild))",
        r"(isso é (loco|insano|incrível|surreal|selvagem))",
    ]
]


def _calc_audio_energy(video_path: str, sr: int = 22050) -> np.ndarray:
    """Carrega o áudio de um vídeo e retorna o envelope RMS frame a frame."""
    try:
        y, _ = librosa.load(video_path, sr=sr, mono=True)
        hop_length = 512
        rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=hop_length)[0]
        return rms, sr, hop_length
    except Exception as exc:
        logger.warning("Não foi possível analisar áudio de %s: %s", video_path, exc)
        return None, sr, 512


def _segment_energy(
    rms: np.ndarray, sr: int, hop_length: int, start: float, end: float
) -> float:
    """Média do RMS dentro do intervalo [start, end] em segundos."""
    if rms is None:
        return 0.5
    i_start = int(start * sr / hop_length)
    i_end = int(end * sr / hop_length)
    segment = rms[max(0, i_start) : min(len(rms), i_end)]
    if len(segment) == 0:
        return 0.5
    return float(np.mean(segment))


def _sentiment_score(text: str) -> float:
    """Polaridade do texto via TextBlob, normalizada para 0-1."""
    if not text or not text.strip():
        return 0.5
    blob = TextBlob(text)
    # polarity vai de -1 a 1; mapeamos para 0-1
    return (blob.sentiment.polarity + 1) / 2


def _hook_score(text: str) -> float:
    """Retorna 1.0 se algum padrão de hook for encontrado, senão 0."""
    if not text:
        return 0.0
    for pattern in _HOOK_PATTERNS:
        if pattern.search(text):
            return 1.0
    return 0.0


def _density_score(words: list) -> float:
    """Densidade de fala: palavras/segundo normalizada (alvo ~3-4 p/s)."""
    if not words or len(words) < 2:
        return 0.5
    total_words = len(words)
    duration = words[-1]["end"] - words[0]["start"]
    if duration <= 0:
        return 0.5
    wps = total_words / duration
    # 3.5 p/s é considerado ideal; normalizar com sigmoid suave
    return float(1.0 / (1.0 + np.exp(-0.8 * (wps - 3.0))))


def _combine_score(
    sentiment: float,
    energy: float,
    hook: float,
    density: float,
) -> int:
    """Ponderação dos 4 fatores → score 0-100."""
    weights = {
        "sentiment": 0.20,
        "energy": 0.30,
        "hook": 0.30,
        "density": 0.20,
    }
    raw = (
        weights["sentiment"] * sentiment
        + weights["energy"] * energy
        + weights["hook"] * hook
        + weights["density"] * density
    )
    return min(100, max(0, int(raw * 100)))


def _extract_segment_text(transcription: dict, start: float, end: float) -> str:
    """Extrai texto da transcrição dentro do intervalo [start, end]."""
    parts = []
    for seg in transcription.get("segments", []):
        if seg["start"] < end and seg["end"] > start:
            parts.append(seg["text"])
    return " ".join(parts)


def _extract_segment_words(transcription: dict, start: float, end: float) -> list:
    """Extrai words dentro do intervalo [start, end]."""
    words = []
    for seg in transcription.get("segments", []):
        for w in seg.get("words", []):
            if w["start"] >= start and w["end"] <= end:
                words.append(w)
    return words


def detect_clips(
    transcription: dict,
    video_path: str,
    num_clips: int = 5,
    clip_duration: float = 30.0,
    min_segment_duration: float = 5.0,
) -> list[dict]:
    """
    Analisa a transcrição + áudio e retorna os N melhores segmentos para clipes.

    Cada item retornado:
        {
            "start": float,
            "end": float,
            "score": int (0-100),
            "breakdown": {
                "sentiment": float,
                "energy": float,
                "hook": bool,
                "density": float
            }
        }
    """
    duration = transcription.get("duration", 0)
    if duration <= 0:
        logger.warning("Duração do vídeo inválida: %s", duration)
        return []

    rms, sr, hop_length = _calc_audio_energy(video_path)

    # Janelas deslizantes de clip_duration segundos
    candidates = []
    step = clip_duration / 2  # 50% de overlap
    t = 0.0
    while t + clip_duration <= duration:
        start = t
        end = t + clip_duration

        text = _extract_segment_text(transcription, start, end)
        words = _extract_segment_words(transcription, start, end)

        sentiment = _sentiment_score(text)
        energy = _segment_energy(rms, sr, hop_length, start, end) if rms is not None else 0.5
        hook = _hook_score(text)
        density = _density_score(words)

        score = _combine_score(sentiment, energy, hook, density)

        candidates.append({
            "start": round(start, 1),
            "end": round(end, 1),
            "score": score,
            "breakdown": {
                "sentiment": round(sentiment, 3),
                "energy": round(energy, 3),
                "hook": bool(hook),
                "density": round(density, 3),
            },
        })
        t += step

    # Ordenar por score descendente e pegar os top N
    candidates.sort(key=lambda c: c["score"], reverse=True)
    top = candidates[:num_clips]

    logger.info(
        "detect_clips: %d candidatos analisados, top %d selecionados (score máximo: %d)",
        len(candidates),
        num_clips,
        top[0]["score"] if top else 0,
    )

    return top
