import os
import moviepy.editor as mp
import uuid
import logging

from core.video_editor import reframe_9_16
from core.subtitle_renderer import add_word_captions

logger = logging.getLogger(__name__)


def _words_in_range(transcription: dict, start: float, end: float) -> list[dict]:
    words = []
    for seg in transcription.get("segments", []):
        for w in seg.get("words", []):
            if w["start"] >= start and w["end"] <= end:
                words.append(w)
    return words


def generate_clips(video_path, segments, upload_folder, transcription=None, subtitle_style="tiktok"):
    clips = []
    video = mp.VideoFileClip(video_path)

    for i, seg in enumerate(segments):
        start = seg["start"]
        end = seg["end"]

        raw_path = os.path.join(upload_folder, f'raw_{uuid.uuid4()}.mp4')
        subclip = video.subclip(start, end)
        subclip.write_videofile(raw_path, codec='libx264', audio_codec='aac', logger=None)

        reframed_path = reframe_9_16(raw_path, raw_path.replace(".mp4", "_reframed.mp4"))
        os.remove(raw_path)

        words = _words_in_range(transcription, start, end) if transcription else []
        shifted = [
            {"word": w["word"], "start": w["start"] - start, "end": w["end"] - start}
            for w in words
        ]

        final_path = os.path.join(upload_folder, f'clip_{uuid.uuid4()}.mp4')
        add_word_captions(reframed_path, final_path, shifted, style=subtitle_style)
        os.remove(reframed_path)

        clips.append({
            'path': final_path,
            'prob': seg["score"],
            'duration': round(end - start, 1),
            'breakdown': seg.get("breakdown", {}),
        })

    video.close()
    return clips


def add_captions_and_edit(clip_path, text="Texto viral!"):
    clip = mp.VideoFileClip(clip_path)
    txt_clip = mp.TextClip(text, fontsize=70, color='white').set_position('center').set_duration(clip.duration)
    edited_clip = mp.CompositeVideoClip([clip, txt_clip]).fx(mp.vfx.blackwhite)
    directory, filename = os.path.split(clip_path)
    edited_filename = filename.replace('.mp4', '_edited.mp4')
    edited_path = os.path.join(directory, edited_filename)
    edited_clip.write_videofile(edited_path, codec='libx264', audio_codec='aac', logger=None)
    clip.close()
    edited_clip.close()
    return edited_path
