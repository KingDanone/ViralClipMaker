"""
ViralClipMaker CLI — Processamento de vídeos via linha de comando.

Uso:
    python -m viralclip video.mp4
    python -m viralclip video.mp4 --clips 5 --duration 30
    python -m viralclip https://youtube.com/watch?v=... --output ./clips/
"""

import argparse
import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        prog="viralclip",
        description="ViralClipMaker — Transforme vídeos em clips virais",
    )
    parser.add_argument(
        "video",
        help="Caminho do vídeo local ou URL do YouTube",
    )
    parser.add_argument(
        "--clips", "-n",
        type=int,
        default=5,
        help="Número de clips a gerar (padrão: 5)",
    )
    parser.add_argument(
        "--duration", "-d",
        type=int,
        default=30,
        choices=[15, 30, 60, 90],
        help="Duração de cada clip em segundos (padrão: 30)",
    )
    parser.add_argument(
        "--model", "-m",
        default="tiny",
        choices=["tiny", "base", "small"],
        help="Modelo Whisper para transcrição (padrão: tiny)",
    )
    parser.add_argument(
        "--style", "-s",
        default="tiktok",
        choices=["tiktok", "bold_shadow", "neon", "minimal"],
        help="Estilo da legenda (padrão: tiktok)",
    )
    parser.add_argument(
        "--crop",
        default="center",
        choices=["left", "center", "right", "auto"],
        help="Posição do crop (padrão: center)",
    )
    parser.add_argument(
        "--zoom",
        type=float,
        default=1.0,
        help="Fator de zoom (1.0 a 2.0, padrão: 1.0)",
    )
    parser.add_argument(
        "--resolution",
        default="1080x1920",
        help="Resolução de saída WxH (padrão: 1080x1920)",
    )
    parser.add_argument(
        "--output", "-o",
        default="output",
        help="Diretório de saída (padrão: output/)",
    )

    args = parser.parse_args()

    try:
        w, h = map(int, args.resolution.split("x"))
    except ValueError:
        parser.error("Resolução inválida. Use WxH, ex: 1080x1920")

    os.makedirs(args.output, exist_ok=True)

    video_path = _resolve_video(args.video, args.output)

    logger.info("Processando: %s", video_path)
    logger.info("Config: %d clips, %ds, modelo=%s, crop=%s, zoom=%.1f",
                args.clips, args.duration, args.model, args.crop, args.zoom)

    from core.transcriber import transcribe
    from core.clip_detector import detect_clips
    from video_processing import generate_clips
    from app import _parse_crop_position

    logger.info("Transcrevendo...")
    transcription = transcribe(video_path, model_size=args.model)

    logger.info("Analisando momentos...")
    segments = detect_clips(
        transcription, video_path,
        num_clips=args.clips,
        clip_duration=args.duration,
    )

    crop_params = _parse_crop_position(args.crop, args.zoom)
    crop_params.pop("auto_crop", None)

    logger.info("Gerando %d clips...", len(segments))
    clips = generate_clips(
        video_path, segments, args.output,
        transcription=transcription,
        subtitle_style=args.style,
        out_w=w, out_h=h,
        **crop_params,
    )

    logger.info("")
    logger.info("✅ %d clips gerados em %s/", len(clips), args.output)
    for i, clip in enumerate(clips, 1):
        fname = os.path.basename(clip["path"])
        logger.info("  %d. %s (%ds, score: %d%%)", i, fname, clip["duration"], clip["prob"])


def _resolve_video(video_arg: str, output_dir: str) -> str:
    """Resolve o vídeo de entrada (local ou URL)."""
    if os.path.isfile(video_arg):
        return video_arg

    if video_arg.startswith(("http://", "https://")):
        logger.info("Baixando vídeo do YouTube...")
        from core.downloader import download_video
        return download_video(video_arg, output_dir)

    logger.error("Arquivo não encontrado: %s", video_arg)
    sys.exit(1)


if __name__ == "__main__":
    main()
