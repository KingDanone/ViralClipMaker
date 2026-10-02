"""
core/history.py — Histórico local de projetos (JSON, máx. 50 entradas).
"""

import os
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HISTORY_FILE = os.path.join(_ROOT, "history.json")
_MAX_ENTRIES = 50


def load_history() -> list:
    """Retorna o histórico salvo (lista, mais recente primeiro)."""
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        logger.warning("history.json inválido — ignorando")
        return []


def append_history(data: dict) -> dict:
    """Adiciona uma entrada ao histórico e persiste. Retorna a entrada salva."""
    entry = dict(data)
    entry["timestamp"] = datetime.now().isoformat()

    history = load_history()
    history.insert(0, entry)
    history = history[:_MAX_ENTRIES]

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    return entry
