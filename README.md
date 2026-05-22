# ViralClipMaker

Open-source, 100% local alternative to Opus Clip.  
Transforms long videos into short viral clips (TikTok, Reels, Shorts) with captions, reframe, and virality scoring — all running on your machine, no cloud, no data upload.

## Features

- **Input**: YouTube URL or local video file upload
- **Automatic clipping**: Splits long videos into short segments
- **Virality score**: Rates each clip based on duration and simulated face/movement detection
- **Preview**: HTML5 video players for each generated clip
- **Simple editing**: Add centered text captions + black-and-white filter
- **Music suggestions**: Random picks from a curated viral tracks list
- **Download**: Individual clip download (original or edited)

## Requirements

- Python **3.10+**
- ~75 MB free disk for the Whisper model (auto-downloaded on first run)

No system-wide FFmpeg or Node.js installation required. Both are bundled via Python packages (`imageio-ffmpeg`, `nodejs-bin`).

## Quick Start

```bash
git clone https://github.com/your-username/ViralClipMaker.git
cd ViralClipMaker
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python run.py
```

The browser will open at `http://localhost:5000` automatically.

### `run.py` options

| Flag | Description |
|---|---|
| `--no-browser` | Don't open the browser automatically |
| `--port PORT` | Server port (default: 5000) |
| `--whisper-model {tiny,base,small,medium,large-v2,large-v3}` | Whisper model size (default: tiny) |

## Project Status

ViralClipMaker is in **active development** (Phase 1 — Foundation).

### What works
- YouTube download via `yt-dlp` with bundled Node.js runtime
- Local file upload
- Video splitting into 5 segments
- Clip preview and download
- Basic caption editing (static text, black-and-white filter)
- Music suggestion
- Cross-platform portability (Windows, macOS, Linux)

### What's coming
- **Phase 2**: Real transcription (faster-whisper), actual virality scoring (NLP + audio energy)
- **Phase 3**: TikTok 9:16 reframe, word-by-word animated captions, face tracking
- **Phase 4**: Real-time progress via SSE, project history
- **Phase 5**: Advanced features (batch mode, CLI, Ollama integration)

## Project Structure

```
ViralClipMaker/
├── app.py                 # Flask server, routes
├── video_processing.py    # Download, clip analysis, editing
├── core/
│   ├── __init__.py
│   └── runtime.py         # Platform detection, binary resolution
├── run.py                 # Single entry point launcher
├── requirements.txt
├── musicas_virais.json    # Music track list
├── static/                # Frontend assets (CSS, JS)
├── templates/             # HTML templates
├── models/                # Whisper models (auto-downloaded)
├── uploads/               # Temp uploads and generated clips
└── outputs/               # Future: exported clips
```

## License

MIT — see [LICENSE](LICENSE).
