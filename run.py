"""
run.py — Ponto de entrada único do ViralClipMaker.

Uso:
    python run.py          # Modo web (abre o browser automaticamente)
    python run.py --no-browser  # Modo web sem abrir o browser

O que este script faz, em ordem:
    1. Verifica a versão do Python (>= 3.10)
    2. Verifica se todas as dependências do requirements.txt estão instaladas
    3. Baixa o modelo Whisper 'tiny' se ainda não existir em models/
    4. Garante que as pastas uploads/ e outputs/ existem
    5. Inicia o servidor Flask e abre http://localhost:5000 no browser padrão
"""

import sys
import os
import subprocess
import importlib.util
import argparse

# ---------------------------------------------------------------------------
# Auto-venv (executa tudo dentro da venv do projeto)
# ---------------------------------------------------------------------------

def _ensure_venv() -> None:
    """Se não estiver dentro da venv do projeto, reexecuta com venv/bin/python."""
    if sys.prefix != sys.base_prefix:
        return  # já estamos na venv
    venv_python = os.path.join(os.path.dirname(os.path.abspath(__file__)), "venv", "bin", "python")
    if os.path.isfile(venv_python):
        _print("Fora da venv detectado — reexecutando com venv/bin/python ...", "warn")
        sys.stdout.flush()
        os.execv(venv_python, [venv_python] + sys.argv)
    _print(
        "Execute o projeto dentro da venv:\n"
        "    source venv/bin/activate\n"
        "    pip install -r requirements.txt\n"
        "    python run.py",
        "err",
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _print(msg: str, level: str = "info") -> None:
    prefix = {"info": "▶", "ok": "✅", "warn": "⚠️ ", "err": "❌"}
    print(f"  {prefix.get(level, '▶')} {msg}")


def check_python_version() -> None:
    if sys.version_info < (3, 10):
        _print(f"Python 3.10+ obrigatório. Você está usando {sys.version}", "err")
        sys.exit(1)
    _print(f"Python {sys.version_info.major}.{sys.version_info.minor} detectado", "ok")


def check_dependencies() -> None:
    """Verifica se os pacotes críticos estão instalados; instala se necessário."""
    _print("Verificando dependências...")

    req_path = os.path.join(os.path.dirname(__file__), "requirements.txt")
    if not os.path.exists(req_path):
        _print("requirements.txt não encontrado — pulando verificação de deps.", "warn")
        return

    # Pacotes que não têm um módulo importável com o mesmo nome
    NAME_MAP = {
        "opencv-python": "cv2",
        "imageio-ffmpeg": "imageio_ffmpeg",
        "nodejs-bin": "nodejs",
        "yt-dlp": "yt_dlp",
        "yt-dlp-ejs": None,          # helper interno do yt-dlp, não importável diretamente
        "faster-whisper": "faster_whisper",
        "Pillow": "PIL",
        "pillow": "PIL",
        "SpeechRecognition": "speech_recognition",
    }

    missing = []
    with open(req_path) as f:
        for raw in f:
            raw = raw.strip()
            # Ignorar linhas vazias e comentários
            if not raw or raw.startswith("#"):
                continue
            # Remover versão pinada, e.g. "Flask==3.1.2" → "Flask"
            pkg_name = raw.split("==")[0].split(">=")[0].split("<=")[0].strip()
            import_name = NAME_MAP.get(pkg_name, pkg_name.replace("-", "_").lower())
            if import_name is None:
                continue
            if importlib.util.find_spec(import_name) is None:
                missing.append(pkg_name)

    if missing:
        _print(f"Instalando pacotes ausentes: {', '.join(missing)}", "warn")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet"] + missing
        )
        _print("Instalação concluída", "ok")
    else:
        _print("Todas as dependências satisfeitas", "ok")


def ensure_dirs() -> None:
    """Cria as pastas essenciais se não existirem."""
    for d in ("uploads", "outputs", "models"):
        os.makedirs(d, exist_ok=True)
    _print("Pastas uploads/, outputs/, models/ prontas", "ok")


def download_whisper_model(model_size: str = "tiny") -> None:
    """Baixa o modelo Whisper se ainda não estiver em models/."""
    model_dir = os.path.join(os.path.dirname(__file__), "models")
    # faster-whisper armazena modelos em subpastas como "models/models--Systran--faster-whisper-tiny"
    # Verificamos se alguma subpasta do modelo já existe antes de baixar.
    already_present = any(
        model_size in entry for entry in os.listdir(model_dir)
    ) if os.path.exists(model_dir) else False

    if already_present:
        _print(f"Modelo Whisper '{model_size}' já presente em models/", "ok")
        return

    try:
        from faster_whisper import WhisperModel

        _print(
            f"Baixando modelo Whisper '{model_size}' (~75 MB para 'tiny'). "
            "Isso pode levar alguns minutos na primeira execução...",
            "warn",
        )
        # Instanciar o modelo dispara o download automaticamente.
        WhisperModel(model_size, device="cpu", download_root=model_dir)
        _print(f"Modelo Whisper '{model_size}' baixado com sucesso", "ok")
    except ImportError:
        _print(
            "faster-whisper não instalado ainda — modelo será baixado na primeira transcrição.",
            "warn",
        )


def start_server(open_browser: bool = True, port: int = 5000) -> None:
    """Inicia o Flask e, opcionalmente, abre o browser."""
    import threading
    import webbrowser
    import time

    url = f"http://localhost:{port}"

    if open_browser:
        def _open():
            time.sleep(1.5)  # Dá tempo para o Flask subir
            webbrowser.open(url)

        threading.Thread(target=_open, daemon=True).start()

    _print(f"Iniciando servidor em {url}  (Ctrl+C para encerrar)", "info")

    from app import app as flask_app

    try:
        from waitress import serve
        serve(flask_app, host="0.0.0.0", port=port)
    except ImportError:
        flask_app.run(host="0.0.0.0", port=port, debug=False)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="ViralClipMaker — launcher único"
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Não abrir o browser automaticamente",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="Porta do servidor web (padrão: 5000)",
    )
    parser.add_argument(
        "--whisper-model",
        default="tiny",
        choices=["tiny", "base", "small", "medium", "large-v2", "large-v3"],
        help="Tamanho do modelo Whisper a baixar/usar (padrão: tiny)",
    )
    args = parser.parse_args()

    print("\n🎬  ViralClipMaker — iniciando...\n")

    _ensure_venv()
    check_python_version()
    check_dependencies()
    ensure_dirs()
    download_whisper_model(args.whisper_model)

    print()
    start_server(open_browser=not args.no_browser, port=args.port)


if __name__ == "__main__":
    main()
