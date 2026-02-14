# ViralClipMaker

ViralClipMaker is a web-based application designed to automatically generate short, "viral-style" video clips from longer videos. Users can provide a YouTube link or upload a local video file, and the application will process it to find potentially interesting segments, generate clips, and provide tools for basic editing.

## Features

- **Video Input**: Supports video processing from both YouTube URLs and direct file uploads.
- **Automatic Clip Generation**: Analyzes video duration to generate a set of shorter sub-clips.
- **Virality Score**: Assigns a simulated "virality probability" to each generated clip.
- **Video Previews**: Displays the generated clips in a modern, card-based layout with video players for instant preview.
- **Simple Editing**: Allows users to add a text caption to any generated clip.
- **Music Suggestions**: Provides viral music suggestions to accompany the clips.
- **Download**: Users can download the final edited or unedited clips.

## Setup and Installation

To get the project running locally, follow these steps:

1.  **Clone the Repository**
    ```bash
    git clone <your-repository-url>
    cd ViralClipMaker
    ```

2.  **Create and Activate a Virtual Environment**

    For macOS/Linux:
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

    For Windows:
    ```bash
    python -m venv venv
    .\venv\Scripts\activate
    ```

3.  **Install Dependencies**
    A aplicação é totalmente independente e portátil. Ela já inclui os binários necessários para o **ffmpeg** (via `imageio-ffmpeg`) e **Node.js** (via `nodejs-bin`), portanto você não precisa instalar nada no seu sistema operacional além do Python.

    Instale os pacotes Python:
    ```bash
    pip install -r requirements.txt
    ```

## How to Run

With your virtual environment activated and dependencies installed, you can start the Flask development server:

```bash
python3 app.py
```

Open your web browser and navigate to `http://127.0.0.1:5000` to use the application.