"""
run.py — Ponto de entrada único do ViralClipMaker.

Uso:
    python run.py                  # Modo web (abre o browser automaticamente)
    python run.py --no-browser     # Modo web sem abrir o browser

O que este script faz, em ordem:
    1. Reexecuta dentro da venv do projeto, se necessário (venv/, .venv/, Windows)
    2. Verifica a versão do Python (>= 3.10)
    3. Verifica se as dependências do requirements.txt estão instaladas
    4. Baixa o modelo Whisper 'tiny' se ainda não existir em models/
    5. Garante que as pastas uploads/ e outputs/ existem
    6. Inicia o servidor (FastAPI + uvicorn) e abre http://localhost:5000
"""

import sys
import os
import subprocess
import importlib.util
import argparse

_ROOT = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# Auto-venv (reexecuta dentro da venv do projeto)
# ---------------------------------------------------------------------------

def _venv_python_candidates() -> list[str]:
    """Caminhos possíveis do python da venv: venv/, .venv/, Linux-mac/Windows."""
    candidates = []
    for venv_dir in ("venv", ".venv"):
        candidates.append(os.path.join(_ROOT, venv_dir, "bin", "python"))
        candidates.append(os.path.join(_ROOT, venv_dir, "Scripts", "python.exe"))
    return candidates


def _ensure_venv() -> None:
    """Se não estiver dentro da venv do projeto, reexecuta com o python dela."""
    if sys.prefix != sys.base_prefix:
        return  # já estamos numa venv

    for python_path in _venv_python_candidates():
        if os.path.isfile(python_path):
            print(f"  ▶ Fora da venv — reexecutando com {python_path} ...")
            sys.stdout.flush()
            os.execv(python_path, [python_path] + sys.argv)

    print(
        "  ❌ Venv não encontrada. Crie e instale as dependências:\n"
        "       python -m venv .venv\n"
        "       source .venv/bin/activate        # Windows: .venv\\Scripts\\activate\n"
        "       pip install -r requirements.txt\n"
        "       python run.py"
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

    req_path = os.path.join(_ROOT, "requirements.txt")
    if not os.path.exists(req_path):
        _print("requirements.txt não encontrado — pulando verificação de deps.", "warn")
        return

    # Pacotes cujo módulo importável tem nome diferente do pacote
    NAME_MAP = {
        "imageio-ffmpeg": "imageio_ffmpeg",
        "nodejs-bin": "nodejs",
        "yt-dlp": "yt_dlp",
        "yt-dlp-ejs": None,            # helper interno do yt-dlp, não importável diretamente
        "faster-whisper": "faster_whisper",
        "python-multipart": "python_multipart",
    }

    missing = []
    with open(req_path) as f:
        for raw in f:
            raw = raw.strip()
            if not raw or raw.startswith("#"):
                continue
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
        os.makedirs(os.path.join(_ROOT, d), exist_ok=True)
    _print("Pastas uploads/, outputs/, models/ prontas", "ok")


def download_whisper_model(model_size: str = "tiny") -> None:
    """Baixa o modelo Whisper se ainda não estiver em models/."""
    model_dir = os.path.join(_ROOT, "models")
    # faster-whisper armazena modelos em subpastas como "models--Systran--faster-whisper-tiny"
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
        WhisperModel(model_size, device="cpu", download_root=model_dir)
        _print(f"Modelo Whisper '{model_size}' baixado com sucesso", "ok")
    except ImportError:
        _print(
            "faster-whisper não instalado ainda — modelo será baixado na primeira transcrição.",
            "warn",
        )


def start_server(open_browser: bool = True, port: int = 5000) -> None:
    """Inicia o servidor FastAPI (uvicorn) e opcionalmente abre o browser."""
    import threading
    import webbrowser
    import time

    url = f"http://localhost:{port}"

    if open_browser:
        def _open():
            time.sleep(1.5)
            webbrowser.open(url)
        threading.Thread(target=_open, daemon=True).start()

    _print(f"Iniciando servidor em {url}  (Ctrl+C para encerrar)", "info")

    try:
        import uvicorn
    except ImportError:
        _print("uvicorn não instalado. Rode: pip install -r requirements.txt", "err")
        sys.exit(1)

    uvicorn.run("app:app", host="0.0.0.0", port=port, log_level="info")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    os.chdir(_ROOT)

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
