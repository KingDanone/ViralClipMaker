# ViralClipMaker

Open-source, 100% local alternative to Opus Clip.
Transforms long videos into short viral clips (TikTok, Reels, Shorts) with captions, reframe, and virality scoring — all running on your machine, no cloud, no data upload.

## Features

- **Input**: YouTube URL or local video file upload
- **AI Transcription**: faster-whisper with word-level timestamps
- **Virality Score**: Multi-factor analysis (sentiment, audio energy, viral hooks, speech density)
- **Smart Clipping**: Sliding window detection, top N segments by score
- **9:16 Reframe**: Crop, letterbox, or blur padding for TikTok/Reels format
- **Animated Captions**: Word-by-word karaoke subtitles (4 styles: TikTok, Bold, Neon, Minimal)
- **Camera Tracking**: Auto-detect faces and follow them (MediaPipe)
- **Crop Control**: Choose position (left/center/right/auto) and zoom (1.0x-2.0x)
- **Resolution Presets**: TikTok 1080×1920, Reels 1080×1920, 720×1280
- **Duration Presets**: 15s, 30s, 60s, 90s clips
- **Export Subtitles**: Download .srt or .vtt files
- **Batch Download**: Download all clips as .zip
- **CLI**: Command-line interface for automation
- **Dark/Light Mode**: Automatic based on system preference
- **Project History**: Saves last 50 projects locally

## Requirements

- Python **3.10+**
- ~75 MB free disk for Whisper model (auto-downloaded on first run)
- 8GB RAM recommended

No system-wide FFmpeg or Node.js installation required.

## Quick Start

```bash
git clone https://github.com/your-username/ViralClipMaker.git
cd ViralClipMaker
python run.py
```

The browser will open at `http://localhost:5000` automatically.

### `run.py` options

| Flag | Description |
|---|---|
| `--no-browser` | Don't open the browser automatically |
| `--port PORT` | Server port (default: 5000) |
| `--whisper-model {tiny,base,small}` | Whisper model size (default: tiny) |

## CLI Usage

```bash
# Basic usage
python -m viralclip video.mp4

# With options
python -m viralclip video.mp4 --clips 5 --duration 30 --model small

# From YouTube
python -m viralclip https://youtube.com/watch?v=... --output ./clips/

# Custom resolution
python -m viralclip video.mp4 --resolution 720x1280 --crop left --zoom 1.5
```

### CLI Options

| Flag | Description | Default |
|---|---|---|
| `--clips, -n` | Number of clips to generate | 5 |
| `--duration, -d` | Clip duration (15, 30, 60, 90) | 30 |
| `--model, -m` | Whisper model (tiny, base, small) | tiny |
| `--style, -s` | Subtitle style | tiktok |
| `--crop` | Crop position (left, center, right, auto) | center |
| `--zoom` | Zoom factor (1.0-2.0) | 1.0 |
| `--resolution` | Output resolution WxH | 1080x1920 |
| `--output, -o` | Output directory | output/ |

## How It Works

```
[Input: YouTube URL or local file]
    → 1. DOWNLOAD       (yt-dlp / upload)
    → 2. TRANSCRIBE     (faster-whisper, word timestamps)
    → 3. SCORE          (sentiment + energy + hooks + density)
    → 4. SELECT         (top N segments by score)
    → 5. REFRAME        (9:16 crop/scale)
    → 6. CAPTIONS       (word-by-word ASS overlay)
    → 7. EXPORT         (H.264, configurable resolution)
```

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Flask (Python) |
| Transcription | faster-whisper |
| Audio Analysis | librosa + FFmpeg |
| NLP Scoring | TextBlob |
| Face Detection | MediaPipe |
| Video Processing | FFmpeg |
| Frontend | Alpine.js + Tailwind CSS |

## Project Structure

```
ViralClipMaker/
├── app.py                  # Flask server, routes
├── video_processing.py     # Pipeline orchestration
├── run.py                  # Single entry point
├── requirements.txt
├── musicas_virais.json     # Music track list
│
├── core/
│   ├── runtime.py          # Platform detection, binary paths
│   ├── transcriber.py      # faster-whisper + adaptive transcription
│   ├── clip_detector.py    # Multi-factor virality scoring
│   ├── video_editor.py     # 9:16 reframe (crop/letterbox/blur)
│   ├── subtitle_renderer.py # Word-by-word ASS subtitles
│   ├── subtitle_export.py  # SRT/VTT export
│   ├── pipeline.py         # Unified FFmpeg pipeline
│   ├── face_tracker.py     # MediaPipe face detection
│   ├── auto_zoom.py        # Audio energy-based zoom
│   └── downloader.py       # yt-dlp wrapper
│
├── viralclip/
│   └── __main__.py         # CLI entry point
│
├── static/                 # Frontend assets
├── templates/              # HTML templates
├── models/                 # Whisper models (auto-downloaded)
├── uploads/                # Temp uploads and clips
└── outputs/                # Transcription cache
```

## UI Modes

- **Simple Mode**: Just upload + generate button
- **Advanced Mode**: Access to all settings (model, duration, crop, zoom, style, resolution)

## Troubleshooting

### YouTube Downloads

If downloads fail with "Sign in to confirm you're not a bot", try:

1. Install "Get cookies.txt LOCALLY" browser extension
2. Go to youtube.com and log in
3. Export cookies to `youtube_cookies.txt` in project root

### Whisper Model Download

First run downloads the model automatically (~75MB for tiny). Subsequent runs use the cached model.

### Performance

- **Tiny model**: ~30s for 10min video (fast, less accurate)
- **Small model**: ~2-5min for 10min video (slower, more accurate)
- **Parallel clips**: Up to 2 clips processed simultaneously
- **Pipeline**: Single FFmpeg encode per clip (3x faster than naive approach)

## License

MIT — see [LICENSE](LICENSE).
