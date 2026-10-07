import os
import uuid
import logging
import bisect
import subprocess
from concurrent.futures import ProcessPoolExecutor, as_completed

from core.pipeline import export_clip
from core.subtitle_renderer import generate_ass, generate_static_ass
from core.subtitle_export import extract_clip_segments
from core.runtime import get_ffmpeg_path

logger = logging.getLogger(__name__)


def _build_word_index(transcription: dict) -> tuple[list[dict], list[float]]:
    """Constrói índice ordenado de palavras para busca binária."""
    all_words = []
    if not transcription:
        return all_words, []
    for seg in transcription.get("segments", []):
        all_words.extend(seg.get("words", []))
    all_words.sort(key=lambda w: w["start"])
    starts = [w["start"] for w in all_words]
    return all_words, starts


def _words_in_range_indexed(
    all_words: list[dict],
    starts: list[float],
    start: float,
    end: float,
) -> list[dict]:
    """Busca binária O(log n) para extrair palavras no intervalo."""
    if not all_words:
        return []
    left = bisect.bisect_left(starts, start)
    right = bisect.bisect_right(starts, end)
    return all_words[left:right]


def _get_optimal_workers() -> int:
    """Determina número máximo de workers paralelos baseado no hardware."""
    try:
        import psutil
        ram_gb = psutil.virtual_memory().available / (1024**3)
    except ImportError:
        ram_gb = 8.0

    cpu = os.cpu_count() or 2
    max_by_ram = max(1, int(ram_gb / 0.5))
    return min(cpu, 2, max_by_ram)


def _process_single_clip(args: tuple) -> dict | None:
    """Processa um clip individual (chamado em worker separado)."""
    (
        video_path, start, end, output_path, ass_path, method,
        out_w, out_h, x_offset, y_offset, zoom_factor,
        score, breakdown, duration, segments,
    ) = args

    try:
        export_clip(
            video_path, start, end, output_path,
            ass_path=ass_path, method=method,
            out_w=out_w, out_h=out_h,
            x_offset=x_offset, y_offset=y_offset,
            zoom_factor=zoom_factor,
        )

        crop_label = _get_crop_label(x_offset)
        zoom_label = f"{zoom_factor:.1f}x" if zoom_factor > 1.0 else None

        return {
            "path": output_path,
            "prob": score,
            "duration": round(duration, 1),
            "breakdown": breakdown,
            "crop": crop_label,
            "zoom": zoom_label,
            "segments": segments,
        }
    except Exception as e:
        logger.error("Erro ao processar clip %.1f-%.1f: %s", start, end, e)
        return None


def _get_crop_label(x_offset: float | None) -> str:
    """Converte x_offset em label legível."""
    if x_offset is None or x_offset == 0.5:
        return "Centro"
    elif x_offset <= 0.1:
        return "Esquerda"
    elif x_offset >= 0.9:
        return "Direita"
    return "Centro"


def generate_clips(
    video_path,
    segments,
    upload_folder,
    transcription=None,
    subtitle_style="tiktok",
    *,
    method="crop",
    out_w=1080,
    out_h=1920,
    x_offset=None,
    y_offset=None,
    zoom_factor=1.0,
    auto_zoom=False,
    caption_position="third",
):
    """
    Gera clips usando pipeline FFmpeg unificado com processamento paralelo.

    Offsets e zoom são resolvidos POR SEGMENTO: `seg["x_offset"]`,
    `seg["y_offset"]` e `seg["zoom_factor"]` têm prioridade sobre os
    parâmetros globais (é assim que o crop automático por face tracking
    e o zoom automático chegam ao FFmpeg).

    Cada clip retornado carrega `segments`: transcrição do próprio clip
    com timestamps relativos (usada pelo export SRT/VTT).
    """
    all_words, starts = _build_word_index(transcription)

    zoom_moments = []
    if auto_zoom:
        from core.auto_zoom import detect_zoom_moments, boost_zoom_for_range
        zoom_moments = detect_zoom_moments(video_path)
        logger.info("Zoom automático: %d momentos de alta energia", len(zoom_moments))

    clip_args = []
    for seg in segments:
        start = seg["start"]
        end = seg["end"]
        duration = end - start

        # Parâmetros por segmento (crop por face / zoom por energia)
        seg_x = seg.get("x_offset", x_offset)
        seg_y = seg.get("y_offset", y_offset)
        seg_zoom = seg.get("zoom_factor", zoom_factor)
        if auto_zoom and zoom_moments:
            seg_zoom = boost_zoom_for_range(zoom_moments, start, end, seg_zoom)

        ass_path = None
        if all_words:
            words = _words_in_range_indexed(all_words, starts, start, end)
            if words:
                shifted = [
                    {"word": w["word"], "start": w["start"] - start, "end": w["end"] - start}
                    for w in words
                ]
                ass_path = os.path.join(upload_folder, f"subs_{uuid.uuid4()}.ass")
                generate_ass(
                    shifted, ass_path,
                    style=subtitle_style, width=out_w, height=out_h,
                    position=caption_position,
                )

        output_path = os.path.join(upload_folder, f"clip_{uuid.uuid4()}.mp4")

        clip_segments = (
            extract_clip_segments(transcription, start, end) if transcription else []
        )

        clip_args.append((
            video_path, start, end, output_path, ass_path,
            method, out_w, out_h, seg_x, seg_y, seg_zoom,
            seg["score"], seg.get("breakdown", {}), duration, clip_segments,
        ))

    workers = _get_optimal_workers()
    logger.info("Gerando %d clips com %d workers", len(clip_args), workers)

    clips = []
    if workers <= 1 or len(clip_args) == 1:
        for args in clip_args:
            result = _process_single_clip(args)
            if result:
                clips.append(result)
    else:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(_process_single_clip, args): i
                for i, args in enumerate(clip_args)
            }
            for future in as_completed(futures):
                result = future.result()
                if result:
                    clips.append(result)

    for args in clip_args:
        ass_path = args[4]
        if ass_path and os.path.exists(ass_path):
            os.remove(ass_path)

    return clips


def add_captions_and_edit(clip_path, text="Texto viral!"):
    """
    Edita um clip existente: caption estática sobreposta + efeito preto-e-branco.

    Implementado com FFmpeg puro (sem MoviePy/ImageMagick): gera um ASS
    estático e queima no vídeo junto com o filtro hue=s=0.
    """
    from core.ffprobe import probe_duration
    from core.video_editor import probe_dimensions

    duration = probe_duration(clip_path)
    if duration <= 0:
        raise RuntimeError(f"Não foi possível determinar a duração de {clip_path}")

    width, height = probe_dimensions(clip_path)

    directory, filename = os.path.split(clip_path)
    edited_filename = filename.replace(".mp4", "_edited.mp4")
    edited_path = os.path.join(directory, edited_filename)

    ass_path = os.path.join(directory, f"edit_{uuid.uuid4()}.ass")
    generate_static_ass(text, duration, ass_path, width=width, height=height)

    try:
        ffmpeg = get_ffmpeg_path()
        cmd = [
            ffmpeg, "-i", clip_path,
            "-vf", f"hue=s=0,ass={ass_path}",
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-c:a", "copy",
            "-y", edited_path,
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        logger.info("Clip editado: %s", edited_path)
    finally:
        if os.path.exists(ass_path):
            os.remove(ass_path)

    return edited_path
