document.addEventListener('DOMContentLoaded', (event) => {
    // Show URL input by default
    document.getElementById('file_input').style.display = 'none';
    document.getElementById('url_input').style.display = 'block';
});

document.getElementById('input_type').addEventListener('change', function() {
    const type = this.value;
    document.getElementById('file_input').style.display = type === 'file' ? 'block' : 'none';
    document.getElementById('url_input').style.display = type === 'url' ? 'block' : 'none';
});

document.getElementById('uploadForm').addEventListener('submit', function(e) {
    e.preventDefault();
    
    const processBtn = document.getElementById('process-btn');
    const spinner = document.getElementById('spinner');
    const errorAlert = document.getElementById('error-alert');
    const resultsDiv = document.getElementById('results');
    const clipsList = document.getElementById('clipsList');
    
    // 1. Reset UI
    processBtn.disabled = true;
    spinner.style.display = 'inline-block';
    errorAlert.style.display = 'none';
    resultsDiv.style.display = 'none';
    clipsList.innerHTML = '';
    document.getElementById('editSection').style.display = 'none'; // Hide edit section on new process

    const formData = new FormData(this);
    
    fetch('/process', {
        method: 'POST',
        body: formData
    })
    .then(response => {
        if (!response.ok) {
            return response.json().then(err => Promise.reject(err));
        }
        return response.json();
    })
    .then(data => {
        if (data.error) {
            errorAlert.innerText = data.error;
            errorAlert.style.display = 'block';
        } else {
            displayClips(data.clips);
        }
    })
    .catch(error => {
        console.error('Fetch Error:', error);
        const errorMessage = error.error || 'Ocorreu um erro inesperado. Verifique o console para mais detalhes.';
        errorAlert.innerText = errorMessage;
        errorAlert.style.display = 'block';
    })
    .finally(() => {
        processBtn.disabled = false;
        spinner.style.display = 'none';
    });
});

function displayClips(clips) {
    const list = document.getElementById('clipsList');
    list.innerHTML = ''; // Clear previous results

    if (clips.length === 0) {
        list.innerHTML = '<p class="text-center">Nenhum corte foi gerado a partir deste vídeo.</p>';
        document.getElementById('results').style.display = 'block';
        return;
    }

    clips.forEach((clip, index) => {
        const clipFileName = clip.path.split('/').pop();
        const videoUrl = `/uploads/${clipFileName}`;

        const cardColumn = document.createElement('div');
        cardColumn.className = 'col-md-6 col-lg-4';

        cardColumn.innerHTML = `
            <div class="card h-100 shadow-sm">
                <video src="${videoUrl}" class="card-img-top" controls preload="metadata"></video>
                <div class="card-body">
                    <h5 class="card-title">Corte ${index + 1}</h5>
                    <p class="card-text mb-2">
                        <strong>Viral Score:</strong> 
                        <span class="badge bg-success">${clip.prob}%</span>
                    </p>
                    <p class="card-text text-muted">
                        <strong>Duração:</strong> ${Math.round(clip.duration)}s
                    </p>
                </div>
                <div class="card-footer bg-white border-top-0 pb-3">
                    <button class="btn btn-sm btn-primary w-100 mb-2" onclick="downloadClip('${clip.path}')">Download</button>
                    <button class="btn btn-sm btn-outline-secondary w-100" onclick="selectForEdit('${clip.path}')">Editar Legenda</button>
                </div>
            </div>
        `;
        list.appendChild(cardColumn);
    });
    document.getElementById('results').style.display = 'block';
}

function downloadClip(path) {
    // The path from backend includes 'uploads/', but the download route is just /download/<filename>
    const filename = path.split('/').pop();
    window.location.href = `/download/${filename}`;
}

function selectForEdit(path) {
    const editSection = document.getElementById('editSection');
    editSection.style.display = 'block';
    
    const filename = path.split('/').pop();
    const videoUrl = `/uploads/${filename}`;

    // Add a video preview to the edit section
    document.getElementById('editPreview').innerHTML = `
        <p class="text-center">Editando:</p>
        <video src="${videoUrl}" class="img-fluid rounded" controls></video>
    `;

    document.getElementById('editBtn').onclick = function() {
        const text = document.getElementById('captionText').value;
        // Simple loading state for edit button
        this.disabled = true;
        this.innerText = 'Aplicando...';

        fetch('/edit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ clip_path: path, text: text })
        })
        .then(response => response.json())
        .then(data => {
            if (data.edited_path) {
                alert('Edição aplicada! O download começará em seguida.');
                downloadClip(data.edited_path);
            } else {
                alert(data.error || 'Ocorreu um erro na edição.');
            }
        })
        .catch(err => {
            console.error('Edit Error:', err);
            alert('Ocorreu um erro de comunicação ao editar.');
        })
        .finally(() => {
            this.disabled = false;
            this.innerText = 'Aplicar Edição e Baixar';
        });
    };
    
    // Scroll to edit section for better UX on mobile
    editSection.scrollIntoView({ behavior: 'smooth' });

    // Suggest music
    fetch('/suggest_music', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ theme: 'energetic' })
    })
    .then(response => response.json())
    .then(data => {
        document.getElementById('musicSuggestion').innerHTML = `<p class="mt-3 text-center"><strong>Sugestão de Música:</strong> ${data.music}</p>`;
    });
}
