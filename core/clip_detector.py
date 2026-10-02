import re
import subprocess
import logging

import numpy as np
import librosa

from textblob import TextBlob

logger = logging.getLogger(__name__)

_HOOK_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"você (sabia|viu|conhece|já ouviu)",
        r"(what|why|how|did you|have you|do you|are you)",
        r"(never|always|everyone|nobody|impossible|incrível|amei|odeio|perfeito)",
        r"(you won't believe|you need to see|wait till|watch this)",
        r"(você não vai acreditar|você precisa ver|olha isso|espera até)",
        r"(the (best|worst|biggest|most|only))",
        r"(o (melhor|pior|maior|único))",
        r"(this is (crazy|insane|amazing|unreal|wild))",
        r"(isso é (louco|insano|incrível|surreal|absurdo))",
    ]
]

# Léxico PT-BR para sentimento — TextBlob só funciona bem em inglês.
_PT_POSITIVE = {
    "incrível", "incrivel", "amazing", "melhor", "melhores", "top", "amei",
    "amo", "adoro", "perfeito", "perfeita", "genial", "fantástico",
    "fantastico", "maravilhoso", "maravilhosa", "excelente", "sensacional",
    "épico", "epico", "brabo", "braba", "lendário", "lendario", "demais",
    "show", "parabéns", "parabens", "sucesso", "viral", "imperdível",
    "imperdivel", "ótimo", "otimo", "bom", "boa", "legal", "maneiro",
    "massa", "dahora", "curti", "gostei", "feliz", "engraçado", "hilário",
    "hilario", "insano", "insana", "surpreendente", "forte", "poderoso",
    "eficiente", "funciona", "grátis", "gratis", "fácil", "facil",
    "rápido", "rapido", "ganhar", "ganhe", "lucro", "vencer", "conquistar",
}
_PT_NEGATIVE = {
    "pior", "piores", "horrível", "horrivel", "odeio", "detesto",
    "terrível", "terrivel", "chato", "chata", "ruim", "fraco", "fraca",
    "lento", "demorado", "difícil", "dificil", "impossível", "impossivel",
    "fracasso", "erro", "falha", "falhou", "mentira", "fake", "golpe",
    "perda", "perder", "prejuízo", "prejuizo", "caro", "cansativo",
    "tedioso", "problema", "nunca", "jamais", "ninguém", "triste",
}

_TOKEN_RE = re.compile(r"[\wáàâãéèêíïóôõúûüç]+", re.UNICODE)

# Razão máxima de sobreposição entre clips selecionados (NMS temporal).
_MAX_OVERLAP = 0.5


def _audio_to_numpy(video_path: str, sr: int = 22050) -> np.ndarray:
    """Extrai áudio via FFmpeg pipe para numpy array (sem arquivo temporário)."""
    from core.runtime import get_ffmpeg_path

    ffmpeg = get_ffmpeg_path()
    cmd = [
        ffmpeg, "-i", video_path,
        "-vn",
        "-f", "s16le", "-acodec", "pcm_s16le",
        "-ar", str(sr), "-ac", "1",
        "-",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, check=True)
        audio = np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32) / 32768.0
        return audio
    except Exception as exc:
        logger.warning("FFmpeg audio pipe falhou: %s — tentando librosa", exc)
        y, _ = librosa.load(video_path, sr=sr, mono=True)
        return y


def _calc_audio_energy(video_path: str, sr: int = 22050):
    """Carrega áudio via FFmpeg pipe e retorna envelope RMS."""
    try:
        y = _audio_to_numpy(video_path, sr=sr)
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


def _lexicon_sentiment(text: str) -> float:
    """Sentimento 0-1 via léxico PT-BR (TextBlob não funciona em português)."""
    tokens = set(_TOKEN_RE.findall(text.lower()))
    pos = len(tokens & _PT_POSITIVE)
    neg = len(tokens & _PT_NEGATIVE)
    hits = pos + neg
    if hits == 0:
        return 0.5
    return 0.5 + 0.5 * (pos - neg) / hits


def _sentiment_score(text: str, language: str = "auto") -> float:
    """
    Sentimento 0-1 do texto.

    Usa TextBlob para inglês e léxico PT-BR para os demais idiomas
    (TextBlob sempre retorna polaridade 0 para português).
    """
    if not text or not text.strip():
        return 0.5
    if (language or "auto").lower().startswith("en"):
        blob = TextBlob(text)
        return (blob.sentiment.polarity + 1) / 2
    return _lexicon_sentiment(text)


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


def _overlap_ratio(a: dict, b: dict) -> float:
    """Fração do clip mais curto coberta pelo outro (0.0 a 1.0)."""
    inter = min(a["end"], b["end"]) - max(a["start"], b["start"])
    if inter <= 0:
        return 0.0
    shorter = min(a["end"] - a["start"], b["end"] - b["start"])
    return inter / shorter if shorter > 0 else 0.0


def _select_top_n(candidates: list[dict], num_clips: int) -> list[dict]:
    """Seleciona os N melhores candidatos suprimindo sobreposição (NMS temporal)."""
    selected = []
    for cand in sorted(candidates, key=lambda c: c["score"], reverse=True):
        if all(_overlap_ratio(cand, s) < _MAX_OVERLAP for s in selected):
            selected.append(cand)
        if len(selected) >= num_clips:
            break
    return selected


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

    language = transcription.get("language", "auto")

    # Fallback: vídeo mais curto que a duração pedida vira um único clip.
    clip_duration = float(clip_duration) if clip_duration else 30.0
    if clip_duration <= 0:
        clip_duration = 30.0
    clip_duration = min(clip_duration, duration)

    rms, sr, hop_length = _calc_audio_energy(video_path)

    def _score_window(start: float, end: float) -> dict:
        text = _extract_segment_text(transcription, start, end)
        words = _extract_segment_words(transcription, start, end)

        sentiment = _sentiment_score(text, language)
        energy = _segment_energy(rms, sr, hop_length, start, end) if rms is not None else 0.5
        hook = _hook_score(text)
        density = _density_score(words)
        score = _combine_score(sentiment, energy, hook, density)

        return {
            "start": round(start, 1),
            "end": round(end, 1),
            "score": score,
            "breakdown": {
                "sentiment": round(sentiment, 3),
                "energy": round(energy, 3),
                "hook": bool(hook),
                "density": round(density, 3),
            },
        }

    candidates = []
    step = max(clip_duration / 2, 1.0)
    t = 0.0
    while t + clip_duration <= duration + 1e-6:
        candidates.append(_score_window(t, t + clip_duration))
        t += step

    if not candidates and duration >= min_segment_duration:
        candidates.append(_score_window(0.0, duration))

    top = _select_top_n(candidates, num_clips)

    logger.info(
        "detect_clips: %d candidatos analisados, %d selecionados (score máximo: %d)",
        len(candidates),
        len(top),
        top[0]["score"] if top else 0,
    )

    return top
