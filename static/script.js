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

            // Simulate step progress while waiting
            const stepInterval = setInterval(() => {
                if (this.currentStep < this.steps.length - 1) {
                    this.currentStep++;
                    this.progress = Math.min(90, this.currentStep * 20);
                }
            }, 3000);

            try {
                const formData = new FormData();
                formData.append('whisper_model', this.whisperModel);
                formData.append('clip_duration', this.clipDuration);
                formData.append('crop_position', this.cropPosition);
                formData.append('zoom_factor', this.zoomFactor);
                formData.append('subtitle_style', this.subtitleStyle);

                if (this.url) {
                    formData.append('input_type', 'url');
                    formData.append('url', this.url);
                    this.progressText = 'Baixando vídeo do YouTube...';
                } else {
                    formData.append('input_type', 'file');
                    formData.append('file', this.file);
                    this.progressText = 'Enviando arquivo...';
                }

                const response = await fetch('/process', {
                    method: 'POST',
                    body: formData,
                });

                const data = await response.json();

                if (data.error) {
                    throw new Error(data.error);
                }

                // Complete progress
                this.currentStep = this.steps.length;
                this.progress = 100;
                this.progressText = 'Concluído!';

                // Small delay then show results
                await new Promise(r => setTimeout(r, 500));

                this.clips = (data.clips || []).map(c => ({ ...c, expanded: false }));
                this.state = 'results';
                this.saveToHistory();

            } catch (err) {
                this.error = err.message || 'Ocorreu um erro ao processar o vídeo.';
                this.state = 'upload';
            } finally {
                clearInterval(stepInterval);
                this.processing = false;
            }
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
