import os
import json
import logging

from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)

_MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")
_OUTPUTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "outputs")


def transcribe(
    video_path: str,
    model_size: str = "tiny",
    device: str = "cpu",
    compute_type: str = "int8",
) -> dict:
    """
    Transcribe a video file using faster-whisper with word-level timestamps.

    Returns
    -------
    dict with keys:
        segments : list[dict]
            Each segment: {start, end, text, words: [{word, start, end}]}
        language : str
        duration : float (video duration in seconds, from whisper)
    """
    model = WhisperModel(model_size, device=device, compute_type=compute_type, download_root=_MODELS_DIR)

    segments_generator, info = model.transcribe(video_path, word_timestamps=True)

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

    result = {
        "segments": segments,
        "language": info.language,
        "duration": info.duration,
    }

    # Cache JSON em outputs/ para debug/reuso
    os.makedirs(_OUTPUTS_DIR, exist_ok=True)
    stem = os.path.splitext(os.path.basename(video_path))[0]
    cache_path = os.path.join(_OUTPUTS_DIR, f"{stem}_transcription.json")
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    logger.info("Transcrição salva em %s", cache_path)

    return result
