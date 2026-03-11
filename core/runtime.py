"""
core/runtime.py — Detecta a plataforma e retorna os caminhos corretos
para os binários embutidos no diretório /bin/.

Uso:
    from core.runtime import get_ffmpeg_path, get_node_path

Durante a Fase 1, enquanto os binários estáticos em /bin/ ainda não estão
incluídos no repositório, o módulo cai de volta para os binários instalados
via pacotes Python (imageio-ffmpeg e nodejs-bin), garantindo que o resto do
código já use a API final sem precisar mudar quando /bin/ for preenchido.
"""

import os
import platform
import sys
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BIN_DIR = os.path.join(_ROOT, "bin")

_SYSTEM = platform.system()  # "Windows", "Darwin", "Linux"


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _bin_path(*parts: str) -> str:
    """Monta o caminho absoluto para um binário dentro de /bin/."""
    return os.path.join(_BIN_DIR, *parts)


def _is_exec(path: str) -> bool:
    """Retorna True se o path existir e for executável."""
    return os.path.isfile(path) and os.access(path, os.X_OK)


# ---------------------------------------------------------------------------
# FFmpeg
# ---------------------------------------------------------------------------

def get_ffmpeg_path() -> str:
    """
    Retorna o caminho para o executável do FFmpeg.

    Ordem de preferência:
        1. Binário estático em /bin/  (alvo pós-Fase 1)
        2. imageio-ffmpeg             (fallback atual, Fase 1)
        3. ffmpeg no PATH do sistema  (último recurso)

    Raises:
        RuntimeError: Se nenhum FFmpeg for encontrado.
    """
    # 1. Binário estático em /bin/
    candidates = {
        "Windows": _bin_path("ffmpeg-win.exe"),
        "Darwin":  _bin_path("ffmpeg-macos"),
        "Linux":   _bin_path("ffmpeg-linux"),
    }
    static = candidates.get(_SYSTEM)
    if static and _is_exec(static):
        logger.debug("FFmpeg: usando binário estático em %s", static)
        return static

    # 2. imageio-ffmpeg (instalado via requirements.txt)
    try:
        import imageio_ffmpeg
        path = imageio_ffmpeg.get_ffmpeg_exe()
        if path and _is_exec(path):
            logger.debug("FFmpeg: usando imageio-ffmpeg em %s", path)
            return path
    except ImportError:
        pass

    # 3. ffmpeg no PATH do sistema
    import shutil
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        logger.debug("FFmpeg: usando ffmpeg do sistema em %s", system_ffmpeg)
        return system_ffmpeg

    raise RuntimeError(
        "FFmpeg não encontrado. Instale imageio-ffmpeg (`pip install imageio-ffmpeg`) "
        "ou adicione ffmpeg ao PATH do sistema."
    )


# ---------------------------------------------------------------------------
# Node.js
# ---------------------------------------------------------------------------

def get_node_path() -> str:
    """
    Retorna o caminho para o executável do Node.js.

    Ordem de preferência:
        1. Binário estático em /bin/  (alvo pós-Fase 1)
        2. nodejs-bin                 (fallback atual, Fase 1)
        3. node no PATH do sistema    (último recurso)

    Raises:
        RuntimeError: Se nenhum Node.js for encontrado.
    """
    # 1. Binário estático em /bin/
    candidates = {
        "Windows": _bin_path("node-win.exe"),
        "Darwin":  _bin_path("node-macos"),
        "Linux":   _bin_path("node-linux"),
    }
    static = candidates.get(_SYSTEM)
    if static and _is_exec(static):
        logger.debug("Node.js: usando binário estático em %s", static)
        return static

    # 2. nodejs-bin (instalado via requirements.txt)
    try:
        import nodejs
        path = nodejs.node.path
        if path and _is_exec(path):
            logger.debug("Node.js: usando nodejs-bin em %s", path)
            return path
    except ImportError:
        pass

    # 3. node no PATH do sistema
    import shutil
    system_node = shutil.which("node")
    if system_node:
        logger.debug("Node.js: usando node do sistema em %s", system_node)
        return system_node

    raise RuntimeError(
        "Node.js não encontrado. Instale nodejs-bin (`pip install nodejs-bin`) "
        "ou adicione node ao PATH do sistema."
    )


# ---------------------------------------------------------------------------
# PATH helpers (para yt-dlp e outros que dependem de NODE no PATH)
# ---------------------------------------------------------------------------

def patch_env_path() -> None:
    """
    Adiciona os diretórios dos binários (FFmpeg e Node.js) ao PATH do processo,
    para que ferramentas externas como yt-dlp os encontrem automaticamente.
    Se um binário não estiver disponível, registra um aviso e segue em frente.
    """
    additions = []

    for getter in (get_ffmpeg_path, get_node_path):
        try:
            bin_path = getter()
            bin_dir = os.path.dirname(bin_path)
            if bin_dir not in os.environ.get("PATH", ""):
                additions.append(bin_dir)
        except RuntimeError as exc:
            logger.warning("patch_env_path: %s", exc)

    if additions:
        os.environ["PATH"] = os.pathsep.join(additions) + os.pathsep + os.environ.get("PATH", "")
        logger.debug("PATH atualizado com: %s", additions)


# ---------------------------------------------------------------------------
# Info
# ---------------------------------------------------------------------------

def runtime_info() -> dict:
    """Retorna um dict com info resumida do ambiente — útil para logging/debug."""
    info: dict = {
        "platform": _SYSTEM,
        "python": sys.version,
        "ffmpeg": None,
        "node": None,
    }
    for key, getter in (("ffmpeg", get_ffmpeg_path), ("node", get_node_path)):
        try:
            info[key] = getter()
        except RuntimeError:
            info[key] = "não encontrado"
    return info
