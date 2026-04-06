from __future__ import annotations

import re
from typing import Any, Dict


_EMAIL_RE = re.compile(r"\b[\w\.-]+@[\w\.-]+\.\w+\b", re.IGNORECASE)
_PHONE_RE = re.compile(r"\b(?:\+?\d[\d\s\-]{8,}\d)\b")
_ACCOUNT_RE = re.compile(r"\b\d{10,19}\b")
_FULLNAME_RE = re.compile(
    r"\b(?:[А-ЯЁ][а-яё]+)\s+(?:[А-ЯЁ][а-яё]+)(?:\s+(?:[А-ЯЁ][а-яё]+))?\b"
)


def redact_text(text: str) -> str:
    """
    Эвристическое маскирование потенциально конфиденциальных данных.
    Цель: снизить риск утечек в LLM и в audit_log.
    """
    if not text:
        return text

    out = text
    out = _EMAIL_RE.sub("[EMAIL]", out)
    out = _PHONE_RE.sub("[PHONE]", out)
    out = _ACCOUNT_RE.sub("[ACCOUNT]", out)
    # Маскируем ФИО (частично, чтобы не ломать синтаксис)
    out = _FULLNAME_RE.sub("[NAME]", out)
    return out


def redact_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    На текущем этапе редактируем только строки.
    """
    out: Dict[str, Any] = {}
    for k, v in payload.items():
        if isinstance(v, str):
            out[k] = redact_text(v)
        else:
            out[k] = v
    return out


