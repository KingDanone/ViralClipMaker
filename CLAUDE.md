# ViralClipMaker — CLAUDE.md

> **Este arquivo é a memória viva do projeto.**
> Leia-o inteiro antes de qualquer ação. Atualize-o ao concluir tarefas ou tomar decisões de arquitetura.
> Não é documentação para humanos — é contexto operacional para o agente de IA.

---

## VISÃO DO PROJETO

Clone open source e 100% local do Opus Clip. Transforma vídeos longos em clips curtos virais (TikTok, Reels, Shorts) com legendas automáticas sincronizadas, reframe inteligente 9:16, seleção de segmentos por IA e camera tracking — tudo rodando na máquina do usuário, sem nuvem, sem custo, sem envio de dados.

**Diferencial central:** experiência "download and play". Quem tem Python instalado roda com `python run.py` e pronto. Binários de Node.js e FFmpeg são embutidos no repositório — zero configuração extra.

**Público:** leigos (interface web simples, um botão) e profissionais/devs (CLI, configs avançadas, modo batch).

**Licença:** MIT — qualquer pessoa pode usar, modificar, distribuir.

**Filosofia de hardware:** Roda em máquinas modestas (8GB RAM, CPU integrada). Sem dependência de APIs pagas ou modelos de IA pesados. Acessível para criadores de conteúdo no Brasil e no mundo.

---

## ESTADO ATUAL DO CÓDIGO (AUDITADO EM 19/06/2026)

### Arquivos e Funções Reais

| Arquivo | Função | Status |
|---|---|---|
| `app.py` | Servidor Flask, rotas: `/`, `/process`, `/edit`, `/suggest_music` | ✅ Funcional, integrado com core/ |
| `video_processing.py` | Pipeline de clips: corte → reframe → legendas | ✅ Funcional com MoviePy (gargalo de performance) |
| `core/transcriber.py` | faster-whisper, word_timestamps, cache JSON | ✅ Funcional |
| `core/clip_detector.py` | Score multi-fator (sentimento, energy, hooks, density) | ✅ Funcional |
| `core/video_editor.py` | Reframe 9:16 (crop, letterbox, blur) | ✅ Funcional |
| `core/subtitle_renderer.py` | Legendas word-by-word ASS, 4 estilos | ✅ Funcional |
| `core/downloader.py` | yt-dlp wrapper | ✅ Funcional |
| `core/runtime.py` | Detecção de plataforma, paths de binários | ✅ Funcional |
| `run.py` | Launcher único (deps, modelo, browser) | ✅ Funcional |
| `musicas_virais.json` | Lista de 19 faixas de música | ✅ Funcional |
| `requirements.txt` | Todas as deps das Fases 1-3 | ✅ Atualizado |
| `static/script.js` | Lógica da UI, fetch para as rotas Flask | ✅ Funcional |
| `static/styles.css` | Estilos da interface | ✅ Funcional |
| `templates/index.html` | Frontend com Bootstrap 5 via CDN | ✅ Funcional |

### O que realmente acontece hoje no código

- **Upload/Download:** Upload local funciona. Download via `yt-dlp` funciona. Usa `nodejs-bin` e `imageio-ffmpeg` para portabilidade.
- **Transcrição:** `faster-whisper` com `word_timestamps=True`. Modelo `tiny` padrão, `small` disponível. Cache JSON em `outputs/`.
- **Score de Viralidade:** Análise real com 4 fatores: sentimento (TextBlob), energia de áudio (librosa RMS), hooks virais (regex), densidade de fala. Score 0-100 com breakdown.
- **Seleção de Segmentos:** Sliding window de 30s com 50% overlap. Top N por score.
- **Reframe 9:16:** Crop central, letterbox preto, ou padding blur via FFmpeg. 3 métodos disponíveis.
- **Legendas:** Word-by-word com ASS karaoke. 4 estilos: tiktok, bold_shadow, neon, minimal.
- **Edição:** `add_captions_and_edit()` usa MoviePy TextClip (lento, requer ImageMagick).
- **Preview:** Cards com player HTML5, score breakdown, download individual.
- **Pipeline atual:** 3 re-encodeções por clip (MoviePy → FFmpeg reframe → FFmpeg legendas).

### Gargalos de Performance Identificados

1. **Triple re-encoding por clip** — cada clip passa por 3 encodeções H.264 (25-60s por clip, 2-5min total para 5 clips).
2. **MoviePy para extração** — `subclip()` + `write_videofile()` é lento vs FFmpeg direto.
3. **Processamento sequencial** — clips processados um a um.
4. **Modelo Whisper recarregado** — `WhisperModel()` chamado a cada request (2-5s).
5. **Transcrição desperdiçada** — vídeos longos (1-3h) transcrevem tudo, mas só 2-5min são usados.
6. **Probe redundante** — `_probe_aspect()` chamado N vezes para o mesmo vídeo.

---

## ARQUITETURA ALVO

### Stack

| Camada | Tecnologia | Motivo |
|---|---|---|
| Backend | Flask (atual) → FastAPI (Fase 4) | Manter compatibilidade; FastAPI para SSE/async |
| Transcrição | `faster-whisper` | 4x mais rápido que whisper padrão, roda em CPU, word timestamps nativos |
| Download | `yt-dlp` (já existe) | Mais robusto e atualizado que pytube/youtube-dl |
| Edição de vídeo | `moviepy` + `ffmpeg-python` | Corte, reframe, legendas burned-in |
| Face detection | `mediapipe` (Google, MIT) | Camera tracking, roda em CPU a 30+ FPS |
| NLP / score | `spacy` + `librosa` | Análise de sentimento + análise de áudio |
| Legendas visuais | `Pillow` + FFmpeg | Renderização frame a frame |
| Node.js | Binário standalone em `/bin/` | Substituir `nodejs-bin` atual |
| FFmpeg | Build estática em `/bin/` | Substituir `imageio-ffmpeg` atual |
| Frontend | Alpine.js + Tailwind CSS (CDN) | Sem build step, reatividade + design moderno |

### Estrutura de Pastas Alvo

```
ViralClipMaker/
├── bin/                         # Binários embutidos por plataforma
│   ├── ffmpeg-win.exe           # Substituir imageio-ffmpeg
│   ├── ffmpeg-macos
│   ├── ffmpeg-linux
│   ├── node-win.exe             # Substituir nodejs-bin
│   ├── node-macos
│   └── node-linux
│
├── core/                        # Módulos de processamento (extrair de video_processing.py)
│   ├── __init__.py
│   ├── runtime.py               # Detecta plataforma, retorna paths de /bin/
│   ├── transcriber.py           # faster-whisper, word_timestamps=True
│   ├── clip_detector.py         # score multi-fator real (substitui lógica randômica)
│   ├── video_editor.py          # corte, reframe 9:16, legendas
│   ├── subtitle_renderer.py     # legendas word-by-word animadas
│   ├── pipeline.py              # NOVO — FFmpeg unificado (crop + scale + ass)
│   ├── face_tracker.py          # mediapipe face detection + auto crop
│   ├── auto_zoom.py             # zoom automático por energia de áudio
│   ├── subtitle_export.py       # export SRT/VTT
│   └── downloader.py            # yt-dlp wrapper (extrair de video_processing.py)
│
├── web/                         # Camada web (mover app.py atual para cá)
│   ├── app.py
│   ├── templates/
│   └── static/
│
├── models/                      # Modelos Whisper (download automático na 1ª execução)
│   └── .gitkeep
│
├── outputs/                     # Clips exportados
├── uploads/                     # Vídeos enviados pelo usuário
├── run.py                       # NOVO — launcher único
├── viralclip/                   # NOVO — módulo CLI
│   ├── __init__.py
│   └── __main__.py             # CLI: python -m viralclip
├── app.py                       # ATUAL — manter até migração para web/ estar completa
├── video_processing.py          # ATUAL — manter até migração para core/ estar completa
├── musicas_virais.json
└── requirements.txt
```

### Pipeline de Processamento (Alvo)

```
[Input: URL YouTube ou arquivo local]
    → 1. DOWNLOAD/IMPORT     (yt-dlp / upload) + normalização FFmpeg
    → 2. TRANSCRIÇÃO         (faster-whisper, word-level timestamps)
    → 3. SCORE DE VIRALIDADE (NLP + energia de áudio + densidade de fala)
    → 4. SELEÇÃO DE SEGMENTOS (top N por score, corte preciso por timestamp)
    → 5. REFRAME 9:16        (crop dinâmico, position editável pelo usuário)
    → 6. CAMERA TRACKING     (suavização do crop frame a frame, opcional)
    → 7. LEGENDAS            (word-by-word, estilo configurável, burned-in)
    → 8. EXPORT              (H.264, preset TikTok 1080×1920 ou custom)
```

### Pipeline Unificado (Fase 3.5)

```
ANTES (3 encodes por clip):
  MoviePy subclip → write_videofile → reframe_9_16 → burn_subtitles
  ~25-60s por clip × 5 clips = 2-5min

DEPOIS (1 encode por clip):
  FFmpeg: -ss {start} -t {duration} -i input
          -vf "crop=W:H:X:Y,scale=1080:1920,ass=subs.ass"
          -c:v libx264 -preset fast -crf 22
  ~8-20s por clip × 5 clips = 40-60s (3-4x mais rápido)
```

---

## DECISÕES DE ARQUITETURA

- **faster-whisper** em vez de whisper padrão: `word_timestamps=True` nativo, 4x mais rápido, INT8 roda em CPU.
- **MediaPipe** em vez de dlib/insightface: MIT license, zero custo, CPU a 30fps.
- **yt-dlp já existe** — apenas encapsular em `core/downloader.py`, não trocar.
- **Binários estáticos em `/bin/`** substituem `nodejs-bin` e `imageio-ffmpeg` — mesma portabilidade, mais controle.
- **Modelos Whisper em `models/`**: `tiny` (~75MB) padrão inicial, `small` (~244MB) recomendado. `WhisperModel(size, download_root="./models")`.
- **Migração incremental**: `app.py` e `video_processing.py` continuam funcionando enquanto `core/` é construído ao lado.
- **Flask mantido até Fase 4**: migrar para FastAPI apenas quando SSE for implementado.
- **Pipeline unificado em `core/pipeline.py`**: crop + scale + ASS em 1 comando FFmpeg. Substitui MoviePy subclip + write_videofile + reframe_9_16 + burn_subtitles.
- **Crop editável via parâmetro**: `export_clip()` aceita `x_offset`/`y_offset`/`zoom_factor`. Posições predefinidas (left/center/right) + valor manual.
- **Transcrição adaptativa**: vídeos > 30min usam transcrição seletiva (top 50% por energia RMS). Vídeos ≤ 30min transcrevem tudo.

---

## ROADMAP — FASES E TAREFAS

> Status: `[ ]` = pendente | `[x]` = concluído | `[~]` = em andamento

### FASE 1 — Fundação & "Download and Play"
**Objetivo:** `python run.py` funciona do zero. Bugs críticos corrigidos.

- [x] **Fix:** Sincronizar assinatura de `add_captions_and_edit` — aceitar `text` como parâmetro em `video_processing.py`
- [x] **Fix:** Corrigir `/edit` e `/suggest_music` para aceitar JSON (`request.get_json()`) em vez de form-data
- [x] **Limpeza:** Remover `SpeechRecognition`, `spotipy` e `redis` do `requirements.txt`
- [x] Criar `run.py` — verifica deps → instala automaticamente → baixa modelo Whisper `tiny` → abre `http://localhost:5000` no browser
- [x] Criar `core/__init__.py` e `core/runtime.py` — detecta plataforma, retorna path dos binários em `/bin/`
- [ ] Criar `/bin/` com FFmpeg estático para Windows, macOS e Linux *(usando imageio-ffmpeg como fallback)*
- [ ] Criar `/bin/` com Node.js standalone para Windows, macOS e Linux *(usando nodejs-bin como fallback)*
- [x] Atualizar `requirements.txt`: adicionar `faster-whisper`, `mediapipe`, `librosa`, `Pillow`, `spacy`
- [x] Criar estrutura `core/` — `web/` fica para quando app.py for migrado

### FASE 2 — Transcrição & Score Real
**Objetivo:** Substituir completamente a lógica randômica por análise real.

- [x] Criar `core/downloader.py` — encapsular `yt-dlp` existente, usando `core/runtime.py`
- [x] Criar `core/transcriber.py` — `faster-whisper`, `word_timestamps=True`, salvar JSON em `outputs/`
  - Sentimento via **TextBlob** (mais leve que spacy para análise inline)
- [x] Criar `core/clip_detector.py` — score multi-fator:
  - sentimento via `TextBlob`
  - picos de energia RMS via `librosa`
  - detecção de hooks (interrogativas, "nunca", "incrível", "você sabia")
  - densidade de fala (palavras/segundo)
- [x] Substituir `analyze_video_for_cuts` e `classify_viral_probability` pelos módulos reais
- [x] Exibir score real nos cards com breakdown dos fatores
- [x] Opção de seleção de modelo Whisper na UI

### FASE 3 — Formato TikTok & Legendas Animadas
**Objetivo:** Clips prontos para publicar — 9:16, legendas word-by-word.

- [x] Criar `core/video_editor.py` — reframe 9:16: crop central, letterbox preto, padding blur via FFmpeg
- [x] Criar `core/subtitle_renderer.py` — word-by-word no timestamp exato, ASS + FFmpeg overlay
- [x] 4 estilos de legenda: `tiktok` (highlight amarelo), `bold_shadow`, `neon`, `minimal`
- [x] Integrado no pipeline: cada clip sai reframed + legendado automaticamente
- [x] UI: presets de tamanho — TikTok Short (15–30s), Medium (30–60s), Long (60–90s), Shorts, Custom
- [x] UI: presets de resolução — TikTok 1080×1920, Reels 1080×1920, Custom
- [x] Camera tracking como toggle opcional (MediaPipe)

### FASE 3.5 — Performance & Pipeline Unificado
**Objetivo:** Eliminar triple re-encoding, reduzir tempo de processamento em ~60-70%.

> Hardware alvo: 8GB RAM, 4+ cores, SSD. Otimizar para criadores de conteúdo (podcasters, editores de vídeo).

- [x] Criar `core/pipeline.py` — FFmpeg unificado: crop + scale + ASS overlay em 1 comando por clip
  - Função `export_clip(video_path, start, end, output_path, ass_path, method, dims)`
  - Substitui: MoviePy subclip + write_videofile + reframe_9_16 + burn_subtitles
  - Redução: 3 encodes/clip → 1 encode/clip
- [x] `core/video_editor.py` — tornar `probe_dimensions()` público + cache dict
  - `reframe_9_16()` aceita `in_w`/`in_h` opcional (pula probe)
- [x] `core/transcriber.py` — singleton WhisperModel + transcrição adaptativa
  - Cache: `_model_cache` com key `model_size:device:compute_type`
  - `release_model_cache()` para liberar memória
  - Vídeos > 30min: transcrição seletiva (top 50% por energia RMS)
  - Vídeos ≤ 30min: transcrição completa (atual)
- [x] `core/clip_detector.py` — áudio via FFmpeg pipe
  - `_audio_to_numpy()`: `ffmpeg -f s16le` → `np.frombuffer()`
  - Substitui `librosa.load()` que carrega tudo em RAM
- [x] `video_processing.py` — pipeline + paralelismo
  - Usar `export_clip()` em vez de 3 chamadas
  - `ProcessPoolExecutor(max_workers=min(cpu_count, 2))`
  - Pré-computar word index com `bisect`
- [x] `app.py` — cleanup pós-processamento (cache dims, ASS temporários)

### FASE 3.6 — Crop Editável & Presets de Duração
**Objetivo:** Permitir ao usuário controlar o enquadramento e duração dos clips.

- [x] Backend: `core/video_editor.py` — suportar crop position customizada
  - `x_offset` e `y_offset` como parâmetros em `_build_filter_crop()`
  - Posições predefinidas: `left`, `center`, `right` + valor manual
  - Zoom: parâmetro `zoom_factor` (1.0 = sem zoom, 1.5 = 50% zoom)
- [x] Backend: `core/pipeline.py` — aceitar crop params no `export_clip()`
- [x] Backend: `core/clip_detector.py` — aceitar `clip_duration` customizado
  - Presets: 15s, 30s, 60s, 90s
- [x] Frontend: UI de edição de crop
  - Slider ou botões de posição (esquerda/centro/direita)
  - Slider de zoom (1.0x a 2.0x)
  - Preview do enquadramento antes de processar
- [x] Frontend: dropdown de duração do clip
  - Opções: 15s, 30s, 60s, 90s
- [x] Frontend: atualizar cards para mostrar posição de crop aplicada
- [x] Integração: enviar crop params do frontend para `/process`

### FASE 4 — UX & Polimento
**Objetivo:** Experiência fluida para leigos e profissionais.

- [x] Redesign completo da UI — Alpine.js + Tailwind CSS
  - 3 estados: Upload → Processing → Results
  - Progressive disclosure (opções avançadas colapsadas)
  - Dark/light mode automático (prefers-color-scheme)
  - Mobile-first, drag & drop, visual feedback
- [x] Migrar para FastAPI (app_fastapi.py com SSE)
- [x] Progresso em tempo real via SSE: download → transcrição → score → reframe → legendas → export
- [x] Toggle Modo Simples / Modo Avançado
- [ ] Editor de timeline manual
- [x] Download em lote (botão "Baixar Todos" → `.zip`)
- [x] Limpeza automática de `uploads/` (arquivos com mais de X horas)
- [x] Histórico de projetos em JSON local

### FASE 5 — Features Avançadas
**Objetivo:** Paridade total com Opus Clip + diferenciais open source.

> **Filosofia:** Tudo deve rodar em hardware modesto (8GB RAM, CPU integrada). Sem dependência de APIs pagas ou modelos de IA pesados. O app é 100% local, gratuito e acessível.

- [x] Modo batch: fila de URLs/arquivos com status individual
- [x] Export de `.srt` / `.vtt` separado
- [x] Zoom automático em momentos-chave (análise de energia de áudio, sem IA)
- [x] CLI: `python -m viralclip video.mp4 --clips 5 --format tiktok`
- [x] Instalador `.exe` (Windows) e `.app` (macOS) via PyInstaller

---

## CONVENÇÕES DO PROJETO

### Python
- Python 3.10+ obrigatório
- Type hints em todas as funções públicas dos módulos `core/`
- Docstrings em inglês, comentários de lógica em português são ok
- Nenhum módulo `core/` importa de `web/` — dependência unidirecional
- Logging via `logging` padrão, não `print()`, exceto em `run.py`

### Commits
- Prefixo por fase: `[F1]`, `[F2]`, etc.
- Exemplo: `[F1] fix mismatch JSON vs form-data nas rotas /edit e /suggest_music`

### FFmpeg
- Atualmente usa `imageio-ffmpeg` — funciona, mas será substituído na Fase 1
- Após Fase 1: sempre usar binário de `/bin/` via `core/runtime.py` — nunca assumir `ffmpeg` no PATH
- Comandos FFmpeg via `ffmpeg-python` ou subprocess com lista (nunca string concatenada)

### Modelos Whisper
- Armazenados em `models/` — nunca em `core/` ou raiz
- Download: `WhisperModel(model_size, download_root="./models")`

### Frontend
- Alpine.js + Tailwind CSS via CDN — sem build step
- Dark/light mode via `prefers-color-scheme` automático
- Sem frameworks JS pesados (sem React, Vue, Angular)
- Novos scripts em `/static/`, nunca inline no HTML exceto para variáveis dinâmicas
- Progressive disclosure para opções avançadas

---

## COMPARATIVO COM OPUS CLIP

| Feature | Opus Clip | ViralClipMaker |
|---|---|---|
| Preço | US$19–49/mês | Gratuito |
| Funciona offline | ❌ Cloud obrigatório | ✅ 100% local |
| Privacidade dos dados | ❌ Upload para servidores | ✅ Dados ficam na máquina |
| Legenda word-by-word | ✅ | ✅ Fase 3 |
| Reframe 9:16 | ✅ | ✅ Fase 3 |
| Detecção de momentos | ✅ IA proprietária | ✅ Análise de áudio + NLP local |
| Camera tracking | ✅ | Fase 3 |
| Crop editável pelo usuário | ✅ | Fase 3.6 |
| Open Source | ❌ Proprietário | ✅ MIT |
| Requisitos de hardware | Alto (cloud) | Baixo (CPU local) |
| Download and play | N/A (SaaS) | ✅ Fase 1 |

---

## NOTAS E GOTCHAS

- **`nodejs-bin` e `imageio-ffmpeg`** são a solução atual de portabilidade — não remover antes de `/bin/` estar pronto e testado nas 3 plataformas.
- **FFmpeg no Windows** exige `.exe` explícito — `runtime.py` precisa tratar isso.
- **`faster-whisper` na 1ª execução** baixa o modelo automaticamente se não encontrar em `models/` — pode demorar; comunicar progresso ao usuário.
- **MediaPipe em alguns setups macOS** pode exigir Rosetta — documentar no README ao chegar na Fase 3.
- **`librosa`** tem dependência de `soundfile` que pode precisar de `libsndfile` no sistema — verificar e documentar.
- **Acoplamento em `video_processing.py`**: download, análise e edição estão misturados na mesma função — separar com cuidado, testando cada extração individualmente.
- **ASS paths com caracteres especiais**: FFmpeg precisa de escape em paths com `:` ou `\`. Linux: OK. Windows: tratar.
- **`add_captions_and_edit()`** continua usando MoviePy `TextClip` (requer ImageMagick). Deve ser substituído por FFmpeg `drawtext` na Fase 4.
- **Flask single-thread**: `ProcessPoolExecutor` funciona, mas se migrar para FastAPI com workers múltiplos, precisa de lock no modelo cache.

---

*Última atualização: 19/06/2026 — Fases 1-3 core concluídas. Adicionadas Fases 3.5 (Performance) e 3.6 (Crop Editável).*