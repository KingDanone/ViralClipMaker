# ViralClipMaker

Open-source, 100% local alternative to Opus Clip.
Transforms long videos into short viral clips (TikTok, Reels, Shorts) with captions, reframe, and virality scoring — all running on your machine, no cloud, no data upload.

## Features

- **Input**: YouTube URL or local video file upload
- **AI Transcription**: faster-whisper with word-level timestamps (adaptive for >30min videos)
- **Virality Score**: Multi-factor analysis (sentiment PT-BR/EN, audio energy, viral hooks, speech density) with overlap suppression — every clip is a distinct moment
- **9:16 Reframe**: Crop, letterbox, or blur padding for TikTok/Reels format
- **Animated Captions**: Word-by-word karaoke subtitles (4 styles: TikTok, Bold, Neon, Minimal)
- **Camera Tracking**: Auto-detect faces and follow them (MediaPipe)
- **Crop Control**: Position (left/center/right/auto) and zoom (1.0x–2.0x)
- **Auto Zoom**: Automatic zoom boost on high-energy moments (optional)
- **Real-time Progress**: Server-Sent Events — no fake progress bars
- **Export Subtitles**: Download .srt or .vtt per clip (relative timestamps)
- **Batch Download**: Download all clips as .zip
- **CLI**: Command-line interface for automation
- **Dark/Light Mode**: Automatic based on system preference
- **Project History**: Last 50 projects saved locally

## Requirements

- Python **3.10+**
- ~75 MB free disk for the Whisper model (auto-downloaded on first run)
- 8GB RAM recommended

No system-wide FFmpeg or Node.js installation required.

## Quick Start

```bash
git clone https://github.com/your-username/ViralClipMaker.git
cd ViralClipMaker
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

The browser will open at `http://localhost:5000` automatically.
If a `venv/` or `.venv/` exists in the project, `run.py` re-executes inside it automatically.

### `run.py` options

| Flag | Description |
|---|---|
| `--no-browser` | Don't open the browser automatically |
| `--port PORT` | Server port (default: 5000) |
| `--whisper-model {tiny,base,small,...}` | Whisper model size (default: tiny) |

## CLI Usage

```bash
# Basic usage
python -m viralclip video.mp4

# With options
python -m viralclip video.mp4 --clips 5 --duration 30 --model small

# From YouTube
python -m viralclip https://youtube.com/watch?v=... --output ./clips/

# Custom resolution, crop, auto zoom
python -m viralclip video.mp4 --resolution 720x1280 --crop left --auto-zoom
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
| `--auto-zoom` | Zoom boost on high-energy moments | off |
| `--resolution` | Output resolution WxH | 1080x1920 |
| `--output, -o` | Output directory | output/ |

## How It Works

```
[Input: YouTube URL or local file]
    → 1. DOWNLOAD       (yt-dlp / streaming upload)
    → 2. TRANSCRIBE     (faster-whisper, word timestamps)
    → 3. SCORE          (sentiment + energy + hooks + density)
    → 4. SELECT         (top N segments, temporal NMS — no duplicates)
    → 5. REFRAME        (9:16 crop, face tracking optional)
    → 6. CAPTIONS       (word-by-word ASS overlay)
    → 7. EXPORT         (H.264, 1 FFmpeg encode per clip)
```

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI + uvicorn (SSE for real-time progress) |
| Transcription | faster-whisper |
| Audio Analysis | librosa + FFmpeg |
| Sentiment | TextBlob (EN) + built-in PT-BR lexicon |
| Face Detection | MediaPipe |
| Video Processing | FFmpeg (single encode per clip) |
| Frontend | Alpine.js + Tailwind CSS |

## Project Structure

```
ViralClipMaker/
├── app.py                  # FastAPI backend (single server, SSE)
├── video_processing.py     # Clip orchestration (parallel FFmpeg)
├── run.py                  # Single entry point
├── requirements.txt
├── musicas_virais.json     # Music track list
├── viralclip.spec          # PyInstaller build spec
│
├── core/
│   ├── runtime.py          # Platform detection, binary paths
│   ├── ffprobe.py          # Fast header-only video metadata
│   ├── downloader.py       # yt-dlp wrapper
│   ├── transcriber.py      # faster-whisper + adaptive transcription
│   ├── clip_detector.py    # Multi-factor scoring + NMS dedup
│   ├── pipeline.py         # Unified FFmpeg pipeline (1 encode/clip)
│   ├── video_editor.py     # 9:16 reframe (crop/letterbox/blur)
│   ├── subtitle_renderer.py# Word-by-word ASS subtitles
│   ├── subtitle_export.py  # SRT/VTT export (clip-relative timestamps)
│   ├── face_tracker.py     # MediaPipe face → auto crop
│   ├── auto_zoom.py        # Audio energy-based zoom boost
│   └── history.py          # Local project history
│
├── viralclip/
│   └── __main__.py         # CLI entry point
│
├── static/                 # Frontend assets (Alpine.js)
├── templates/              # HTML templates
├── models/                 # Whisper models (auto-downloaded)
├── uploads/                # Temp uploads and clips
└── outputs/                # Transcription cache
```

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
