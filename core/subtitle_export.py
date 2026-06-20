"""
core/subtitle_export.py — Export de legendas em formato SRT e VTT.
"""


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


def _format_srt_time(seconds: float) -> str:
    """Formata tempo para SRT: HH:MM:SS,mmm"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _format_vtt_time(seconds: float) -> str:
    """Formata tempo para VTT: HH:MM:SS.mmm"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"
