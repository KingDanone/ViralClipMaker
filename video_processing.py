import os
import uuid
import logging
import bisect
from concurrent.futures import ProcessPoolExecutor, as_completed

from core.pipeline import export_clip
from core.subtitle_renderer import generate_ass

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
    import os
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
    video_path, start, end, output_path, ass_path, method, out_w, out_h, x_offset, y_offset, zoom_factor, score, breakdown, duration = args

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
        }
    except Exception as e:
        logger.error("Erro ao processar clip %.1f-%.1f: %s", start, end, e)
        return None


def _get_crop_label(x_offset: float | None) -> str:
    """Converte x_offset em label legível."""
    if x_offset is None:
        return "Centro"
    elif x_offset == 0.5:
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
):
    """
    Gera clips usando pipeline FFmpeg unificado com processamento paralelo.
    """
    all_words, starts = _build_word_index(transcription)

    clip_args = []
    for seg in segments:
        start = seg["start"]
        end = seg["end"]
        duration = end - start

        ass_path = None
        if all_words:
            words = _words_in_range_indexed(all_words, starts, start, end)
            if words:
                shifted = [
                    {"word": w["word"], "start": w["start"] - start, "end": w["end"] - start}
                    for w in words
                ]
                ass_path = os.path.join(upload_folder, f"subs_{uuid.uuid4()}.ass")
                generate_ass(shifted, ass_path, style=subtitle_style)

        output_path = os.path.join(upload_folder, f"clip_{uuid.uuid4()}.mp4")

        clip_args.append((
            video_path, start, end, output_path, ass_path,
            method, out_w, out_h, x_offset, y_offset, zoom_factor,
            seg["score"], seg.get("breakdown", {}), duration,
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
    """Edita um clip existente com texto e efeito preto-e-branco."""
    import moviepy.editor as mp

    clip = mp.VideoFileClip(clip_path)
    txt_clip = mp.TextClip(text, fontsize=70, color="white").set_position("center").set_duration(clip.duration)
    edited_clip = mp.CompositeVideoClip([clip, txt_clip]).fx(mp.vfx.blackwhite)
    directory, filename = os.path.split(clip_path)
    edited_filename = filename.replace(".mp4", "_edited.mp4")
    edited_path = os.path.join(directory, edited_filename)
    edited_clip.write_videofile(edited_path, codec="libx264", audio_codec="aac", logger=None)
    clip.close()
    edited_clip.close()
    return edited_path
