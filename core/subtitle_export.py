"""
core/subtitle_export.py — Export de legendas em formato SRT e VTT.

Os segmentos exportados usam timestamps RELATIVOS ao início do clip
(00:00:00), não ao vídeo original. Use `extract_clip_segments` para
recortar a transcrição do vídeo para o intervalo do clip.
"""


def extract_clip_segments(
    transcription: dict, start: float, end: float
) -> list[dict]:
    """
    Extrai os segmentos de `transcription` que intersectam [start, end],
    já com timestamps relativos ao início do clip.
    """
    out = []
    for seg in transcription.get("segments", []):
        if seg["start"] >= end or seg["end"] <= start:
            continue
        clipped = {
            "start": max(0.0, seg["start"] - start),
            "end": min(seg["end"], end) - start,
            "text": seg.get("text", "").strip(),
        }
        words = [
            {
                "word": w["word"],
                "start": max(0.0, w["start"] - start),
                "end": min(w["end"], end) - start,
            }
            for w in seg.get("words", [])
            if w["start"] >= start and w["end"] <= end
        ]
        if words:
            clipped["words"] = words
        out.append(clipped)
    return out


def export_srt(segments: list[dict], output_path: str) -> str:
    """Exporta segmentos de transcrição como arquivo .srt."""
    with open(output_path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(segments, 1):
            start = _format_srt_time(seg["start"])
            end = _format_srt_time(seg["end"])
            text = seg.get("text", "").strip()
            f.write(f"{i}\n{start} --> {end}\n{text}\n\n")
    return output_path


def export_vtt(segments: list[dict], output_path: str) -> str:
    """Exporta segmentos de transcrição como arquivo .vtt."""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("WEBVTT\n\n")
        for seg in segments:
            start = _format_vtt_time(seg["start"])
            end = _format_vtt_time(seg["end"])
            text = seg.get("text", "").strip()
            f.write(f"{start} --> {end}\n{text}\n\n")
    return output_path


def _split_ms(seconds: float) -> tuple[int, int, int, int]:
    """Decompõe segundos em (h, m, s, ms) com carry correto (ms nunca passa de 999)."""
    total_ms = int(round(max(0.0, seconds) * 1000))
    h, rem = divmod(total_ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1_000)
    return h, m, s, ms


def _format_srt_time(seconds: float) -> str:
    """Formata tempo para SRT: HH:MM:SS,mmm"""
    h, m, s, ms = _split_ms(seconds)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _format_vtt_time(seconds: float) -> str:
    """Formata tempo para VTT: HH:MM:SS.mmm"""
    h, m, s, ms = _split_ms(seconds)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"
