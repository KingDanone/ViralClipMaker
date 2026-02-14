import os
import cv2
import moviepy.editor as mp
import yt_dlp
import random
import uuid
import nodejs
import imageio_ffmpeg

def download_youtube_video(url, upload_folder):
    filename_template = os.path.join(upload_folder, f"{uuid.uuid4()}.mp4")
    
    # Adiciona o binário do nodejs-bin ao PATH para o yt-dlp usar como runtime JS
    node_bin_dir = os.path.dirname(nodejs.node.path)
    if node_bin_dir not in os.environ['PATH']:
        os.environ['PATH'] = node_bin_dir + os.pathsep + os.environ['PATH']

    # Localiza o binário do ffmpeg que já vem no requirements (imageio-ffmpeg)
    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()

    ydl_opts = {
        # Tenta baixar o melhor vídeo com áudio em formato mp4, limitando a 1080p
        'format': 'bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': filename_template,
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'merge_output_format': 'mp4',
        'ffmpeg_location': ffmpeg_path, # Usa o ffmpeg portátil
        'js_runtimes': {'node': {}},
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            ydl.download([url])
        except Exception as e:
            raise RuntimeError(f"Falha no download do yt-dlp: {str(e)}")
        
    if not os.path.exists(filename_template) or os.path.getsize(filename_template) == 0:
        if os.path.exists(filename_template):
            os.remove(filename_template)
        raise RuntimeError("O download resultou em um arquivo vazio ou inexistente. Verifique a URL ou o suporte a JavaScript (dukpy).")
        
    return filename_template

def analyze_video_for_cuts(video_path, num_cuts=5):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video file: {video_path}")
        
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps
    
    cuts = []
    if duration > 0:
        for i in range(num_cuts):
            start_time = random.uniform(0, max(0, duration - 30))
            end_time = start_time + 30
            cuts.append((start_time, end_time))
    
    cap.release()
    return cuts

def classify_viral_probability(cut_duration, has_faces=False, has_movement=False):
    base_prob = 50
    if 15 <= cut_duration <= 45:
        base_prob += 20
    if has_faces:
        base_prob += 15
    if has_movement:
        base_prob += 15
    return min(base_prob, 100)

def generate_clips(video_path, cuts, upload_folder):
    clips = []
    video = mp.VideoFileClip(video_path)
    for i, (start, end) in enumerate(cuts):
        clip = video.subclip(start, end)
        clip_path = os.path.join(upload_folder, f'clip_{uuid.uuid4()}.mp4')
        clip.write_videofile(clip_path, codec='libx264', audio_codec='aac', logger=None)
        duration = end - start
        has_faces = random.choice([True, False])  # Simulação
        has_movement = random.choice([True, False])
        prob = classify_viral_probability(duration, has_faces, has_movement)
        clips.append({'path': clip_path, 'prob': prob, 'duration': duration})
    video.close()
    return clips

def add_captions_and_edit(clip_path):
    clip = mp.VideoFileClip(clip_path)
    # Placeholder text, can be passed as an argument
    text = "Texto viral!"
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
