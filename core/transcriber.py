import os
import json
import subprocess
import logging
import tempfile

import numpy as np
import librosa
import soundfile as sf

from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)

_MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")
_OUTPUTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "outputs")

_DURATION_THRESHOLD = 30 * 60  # 30 minutos

_model_cache: dict[str, WhisperModel] = {}


def _get_model(model_size: str, device: str, compute_type: str) -> WhisperModel:
    """Retorna modelo Whisper cached. Carrega apenas na primeira chamada."""
    key = f"{model_size}:{device}:{compute_type}"
    if key not in _model_cache:
        logger.info("Carregando modelo Whisper '%s'...", model_size)
        _model_cache[key] = WhisperModel(
            model_size, device=device, compute_type=compute_type,
            download_root=_MODELS_DIR,
        )
    return _model_cache[key]


def release_model_cache() -> None:
    """Libera modelos Whisper da memória."""
    _model_cache.clear()
    import gc
    gc.collect()
    logger.info("Cache de modelos Whisper liberado")


def _get_duration(video_path: str) -> float:
    """Obtém duração do vídeo via ffmpeg (~0.1s)."""
    from core.runtime import get_ffmpeg_path
    ffmpeg = get_ffmpeg_path()
    cmd = [
        ffmpeg, "-i", video_path,
        "-f", "null", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    for line in result.stderr.splitlines():
        if "Duration:" in line:
            try:
                duration_str = line.split("Duration:")[1].split(",")[0].strip()
                parts = duration_str.split(":")
                hours = float(parts[0])
                minutes = float(parts[1])
                seconds = float(parts[2])
                return hours * 3600 + minutes * 60 + seconds
            except (IndexError, ValueError):
                pass
    return 0.0


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


def _process_segments(segments_generator, info) -> dict:
    """Converte generator de segments para dict padronizado."""
    segments = []
    for seg in segments_generator:
        words = []
        if seg.words:
            for w in seg.words:
                words.append({
                    "word": w.word,
                    "start": w.start,
                    "end": w.end,
                })
        segments.append({
            "start": seg.start,
            "end": seg.end,
            "text": seg.text.strip(),
            "words": words,
        })

    return {
        "segments": segments,
        "language": info.language,
        "duration": info.duration,
    }


def _transcribe_full(
    video_path: str,
    model_size: str,
    device: str,
    compute_type: str,
) -> dict:
    """Transcrição completa — usada para vídeos curtos."""
    model = _get_model(model_size, device, compute_type)
    segments_generator, info = model.transcribe(video_path, word_timestamps=True)
    return _process_segments(segments_generator, info)


def _transcribe_selective(
    video_path: str,
    model_size: str,
    device: str,
    compute_type: str,
    duration: float,
) -> dict:
    """Transcrição seletiva — só regiões energéticas de vídeos longos."""
    from core.clip_detector import _segment_energy

    logger.info(
        "Vídeo longo (%.0fmin) — usando transcrição seletiva (top 50%% por energia)",
        duration / 60,
    )

    y = _audio_to_numpy(video_path, sr=22050)
    sr = 22050
    hop_length = 512
    rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=hop_length)[0]

    window_sec = 30
    step_sec = 15
    candidates = []
    for t_f in np.arange(0, duration - window_sec, step_sec):
        t = float(t_f)
        energy = _segment_energy(rms, sr, hop_length, t, t + window_sec)
        candidates.append((t, t + window_sec, energy))

    candidates.sort(key=lambda c: c[2], reverse=True)
    n_keep = max(len(candidates) // 2, 10)
    selected = sorted(candidates[:n_keep], key=lambda c: c[0])

    logger.info(
        "Transcrição seletiva: %d janelas de 30s selecionadas de %d totais",
        len(selected), len(candidates),
    )

    model = _get_model(model_size, device, compute_type)
    all_segments = []

    for start, end, _ in selected:
        i_start = int(start * sr)
        i_end = int(end * sr)
        segment_audio = y[i_start:i_end]

        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()
        try:
            sf.write(tmp.name, segment_audio, sr)
            seg_gen, _ = model.transcribe(tmp.name, word_timestamps=True)
            for seg in seg_gen:
                words = [
                    {"word": w.word, "start": w.start + start, "end": w.end + start}
                    for w in (seg.words or [])
                ]
                all_segments.append({
                    "start": seg.start + start,
                    "end": seg.end + start,
                    "text": seg.text.strip(),
                    "words": words,
                })
        finally:
            if os.path.exists(tmp.name):
                os.remove(tmp.name)

    all_segments.sort(key=lambda s: s["start"])
    merged = _merge_overlapping(all_segments)

    return {
        "segments": merged,
        "language": "auto",
        "duration": duration,
    }


def _merge_overlapping(segments: list[dict]) -> list[dict]:
    """Remove segmentos sobrepostos de janelas adjacentes."""
    if not segments:
        return segments
    merged = [segments[0]]
    for seg in segments[1:]:
        last = merged[-1]
        if seg["start"] < last["end"]:
            if seg["end"] > last["end"]:
                merged[-1] = seg
        else:
            merged.append(seg)
    return merged


def transcribe(
    video_path: str,
    model_size: str = "tiny",
    device: str = "cpu",
    compute_type: str = "int8",
) -> dict:
    """
    Transcribe a video file using faster-whisper with word-level timestamps.

    Para vídeos > 30min, usa transcrição seletiva (top 50% por energia RMS).

    Returns
    -------
    dict with keys:
        segments : list[dict]
            Each segment: {start, end, text, words: [{word, start, end}]}
        language : str
        duration : float (video duration in seconds)
    """
    duration = _get_duration(video_path)

    if duration <= _DURATION_THRESHOLD:
        result = _transcribe_full(video_path, model_size, device, compute_type)
    else:
        result = _transcribe_selective(video_path, model_size, device, compute_type, duration)

    os.makedirs(_OUTPUTS_DIR, exist_ok=True)
    stem = os.path.splitext(os.path.basename(video_path))[0]
    cache_path = os.path.join(_OUTPUTS_DIR, f"{stem}_transcription.json")
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    logger.info("Transcrição salva em %s", cache_path)

    return result
