# ViralClipMaker — CLAUDE.md

> **Este arquivo é a memória viva do projeto.**
> Leia-o inteiro antes de qualquer ação. Atualize-o ao concluir tarefas ou tomar decisões de arquitetura.
> Não é documentação para humanos — é contexto operacional para o agente de IA.

---

## VISÃO DO PROJETO

Clone open source e 100% local do Opus Clip. Transforma vídeos longos em clips curtos virais (TikTok, Reels, Shorts) com legendas automáticas sincronizadas, reframe inteligente 9:16, seleção de segmentos por IA e camera tracking — tudo rodando na máquina do usuário, sem nuvem, sem custo, sem envio de dados.

**Diferencial central:** experiência "download and play". Quem tem Python instalado roda com `python run.py` e pronto. Binários de Node.js e FFmpeg vêm via pacotes Python (`nodejs-bin`, `imageio-ffmpeg`) — zero configuração extra.

**Público:** leigos (interface web simples, um botão) e profissionais/devs (CLI, configs avançadas, modo batch).

**Licença:** MIT — qualquer pessoa pode usar, modificar, distribuir.

**Filosofia de hardware:** Roda em máquinas modestas (8GB RAM, CPU integrada). Sem dependência de APIs pagas ou modelos de IA pesados. Acessível para criadores de conteúdo no Brasil e no mundo.

---

## ESTADO ATUAL DO CÓDIGO (AUDITADO E CORRIGIDO EM 21/09/2026)

### Validação E2E da recepção — 02/10/2026

- **E2E browser real (Chrome DevTools)** validado: upload de arquivo, URL do YouTube, SSE, resultados, reprodução dos clips, `.srt`/`.vtt` (com payload e fallback sidecar), `/edit` (P&B + legenda estática), `/download-all` (zip íntegro), `/history`.
- **CLI E2E validado** (`python -m viralclip` em vídeo local com fala).
- **FIX aplicado:** `yt-dlp` bump `2026.02.04` → `2026.8.19` — a pin antiga recebia **HTTP 403** do YouTube (anti-bot); com a nova versão o download funciona sem cookies.
- **FIX aplicado:** plural "1 clipes gerados" → ternário em `templates/index.html`.
- **Observações registradas (não corrigidas):** grupos de legenda com 7 palavras podem transbordar (`WrapStyle: 2` = sem quebra); favicon 404 no console; vídeo sem fala transcribe 0 segmentos (comportamento correto, já documentado).
- Erro `ERR_ALPN_NEGOTIATION_FAILED` no upload via browser ocorreu **apenas no browser sandbox do MCP** (File size 0, sem acesso ao disco) — não é defeito do app (curl E2E e blobs em memória funcionam).

### Arquivos e Funções Reais

| Arquivo | Função | Status |
|---|---|---|
| `app.py` | **Backend único FastAPI** — todas as rotas (`/process`, `/process-stream` SSE, `/edit`, `/batch/*`, `/history`, `/export-subtitles`, `/download-all`) | ✅ Upload em stream (sem RAM cheia), fallback sidecar correto |
| `video_processing.py` | Orquestra clips: word index (bisect) + `core/pipeline.py` + ProcessPoolExecutor. **Lê offsets/zoom por segmento** (crop auto funciona) | ✅ `/edit` sem MoviePy (FFmpeg puro: ASS estático + P&B) |
| `core/ffprobe.py` | Metadados lidos do header (`ffmpeg -i` sem decode) | ✅ Novo — elimina decode completo |
| `core/transcriber.py` | faster-whisper, word_timestamps, cache JSON, singleton, transcrição adaptativa >30min | ✅ Usa `ffprobe.probe_duration` |
| `core/clip_detector.py` | Score multi-fator + **NMS temporal** + fallback p/ vídeos curtos + **sentimento PT-BR por léxico** | ✅ Bugs da auditoria corrigidos |
| `core/pipeline.py` | FFmpeg unificado: 1 encode/clip + `parse_crop_position()` | ✅ |
| `core/video_editor.py` | Reframe 9:16 (crop/letterbox/blur), probe com cache via ffprobe | ✅ |
| `core/subtitle_renderer.py` | ASS word-by-word (4 estilos) + `generate_static_ass` p/ edição | ✅ Overflow de centésimos corrigido |
| `core/subtitle_export.py` | SRT/VTT com timestamps relativos + `extract_clip_segments` | ✅ Export correto por clip |
| `core/face_tracker.py` | MediaPipe face detection + `apply_auto_crop` | ✅ Integrado de ponta a ponta |
| `core/auto_zoom.py` | Zoom por energia de áudio + `boost_zoom_for_range` | ✅ Integrado (toggle UI / `--auto-zoom`) |
| `core/downloader.py` | yt-dlp wrapper + `resolve_video_source`; chama `patch_env_path()` | ✅ node no PATH garantido |
| `core/history.py` | Histórico JSON (load/append) | ✅ Novo — extraído do app |
| `viralclip/__main__.py` | CLI (`python -m viralclip`), importa só de `core/` e `video_processing` | ✅ Desacoplado do app |
| `run.py` | Launcher único — detecta `venv/`, `.venv/` e Windows; backend único uvicorn | ✅ Bugs da auditoria corrigidos |
| `viralclip.spec` | PyInstaller spec corrigido (scipy OK, ffmpeg/mediapipe embutidos via `collect_all`) | ⚠️ Corrigido estaticamente, build não verificado |
| `requirements.txt` | Só deps diretas e usadas | ✅ `spacy`, `moviepy`, `flask`, `waitress` removidos |
| `static/script.js` | Alpine.js, consome **SSE real** de `/process-stream` | ✅ Sem progresso fake |
| `templates/index.html` | Frontend Alpine.js + Tailwind via CDN + toggle auto-zoom | ✅ |

### Auditoria 21/09/2026 — resolução dos achados

**Críticos — TODOS CORRIGIDOS:**
1. ✅ Crop "Auto" descartado → `generate_clips` lê `seg["x_offset"]/["y_offset"]/["zoom_factor"]` por segmento.
2. ✅ Sem dedup → NMS temporal (`_select_top_n`, overlap máx. 0.5) em `detect_clips`.
3. ✅ Vídeo curto = 0 clips → `clip_duration = min(clip_duration, duration)`.
4. ✅ SRT/VTT absolutos → `extract_clip_segments` (relativo ao clip) + sidecar por clip em `outputs/`.
5. ✅ TextBlob PT-BR → léxico PT-BR próprio (TextBlob só p/ inglês).
6. ✅ `run.py` venv → aceita `venv/`, `.venv/`, `bin/python` e `Scripts/python.exe`.
7. ✅ `auto_zoom.py` morto → integrado ao pipeline (UI toggle + CLI flag).

**Médios — corrigidos:**
8. ✅ SSE consumido pelo frontend (`fetch` + `ReadableStream` em `_readSSE`).
9. ✅ Upload FastAPI em stream de 1MB (sem `await file.read()` inteiro).
10. ✅ Probes via header-only (`core/ffprobe.py`).
11. ✅ `patch_env_path()` chamado em `download_video()`.
12. ✅ `viralclip.spec`: scipy/scikit-learn mantidos; ffmpeg e mediapipe embutidos via `collect_all`.
13. ✅ **Backend único**: Flask removido; só existe `app.py` (FastAPI).

**Baixos — corrigidos ou aceitos:** `spacy` removido; timestamp overflow corrigido; fila batch podada (máx. 20 finalizados); CLI desacoplado; `debug=True` removido; `_safe_upload_path` com validação explícita; path traversal já era mitigado pelo routing.

---

## ARQUITETURA

### Stack

| Camada | Tecnologia | Motivo |
|---|---|---|
| Backend | **FastAPI + uvicorn (único)** | SSE nativo, async, streaming de upload |
| Transcrição | `faster-whisper` | 4x mais rápido que whisper padrão, word timestamps nativos |
| Download | `yt-dlp` | Mais robusto e atualizado |
| Edição de vídeo | `ffmpeg` via subprocess | 1 encode/clip, zero MoviePy |
| Face detection | `mediapipe` | Camera tracking, CPU 30+ FPS |
| NLP / score | TextBlob (EN) + léxico PT-BR + `librosa` | Sentimento real em PT-BR, energia RMS |
| Binários | `imageio-ffmpeg` + `nodejs-bin` | Portabilidade sem instalação global |
| Frontend | Alpine.js + Tailwind CSS (CDN) | Sem build step |

### Estrutura de Pastas

```
ViralClipMaker/
├── app.py                  # Backend FastAPI único (rotas + SSE + batch)
├── video_processing.py     # Orquestração de clips (paralelo, 1 encode/clip)
├── run.py                  # Launcher: venv, deps, modelo, servidor
├── requirements.txt        # Só deps diretas
├── musicas_virais.json
├── viralclip.spec          # PyInstaller (corrigido, não testado E2E)
│
├── core/
│   ├── runtime.py          # Plataforma, paths de binários, patch_env_path
│   ├── ffprobe.py          # Metadados via header (sem decode)
│   ├── downloader.py       # yt-dlp + resolve_video_source
│   ├── transcriber.py      # faster-whisper + adaptativa >30min
│   ├── clip_detector.py    # Score multi-fator + NMS temporal
│   ├── pipeline.py         # FFmpeg unificado + parse_crop_position
│   ├── video_editor.py     # Reframe 9:16 + probe_dimensions (cache)
│   ├── subtitle_renderer.py# ASS karaoke + ASS estático
│   ├── subtitle_export.py  # SRT/VTT relativo + extract_clip_segments
│   ├── face_tracker.py     # MediaPipe → x_offset/y_offset por segmento
│   ├── auto_zoom.py        # Momentos de energia → boost de zoom
│   └── history.py          # Histórico JSON local
│
├── viralclip/__main__.py   # CLI
├── static/  templates/     # Frontend (Alpine + Tailwind)
├── models/  uploads/  outputs/
```

### Pipeline de Processamento (atual)

```
[Input: URL YouTube ou arquivo local (upload em stream)]
    → 1. DOWNLOAD/IMPORT     (yt-dlp / chunks de 1MB)
    → 2. TRANSCRIÇÃO         (faster-whisper, word timestamps; seletiva >30min)
    → 3. SCORE DE VIRALIDADE (sentimento EN/PT, energia RMS, hooks, densidade)
    → 4. SELEÇÃO             (top N por score + NMS: sem janelas sobrepostas)
    → 5. CROP/AUTO           (face detection por segmento, se crop=auto)
    → 6. AUTO ZOOM           (boost 1.3x em picos de energia, opcional)
    → 7. LEGENDAS            (word-by-word ASS, 4 estilos)
    → 8. EXPORT              (FFmpeg único por clip: crop+scale+ass, H.264)
```

---

## DECISÕES DE ARQUITETURA

- **Backend único FastAPI** (desde 21/09/2026): antes havia Flask (`app.py`) + FastAPI (`app_fastapi.py`) com ~90% de duplicação e divergências. Flask e waitress removidos.
- **faster-whisper** em vez de whisper padrão: `word_timestamps=True` nativo, 4x mais rápido, INT8 roda em CPU.
- **MediaPipe** em vez de dlib/insightface: MIT license, CPU a 30fps.
- **Léxico PT-BR próprio para sentimento**: TextBlob retorna polaridade 0 para português. Léxico embutido em `clip_detector.py` (~100 palavras), zero deps, 100% offline. TextBlob permanece apenas para inglês.
- **Parâmetros por segmento em `generate_clips`**: `seg["x_offset"]`, `seg["y_offset"]`, `seg["zoom_factor"]` têm precedência sobre os globais. É assim que face tracking e auto-zoom chegam ao FFmpeg.
- **SSE com fallback JSON**: rotas retornam `{"error": ...}` em falhas; o frontend detecta event-stream vs JSON pelo content-type.
- **Modelos Whisper em `models/`**: download automático na 1ª execução (`tiny` padrão).
- **Binários via pacotes Python** (`imageio-ffmpeg`, `nodejs-bin`): alternativa à pasta `/bin/` estática, que nunca foi criada. `runtime.py` ainda prefere `/bin/` se existir.
- **Transcrição adaptativa**: vídeos > 30min usam transcrição seletiva (top 50% por energia RMS).
- **Sem MoviePy/ImageMagick**: `/edit` usa FFmpeg (ASS estático + `hue=s=0`).

---

## ROADMAP — FASES E TAREFAS

> Status: `[ ]` = pendente | `[x]` = concluído | `[~]` = parcial

### FASE 1 — Fundação & "Download and Play" ✅
- [x] `run.py` launcher (venv auto-detect: `venv/`, `.venv/`, Windows) ✅ corrigido 21/09
- [x] `core/runtime.py` + fallbacks `imageio-ffmpeg`/`nodejs-bin`
- [x] requirements limpos (deps mortas removidas)
- [ ] `/bin/` com binários estáticos FFmpeg/Node (opcional — fallback via pip já funciona)

### FASE 2 — Transcrição & Score Real ✅
- [x] `core/downloader.py`, `core/transcriber.py`, `core/clip_detector.py`
- [x] Score multi-fator com breakdown na UI; modelo Whisper selecionável
- [x] Sentimento PT-BR via léxico (21/09)

### FASE 3 — Formato TikTok & Legendas ✅
- [x] Reframe 9:16 (crop/letterbox/blur), ASS word-by-word, 4 estilos
- [x] Presets de duração e resolução
- [x] Camera tracking (MediaPipe) — **de ponta a ponta desde 21/09** (antes o resultado era descartado)

### FASE 3.5 — Performance & Pipeline Unificado ✅
- [x] 1 encode/clip (`core/pipeline.py`), ProcessPoolExecutor, singleton Whisper, transcrição seletiva, áudio via pipe

### FASE 3.6 — Crop Editável & Presets ✅
- [x] Crop por posição/zoom editável na UI, presets de duração

### FASE 4 — UX & Polimento ✅ (quase)
- [x] UI Alpine.js + Tailwind, dark/light, drag & drop
- [x] Backend único FastAPI
- [x] **Progresso real via SSE consumido pelo frontend** (21/09 — antes era simulado)
- [x] Modo Simples/Avançado, download .zip, cleanup de uploads, histórico
- [ ] Editor de timeline manual

### FASE 5 — Features Avançadas
- [x] Modo batch: backend completo (`/batch/add|status|process`), com parâmetros do usuário (21/09). **Sem UI no frontend** (API only)
- [x] Export `.srt`/`.vtt` por clip com timestamps relativos (corrigido 21/09)
- [x] Zoom automático integrado ao pipeline (21/09 — era código morto)
- [x] CLI funcional e desacoplado do backend web
- [~] Instalador via PyInstaller: spec corrigido (scipy OK, ffmpeg/mediapipe embutidos), **build não verificado E2E**

---

## CONVENÇÕES DO PROJETO

### Python
- Python 3.10+; type hints em funções públicas dos módulos `core/`
- Docstrings em inglês; comentários de lógica podem ser PT
- Nenhum módulo `core/` importa de `app.py`/frontend — dependência unidirecional
- Logging via `logging`; `print()` só em `run.py`/CLI

### Commits
- Prefixo por fase: `[F1]`, `[F2]`, etc.

### FFmpeg
- Sempre via `core/runtime.get_ffmpeg_path()` — nunca assumir `ffmpeg` no PATH
- subprocess com lista (nunca string concatenada)

### Frontend
- Alpine.js + Tailwind via CDN; sem build step; dark/light via `prefers-color-scheme`
- Progresso real via SSE — nunca progresso simulado

---

## COMPARATIVO COM OPUS CLIP

| Feature | Opus Clip | ViralClipMaker |
|---|---|---|
| Preço | US$19–49/mês | Gratuito |
| Funciona offline | ❌ Cloud | ✅ 100% local |
| Privacidade | ❌ Upload | ✅ Dados ficam na máquina |
| Legenda word-by-word | ✅ | ✅ |
| Reframe 9:16 | ✅ | ✅ |
| Detecção de momentos | ✅ | ✅ (áudio + NLP local, sem overlap) |
| Camera tracking | ✅ | ✅ |
| Crop editável | ✅ | ✅ |
| Zoom automático | ✅ | ✅ (por energia) |
| Open Source | ❌ | ✅ MIT |
| Hardware | Alto (cloud) | Baixo (CPU local) |

---

## NOTAS E GOTCHAS

- **ASS paths com caracteres especiais** (`:`, `\`): Linux OK; Windows precisa de escaping — não testado.
- **MediaPipe em macOS/ARM** pode exigir Rosetta.
- **Transcrição seletiva (>30min)** transcreve só top 50% por energia — regiões fracas ficam sem legendas no SRT.
- **ProcessPoolExecutor** no Windows exige `if __name__ == "__main__"` — preservado em `run.py`.
- **PyInstaller spec** corrigido estaticamente (21/09); o build real nunca foi executado — validar antes de distribuir.
- **Vídeo sem fala**: clips saem sem legendas e `/export-subtitles` retorna 404 (segmentos vazios) — comportamento correto.

---

*Última atualização: 02/10/2026 — Recepção por nova equipe: auditoria de 21/09 commitada, validação E2E completa (browser + CLI + YouTube), yt-dlp atualizado para 2026.8.19 (corrige 403 do YouTube), fix de plural na UI. Release v1.0.0 em main. Atualização anterior (21/09): backend único FastAPI, 7 bugs críticos corrigidos (crop auto, NMS, vídeos curtos, SRT relativo, sentimento PT-BR, venv detection, auto-zoom), SSE real no frontend, upload em stream, probes sem decode, deps limpas (sem spacy/moviepy/flask).*
