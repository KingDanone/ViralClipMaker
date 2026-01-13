from flask import Flask, render_template, request, send_file, jsonify, send_from_directory
import os
import json
import uuid
import random
from video_processing import (
    download_youtube_video,
    analyze_video_for_cuts,
    generate_clips,
    add_captions_and_edit
)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads/'

# Carrega a lista de músicas virais do arquivo JSON
try:
    with open('musicas_virais.json', 'r', encoding='utf-8') as f:
        viral_tracks = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    viral_tracks = [
        "Música Padrão 1 - Artista Genérico",
        "Música Padrão 2 - Artista Genérico"
    ]

def suggest_music(theme=None):
    """Sugere uma música da lista de faixas virais carregada do JSON."""
    return random.choice(viral_tracks)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process():
    input_type = request.form.get('input_type')
    video_path = None
    
    if input_type == 'url':
        url = request.form.get('url')
        try:
            video_path = download_youtube_video(url, app.config['UPLOAD_FOLDER'])
        except Exception as e:
            print(f"Erro ao baixar vídeo do YouTube: {e}")
            return jsonify({'error': 'Erro ao baixar o vídeo do YouTube. A URL pode ser inválida ou o vídeo pode ter restrições.'})
    elif input_type == 'file':
        file = request.files['file']
        if file and file.filename:
            filename = f"{uuid.uuid4()}.mp4"
            video_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(video_path)
        else:
            return jsonify({'error': 'Nenhum arquivo selecionado para upload.'})

    if not video_path or not os.path.exists(video_path):
        return jsonify({'error': 'Vídeo inválido ou erro no download.'})
    
    try:
        cuts = analyze_video_for_cuts(video_path)
        clips = generate_clips(video_path, cuts, app.config['UPLOAD_FOLDER'])
    except Exception as e:
        print(f"Erro ao processar vídeo: {e}")
        # Limpar vídeo original em caso de falha no processamento
        if os.path.exists(video_path):
            os.remove(video_path)
        return jsonify({'error': 'Erro ao processar o vídeo. O arquivo pode estar corrompido.'})

    # Limpar vídeo original
    if os.path.exists(video_path):
        os.remove(video_path)
    
    return jsonify({'clips': clips})

@app.route('/edit', methods=['POST'])
def edit():
    clip_path = request.form.get('clip_path')
    text = request.form.get('text', 'Texto viral!')
    
    if not clip_path or not os.path.exists(clip_path):
        return jsonify({'error': 'O clipe original não foi encontrado.'})

    try:
        edited_path = add_captions_and_edit(clip_path, text)
    except Exception as e:
        print(f"Erro ao editar vídeo: {e}")
        return jsonify({'error': 'Erro ao aplicar a edição no clipe.'})

    # Opcional: remover o clipe não editado após a edição
    # if os.path.exists(clip_path):
    #     os.remove(clip_path)

    return jsonify({'edited_path': edited_path})

@app.route('/suggest_music', methods=['POST'])
def suggest_music_route():
    theme = request.form.get('theme')
    music = suggest_music(theme)
    return jsonify({'music': music})

@app.route('/uploads/<path:filename>')
def serve_clip(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/download/<path:filename>')
def download(filename):
    return send_file(os.path.join(app.config['UPLOAD_FOLDER'], filename), as_attachment=True)

if __name__ == '__main__':
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    app.run(debug=True)
