function app() {
    return {
        // State
        state: 'upload', // 'upload' | 'processing' | 'results'

        // Upload
        url: '',
        file: null,
        fileName: '',
        dragOver: false,

        // Advanced options
        showAdvanced: false,
        simpleMode: false,
        whisperModel: 'tiny',
        clipDuration: 30,
        cropPosition: 'center',
        zoomFactor: 1.0,
        autoZoom: false,
        captionPosition: 'third',
        subtitleStyle: 'tiktok',
        outW: 1080,
        outH: 1920,

        // Processing
        processing: false,
        currentStep: 0,
        progress: 0,
        progressText: '',

        // Results
        clips: [],

        // Edit modal
        showEditModal: false,
        editClip: null,
        editCaption: '',
        editStyle: 'tiktok',
        musicSuggestion: '',

        // Error
        error: '',

        // Options data
        models: [
            { value: 'tiny', label: 'Tiny', desc: 'Rápido (~75MB). Ideal para testes.' },
            { value: 'base', label: 'Base', desc: 'Equilibrado (~142MB).' },
            { value: 'small', label: 'Small', desc: 'Recomendado (~466MB). Mais preciso.' },
        ],
        durations: [
            { value: 15, label: '15s' },
            { value: 30, label: '30s' },
            { value: 60, label: '1min' },
            { value: 90, label: '1:30' },
        ],
        crops: [
            { value: 'auto', label: 'Auto', icon: '🎯' },
            { value: 'left', label: 'Esquerda', icon: '←' },
            { value: 'center', label: 'Centro', icon: '•' },
            { value: 'right', label: 'Direita', icon: '→' },
        ],
        captionPositions: [
            { value: 'bottom', label: 'Base' },
            { value: 'third', label: 'Terço inferior' },
            { value: 'middle', label: 'Meio' },
        ],
        resolutions: [
            { value: 'tiktok', label: 'TikTok', w: 1080, h: 1920 },
            { value: 'reels', label: 'Reels', w: 1080, h: 1920 },
            { value: '720p', label: '720p', w: 720, h: 1280 },
        ],
        styles: [
            { value: 'tiktok', label: 'TikTok', bg: '#ffffff', fg: '#000000', accent: '#facc15' },
            { value: 'bold_shadow', label: 'Bold', bg: '#1f2937', fg: '#ffffff', accent: '#f97316' },
            { value: 'neon', label: 'Neon', bg: '#0f172a', fg: '#22d3ee', accent: '#ec4899' },
            { value: 'minimal', label: 'Minimal', bg: '#f9fafb', fg: '#6b7280', accent: '#9ca3af' },
        ],
        steps: [
            'Baixando vídeo',
            'Extraindo áudio',
            'Transcrevendo áudio',
            'Analisando momentos',
            'Gerando cortes',
        ],

        init() {
            // Nothing needed on init
        },

        handleDrop(event) {
            this.dragOver = false;
            const files = event.dataTransfer.files;
            if (files.length > 0) {
                this.setFile(files[0]);
            }
        },

        handleFile(event) {
            const files = event.target.files;
            if (files.length > 0) {
                this.setFile(files[0]);
            }
        },

        setFile(file) {
            if (!file.type.startsWith('video/')) {
                this.error = 'Por favor, selecione um arquivo de vídeo.';
                return;
            }
            this.file = file;
            this.fileName = file.name;
            this.url = '';
            this.error = '';
        },

        // Mapa dos passos do backend para o índice do checklist da UI
        sseSteps: { download: 0, transcribe: 2, analyze: 3, generate: 4, done: 5 },

        async processVideo() {
            if (!this.url && !this.file) {
                this.error = 'Por favor, selecione um vídeo ou cole uma URL.';
                return;
            }

            this.error = '';
            this.processing = true;
            this.state = 'processing';
            this.currentStep = 0;
            this.progress = 0;

            try {
                const formData = new FormData();
                formData.append('whisper_model', this.whisperModel);
                formData.append('clip_duration', this.clipDuration);
                formData.append('crop_position', this.cropPosition);
                formData.append('zoom_factor', this.zoomFactor);
                formData.append('auto_zoom', this.autoZoom);
                formData.append('caption_position', this.captionPosition);
                formData.append('subtitle_style', this.subtitleStyle);
                formData.append('output_width', this.outW);
                formData.append('output_height', this.outH);

                if (this.url) {
                    formData.append('input_type', 'url');
                    formData.append('url', this.url);
                } else {
                    formData.append('input_type', 'file');
                    formData.append('file', this.file);
                }

                const response = await fetch('/process-stream', {
                    method: 'POST',
                    body: formData,
                });

                // Erros "de infra" chegam como JSON; progresso chega como SSE
                if (!response.ok || !(response.headers.get('content-type') || '').includes('event-stream')) {
                    const data = await response.json().catch(() => ({}));
                    throw new Error(data.error || `Erro no servidor (${response.status})`);
                }

                const result = await this._readSSE(response);

                // Small delay then show results
                await new Promise(r => setTimeout(r, 400));

                this.clips = (result.clips || []).map(c => ({ ...c, expanded: false }));
                this.state = 'results';
                this.saveToHistory();

            } catch (err) {
                this.error = err.message || 'Ocorreu um erro ao processar o vídeo.';
                this.state = 'upload';
            } finally {
                this.processing = false;
            }
        },

        async _readSSE(response) {
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            let finalEvent = null;

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });

                let idx;
                while ((idx = buffer.indexOf('\n\n')) !== -1) {
                    const rawEvent = buffer.slice(0, idx);
                    buffer = buffer.slice(idx + 2);

                    const dataLine = rawEvent
                        .split('\n')
                        .find(l => l.startsWith('data: '));
                    if (!dataLine) continue;

                    let evt;
                    try {
                        evt = JSON.parse(dataLine.slice(6));
                    } catch { continue; }

                    if (evt.error) throw new Error(evt.error);

                    if (evt.progress !== undefined) this.progress = evt.progress;
                    if (evt.message) this.progressText = evt.message;
                    if (evt.step && evt.step in this.sseSteps) {
                        this.currentStep = this.sseSteps[evt.step];
                    }
                    if (evt.step === 'done') finalEvent = evt;
                }
            }

            if (!finalEvent) {
                throw new Error('O servidor encerrou sem concluir o processamento.');
            }
            return finalEvent;
        },

        downloadClip(clip) {
            const filename = clip.path.split('/').pop();
            window.location.href = `/download/${filename}`;
        },

        openEdit(clip) {
            this.editClip = clip;
            this.editCaption = '';
            this.editStyle = this.subtitleStyle;
            this.showEditModal = true;
            this.fetchMusicSuggestion();
        },

        async applyEdit() {
            if (!this.editClip || !this.editCaption) return;

            try {
                const response = await fetch('/edit', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        clip_path: this.editClip.path,
                        text: this.editCaption,
                    }),
                });

                const data = await response.json();

                if (data.edited_path) {
                    const filename = data.edited_path.split('/').pop();
                    window.location.href = `/download/${filename}`;
                    this.showEditModal = false;
                } else {
                    alert(data.error || 'Erro ao aplicar edição.');
                }
            } catch (err) {
                alert('Erro de comunicação ao editar.');
            }
        },

        async fetchMusicSuggestion() {
            try {
                const response = await fetch('/suggest_music', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ theme: 'energetic' }),
                });
                const data = await response.json();
                this.musicSuggestion = data.music || '';
            } catch (err) {
                // Silently ignore
            }
        },

        async exportSubtitles(clip, format) {
            try {
                const response = await fetch('/export-subtitles', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        clip_path: clip.path,
                        format,
                        segments: clip.segments || null,
                    }),
                });
                if (!response.ok) throw new Error('Erro ao exportar');
                const blob = await response.blob();
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = clip.path.split('/').pop().replace('.mp4', `.${format}`);
                a.click();
                URL.revokeObjectURL(url);
            } catch (err) {
                alert('Erro ao exportar legendas.');
            }
        },

        async saveToHistory() {
            try {
                await fetch('/history', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        source: this.url || this.fileName,
                        clips: this.clips.length,
                    }),
                });
            } catch (err) {
                // Silently ignore
            }
        },

        reset() {
            this.state = 'upload';
            this.url = '';
            this.file = null;
            this.fileName = '';
            this.clips = [];
            this.error = '';
            this.processing = false;
            this.currentStep = 0;
            this.progress = 0;
        },

        async downloadAll() {
            const paths = this.clips.map(c => c.path);
            try {
                const response = await fetch('/download-all', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ paths }),
                });
                if (!response.ok) throw new Error('Erro ao baixar');
                const blob = await response.blob();
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'clips.zip';
                a.click();
                URL.revokeObjectURL(url);
            } catch (err) {
                alert('Erro ao baixar clips.');
            }
        },
    };
}
