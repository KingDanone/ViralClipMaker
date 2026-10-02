import os
import subprocess
import logging

from core.runtime import get_ffmpeg_path

logger = logging.getLogger(__name__)

# ── Style definitions ──────────────────────────────────────────────────

_STYLES = {
    "tiktok": {
        "font": "Arial",
        "fontsize": 68,
        "bold": -1,
        "primary": "&H00FFFFFF",
        "secondary": "&H0000FFFF",
        "outline": "&H00000000",
        "outline_w": 2,
        "shadow": 0,
        "margin_v": 100,
    },
    "bold_shadow": {
        "font": "Arial",
        "fontsize": 66,
        "bold": -1,
        "primary": "&H00FFFFFF",
        "secondary": "&H0000CCFF",
        "outline": "&H00000000",
        "outline_w": 3,
        "shadow": 2,
        "margin_v": 100,
    },
    "neon": {
        "font": "Arial",
        "fontsize": 70,
        "bold": 0,
        "primary": "&H0000FFFF",
        "secondary": "&H00FF00FF",
        "outline": "&H00222222",
        "outline_w": 1,
        "shadow": 3,
        "margin_v": 110,
    },
    "minimal": {
        "font": "Arial",
        "fontsize": 60,
        "bold": 0,
        "primary": "&H00FFFFFF",
        "secondary": "&H00AAAAAA",
        "outline": "&H00000000",
        "outline_w": 1,
        "shadow": 1,
        "margin_v": 100,
    },
}


def _ass_escape(text: str) -> str:
    return text.replace("{", "\\{").replace("}", "\\}")


def _secs_to_ass(seconds: float) -> str:
    """Converte segundos para o formato ASS H:MM:SS.cc (sem overflow de centésimos)."""
    total_cs = int(round(max(0.0, seconds) * 100))
    h, rem = divmod(total_cs, 360_000)
    m, rem = divmod(rem, 6_000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _group_words(words: list[dict], max_words: int = 7) -> list[list[dict]]:
    groups = []
    current = []
    for w in words:
        current.append(w)
        if len(current) >= max_words:
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return groups


def _ass_header(width: int, height: int, style_name: str) -> str:
    s = _STYLES.get(style_name, _STYLES["tiktok"])
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style:{style_name},{s["font"]},{s["fontsize"]},{s["primary"]},{s["secondary"]},{s["outline"]},&H00000000,{s["bold"]},0,0,0,100,100,0,0,1,{s["outline_w"]},{s["shadow"]},2,50,50,{s["margin_v"]},1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""


def _words_to_ass_events(
    words: list[dict], style_name: str
) -> list[str]:
    groups = _group_words(words, max_words=7)
    events = []
    for group in groups:
        g_start = group[0]["start"]
        g_end = group[-1]["end"]
        karaoke_parts = []
        for w in group:
            dur_cs = max(1, int(round((w["end"] - w["start"]) * 100)))
            escaped = _ass_escape(w["word"])
            karaoke_parts.append(f"{{\\k{dur_cs}}}{escaped} ")
        text = "".join(karaoke_parts).strip()
        events.append(
            f"Dialogue: 0,{_secs_to_ass(g_start)},{_secs_to_ass(g_end)},{style_name},,0,0,0,,{text}"
        )
    return events


def generate_ass(
    words: list[dict],
    output_ass: str,
    *,
    style: str = "tiktok",
    width: int = 1080,
    height: int = 1920,
) -> str:
    if style not in _STYLES:
        style = "tiktok"

    header = _ass_header(width, height, style)
    events = _words_to_ass_events(words, style)

    with open(output_ass, "w", encoding="utf-8") as f:
        f.write(header)
        for ev in events:
            f.write(ev + "\n")

    logger.info("ASS gerado: %s (%d linhas, estilo=%s)", output_ass, len(events), style)
    return output_ass


def generate_static_ass(
    text: str,
    duration: float,
    output_ass: str,
    *,
    style: str = "tiktok",
    width: int = 1080,
    height: int = 1920,
) -> str:
    """Gera um .ass com um único texto estático visível durante todo o clip."""
    if style not in _STYLES:
        style = "tiktok"

    header = _ass_header(width, height, style)
    event = (
        f"Dialogue: 0,{_secs_to_ass(0.0)},{_secs_to_ass(duration)},"
        f"{style},,0,0,0,,{_ass_escape(text)}"
    )

    with open(output_ass, "w", encoding="utf-8") as f:
        f.write(header)
        f.write(event + "\n")

    logger.info("ASS estático gerado: %s (estilo=%s)", output_ass, style)
    return output_ass


def burn_subtitles(
    video_path: str,
    output_path: str,
    ass_path: str,
) -> str:
    ffmpeg = get_ffmpeg_path()
    cmd = [
        ffmpeg,
        "-i", video_path,
        "-vf", f"ass={ass_path}",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "22",
        "-c:a", "aac",
        "-b:a", "128k",
        "-y",
        output_path,
    ]
    logger.debug("FFmpeg burn: %s", " ".join(cmd))
    subprocess.run(cmd, check=True, capture_output=True)
    logger.info("Legendas queimadas: %s", output_path)
    return output_path


def add_word_captions(
    video_path: str,
    output_path: str,
    words: list[dict],
    *,
    style: str = "tiktok",
    width: int = 1080,
    height: int = 1920,
) -> str:
    if not words:
        logger.warning("Nenhuma palavra para legendas — copiando vídeo original")
        import shutil
        shutil.copy2(video_path, output_path)
        return output_path

    ass_path = output_path.replace(".mp4", ".ass")
    generate_ass(words, ass_path, style=style, width=width, height=height)
    return burn_subtitles(video_path, output_path, ass_path)
