import os
import moviepy.editor as mp
import uuid
import logging

logger = logging.getLogger(__name__)


def generate_clips(video_path, segments, upload_folder):
    clips = []
    video = mp.VideoFileClip(video_path)
    for i, seg in enumerate(segments):
        start = seg["start"]
        end = seg["end"]
        clip = video.subclip(start, end)
        clip_path = os.path.join(upload_folder, f'clip_{uuid.uuid4()}.mp4')
        clip.write_videofile(clip_path, codec='libx264', audio_codec='aac', logger=None)
        clips.append({
            'path': clip_path,
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
    
    # Create a new path for the edited clip
    directory, filename = os.path.split(clip_path)
    edited_filename = filename.replace('.mp4', '_edited.mp4')
    edited_path = os.path.join(directory, edited_filename)

    edited_clip.write_videofile(edited_path, codec='libx264', audio_codec='aac', logger=None)
    
    clip.close()
    edited_clip.close()
    
    return edited_path
